# Handoff: Today planning — flexible task list replaces the five blocks

What changed in the backend, and what the frontend / scheduled tasks do with it.

## The shape change

A day's work was five fixed `BlockEntry` rows (one per seeded `Block`,
BUILD/LEARN/APPLY/SHARPEN/FLEX). It's now **`TodaySelection`** — an ordered
list of any length, each row pointing back at where it came from.

`Block` / `BlockEntry` and their endpoints (`/api/blocks/<code>/start|complete/`,
`PATCH /api/block-entries/<id>/`) **still exist and still work** — they're just
not what `/api/today/` or the frontend use any more. `/api/analytics/rhythm/`
still reads `BlockEntry`, so it quietly flat-lines rather than breaking.

## New models

| Model | Purpose | Written by |
|---|---|---|
| `BacklogItem` | ASCEND-native candidate work (project/cert tasks not on the Notion board). `title`, `source_project` (`case-intel`/`ai-103`/`other`), `status` (`pending`/`done`). | `POST /api/ingest/` → `backlog_items` (upsert on `title`) |
| `DailyRecommendation` | One suggested task for one `date`, with a short `rationale` + `source_project`. ASCEND stores, never generates. | `POST /api/today/recommendations/` (replace-for-date) |
| `TodaySelection` | One committed task for a `date`: `source_type` (`backlog`/`notion`/`recommendation`/`adhoc`), `source_id` (local pk, null for adhoc), denormalised `title`, optional `block` tag, `minutes_spent`, `done`, `position`. | `POST /api/today/selections/` (append) |

## `/api/today/` response — changed

- `blocks: [...]` is **gone**.
- `today_selections: [...]` — the day's list, ordered by `position`.
- `deep_work_total: <int>` — computed sum of `today_selections[].minutes_spent`.

`streak` is unchanged in shape but redefined: a day is green when
`done >= ceil(planned * 2/3)` of its `TodaySelection` rows (min one planned),
replacing "4 of 5 blocks" (`GREEN_DAY_DONE_NUMERATOR`/`_DENOMINATOR` in
`core/constants.py`). The ~3 days of pre-existing `BlockEntry` data are not
migrated — those days read as non-green now.

## `deep_work_minutes` — deprecated, not removed

`DailyLog.deep_work_minutes` (the single day-level quick-log field) stays: the
column is still there and `POST /api/ingest/` `daily_logs` still accepts it
(the 22:00 task keeps working). But the **computed** `deep_work_total` is what
the API now surfaces for display:

- `/api/today/` — top-level `deep_work_total`.
- `/api/daily-logs/` — each row gains a `deep_work_total` field (annotation).

`correlations` / `observations` analytics still read the `deep_work_minutes`
column for now — switch them to the computed total when the column is retired
for good.

## New endpoints

| Endpoint | Auth | Notes |
|---|---|---|
| `GET /api/today/pool/` | user **or** ingest | pending `BacklogItem` + open (not done-like) `NotionTask`, each tagged `source` |
| `GET /api/today/recommendations/?date=` | user **or** ingest | `date` defaults to today |
| `POST /api/today/recommendations/` | user **or** ingest | bare array of `{title, rationale, source_project}`; **replaces** today's set |
| `GET /api/today/selections/?date=` | user only | the day's list, ordered |
| `POST /api/today/selections/` | user only | bare array of `{source_type, source_id, title}`; **appends**; non-adhoc rows deduped on `(date, source_type, source_id)` |
| `PATCH /api/today/selections/<id>/` | user only | `{minutes_spent?, done?}`; any other key → 400 |
| `DELETE /api/today/selections/<id>/` | user only | remove a mis-added row |

Full payload examples: [`INGEST_API.md`](INGEST_API.md) "Today planning" section.
Scheduled-task usage: [`CLAUDE_TASK_PAYLOADS.md`](CLAUDE_TASK_PAYLOADS.md) (the
10:00 "plan the day" task now pushes recommendations).

## Migration

`0007_backlogitem_dailyrecommendation_todayselection.py` — three `CreateModel`s,
no data migration, no change to any existing table. Applied to the pytest
`test_` DB on the test run; production applies it on the Render deploy.
