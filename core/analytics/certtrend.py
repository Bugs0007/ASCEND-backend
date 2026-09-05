"""
GET /api/analytics/certtrend/ — practice test scores (normalized to a
0-AI103_MAX_SCORE scale so differing max_score values stay comparable),
with a linear projection to the exam date. AI-103 exam date is TBD until
the Countdown row with label="AI-103 exam" is given a target_date — the
projection is null with an explicit reason until then.
"""
from core import stats
from core.constants import AI103_MAX_SCORE, AI103_PASS_MARK
from core.models import Countdown, PracticeTest


def _normalized(test):
    pct = stats.safe_div(test.score, test.max_score)
    if pct is None:
        return None
    return pct * AI103_MAX_SCORE


def compute(practice_tests_qs=None, cert_code="AI-103", exam_date=None):
    practice_tests_qs = (
        practice_tests_qs if practice_tests_qs is not None else PracticeTest.objects.all()
    )
    tests = list(practice_tests_qs.filter(cert_code=cert_code).order_by("taken_on"))

    if exam_date is None:
        countdown = Countdown.objects.filter(label="AI-103 exam").first()
        exam_date = countdown.target_date if countdown else None

    test_rows = [
        {
            "taken_on": t.taken_on,
            "score": t.score,
            "max_score": t.max_score,
            "normalized_score": _normalized(t),
        }
        for t in tests
    ]

    projected_score = None
    reason = None
    if not tests:
        reason = "no practice tests recorded yet"
    elif len(tests) < 2:
        reason = "need at least 2 practice tests to fit a trend"
    elif exam_date is None:
        reason = "exam date not set"
    else:
        xs = [t.taken_on.toordinal() for t in tests]
        ys = [_normalized(t) for t in tests]
        projected_score = stats.project_at(xs, ys, exam_date.toordinal())

    return {
        "cert_code": cert_code,
        "pass_mark": AI103_PASS_MARK,
        "max_score": AI103_MAX_SCORE,
        "exam_date": exam_date,
        "tests": test_rows,
        "projected_score_at_exam": projected_score,
        "reason": reason,
    }
