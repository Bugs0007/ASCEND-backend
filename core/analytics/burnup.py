"""
GET /api/analytics/burnup/ — milestones planned vs completed per week
(cumulative), with a linear projection of the completed line to week 13.

"Planned by week N" = milestones with a due_date on or before week N's end.
"Completed by week N" = milestones with a completed_on on or before week N's
end. Both are cumulative counts, which is what makes this a burn-up chart
rather than a per-week tally.
"""
from core import stats
from core.constants import PROGRAM_TOTAL_WEEKS
from core.models import Milestone, Week


def compute(milestones_qs=None, weeks_qs=None):
    milestones_qs = milestones_qs if milestones_qs is not None else Milestone.objects.all()
    weeks_qs = weeks_qs if weeks_qs is not None else Week.objects.order_by("week_no")

    milestones = list(milestones_qs)
    weeks = list(weeks_qs)

    rows = []
    for week in weeks:
        planned_cumulative = sum(
            1 for m in milestones if m.due_date is not None and m.due_date <= week.end_date
        )
        completed_cumulative = sum(
            1 for m in milestones if m.completed_on is not None and m.completed_on <= week.end_date
        )
        rows.append(
            {
                "week_no": week.week_no,
                "planned_cumulative": planned_cumulative,
                "completed_cumulative": completed_cumulative,
            }
        )

    xs = [row["week_no"] for row in rows]
    ys = [row["completed_cumulative"] for row in rows]
    projection_at_final_week = stats.project_at(xs, ys, PROGRAM_TOTAL_WEEKS)

    return {
        "weeks": rows,
        "final_week": PROGRAM_TOTAL_WEEKS,
        "projected_completed_at_final_week": projection_at_final_week,
    }
