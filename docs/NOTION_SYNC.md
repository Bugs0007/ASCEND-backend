# Notion "Daily Board" sync

Two-way link between your Notion task-list database and `NotionTask` rows:

- **Pull** (`POST /api/sync/notion/`, machine token, on a cron) mirrors the
  whole board into `NotionTask` — title, status, category, due date.
- **Push** (`PATCH /api/notion-tasks/<id>/`, your user token, UI-triggered)
  writes a single task's **status** back to its Notion page and updates the
  local row in the same request.

Everything except status is a one-directional mirror — this backend never
rewrites a task's title, category or date in Notion.

## 1. Create a Notion internal integration

1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations) →
   **New integration**.
2. Give it any name (e.g. "ASCEND sync"), pick your workspace, and choose
   **Internal integration**. Capabilities: **Read content** *and* **Update
   content**. Read alone is enough for the pull sync; the status write-back
   (`PATCH /api/notion-tasks/<id>/`) needs **Update content** as well, or
   every write-back call fails with Notion's `403` (surfaced here as a
   `502`). It still never needs Insert content.
3. Submit, then copy the **Internal Integration Secret** (starts with
   `secret_` or `ntn_` depending on when your workspace was created). This
   is your `NOTION_TOKEN`.

   > Already had this integration set up as **Read content** only? Open it
   > at [notion.so/my-integrations](https://www.notion.so/my-integrations),
   > add **Update content** under Capabilities, and save. No token change,
   > no re-share needed.

## 2. Share the Daily Board page with the integration

**This is the step people forget.** A brand-new integration has access to
*nothing* until you explicitly share a page with it — the token alone
doesn't grant access, even to your own workspace's content.

1. Open your Daily Board database in Notion.
2. Click **`•••`** (top right) → **Connections** (or **Add connections** in
   older Notion UIs) → find and select your integration by name.
3. Confirm. Without this step, every sync call fails with a `404` from
   Notion's own API (not `403` — Notion deliberately doesn't reveal whether
   a database exists to an integration it hasn't been shared with), which
   this backend surfaces as a `502` from `/api/sync/notion/`. If your very
   first sync call 502s, this is the first thing to check.

## 3. Set `NOTION_TOKEN` on Render

Render dashboard → your service → **Environment** tab → add:

```
NOTION_TOKEN=<the secret you copied in step 1>
```

`NOTION_DAILY_BOARD_DB_ID` already defaults to your Daily Board's id
(`94fb5ba274ab499b8ae23e652774be2a`) in code — you only need to add it as an
env var if you ever point this at a different Notion database.

Saving triggers a redeploy. Until `NOTION_TOKEN` is set, `POST
/api/sync/notion/` returns a clean `503` (not a crash — the rest of the app
keeps working normally either way).

## 4. Test it once by hand

```bash
curl -X POST https://<your-service>.onrender.com/api/sync/notion/ \
  -H "Authorization: Bearer <your INGEST_TOKEN>"
```

Expect something like:

```json
{
  "created": 12,
  "updated": 0,
  "unchanged": 0,
  "matched_properties": {
    "title": "Name",
    "status": "Status",
    "date": "Date",
    "category": "Project"
  }
}
```

`matched_properties` names the actual Notion property this sync mapped to
each of our fields — worth a glance on the first run to confirm it read
your board's actual layout correctly (schema detection is dynamic, never
hardcoded to a specific property name — see `core/notion_sync.py`). Run the
exact same call again immediately after; a healthy second run reports
`"unchanged"` equal to your row count, `"created": 0` — that's the
idempotency check.

## 5. Point a cron-job.org job at it

Same free account as the `/api/health/` keep-warm job (docs/SETUP.md).

- **URL:** `https://<your-service>.onrender.com/api/sync/notion/`
- **Method:** POST
- **Header:** `Authorization: Bearer <your INGEST_TOKEN>`
- **Interval: every 20 minutes.** Notion's API rate limit averages roughly
  3 requests/second, and one sync run of a personal task board is 1–2
  requests (one schema fetch, one or two paginated query calls) — 20
  minutes is comfortably inside that limit with room to spare, while still
  keeping the mirror reasonably fresh for a list you edit throughout the
  day. If you'd rather have more headroom and don't mind slightly staler
  data, 30 minutes is the more conservative choice — either is safe. Don't
  go tighter than 15 minutes.

## Reading the result

- `GET /api/notion-tasks/` (your own DRF token, not `INGEST_TOKEN`) lists
  the synced rows — same auth pattern, owner-scoping and filter/ordering
  support as the other new read endpoints (`docs/INGEST_API.md`).
- `status`/`category` reflect whatever your board's actual Status/Project
  (or similarly-typed) properties are — if your board doesn't have one of
  these, that field stays blank/null for every row rather than the sync
  failing.
- `due_date` only stores the calendar date — if your board's date property
  carries a time-of-day, it's discarded (this app's `DailyLog`/`SleepLog`
  etc. all reason in whole calendar days too).
- `notion_last_edited` moves on *any* edit to the page; `synced_at` moves on
  *every* sync. `status_changed_at` moves only when the `status` value
  actually changes (via a sync that sees a new value, or the write-back
  endpoint) — it's what a "this task has sat in its column for N hours" rule
  should count from. It's `null` for rows that existed before the field was
  added; they get a real value the next time their status changes.

## Writing a status back — `PATCH /api/notion-tasks/<id>/`

Your **own DRF token** (`Authorization: Token <key>`), not `INGEST_TOKEN` —
this is a UI action from the board page, not the machine ingest path.

```bash
curl -X PATCH "$BASE/api/notion-tasks/42/" \
  -H "Authorization: Token $USER_TOKEN" -H "Content-Type: application/json" \
  -d '{"status": "In Progress"}'
```

Body is exactly one field, `status`; any other key is a `400`. What happens:

1. The new status is validated against the **live** options Notion reports
   for the board's status property (`GET /v1/databases/{id}`, the same call
   the pull sync makes). A value that isn't a real option on the board is a
   `400` — an arbitrary string is never written into Notion.
2. The backend detects whether that property is a native **status** type or
   a **select** type and builds the matching Notion payload
   (`{"status": {"name": …}}` vs `{"select": {"name": …}}`).
3. It `PATCH`es `https://api.notion.com/v1/pages/{notion_page_id}` with that
   payload.
4. On success, the local `NotionTask` row is updated immediately — new
   `status`, and `status_changed_at` / `synced_at` set to now — so the
   change shows without waiting for the next cron sync. The response is the
   updated row (same shape as `GET /api/notion-tasks/`).
5. On a Notion API failure the call returns `502` with the error and the
   local row is left untouched — it never silently no-ops.

Requires the integration's **Update content** capability (see step 1). A
`502` mentioning `403` / `restricted` on an otherwise-healthy setup almost
always means that capability is still missing.
