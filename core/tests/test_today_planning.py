import datetime

import pytest

from core.models import DailyRecommendation, TodaySelection
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
