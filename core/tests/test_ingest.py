import datetime

import pytest
from rest_framework.exceptions import ValidationError

from core.ingest import resolve_sleep_log_date, run_ingest, run_sleep_event_ingest
from core.models import (
    Application,
    Course,
    DailyLog,
    EmailEvent,
    Milestone,
    PracticeTest,
    Skill,
    SleepLog,
)
from core.tests.factories import make_application

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(user):
    return user


class TestUnknownFieldRejection:
    def test_unknown_top_level_resource_is_400(self, owner):
        with pytest.raises(ValidationError):
            run_ingest({"not_a_real_resource": [{"x": 1}]}, owner)

    def test_unknown_field_within_a_row_is_400(self, owner):
        with pytest.raises(ValidationError):
            run_ingest(
                {"daily_logs": [{"log_date": "2026-09-07", "energy": 3, "made_up_field": 1}]},
                owner,
            )

    def test_non_list_resource_value_is_400(self, owner):
        with pytest.raises(ValidationError):
            run_ingest({"daily_logs": {"log_date": "2026-09-07"}}, owner)


class TestIngestIdempotency:
    def test_identical_daily_log_payload_twice_produces_one_row(self, owner):
        payload = {
            "daily_logs": [
                {"log_date": "2026-09-07", "deep_work_minutes": 120, "energy": 4, "gym": True}
            ]
        }
        summary1 = run_ingest(payload, owner)
        assert summary1["daily_logs"] == {"created": 1, "updated": 0}

        summary2 = run_ingest(payload, owner)
        assert summary2["daily_logs"] == {"created": 0, "updated": 1}

        assert DailyLog.objects.filter(log_date=datetime.date(2026, 9, 7)).count() == 1

    def test_second_post_updates_fields(self, owner):
        run_ingest({"daily_logs": [{"log_date": "2026-09-07", "energy": 2}]}, owner)
        run_ingest(
            {"daily_logs": [{"log_date": "2026-09-07", "energy": 5, "deep_work_minutes": 200}]},
            owner,
        )
        log = DailyLog.objects.get(log_date=datetime.date(2026, 9, 7))
        assert log.energy == 5
        assert log.deep_work_minutes == 200

    def test_application_idempotent_on_company_role(self, owner):
        payload = {
            "applications": [
                {
                    "company": "Acme", "role": "Backend Engineer", "source": "referral",
                    "applied_on": "2026-09-10", "last_update": "2026-09-10",
                }
            ]
        }
        run_ingest(payload, owner)
        run_ingest(payload, owner)
        assert Application.objects.filter(company="Acme", role="Backend Engineer").count() == 1

    def test_practice_test_idempotent_on_cert_code_and_date(self, owner):
        payload = {
            "practice_tests": [{"cert_code": "AI-103", "taken_on": "2026-09-15", "score": 650}]
        }
        run_ingest(payload, owner)
        run_ingest(payload, owner)
        assert PracticeTest.objects.filter(cert_code="AI-103", taken_on=datetime.date(2026, 9, 15)).count() == 1

    def test_sleep_log_idempotent_on_log_date(self, owner):
        payload = {"sleep_logs": [{"log_date": "2026-09-07", "source": "manual"}]}
        run_ingest(payload, owner)
        run_ingest(payload, owner)
        assert SleepLog.objects.filter(log_date=datetime.date(2026, 9, 7)).count() == 1


class TestCourseAndSkillIngest:
    def test_course_upsert_on_name_updates_the_seeded_row(self, owner):
        # "Claude 101 and Claude Code" is seeded by 0002_seed_program, so the
        # first POST updates it rather than creating — progress_pct moves off
        # its seed value of 0.
        payload = {"courses": [{"name": "Claude 101 and Claude Code", "progress_pct": 100}]}
        assert run_ingest(payload, owner)["courses"] == {"created": 0, "updated": 1}
        assert run_ingest(payload, owner)["courses"] == {"created": 0, "updated": 1}

        assert Course.objects.filter(name="Claude 101 and Claude Code").count() == 1
        assert Course.objects.get(name="Claude 101 and Claude Code").progress_pct == 100

    def test_course_partial_update_leaves_other_fields_alone(self, owner):
        run_ingest({"courses": [{"name": "Claude 101 and Claude Code", "active": False}]}, owner)
        run_ingest({"courses": [{"name": "Claude 101 and Claude Code", "progress_pct": 30}]}, owner)
        course = Course.objects.get(name="Claude 101 and Claude Code")
        assert course.progress_pct == 30
        assert course.active is False

    def test_skill_upsert_on_name(self, owner):
        payload = {"skills": [{"name": "Python", "level": 45}]}
        run_ingest(payload, owner)
        run_ingest(payload, owner)
        assert Skill.objects.filter(name="Python").count() == 1
        assert Skill.objects.get(name="Python").level == 45

    def test_unseen_course_name_creates_a_new_row(self, owner):
        summary = run_ingest({"courses": [{"name": "Brand New Course", "progress_pct": 10}]}, owner)
        assert summary["courses"] == {"created": 1, "updated": 0}
        assert Course.objects.get(name="Brand New Course").owner == owner

    def test_unseen_skill_name_creates_a_new_row(self, owner):
        summary = run_ingest({"skills": [{"name": "Rust", "level": 5}]}, owner)
        assert summary["skills"] == {"created": 1, "updated": 0}
        assert Skill.objects.get(name="Rust").owner == owner

    def test_course_unknown_field_is_400(self, owner):
        with pytest.raises(ValidationError):
            run_ingest(
                {"courses": [{"name": "Claude 101 and Claude Code", "provider": "Anthropic"}]},
                owner,
            )

    def test_skill_unknown_field_is_400(self, owner):
        with pytest.raises(ValidationError):
            run_ingest({"skills": [{"name": "Python", "mastery": 3}]}, owner)

    def test_course_progress_pct_over_100_is_400(self, owner):
        with pytest.raises(ValidationError):
            run_ingest(
                {"courses": [{"name": "Claude 101 and Claude Code", "progress_pct": 150}]},
                owner,
            )


