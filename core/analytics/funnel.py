"""
GET /api/analytics/funnel/ — stage counts, stage-to-stage conversion,
interview rate per source, and the ghost count from the computed 21-day
rule (Application.is_ghosted — never mutates the stored `stage`).
"""
from django.utils import timezone

from core import stats
from core.constants import STAGE_ORDER
from core.models import Application


def _furthest_index(application):
    """Index into STAGE_ORDER of the furthest stage this application reached."""
    stage = application.furthest_stage()
    try:
        return STAGE_ORDER.index(stage)
    except ValueError:
        return 0  # unrecognized round_reached tag falls back to "applied"


def compute(applications_qs=None, as_of=None):
    applications_qs = applications_qs if applications_qs is not None else Application.objects.all()
    as_of = as_of or timezone.localdate()
    applications = list(applications_qs)

    # --- raw stage counts (current stored `stage`, includes rejected/ghosted) ---
    stage_counts = {choice: 0 for choice in Application.Stage.values}
    for app in applications:
        stage_counts[app.stage] = stage_counts.get(app.stage, 0) + 1

    # --- cumulative funnel: how many reached each stage or beyond ---
    reached_counts = {stage: 0 for stage in STAGE_ORDER}
    for app in applications:
        furthest_idx = _furthest_index(app)
        for i, stage in enumerate(STAGE_ORDER):
            if i <= furthest_idx:
                reached_counts[stage] += 1

    conversion = {}
    for i in range(len(STAGE_ORDER) - 1):
        from_stage, to_stage = STAGE_ORDER[i], STAGE_ORDER[i + 1]
        conversion[f"{from_stage}_to_{to_stage}"] = stats.safe_div(
            reached_counts[to_stage], reached_counts[from_stage]
        )

    # --- interview rate per source (reached 'screen' or beyond) ---
    screen_idx = STAGE_ORDER.index("screen")
    by_source_total = {}
    by_source_interviewed = {}
    for app in applications:
        by_source_total[app.source] = by_source_total.get(app.source, 0) + 1
        if _furthest_index(app) >= screen_idx:
            by_source_interviewed[app.source] = by_source_interviewed.get(app.source, 0) + 1
    interview_rate_per_source = {
        source: stats.safe_div(by_source_interviewed.get(source, 0), total)
        for source, total in by_source_total.items()
    }

    # --- computed ghost count (never mutates `stage`) ---
    ghost_count = sum(1 for app in applications if app.is_ghosted(as_of))

    return {
        "stage_counts": stage_counts,
        "reached_counts": reached_counts,
        "conversion": conversion,
        "interview_rate_per_source": interview_rate_per_source,
        "ghost_count": ghost_count,
        "total_applications": len(applications),
    }
