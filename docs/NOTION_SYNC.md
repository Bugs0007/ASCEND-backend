# Notion "Daily Board" sync

Read-only mirror of your Notion task-list database into `NotionTask` rows,
via `POST /api/sync/notion/`. This backend never writes back to Notion —
only reads.

## 1. Create a Notion internal integration

1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations) →
   **New integration**.
2. Give it any name (e.g. "ASCEND sync"), pick your workspace, and choose
   **Internal integration**. Capabilities: **Read content** only — this
   integration never needs to write, insert, or update anything.
3. Submit, then copy the **Internal Integration Secret** (starts with
   `secret_` or `ntn_` depending on when your workspace was created). This
   is your `NOTION_TOKEN`.

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
