# iPhone Shortcuts — sleep tracking

Two automations, both hitting the same tiny endpoint:
`POST /api/ingest/sleep/`. This is the endpoint the backend prompt asked
for specifically *because* full JSON is painful to build in the Shortcuts
app — each of these is a 4-step automation.

Both use the **machine token** (`INGEST_TOKEN`), not your own login.

---

## Shortcut 1 — "Sleep Focus turns on" → bed event

**Automation → Create Personal Automation → Focus → Sleep → When Turned On.**
Turn off "Ask Before Running" once it's working, so it fires silently.

Add these actions:

1. **Current Date** — gives you `at`.
2. **Format Date** — set the format to ISO 8601 (`Custom Format`:
   `yyyy-MM-dd'T'HH:mm:ssXXXXX` reproduces `2026-09-08T00:47:00+05:30`).
3. **Text** — build the JSON body:
   ```
   {"event": "bed", "at": "[Formatted Date]"}
   ```
   (Replace `[Formatted Date]` with the magic-variable output of step 2.)
4. **Get Contents of URL**:
   - URL: `https://<your-render-url>/api/ingest/sleep/`
   - Method: `POST`
   - Headers: `Authorization` = `Bearer <your INGEST_TOKEN>`,
     `Content-Type` = `application/json`
   - Request Body: `Text` (the JSON from step 3)

That's the whole automation. A bed time in the small hours after midnight
is automatically attributed to the previous calendar day's row — see
[INGEST_API.md](INGEST_API.md#post-apiingestsleep) — so you don't need to
do anything special for a late night.

---

## Shortcut 2 — "Sleep Focus turns off" (or alarm stopped) → wake event

**Automation → Focus → Sleep → When Turned Off.** If you'd rather trigger
on the alarm itself, use **Automation → Time of Day** set a few minutes
after your usual alarm instead, or **App → Clock → Alarm stopped** if your
iOS version exposes that trigger.

Identical to Shortcut 1, except step 3's body is:
```
{"event": "wake", "at": "[Formatted Date]"}
```

---

## Testing it

Run each Shortcut manually once (tap it in the Shortcuts app rather than
waiting for the trigger) and confirm with:

```bash
curl "https://<your-render-url>/api/today/" -H "Authorization: Bearer <INGEST_TOKEN>"
```

or query the row directly via `/admin/` (Django admin, your own login) —
`core > Sleep logs`. A successful call returns the row's computed `hours`
once both `bed_at` and `wake_at` are set:

```json
{ "log_date": "2026-09-07", "created": false, "bed_at": "...", "wake_at": "...", "hours": 6.22 }
```
