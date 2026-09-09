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
| `GET /api/milestones/` | `status`, `project` (code, e.g. `A`) | `due_date` (default), `title` | Milestone lists beyond `/today/`'s slice — now includes a `detail` field (long-form scope, `null` where not yet written) |
| `GET /api/sleep-logs/` | `log_date__gte`/`__lte` | `log_date` | Sleep history |
| `GET /api/daily-logs/` | `log_date__gte`/`__lte` | `log_date` | **The `/rhythm` heatmap — this was rendering empty before, this is the fix** |
| `GET /api/skills/` | — | `name`, `level` | **The skill radar — same story, was an empty state** |
| `GET /api/courses/` | — | `name`, `progress_pct` | Course progress list |
| `GET /api/cert-domains/` | — | `domain_no`, `mastery_pct` | Cert domain breakdown |
| `GET /api/content-posts/` | — | `posted_on` (default) | Content history |
| `GET /api/reflections/` | `log_date__gte`/`__lte` | `log_date` | Reflection journal view |
| `GET /api/notion-tasks/` | `status` | `due_date`, `notion_last_edited` | The Notion Daily Board mirror (below) |

Plus three writes that had none before:

- `PATCH /api/countdowns/<id>/` — `{"target_date": "YYYY-MM-DD"}` or `null`.
  `400` if that countdown's `editable` is `false` (Program end is fixed).
- `PATCH /api/block-entries/<id>/` — `{}` undoes a completion (clears
  `ended_at`/`elapsed_minutes`, keeps `started_at`). Idempotent, safe to
  call more than once.
- `PATCH /api/notion-tasks/<id>/` — `{"status": "<new status>"}` writes the
  status back to Notion **and** updates the local row in the same response.
  `400` if the value isn't a real option on the board; `502` if Notion
  rejects the write. See the Notion section below.

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

## Notion "Daily Board" mirror — now two-way

`GET /api/notion-tasks/` lists rows synced from Notion via
`POST /api/sync/notion/` (machine token, on a ~20 min cron — see
[`NOTION_SYNC.md`](NOTION_SYNC.md)). Shape:

```json
{
  "id": 1, "notion_page_id": "...", "title": "...", "status": "...",
  "category": "...", "due_date": "2026-09-10",
  "notion_last_edited": "...", "synced_at": "...",
  "status_changed_at": "2026-09-08T14:03:00Z"
}
```

`status`/`category` are whatever your board's actual properties resolved
to at sync time (dynamic detection, not a fixed enum — don't hardcode a
choice list against these in the frontend). Either can be blank/null if the
board doesn't have a matching property.

**`status_changed_at`** (new) is when `status` last actually changed value —
not any edit (`notion_last_edited`), not every sync (`synced_at`). This is
the field to count a "sat in its current column for 48h → auto-archive"
rule from. It's `null` on rows that predate the field; they pick up a real
value the next time their status changes.

### Writing a status back

`PATCH /api/notion-tasks/<id>/` with `{"status": "<new status>"}` (your user
token). The backend validates the value against the board's live status
options, pushes it to the Notion page with the right payload shape for the
property type (native `status` vs `select`), and updates the local row —
the response is the updated row, so you don't need to refetch or wait for
the cron sync. `400` for a status that isn't a real board option (the
response body lists the valid ones); `502` if Notion itself rejects it.

One-time setup dependency: the Notion integration needs **Update content**
capability enabled (it was **Read content** only before) — flagged in
`NOTION_SYNC.md`. Until that's done every write-back `502`s.

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
