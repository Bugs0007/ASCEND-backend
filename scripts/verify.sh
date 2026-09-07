#!/usr/bin/env bash
# Walks every ASCEND endpoint against a live deployment and asserts status
# codes. This is the finish line for a deploy — it must pass against the
# real Render URL, not localhost, before the backend is considered done.
#
# Usage: ./scripts/verify.sh <base-url> <user-token> <ingest-token>
# Example:
#   ./scripts/verify.sh https://ascend-backend.onrender.com abc123... xyz789...
set -euo pipefail

BASE="${1:?Usage: verify.sh <base-url> <user-token> <ingest-token>}"
USER_TOKEN="${2:?Usage: verify.sh <base-url> <user-token> <ingest-token>}"
INGEST_TOKEN="${3:?Usage: verify.sh <base-url> <user-token> <ingest-token>}"

BASE="${BASE%/}"
PASS=0
FAIL=0

check() {
  local desc="$1" expected="$2" method="$3" path="$4" auth="$5" body="${6:-}"
  local auth_header=()
  case "$auth" in
    user)   auth_header=(-H "Authorization: Token $USER_TOKEN") ;;
    ingest) auth_header=(-H "Authorization: Bearer $INGEST_TOKEN") ;;
    none)   auth_header=() ;;
  esac

  local body_file
  body_file=$(mktemp)
  local args=(-s -o "$body_file" -w "%{http_code}" -X "$method" "$BASE$path" "${auth_header[@]}")
  if [ -n "$body" ]; then
    args+=(-H "Content-Type: application/json" -d "$body")
  fi

  local code
  code=$(curl "${args[@]}")
  if [ "$code" = "$expected" ]; then
    echo "  OK   [$code] $desc"
    PASS=$((PASS + 1))
  else
    echo "  FAIL [$code, expected $expected] $desc"
    echo "       body: $(head -c 300 "$body_file" 2>/dev/null)"
    FAIL=$((FAIL + 1))
  fi
  rm -f "$body_file"
}

echo "== ASCEND backend verification against $BASE =="
echo

echo "-- Health --"
check "GET /api/health/ (no auth)" 200 GET "/api/health/" none

echo
echo "-- Auth separation --"
check "GET /api/analytics/funnel/ with no token -> 401" 401 GET "/api/analytics/funnel/" none
check "POST /api/ingest/ with user token -> 401" 401 POST "/api/ingest/" user '{"daily_logs": []}'

echo
echo "-- Ingest idempotency (same payload twice) --"
DAILY_LOG_PAYLOAD='{"daily_logs": [{"log_date": "2026-09-07", "deep_work_minutes": 120, "energy": 4}]}'
check "POST /api/ingest/ first daily_log" 200 POST "/api/ingest/" ingest "$DAILY_LOG_PAYLOAD"
check "POST /api/ingest/ same daily_log again" 200 POST "/api/ingest/" ingest "$DAILY_LOG_PAYLOAD"

echo
echo "-- Unknown field rejection --"
check "POST /api/ingest/ with unknown field -> 400" 400 POST "/api/ingest/" ingest \
  '{"daily_logs": [{"log_date": "2026-09-07", "energy": 4, "not_a_real_field": 1}]}'

echo
echo "-- Courses / skills ingest --"
# Deliberately throwaway names so this smoke test never mutates a real
# seeded course/skill (an unseen name creates a new row).
COURSE_PAYLOAD='{"courses": [{"name": "__verify smoke test course__", "progress_pct": 50}]}'
check "POST /api/ingest/ course upsert" 200 POST "/api/ingest/" ingest "$COURSE_PAYLOAD"
check "POST /api/ingest/ same course again (idempotent)" 200 POST "/api/ingest/" ingest "$COURSE_PAYLOAD"
check "POST /api/ingest/ skill upsert" 200 POST "/api/ingest/" ingest \
  '{"skills": [{"name": "__verify smoke test skill__", "level": 50}]}'
check "POST /api/ingest/ course with unknown field -> 400" 400 POST "/api/ingest/" ingest \
  '{"courses": [{"name": "__verify smoke test course__", "provider": "nope"}]}'

