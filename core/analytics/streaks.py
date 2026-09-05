"""
Streak and green-day computation.

A day is "green" once at least GREEN_DAY_BLOCK_THRESHOLD (4) of its 5 blocks
are marked completed. The streak is the count of consecutive green days
ending at (and including) `as_of`, walking backwards until a day is missing
or not green.
"""
import datetime

from django.utils import timezone

from core.constants import GREEN_DAY_BLOCK_THRESHOLD
from core.models import DailyLog


def is_green_day(daily_log):
    """True once >= GREEN_DAY_BLOCK_THRESHOLD blocks are completed for this log."""
    if daily_log is None:
        return False
    completed = daily_log.block_entries.filter(completed=True).count()
    return completed >= GREEN_DAY_BLOCK_THRESHOLD


def current_streak(as_of=None, daily_logs_qs=None):
    """
    Consecutive green days ending at `as_of` (default: today in local tz).
    Zero if `as_of` itself has no log or isn't green.
    """
    as_of = as_of or timezone.localdate()
    qs = daily_logs_qs if daily_logs_qs is not None else DailyLog.objects.all()

    logs_by_date = {log.log_date: log for log in qs.filter(log_date__lte=as_of)}

    streak = 0
    day = as_of
    while True:
        log = logs_by_date.get(day)
        if log is None or not is_green_day(log):
            break
        streak += 1
        day -= datetime.timedelta(days=1)
    return streak
