"""
Upsert logic for POST /api/ingest/ and POST /api/ingest/sleep/.

Natural keys (idempotency): daily_logs and sleep_logs on log_date,
applications on (company, role), email_events on gmail_message_id,
practice_tests on (cert_code, taken_on) — exactly the four the spec names.
Beyond those, this module extends the same idempotent spirit with keys that
make sense for the resource (documented per-function below and in
docs/INGEST_API.md); anything with no sensible natural key (study_sessions,
activity_samples) supports an optional `id` field for explicit correction
and otherwise always creates a new row.

Every write goes through a model's own .save() — including the
full_clean()-enforcing ones (Milestone, SleepLog, BlockEntry) — so a Django
ValidationError (e.g. a milestone marked done with no evidence_url) becomes
a 400 here rather than a 500 or a silently-accepted bad row.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
import datetime

from rest_framework.exceptions import ValidationError as DRFValidationError

from core.models import (
    ActivitySample,
    Application,
    BlockEntry,
    CertDomain,
    ContentPost,
    Course,
    DailyLog,
    EmailEvent,
    LossPostmortem,
    Milestone,
    Phase,
    PracticeTest,
    Project,
    Reflection,
    SleepLog,
    StudySession,
)
from core.serializers import INGEST_SERIALIZERS


# --------------------------------------------------------------------------
# Generic helpers
# --------------------------------------------------------------------------

def _get_or_new(model, lookup, owner):
    try:
        return model.objects.get(**lookup), False
    except model.DoesNotExist:
        return model(owner=owner, **lookup), True


def _apply_fields(instance, data, skip_fields=frozenset()):
    for field, value in data.items():
        if field in skip_fields:
            continue
        setattr(instance, field, value)


def _save(instance):
    try:
        instance.save()
    except DjangoValidationError as exc:
        detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
        raise DRFValidationError(detail)
    return instance


# --------------------------------------------------------------------------
# FK resolution by human-readable identifier (never a raw DB id, except
# where an explicit `id` field is offered for direct correction)
# --------------------------------------------------------------------------

def _resolve_cert_domain(domain_no):
    if domain_no is None:
        return None
    try:
        return CertDomain.objects.get(cert_code="AI-103", domain_no=domain_no)
    except CertDomain.DoesNotExist:
        raise DRFValidationError({"cert_domain_no": f"No AI-103 domain numbered {domain_no}."})


def _resolve_course(course_name):
    if not course_name:
        return None
    try:
        return Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        raise DRFValidationError({"course_name": f"No course named {course_name!r}."})


def _resolve_application(company, role, *, required):
    try:
        return Application.objects.get(company=company, role=role)
    except Application.DoesNotExist:
        if required:
            raise DRFValidationError({"application": f"No application for {company} / {role}."})
        return None


def _resolve_project(project_code):
    if not project_code:
        return None
    try:
        return Project.objects.get(code=project_code)
    except Project.DoesNotExist:
        raise DRFValidationError({"project_code": f"No project with code {project_code!r}."})


def _resolve_phase(phase_no):
    if phase_no is None:
        return None
    try:
        return Phase.objects.get(phase_no=phase_no)
    except Phase.DoesNotExist:
        raise DRFValidationError({"phase_no": f"No phase numbered {phase_no}."})


def _resolve_milestone_by_title(title):
    return Milestone.objects.filter(title=title).order_by("-updated_at").first()


def _resolve_block_entry(block_entry_id):
    if block_entry_id is None:
        return None
    try:
        return BlockEntry.objects.get(pk=block_entry_id)
    except BlockEntry.DoesNotExist:
        raise DRFValidationError({"block_entry_id": f"No block_entry with id {block_entry_id}."})


# --------------------------------------------------------------------------
# Per-resource upsert. Each returns True if a row was created, False if an
# existing row was updated — the caller tallies these into the response.
# --------------------------------------------------------------------------

def _upsert_daily_log(data, owner):
    obj, created = _get_or_new(DailyLog, {"log_date": data["log_date"]}, owner)
    _apply_fields(obj, data, skip_fields={"log_date"})
    _save(obj)
    return created


def _upsert_sleep_log(data, owner):
    obj, created = _get_or_new(SleepLog, {"log_date": data["log_date"]}, owner)
    _apply_fields(obj, data, skip_fields={"log_date"})
    _save(obj)
    return created


def _upsert_study_session(data, owner):
    data = dict(data)
    session_id = data.pop("id", None)
    cert_domain = _resolve_cert_domain(data.pop("cert_domain_no", None))
    course = _resolve_course(data.pop("course_name", ""))

    if session_id is not None:
        try:
            obj = StudySession.objects.get(pk=session_id)
        except StudySession.DoesNotExist:
            raise DRFValidationError({"id": f"No study_session with id {session_id}."})
        created = False
    else:
        obj = StudySession(owner=owner)
        created = True

    _apply_fields(obj, data)
    obj.cert_domain = cert_domain
    obj.course = course
    _save(obj)
    return created


def _upsert_application(data, owner):
    obj, created = _get_or_new(Application, {"company": data["company"], "role": data["role"]}, owner)
    _apply_fields(obj, data, skip_fields={"company", "role"})
    _save(obj)
    return created


def _upsert_email_event(data, owner):
    data = dict(data)
    app_company = data.pop("application_company", None)
    app_role = data.pop("application_role", None)

    obj, created = _get_or_new(EmailEvent, {"gmail_message_id": data["gmail_message_id"]}, owner)
    _apply_fields(obj, data, skip_fields={"gmail_message_id"})

    if app_company and app_role:
        obj.application = _resolve_application(app_company, app_role, required=True)
        obj.matched = True
    elif obj.application_id is None:
        # Auto-match by sender domain vs Application.company_domain.
        # Ambiguous (0 or >1 matches) stays unmatched — a review-queue row,
        # not a guess.
        domain = (data.get("from_address") or obj.from_address or "").rsplit("@", 1)[-1].lower()
        if domain:
            matches = list(Application.objects.filter(company_domain__iexact=domain))
            if len(matches) == 1:
                obj.application = matches[0]
                obj.matched = True

    _save(obj)
    return created


def _upsert_loss_postmortem(data, owner):
    data = dict(data)
    application = _resolve_application(
        data.pop("application_company"), data.pop("application_role"), required=True
    )
    round_reached = data.get("round_reached", "")
    obj, created = _get_or_new(
        LossPostmortem, {"application": application, "round_reached": round_reached}, owner
    )
    _apply_fields(obj, data)
    obj.application = application
    _save(obj)
    return created


def _upsert_content_post(data, owner):
    data = dict(data)
    post_id = data.pop("id", None)
    milestone_title = data.pop("milestone_title", "")
    milestone = _resolve_milestone_by_title(milestone_title) if milestone_title else None
    url = data.get("url", "")

    if post_id is not None:
        try:
            obj = ContentPost.objects.get(pk=post_id)
        except ContentPost.DoesNotExist:
            raise DRFValidationError({"id": f"No content_post with id {post_id}."})
        created = False
    elif url:
        obj, created = _get_or_new(ContentPost, {"url": url}, owner)
    else:
        obj, created = ContentPost(owner=owner), True

    _apply_fields(obj, data)
    obj.milestone = milestone
    _save(obj)
    return created


def _upsert_practice_test(data, owner):
    obj, created = _get_or_new(
        PracticeTest, {"cert_code": data["cert_code"], "taken_on": data["taken_on"]}, owner
    )
    _apply_fields(obj, data, skip_fields={"cert_code", "taken_on"})
    _save(obj)
    return created


def _upsert_milestone(data, owner):
    data = dict(data)
    milestone_id = data.pop("id", None)
    project_code = data.pop("project_code", "")
    phase_no = data.pop("phase_no", None)
    project = _resolve_project(project_code) if project_code else None
    phase = _resolve_phase(phase_no) if phase_no is not None else None

    if milestone_id is not None:
        try:
            obj = Milestone.objects.get(pk=milestone_id)
        except Milestone.DoesNotExist:
            raise DRFValidationError({"id": f"No milestone with id {milestone_id}."})
        created = False
    elif project is not None:
        obj, created = _get_or_new(Milestone, {"project": project, "title": data["title"]}, owner)
    else:
        existing = Milestone.objects.filter(project__isnull=True, title=data["title"]).first()
        obj, created = (existing, False) if existing else (Milestone(owner=owner), True)

    _apply_fields(obj, data)
    # project/phase are only reassigned when explicitly provided — an
    # update that omits project_code must not silently detach an existing
    # milestone from its project.
    if project_code:
        obj.project = project
    if phase_no is not None:
        obj.phase = phase
    _save(obj)
    return created


def _upsert_reflection(data, owner):
    obj, created = _get_or_new(Reflection, {"log_date": data["log_date"]}, owner)
    _apply_fields(obj, data, skip_fields={"log_date"})
    _save(obj)
    return created


def _upsert_activity_sample(data, owner):
    data = dict(data)
    block_entry = _resolve_block_entry(data.pop("block_entry_id", None))
    obj = ActivitySample(owner=owner, block_entry=block_entry, **data)
    _save(obj)
    return True  # append-only — nothing writes here in v1, but always "created"


UPSERT_DISPATCH = {
    "daily_logs": _upsert_daily_log,
    "sleep_logs": _upsert_sleep_log,
    "study_sessions": _upsert_study_session,
    "applications": _upsert_application,
    "email_events": _upsert_email_event,
    "loss_postmortems": _upsert_loss_postmortem,
    "content_posts": _upsert_content_post,
    "practice_tests": _upsert_practice_test,
    "milestones": _upsert_milestone,
    "reflections": _upsert_reflection,
    "activity_samples": _upsert_activity_sample,
}


# --------------------------------------------------------------------------
# POST /api/ingest/ entry point
# --------------------------------------------------------------------------

def run_ingest(payload, owner):
    """
    payload: {"daily_logs": [...], "applications": [...], ...}
    Returns {"daily_logs": {"created": n, "updated": n}, ...}.
    All-or-nothing: the entire payload is applied in one transaction, so a
    validation failure on row 7 of 10 doesn't leave rows 1-6 committed.
    """
    if not isinstance(payload, dict):
        raise DRFValidationError({"detail": "Payload must be a JSON object keyed by resource type."})

    unknown_resources = set(payload.keys()) - set(INGEST_SERIALIZERS.keys())
    if unknown_resources:
        raise DRFValidationError({r: "Unknown resource type." for r in sorted(unknown_resources)})

    summary = {}
    with transaction.atomic():
        for resource, rows in payload.items():
            if not isinstance(rows, list):
                raise DRFValidationError({resource: "Must be a list of objects."})

            serializer_cls = INGEST_SERIALIZERS[resource]
            upsert_fn = UPSERT_DISPATCH[resource]
            created_count = 0
            updated_count = 0
            for row in rows:
                serializer = serializer_cls(data=row)
                serializer.is_valid(raise_exception=True)
                if upsert_fn(serializer.validated_data, owner):
                    created_count += 1
                else:
                    updated_count += 1
            summary[resource] = {"created": created_count, "updated": updated_count}
    return summary


# --------------------------------------------------------------------------
# POST /api/ingest/sleep/ — day attribution for the iPhone Shortcuts endpoint
# --------------------------------------------------------------------------

# A sleep event's local time-of-day before this cutoff belongs to the
# *previous* calendar day's SleepLog — this is what correctly attributes
# both a post-midnight bedtime (e.g. 00:47) and a morning wake (e.g. 06:30)
# to the same night's row.
_SLEEP_DAY_CUTOFF = datetime.time(12, 0)


def resolve_sleep_log_date(at_datetime):
    local = timezone.localtime(at_datetime)
    if local.time() < _SLEEP_DAY_CUTOFF:
        return local.date() - datetime.timedelta(days=1)
    return local.date()


def run_sleep_event_ingest(event, at_datetime, owner):
    log_date = resolve_sleep_log_date(at_datetime)
    obj, created = _get_or_new(SleepLog, {"log_date": log_date}, owner)
    obj.source = SleepLog.Source.SHORTCUT
    if event == "bed":
        obj.bed_at = at_datetime
    else:
        obj.wake_at = at_datetime
    _save(obj)
    return obj, created
