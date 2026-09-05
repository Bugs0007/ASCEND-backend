"""
GET /api/analytics/activity/ — once ActivitySample has rows: active vs
elapsed time per block, category split, top distractions. Nothing writes to
ActivitySample in v1 (an external agent populates it later), so this
returns an explicit `insufficient_data: true` flag rather than zeros that
could be misread as "no distractions" when really it's "no data at all".
"""
from core import stats
from core.models import ActivitySample


def compute(samples_qs=None):
    samples_qs = samples_qs if samples_qs is not None else ActivitySample.objects.all()
    samples = list(samples_qs.select_related("block_entry__block"))

    if not samples:
        return {"insufficient_data": True}

    by_block = {}
    for sample in samples:
        if sample.block_entry is None:
            continue
        code = sample.block_entry.block.code
        by_block.setdefault(code, {"active_seconds": 0, "elapsed_seconds": 0})
        by_block[code]["active_seconds"] += sample.active_seconds
        if sample.block_entry.elapsed_minutes:
            by_block[code]["elapsed_seconds"] = sample.block_entry.elapsed_minutes * 60

    active_vs_elapsed = {
        code: {
            "active_seconds": v["active_seconds"],
            "elapsed_seconds": v["elapsed_seconds"],
            "active_ratio": stats.safe_div(v["active_seconds"], v["elapsed_seconds"]),
        }
        for code, v in by_block.items()
    }

    category_split = {}
    for sample in samples:
        category_split[sample.category] = category_split.get(sample.category, 0) + sample.active_seconds

    distractions = [s for s in samples if s.category == ActivitySample.Category.DISTRACTION]
    by_app = {}
    for s in distractions:
        by_app[s.app] = by_app.get(s.app, 0) + s.active_seconds
    top_distractions = sorted(
        ({"app": app, "active_seconds": secs} for app, secs in by_app.items()),
        key=lambda row: row["active_seconds"],
        reverse=True,
    )[:10]

    return {
        "insufficient_data": False,
        "active_vs_elapsed_by_block": active_vs_elapsed,
        "category_split_seconds": category_split,
        "top_distractions": top_distractions,
    }
