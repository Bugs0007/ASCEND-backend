"""
Read (list/detail) serializers for the new GET endpoints in core/views.py.

Deliberately a separate file from core/serializers.py: that file's own
docstring scopes it to ingest write-validation (StrictFieldsMixin,
INGEST_SERIALIZERS) — these are read-only ModelSerializers with a different
job, and mixing the two would blur a documented boundary.

Every serializer exposes the model's business fields plus `id` (so a
frontend has something stable to key/address by); none expose `owner`,
`created_at` or `updated_at` — internal bookkeeping, consistent with every
existing _serialize_* dict helper in views.py never exposing them either.
"""
from rest_framework import serializers

from core.models import (
    Application,
    CertDomain,
    ContentPost,
    Course,
    DailyLog,
    Milestone,
    NotionTask,
    Reflection,
    Skill,
    SleepLog,
)


class ApplicationReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Application
        fields = [
            "id", "company", "role", "source", "applied_on", "stage",
            "last_update", "last_email_at", "notes", "contact", "company_domain",
        ]


class MilestoneReadSerializer(serializers.ModelSerializer):
    # Same shape as views._serialize_milestone's existing "project" key
    # (the project's natural code, not its DB id) — one consistent milestone
    # shape regardless of which endpoint returned it.
    project = serializers.SerializerMethodField()

    class Meta:
        model = Milestone
        fields = [
            "id", "title", "project", "phase", "week_no", "category",
            "due_date", "status", "completed_on", "evidence_url", "post_angle",
        ]

    def get_project(self, obj):
        return obj.project.code if obj.project_id else None


class SleepLogReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = SleepLog
        fields = ["id", "log_date", "bed_at", "wake_at", "hours", "source"]


class DailyLogReadSerializer(serializers.ModelSerializer):
    # Same key set as views._serialize_daily_log (no `id`) — the /rhythm
    # heatmap and any other consumer get one consistent daily-log shape
    # whether it came from /api/today/ or this new list endpoint.
    class Meta:
        model = DailyLog
        fields = [
            "log_date", "deep_work_minutes", "energy", "steps_after_10",
            "gym", "last_caffeine_at", "mood", "notes",
        ]


class SkillReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = ["id", "name", "category", "level", "target"]


class CourseReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ["id", "name", "provider", "credential_type", "url", "progress_pct", "active"]


class CertDomainReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = CertDomain
        fields = [
            "id", "cert_code", "domain_no", "name", "weight_pct",
            "weight_is_approximate", "mastery_pct", "last_studied",
        ]


class ContentPostReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentPost
        fields = [
            "id", "platform", "title", "url", "posted_on",
            "impressions", "reactions", "comments", "milestone",
        ]


class ReflectionReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reflection
        fields = ["id", "log_date", "went_well", "blocked_by", "one_thing_tomorrow"]


class NotionTaskReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotionTask
        fields = [
            "id", "notion_page_id", "title", "status", "category",
            "due_date", "notion_last_edited", "synced_at",
        ]
