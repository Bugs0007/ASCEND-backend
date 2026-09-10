# Claude scheduled task payloads

Paste these directly into the prompts of your two scheduled Claude tasks.
Both use the machine token — never your own login token.

```
BASE = <your live Render URL>
INGEST_TOKEN = <from your Render environment variables>
```

## Standing instruction — course and skill progress

When a check-in mentions **finishing a course** or **getting noticeably
better at a skill**, fold it into the same `/api/ingest/` call as a
`courses` or `skills` write — don't wait to be asked, and don't raise it
as a separate question.

- Only write a number that was actually stated. "Finished Claude 101" is
  `{"progress_pct": 100}`. "Halfway through the LangGraph course" is
  `{"progress_pct": 50}`. A vague "made some progress" or "feeling more
  confident on RAG" with no number is **not** a write — leave it.
- `name` must match a seeded course/skill exactly (the lists are in
  [`core/migrations/0002_seed_program.py`](../core/migrations/0002_seed_program.py),
  courses as corrected by
  [`0004_correct_course_data.py`](../core/migrations/0004_correct_course_data.py)
  — e.g. it's "Claude 101" and "Claude Code 101", two separate rows).
  An unmatched name creates a *new* row, so a typo silently makes a
  duplicate — copy the name, don't retype it.
- `level` for skills is 0-100. Same rule: only a stated number, never an
  estimate.

---

## 10:00 task — plan the day

**Step 1: read state before planning anything.**

```bash
curl -s "$BASE/api/today/" -H "Authorization: Bearer $INGEST_TOKEN"
```

Use the response to plan: `status` (handle `pre_start` before day one —
just report the countdown and stop), `streak`, `today_selections` (the
day's task list — empty at 10:00 until the user runs "Start the day";
`deep_work_total` is the computed minutes so far),
`open_milestones` and `shippable_milestones` (anything postable today?),
`decay_alerts` (projects/cert domains/applications gone quiet for 14+
days — nudge on these), `unmatched_email_count` (if > 0, mention the
review queue is waiting), and `countdowns` (AI-103 exam, program end, AWS
credit runway).

**Step 2: push the day's recommendations.** Read the candidate pool, then
POST 2-4 suggestions for the user to pick from in the "Plan" view.

```bash
# The pool: open ASCEND backlog items + open Notion Daily Board rows.
curl -s "$BASE/api/today/pool/" -H "Authorization: Bearer $INGEST_TOKEN"

# Replace today's recommendation set (bare array, idempotent to re-run).
curl -X POST "$BASE/api/today/recommendations/" \
  -H "Authorization: Bearer $INGEST_TOKEN" -H "Content-Type: application/json" \
  -d '[
    { "title": "Faithfulness metric — first pass", "rationale": "Unblocks the week-2 runner", "source_project": "case-intel" },
    { "title": "AI-103 D2: function calling module", "rationale": "Weakest sub-topic on practice test 1", "source_project": "ai-103" }
  ]'
```

`source_project` is `case-intel` / `ai-103` / `other`. The user checks off
what they want in the app; ASCEND creates the `TodaySelection` rows — this
task never writes selections directly.

**Optionally** seed the backlog itself (ASCEND-native candidate work, so it
shows in the pool):

```bash
curl -X POST "$BASE/api/ingest/" \
  -H "Authorization: Bearer $INGEST_TOKEN" -H "Content-Type: application/json" \
  -d '{ "backlog_items": [ { "title": "Wire the CI regression gate", "source_project": "case-intel" } ] }'
```

**Step 3 (optional): log a plan-time reflection or adjust a milestone.**

```bash
curl -X POST "$BASE/api/ingest/" \
  -H "Authorization: Bearer $INGEST_TOKEN" -H "Content-Type: application/json" \
  -d '{
    "reflections": [
      { "log_date": "2026-09-08", "one_thing_tomorrow": "Ship the ablation CI gate" }
    ]
  }'
```

---

## 22:00 task — Gmail sweep, close out the day, log postmortems

**Step 1: sweep Gmail for anything relevant since the last run**, classify
each message, and match it to an application by company/domain if you
already know which one it is (otherwise let the backend auto-match on
`company_domain` — never guess).

```bash
curl -X POST "$BASE/api/ingest/" \
  -H "Authorization: Bearer $INGEST_TOKEN" -H "Content-Type: application/json" \
  -d '{
    "email_events": [
      {
        "gmail_message_id": "18c2f1a9b3d4e5f6",
        "received_at": "2026-09-15T09:03:00Z",
        "from_address": "recruiting@acme.com",
        "subject": "Next steps on your application",
        "classified_as": "interview_invite"
      },
      {
        "gmail_message_id": "18c2f2b0c4e5f6a7",
        "received_at": "2026-09-15T14:20:00Z",
        "from_address": "noreply@lever.co",
        "subject": "Thank you for your interest",
        "classified_as": "rejection",
        "application_company": "Beta Inc",
        "application_role": "ML Engineer"
      }
    ]
  }'
```

Re-running this with the same `gmail_message_id`s is safe — it's
idempotent, so a sweep that re-scans the last 3 days of mail on every run
never double-counts.

**Step 2: if a rejection closes out an application you had a real round
for, log the postmortem** (cause and what happened — this feeds
`/api/analytics/losses/`):

```bash
curl -X POST "$BASE/api/ingest/" \
  -H "Authorization: Bearer $INGEST_TOKEN" -H "Content-Type: application/json" \
  -d '{
    "applications": [
      { "company": "Beta Inc", "role": "ML Engineer", "source": "portal", "applied_on": "2026-08-20", "stage": "rejected", "last_update": "2026-09-15" }
    ],
    "loss_postmortems": [
      { "application_company": "Beta Inc", "application_role": "ML Engineer", "round_reached": "tech", "cause": "system_design", "what_happened": "Froze on the load-balancing question", "logged_on": "2026-09-15" }
    ]
  }'
```

**Step 3: close out the day's log** — deep work, energy, steps, gym,
caffeine, mood, notes, plus the reflection:

```bash
curl -X POST "$BASE/api/ingest/" \
  -H "Authorization: Bearer $INGEST_TOKEN" -H "Content-Type: application/json" \
  -d '{
    "daily_logs": [
      { "log_date": "2026-09-15", "deep_work_minutes": 165, "energy": 4, "steps_after_10": 6400, "gym": true, "last_caffeine_at": "15:00:00", "mood": "tired but good", "notes": "Ablation study done, CI gate up next" }
    ],
    "reflections": [
      { "log_date": "2026-09-15", "went_well": "Ablation study landed clean numbers", "blocked_by": "Langfuse dashboard auth", "one_thing_tomorrow": "CI regression gate" }
    ]
  }'
```

**Step 4: course / skill progress** — if the check-in surfaced any (see
the standing instruction above), write it in the same style. Only send
fields that actually moved:

```bash
curl -X POST "$BASE/api/ingest/" \
  -H "Authorization: Bearer $INGEST_TOKEN" -H "Content-Type: application/json" \
  -d '{
    "courses": [
      { "name": "Claude 101", "progress_pct": 100 }
    ],
    "skills": [
      { "name": "RAG and retrieval", "level": 55 }
    ]
  }'
```

Response: `{"courses": {"created": 0, "updated": 1}, "skills": {"created": 0, "updated": 1}}`.
Re-running with the same values is a harmless no-op (idempotent on `name`).

**Step 5: check the review queue** and ask about anything still
unmatched:

```bash
curl -s "$BASE/api/email-queue/" -H "Authorization: Bearer $INGEST_TOKEN"
```

For each unmatched row, ask which application it belongs to (or that it's
noise), then re-POST it to `email_events` with the resolved
`application_company`/`application_role` — the same `gmail_message_id`
updates the existing row rather than duplicating it.
