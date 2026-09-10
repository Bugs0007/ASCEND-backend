"""
All API views. Two authentication code paths, deliberately separate:

  * TokenAuthentication (human) guards analytics and the block-tap actions.
  * IngestTokenAuthentication (machine) guards /api/ingest/*.
  * /api/today/ and /api/email-queue/ accept either — the frontend polls
    the same endpoints the scheduled Claude tasks read.
  * /api/health/ requires neither (cron-job.org keep-warm hits this).
"""
import re

import django_filters
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import IntegerField, Max, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import authentication, generics, permissions
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from core.analytics import activity, burnup, certtrend, correlations, decay, funnel, losses, observations, rhythm, streaks
from core.auth import IngestTokenAuthentication
from core.constants import PROGRAM_START
from core.ingest import run_ingest, run_sleep_event_ingest
from core.models import (
    Application,
    BacklogItem,
    Block,
    BlockEntry,
    CertDomain,
    ContentPost,
    Countdown,
    Course,
    DailyLog,
    DailyRecommendation,
    EmailEvent,
    Milestone,
    NotionTask,
    Reflection,
    Skill,
    SleepLog,
    TodaySelection,
    daily_minutes_total,
)
from core import notion_sync
from core.serializers import (
    BlockEntryUndoSerializer,
    CountdownPatchSerializer,
    DailyRecommendationItemSerializer,
    NotionTaskStatusPatchSerializer,
    SleepEventSerializer,
    SleepLogPatchSerializer,
    TodaySelectionItemSerializer,
    TodaySelectionPatchSerializer,
)
from core.serializers_read import (
    ApplicationReadSerializer,
    CertDomainReadSerializer,
    ContentPostReadSerializer,
    CourseReadSerializer,
    DailyLogReadSerializer,
    MilestoneReadSerializer,
    NotionTaskReadSerializer,
    ReflectionReadSerializer,
    SkillReadSerializer,
    SleepLogReadSerializer,
)


# --------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------

class HealthView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        # Actually touch the DB — this is what cron-job.org pings every 10
        # minutes to keep the Render free instance warm (docs/SETUP.md).
        user_count = get_user_model().objects.count()
        return Response({"status": "ok", "db": "ok", "users": user_count, "time": timezone.now()})


# --------------------------------------------------------------------------
# Ingest (machine token only)
# --------------------------------------------------------------------------

