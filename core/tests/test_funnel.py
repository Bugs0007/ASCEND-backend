import datetime

import pytest

from core.analytics import funnel
from core.constants import GHOST_DAYS
from core.models import Application
from core.tests.factories import make_application, make_loss_postmortem

pytestmark = pytest.mark.django_db

AS_OF = datetime.date(2026, 10, 1)


class TestFunnelConversion:
    def test_empty_funnel_no_divide_by_zero(self):
        result = funnel.compute(as_of=AS_OF)
        assert result["total_applications"] == 0
        for pct in result["conversion"].values():
            assert pct is None  # safe_div default, not a ZeroDivisionError

    def test_stage_counts_and_conversion(self):
        # 4 applied, 2 reached screen, 1 reached tech
        make_application("A", "r1", stage=Application.Stage.APPLIED, last_update=AS_OF)
        make_application("B", "r2", stage=Application.Stage.APPLIED, last_update=AS_OF)
        make_application("C", "r3", stage=Application.Stage.SCREEN, last_update=AS_OF)
        make_application("D", "r4", stage=Application.Stage.TECH, last_update=AS_OF)
        result = funnel.compute(as_of=AS_OF)
        assert result["reached_counts"]["applied"] == 4
        assert result["reached_counts"]["screen"] == 2
        assert result["reached_counts"]["tech"] == 1
        assert result["reached_counts"]["oa"] == 1  # tech implies reached oa too
        assert result["conversion"]["applied_to_screen"] == pytest.approx(0.5)
        assert result["conversion"]["screen_to_oa"] == pytest.approx(0.5)

    def test_interview_rate_per_source(self):
        make_application("A", "r1", source=Application.Source.REFERRAL, stage=Application.Stage.SCREEN, last_update=AS_OF)
        make_application("B", "r2", source=Application.Source.REFERRAL, stage=Application.Stage.APPLIED, last_update=AS_OF)
        make_application("C", "r3", source=Application.Source.PORTAL, stage=Application.Stage.APPLIED, last_update=AS_OF)
        result = funnel.compute(as_of=AS_OF)
        assert result["interview_rate_per_source"]["referral"] == pytest.approx(0.5)
        assert result["interview_rate_per_source"]["portal"] == pytest.approx(0.0)

    def test_rejected_application_uses_postmortem_furthest_stage(self):
        app = make_application(
            "A", "r1", stage=Application.Stage.REJECTED, last_update=AS_OF
        )
        make_loss_postmortem(app, round_reached="tech", logged_on=AS_OF)
        result = funnel.compute(as_of=AS_OF)
        assert result["reached_counts"]["tech"] == 1
        assert result["reached_counts"]["final"] == 0


class TestGhostBoundary:
    """The rule is >= GHOST_DAYS (21): day 20 not ghosted, day 21 ghosted."""

    def test_20_days_not_ghosted(self):
        app = make_application(
            "A", "r1",
            stage=Application.Stage.APPLIED,
            last_update=AS_OF - datetime.timedelta(days=20),
        )
        assert app.is_ghosted(as_of=AS_OF) is False

    def test_21_days_is_ghosted(self):
        assert GHOST_DAYS == 21
        app = make_application(
            "A", "r1",
            stage=Application.Stage.APPLIED,
            last_update=AS_OF - datetime.timedelta(days=21),
        )
        assert app.is_ghosted(as_of=AS_OF) is True

    def test_ghost_never_mutates_stored_stage(self):
        app = make_application(
            "A", "r1",
            stage=Application.Stage.APPLIED,
            last_update=AS_OF - datetime.timedelta(days=30),
        )
        assert app.is_ghosted(as_of=AS_OF) is True
        app.refresh_from_db()
        assert app.stage == Application.Stage.APPLIED  # unchanged

    def test_terminal_stages_are_never_ghosted(self):
        rejected = make_application(
            "A", "r1", stage=Application.Stage.REJECTED,
            last_update=AS_OF - datetime.timedelta(days=100),
        )
        offer = make_application(
            "B", "r2", stage=Application.Stage.OFFER,
            last_update=AS_OF - datetime.timedelta(days=100),
        )
        assert rejected.is_ghosted(as_of=AS_OF) is False
        assert offer.is_ghosted(as_of=AS_OF) is False

    def test_ghost_count_in_funnel(self):
        make_application("A", "r1", stage=Application.Stage.APPLIED, last_update=AS_OF - datetime.timedelta(days=21))
        make_application("B", "r2", stage=Application.Stage.APPLIED, last_update=AS_OF - datetime.timedelta(days=5))
        result = funnel.compute(as_of=AS_OF)
        assert result["ghost_count"] == 1
