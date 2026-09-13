import importlib

import pytest
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

JOB_SEARCH_SEED = importlib.import_module("core.migrations.0010_seed_job_search_2026_09_13")


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Migrations run for the test database, so 0010's real personal rows
    (five applications, one LinkedIn snapshot) land in it too. Every funnel/
    decay/read-endpoint test assumes it starts with no applications, so strip
    exactly those rows once per session. Program scaffolding (0002/0006) is
    untouched. The seed itself is covered in test_job_search.py by calling
    the migration function directly."""
    from core.models import Application, LinkedInSnapshot

    with django_db_blocker.unblock():
        for company, role, *_ in JOB_SEARCH_SEED.APPLICATIONS:
            Application.objects.filter(
                company=company, role=role, applied_on=JOB_SEARCH_SEED.SEED_DATE
            ).delete()
        LinkedInSnapshot.objects.filter(log_date=JOB_SEARCH_SEED.SEED_DATE).delete()


@pytest.fixture
def user(db):
    User = get_user_model()
    return User.objects.create_superuser(username="bhagath", email="bhagath@example.com", password="x")


@pytest.fixture
def user_token(user):
    token, _ = Token.objects.get_or_create(user=user)
    return token.key


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_client(api_client, user_token):
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {user_token}")
    return api_client


@pytest.fixture
def ingest_client(api_client, settings, user):
    # `user` (a superuser) must exist for IngestTokenAuthentication to have
    # someone to attribute machine-written rows to (core.auth.resolve_ingest_owner).
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {settings.INGEST_TOKEN}")
    return api_client
