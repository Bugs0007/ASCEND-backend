"""
Ingest serializers — shape validation only. Natural-key upsert logic and FK
resolution (by human-readable identifiers, not DB ids, since the machine
callers are scheduled Claude tasks and iPhone Shortcuts that don't know our
primary keys) live in core/ingest.py.

Every serializer mixes in StrictFieldsMixin: an unknown top-level key is a
400, never a silent ignore. See docs/INGEST_API.md for the full contract
and a curl example per shape.
"""
from rest_framework import serializers


class StrictFieldsMixin:
    """Reject any payload key that isn't a declared field. Unknown fields
    return 400 rather than being silently dropped."""

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data.keys()) - set(self.fields.keys())
            if unknown:
                raise serializers.ValidationError(
                    {field: "Unknown field." for field in sorted(unknown)}
                )
        return super().to_internal_value(data)


# --------------------------------------------------------------------------
# POST /api/ingest/ — one serializer per resource type
# --------------------------------------------------------------------------

class DailyLogIngestSerializer(StrictFieldsMixin, serializers.Serializer):
    log_date = serializers.DateField()
    deep_work_minutes = serializers.IntegerField(required=False, min_value=0)
    energy = serializers.IntegerField(min_value=1, max_value=5)
    steps_after_10 = serializers.IntegerField(required=False, min_value=0)
    gym = serializers.BooleanField(required=False)
    last_caffeine_at = serializers.TimeField(required=False, allow_null=True)
    mood = serializers.CharField(required=False, allow_blank=True, max_length=50)
    notes = serializers.CharField(required=False, allow_blank=True)


class SleepLogIngestSerializer(StrictFieldsMixin, serializers.Serializer):
    log_date = serializers.DateField()
    bed_at = serializers.DateTimeField(required=False, allow_null=True)
    wake_at = serializers.DateTimeField(required=False, allow_null=True)
    source = serializers.ChoiceField(choices=["manual", "shortcut", "estimate"], required=False)


class StudySessionIngestSerializer(StrictFieldsMixin, serializers.Serializer):
    id = serializers.IntegerField(required=False)
    session_date = serializers.DateField()
    topic = serializers.CharField(max_length=200)
    category = serializers.CharField(required=False, allow_blank=True, max_length=50)
    minutes = serializers.IntegerField(min_value=0)
    source = serializers.CharField(required=False, allow_blank=True, max_length=100)
    # AI-103 is the only cert in v1, so a domain number is enough context.
    cert_domain_no = serializers.IntegerField(required=False, allow_null=True)
    course_name = serializers.CharField(required=False, allow_blank=True, max_length=200)


class ApplicationIngestSerializer(StrictFieldsMixin, serializers.Serializer):
    company = serializers.CharField(max_length=200)
    role = serializers.CharField(max_length=200)
    source = serializers.ChoiceField(choices=["referral", "direct", "portal", "outreach"])
    applied_on = serializers.DateField()
    stage = serializers.ChoiceField(
        choices=["applied", "screen", "oa", "tech", "final", "offer", "rejected", "ghosted"],
        required=False,
    )
    last_update = serializers.DateField()
    last_email_at = serializers.DateTimeField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    contact = serializers.CharField(required=False, allow_blank=True, max_length=200)
    company_domain = serializers.CharField(required=False, allow_blank=True, max_length=200)


class EmailEventIngestSerializer(StrictFieldsMixin, serializers.Serializer):
    gmail_message_id = serializers.CharField(max_length=200)
    received_at = serializers.DateTimeField()
    from_address = serializers.CharField(max_length=200)
    subject = serializers.CharField(required=False, allow_blank=True, max_length=500)
    classified_as = serializers.ChoiceField(
        choices=["rejection", "interview_invite", "oa_link", "acknowledgement", "other"],
        required=False,
    )
    # Explicit match, only when the caller already knows which application
    # this is about. Omit both to let the backend auto-match on
    # company_domain — an unresolved auto-match is a review-queue row, not
    # an error.
    application_company = serializers.CharField(required=False, max_length=200)
    application_role = serializers.CharField(required=False, max_length=200)


