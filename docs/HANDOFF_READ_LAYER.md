# Handoff: read layer + Notion sync (for the next frontend session)

What changed in the backend since the frontend was last built against it,
and what to do with it.

## New endpoints, replace your placeholders with these

All human-token (`Authorization: Token <key>`), paginated
(`{"count","next","previous","results"}`, 50/page), owner-scoped, filterable
and orderable via standard DRF query params:

| Endpoint | Filters | Ordering | Powers |
|---|---|---|---|
| `GET /api/applications/` | `stage`, `source` | `last_update` (default), `applied_on`, `company` | Pipeline/funnel board |
| `GET /api/milestones/` | `status`, `project` (code, e.g. `A`) | `due_date` (default), `title` | Milestone lists beyond `/today/`'s slice |
| `GET /api/sleep-logs/` | `log_date__gte`/`__lte` | `log_date` | Sleep history |
| `GET /api/daily-logs/` | `log_date__gte`/`__lte` | `log_date` | **The `/rhythm` heatmap — this was rendering empty before, this is the fix** |
| `GET /api/skills/` | — | `name`, `level` | **The skill radar — same story, was an empty state** |
| `GET /api/courses/` | — | `name`, `progress_pct` | Course progress list |
| `GET /api/cert-domains/` | — | `domain_no`, `mastery_pct` | Cert domain breakdown |
| `GET /api/content-posts/` | — | `posted_on` (default) | Content history |
| `GET /api/reflections/` | `log_date__gte`/`__lte` | `log_date` | Reflection journal view |
| `GET /api/notion-tasks/` | `status` | `due_date`, `notion_last_edited` | The Notion Daily Board mirror (below) |

Plus two writes that had none before:

- `PATCH /api/countdowns/<id>/` — `{"target_date": "YYYY-MM-DD"}` or `null`.
  `400` if that countdown's `editable` is `false` (Program end is fixed).
- `PATCH /api/block-entries/<id>/` — `{}` undoes a completion (clears
  `ended_at`/`elapsed_minutes`, keeps `started_at`). Idempotent, safe to
  call more than once.

**`GET /api/schema/`** (public, no auth) is the canonical field/type
reference for all of the above — generate real types from it rather than
hand-writing them; this doc gives shapes and intent, not an exhaustive spec.

## Owner-scoping asymmetry — deliberate, not a bug

These new endpoints filter by `Q(owner=request.user) | Q(owner__isnull=True)`.
The *older* endpoints (`/api/today/`, `/api/email-queue/`, every
`/api/analytics/*`) do **not** — they return everything regardless of
owner, and only tag new rows with an owner on write. This was already true
before this change; it wasn't retrofitted onto the old endpoints here
(out of scope, and would mean touching every analytics module's
signature). Doesn't matter for the single real user today; worth knowing
if that ever changes.

## Notion "Daily Board" mirror

`GET /api/notion-tasks/` lists rows synced from Notion via
`POST /api/sync/notion/` (machine token, on a ~20 min cron — see
[`NOTION_SYNC.md`](NOTION_SYNC.md)). Read-only from the frontend's
perspective same as everything else here — this backend never writes back
to Notion. Shape:

```json
{
  "id": 1, "notion_page_id": "...", "title": "...", "status": "...",
  "category": "...", "due_date": "2026-09-10",
  "notion_last_edited": "...", "synced_at": "..."
}
```

`status`/`category` are whatever your board's actual properties resolved
to at sync time (dynamic detection, not a fixed enum — don't hardcode a
choice list against these in the frontend). Either can be blank/null if the
board doesn't have a matching property.

## Known, unrelated doc/reality gap (not fixed here, flagging so it doesn't look like an oversight)

`docs/SETUP.md` still describes Render as Blueprint-deploying from
`render.yaml` automatically. In reality this specific service was created
via Render's raw API, not as a Blueprint — `render.yaml` is not
authoritative for it; env vars and the build command were set/patched
directly via Render's API in this and the prior session. `render.yaml` is
still kept up to date in the repo for documentation and in case the
service is ever recreated as a real Blueprint, but don't trust it as a
description of the *current* live service's actual configuration without
double-checking via `GET /v1/services/{id}`.
