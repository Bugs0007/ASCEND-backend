import pytest
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient


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
