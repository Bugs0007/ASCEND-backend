"""
Django settings for the ASCEND backend.

Everything environment-specific is read through python-decouple from a
`.env` file (local dev) or real environment variables (Render). See
.env.example for the full list of variables and what they mean.
"""
from pathlib import Path

import dj_database_url
from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Core ---
SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

# Render sets this automatically for the service's own domain; add it so the
# health check and the app itself are reachable without hand-maintaining it.
_render_host = config("RENDER_EXTERNAL_HOSTNAME", default="")
if _render_host:
    ALLOWED_HOSTS.append(_render_host)

# Django's ALLOWED_HOSTS supports a leading-dot wildcard (".onrender.com"
# matches any subdomain); CSRF_TRUSTED_ORIGINS needs the same idea spelled
# with a leading "*" instead, so translate rather than string-pasting the
# two together into something invalid.
CSRF_TRUSTED_ORIGINS = [
    f"https://*{h}" if h.startswith(".") else f"https://{h}"
    for h in ALLOWED_HOSTS
    if h not in ("localhost", "127.0.0.1")
]

# --- Applications ---
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "ascend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "ascend.wsgi.application"

# --- Database (Neon Postgres) ---
# CONN_MAX_AGE=0: short-lived connections are fine for a single-user app and
# sidestep any pooling weirdness. ssl_require follows Neon's own requirement.
# The direct (unpooled) connection string is required — psycopg3 issues
# server-side PREPARE statements by default, which PgBouncer transaction
# pooling (Neon's pooled endpoint) cannot support across requests.
DATABASES = {
    "default": dj_database_url.config(
        default=config("DATABASE_URL"),
        conn_max_age=0,
        ssl_require=not DEBUG,
    )
}
# Disable psycopg3 server-side prepared statements for the same reason, and
# because it's simply unnecessary for this traffic volume.
DATABASES["default"].setdefault("OPTIONS", {})
DATABASES["default"]["OPTIONS"]["prepare_threshold"] = None
# Neon's serverless computes suspend after a period of idle and take a
# noticeable few seconds to cold-start on the next connection (observed
# ~15-20s against a suspended branch) — psycopg3's own default connect
# timeout is otherwise short enough to fail during exactly that window.
# This can stack with Render's own free-tier cold start, so it's worth
# tolerating here rather than surfacing as a flaky 500.
DATABASES["default"]["OPTIONS"]["connect_timeout"] = 30

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- I18N / timezone ---
# Drives SleepLog day-attribution, the rhythm start-time distribution and
# every streak/green-day boundary. Stored in UTC (USE_TZ=True); anything that
# reasons about "which calendar day" converts to this zone first.
LANGUAGE_CODE = "en-us"
TIME_ZONE = config("TIME_ZONE", default="Asia/Kolkata")
USE_I18N = True
USE_TZ = True

# --- Static files ---
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- DRF ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "core.auth.IngestTokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    # Global default so the new list endpoints get filtering/ordering "for
    # free" just by declaring filterset_fields/ordering_fields — harmless for
    # every existing hand-rolled APIView, which never calls filter_queryset()
    # in the first place.
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# --- OpenAPI schema (drf-spectacular) ---
# So the frontend can generate real types from /api/schema/ instead of
# hand-written ones that drift. Existing hand-rolled analytics/today/ingest
# views will produce noisier/less-typed schema entries than the new
# ModelSerializer-backed read endpoints — that's pre-existing-view noise,
# not a regression, and not something this change tries to retrofit.
SPECTACULAR_SETTINGS = {
    "TITLE": "ASCEND API",
    "DESCRIPTION": "Personal 90-day program-tracking backend.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# --- CORS ---
# The frontend is a separate origin that polls this API. Origins are
# env-driven so nothing is hardcoded per-deploy.
CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="", cast=Csv())

# --- ASCEND-specific ---
# Bearer token for the machine-auth code path used by scheduled Claude tasks
# and iPhone Shortcuts. Separate credential, separate auth class
# (core.auth.IngestTokenAuthentication), constant-time compare.
INGEST_TOKEN = config("INGEST_TOKEN")
# Username of the superuser that machine-written rows are attributed to.
# Falls back to the first superuser found (by id) if unset.
INGEST_OWNER_USERNAME = config("INGEST_OWNER_USERNAME", default="")

# Notion "Daily Board" read-only mirror (core/notion_sync.py). Deliberately
# optional here, unlike SECRET_KEY/INGEST_TOKEN above — this app is already
# live serving real traffic, and a required-no-default config() call crashes
# every request at boot the moment this code deploys, until the var is set on
# Render. The actual "is this configured" check happens at call time inside
# core/notion_sync.py, returning a 503 rather than crashing the whole app.
NOTION_TOKEN = config("NOTION_TOKEN", default="")
NOTION_DAILY_BOARD_DB_ID = config("NOTION_DAILY_BOARD_DB_ID", default="94fb5ba274ab499b8ae23e652774be2a")

# --- Security (mostly relevant behind Render's TLS-terminating proxy) ---
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
