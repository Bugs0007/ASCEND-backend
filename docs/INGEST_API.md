# Ingest API contract

All ingest endpoints use a **machine token**, separate from your own login.

```
Authorization: Bearer <INGEST_TOKEN>
```

This is a different code path from the human `TokenAuthentication` used by
`/api/analytics/*` and the block-tap endpoints — a stray user token gets a
401 here, and the ingest token gets a 401 on those (see
[`core/auth.py`](../core/auth.py)). Rows written through ingest are
attributed to the resolved **ingest owner** — `INGEST_OWNER_USERNAME` if
set, else the first superuser — never left ownerless.

Base URL below is written as `$BASE` — substitute your live Render URL
(e.g. `https://ascend-backend.onrender.com`) or `http://localhost:8000`
for local testing.

---

## POST /api/ingest/

Body: a JSON object keyed by resource type, each value a **list** of rows.
You can post one resource type or all thirteen in a single call.

```json
{
  "daily_logs": [ { "...": "..." } ],
  "applications": [ { "...": "..." } ]
}
```

**Unknown fields return 400** — a typo'd key, not a silently dropped one.
An unknown top-level resource-type key is also a 400. The whole payload is
applied in one transaction: if any row in any resource fails validation,
nothing in that request is committed.

The response is a per-resource created/updated tally:

```json
{
  "daily_logs": { "created": 1, "updated": 0 },
  "applications": { "created": 0, "updated": 2 }
}
```

### Idempotency — natural keys

| Resource | Natural key | Notes |
|---|---|---|
| `daily_logs` | `log_date` | |
| `sleep_logs` | `log_date` | Prefer `/api/ingest/sleep/` for Shortcuts; use this for manual/batch entry. |
| `applications` | `(company, role)` | |
| `email_events` | `gmail_message_id` | |
| `practice_tests` | `(cert_code, taken_on)` | |
| `reflections` | `log_date` | Extension beyond the spec's four, same spirit — one reflection per day. |
| `loss_postmortems` | `(application, round_reached)` | Resolved via `application_company`/`application_role`. |
| `content_posts` | `url` when given | Falls back to `id`-based update, else always creates. |
| `milestones` | `title` | `id` takes priority when given (see below). `project_code`/`phase_no` only ever *set* the project/phase — they never narrow the lookup, so omitting them on an update can't detach an existing link. |
| `courses` | `name` | Matches a seeded `Course.name`; an unseen name creates a new row. |
| `skills` | `name` | Matches a seeded `Skill.name`; an unseen name creates a new row. |
| `study_sessions` | none | Always creates unless `id` is given. |
| `activity_samples` | none | Append-only; nothing writes here in v1. |

### Payload shapes and curl examples

#### `daily_logs`

```json
{
  "log_date": "2026-09-08",
  "deep_work_minutes": 145,
  "energy": 4,
  "steps_after_10": 6200,
  "gym": true,
  "last_caffeine_at": "15:30:00",
  "mood": "focused",
  "notes": "Good B1 block, slow start on B3"
}
```
`energy` (1-5) is the only required field beyond `log_date`.

```bash
curl -X POST "$BASE/api/ingest/" \
  -H "Authorization: Bearer $INGEST_TOKEN" -H "Content-Type: application/json" \
  -d '{"daily_logs": [{"log_date": "2026-09-08", "deep_work_minutes": 145, "energy": 4, "gym": true}]}'
```

#### `sleep_logs`

