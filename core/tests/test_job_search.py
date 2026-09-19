"""
Job-applications quick-add (POST /api/applications/, PATCH heard_back),
the /api/today/ application counts, LinkedIn snapshots
(GET/POST /api/linkedin-snapshots/), and the 0010 seed migration.
"""
import datetime
import importlib

import pytest
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.constants import CHANNEL_DEFAULT_SOURCE
from core.models import Application, LinkedInSnapshot
from core.tests.factories import make_application

pytestmark = pytest.mark.django_db

seed = importlib.import_module("core.migrations.0010_seed_job_search_2026_09_13")


class TestApplicationQuickAdd:
    def test_creates_with_today_derived_source_and_owner(self, auth_client, user):
        resp = auth_client.post(
            "/api/applications/",
            {"company": "  Rehlat ", "role": "Python Developer", "channel": "linkedin_easy_apply"},
        )
        assert resp.status_code == 201
        today = timezone.localdate()
        assert resp.data["company"] == "Rehlat"  # trimmed
        assert resp.data["channel"] == "linkedin_easy_apply"
        assert resp.data["source"] == "portal"
        assert resp.data["stage"] == "applied"
        assert resp.data["heard_back"] == "pending"
        assert resp.data["applied_on"] == today.isoformat()
        assert resp.data["last_update"] == today.isoformat()
        assert Application.objects.get(pk=resp.data["id"]).owner == user

    @pytest.mark.parametrize("channel, source", sorted(CHANNEL_DEFAULT_SOURCE.items()))
    def test_every_channel_maps_to_a_real_source(self, auth_client, channel, source):
        assert source in Application.Source.values
        resp = auth_client.post(
            "/api/applications/", {"company": f"Co {channel}", "role": "Dev", "channel": channel}
        )
        assert resp.status_code == 201
        assert resp.data["source"] == source

    def test_mapping_covers_every_channel_choice(self):
        assert set(CHANNEL_DEFAULT_SOURCE) == set(Application.Channel.values)

    def test_duplicate_company_role_is_400_case_insensitive(self, auth_client):
        make_application(company="Delaplex", role="Backend Engineer")
        resp = auth_client.post(
            "/api/applications/",
            {"company": "delaplex", "role": "backend engineer", "channel": "naukri"},
        )
        assert resp.status_code == 400
        assert "Already logged" in resp.data["detail"]
        assert Application.objects.filter(company__iexact="delaplex").count() == 1

    def test_explicit_past_date_is_used(self, auth_client):
        resp = auth_client.post(
            "/api/applications/",
            {"company": "Infosys", "role": "Technology Lead", "channel": "careers_page", "applied_on": "2026-09-12"},
        )
        assert resp.status_code == 201
        assert resp.data["applied_on"] == "2026-09-12"
        assert resp.data["source"] == "direct"

    def test_future_date_is_400(self, auth_client):
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        resp = auth_client.post(
            "/api/applications/",
            {"company": "X", "role": "Y", "channel": "other", "applied_on": tomorrow.isoformat()},
        )
        assert resp.status_code == 400
        assert "applied_on" in resp.data

    @pytest.mark.parametrize(
        "body",
        [
            {"company": "X", "role": "Y"},  # channel required
            {"company": "X", "role": "Y", "channel": "monster"},  # unknown channel
            {"company": "", "role": "Y", "channel": "other"},  # blank company
            {"company": "X", "role": "Y", "channel": "other", "stage": "offer"},  # unknown field
        ],
    )
    def test_bad_bodies_are_400(self, auth_client, body):
        assert auth_client.post("/api/applications/", body).status_code == 400
        assert Application.objects.count() == 0

    def test_requires_human_token(self, api_client, ingest_client):
        body = {"company": "X", "role": "Y", "channel": "other"}
        assert api_client.post("/api/applications/", body).status_code == 401
        assert ingest_client.post("/api/applications/", body).status_code in (401, 403)


class TestApplicationHeardBack:
    def test_patch_sets_flag_and_leaves_pipeline_fields(self, auth_client):
        app = make_application(company="Nineleaps", role="Python Backend Engineer")
        before = (app.stage, app.last_update)
        resp = auth_client.patch(f"/api/applications/{app.id}/", {"heard_back": "yes"})
        assert resp.status_code == 200
        assert resp.data["heard_back"] == "yes"
        app.refresh_from_db()
        assert app.heard_back == "yes"
        assert (app.stage, app.last_update) == before

    def test_patch_bad_value_or_extra_field_is_400(self, auth_client):
        app = make_application()
        assert auth_client.patch(f"/api/applications/{app.id}/", {"heard_back": "maybe"}).status_code == 400
        assert auth_client.patch(
            f"/api/applications/{app.id}/", {"heard_back": "no", "stage": "offer"}
        ).status_code == 400

    def test_patch_another_users_row_is_404(self, auth_client):
        other = get_user_model().objects.create_user(username="other-hb", password="x")
        app = make_application(owner=other)
        assert auth_client.patch(f"/api/applications/{app.id}/", {"heard_back": "yes"}).status_code == 404