class LossPostmortemIngestSerializer(StrictFieldsMixin, serializers.Serializer):
    application_company = serializers.CharField(max_length=200)
    application_role = serializers.CharField(max_length=200)
    round_reached = serializers.CharField(required=False, allow_blank=True, max_length=20)
    cause = serializers.ChoiceField(
        choices=[
            "take_home", "system_design", "dsa", "behavioral", "domain_knowledge",
            "communication", "culture_fit", "comp_mismatch", "ghosted_by_them", "other",
        ],
        required=False,
    )
    what_happened = serializers.CharField(required=False, allow_blank=True)
    logged_on = serializers.DateField()


class ContentPostIngestSerializer(StrictFieldsMixin, serializers.Serializer):
    id = serializers.IntegerField(required=False)
    platform = serializers.ChoiceField(choices=["linkedin", "github", "blog"])
    title = serializers.CharField(max_length=300)
    url = serializers.URLField(required=False, allow_blank=True)
    posted_on = serializers.DateField()
    impressions = serializers.IntegerField(required=False, min_value=0)
    reactions = serializers.IntegerField(required=False, min_value=0)
    comments = serializers.IntegerField(required=False, min_value=0)
    milestone_title = serializers.CharField(required=False, allow_blank=True, max_length=300)


class PracticeTestIngestSerializer(StrictFieldsMixin, serializers.Serializer):
    cert_code = serializers.CharField(max_length=20)
    taken_on = serializers.DateField()
    score = serializers.IntegerField(min_value=0)
    max_score = serializers.IntegerField(required=False, min_value=1)
    per_domain = serializers.JSONField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class MilestoneIngestSerializer(StrictFieldsMixin, serializers.Serializer):
    id = serializers.IntegerField(required=False)
    title = serializers.CharField(max_length=300)
    project_code = serializers.CharField(required=False, allow_blank=True, max_length=10)
    phase_no = serializers.IntegerField(required=False, allow_null=True)
    week_no = serializers.IntegerField(required=False, allow_null=True)
    category = serializers.ChoiceField(
        choices=["project", "cert", "content", "career", "admin"], required=False
    )
    due_date = serializers.DateField(required=False, allow_null=True)
    status = serializers.ChoiceField(choices=["todo", "doing", "done", "dropped"], required=False)
    completed_on = serializers.DateField(required=False, allow_null=True)
    evidence_url = serializers.URLField(required=False, allow_blank=True)
    post_angle = serializers.CharField(required=False, allow_blank=True)


class ReflectionIngestSerializer(StrictFieldsMixin, serializers.Serializer):
    log_date = serializers.DateField()
    went_well = serializers.CharField(required=False, allow_blank=True)
    blocked_by = serializers.CharField(required=False, allow_blank=True)
    one_thing_tomorrow = serializers.CharField(required=False, allow_blank=True)


class ActivitySampleIngestSerializer(StrictFieldsMixin, serializers.Serializer):
    block_entry_id = serializers.IntegerField(required=False, allow_null=True)
    started_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField()
    app = serializers.CharField(max_length=200)
    window_title = serializers.CharField(required=False, allow_blank=True, max_length=500)
    category = serializers.ChoiceField(
        choices=["build", "learn", "apply", "sharpen", "flex", "idle", "distraction", "unknown"],
        required=False,
    )
    active_seconds = serializers.IntegerField(required=False, min_value=0)


# Resource key (as used in the POST /api/ingest/ payload) -> serializer class.
INGEST_SERIALIZERS = {
    "daily_logs": DailyLogIngestSerializer,
    "sleep_logs": SleepLogIngestSerializer,
    "study_sessions": StudySessionIngestSerializer,
    "applications": ApplicationIngestSerializer,
    "email_events": EmailEventIngestSerializer,
    "loss_postmortems": LossPostmortemIngestSerializer,
    "content_posts": ContentPostIngestSerializer,
    "practice_tests": PracticeTestIngestSerializer,
    "milestones": MilestoneIngestSerializer,
    "reflections": ReflectionIngestSerializer,
    "activity_samples": ActivitySampleIngestSerializer,
}


# --------------------------------------------------------------------------
# POST /api/ingest/sleep/ — the tiny iPhone Shortcuts endpoint
# --------------------------------------------------------------------------

class SleepEventSerializer(StrictFieldsMixin, serializers.Serializer):
    event = serializers.ChoiceField(choices=["bed", "wake"])
    at = serializers.DateTimeField()
