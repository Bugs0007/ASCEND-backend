from django.urls import path
from drf_spectacular.views import SpectacularAPIView
from rest_framework import permissions
from rest_framework.authtoken.views import obtain_auth_token

from core import views

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    # DRF's built-in view: POST {"username","password"} -> {"token": "..."}.
    # Render's free plan dropped Shell/SSH access (paid-only now), so this
    # is how you mint your own token — see docs/SETUP.md. It only ever
    # takes credentials you enter yourself; nothing here reads or stores
    # your password beyond Django's own auth check.
    path("auth/token/", obtain_auth_token, name="auth-token"),
    path("ingest/", views.IngestView.as_view(), name="ingest"),
    path("ingest/sleep/", views.IngestSleepView.as_view(), name="ingest-sleep"),
    path("today/", views.TodayView.as_view(), name="today"),
    path("email-queue/", views.EmailQueueView.as_view(), name="email-queue"),
    path("blocks/<str:code>/start/", views.BlockStartView.as_view(), name="block-start"),
    path("blocks/<str:code>/complete/", views.BlockCompleteView.as_view(), name="block-complete"),
    path("analytics/rhythm/", views.RhythmView.as_view(), name="analytics-rhythm"),
    path("analytics/correlations/", views.CorrelationsView.as_view(), name="analytics-correlations"),
    path("analytics/funnel/", views.FunnelView.as_view(), name="analytics-funnel"),
    path("analytics/losses/", views.LossesView.as_view(), name="analytics-losses"),
    path("analytics/burnup/", views.BurnupView.as_view(), name="analytics-burnup"),
    path("analytics/certtrend/", views.CertTrendView.as_view(), name="analytics-certtrend"),
    path("analytics/decay/", views.DecayView.as_view(), name="analytics-decay"),
    path("analytics/activity/", views.ActivityView.as_view(), name="analytics-activity"),
    path("analytics/observations/", views.ObservationsView.as_view(), name="analytics-observations"),
    # --- Read endpoints (human token only) ---
    path("applications/", views.ApplicationListView.as_view(), name="applications"),
    path("milestones/", views.MilestoneListView.as_view(), name="milestones-list"),
    path("sleep-logs/", views.SleepLogListView.as_view(), name="sleep-logs"),
    path("daily-logs/", views.DailyLogListView.as_view(), name="daily-logs"),
    path("skills/", views.SkillListView.as_view(), name="skills"),
    path("courses/", views.CourseListView.as_view(), name="courses"),
    path("cert-domains/", views.CertDomainListView.as_view(), name="cert-domains"),
    path("content-posts/", views.ContentPostListView.as_view(), name="content-posts"),
    path("reflections/", views.ReflectionListView.as_view(), name="reflections"),
    path("countdowns/<int:pk>/", views.CountdownDetailView.as_view(), name="countdown-detail"),
    path("block-entries/<int:pk>/", views.BlockEntryDetailView.as_view(), name="block-entry-detail"),
    # --- Notion "Daily Board" sync ---
    path("sync/notion/", views.NotionSyncView.as_view(), name="sync-notion"),
    path("notion-tasks/", views.NotionTaskListView.as_view(), name="notion-tasks"),
    # --- OpenAPI schema, public: field/endpoint shape only, no user data ---
    path(
        "schema/",
        SpectacularAPIView.as_view(authentication_classes=[], permission_classes=[permissions.AllowAny]),
        name="schema",
    ),
]