class TestApplicationListFilters:
    def test_filter_by_applied_on_and_channel(self, auth_client):
        make_application(company="A", role="r", applied_on=datetime.date(2026, 9, 13), channel="cutshort")
        make_application(company="B", role="r", applied_on=datetime.date(2026, 9, 13), channel="naukri")
        make_application(company="C", role="r", applied_on=datetime.date(2026, 9, 12), channel="cutshort")

        on_day = auth_client.get("/api/applications/?applied_on=2026-09-13")
        assert {r["company"] for r in on_day.data["results"]} == {"A", "B"}

        cutshort = auth_client.get("/api/applications/?channel=cutshort")
        assert {r["company"] for r in cutshort.data["results"]} == {"A", "C"}

    def test_ordering_newest_applied_then_newest_added(self, auth_client):
        first = make_application(company="First", role="r", applied_on=datetime.date(2026, 9, 13))
        second = make_application(company="Second", role="r", applied_on=datetime.date(2026, 9, 13))
        make_application(company="Older", role="r", applied_on=datetime.date(2026, 9, 1))
        resp = auth_client.get("/api/applications/?ordering=-applied_on,-id")
        assert [r["company"] for r in resp.data["results"]] == [second.company, first.company, "Older"]


class TestTodayApplicationCounts:
    def test_today_and_total(self, auth_client):
        today = timezone.localdate()
        make_application(company="T1", role="r", applied_on=today, last_update=today)
        make_application(company="T2", role="r", applied_on=today, last_update=today)
        make_application(company="Old", role="r", applied_on=today - datetime.timedelta(days=3))

        resp = auth_client.get("/api/today/")
        assert resp.status_code == 200
        if resp.data["status"] != "active":
            pytest.skip("program hasn't started in wall-clock time")
        assert resp.data["applications_today"] == 2
        assert resp.data["applications_total"] == 3

    def test_quick_add_moves_the_counts(self, auth_client):
        resp = auth_client.get("/api/today/")
        if resp.data["status"] != "active":
            pytest.skip("program hasn't started in wall-clock time")
        assert (resp.data["applications_today"], resp.data["applications_total"]) == (0, 0)

        auth_client.post("/api/applications/", {"company": "X", "role": "Y", "channel": "other"})
        resp = auth_client.get("/api/today/")
        assert (resp.data["applications_today"], resp.data["applications_total"]) == (1, 1)


