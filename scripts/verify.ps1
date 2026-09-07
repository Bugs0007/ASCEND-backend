# Walks every ASCEND endpoint against a live deployment and asserts status
# codes. This is the finish line for a deploy — it must pass against the
# real Render URL, not localhost, before the backend is considered done.
#
# Usage:
#   ./scripts/verify.ps1 -BaseUrl https://ascend-backend.onrender.com -UserToken abc123 -IngestToken xyz789
param(
    [Parameter(Mandatory = $true)][string]$BaseUrl,
    [Parameter(Mandatory = $true)][string]$UserToken,
    [Parameter(Mandatory = $true)][string]$IngestToken
)

$ErrorActionPreference = "Stop"
$BaseUrl = $BaseUrl.TrimEnd("/")
$script:Pass = 0
$script:Fail = 0

function Test-Endpoint {
    param(
        [string]$Desc,
        [int]$Expected,
        [string]$Method,
        [string]$Path,
        [string]$Auth,       # "user" | "ingest" | "none"
        [string]$Body = $null
    )

    $headers = @{}
    switch ($Auth) {
        "user"   { $headers["Authorization"] = "Token $UserToken" }
        "ingest" { $headers["Authorization"] = "Bearer $IngestToken" }
    }

    $uri = "$BaseUrl$Path"
    try {
        if ($Body) {
            $resp = Invoke-WebRequest -Uri $uri -Method $Method -Headers $headers `
                -ContentType "application/json" -Body $Body -SkipHttpErrorCheck
        } else {
            $resp = Invoke-WebRequest -Uri $uri -Method $Method -Headers $headers -SkipHttpErrorCheck
        }
        $code = [int]$resp.StatusCode
        $respBody = $resp.Content
    } catch {
        # Older PowerShell/.NET without -SkipHttpErrorCheck throws on non-2xx.
        if ($_.Exception.Response) {
            $code = [int]$_.Exception.Response.StatusCode
            $respBody = ""
        } else {
            $code = -1
            $respBody = $_.Exception.Message
        }
    }

    if ($code -eq $Expected) {
        Write-Host "  OK   [$code] $Desc"
        $script:Pass++
    } else {
        Write-Host "  FAIL [$code, expected $Expected] $Desc"
        if ($respBody) { Write-Host "       body: $($respBody.Substring(0, [Math]::Min(300, $respBody.Length)))" }
        $script:Fail++
    }
}

Write-Host "== ASCEND backend verification against $BaseUrl =="
Write-Host ""

Write-Host "-- Health --"
Test-Endpoint -Desc "GET /api/health/ (no auth)" -Expected 200 -Method GET -Path "/api/health/" -Auth none

Write-Host ""
Write-Host "-- Auth separation --"
Test-Endpoint -Desc "GET /api/analytics/funnel/ with no token -> 401" -Expected 401 -Method GET -Path "/api/analytics/funnel/" -Auth none
Test-Endpoint -Desc "POST /api/ingest/ with user token -> 401" -Expected 401 -Method POST -Path "/api/ingest/" -Auth user -Body '{"daily_logs": []}'

Write-Host ""
Write-Host "-- Ingest idempotency (same payload twice) --"
$dailyLogPayload = '{"daily_logs": [{"log_date": "2026-09-07", "deep_work_minutes": 120, "energy": 4}]}'
Test-Endpoint -Desc "POST /api/ingest/ first daily_log" -Expected 200 -Method POST -Path "/api/ingest/" -Auth ingest -Body $dailyLogPayload
Test-Endpoint -Desc "POST /api/ingest/ same daily_log again" -Expected 200 -Method POST -Path "/api/ingest/" -Auth ingest -Body $dailyLogPayload

Write-Host ""
Write-Host "-- Unknown field rejection --"
Test-Endpoint -Desc "POST /api/ingest/ with unknown field -> 400" -Expected 400 -Method POST -Path "/api/ingest/" -Auth ingest `
    -Body '{"daily_logs": [{"log_date": "2026-09-07", "energy": 4, "not_a_real_field": 1}]}'

Write-Host ""
Write-Host "-- Courses / skills ingest --"
# Deliberately throwaway names so this smoke test never mutates a real
# seeded course/skill (an unseen name creates a new row).
$coursePayload = '{"courses": [{"name": "__verify smoke test course__", "progress_pct": 50}]}'
Test-Endpoint -Desc "POST /api/ingest/ course upsert" -Expected 200 -Method POST -Path "/api/ingest/" -Auth ingest -Body $coursePayload
Test-Endpoint -Desc "POST /api/ingest/ same course again (idempotent)" -Expected 200 -Method POST -Path "/api/ingest/" -Auth ingest -Body $coursePayload
Test-Endpoint -Desc "POST /api/ingest/ skill upsert" -Expected 200 -Method POST -Path "/api/ingest/" -Auth ingest `
    -Body '{"skills": [{"name": "__verify smoke test skill__", "level": 50}]}'
Test-Endpoint -Desc "POST /api/ingest/ course with unknown field -> 400" -Expected 400 -Method POST -Path "/api/ingest/" -Auth ingest `
    -Body '{"courses": [{"name": "__verify smoke test course__", "provider": "nope"}]}'

Write-Host ""
Write-Host "-- Ingest sleep shortcut --"
Test-Endpoint -Desc "POST /api/ingest/sleep/ bed event" -Expected 200 -Method POST -Path "/api/ingest/sleep/" -Auth ingest `
    -Body '{"event": "bed", "at": "2026-09-08T00:47:00+05:30"}'

Write-Host ""
Write-Host "-- Read endpoints --"
Test-Endpoint -Desc "GET /api/today/ (ingest token)" -Expected 200 -Method GET -Path "/api/today/" -Auth ingest
Test-Endpoint -Desc "GET /api/today/ (user token)" -Expected 200 -Method GET -Path "/api/today/" -Auth user
Test-Endpoint -Desc "GET /api/email-queue/ (ingest token)" -Expected 200 -Method GET -Path "/api/email-queue/" -Auth ingest

Write-Host ""
Write-Host "-- Analytics (user token only) --"
foreach ($path in @("rhythm", "correlations", "funnel", "losses", "burnup", "certtrend", "decay", "activity", "observations")) {
    Test-Endpoint -Desc "GET /api/analytics/$path/" -Expected 200 -Method GET -Path "/api/analytics/$path/" -Auth user
    Test-Endpoint -Desc "GET /api/analytics/$path/ with ingest token -> 401" -Expected 401 -Method GET -Path "/api/analytics/$path/" -Auth ingest
}

Write-Host ""
Write-Host "-- New read endpoints (user token only) --"
foreach ($path in @("applications", "milestones", "sleep-logs", "daily-logs", "skills", "courses", "cert-domains", "content-posts", "reflections", "notion-tasks")) {
    Test-Endpoint -Desc "GET /api/$path/ with no token -> 401" -Expected 401 -Method GET -Path "/api/$path/" -Auth none
    Test-Endpoint -Desc "GET /api/$path/" -Expected 200 -Method GET -Path "/api/$path/" -Auth user
    Test-Endpoint -Desc "GET /api/$path/ with ingest token -> 401" -Expected 401 -Method GET -Path "/api/$path/" -Auth ingest
}

Write-Host ""
Write-Host "-- OpenAPI schema (public) --"
Test-Endpoint -Desc "GET /api/schema/ (no auth)" -Expected 200 -Method GET -Path "/api/schema/" -Auth none

Write-Host ""
Write-Host "-- Countdown PATCH --"
# Ids below match this deployment's seed migration insertion order
# (AI-103 exam=1, editable; Program end=2, not editable) — adjust if this
# is ever run against a database seeded differently.
Test-Endpoint -Desc "PATCH /api/countdowns/1/ (editable) -> 200" -Expected 200 -Method PATCH -Path "/api/countdowns/1/" -Auth user -Body '{"target_date": "2026-11-15"}'
Test-Endpoint -Desc "PATCH /api/countdowns/2/ (Program end, not editable) -> 400" -Expected 400 -Method PATCH -Path "/api/countdowns/2/" -Auth user -Body '{"target_date": "2026-01-01"}'

Write-Host ""
Write-Host "-- BlockEntry undo round-trip --"
Invoke-WebRequest -Uri "$BaseUrl/api/blocks/B1/start/" -Method POST -Headers @{Authorization = "Token $UserToken"} -SkipHttpErrorCheck | Out-Null
$completeResp = Invoke-WebRequest -Uri "$BaseUrl/api/blocks/B1/complete/" -Method POST -Headers @{Authorization = "Token $UserToken"} -SkipHttpErrorCheck
$entryId = ($completeResp.Content | ConvertFrom-Json).id
if ($entryId) {
    Test-Endpoint -Desc "PATCH /api/block-entries/$entryId/ (undo) -> 200" -Expected 200 -Method PATCH -Path "/api/block-entries/$entryId/" -Auth user -Body '{}'
} else {
    Write-Host "  FAIL [no id] could not extract BlockEntry id from complete response: $($completeResp.Content)"
    $script:Fail++
}

Write-Host ""
Write-Host "-- Notion sync (machine token) --"
Write-Host "   Run this once BEFORE setting NOTION_TOKEN/NOTION_DAILY_BOARD_DB_ID,"
Write-Host "   and again AFTER — see docs/NOTION_SYNC.md for the full walkthrough."
$syncResp = Invoke-WebRequest -Uri "$BaseUrl/api/sync/notion/" -Method POST -Headers @{Authorization = "Bearer $IngestToken"} -SkipHttpErrorCheck
$syncCode = [int]$syncResp.StatusCode
if ($syncCode -eq 503) {
    Write-Host "  OK   [503] POST /api/sync/notion/ — not configured yet (expected before NOTION_TOKEN is set)"
    $script:Pass++
} elseif ($syncCode -eq 200) {
    Write-Host "  OK   [200] POST /api/sync/notion/ — $($syncResp.Content)"
    $script:Pass++
} else {
    Write-Host "  FAIL [$syncCode] POST /api/sync/notion/ — $($syncResp.Content)"
    $script:Fail++
}

Write-Host ""
Write-Host "== $($script:Pass) passed, $($script:Fail) failed =="
if ($script:Fail -gt 0) { exit 1 }
