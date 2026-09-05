"""
GET /api/analytics/correlations/ — Pearson r for sleep vs deep work and
energy vs deep work, trend line endpoints for both, and the median deep-work
split above/below the DEEP_WORK_SPLIT_HOURS (6.5h) sleep threshold.
"""
from core import stats
from core.constants import DEEP_WORK_SPLIT_HOURS
from core.models import DailyLog, SleepLog


def compute(daily_logs_qs=None, sleep_logs_qs=None):
    daily_logs_qs = daily_logs_qs if daily_logs_qs is not None else DailyLog.objects.all()
    sleep_logs_qs = sleep_logs_qs if sleep_logs_qs is not None else SleepLog.objects.all()

    sleep_by_date = {s.log_date: s for s in sleep_logs_qs}
    daily_logs = list(daily_logs_qs)

    # --- sleep vs deep work ---
    sleep_hours, deep_work_for_sleep = [], []
    below_threshold, at_or_above_threshold = [], []
    for log in daily_logs:
        sleep = sleep_by_date.get(log.log_date)
        if sleep is None or sleep.hours is None:
            continue
        hours = float(sleep.hours)
        sleep_hours.append(hours)
        deep_work_for_sleep.append(log.deep_work_minutes)
        if hours >= DEEP_WORK_SPLIT_HOURS:
            at_or_above_threshold.append(log.deep_work_minutes)
        else:
            below_threshold.append(log.deep_work_minutes)

    sleep_vs_deep_work = {
        "r": stats.pearson_r(sleep_hours, deep_work_for_sleep),
        "trend_line": stats.trend_line_endpoints(sleep_hours, deep_work_for_sleep),
        "n": len(sleep_hours),
    }

    deep_work_split = {
        "threshold_hours": DEEP_WORK_SPLIT_HOURS,
        "below": {"n": len(below_threshold), "median_deep_work_minutes": stats.median(below_threshold)},
        "at_or_above": {
            "n": len(at_or_above_threshold),
            "median_deep_work_minutes": stats.median(at_or_above_threshold),
        },
    }

    # --- energy vs deep work ---
    energy_values = [log.energy for log in daily_logs if log.energy is not None]
    deep_work_for_energy = [log.deep_work_minutes for log in daily_logs if log.energy is not None]

    energy_vs_deep_work = {
        "r": stats.pearson_r(energy_values, deep_work_for_energy),
        "trend_line": stats.trend_line_endpoints(energy_values, deep_work_for_energy),
        "n": len(energy_values),
    }

    return {
        "sleep_vs_deep_work": sleep_vs_deep_work,
        "energy_vs_deep_work": energy_vs_deep_work,
        "deep_work_split_by_sleep": deep_work_split,
    }