class TestLinkedInSnapshots:
    BODY = {"post_impressions": 670, "post_likes": 30, "connections": 492, "note": "Café Cursor meetup post"}

    def test_post_creates_for_today_by_default(self, auth_client, user):
        resp = auth_client.post("/api/linkedin-snapshots/", self.BODY)
        assert resp.status_code == 201
        assert resp.data["log_date"] == timezone.localdate().isoformat()
        assert resp.data["connections"] == 492
        assert resp.data["note"] == "Café Cursor meetup post"
        assert LinkedInSnapshot.objects.get(pk=resp.data["id"]).owner == user

    def test_reposting_a_date_updates_that_row(self, auth_client):
        first = auth_client.post("/api/linkedin-snapshots/", {**self.BODY, "log_date": "2026-09-12"})
        assert first.status_code == 201
        second = auth_client.post(
            "/api/linkedin-snapshots/",
            {"log_date": "2026-09-12", "post_impressions": 900, "post_likes": 41, "connections": 495},
        )
        assert second.status_code == 200
        assert second.data["id"] == first.data["id"]
        row = LinkedInSnapshot.objects.get(log_date=datetime.date(2026, 9, 12))
        assert (row.post_impressions, row.post_likes, row.connections) == (900, 41, 495)
        assert row.note == "Café Cursor meetup post"  # omitted on update -> kept
        assert LinkedInSnapshot.objects.count() == 1

    @pytest.mark.parametrize(
        "patch",
        [
            {"post_impressions": -1},
            {"post_likes": "lots"},  # optional is not the same as unvalidated
            {"connections": None},
            {"note": "x" * 201},
            {"likes": 3},  # unknown field
        ],
    )
    def test_bad_bodies_are_400(self, auth_client, patch):
        body = {**self.BODY, **patch}
        assert auth_client.post("/api/linkedin-snapshots/", body).status_code == 400

    def test_missing_number_is_400(self, auth_client):
        body = {k: v for k, v in self.BODY.items() if k != "connections"}
        assert auth_client.post("/api/linkedin-snapshots/", body).status_code == 400

    def test_future_date_is_400(self, auth_client):
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        resp = auth_client.post("/api/linkedin-snapshots/", {**self.BODY, "log_date": tomorrow.isoformat()})
        assert resp.status_code == 400

    def test_list_orderable_chronologically(self, auth_client):
        for day, conns in [(13, 492), (11, 480), (12, 488)]:
            LinkedInSnapshot.objects.create(
                log_date=datetime.date(2026, 9, day), post_impressions=1, post_likes=0, connections=conns
            )
        newest_first = auth_client.get("/api/linkedin-snapshots/")
        assert [r["connections"] for r in newest_first.data["results"]] == [492, 488, 480]
        chrono = auth_client.get("/api/linkedin-snapshots/?ordering=log_date")
        assert [r["log_date"] for r in chrono.data["results"]] == ["2026-09-11", "2026-09-12", "2026-09-13"]

    def test_unauthenticated_is_401(self, api_client):
        assert api_client.get("/api/linkedin-snapshots/").status_code == 401

    def test_wrong_bearer_token_is_401(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer not-the-ingest-token")
        assert api_client.get("/api/linkedin-snapshots/").status_code == 401
        assert api_client.post("/api/linkedin-snapshots/", self.BODY).status_code == 401
        assert LinkedInSnapshot.objects.count() == 0

    # --- bearer INGEST_TOKEN (machine caller) ---
    # auth_client and ingest_client share one function-scoped api_client, so
    # a test must request only one of them or the last fixture's header wins.

    def test_bearer_get_lists_snapshots(self, ingest_client):
        LinkedInSnapshot.objects.create(
            log_date=datetime.date(2026, 9, 11), post_impressions=1, post_likes=0, connections=480
        )
        resp = ingest_client.get("/api/linkedin-snapshots/")
        assert resp.status_code == 200
        assert [r["connections"] for r in resp.data["results"]] == [480]

    def test_bearer_post_creates_snapshot(self, ingest_client, user):
        resp = ingest_client.post("/api/linkedin-snapshots/", {**self.BODY, "log_date": "2026-09-14"})
        assert resp.status_code == 201
        row = LinkedInSnapshot.objects.get(pk=resp.data["id"])
        assert row.log_date == datetime.date(2026, 9, 14)
        assert (row.post_impressions, row.post_likes, row.connections) == (670, 30, 492)
        assert row.note == "Café Cursor meetup post"
        assert row.owner == user  # attributed to the ingest owner, not left ownerless

    def test_bearer_second_post_for_same_log_date_updates_it(self, ingest_client):
        first = ingest_client.post("/api/linkedin-snapshots/", {**self.BODY, "log_date": "2026-09-14"})
        second = ingest_client.post(
            "/api/linkedin-snapshots/",
            {"log_date": "2026-09-14", "post_impressions": 900, "post_likes": 41, "connections": 495},
        )
        assert (first.status_code, second.status_code) == (201, 200)
        assert second.data["id"] == first.data["id"]
        rows = LinkedInSnapshot.objects.filter(log_date=datetime.date(2026, 9, 14))
        assert rows.count() == 1
        row = rows.get()
        assert (row.post_impressions, row.post_likes, row.connections) == (900, 41, 495)

    # --- post_impressions / post_likes are optional ---

    @pytest.mark.parametrize(
        "omit",
        [("post_impressions",), ("post_likes",), ("post_impressions", "post_likes")],
        ids=["no-impressions", "no-likes", "no-post-at-all"],
    )
    def test_impressions_and_likes_are_optional_on_a_new_day(self, ingest_client, omit):
        body = {k: v for k, v in self.BODY.items() if k not in omit}
        resp = ingest_client.post("/api/linkedin-snapshots/", body)
        assert resp.status_code == 201  # not a 400
        row = LinkedInSnapshot.objects.get(pk=resp.data["id"])
        expected = {"post_impressions": 670, "post_likes": 30}
        for key in ("post_impressions", "post_likes"):
            assert getattr(row, key) == (0 if key in omit else expected[key])
        assert row.connections == 492

    def test_omitted_counts_keep_the_stored_values_on_update(self, ingest_client):
        ingest_client.post("/api/linkedin-snapshots/", {**self.BODY, "log_date": "2026-09-14"})
        resp = ingest_client.post("/api/linkedin-snapshots/", {"log_date": "2026-09-14", "connections": 495})
        assert resp.status_code == 200
        row = LinkedInSnapshot.objects.get(log_date=datetime.date(2026, 9, 14))
        assert (row.post_impressions, row.post_likes, row.connections) == (670, 30, 495)

    def test_null_counts_are_treated_as_omitted(self, ingest_client):
        nulls = {"post_impressions": None, "post_likes": None}
        new_day = ingest_client.post(
            "/api/linkedin-snapshots/", {"log_date": "2026-09-15", "connections": 500, **nulls}
        )
        assert new_day.status_code == 201
        assert (new_day.data["post_impressions"], new_day.data["post_likes"]) == (0, 0)

        ingest_client.post("/api/linkedin-snapshots/", {**self.BODY, "log_date": "2026-09-14"})
        existing_day = ingest_client.post(
            "/api/linkedin-snapshots/", {"log_date": "2026-09-14", "connections": 495, **nulls}
        )
        assert existing_day.status_code == 200
        assert (existing_day.data["post_impressions"], existing_day.data["post_likes"]) == (670, 30)

    def test_connections_stays_required_for_bearer_posts(self, ingest_client):
        resp = ingest_client.post("/api/linkedin-snapshots/", {"post_impressions": 5, "post_likes": 1})
        assert resp.status_code == 400
        assert "connections" in resp.data


class TestIngestAcceptsNewApplicationFields:
    def test_channel_and_heard_back_upsert(self, ingest_client):
        row = {
            "company": "Acme", "role": "Dev", "source": "referral", "applied_on": "2026-09-13",
            "last_update": "2026-09-13", "channel": "careers_page", "heard_back": "no",
        }
        resp = ingest_client.post("/api/ingest/", {"applications": [row]}, format="json")
        assert resp.status_code == 200
        app = Application.objects.get(company="Acme", role="Dev")
        assert (app.channel, app.heard_back, app.source) == ("careers_page", "no", "referral")


class TestSeedMigration:
    """Runs 0010's RunPython function against the live app registry — the
    session fixture in conftest.py removed what the real migration wrote."""

    def test_seeds_the_five_applications_and_snapshot(self, user):
        seed.seed_job_search(django_apps, None)

        apps_on_day = Application.objects.filter(applied_on=seed.SEED_DATE)
        assert apps_on_day.count() == 5
        got = {(a.company, a.role, a.channel, a.source) for a in apps_on_day}
        assert got == {
            ("Rehlat", "Python Developer", "linkedin_easy_apply", "portal"),
            ("SRS Business Solutions India Pvt Ltd", "Python Developer", "linkedin_easy_apply", "portal"),
            ("Delaplex", "Backend Engineer", "linkedin_easy_apply", "portal"),
            ("Infosys", "Technology Lead", "careers_page", "direct"),
            ("Nineleaps", "Python Backend Engineer", "cutshort", "portal"),
        }
        for a in apps_on_day:
            assert (a.stage, a.heard_back, a.last_update, a.owner) == ("applied", "pending", seed.SEED_DATE, user)
            assert a.source == CHANNEL_DEFAULT_SOURCE[a.channel]

        snap = LinkedInSnapshot.objects.get(log_date=seed.SEED_DATE)
        assert (snap.post_impressions, snap.post_likes, snap.connections) == (670, 30, 492)
        assert snap.note == "Café Cursor meetup post"
        assert snap.owner == user

    def test_is_idempotent_and_never_overwrites(self, user):
        make_application(company="rehlat", role="python developer", stage="screen", channel="")
        LinkedInSnapshot.objects.create(
            log_date=seed.SEED_DATE, post_impressions=700, post_likes=31, connections=493
        )

        seed.seed_job_search(django_apps, None)
        seed.seed_job_search(django_apps, None)

        assert Application.objects.filter(company__iexact="rehlat").count() == 1
        existing = Application.objects.get(company="rehlat")
        assert existing.stage == "screen"  # untouched
        assert existing.channel == "linkedin_easy_apply"  # blank channel filled
        assert Application.objects.count() == 5
        assert LinkedInSnapshot.objects.get(log_date=seed.SEED_DATE).post_impressions == 700

    def test_owner_null_without_any_user(self):
        seed.seed_job_search(django_apps, None)
        assert Application.objects.filter(owner__isnull=True).count() == 5

    def test_seeded_rows_show_on_the_dashboard_endpoints(self, auth_client):
        seed.seed_job_search(django_apps, None)
        listed = auth_client.get("/api/applications/?applied_on=2026-09-13")
        assert listed.data["count"] == 5
        snaps = auth_client.get("/api/linkedin-snapshots/?ordering=log_date")
        assert snaps.data["results"][0]["connections"] == 492
