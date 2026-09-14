import datetime
from unittest.mock import patch

import pytest

from core import notion_sync
from core.models import DailyRecommendation, NotionTask, TodaySelection
from core.tests.factories import (
    make_backlog_item,
    make_daily_log,
    make_daily_recommendation,
    make_notion_task,
    make_today_selection,
)

pytestmark = pytest.mark.django_db


class TestTodayPool:
    def test_merges_pending_backlog_and_open_notion_rows(self, auth_client):
        make_backlog_item(title="Backlog pending", status="pending")
        make_backlog_item(title="Backlog done", status="done")
        make_notion_task("n-open", title="Notion open", status="In Progress")
        make_notion_task("n-done", title="Notion done", status="Completed")

        resp = auth_client.get("/api/today/pool/")
        assert resp.status_code == 200
        by_title = {r["title"]: r for r in resp.data["results"]}
        assert "Backlog pending" in by_title
        assert "Backlog done" not in by_title
        assert "Notion open" in by_title
        assert "Notion done" not in by_title
        assert by_title["Backlog pending"]["source"] == "backlog"
        assert by_title["Notion open"]["source"] == "notion"

    def test_done_like_notion_statuses_are_all_excluded(self, auth_client):
        for i, status in enumerate(["Done", "shipped", "ARCHIVED", "closed", "complete"]):
            make_notion_task(f"n{i}", title=f"t{i}", status=status)
        make_notion_task("keep", title="keep me", status="To Do")

        resp = auth_client.get("/api/today/pool/")
        titles = {r["title"] for r in resp.data["results"]}
        assert titles == {"keep me"}

    def test_ingest_token_also_allowed(self, ingest_client):
        assert ingest_client.get("/api/today/pool/").status_code == 200

    def test_requires_auth(self, api_client):
        assert api_client.get("/api/today/pool/").status_code == 401


class TestRecommendations:
    def test_post_replaces_the_days_set(self, ingest_client):
        first = ingest_client.post(
            "/api/today/recommendations/",
            [{"title": "One", "rationale": "r1", "source_project": "case-intel"}],
            format="json",
        )
        assert first.status_code == 201
        assert len(first.data["results"]) == 1

        second = ingest_client.post(
            "/api/today/recommendations/",
            [
                {"title": "Two", "rationale": "r2", "source_project": "ai-103"},
                {"title": "Three", "rationale": "r3", "source_project": "other"},
            ],
            format="json",
        )
        assert second.status_code == 201
        titles = [r["title"] for r in second.data["results"]]
        assert titles == ["Two", "Three"]
        # "One" is gone — POST is a replace, not an append.
        assert DailyRecommendation.objects.count() == 2

    def test_get_by_date(self, auth_client):
        make_daily_recommendation(datetime.date(2026, 9, 20), title="Future rec")
        resp = auth_client.get("/api/today/recommendations/?date=2026-09-20")
        assert resp.status_code == 200
        assert [r["title"] for r in resp.data["results"]] == ["Future rec"]

    def test_get_default_date_is_today(self, auth_client):
        import django.utils.timezone as tz

        resp = auth_client.get("/api/today/recommendations/")
        assert resp.status_code == 200
        # resp.data is pre-render — a date object, not a string.
        assert resp.data["date"] == tz.localdate()

    def test_empty_post_is_400(self, ingest_client):
        resp = ingest_client.post("/api/today/recommendations/", [], format="json")
        assert resp.status_code == 400

    def test_bad_date_param_is_400(self, auth_client):
        assert auth_client.get("/api/today/recommendations/?date=nope").status_code == 400


