"""
GET /api/analytics/observations/ — 3 to 6 rules-based sentences generated
from real computed values. No LLM call, no vibes: every sentence here is
built directly from a number produced by another analytics module. Returns
an empty list below MIN_DAYS_FOR_OBSERVATIONS (7) DailyLog rows rather than
generating something misleading from a thin sample.
"""
import datetime

from django.utils import timezone

from core import stats
from core.analytics import correlations, decay, funnel, streaks
from core.constants import (
    DECAY_DAYS,
    GHOST_DAYS,
    GREEN_DAY_BLOCK_THRESHOLD,
    MAX_OBSERVATIONS,
    MIN_DAYS_FOR_OBSERVATIONS,
)
from core.models import DailyLog


def compute(as_of=None):
    as_of = as_of or timezone.localdate()
    daily_logs = DailyLog.objects.all()

    if daily_logs.count() < MIN_DAYS_FOR_OBSERVATIONS:
        return []

    observations = []

    # 1. Streak
    streak = streaks.current_streak(as_of=as_of)
    if streak > 0:
        observations.append(
            f"You're on a {streak}-day green streak "
            f"(>= {GREEN_DAY_BLOCK_THRESHOLD} of 5 blocks completed)."
        )
    else:
        observations.append(
            f"No active green streak — the most recent day fell short of "
            f"{GREEN_DAY_BLOCK_THRESHOLD} of 5 blocks completed."
        )

    # 2. Last 7 days deep work vs program-wide average
    recent_logs = list(
        daily_logs.filter(log_date__gt=as_of - datetime.timedelta(days=7), log_date__lte=as_of)
    )
    recent_avg = stats.mean([log.deep_work_minutes for log in recent_logs])
    overall_avg = stats.mean([log.deep_work_minutes for log in daily_logs])
    if recent_avg is not None and overall_avg is not None:
        diff = recent_avg - overall_avg
        direction = "above" if diff >= 0 else "below"
        observations.append(
            f"Last 7 days averaged {recent_avg:.0f} deep-work minutes/day, "
            f"{abs(diff):.0f} minutes {direction} your {overall_avg:.0f}-minute program average."
        )

    # 3 & 4. Correlations
    corr = correlations.compute()
    sleep_corr = corr["sleep_vs_deep_work"]
    if sleep_corr["r"] is not None:
        observations.append(
            f"Sleep correlates with deep work at r={sleep_corr['r']:.2f} across {sleep_corr['n']} days."
        )
    energy_corr = corr["energy_vs_deep_work"]
    if energy_corr["r"] is not None:
        observations.append(
            f"Energy correlates with deep work at r={energy_corr['r']:.2f} across {energy_corr['n']} days."
        )

    # 5. Funnel ghost count
    fun = funnel.compute(as_of=as_of)
    if fun["total_applications"] > 0:
        observations.append(
            f"{fun['ghost_count']} of {fun['total_applications']} applications are ghosted "
            f"per the {GHOST_DAYS}-day no-movement rule."
        )

    # 6. Decay
    dec = decay.compute(as_of=as_of)
    stale_count = len(dec["projects"]) + len(dec["cert_domains"]) + len(dec["applications"])
    if stale_count > 0:
        observations.append(
            f"{stale_count} item(s) untouched for >= {DECAY_DAYS} days: "
            f"{len(dec['projects'])} project(s), {len(dec['cert_domains'])} cert domain(s), "
            f"{len(dec['applications'])} application(s)."
        )

    return observations[:MAX_OBSERVATIONS]
