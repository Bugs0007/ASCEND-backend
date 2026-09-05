import datetime

import pytest

from core.analytics import correlations
from core.constants import DEEP_WORK_SPLIT_HOURS
from core.tests.factories import make_daily_log, make_sleep_log

pytestmark = pytest.mark.django_db

DAY0 = datetime.date(2026, 9, 7)


def _dt(day_offset, hour, minute=0):
    day = DAY0 + datetime.timedelta(days=day_offset)
    return datetime.datetime(day.year, day.month, day.day, hour, minute, tzinfo=datetime.timezone.utc)


class TestSleepVsDeepWork:
    def test_hand_computed_pearson_r(self):
        # sleep hours vs deep_work_minutes, same relationship as the
        # hand-computed fixture in test_stats: xs=[1,2,3,4,5] ys=[2,1,4,3,5]
        # scaled so the numbers make sense as hours/minutes.
        sleep_hours = [5, 6, 7, 8, 9]  # analog of xs shifted, but reuse ys pattern
        deep_work = [20, 10, 40, 30, 50]  # analog of ys * 10
        for i, (h, dw) in enumerate(zip(sleep_hours, deep_work)):
            log_date = DAY0 + datetime.timedelta(days=i)
            make_daily_log(log_date, deep_work_minutes=dw, energy=3)
            make_sleep_log(
                log_date,
                bed_at=_dt(i, 22),
                wake_at=_dt(i, 22) + datetime.timedelta(hours=h),
            )
        result = correlations.compute()
        assert result["sleep_vs_deep_work"]["r"] == pytest.approx(0.8, abs=1e-6)
        assert result["sleep_vs_deep_work"]["n"] == 5

    def test_no_sleep_data_returns_none(self):
        make_daily_log(DAY0, deep_work_minutes=100)
        result = correlations.compute()
        assert result["sleep_vs_deep_work"]["r"] is None
        assert result["sleep_vs_deep_work"]["n"] == 0

    def test_deep_work_split_by_threshold(self):
        # Below 6.5h: deep work 60, 80 (median 70). At/above 6.5h: 200, 240 (median 220).
        pairs = [(5.0, 60), (6.0, 80), (7.0, 200), (8.0, 240)]
        for i, (hours, dw) in enumerate(pairs):
            log_date = DAY0 + datetime.timedelta(days=i)
            make_daily_log(log_date, deep_work_minutes=dw)
            make_sleep_log(
                log_date,
                bed_at=_dt(i, 22),
                wake_at=_dt(i, 22) + datetime.timedelta(hours=hours),
            )
        result = correlations.compute()
        split = result["deep_work_split_by_sleep"]
        assert split["threshold_hours"] == DEEP_WORK_SPLIT_HOURS
        assert split["below"]["n"] == 2
        assert split["below"]["median_deep_work_minutes"] == pytest.approx(70)
        assert split["at_or_above"]["n"] == 2
        assert split["at_or_above"]["median_deep_work_minutes"] == pytest.approx(220)


class TestEnergyVsDeepWork:
    def test_perfect_correlation(self):
        for i, (energy, dw) in enumerate([(1, 20), (2, 40), (3, 60), (4, 80), (5, 100)]):
            make_daily_log(DAY0 + datetime.timedelta(days=i), deep_work_minutes=dw, energy=energy)
        result = correlations.compute()
        assert result["energy_vs_deep_work"]["r"] == pytest.approx(1.0)
        assert result["energy_vs_deep_work"]["n"] == 5
