import datetime

import pytest

from core.analytics import streaks
from core.tests.factories import make_planned_day, make_today_selection

pytestmark = pytest.mark.django_db

DAY0 = datetime.date(2026, 9, 7)


class TestGreenThreshold:
    """ceil(planned * 2 / 3), min one planned task."""

    @pytest.mark.parametrize(
        "planned,expected",
        [(1, 1), (2, 2), (3, 2), (4, 3), (5, 4), (6, 4), (9, 6)],
    )
    def test_threshold_scales_with_planned(self, planned, expected):
        assert streaks.green_threshold(planned) == expected

    def test_zero_planned_has_no_threshold(self):
        assert streaks.green_threshold(0) is None


class TestGreenDayBoundary:
    def test_empty_day_is_not_green(self):
        assert not streaks.is_green_day([])

    def test_three_of_five_is_not_green(self):
        rows = make_planned_day(DAY0, planned=5, done=3)
        assert not streaks.is_green_day(rows)

    def test_four_of_five_is_green(self):
        rows = make_planned_day(DAY0, planned=5, done=4)
        assert streaks.is_green_day(rows)

    def test_five_of_five_is_green(self):
        rows = make_planned_day(DAY0, planned=5, done=5)
        assert streaks.is_green_day(rows)

    def test_two_of_three_is_green(self):
        rows = make_planned_day(DAY0, planned=3, done=2)
        assert streaks.is_green_day(rows)

    def test_one_of_three_is_not_green(self):
        rows = make_planned_day(DAY0, planned=3, done=1)
        assert not streaks.is_green_day(rows)

    def test_one_task_all_done_is_green(self):
        rows = make_planned_day(DAY0, planned=1, done=1)
        assert streaks.is_green_day(rows)

    def test_zero_done_is_not_green(self):
        rows = make_planned_day(DAY0, planned=4, done=0)
        assert not streaks.is_green_day(rows)


class TestCurrentStreak:
    def test_no_selections_at_all(self):
        assert streaks.current_streak(as_of=DAY0) == 0

    def test_a_day_with_only_a_daily_log_is_not_green(self):
        # An energy/steps quick-log with no committed tasks doesn't count.
        from core.tests.factories import make_daily_log

        make_daily_log(DAY0)
        assert streaks.current_streak(as_of=DAY0) == 0

    def test_single_green_day(self):
        make_planned_day(DAY0, planned=5, done=4)
        assert streaks.current_streak(as_of=DAY0) == 1

    def test_three_consecutive_green_days(self):
        for i in range(3):
            make_planned_day(DAY0 + datetime.timedelta(days=i), planned=3, done=2)
        assert streaks.current_streak(as_of=DAY0 + datetime.timedelta(days=2)) == 3

    def test_streak_breaks_on_a_sub_threshold_day(self):
        make_planned_day(DAY0, planned=5, done=4)
        make_planned_day(DAY0 + datetime.timedelta(days=1), planned=5, done=3)  # breaks it
        make_planned_day(DAY0 + datetime.timedelta(days=2), planned=5, done=4)
        assert streaks.current_streak(as_of=DAY0 + datetime.timedelta(days=2)) == 1

    def test_streak_breaks_on_a_missing_day(self):
        make_planned_day(DAY0, planned=5, done=4)
        # day 1 has no selections at all
        make_planned_day(DAY0 + datetime.timedelta(days=2), planned=5, done=4)
        assert streaks.current_streak(as_of=DAY0 + datetime.timedelta(days=2)) == 1

    def test_as_of_not_green_gives_zero(self):
        make_planned_day(DAY0, planned=5, done=4)
        make_planned_day(DAY0 + datetime.timedelta(days=1), planned=5, done=2)
        assert streaks.current_streak(as_of=DAY0 + datetime.timedelta(days=1)) == 0

    def test_mixed_source_types_still_count(self):
        make_today_selection(DAY0, title="from notion", source_type="notion", source_id=1, done=True, position=1)
        make_today_selection(DAY0, title="one-off", source_type="adhoc", done=True, position=2)
        assert streaks.current_streak(as_of=DAY0) == 1
