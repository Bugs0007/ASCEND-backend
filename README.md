# ASCEND backend

Backend for **ASCEND**, a single-user personal progress console tracking a
90-day job-search / AI-engineering program (**2026-09-07 → 2026-12-13**).
Django 5.2 + DRF, plain-Python analytics (no numpy/pandas), Postgres on
Neon, hosted free on Render.

The frontend renders. This backend computes every number — streaks,
correlations, funnel conversion, burn-up projections, the 21-day ghost
rule — and every analytics function is unit-tested against hand-computed
fixtures (`core/tests/`). See [Order](#order) below for why analytics were
built and tested before a single view existed.

## Stack

- Django 5.2, Django REST Framework, Python 3.12 (3.13 also works locally)
- PostgreSQL on [Neon](https://neon.tech) — direct/unpooled connection
- Hosted on [Render](https://render.com) (free web service) via `render.yaml`
- gunicorn + WhiteNoise; settings entirely env-driven via `python-decouple`
- One Django app: `core`
- No numpy/pandas/Celery/Redis/Channels/websockets/AWS — see
  `docs/SETUP.md` for why

## Project layout

```
ascend/            Django project (settings, urls, wsgi)
core/
  models.py         20 models — see the model docstring for the ownership
                     scheme and the three model-layer invariants
  constants.py       every tunable number (GHOST_DAYS, GREEN_DAY_BLOCK_THRESHOLD, ...)
  stats.py           plain-Python mean/median/IQR/Pearson r/OLS — no numpy
  analytics/         one module per /api/analytics/* endpoint
  auth.py            IngestTokenAuthentication — the machine-token code path
  serializers.py      ingest payload validation (unknown fields -> 400)
  ingest.py           upsert-by-natural-key logic + sleep day attribution
  views.py / urls.py  every endpoint
  migrations/         0001_initial, 0002_seed_program (phases/weeks/blocks/
                       projects/milestones/cert domains/courses/skills/countdowns)
  tests/              pytest-django suite, one module per analytics endpoint
                       plus test_ingest.py, test_views.py, test_models.py
docs/                 SETUP.md, INGEST_API.md, CLAUDE_TASK_PAYLOADS.md, SHORTCUTS.md
scripts/              verify.sh / verify.ps1 — live-deployment smoke test
render.yaml           Render Blueprint (free web service)
docker-compose.yml    disposable local Postgres for running the test suite
```

## Local development

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; `source .venv/bin/activate` elsewhere
pip install -r requirements-dev.txt
cp .env.example .env          # fill in a local DATABASE_URL
docker compose up -d db       # disposable local Postgres, see docker-compose.yml
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Running tests

```bash
docker compose up -d db
pytest
```

The suite runs against real Postgres (not SQLite) because `Project.tech`
is a Postgres `ArrayField` — SQLite can't run the migrations.

## API surface

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /api/health/` | none | DB-touching health check for keep-warm |
| `POST /api/auth/token/` | username+password | Mint your DRF token (Render free plan has no Shell — see docs/SETUP.md) |
| `POST /api/ingest/` | machine token | Batch upsert across 11 resource types |
| `POST /api/ingest/sleep/` | machine token | Tiny endpoint for iPhone Shortcuts |
| `GET /api/today/` | either | Today's blocks, streak, milestones, decay, countdowns |
| `GET /api/email-queue/` | either | Unmatched EmailEvent review queue |
| `POST /api/blocks/<code>/start/`, `.../complete/` | human token | Tap-to-track a block |
| `PATCH /api/block-entries/<id>/` | human token | Undo a block completion |
| `PATCH /api/countdowns/<id>/` | human token | Set a countdown's target date (rejected if not `editable`) |
| `GET /api/analytics/{rhythm,correlations,funnel,losses,burnup,certtrend,decay,activity,observations}/` | human token | Read-only computed analytics |
| `GET /api/{applications,milestones,sleep-logs,daily-logs,skills,courses,cert-domains,content-posts,reflections}/` | human token | Read lists, filtered/ordered, owner-scoped |
| `POST /api/sync/notion/` | machine token | Pull your Notion "Daily Board" into `NotionTask` — see [docs/NOTION_SYNC.md](docs/NOTION_SYNC.md) |
| `GET /api/notion-tasks/` | human token | List the synced Notion rows |
| `GET /api/schema/` | none | OpenAPI schema — canonical types for a frontend |

Full contract with curl examples: [docs/INGEST_API.md](docs/INGEST_API.md).

## Deployment

See [docs/SETUP.md](docs/SETUP.md) for the complete first-deploy
walkthrough (Neon → GitHub → Render → superuser → verify → cron-job.org
keep-warm), assuming nothing is set up yet.

## Order

Built in this order, deliberately:

1. Project, `core` app, models, migrations, seed migration.
2. **Analytics functions and their tests, before any view existed.** A
   silent bug in `core/stats.py` or `core/analytics/*` would quietly
   corrupt three months of data — those got the scrutiny first.
3. Serializers, viewsets, auth, ingest, health.
4. Deploy to Render + Neon, verified live with `scripts/verify.sh`.
5. Docs.
