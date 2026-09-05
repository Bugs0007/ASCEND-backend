import datetime

import pytest

from core.analytics import activity
from core.models import ActivitySample
from core.tests.factories import make_block_entry, make_daily_log

pytestmark = pytest.mark.django_db

DAY0 = datetime.date(2026, 9, 7)


class TestActivity:
    def test_insufficient_data_when_empty(self):
        result = activity.compute()
        assert result == {"insufficient_data": True}

    def test_active_vs_elapsed_once_populated(self):
        log = make_daily_log(DAY0)
        entry = make_block_entry(
            log, block_code="B1",
            started_at=datetime.datetime(2026, 9, 7, 9, 0, tzinfo=datetime.timezone.utc),
            ended_at=datetime.datetime(2026, 9, 7, 10, 30, tzinfo=datetime.timezone.utc),
        )
        ActivitySample.objects.create(
            block_entry=entry,
            started_at=entry.started_at,
            ended_at=entry.started_at + datetime.timedelta(minutes=60),
            app="VSCode",
            category=ActivitySample.Category.BUILD,
            active_seconds=3000,
        )
        ActivitySample.objects.create(
            block_entry=entry,
            started_at=entry.started_at + datetime.timedelta(minutes=60),
            ended_at=entry.ended_at,
            app="Twitter",
            category=ActivitySample.Category.DISTRACTION,
            active_seconds=900,
        )
        result = activity.compute()
        assert result["insufficient_data"] is False
        assert result["active_vs_elapsed_by_block"]["B1"]["active_seconds"] == 3900
        assert result["category_split_seconds"]["build"] == 3000
        assert result["category_split_seconds"]["distraction"] == 900
        assert result["top_distractions"][0]["app"] == "Twitter"
