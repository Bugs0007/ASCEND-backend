"""
Streak and green-day computation.

A day is "green" once at least `green_threshold(planned)` of that day's
TodaySelection tasks are done — ceil(planned * GREEN_DAY_DONE_NUMERATOR /
GREEN_DAY_DONE_DENOMINATOR), with a minimum of one planned task. The streak is
the count of consecutive green days ending at (and including) `as_of`, walking
backwards until a day is missing or not green.

(Until 2026-09 a day was green at 4 of 5 fixed blocks. Blocks are retired as
the daily unit — see core.models.TodaySelection — and the rule now scales with
however many tasks the day actually had.)
"""
import datetime

from django.utils import timezone

from core.constants import GREEN_DAY_DONE_DENOMINATOR, GREEN_DAY_DONE_NUMERATOR
from core.models import TodaySelection


def green_threshold(planned):
    """Minimum done-count for a `planned`-task day to count as green, or None
    if the day had nothing planned (an empty day is never green)."""
    if planned < 1:
        return None
    # Integer ceil division — avoids float rounding making 3 * (2/3) == 3.
    return -(-planned * GREEN_DAY_DONE_NUMERATOR // GREEN_DAY_DONE_DENOMINATOR)


def is_green_day(selections):
    """`selections`: an iterable of TodaySelection rows for a single date."""
    selections = list(selections)
    threshold = green_threshold(len(selections))
    if threshold is None:
        return False
    done = sum(1 for s in selections if s.done)
    return done >= threshold


def current_streak(as_of=None, selections_qs=None):
    """
    Consecutive green days ending at `as_of` (default: today in local tz).
    Zero if `as_of` itself has no selections or isn't green.
    """
    as_of = as_of or timezone.localdate()
    qs = selections_qs if selections_qs is not None else TodaySelection.objects.all()

    by_date = {}
    for s in qs.filter(date__lte=as_of):
        by_date.setdefault(s.date, []).append(s)

    streak = 0
    day = as_of
    while True:
        selections = by_date.get(day)
        if not selections or not is_green_day(selections):
            break
        streak += 1
        day -= datetime.timedelta(days=1)
    return streak
