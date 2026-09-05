import pytest

from core.analytics import burnup
from core.models import Week
from core.tests.factories import make_milestone

pytestmark = pytest.mark.django_db


class TestBurnup:
    def test_planned_and_completed_are_cumulative(self):
        weeks = list(Week.objects.filter(week_no__in=[1, 2, 3, 4]).order_by("week_no"))
        w1, w2, w3, w4 = weeks

        # One milestone due in week 1 (planned from week1 onward), one due
        # week 3. One completed in week 2, one completed in week 4.
        make_milestone("m1", due_date=w1.end_date, completed_on=w2.end_date, evidence_url="https://example.com/1")
        make_milestone("m2", due_date=w3.end_date, completed_on=w4.end_date, evidence_url="https://example.com/2")

        result = burnup.compute(weeks_qs=Week.objects.filter(week_no__in=[1, 2, 3, 4]))
        rows = {row["week_no"]: row for row in result["weeks"]}

        assert rows[1]["planned_cumulative"] == 1  # m1 due
        assert rows[1]["completed_cumulative"] == 0
        assert rows[2]["planned_cumulative"] == 1
        assert rows[2]["completed_cumulative"] == 1  # m1 completed
        assert rows[3]["planned_cumulative"] == 2  # m2 due
        assert rows[3]["completed_cumulative"] == 1
        assert rows[4]["planned_cumulative"] == 2
        assert rows[4]["completed_cumulative"] == 2  # m2 completed

    def test_linear_projection_to_final_week(self):
        # Hand-computed: completed_cumulative = week_no exactly for weeks
        # 1..4 (slope=1, intercept=0) -> projection at week 13 must be 13.
        weeks = list(Week.objects.filter(week_no__in=[1, 2, 3, 4]).order_by("week_no"))
        for week in weeks:
            make_milestone(
                f"complete-{week.week_no}",
                due_date=week.end_date,
                completed_on=week.end_date,
                evidence_url=f"https://example.com/{week.week_no}",
            )
        result = burnup.compute(weeks_qs=Week.objects.filter(week_no__in=[1, 2, 3, 4]))
        rows = {row["week_no"]: row["completed_cumulative"] for row in result["weeks"]}
        assert rows == {1: 1, 2: 2, 3: 3, 4: 4}
        assert result["projected_completed_at_final_week"] == pytest.approx(13.0)

    def test_empty_milestones_projection_is_none(self):
        result = burnup.compute(weeks_qs=Week.objects.filter(week_no__in=[1]))
        assert result["projected_completed_at_final_week"] is None  # <2 points
