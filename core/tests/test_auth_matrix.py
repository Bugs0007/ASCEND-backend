"""
Pins which credential each /api/ route accepts, so a view can't drift from
the split documented in core/views.py's header without a test changing too.

Every view declares its own authentication_classes. That matters because the
settings-level DRF default *includes* the machine token: a new view that
forgot to declare its auth would silently accept INGEST_TOKEN. Guards:

  * every route must be listed in EXPECTED_AUTH — adding a view forces a
    conscious decision about who may call it;
  * each route's effective authenticators (class attribute, or an as_view()
    override like the schema view's) must equal what's listed;
  * each route must *declare* its auth in core.* rather than inherit the
    settings default;
  * public routes are AllowAny, everything else IsAuthenticated.

No database needed — this only inspects the URLconf.
"""
import pytest
from django.urls import get_resolver
from rest_framework import permissions
from rest_framework.authentication import TokenAuthentication

from core.auth import IngestTokenAuthentication

HUMAN = frozenset({TokenAuthentication})
MACHINE = frozenset({IngestTokenAuthentication})
EITHER = HUMAN | MACHINE
PUBLIC = frozenset()

HUMAN_ONLY_ROUTES = [
    "api/analytics/activity/",
    "api/analytics/burnup/",
    "api/analytics/certtrend/",
    "api/analytics/correlations/",
    "api/analytics/decay/",
    "api/analytics/funnel/",
    "api/analytics/losses/",
    "api/analytics/observations/",
    "api/analytics/rhythm/",
    "api/applications/",
    "api/applications/<int:pk>/",
    "api/block-entries/<int:pk>/",
    "api/blocks/<str:code>/complete/",
    "api/blocks/<str:code>/start/",
    "api/cert-domains/",
    "api/content-posts/",
    "api/countdowns/<int:pk>/",
    "api/courses/",
    "api/milestones/",
    "api/notion-tasks/",
    "api/notion-tasks/<int:pk>/",
    "api/reflections/",
    "api/skills/",
    "api/sleep-logs/",
    "api/sleep-logs/<int:pk>/",
    "api/today/selections/",
    "api/today/selections/<int:pk>/",
]

EXPECTED_AUTH = {
    "api/health/": PUBLIC,
    "api/schema/": PUBLIC,
    # Machine token only.
    "api/ingest/": MACHINE,
    "api/ingest/sleep/": MACHINE,
    "api/sync/notion/": MACHINE,
    # Either — the frontend and the scheduled Claude tasks share these.
    "api/today/": EITHER,
    "api/today/pool/": EITHER,
    "api/today/recommendations/": EITHER,
    "api/email-queue/": EITHER,
    "api/daily-logs/": EITHER,
    "api/linkedin-snapshots/": EITHER,
    **{route: HUMAN for route in HUMAN_ONLY_ROUTES},
}

# DRF's built-in obtain_auth_token: mints a user token from username +
# password, so it has no auth contract of its own to pin.
EXCLUDED = {"api/auth/token/"}


def _api_routes():
    routes = {}

    def walk(patterns, prefix=""):
        for p in patterns:
            if hasattr(p, "url_patterns"):
                walk(p.url_patterns, prefix + str(p.pattern))
            else:
                route = prefix + str(p.pattern)
                if route.startswith("api/"):
                    routes[route] = p.callback

    walk(get_resolver().url_patterns)
    return routes


API_ROUTES = _api_routes()


def _effective(view, name):
    """The class attribute unless as_view(**initkwargs) overrode it."""
    return getattr(view, "initkwargs", {}).get(name, getattr(view.cls, name))


def test_every_api_route_has_an_expected_auth():
    unlisted = set(API_ROUTES) - set(EXPECTED_AUTH) - EXCLUDED
    assert not unlisted, f"add these to EXPECTED_AUTH with their intended credentials: {sorted(unlisted)}"


def test_no_expected_route_is_stale():
    stale = set(EXPECTED_AUTH) - set(API_ROUTES)
    assert not stale, f"these routes no longer exist, drop them from EXPECTED_AUTH: {sorted(stale)}"


@pytest.mark.parametrize("route", sorted(EXPECTED_AUTH))
def test_route_accepts_exactly_the_expected_credentials(route):
    actual = frozenset(_effective(API_ROUTES[route], "authentication_classes"))
    assert actual == EXPECTED_AUTH[route]


@pytest.mark.parametrize("route", sorted(EXPECTED_AUTH))
def test_route_declares_its_own_auth_instead_of_inheriting_the_default(route):
    view = API_ROUTES[route]
    declared = "authentication_classes" in getattr(view, "initkwargs", {}) or any(
        "authentication_classes" in vars(klass)
        for klass in view.cls.__mro__
        if klass.__module__.startswith("core.")
    )
    assert declared, f"{view.cls.__name__} inherits DRF's default authenticators — declare them explicitly"


@pytest.mark.parametrize("route", sorted(EXPECTED_AUTH))
def test_route_permission_matches_its_auth(route):
    expected = permissions.AllowAny if EXPECTED_AUTH[route] == PUBLIC else permissions.IsAuthenticated
    assert list(_effective(API_ROUTES[route], "permission_classes")) == [expected]
