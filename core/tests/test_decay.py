import datetime

import pytest

from core.analytics import decay
from core.constants import DECAY_DAYS
from core.models import Application, CertDomain, Project
from core.tests.factories import make_application

pytestmark = pytest.mark.django_db

AS_OF = datetime.date(2026, 10, 1)


def _aware(date_obj):
    """updated_at is a DateTimeField — give it an aware datetime, not a bare date."""
    return datetime.datetime.combine(date_obj, datetime.time.min, tzinfo=datetime.timezone.utc)


class TestDecay:
    def test_decay_days_constant_is_14(self):
        assert DECAY_DAYS == 14

    def test_application_flagged_after_decay_days(self):
        make_application(
            "A", "r1", stage=Application.Stage.APPLIED,
            last_update=AS_OF - datetime.timedelta(days=DECAY_DAYS),
        )
        result = decay.compute(as_of=AS_OF)
        assert len(result["applications"]) == 1
        assert result["applications"][0]["company"] == "A"

    def test_application_not_flagged_before_decay_days(self):
        make_application(
            "A", "r1", stage=Application.Stage.APPLIED,
            last_update=AS_OF - datetime.timedelta(days=DECAY_DAYS - 1),
        )
        result = decay.compute(as_of=AS_OF)
        assert len(result["applications"]) == 0

    def test_terminal_applications_never_flagged(self):
        make_application(
            "A", "r1", stage=Application.Stage.REJECTED,
            last_update=AS_OF - datetime.timedelta(days=365),
        )
        result = decay.compute(as_of=AS_OF)
        assert len(result["applications"]) == 0

    def test_cert_domain_never_studied_is_flagged(self):
        domain = CertDomain.objects.filter(cert_code="AI-103").first()
        domain.last_studied = None
        domain.save()
        result = decay.compute(as_of=AS_OF)
        codes = [d["domain_no"] for d in result["cert_domains"]]
        assert domain.domain_no in codes

    def test_cert_domain_recently_studied_not_flagged(self):
        domain = CertDomain.objects.filter(cert_code="AI-103").first()
        domain.last_studied = AS_OF - datetime.timedelta(days=1)
        domain.save()
        result = decay.compute(as_of=AS_OF)
        codes = [d["domain_no"] for d in result["cert_domains"]]
        assert domain.domain_no not in codes

    def test_project_flagged_via_updated_at(self):
        project = Project.objects.get(code="A")
        stale = _aware(AS_OF - datetime.timedelta(days=DECAY_DAYS + 5))
        # Force both the project and its milestones' updated_at deterministically
        # (bypassing auto_now, since QuerySet.update() doesn't trigger it) so
        # this test doesn't depend on the wall-clock moment migrations ran.
        Project.objects.filter(pk=project.pk).update(updated_at=stale)
        project.milestones.update(updated_at=stale)
        result = decay.compute(as_of=AS_OF)
        codes = [p["code"] for p in result["projects"]]
        assert "A" in codes

    def test_project_not_flagged_with_recent_milestone_activity(self):
        project = Project.objects.get(code="A")
        Project.objects.filter(pk=project.pk).update(
            updated_at=_aware(AS_OF - datetime.timedelta(days=DECAY_DAYS + 5))
        )
        # A milestone touched yesterday keeps the project off the decay list
        # even though the project row itself is stale.
        project.milestones.update(updated_at=_aware(AS_OF - datetime.timedelta(days=1)))
        result = decay.compute(as_of=AS_OF)
        codes = [p["code"] for p in result["projects"]]
        assert "A" not in codes