```json
{ "log_date": "2026-09-08", "bed_at": "2026-09-07T23:40:00+05:30", "wake_at": "2026-09-08T06:30:00+05:30", "source": "manual" }
```
`hours` is server-computed — do not send it (it's an unknown field → 400).

#### `study_sessions`

```json
{
  "session_date": "2026-09-08", "topic": "AI-103 D1 plan and manage",
  "category": "learn", "minutes": 60, "source": "microsoft-learn",
  "cert_domain_no": 1, "course_name": "Microsoft Learn AI-103 path"
}
```
`cert_domain_no` is an AI-103 domain number 1-5 (the only cert in v1).
`course_name` must exactly match a seeded `Course.name`. Both optional.
Pass `"id": 42` instead of `session_date`/`topic`/etc to correct a
previously-ingested row.

#### `applications`

```json
{
  "company": "Acme Corp", "role": "Backend Engineer", "source": "referral",
  "applied_on": "2026-09-10", "stage": "applied", "last_update": "2026-09-10",
  "contact": "Jane Doe", "company_domain": "acme.com"
}
```
`company_domain` (no `https://`, no path) is what the email auto-matcher
below compares against the sender's domain — set it so replies get
matched automatically.

```bash
curl -X POST "$BASE/api/ingest/" \
  -H "Authorization: Bearer $INGEST_TOKEN" -H "Content-Type: application/json" \
  -d '{"applications": [{"company": "Acme Corp", "role": "Backend Engineer", "source": "referral", "applied_on": "2026-09-10", "last_update": "2026-09-10", "company_domain": "acme.com"}]}'
```

#### `email_events`

```json
{
  "gmail_message_id": "18c2f1a9b3d4e5f6",
  "received_at": "2026-09-15T09:03:00Z",
  "from_address": "recruiting@acme.com",
  "subject": "Next steps on your application",
  "classified_as": "interview_invite"
}
```
Omit `application_company`/`application_role` to let the backend
auto-match by comparing the sender's domain to `Application.company_domain`
— an ambiguous or absent match stays `matched: false` (shows up in
`GET /api/email-queue/`), it is never guessed. Pass both explicitly when
your classification task already knows which application this is about:

```json
{ "...": "...", "application_company": "Acme Corp", "application_role": "Backend Engineer" }
```

#### `loss_postmortems`

```json
{
  "application_company": "Acme Corp", "application_role": "Backend Engineer",
  "round_reached": "tech", "cause": "system_design",
  "what_happened": "Froze on the load-balancing question", "logged_on": "2026-09-20"
}
```
`cause` is one of: `take_home, system_design, dsa, behavioral,
domain_knowledge, communication, culture_fit, comp_mismatch,
ghosted_by_them, other`.

#### `content_posts`

```json
{
  "platform": "linkedin", "title": "Shipped the eval harness ablation study",
  "url": "https://linkedin.com/posts/...", "posted_on": "2026-10-01",
  "impressions": 340, "reactions": 12, "comments": 3,
  "milestone_title": "Ablation: HyDE on/off"
}
```

#### `practice_tests`

```json
{ "cert_code": "AI-103", "taken_on": "2026-09-28", "score": 680, "max_score": 1000, "per_domain": {"1": 0.7, "2": 0.6} }
```

```bash
curl -X POST "$BASE/api/ingest/" \
  -H "Authorization: Bearer $INGEST_TOKEN" -H "Content-Type: application/json" \
  -d '{"practice_tests": [{"cert_code": "AI-103", "taken_on": "2026-09-28", "score": 680}]}'
```

#### `milestones`

```json
{ "title": "Golden dataset", "project_code": "A", "status": "done", "evidence_url": "https://github.com/you/case-intel/commit/abc123" }
```
**Marking `status: "done"` without `evidence_url` is a 400** — enforced in
the model layer (`Milestone.clean()`), not just here. Omitting
`project_code` on an update does **not** detach an existing project link.
Pass `"id": 17` to update by primary key instead (get ids from
`GET /api/today/`'s `open_milestones`).

#### `reflections`

```json
{ "log_date": "2026-09-08", "went_well": "Shipped the metric runner", "blocked_by": "Langfuse auth", "one_thing_tomorrow": "Wire up tracing" }
```

#### `activity_samples`

```json
{ "block_entry_id": 142, "started_at": "2026-09-08T09:03:00Z", "ended_at": "2026-09-08T09:18:00Z", "app": "Chrome", "window_title": "Stack Overflow", "category": "distraction", "active_seconds": 620 }
```
Nothing writes here in v1 — the model and endpoint exist for the future
activity-tracking agent. `block_entry_id` is optional.

#### `courses`

```json
{ "name": "Claude 101 and Claude Code", "progress_pct": 100, "active": true }
```
Upsert on `name` — it must match a seeded `Course.name` exactly (the seed
list is in [`core/migrations/0002_seed_program.py`](../core/migrations/0002_seed_program.py);
note "Claude 101 and Claude Code" is one combined row). An unseen name
creates a new course (its `provider`/`credential_type` stay blank — this
payload doesn't carry them). `progress_pct` is 0-100; `active` (default
`true`) parks a course when `false`. Both optional — send only what moved.

```bash
curl -X POST "$BASE/api/ingest/" \
  -H "Authorization: Bearer $INGEST_TOKEN" -H "Content-Type: application/json" \
  -d '{"courses": [{"name": "Claude 101 and Claude Code", "progress_pct": 100}]}'
```

#### `skills`

```json
{ "name": "RAG and retrieval", "level": 55, "target": 80 }
```
Upsert on `name` (must match a seeded `Skill.name`; an unseen name creates
a new row). `level` (0-100) is what changes over time; `target` (0-100) is
a fixed goal and rarely moves, but is accepted for the case it does. Both
optional.

```bash
curl -X POST "$BASE/api/ingest/" \
  -H "Authorization: Bearer $INGEST_TOKEN" -H "Content-Type: application/json" \
  -d '{"skills": [{"name": "RAG and retrieval", "level": 55}]}'
```

---

## POST /api/ingest/sleep/

The tiny endpoint for iPhone Shortcuts (see [SHORTCUTS.md](SHORTCUTS.md)).

```json
{ "event": "bed", "at": "2026-09-08T00:47:00+05:30" }
```

`event` is `"bed"` or `"wake"`. Day attribution: a sleep event's **local**
time-of-day before noon belongs to the *previous* calendar day's
`SleepLog` — this is what correctly puts a post-midnight bedtime (e.g.
00:47) and the following morning's wake (e.g. 06:30) on the **same** row.
`source` is always set to `"shortcut"`.

```bash
curl -X POST "$BASE/api/ingest/sleep/" \
  -H "Authorization: Bearer $INGEST_TOKEN" -H "Content-Type: application/json" \
  -d '{"event": "bed", "at": "2026-09-08T00:47:00+05:30"}'

curl -X POST "$BASE/api/ingest/sleep/" \
  -H "Authorization: Bearer $INGEST_TOKEN" -H "Content-Type: application/json" \
  -d '{"event": "wake", "at": "2026-09-08T06:30:00+05:30"}'
```

---

## GET /api/today/

Machine token or your own user token. Handles the pre-2026-09-07 state:

```json
{ "status": "pre_start", "today": "2026-09-05", "program_start": "2026-09-07", "days_to_start": 2, "countdowns": [ "..." ] }
```

Once the program has started:

```json
{
  "status": "active", "today": "2026-09-08",
  "daily_log": { "...": "..." },
  "blocks": [ { "code": "B1", "label": "BUILD", "completed": false, "started_at": null, "elapsed_minutes": null } ],
  "streak": 3,
  "open_milestones": [ "..." ],
  "shippable_milestones": [ "..." ],
  "decay_alerts": { "decay_days": 14, "projects": [], "cert_domains": [], "applications": [] },
  "unmatched_email_count": 2,
  "countdowns": [ "..." ]
}
```

```bash
curl "$BASE/api/today/" -H "Authorization: Bearer $INGEST_TOKEN"
```

## GET /api/email-queue/

Unmatched `EmailEvent` rows — the 22:00 task's review queue. Machine token
or your own user token.

```bash
curl "$BASE/api/email-queue/" -H "Authorization: Bearer $INGEST_TOKEN"
```

---

## Read endpoints (your own user token only)

Everything below is **your login token** (`Authorization: Token <key>`),
never `INGEST_TOKEN` — these are for a frontend/dashboard reading your own
data, not the machine ingest path.

| Endpoint | Filters | Ordering |
|---|---|---|
| `GET /api/applications/` | `?stage=`, `?source=` | `last_update` (default, newest first), `applied_on`, `company` |
| `GET /api/milestones/` | `?status=`, `?project=` (project **code**, e.g. `A`) | `due_date` (default), `title` |
| `GET /api/sleep-logs/` | `?log_date__gte=`, `?log_date__lte=` | `log_date` (default, newest first) |
| `GET /api/daily-logs/` | `?log_date__gte=`, `?log_date__lte=` | `log_date` (default, newest first) |
| `GET /api/skills/` | — | `name`, `level` |
| `GET /api/courses/` | — | `name`, `progress_pct` |
| `GET /api/cert-domains/` | — | `domain_no`, `mastery_pct` |
| `GET /api/content-posts/` | — | `posted_on` (default, newest first) |
| `GET /api/reflections/` | `?log_date__gte=`, `?log_date__lte=` | `log_date` (default, newest first) |
| `GET /api/notion-tasks/` | `?status=` | `due_date`, `notion_last_edited` |

Every list is paginated (`{"count", "next", "previous", "results"}`, 50 per
page) and scoped to you — a row someone else owns, or that has no owner at
all (shared program scaffolding), is included; another user's row never
shows up. Sort ascending/descending with `?ordering=field` /
`?ordering=-field`.

```bash
curl "$BASE/api/applications/?stage=offer" -H "Authorization: Token $USER_TOKEN"
curl "$BASE/api/daily-logs/?log_date__gte=2026-09-01&log_date__lte=2026-09-30" \
  -H "Authorization: Token $USER_TOKEN"
```

**`PATCH /api/countdowns/<id>/`** — `{"target_date": "2026-11-15"}` (or
`null` to go back to TBD). Rejected with `400` if that countdown's
`editable` flag is `false` (the program-end date, for one, is fixed).

**`PATCH /api/block-entries/<id>/`** — undo a completion. Empty body
(`{}`); any other key is a 400. Sets `completed` back to `false` and clears
`ended_at`/`elapsed_minutes`, but leaves `started_at` alone — the block goes
back to "in progress", not "never started". Safe to call twice.

```bash
curl -X PATCH "$BASE/api/countdowns/2/" -H "Authorization: Token $USER_TOKEN" \
  -H "Content-Type: application/json" -d '{"target_date": "2026-11-15"}'

curl -X PATCH "$BASE/api/block-entries/17/" -H "Authorization: Token $USER_TOKEN" \
  -H "Content-Type: application/json" -d '{}'
```

**`GET /api/schema/`** — the full OpenAPI schema (public, no auth needed —
field/endpoint shape only, no user data), for generating real frontend
types instead of hand-writing them. This is the canonical reference for
exact field names/types on every endpoint above; this doc gives shapes and
curl examples, not an exhaustive field list.

Notion sync (`POST /api/sync/notion/`, machine token) is documented
separately in [`NOTION_SYNC.md`](NOTION_SYNC.md).
