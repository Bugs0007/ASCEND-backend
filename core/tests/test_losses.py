import datetime

import pytest

from core.analytics import losses
from core.models import LossPostmortem
from core.tests.factories import make_application, make_loss_postmortem

pytestmark = pytest.mark.django_db

DAY = datetime.date(2026, 9, 20)


class TestLosses:
    def test_empty(self):
        result = losses.compute()
        assert result["total"] == 0
        assert result["dominant_cause"] is None

    def test_below_dominance_threshold(self):
        app = make_application("A", "r1")
        make_loss_postmortem(app, round_reached="tech", cause=LossPostmortem.Cause.DSA, logged_on=DAY)
        make_loss_postmortem(app, round_reached="final", cause=LossPostmortem.Cause.DSA, logged_on=DAY)
        result = losses.compute()
        assert result["by_cause"]["dsa"] == 2
        assert result["dominant_cause"] is None  # needs >= 3

    def test_dominant_cause_named_at_three(self):
        apps = [make_application(f"Co{i}", "role") for i in range(3)]
        for i, app in enumerate(apps):
            make_loss_postmortem(app, round_reached=f"round{i}", cause=LossPostmortem.Cause.SYSTEM_DESIGN, logged_on=DAY)
        result = losses.compute()
        assert result["by_cause"]["system_design"] == 3
        assert result["dominant_cause"] == "system_design"

    def test_tie_at_top_has_no_dominant(self):
        apps = [make_application(f"Co{i}", "role") for i in range(6)]
        for i in range(3):
            make_loss_postmortem(apps[i], round_reached=f"r{i}", cause=LossPostmortem.Cause.DSA, logged_on=DAY)
        for i in range(3, 6):
            make_loss_postmortem(apps[i], round_reached=f"r{i}", cause=LossPostmortem.Cause.COMMUNICATION, logged_on=DAY)
        result = losses.compute()
        assert result["dominant_cause"] is None