class TestSelections:
    def test_post_appends_and_assigns_positions(self, auth_client):
        b = make_backlog_item(title="from backlog")
        r1 = auth_client.post(
            "/api/today/selections/",
            [{"source_type": "backlog", "source_id": b.id, "title": "from backlog"}],
            format="json",
        )
        assert r1.status_code == 201
        assert len(r1.data["results"]) == 1
        assert r1.data["results"][0]["position"] == 1

        r2 = auth_client.post(
            "/api/today/selections/",
            [{"source_type": "adhoc", "title": "a one-off"}],
            format="json",
        )
        positions = [row["position"] for row in r2.data["results"]]
        assert positions == [1, 2]
        assert [row["title"] for row in r2.data["results"]] == ["from backlog", "a one-off"]

    def test_reposting_the_same_non_adhoc_item_is_idempotent(self, auth_client):
        b = make_backlog_item(title="dedupe me")
        body = [{"source_type": "backlog", "source_id": b.id, "title": "dedupe me"}]
        auth_client.post("/api/today/selections/", body, format="json")
        resp = auth_client.post("/api/today/selections/", body, format="json")
        assert len(resp.data["results"]) == 1
        assert TodaySelection.objects.count() == 1

    def test_adhoc_rows_are_never_deduped(self, auth_client):
        body = [{"source_type": "adhoc", "title": "same words"}]
        auth_client.post("/api/today/selections/", body, format="json")
        auth_client.post("/api/today/selections/", body, format="json")
        assert TodaySelection.objects.filter(title="same words").count() == 2

    def test_adhoc_with_source_id_is_400(self, auth_client):
        resp = auth_client.post(
            "/api/today/selections/",
            [{"source_type": "adhoc", "source_id": 5, "title": "x"}],
            format="json",
        )
        assert resp.status_code == 400

    def test_non_adhoc_without_source_id_is_400(self, auth_client):
        resp = auth_client.post(
            "/api/today/selections/",
            [{"source_type": "notion", "title": "x"}],
            format="json",
        )
        assert resp.status_code == 400

    def test_patch_minutes_and_done(self, auth_client):
        row = make_today_selection(datetime.date.today(), title="patch me")
        resp = auth_client.patch(
            f"/api/today/selections/{row.id}/",
            {"minutes_spent": 45, "done": True},
            format="json",
        )
        assert resp.status_code == 200
        row.refresh_from_db()
        assert row.minutes_spent == 45
        assert row.done is True

    def test_patch_empty_body_is_400(self, auth_client):
        row = make_today_selection(datetime.date.today())
        assert auth_client.patch(f"/api/today/selections/{row.id}/", {}, format="json").status_code == 400

    def test_patch_unknown_field_is_400(self, auth_client):
        row = make_today_selection(datetime.date.today())
        resp = auth_client.patch(
            f"/api/today/selections/{row.id}/", {"title": "sneaky"}, format="json"
        )
        assert resp.status_code == 400

    def test_delete_removes_the_row(self, auth_client):
        row = make_today_selection(datetime.date.today(), title="delete me")
        resp = auth_client.delete(f"/api/today/selections/{row.id}/")
        assert resp.status_code == 204
        assert not TodaySelection.objects.filter(id=row.id).exists()

    def test_machine_token_cannot_write_selections(self, ingest_client):
        assert ingest_client.post(
            "/api/today/selections/",
            [{"source_type": "adhoc", "title": "x"}],
            format="json",
        ).status_code in (401, 403)


def _board_schema(options=("To Do", "In Progress", "Completed", "Missed")):
    """The live Daily Board's shape: Status is a select, not a native status."""
    return {
        "object": "database",
        "properties": {
            "Task": {"name": "Task", "type": "title", "title": {}},
            "Status": {
                "name": "Status",
                "type": "select",
                "select": {"options": [{"name": n} for n in options]},
            },
        },
    }


