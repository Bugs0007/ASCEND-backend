import datetime

import pytest
from django.core.exceptions import ValidationError

from core.models import Application, Milestone, Project, SleepLog
from core.tests.factories import make_block_entry, make_daily_log, make_milestone

pytestmark = pytest.mark.django_db

DAY0 = datetime.date(2026, 9, 7)


class TestMilestoneEvidenceGate:
    def test_done_without_evidence_url_raises(self):
        milestone = make_milestone("m1", status=Milestone.Status.TODO)
        milestone.status = Milestone.Status.DONE
        milestone.evidence_url = ""
        with pytest.raises(ValidationError):
            milestone.save()

    def test_done_with_evidence_url_succeeds(self):
        milestone = make_milestone("m2", status=Milestone.Status.TODO)
        milestone.status = Milestone.Status.DONE
        milestone.evidence_url = "https://example.com/proof"
        milestone.save()  # must not raise
        milestone.refresh_from_db()
        assert milestone.status == Milestone.Status.DONE

    def test_non_done_status_does_not_require_evidence(self):
        milestone = make_milestone("m3", status=Milestone.Status.DOING, evidence_url="")
        milestone.save()  # must not raise


class TestShippableQueues:
    def test_project_shippable_excludes_gated_project(self):
        project = Project.objects.get(code="A")  # seeded with a publish_gate
        assert project.publish_gate
        project.status = Project.Status.SHIPPED
        project.save()
        assert project not in Project.objects.shippable()

    def test_project_shippable_includes_ungated_shipped_project(self):
        project = Project.objects.get(code="B")  # seeded with no publish_gate
        project.status = Project.Status.SHIPPED
        project.save()
        assert project in Project.objects.shippable()

    def test_milestone_shippable_excludes_gated_project(self):
        project = Project.objects.get(code="A")
        milestone = make_milestone(
            "gated-done", project=project, status=Milestone.Status.DONE,
            evidence_url="https://example.com/1",
        )
        assert milestone not in Milestone.objects.shippable()

    def test_milestone_shippable_includes_ungated_project(self):
        project = Project.objects.get(code="B")
        milestone = make_milestone(
            "ungated-done", project=project, status=Milestone.Status.DONE,
            evidence_url="https://example.com/2",
        )
        assert milestone in Milestone.objects.shippable()


class TestSleepLogDerivation:
    def test_hours_derived_when_both_present(self):
        bed = datetime.datetime(2026, 9, 6, 23, 30, tzinfo=datetime.timezone.utc)
        wake = datetime.datetime(2026, 9, 7, 6, 30, tzinfo=datetime.timezone.utc)
        log = SleepLog.objects.create(log_date=DAY0, bed_at=bed, wake_at=wake)
        assert log.hours == pytest.approx(7.0)

    def test_hours_null_when_one_missing(self):
        bed = datetime.datetime(2026, 9, 6, 23, 30, tzinfo=datetime.timezone.utc)
        log = SleepLog.objects.create(log_date=DAY0, bed_at=bed, wake_at=None)
        assert log.hours is None

    def test_wake_before_bed_raises(self):
        bed = datetime.datetime(2026, 9, 7, 6, 30, tzinfo=datetime.timezone.utc)
        wake = datetime.datetime(2026, 9, 6, 23, 30, tzinfo=datetime.timezone.utc)
        with pytest.raises(ValidationError):
            SleepLog.objects.create(log_date=DAY0, bed_at=bed, wake_at=wake)


class TestBlockEntryDerivation:
    def test_elapsed_minutes_derived(self):
        log = make_daily_log(DAY0)
        entry = make_block_entry(
            log, block_code="B1",
            started_at=datetime.datetime(2026, 9, 7, 9, 0, tzinfo=datetime.timezone.utc),
            ended_at=datetime.datetime(2026, 9, 7, 10, 15, tzinfo=datetime.timezone.utc),
        )
        assert entry.elapsed_minutes == 75

    def test_duplicate_block_for_same_day_raises(self):
        log = make_daily_log(DAY0)
        make_block_entry(log, block_code="B1")
        with pytest.raises(ValidationError):
            make_block_entry(log, block_code="B1")


class TestApplicationFurthestStage:
    def test_in_flight_furthest_stage_is_itself(self):
        from core.tests.factories import make_application

        app = make_application("A", "r1", stage=Application.Stage.TECH)
        assert app.furthest_stage() == "tech"

    def test_rejected_without_postmortem_falls_back_to_applied(self):
        from core.tests.factories import make_application

        app = make_application("A", "r1", stage=Application.Stage.REJECTED)
        assert app.furthest_stage() == Application.Stage.APPLIED
