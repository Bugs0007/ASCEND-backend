"""
Idempotent, non-interactive superuser bootstrap for build-time use on
Render's free plan, which has no Shell/SSH/Jobs access (those became a
paid-plan feature) — see docs/SETUP.md.

Reads DJANGO_SUPERUSER_USERNAME / DJANGO_SUPERUSER_EMAIL /
DJANGO_SUPERUSER_PASSWORD, all set by the user directly in the Render
dashboard's Environment tab (never seen by, or passed through, anything
else in this codebase). Always exits 0 so it's safe to chain into
buildCommand on every deploy:

  * If the two required env vars aren't set, or a superuser already
    exists, it's a clean no-op — the build never fails because of this
    step, whether or not the vars are present yet.
  * Otherwise it creates exactly one superuser, once.
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create a superuser from DJANGO_SUPERUSER_* env vars if one doesn't already exist."

    def handle(self, *args, **options):
        User = get_user_model()

        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write("bootstrap_superuser: a superuser already exists — skipping.")
            return

        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")

        if not username or not password:
            self.stdout.write(
                "bootstrap_superuser: DJANGO_SUPERUSER_USERNAME/PASSWORD not set yet — skipping. "
                "Add them in the Render dashboard's Environment tab and redeploy."
            )
            return

        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(f"bootstrap_superuser: created superuser '{username}'.")