@patch("core.notion_sync._notion_patch")
@patch("core.notion_sync._notion_get")
class TestSelectionDoneWritesBackToNotion:
    """Checking a Notion-sourced TODAY row done completes the Notion page too
    (the same write path as the /board drag); ASCEND-native rows stay local."""

    @pytest.fixture(autouse=True)
    def notion_configured(self, settings):
        settings.NOTION_TOKEN = "fake-notion-token"
        settings.NOTION_DAILY_BOARD_DB_ID = "fake-db-id"

    def _notion_row(self, status="In Progress"):
        task = make_notion_task("page-1", title="Apply to X", status=status)
        row = make_today_selection(
            datetime.date.today(), title=task.title, source_type="notion", source_id=task.id
        )
        return task, row

    def _patch(self, client, row, body):
        return client.patch(f"/api/today/selections/{row.id}/", body, format="json")

    def test_done_completes_the_notion_page(self, mock_get, mock_patch, auth_client):
        mock_get.return_value = _board_schema()
        task, row = self._notion_row()

        resp = self._patch(auth_client, row, {"done": True})

        assert resp.status_code == 200
        assert resp.data["done"] is True
        path, body = mock_patch.call_args.args
        assert path == "/pages/page-1"
        assert body == {"properties": {"Status": {"select": {"name": "Completed"}}}}
        task.refresh_from_db()
        assert task.status == "Completed"  # the /board mirror row, no sync needed
        assert task.status_changed_at is not None
        row.refresh_from_db()
        assert row.notion_prior_status == "In Progress"

    def test_completed_task_leaves_the_planning_pool(self, mock_get, mock_patch, auth_client):
        mock_get.return_value = _board_schema()
        task, row = self._notion_row()

        self._patch(auth_client, row, {"done": True})

        pool = auth_client.get("/api/today/pool/").data["results"]
        assert not [p for p in pool if p["source"] == "notion" and p["source_id"] == task.id]

    def test_notion_failure_leaves_the_row_unchecked(self, mock_get, mock_patch, auth_client):
        mock_get.return_value = _board_schema()
        mock_patch.side_effect = notion_sync.NotionAPIError("Notion said no")
        task, row = self._notion_row()

        resp = self._patch(auth_client, row, {"done": True})

        assert resp.status_code == 502
        row.refresh_from_db()
        assert row.done is False
        assert NotionTask.objects.get(pk=task.pk).status == "In Progress"

    def test_repeated_done_writes_once(self, mock_get, mock_patch, auth_client):
        mock_get.return_value = _board_schema()
        _, row = self._notion_row()

        assert self._patch(auth_client, row, {"done": True}).status_code == 200
        assert self._patch(auth_client, row, {"done": True}).status_code == 200
        assert mock_patch.call_count == 1

    def test_undo_restores_the_prior_status(self, mock_get, mock_patch, auth_client):
        mock_get.return_value = _board_schema()
        task, row = self._notion_row(status="To Do")
        self._patch(auth_client, row, {"done": True})

        resp = self._patch(auth_client, row, {"done": False})

        assert resp.status_code == 200
        _, body = mock_patch.call_args.args
        assert body == {"properties": {"Status": {"select": {"name": "To Do"}}}}
        task.refresh_from_db()
        assert task.status == "To Do"
        row.refresh_from_db()
        assert row.done is False
        assert row.notion_prior_status == ""

    def test_undo_leaves_a_card_moved_on_the_board_alone(self, mock_get, mock_patch, auth_client):
        mock_get.return_value = _board_schema()
        task, row = self._notion_row()
        self._patch(auth_client, row, {"done": True})
        NotionTask.objects.filter(pk=task.pk).update(status="Missed")  # dragged on /board
        mock_patch.reset_mock()

        assert self._patch(auth_client, row, {"done": False}).status_code == 200

        mock_patch.assert_not_called()
        assert NotionTask.objects.get(pk=task.pk).status == "Missed"

    def test_already_completed_task_writes_nothing(self, mock_get, mock_patch, auth_client):
        _, row = self._notion_row(status="Completed")

        assert self._patch(auth_client, row, {"done": True}).status_code == 200
        assert self._patch(auth_client, row, {"done": False}).status_code == 200

        mock_get.assert_not_called()
        mock_patch.assert_not_called()

    def test_ascend_native_rows_stay_local(self, mock_get, mock_patch, auth_client):
        backlog = make_backlog_item(title="Study")
        rows = [
            make_today_selection(
                datetime.date.today(), title="Study", source_type="backlog", source_id=backlog.id
            ),
            make_today_selection(datetime.date.today(), title="One-off"),
        ]

        for row in rows:
            assert self._patch(auth_client, row, {"done": True}).status_code == 200
            row.refresh_from_db()
            assert row.done is True

        mock_get.assert_not_called()
        mock_patch.assert_not_called()

    def test_minutes_only_patch_does_not_touch_notion(self, mock_get, mock_patch, auth_client):
        _, row = self._notion_row()

        assert self._patch(auth_client, row, {"minutes_spent": 30}).status_code == 200

        mock_get.assert_not_called()
        mock_patch.assert_not_called()


class TestTodayViewShape:
    def test_active_response_carries_selections_and_computed_total(self, auth_client):
        from core.constants import PROGRAM_START
        import django.utils.timezone as tz

        if tz.localdate() < PROGRAM_START:
            pytest.skip("program hasn't started in wall-clock time")

        today = tz.localdate()
        make_daily_log(today, deep_work_minutes=0)
        make_today_selection(today, title="t1", minutes_spent=60, position=1)
        make_today_selection(today, title="t2", minutes_spent=30, position=2)

        resp = auth_client.get("/api/today/")
        assert resp.status_code == 200
        assert resp.data["status"] == "active"
        assert "blocks" not in resp.data
        assert [s["title"] for s in resp.data["today_selections"]] == ["t1", "t2"]
        assert resp.data["deep_work_total"] == 90


class TestDailyLogComputedTotal:
    def test_daily_logs_endpoint_annotates_deep_work_total(self, auth_client):
        d = datetime.date(2026, 9, 8)
        make_daily_log(d, deep_work_minutes=0)
        make_today_selection(d, title="x", minutes_spent=25, position=1)
        make_today_selection(d, title="y", minutes_spent=None, position=2)

        resp = auth_client.get(f"/api/daily-logs/?log_date__gte={d}&log_date__lte={d}")
        assert resp.status_code == 200
        assert resp.data["results"][0]["deep_work_total"] == 25

    def test_deep_work_total_is_zero_when_no_selections(self, auth_client):
        d = datetime.date(2026, 9, 9)
        make_daily_log(d, deep_work_minutes=120)
        resp = auth_client.get(f"/api/daily-logs/?log_date__gte={d}&log_date__lte={d}")
        assert resp.data["results"][0]["deep_work_total"] == 0
