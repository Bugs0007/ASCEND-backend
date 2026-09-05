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
Write-Host "== $($script:Pass) passed, $($script:Fail) failed =="
if ($script:Fail -gt 0) { exit 1 }
