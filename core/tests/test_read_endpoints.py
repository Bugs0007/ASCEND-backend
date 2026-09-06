import datetime

import pytest
from django.contrib.auth import get_user_model

from core.tests.factories import (
    make_application,
    make_content_post,
    make_daily_log,
    make_milestone,
    make_notion_task,
    make_reflection,
    make_skill,
    make_sleep_log,
    get_project,
)

pytestmark = pytest.mark.django_db

LIST_ENDPOINTS = [
    "/api/applications/",
    "/api/milestones/",
    "/api/sleep-logs/",
    "/api/daily-logs/",
    "/api/skills/",
    "/api/courses/",
    "/api/cert-domains/",
    "/api/content-posts/",
    "/api/reflections/",
    "/api/notion-tasks/",
]


class TestReadEndpointsRequireAuth:
    @pytest.mark.parametrize("path", LIST_ENDPOINTS)
    def test_unauthenticated_is_401(self, api_client, path):
        assert api_client.get(path).status_code == 401

    @pytest.mark.parametrize("path", LIST_ENDPOINTS)
    def test_machine_token_is_rejected(self, ingest_client, path):
        # These are human-token-only, unlike /api/today/ and /api/email-queue/.
        assert ingest_client.get(path).status_code in (401, 403)


class TestOwnerScoping:
    def test_applications_exclude_another_users_rows_include_null_owned(self, auth_client, user):
        other_user = get_user_model().objects.create_user(username="someone-else", password="x")
        mine = make_application(company="Mine Corp", role="Engineer", owner=user)
        make_application(company="Theirs Corp", role="Engineer", owner=other_user)
        shared = make_application(company="Shared Corp", role="Engineer", owner=None)

        resp = auth_client.get("/api/applications/")
        assert resp.status_code == 200
        companies = {row["company"] for row in resp.data["results"]}
        assert mine.company in companies
        assert shared.company in companies
        assert "Theirs Corp" not in companies

    def test_notion_tasks_exclude_another_users_rows(self, auth_client, user):
        other_user = get_user_model().objects.create_user(username="someone-else-2", password="x")
        make_notion_task("page-mine", title="Mine", owner=user)
        make_notion_task("page-theirs", title="Theirs", owner=other_user)

        resp = auth_client.get("/api/notion-tasks/")
        titles = {row["title"] for row in resp.data["results"]}
        assert "Mine" in titles
        assert "Theirs" not in titles


class TestApplicationFilters:
    def test_filter_by_stage(self, auth_client):
        make_application(company="A Co", role="R1", stage="applied", applied_on=datetime.date(2026, 9, 10), last_update=datetime.date(2026, 9, 10))
        make_application(company="B Co", role="R2", stage="offer", applied_on=datetime.date(2026, 9, 10), last_update=datetime.date(2026, 9, 10))

        resp = auth_client.get("/api/applications/?stage=offer")
        assert resp.status_code == 200
        companies = [row["company"] for row in resp.data["results"]]
        assert companies == ["B Co"]

    def test_filter_by_source(self, auth_client):
        make_application(company="C Co", role="R3", source="referral", applied_on=datetime.date(2026, 9, 10), last_update=datetime.date(2026, 9, 10))
        make_application(company="D Co", role="R4", source="portal", applied_on=datetime.date(2026, 9, 10), last_update=datetime.date(2026, 9, 10))

        resp = auth_client.get("/api/applications/?source=referral")
        companies = [row["company"] for row in resp.data["results"]]
        assert companies == ["C Co"]


class TestMilestoneFilters:
    def test_filter_by_status(self, auth_client):
        make_milestone(title="Todo one", status="todo")
        make_milestone(title="Done one", status="done", evidence_url="https://example.com/e")

        resp = auth_client.get("/api/milestones/?status=done")
        titles = [row["title"] for row in resp.data["results"]]
        assert titles == ["Done one"]

    def test_filter_by_project_code(self, auth_client):
        project_a = get_project("A")
        project_b = get_project("B")
        make_milestone(title="On A", project=project_a)
        make_milestone(title="On B", project=project_b)

        # Project A already has seeded milestones (0002_seed_program), so
        # this only checks "On A" is included, "On B" is excluded, and every
        # returned row is genuinely under project A — not an exact list.
        resp = auth_client.get("/api/milestones/?project=A")
        titles = [row["title"] for row in resp.data["results"]]
        assert "On A" in titles
        assert "On B" not in titles
        assert all(row["project"] == "A" for row in resp.data["results"])


class TestDateRangeFilters:
    def test_daily_logs_date_range(self, auth_client):
        make_daily_log(datetime.date(2026, 9, 1))
        make_daily_log(datetime.date(2026, 9, 10))
        make_daily_log(datetime.date(2026, 9, 20))

        resp = auth_client.get("/api/daily-logs/?log_date__gte=2026-09-05&log_date__lte=2026-09-15")
        dates = [row["log_date"] for row in resp.data["results"]]
        assert dates == ["2026-09-10"]

    def test_sleep_logs_date_range(self, auth_client):
        make_sleep_log(datetime.date(2026, 9, 1))
        make_sleep_log(datetime.date(2026, 9, 12))

        resp = auth_client.get("/api/sleep-logs/?log_date__gte=2026-09-10")
        dates = [row["log_date"] for row in resp.data["results"]]
        assert dates == ["2026-09-12"]

    def test_reflections_date_range(self, auth_client):
        make_reflection(datetime.date(2026, 9, 1))
        make_reflection(datetime.date(2026, 9, 12))

        resp = auth_client.get("/api/reflections/?log_date__gte=2026-09-10")
        dates = [row["log_date"] for row in resp.data["results"]]
        assert dates == ["2026-09-12"]


class TestOrdering:
    def test_content_posts_default_newest_first(self, auth_client):
        make_content_post(title="Older", posted_on=datetime.date(2026, 9, 1))
        make_content_post(title="Newer", posted_on=datetime.date(2026, 9, 20))

        resp = auth_client.get("/api/content-posts/")
        titles = [row["title"] for row in resp.data["results"]]
        assert titles == ["Newer", "Older"]

    def test_applications_orderable_by_company(self, auth_client):
        make_application(company="Zeta", role="R", applied_on=datetime.date(2026, 9, 1), last_update=datetime.date(2026, 9, 1))
        make_application(company="Alpha", role="R", applied_on=datetime.date(2026, 9, 1), last_update=datetime.date(2026, 9, 1))

        resp = auth_client.get("/api/applications/?ordering=company")
        companies = [row["company"] for row in resp.data["results"]]
        assert companies == ["Alpha", "Zeta"]


class TestSkillsAndCourses:
    def test_skills_list(self, auth_client):
        make_skill(name="A brand new skill")
        resp = auth_client.get("/api/skills/")
        names = [row["name"] for row in resp.data["results"]]
        assert "A brand new skill" in names

    def test_courses_list_includes_seeded_courses(self, auth_client):
        resp = auth_client.get("/api/courses/")
        assert resp.status_code == 200
        assert resp.data["count"] >= 1

    def test_cert_domains_list_includes_seeded_domains(self, auth_client):
        resp = auth_client.get("/api/cert-domains/")
        assert resp.status_code == 200
        assert resp.data["count"] >= 1
