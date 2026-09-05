import datetime

import pytest

from core.analytics import observations
from core.constants import MIN_DAYS_FOR_OBSERVATIONS
from core.tests.factories import make_daily_log

pytestmark = pytest.mark.django_db

DAY0 = datetime.date(2026, 9, 7)


class TestObservations:
    def test_empty_below_seven_days(self):
        assert MIN_DAYS_FOR_OBSERVATIONS == 7
        for i in range(MIN_DAYS_FOR_OBSERVATIONS - 1):  # 6 days
            make_daily_log(DAY0 + datetime.timedelta(days=i), deep_work_minutes=100)
        result = observations.compute(as_of=DAY0 + datetime.timedelta(days=5))
        assert result == []

    def test_non_empty_at_seven_days(self):
        for i in range(MIN_DAYS_FOR_OBSERVATIONS):  # 7 days
            make_daily_log(DAY0 + datetime.timedelta(days=i), deep_work_minutes=100)
        result = observations.compute(as_of=DAY0 + datetime.timedelta(days=6))
        assert len(result) >= 1
        assert all(isinstance(s, str) for s in result)

    def test_never_exceeds_max_observations(self):
        from core.constants import MAX_OBSERVATIONS

        for i in range(20):
            make_daily_log(DAY0 + datetime.timedelta(days=i), deep_work_minutes=100 + i)
        result = observations.compute(as_of=DAY0 + datetime.timedelta(days=19))
        assert len(result) <= MAX_OBSERVATIONS