class IngestView(APIView):
    authentication_classes = [IngestTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        summary = run_ingest(request.data, request.user)
        return Response(summary)


class IngestSleepView(APIView):
    authentication_classes = [IngestTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = SleepEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        obj, created = run_sleep_event_ingest(data["event"], data["at"], request.user)
        return Response(
            {
                "log_date": obj.log_date,
                "created": created,
                "bed_at": obj.bed_at,
                "wake_at": obj.wake_at,
                "hours": obj.hours,
            }
        )


# --------------------------------------------------------------------------
# Serialization helpers (plain dicts — these endpoints are read-only
# aggregates, not generic CRUD resources, so a full ModelSerializer would
# be more machinery than the job needs)
# --------------------------------------------------------------------------

def _serialize_daily_log(log):
    return {
        "log_date": log.log_date,
        "deep_work_minutes": log.deep_work_minutes,
        "energy": log.energy,
        "steps_after_10": log.steps_after_10,
        "gym": log.gym,
        "last_caffeine_at": log.last_caffeine_at,
        "mood": log.mood,
        "notes": log.notes,
    }


def _serialize_milestone(m):
    return {
        "id": m.id,
        "title": m.title,
        "project": m.project.code if m.project_id else None,
        "category": m.category,
        "due_date": m.due_date,
        "status": m.status,
        "completed_on": m.completed_on,
        "evidence_url": m.evidence_url,
    }


def _serialize_countdown(c):
    days_left = (c.target_date - timezone.localdate()).days if c.target_date else None
    return {
        "label": c.label,
        "target_date": c.target_date,
        "days_left": days_left,
        "editable": c.editable,
    }


def _serialize_block_entry(entry):
    return {
        "id": entry.id,
        "log_date": entry.daily_log.log_date,
        "block": entry.block.code,
        "completed": entry.completed,
        "started_at": entry.started_at,
        "ended_at": entry.ended_at,
        "elapsed_minutes": entry.elapsed_minutes,
        "active_minutes": entry.active_minutes,
        "what": entry.what,
    }


def _serialize_today_selection(s):
    return {
        "id": s.id,
        "date": s.date,
        "source_type": s.source_type,
        "source_id": s.source_id,
        "title": s.title,
        "block": s.block.code if s.block_id else None,
        "minutes_spent": s.minutes_spent,
        "done": s.done,
        "position": s.position,
    }


def _serialize_recommendation(r):
    return {
        "id": r.id,
        "title": r.title,
        "rationale": r.rationale,
        "source_project": r.source_project,
        "date": r.date,
    }


def _date_param(request, name="date"):
    """?date=YYYY-MM-DD -> a date, or None if absent. A malformed value is a
    400 rather than a silent fall-through to today."""
    raw = request.query_params.get(name)
    if not raw:
        return None
    parsed = parse_date(raw)
    if parsed is None:
        raise DRFValidationError({name: "Expected YYYY-MM-DD."})
    return parsed


# Mirrors the frontend's grouping.ts isDoneLikeStatus() — a Notion row whose
# status reads as finished is not "open" for planning.
_DONE_LIKE_STATUS = re.compile(r"done|complete|shipped|closed|archived", re.IGNORECASE)


def _notion_status_is_open(status):
    return not _DONE_LIKE_STATUS.search(status or "")


# --------------------------------------------------------------------------
# /api/today/ and /api/email-queue/ — dual auth (human token or ingest token)
# --------------------------------------------------------------------------

class TodayView(APIView):
    authentication_classes = [authentication.TokenAuthentication, IngestTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        today = timezone.localdate()

        countdowns = [_serialize_countdown(c) for c in Countdown.objects.all()]

        if today < PROGRAM_START:
            return Response(
                {
                    "status": "pre_start",
                    "today": today,
                    "program_start": PROGRAM_START,
                    "days_to_start": (PROGRAM_START - today).days,
                    "countdowns": countdowns,
                }
            )

        daily_log = DailyLog.objects.filter(log_date=today).first()

        selections = (
            TodaySelection.objects.filter(date=today).select_related("block")
        )

        open_milestones = Milestone.objects.open().select_related("project").order_by("due_date")[:50]
        shippable_milestones = Milestone.objects.shippable().select_related("project")

        return Response(
            {
                "status": "active",
                "today": today,
                "daily_log": _serialize_daily_log(daily_log) if daily_log else None,
                # Computed replacement for the deprecated day-level
                # deep_work_minutes quick-log — sum of today's minutes_spent.
                "deep_work_total": daily_minutes_total(today),
                "today_selections": [_serialize_today_selection(s) for s in selections],
                "streak": streaks.current_streak(as_of=today),
                "open_milestones": [_serialize_milestone(m) for m in open_milestones],
                "shippable_milestones": [_serialize_milestone(m) for m in shippable_milestones],
                "decay_alerts": decay.compute(as_of=today),
                "unmatched_email_count": EmailEvent.objects.filter(matched=False).count(),
                "countdowns": countdowns,
            }
        )


class EmailQueueView(APIView):
    authentication_classes = [authentication.TokenAuthentication, IngestTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        events = EmailEvent.objects.filter(matched=False).order_by("-received_at")
        return Response(
            {
                "count": events.count(),
                "results": [
                    {
                        "id": e.id,
                        "gmail_message_id": e.gmail_message_id,
                        "received_at": e.received_at,
                        "from_address": e.from_address,
                        "subject": e.subject,
                        "classified_as": e.classified_as,
                        "resolved": e.resolved,
                    }
                    for e in events
                ],
            }
        )


# --------------------------------------------------------------------------
# Block start/complete (human token only) — "started_at stamped on first
# tap" needs an interactive endpoint; ingest is for the machine, this is for
# the live frontend.
# --------------------------------------------------------------------------

class BlockStartView(APIView):
    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, code):
        block = get_object_or_404(Block, code=code)
        today = timezone.localdate()
        daily_log, _ = DailyLog.objects.get_or_create(log_date=today, defaults={"owner": request.user})
        entry, _ = BlockEntry.objects.get_or_create(
            daily_log=daily_log, block=block, defaults={"owner": request.user}
        )
        if entry.started_at is None:
            entry.started_at = timezone.now()
            entry.save()
        return Response(_serialize_block_entry(entry))


class BlockCompleteView(APIView):
    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, code):
        block = get_object_or_404(Block, code=code)
        today = timezone.localdate()
        try:
            daily_log = DailyLog.objects.get(log_date=today)
            entry = BlockEntry.objects.get(daily_log=daily_log, block=block)
        except (DailyLog.DoesNotExist, BlockEntry.DoesNotExist):
            return Response({"detail": "This block hasn't been started today."}, status=400)

        if entry.ended_at is None:
            entry.ended_at = timezone.now()
        entry.completed = True
        entry.save()
        return Response(_serialize_block_entry(entry))


# --------------------------------------------------------------------------
# Analytics (human token only) — every view is a thin wrapper around one
# core.analytics module. Plain Python, computed fresh on every request.
# --------------------------------------------------------------------------

class AnalyticsAPIView(APIView):
    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(self.get_data(request))

    def get_data(self, request):
        raise NotImplementedError


class RhythmView(AnalyticsAPIView):
    def get_data(self, request):
        return rhythm.compute()


class CorrelationsView(AnalyticsAPIView):
    def get_data(self, request):
        return correlations.compute()


class FunnelView(AnalyticsAPIView):
    def get_data(self, request):
        return funnel.compute()


class LossesView(AnalyticsAPIView):
    def get_data(self, request):
        return losses.compute()


class BurnupView(AnalyticsAPIView):
    def get_data(self, request):
        return burnup.compute()


class CertTrendView(AnalyticsAPIView):
    def get_data(self, request):
        return certtrend.compute()


class DecayView(AnalyticsAPIView):
    def get_data(self, request):
        return decay.compute()


class ActivityView(AnalyticsAPIView):
    def get_data(self, request):
        return activity.compute()


class ObservationsView(AnalyticsAPIView):
    def get_data(self, request):
        return observations.compute()


# --------------------------------------------------------------------------
# Read endpoints (human token only) — added so a frontend can replace the
# placeholders/empty-states it shipped with (rhythm heatmap, skill radar,
# etc.) with real data. Unlike every view above, these use real
# ModelSerializers + generics.ListAPIView + django-filter: the user asked
# for "DRF's built-in filter backends, don't build bespoke query parsing",
# and a real serializer_class gives drf-spectacular something worth
# generating types from. Existing hand-rolled views are untouched.
#
# Owner scoping: existing endpoints above (TodayView, EmailQueueView, every
# analytics/* view) do NOT filter by owner at query time today — only new
# rows get tagged with an owner on creation. These new endpoints DO filter,
# closing that gap for the new surface only (see plan/handoff note) — zero
# behavior change for the current single real user, since every existing
# row is either owned by them or NULL-owned seed scaffolding.
# --------------------------------------------------------------------------

def _owned_or_shared(queryset, user):
    return queryset.filter(Q(owner=user) | Q(owner__isnull=True))


class OwnerScopedListAPIView(generics.ListAPIView):
    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]

    def get_queryset(self):
        return _owned_or_shared(self.queryset, self.request.user)


class MilestoneFilterSet(django_filters.FilterSet):
    # declarative filterset_fields can't express "project" meaning the FK's
    # natural code rather than its raw db id — every other natural-key
    # lookup in this app (ingest) uses codes, not ids, so this matches.
    project = django_filters.CharFilter(field_name="project__code")

    class Meta:
        model = Milestone
        fields = ["status"]


class ApplicationListView(OwnerScopedListAPIView):
    queryset = Application.objects.all()
    serializer_class = ApplicationReadSerializer
    filterset_fields = ["stage", "source"]
    ordering_fields = ["last_update", "applied_on", "company"]
    ordering = ["-last_update"]


class MilestoneListView(OwnerScopedListAPIView):
    queryset = Milestone.objects.select_related("project").all()
    serializer_class = MilestoneReadSerializer
    filterset_class = MilestoneFilterSet
    ordering_fields = ["due_date", "title"]
    ordering = ["due_date", "title"]


class SleepLogListView(OwnerScopedListAPIView):
    queryset = SleepLog.objects.all()
    serializer_class = SleepLogReadSerializer
    filterset_fields = {"log_date": ["gte", "lte"]}
    ordering_fields = ["log_date"]
    ordering = ["-log_date"]


class DailyLogListView(OwnerScopedListAPIView):
    queryset = DailyLog.objects.all()
    serializer_class = DailyLogReadSerializer
    filterset_fields = {"log_date": ["gte", "lte"]}
    ordering_fields = ["log_date"]
    ordering = ["-log_date"]

    def get_queryset(self):
        # Annotate each day with the computed deep-work total (sum of that
        # date's TodaySelection minutes_spent) — the replacement aggregate for
        # the deprecated DailyLog.deep_work_minutes single field.
        totals = (
            TodaySelection.objects.filter(date=OuterRef("log_date"))
            .values("date")
            .annotate(s=Sum("minutes_spent"))
            .values("s")
        )
        return super().get_queryset().annotate(
            deep_work_total=Coalesce(
                Subquery(totals, output_field=IntegerField()), 0
            )
        )


class SkillListView(OwnerScopedListAPIView):
    queryset = Skill.objects.all()
    serializer_class = SkillReadSerializer
    ordering_fields = ["name", "level"]


class CourseListView(OwnerScopedListAPIView):
    queryset = Course.objects.all()
    serializer_class = CourseReadSerializer
    ordering_fields = ["name", "progress_pct"]


class CertDomainListView(OwnerScopedListAPIView):
    queryset = CertDomain.objects.all()
    serializer_class = CertDomainReadSerializer
    ordering_fields = ["domain_no", "mastery_pct"]


class ContentPostListView(OwnerScopedListAPIView):
    queryset = ContentPost.objects.all()
    serializer_class = ContentPostReadSerializer
    ordering_fields = ["posted_on"]
    ordering = ["-posted_on"]


class ReflectionListView(OwnerScopedListAPIView):
    queryset = Reflection.objects.all()
    serializer_class = ReflectionReadSerializer
    filterset_fields = {"log_date": ["gte", "lte"]}
    ordering_fields = ["log_date"]
    ordering = ["-log_date"]


class NotionTaskListView(OwnerScopedListAPIView):
    queryset = NotionTask.objects.all()
    serializer_class = NotionTaskReadSerializer
    filterset_fields = ["status"]
    ordering_fields = ["due_date", "notion_last_edited"]


# --------------------------------------------------------------------------
# PATCH-by-id (human token only) — hand-rolled APIView, matching
# BlockStartView/BlockCompleteView's one-purpose-per-view style, not generic
# UpdateAPIView: there's no filtering concept on a single-object PATCH with
# a bespoke business rule, so genericizing these would buy nothing.
# --------------------------------------------------------------------------

class CountdownDetailView(APIView):
    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        countdown = get_object_or_404(_owned_or_shared(Countdown.objects.all(), request.user), pk=pk)
        if not countdown.editable:
            return Response({"detail": "This countdown is not editable."}, status=400)
        serializer = CountdownPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        countdown.target_date = serializer.validated_data["target_date"]
        countdown.save()
        return Response(_serialize_countdown(countdown))


class BlockEntryDetailView(APIView):
    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        entry = get_object_or_404(_owned_or_shared(BlockEntry.objects.all(), request.user), pk=pk)
        serializer = BlockEntryUndoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Idempotent by design: blindly sets completed=False, ended_at=None
        # regardless of current state, so a double-undo is a harmless no-op.
        # started_at is deliberately preserved — the mistap this exists for
        # is on the COMPLETE tap, not the START tap, so the block goes back
        # to "in progress", not "never started". elapsed_minutes resets to
        # None inside BlockEntry.save() itself.
        entry.completed = False
        entry.ended_at = None
        entry.save()
        return Response(_serialize_block_entry(entry))


class SleepLogDetailView(APIView):
    """Correct the bed/wake time on a SleepLog row the frontend is already
    showing (the "fix" control on TODAY's "Last night" panel). Targets the
    row by id — POST /api/ingest/sleep/ can't be used for this because it
    re-derives log_date from the submitted time (before-noon -> previous
    day), which drops a morning correction onto the *previous* night's row
    whenever the displayed night runs past midnight."""

    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        sleep = get_object_or_404(
            _owned_or_shared(SleepLog.objects.all(), request.user), pk=pk
        )
        serializer = SleepLogPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(sleep, field, value)
        try:
            # SleepLog.save() runs full_clean() (wake_at must be after bed_at)
            # and recomputes `hours` from the pair.
            sleep.save()
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
            raise DRFValidationError(detail)
        return Response(SleepLogReadSerializer(sleep).data)


# --------------------------------------------------------------------------
# Notion "Daily Board" sync (machine token only) — pulls the board into
# NotionTask. core/notion_sync.py holds all the actual logic; this view is a
# one-line call, same thinness as IngestView.
# --------------------------------------------------------------------------

class NotionSyncView(APIView):
    authentication_classes = [IngestTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        return Response(notion_sync.sync_notion_tasks(request.user))


# --------------------------------------------------------------------------
# Notion status write-back (human token only) — this is a UI action from the
# /board page, not the machine ingest path, so it takes the user's own
# token like the other PATCH-by-id views above. Validates the new status
# against the board's live options, PATCHes the Notion page, then updates
# the local row so the change shows without waiting for the next cron sync.
# --------------------------------------------------------------------------

class NotionTaskDetailView(APIView):
    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        task = get_object_or_404(
            _owned_or_shared(NotionTask.objects.all(), request.user), pk=pk
        )
        serializer = NotionTaskStatusPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = notion_sync.write_status_to_notion(task, serializer.validated_data["status"])
        return Response(NotionTaskReadSerializer(updated).data)


# --------------------------------------------------------------------------
# Today planning — pool, recommendations, selections
#
# The day's task list is TodaySelection, an ordered list of any length that
# replaces the old fixed 5 blocks. /pool/ and /recommendations/ feed the
# "Plan" view; /selections/ is what the day is actually run against.
# --------------------------------------------------------------------------

class TodayPoolView(APIView):
    """GET — the candidate pool for planning today: pending ASCEND BacklogItem
    rows merged with open (not done-like) Notion "Daily Board" rows, each
    tagged with its source. Dual auth: the live frontend and the Morning
    Brief task both read it."""

    authentication_classes = [authentication.TokenAuthentication, IngestTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        backlog = [
            {
                "source": "backlog",
                "source_id": b.id,
                "title": b.title,
                "source_project": b.source_project,
            }
            for b in BacklogItem.objects.filter(status=BacklogItem.Status.PENDING)
        ]
        notion = [
            {
                "source": "notion",
                "source_id": t.id,
                "title": t.title,
                "status": t.status,
                "category": t.category,
                "due_date": t.due_date,
            }
            for t in NotionTask.objects.all()
            if _notion_status_is_open(t.status)
        ]
        results = backlog + notion
        return Response({"count": len(results), "results": results})


class TodayRecommendationsView(APIView):
    """GET ?date=YYYY-MM-DD (default today) — the day's suggestions.
    POST — a bare JSON array of {title, rationale, source_project} that
    *replaces* the given date's suggestions (the Morning Brief task pushes
    today's 2-4). Dual auth: the frontend reads, the scheduled task writes."""

    authentication_classes = [authentication.TokenAuthentication, IngestTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        date = _date_param(request) or timezone.localdate()
        recs = DailyRecommendation.objects.filter(date=date)
        return Response(
            {"date": date, "results": [_serialize_recommendation(r) for r in recs]}
        )

    def post(self, request):
        serializer = DailyRecommendationItemSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        rows = serializer.validated_data
        if not rows:
            raise DRFValidationError({"detail": "Provide at least one recommendation."})

        date = timezone.localdate()
        with transaction.atomic():
            DailyRecommendation.objects.filter(date=date).delete()
            created = [
                DailyRecommendation.objects.create(
                    owner=request.user,
                    date=date,
                    title=row["title"],
                    rationale=row.get("rationale", ""),
                    source_project=row.get(
                        "source_project", DailyRecommendation.SourceProject.OTHER
                    ),
                )
                for row in rows
            ]
        return Response(
            {"date": date, "results": [_serialize_recommendation(r) for r in created]},
            status=201,
        )


class TodaySelectionsView(APIView):
    """GET ?date= (default today) — the day's committed task list, ordered.
    POST — a bare JSON array of {source_type, source_id, title}; appends
    TodaySelection rows for today. Idempotent on (date, source_type,
    source_id) for non-adhoc rows, so re-submitting a still-checked pool item
    is a no-op rather than a duplicate. Human token only — this is the live
    UI, reachable all day."""

    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        date = _date_param(request) or timezone.localdate()
        rows = TodaySelection.objects.filter(date=date).select_related("block")
        return Response(
            {"date": date, "results": [_serialize_today_selection(s) for s in rows]}
        )

    def post(self, request):
        serializer = TodaySelectionItemSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        items = serializer.validated_data

        today = timezone.localdate()
        existing = list(TodaySelection.objects.filter(date=today))
        next_pos = (max((s.position for s in existing), default=0)) + 1
        seen = {
            (s.source_type, s.source_id) for s in existing if s.source_id is not None
        }

        with transaction.atomic():
            for row in items:
                key = (row["source_type"], row.get("source_id"))
                if row["source_type"] != "adhoc" and key in seen:
                    continue
                TodaySelection.objects.create(
                    owner=request.user,
                    date=today,
                    source_type=row["source_type"],
                    source_id=row.get("source_id"),
                    title=row["title"],
                    position=next_pos,
                )
                next_pos += 1
                if row["source_type"] != "adhoc":
                    seen.add(key)

        rows = TodaySelection.objects.filter(date=today).select_related("block")
        return Response(
            {"date": today, "results": [_serialize_today_selection(s) for s in rows]},
            status=201,
        )


class TodaySelectionDetailView(APIView):
    """PATCH {minutes_spent?, done?} — update one row. DELETE — remove a
    mis-added row. Human token only."""

    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        row = get_object_or_404(
            _owned_or_shared(TodaySelection.objects.all(), request.user), pk=pk
        )
        serializer = TodaySelectionPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(row, field, value)
        row.save()
        return Response(_serialize_today_selection(row))

    def delete(self, request, pk):
        row = get_object_or_404(
            _owned_or_shared(TodaySelection.objects.all(), request.user), pk=pk
        )
        row.delete()
        return Response(status=204)
