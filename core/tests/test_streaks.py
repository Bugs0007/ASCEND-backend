import datetime

import pytest

from core.analytics import streaks
from core.constants import GREEN_DAY_BLOCK_THRESHOLD
from core.tests.factories import make_green_day

pytestmark = pytest.mark.django_db

DAY0 = datetime.date(2026, 9, 7)


class TestGreenDayBoundary:
    """The threshold is GREEN_DAY_BLOCK_THRESHOLD = 4 of 5 blocks."""

    def test_three_of_five_is_not_green(self):
        log = make_green_day(DAY0, blocks_completed=3)
        assert not streaks.is_green_day(log)

    def test_four_of_five_is_green(self):
        assert GREEN_DAY_BLOCK_THRESHOLD == 4  # pin the constant this test relies on
        log = make_green_day(DAY0, blocks_completed=4)
        assert streaks.is_green_day(log)

    def test_five_of_five_is_green(self):
        log = make_green_day(DAY0, blocks_completed=5)
        assert streaks.is_green_day(log)

    def test_zero_of_five_is_not_green(self):
        log = make_green_day(DAY0, blocks_completed=0)
        assert not streaks.is_green_day(log)


class TestCurrentStreak:
    def test_no_logs_at_all(self):
        assert streaks.current_streak(as_of=DAY0) == 0

    def test_single_green_day(self):
        make_green_day(DAY0, blocks_completed=4)
        assert streaks.current_streak(as_of=DAY0) == 1

    def test_three_consecutive_green_days(self):
        for i in range(3):
            make_green_day(DAY0 + datetime.timedelta(days=i), blocks_completed=4)
        assert streaks.current_streak(as_of=DAY0 + datetime.timedelta(days=2)) == 3

    def test_streak_breaks_on_a_three_of_five_day(self):
        make_green_day(DAY0, blocks_completed=4)
        make_green_day(DAY0 + datetime.timedelta(days=1), blocks_completed=3)  # breaks it
        make_green_day(DAY0 + datetime.timedelta(days=2), blocks_completed=4)
        # Streak counted from day 2 backwards: day2 is green, day1 is not -> streak=1
        assert streaks.current_streak(as_of=DAY0 + datetime.timedelta(days=2)) == 1

    def test_streak_breaks_on_a_missing_day(self):
        make_green_day(DAY0, blocks_completed=4)
        # day 1 has no DailyLog at all
        make_green_day(DAY0 + datetime.timedelta(days=2), blocks_completed=4)
        assert streaks.current_streak(as_of=DAY0 + datetime.timedelta(days=2)) == 1

    def test_as_of_not_green_gives_zero(self):
        make_green_day(DAY0, blocks_completed=4)
        make_green_day(DAY0 + datetime.timedelta(days=1), blocks_completed=2)
        assert streaks.current_streak(as_of=DAY0 + datetime.timedelta(days=1)) == 0
