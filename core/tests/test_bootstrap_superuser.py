import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

pytestmark = pytest.mark.django_db

User = get_user_model()


class TestBootstrapSuperuser:
    def test_noop_when_env_vars_unset(self, monkeypatch):
        monkeypatch.delenv("DJANGO_SUPERUSER_USERNAME", raising=False)
        monkeypatch.delenv("DJANGO_SUPERUSER_PASSWORD", raising=False)
        call_command("bootstrap_superuser")
        assert User.objects.count() == 0

    def test_creates_superuser_from_env_vars(self, monkeypatch):
        monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "bhagath")
        monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", "bhagath@example.com")
        monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "a-strong-password")
        call_command("bootstrap_superuser")
        user = User.objects.get(username="bhagath")
        assert user.is_superuser
        assert user.check_password("a-strong-password")

    def test_safe_noop_on_second_run(self, monkeypatch):
        monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "bhagath")
        monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "a-strong-password")
        call_command("bootstrap_superuser")
        call_command("bootstrap_superuser")  # must not raise on redeploy
        assert User.objects.count() == 1

    def test_does_not_overwrite_an_existing_superuser_with_different_env(self, monkeypatch):
        User.objects.create_superuser(username="already-here", email="", password="x")
        monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "someone-else")
        monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "y")
        call_command("bootstrap_superuser")
        assert User.objects.count() == 1
        assert User.objects.get().username == "already-here"
