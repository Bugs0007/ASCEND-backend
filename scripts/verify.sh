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
echo "== $PASS passed, $FAIL failed =="
[ "$FAIL" -eq 0 ]
