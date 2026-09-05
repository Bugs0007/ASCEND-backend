"""
Machine-token authentication for the ingest API and the two dual-auth
read endpoints (/api/today/, /api/email-queue/).

This is a deliberately separate code path from the human's DRF
TokenAuthentication: different credential (INGEST_TOKEN, not a per-user
DRF token), different header value shape is still `Authorization: Bearer
<token>` (DRF's TokenAuthentication expects `Token <key>`, so the two never
collide on the wire), and a constant-time comparison so response timing
can't leak how much of the token was guessed correctly.
"""
import hmac

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import authentication, exceptions

User = get_user_model()


def resolve_ingest_owner():
    """
    The Django user that machine-written rows are attributed to. Explicit
    override via INGEST_OWNER_USERNAME, else the first superuser (by id) —
    there is exactly one in this deployment, created by hand via the Render
    shell (core/models.py, OwnedModel).
    """
    if settings.INGEST_OWNER_USERNAME:
        return User.objects.filter(username=settings.INGEST_OWNER_USERNAME).first()
    return User.objects.filter(is_superuser=True).order_by("id").first()


class IngestTokenAuthentication(authentication.BaseAuthentication):
    """
    Authorization: Bearer <INGEST_TOKEN>

    On success, request.user is set to the resolved ingest owner (a real
    Django User) rather than some synthetic principal, so `owner=request.user`
    works identically whether a row was written by the human or by a
    scheduled Claude task / iPhone Shortcut.
    """

    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("utf-8")
        if not header:
            return None
        parts = header.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            return None  # not our scheme — let other authenticators (or a 401) handle it

        token = parts[1]
        if not hmac.compare_digest(token.encode("utf-8"), settings.INGEST_TOKEN.encode("utf-8")):
            raise exceptions.AuthenticationFailed("Invalid ingest token.")

        owner = resolve_ingest_owner()
        if owner is None:
            raise exceptions.AuthenticationFailed(
                "No superuser exists yet to attribute ingest writes to. "
                "Create one first (see docs/SETUP.md)."
            )
        return (owner, None)

    def authenticate_header(self, request):
        return self.keyword
