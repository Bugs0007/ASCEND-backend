import datetime

import pytest

from core.analytics import certtrend
from core.models import Countdown
from core.tests.factories import make_practice_test

pytestmark = pytest.mark.django_db


class TestCertTrend:
    def test_no_tests_yet(self):
        result = certtrend.compute()
        assert result["tests"] == []
        assert result["projected_score_at_exam"] is None
        assert result["reason"] == "no practice tests recorded yet"

    def test_single_test_cannot_project(self):
        make_practice_test(taken_on=datetime.date(2026, 9, 15), score=650)
        result = certtrend.compute()
        assert result["projected_score_at_exam"] is None
        assert result["reason"] == "need at least 2 practice tests to fit a trend"

    def test_no_exam_date_set(self):
        make_practice_test(taken_on=datetime.date(2026, 9, 15), score=600)
        make_practice_test(taken_on=datetime.date(2026, 10, 1), score=700)
        Countdown.objects.filter(label="AI-103 exam").update(target_date=None)
        result = certtrend.compute()
        assert result["exam_date"] is None
        assert result["projected_score_at_exam"] is None
        assert result["reason"] == "exam date not set"

    def test_projection_with_exam_date(self):
        # Two tests two weeks apart, +100 score over 16 days -> project
        # forward to a known exam date and hand-check the linear fit.
        d1 = datetime.date(2026, 9, 1)
        d2 = datetime.date(2026, 9, 17)  # 16 days later
        make_practice_test(taken_on=d1, score=600, max_score=1000)
        make_practice_test(taken_on=d2, score=700, max_score=1000)
        exam_date = datetime.date(2026, 10, 17)  # 46 days after d1
        result = certtrend.compute(exam_date=exam_date)
        # slope = 100/16 points per day; projected = 600 + (46)*100/16
        expected = 600 + (46 * 100 / 16)
        assert result["projected_score_at_exam"] == pytest.approx(expected)
        assert result["reason"] is None
