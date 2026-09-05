"""
GET /api/analytics/rhythm/ — start-time distribution per block (with IQR)
and per-block completion rate.

"Start time" is when a block was first tapped (BlockEntry.started_at),
expressed as minutes-since-local-midnight so the distribution is
timezone-correct (Asia/Kolkata by default) rather than raw UTC clock time.
"""
from django.utils import timezone

from core import stats
from core.models import Block, BlockEntry


def _minutes_since_midnight(dt):
    local = timezone.localtime(dt)
    return local.hour * 60 + local.minute + local.second / 60


def compute(entries_qs=None):
    entries_qs = entries_qs if entries_qs is not None else BlockEntry.objects.all()
    entries = list(entries_qs.select_related("block"))

    blocks_out = {}
    for block in Block.objects.all():
        block_entries = [e for e in entries if e.block_id == block.id]
        total = len(block_entries)
        completed = sum(1 for e in block_entries if e.completed)
        started_minutes = [
            _minutes_since_midnight(e.started_at) for e in block_entries if e.started_at is not None
        ]
        blocks_out[block.code] = {
            "label": block.label,
            "category": block.category,
            "n": total,
            "completion_rate": stats.safe_div(completed, total),
            "start_minutes_iqr": stats.iqr(started_minutes),
        }

    return {"blocks": blocks_out}