echo
echo "-- Ingest sleep shortcut --"
check "POST /api/ingest/sleep/ bed event" 200 POST "/api/ingest/sleep/" ingest \
  '{"event": "bed", "at": "2026-09-08T00:47:00+05:30"}'

echo
echo "-- Read endpoints --"
check "GET /api/today/ (ingest token)" 200 GET "/api/today/" ingest
check "GET /api/today/ (user token)" 200 GET "/api/today/" user
check "GET /api/email-queue/ (ingest token)" 200 GET "/api/email-queue/" ingest

echo
echo "-- Analytics (user token only) --"
for path in rhythm correlations funnel losses burnup certtrend decay activity observations; do
  check "GET /api/analytics/$path/" 200 GET "/api/analytics/$path/" user
  check "GET /api/analytics/$path/ with ingest token -> 401" 401 GET "/api/analytics/$path/" ingest
done

echo
echo "-- New read endpoints (user token only) --"
for path in applications milestones sleep-logs daily-logs skills courses cert-domains content-posts reflections notion-tasks; do
  check "GET /api/$path/ with no token -> 401" 401 GET "/api/$path/" none
  check "GET /api/$path/" 200 GET "/api/$path/" user
  check "GET /api/$path/ with ingest token -> 401" 401 GET "/api/$path/" ingest
done

echo
echo "-- OpenAPI schema (public) --"
check "GET /api/schema/ (no auth)" 200 GET "/api/schema/" none

echo
echo "-- Countdown PATCH --"
# Ids below match this deployment's seed migration insertion order
# (AI-103 exam=1, editable; Program end=2, not editable) — adjust if this
# is ever run against a database seeded differently.
check "PATCH /api/countdowns/1/ (editable) -> 200" 200 PATCH "/api/countdowns/1/" user '{"target_date": "2026-11-15"}'
check "PATCH /api/countdowns/2/ (Program end, not editable) -> 400" 400 PATCH "/api/countdowns/2/" user '{"target_date": "2026-01-01"}'

echo
echo "-- BlockEntry undo round-trip --"
curl -s -X POST "$BASE/api/blocks/B1/start/" -H "Authorization: Token $USER_TOKEN" >/dev/null
COMPLETE_BODY=$(curl -s -X POST "$BASE/api/blocks/B1/complete/" -H "Authorization: Token $USER_TOKEN")
ENTRY_ID=$(echo "$COMPLETE_BODY" | grep -o '"id":[0-9]*' | head -1 | grep -o '[0-9]*')
if [ -n "$ENTRY_ID" ]; then
  check "PATCH /api/block-entries/$ENTRY_ID/ (undo) -> 200" 200 PATCH "/api/block-entries/$ENTRY_ID/" user '{}'
else
  echo "  FAIL [no id] could not extract BlockEntry id from complete response: $COMPLETE_BODY"
  FAIL=$((FAIL + 1))
fi

echo
echo "-- Notion sync (machine token) --"
echo "   Run this once BEFORE setting NOTION_TOKEN/NOTION_DAILY_BOARD_DB_ID,"
echo "   and again AFTER — see docs/NOTION_SYNC.md for the full walkthrough."
SYNC_CODE=$(curl -s -o /tmp/notion_sync_body -w "%{http_code}" -X POST "$BASE/api/sync/notion/" -H "Authorization: Bearer $INGEST_TOKEN")
if [ "$SYNC_CODE" = "503" ]; then
  echo "  OK   [503] POST /api/sync/notion/ — not configured yet (expected before NOTION_TOKEN is set)"
  PASS=$((PASS + 1))
elif [ "$SYNC_CODE" = "200" ]; then
  echo "  OK   [200] POST /api/sync/notion/ — $(cat /tmp/notion_sync_body)"
  PASS=$((PASS + 1))
else
  echo "  FAIL [$SYNC_CODE] POST /api/sync/notion/ — $(cat /tmp/notion_sync_body)"
  FAIL=$((FAIL + 1))
fi
rm -f /tmp/notion_sync_body

echo
echo "== $PASS passed, $FAIL failed =="
[ "$FAIL" -eq 0 ]
