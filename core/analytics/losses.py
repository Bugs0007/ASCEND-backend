"""
GET /api/analytics/losses/ — post-mortems grouped by cause, with the
dominant cause named once a bucket reaches MIN_POSTMORTEMS_FOR_DOMINANT_CAUSE
(3) entries.
"""
from core.constants import MIN_POSTMORTEMS_FOR_DOMINANT_CAUSE
from core.models import LossPostmortem


def compute(postmortems_qs=None):
    postmortems_qs = postmortems_qs if postmortems_qs is not None else LossPostmortem.objects.all()
    postmortems = list(postmortems_qs)

    by_cause = {}
    for pm in postmortems:
        by_cause[pm.cause] = by_cause.get(pm.cause, 0) + 1

    dominant_cause = None
    if by_cause:
        top_cause, top_count = max(by_cause.items(), key=lambda kv: kv[1])
        if top_count >= MIN_POSTMORTEMS_FOR_DOMINANT_CAUSE:
            # Only "the" dominant cause if it's an outright max — a tie at
            # the top means no single cause dominates yet.
            tied = [c for c, n in by_cause.items() if n == top_count]
            if len(tied) == 1:
                dominant_cause = top_cause

    return {
        "by_cause": by_cause,
        "total": len(postmortems),
        "dominant_cause": dominant_cause,
    }