class TestMilestoneEvidenceGateViaIngest:
    def test_marking_done_without_evidence_url_raises_400(self, owner):
        with pytest.raises(ValidationError):
            run_ingest(
                {
                    "milestones": [
                        {"title": "Golden dataset", "project_code": "A", "status": "done"}
                    ]
                },
                owner,
            )

    def test_marking_done_with_evidence_url_succeeds(self, owner):
        run_ingest(
            {
                "milestones": [
                    {
                        "title": "Golden dataset", "project_code": "A", "status": "done",
                        "evidence_url": "https://github.com/x/y",
                    }
                ]
            },
            owner,
        )
        m = Milestone.objects.get(title="Golden dataset", project__code="A")
        assert m.status == "done"

    def test_omitting_project_code_on_update_does_not_detach_project(self, owner):
        run_ingest(
            {"milestones": [{"title": "Golden dataset", "project_code": "A", "status": "doing"}]},
            owner,
        )
        run_ingest({"milestones": [{"title": "Golden dataset", "status": "doing"}]}, owner)
        m = Milestone.objects.get(title="Golden dataset")
        assert m.project is not None
        assert m.project.code == "A"


IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


class TestSleepDayAttribution:
    def test_bed_after_midnight_attributes_to_previous_day(self):
        # 00:47 IST (the app's configured TIME_ZONE) on Sept 5 -> Sept 4's SleepLog.
        at = datetime.datetime(2026, 9, 5, 0, 47, tzinfo=IST)
        log_date = resolve_sleep_log_date(at)
        assert log_date == datetime.date(2026, 9, 4)

    def test_bed_before_midnight_attributes_to_same_day(self):
        # 23:40 IST on Sept 4 -> stays Sept 4.
        at = datetime.datetime(2026, 9, 4, 23, 40, tzinfo=IST)
        log_date = resolve_sleep_log_date(at)
        assert log_date == datetime.date(2026, 9, 4)

    def test_morning_wake_matches_the_bed_events_log_date(self):
        bed_at = datetime.datetime(2026, 9, 5, 0, 47, tzinfo=IST)
        wake_at = datetime.datetime(2026, 9, 5, 7, 0, tzinfo=IST)
        assert resolve_sleep_log_date(bed_at) == resolve_sleep_log_date(wake_at) == datetime.date(2026, 9, 4)

    def test_full_bed_then_wake_event_flow(self, owner):
        bed_at = datetime.datetime(2026, 9, 5, 0, 47, tzinfo=IST)
        wake_at = datetime.datetime(2026, 9, 5, 7, 0, tzinfo=IST)
        run_sleep_event_ingest("bed", bed_at, owner)
        obj, created = run_sleep_event_ingest("wake", wake_at, owner)
        assert not created  # same row as the bed event
        assert obj.log_date == datetime.date(2026, 9, 4)
        assert obj.source == SleepLog.Source.SHORTCUT
        assert float(obj.hours) == pytest.approx(6.22, abs=0.01)


class TestEmailAutoMatch:
    def test_auto_matches_by_company_domain(self, owner):
        make_application("Acme", "Backend Engineer", company_domain="acme.com")
        summary = run_ingest(
            {
                "email_events": [
                    {
                        "gmail_message_id": "msg-1",
                        "received_at": "2026-09-15T09:00:00Z",
                        "from_address": "recruiting@acme.com",
                        "subject": "Update",
                    }
                ]
            },
            owner,
        )
        assert summary["email_events"] == {"created": 1, "updated": 0}
        event = EmailEvent.objects.get(gmail_message_id="msg-1")
        assert event.matched is True
        assert event.application.company == "Acme"

    def test_unmatched_stays_in_review_queue(self, owner):
        run_ingest(
            {
                "email_events": [
                    {
                        "gmail_message_id": "msg-2",
                        "received_at": "2026-09-15T09:00:00Z",
                        "from_address": "someone@unknown-domain.com",
                        "subject": "Mystery",
                    }
                ]
            },
            owner,
        )
        event = EmailEvent.objects.get(gmail_message_id="msg-2")
        assert event.matched is False
