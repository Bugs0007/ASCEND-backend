from django.urls import path

from core import views

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
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
]
