import datetime

import pytest

from core.constants import PROGRAM_START

pytestmark = pytest.mark.django_db

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


class TestHealth:
    def test_health_requires_no_auth(self, api_client):
        resp = api_client.get("/api/health/")
        assert resp.status_code == 200
        assert resp.data["status"] == "ok"


class TestAuthSeparation:
    def test_ingest_rejects_human_token(self, auth_client):
        resp = auth_client.post("/api/ingest/", {"daily_logs": []}, format="json")
        assert resp.status_code in (401, 403)

    def test_ingest_accepts_machine_token(self, ingest_client):
        resp = ingest_client.post("/api/ingest/", {"daily_logs": []}, format="json")
        assert resp.status_code == 200

    def test_ingest_rejects_wrong_bearer_token(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer wrong-token-entirely")
        resp = api_client.post("/api/ingest/", {"daily_logs": []}, format="json")
        assert resp.status_code == 401

    def test_ingest_with_no_superuser_yet_is_401(self, api_client, settings):
        # Correct token, but no superuser exists to attribute writes to.
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {settings.INGEST_TOKEN}")
        resp = api_client.post("/api/ingest/", {"daily_logs": []}, format="json")
        assert resp.status_code == 401

    def test_analytics_rejects_ingest_token(self, ingest_client):
        resp = ingest_client.get("/api/analytics/funnel/")
        assert resp.status_code in (401, 403)

    def test_analytics_accepts_human_token(self, auth_client):
        resp = auth_client.get("/api/analytics/funnel/")
        assert resp.status_code == 200

    def test_today_accepts_either_token(self, auth_client, ingest_client):
        assert auth_client.get("/api/today/").status_code == 200
        assert ingest_client.get("/api/today/").status_code == 200

    def test_email_queue_accepts_either_token(self, auth_client, ingest_client):
        assert auth_client.get("/api/email-queue/").status_code == 200
        assert ingest_client.get("/api/email-queue/").status_code == 200

    def test_unauthenticated_analytics_is_401(self, api_client):
        resp = api_client.get("/api/analytics/funnel/")
        assert resp.status_code == 401


class TestTodayPreStart:
    def test_pre_start_shape(self, auth_client, settings):
        # PROGRAM_START is 2026-09-07; freeze "today" earlier via a fake
        # override isn't wired up (no freezegun dependency), so this test
        # only runs meaningfully before the program start in real time.
        # Guard with a skip if the environment's clock has passed it.
        import django.utils.timezone as tz

        if tz.localdate() >= PROGRAM_START:
            pytest.skip("program has started in wall-clock time")
        resp = auth_client.get("/api/today/")
        assert resp.status_code == 200
        assert resp.data["status"] == "pre_start"
        assert resp.data["days_to_start"] > 0


class TestAllAnalyticsEndpointsRespond:
    ENDPOINTS = [
        "/api/analytics/rhythm/",
        "/api/analytics/correlations/",
        "/api/analytics/funnel/",
        "/api/analytics/losses/",
        "/api/analytics/burnup/",
        "/api/analytics/certtrend/",
        "/api/analytics/decay/",
        "/api/analytics/activity/",
        "/api/analytics/observations/",
    ]

    @pytest.mark.parametrize("path", ENDPOINTS)
    def test_each_endpoint_returns_200(self, auth_client, path):
        resp = auth_client.get(path)
        assert resp.status_code == 200


class TestBlockTapFlow:
    def test_start_then_complete(self, auth_client):
        start_resp = auth_client.post("/api/blocks/B1/start/")
        assert start_resp.status_code == 200
        assert start_resp.data["started_at"] is not None
        assert start_resp.data["completed"] is False

        complete_resp = auth_client.post("/api/blocks/B1/complete/")
        assert complete_resp.status_code == 200
        assert complete_resp.data["completed"] is True
        assert complete_resp.data["elapsed_minutes"] is not None

    def test_complete_without_start_is_400(self, auth_client):
        resp = auth_client.post("/api/blocks/B2/complete/")
        assert resp.status_code == 400

    def test_starting_twice_does_not_reset_started_at(self, auth_client):
        r1 = auth_client.post("/api/blocks/B3/start/")
        first_started_at = r1.data["started_at"]
        r2 = auth_client.post("/api/blocks/B3/start/")
        assert r2.data["started_at"] == first_started_at


class TestIngestEndToEnd:
    def test_ingest_summary_shape(self, ingest_client):
        resp = ingest_client.post(
            "/api/ingest/",
            {"daily_logs": [{"log_date": "2026-09-07", "energy": 4}]},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["daily_logs"] == {"created": 1, "updated": 0}

    def test_unknown_field_returns_400(self, ingest_client):
        resp = ingest_client.post(
            "/api/ingest/",
            {"daily_logs": [{"log_date": "2026-09-07", "energy": 4, "bogus": 1}]},
            format="json",
        )
        assert resp.status_code == 400

    def test_sleep_shortcut_endpoint(self, ingest_client):
        import datetime

        resp = ingest_client.post(
            "/api/ingest/sleep/",
            {"event": "bed", "at": "2026-09-05T00:47:00+05:30"},  # IST, before the noon cutoff
            format="json",
        )
        assert resp.status_code == 200
        # resp.data holds native Python objects (pre-render) — a date, not a string.
        assert resp.data["log_date"] == datetime.date(2026, 9, 4)


class TestEmailQueue:
    def test_lists_only_unmatched(self, auth_client):
        from core.tests.factories import make_email_event

        make_email_event("m1", subject="Unmatched one")
        resp = auth_client.get("/api/email-queue/")
        assert resp.status_code == 200
        assert resp.data["count"] == 1
        assert resp.data["results"][0]["gmail_message_id"] == "m1"


class TestCountdownPatch:
    def test_patch_updates_target_date_on_editable_countdown(self, auth_client):
        from core.tests.factories import get_countdown

        countdown = get_countdown("AI-103 exam")
        resp = auth_client.patch(
            f"/api/countdowns/{countdown.id}/", {"target_date": "2026-11-15"}, format="json"
        )
        assert resp.status_code == 200
        countdown.refresh_from_db()
        assert countdown.target_date.isoformat() == "2026-11-15"

    def test_patch_rejects_non_editable_countdown(self, auth_client):
        from core.tests.factories import get_countdown

        countdown = get_countdown("Program end")
        original = countdown.target_date
        resp = auth_client.patch(
            f"/api/countdowns/{countdown.id}/", {"target_date": "2026-01-01"}, format="json"
        )
        assert resp.status_code == 400
        countdown.refresh_from_db()
        assert countdown.target_date == original

    def test_patch_requires_auth(self, api_client):
        from core.tests.factories import get_countdown

        countdown = get_countdown("AI-103 exam")
        resp = api_client.patch(
            f"/api/countdowns/{countdown.id}/", {"target_date": "2026-11-15"}, format="json"
        )
        assert resp.status_code == 401


class TestBlockEntryUndo:
    def test_undo_clears_ended_at_and_elapsed_minutes_but_keeps_started_at(self, auth_client):
        auth_client.post("/api/blocks/B4/start/")
        complete_resp = auth_client.post("/api/blocks/B4/complete/")
        entry_id = complete_resp.data["id"]
        started_at = complete_resp.data["started_at"]
        assert complete_resp.data["completed"] is True
        assert complete_resp.data["elapsed_minutes"] is not None

        undo_resp = auth_client.patch(f"/api/block-entries/{entry_id}/", {}, format="json")
        assert undo_resp.status_code == 200
        assert undo_resp.data["completed"] is False
        assert undo_resp.data["ended_at"] is None
        assert undo_resp.data["elapsed_minutes"] is None
        assert undo_resp.data["started_at"] == started_at  # preserved — still "in progress"

    def test_undo_twice_is_a_safe_no_op(self, auth_client):
        auth_client.post("/api/blocks/B5/start/")
        complete_resp = auth_client.post("/api/blocks/B5/complete/")
        entry_id = complete_resp.data["id"]

        first = auth_client.patch(f"/api/block-entries/{entry_id}/", {}, format="json")
        second = auth_client.patch(f"/api/block-entries/{entry_id}/", {}, format="json")
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.data["completed"] is False

    def test_undo_rejects_unknown_field(self, auth_client):
        auth_client.post("/api/blocks/B1/start/")
        complete_resp = auth_client.post("/api/blocks/B1/complete/")
        entry_id = complete_resp.data["id"]
        resp = auth_client.patch(f"/api/block-entries/{entry_id}/", {"what": "sneaky"}, format="json")
        assert resp.status_code == 400

    def test_undo_requires_auth(self, api_client):
        resp = api_client.patch("/api/block-entries/1/", {}, format="json")
        assert resp.status_code == 401


class TestSleepLogPatch:
    """PATCH /api/sleep-logs/<id>/ — the fix control on TODAY's sleep panel.
    Edits the row it's shown by id; never re-derives the night."""

    def _rows(self):
        from core.tests.factories import make_sleep_log

        # The night whose panel log_date (Sep 8) sits one day behind the wall
        # clock of its own bed/wake events (both Sep 9) — the exact shape that
        # made a morning correction via /api/ingest/sleep/ mis-file onto Sep 7.
        target = make_sleep_log(
            datetime.date(2026, 9, 8),
            bed_at=datetime.datetime(2026, 9, 9, 0, 4, tzinfo=IST),
            wake_at=datetime.datetime(2026, 9, 9, 11, 57, tzinfo=IST),
            source="shortcut",
        )
        neighbour = make_sleep_log(
            datetime.date(2026, 9, 7),
            bed_at=datetime.datetime(2026, 9, 7, 23, 16, tzinfo=IST),
            wake_at=datetime.datetime(2026, 9, 8, 8, 15, tzinfo=IST),
            source="shortcut",
        )
        return target, neighbour

    def test_patch_edits_that_row_recomputes_hours_leaves_neighbour_alone(self, auth_client):
        target, neighbour = self._rows()
        neighbour_wake = neighbour.wake_at

        resp = auth_client.patch(
            f"/api/sleep-logs/{target.id}/",
            {"wake_at": "2026-09-09T08:15:00+05:30"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["log_date"] == "2026-09-08"

        target.refresh_from_db()
        neighbour.refresh_from_db()
        assert target.wake_at == datetime.datetime(2026, 9, 9, 8, 15, tzinfo=IST)
        assert float(target.hours) == pytest.approx(8.18, abs=0.02)
        assert neighbour.wake_at == neighbour_wake  # untouched

    def test_patch_rejects_wake_before_bed(self, auth_client):
        target, _ = self._rows()
        resp = auth_client.patch(
            f"/api/sleep-logs/{target.id}/",
            {"wake_at": "2026-09-08T08:15:00+05:30"},  # before the Sep 9 00:04 bed
            format="json",
        )
        assert resp.status_code == 400

    def test_patch_rejects_empty_body(self, auth_client):
        target, _ = self._rows()
        resp = auth_client.patch(f"/api/sleep-logs/{target.id}/", {}, format="json")
        assert resp.status_code == 400

    def test_patch_rejects_unknown_field(self, auth_client):
        target, _ = self._rows()
        resp = auth_client.patch(
            f"/api/sleep-logs/{target.id}/", {"source": "manual"}, format="json"
        )
        assert resp.status_code == 400

    def test_patch_requires_auth(self, api_client):
        resp = api_client.patch(
            "/api/sleep-logs/1/", {"wake_at": "2026-09-09T08:15:00+05:30"}, format="json"
        )
        assert resp.status_code == 401
