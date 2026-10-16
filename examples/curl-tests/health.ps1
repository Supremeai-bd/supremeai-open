# SupremeAI MCP Tower — HTTP endpoint test suite (PowerShell, Windows).
# Companion: health.sh (bash, Linux/macOS). Contract: examples/curl-tests/README.md.
#
# Endpoints exercised (all real, see infrastructure/mcp-control-plane/src/index.ts):
#   GET  /health   — honest aggregate health (200 ok|degraded, 503 outage)
#   GET  /sse      — legacy SSE transport handshake (emits `event: endpoint`)
#   POST /mcp      — Streamable JSON-RPC: initialize -> tools/list -> tools/call
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File health.ps1 [-Cmd all|health|sse|tools|call] [-Tool system.summary]
# Environment:
#   MCP_TOWER_URL — override base URL (default: https://supremeai-mcp-tower.onrender.com)
# Exit codes: 0 pass · 1 test failure · 2 usage error

param(
    [ValidateSet("all", "health", "sse", "tools", "call")]
    [string]$Cmd = "all",
    [string]$Tool = "system.summary"
)

$ErrorActionPreference = "Stop"
$BaseUrl = if ($env:MCP_TOWER_URL) { $env:MCP_TOWER_URL } else { "https://supremeai-mcp-tower.onrender.com" }

# TLS 1.2 on legacy Windows PowerShell 5.1 hosts (no-op elsewhere).
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}

$script:PassCount = 0
$script:FailCount = 0

function Pass([string]$Msg) { $script:PassCount++; Write-Output "PASS: $Msg" }
function Fail([string]$Msg) { $script:FailCount++; Write-Output "FAIL: $Msg" }

# Strip an SSE wrapper from a JSON-RPC response, if present.
function Unwrap-Sse([string]$Body) {
    if ($Body -match '(?m)^data:\s*(.*)$') { return $Matches[1] }
    return $Body
}

# --- 1. Health check -------------------------------------------------------
function Test-Health {
    Write-Output "== health: GET $BaseUrl/health"
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/health" -TimeoutSec 30
        if ($r.StatusCode -eq 200) {
            Pass "health: HTTP 200"
            if ($r.Content -match '"status"') {
                Pass ("health: status field present (" + ($Matches[0]) + ")")
            } else {
                Fail "health: no status field in body"
            }
        } else {
            Fail "health: unexpected HTTP $($r.StatusCode)"
        }
    } catch {
        $code = $null
        try { $code = $_.Exception.Response.StatusCode.value__ } catch {}
        if ($code -eq 503) {
            Fail "health: HTTP 503 outage (service reports itself down - honest, but not healthy)"
        } else {
            Fail "health: network error ($($_.Exception.Message))"
        }
    }
}

# --- 2. SSE handshake -------------------------------------------------------
function Test-Sse {
    Write-Output "== sse: GET $BaseUrl/sse (expect event: endpoint within timeout)"
    try {
        # HttpWebRequest lets us read the raw stream and stop after the handshake.
        $req = [Net.HttpWebRequest]::Create("$BaseUrl/sse")
        $req.Accept = "text/event-stream"
        $req.Timeout = 12000
        $req.ReadWriteTimeout = 12000
        $resp = $req.GetResponse()
        $reader = New-Object IO.StreamReader($resp.GetResponseStream())
        $lines = @()
        while ($lines.Count -lt 20) {
            $line = $reader.ReadLine()
            if ($null -eq $line) { break }
            $lines += $line
            if ($lines -match '^event:\s*endpoint$') { break }
        }
        $reader.Close(); $resp.Close()
        if ($lines -match '^event:\s*endpoint') {
            $dataLine = ($lines | Where-Object { $_ -like 'data:*' } | Select-Object -First 1)
            Pass "sse: endpoint event received ($dataLine)"
        } else {
            Fail ("sse: no endpoint event within timeout (first lines: " + (($lines | Select-Object -First 3) -join ' | ') + ")")
        }
    } catch {
        Fail "sse: stream error ($($_.Exception.Message))"
    }
}

# --- Shared: MCP streamable handshake ---------------------------------------
# Returns a hashtable { SessionId } or $null on handshake failure.
function Start-McpHandshake {
    $headers = @{
        "Accept" = "application/json, text/event-stream"
    }
    $payload = @{
        jsonrpc = "2.0"; id = 1; method = "initialize"
        params = @{
            protocolVersion = "2025-03-26"; capabilities = @{}
            clientInfo = @{ name = "curl-tests"; version = "1.0.0" }
        }
    } | ConvertTo-Json -Depth 6 -Compress

    try {
        $r = Invoke-WebRequest -UseBasicParsing -Method Post -Uri "$BaseUrl/mcp" `
            -ContentType "application/json" -Headers $headers `
            -Body $payload -TimeoutSec 30
        $sid = $null
        if ($r.Headers["mcp-session-id"]) { $sid = [string]($r.Headers["mcp-session-id"]) }
        if (-not $sid) { return $null }
    } catch {
        return $null
    }

    # notifications/initialized — session activation (no response body expected).
    $initPayload = @{ jsonrpc = "2.0"; method = "notifications/initialized" } | ConvertTo-Json -Compress
    try {
        Invoke-WebRequest -UseBasicParsing -Method Post -Uri "$BaseUrl/mcp" `
            -ContentType "application/json" -Headers ($headers + @{ "mcp-session-id" = $sid }) `
            -Body $initPayload -TimeoutSec 30 | Out-Null
    } catch {}

    return @{ SessionId = $sid }
}

function Invoke-McpRpc {
    param([hashtable]$Session, [int]$Id, [string]$Method, [hashtable]$Params)
    $body = @{ jsonrpc = "2.0"; id = $Id; method = $Method }
    if ($Params) { $body.params = $Params }
    $json = $body | ConvertTo-Json -Depth 8 -Compress
    $headers = @{ "Accept" = "application/json, text/event-stream"; "mcp-session-id" = $Session.SessionId }
    $r = Invoke-WebRequest -UseBasicParsing -Method Post -Uri "$BaseUrl/mcp" `
        -ContentType "application/json" -Headers $headers -Body $json -TimeoutSec 60
    return (Unwrap-Sse $r.Content)
}

# --- 3. Tool listing ---------------------------------------------------------
function Test-Tools {
    Write-Output "== tools: POST $BaseUrl/mcp initialize -> tools/list"
    $session = Start-McpHandshake
    if (-not $session) { Fail "tools: initialize handshake failed (no mcp-session-id header)"; return }

    $resp = Invoke-McpRpc -Session $session -Id 2 -Method "tools/list"
    if ($resp -match '"tools"') {
        $count = ([regex]::Matches($resp, '"name"')).Count
        Pass "tools: tools/list returned $count tool entries"
        if ($resp -match '"bridge\.guide"') {
            Pass "tools: bridge.guide visible (zero-credential guest scope)"
        } else {
            Write-Output "NOTE: bridge.guide not in this session's tool list (scope-dependent visibility)"
        }
    } else {
        Fail ("tools: no tools array in response (" + $resp.Substring(0, [Math]::Min(160, $resp.Length)) + ")")
    }
}

# --- 4. Tool call ------------------------------------------------------------
# The Tower's call registry sanitizes registered names (dots -> underscores,
# index.ts server.tool wrapper) while tools/list advertises the dotted form.
# We try the advertised name first and, if the call layer reports "not found",
# retry the call-registry variant - surfacing the mismatch.
function Test-Call([string]$ToolName) {
    Write-Output "== call: tools/call $ToolName"
    $session = Start-McpHandshake
    if (-not $session) { Fail "call: initialize handshake failed (no mcp-session-id header)"; return }

    $resp = Invoke-McpRpc -Session $session -Id 3 -Method "tools/call" -Params @{ name = $ToolName; arguments = @{} }
    if ($resp -match 'not found') {
        $variant = $ToolName.Replace('.', '_')
        if ($variant -ne $ToolName) {
            Write-Output "NOTE: '$ToolName' not callable (advertised by tools/list) - retrying call-registry variant '$variant'"
            $ToolName = $variant
            $resp = Invoke-McpRpc -Session $session -Id 3 -Method "tools/call" -Params @{ name = $ToolName; arguments = @{} }
        }
    }

    if ($resp -match '"isError":\s*true') {
        Fail ("call $ToolName`: tool returned isError:true (" + $resp.Substring(0, [Math]::Min(200, $resp.Length)) + ")")
    } elseif ($resp -match '"content"') {
        Pass ("call $ToolName`: content returned (" + $resp.Substring(0, [Math]::Min(120, $resp.Length)) + "...)")
    } else {
        Fail ("call $ToolName`: unexpected response (" + $resp.Substring(0, [Math]::Min(160, $resp.Length)) + ")")
    }
}

# --- Dispatch ----------------------------------------------------------------
switch ($Cmd) {
    "health" { Test-Health }
    "sse"    { Test-Sse }
    "tools"  { Test-Tools }
    "call"   { Test-Call $Tool }
    "all"    {
        Test-Health
        Test-Sse
        Test-Tools
        Test-Call $Tool
        Test-Call "bridge.guide"
    }
    default {
        Write-Output "usage: powershell -File health.ps1 [-Cmd all|health|sse|tools|call] [-Tool system.summary]"
        exit 2
    }
}

Write-Output ""
Write-Output "summary: $script:PassCount passed, $script:FailCount failed"
if ($script:FailCount -gt 0) { exit 1 }
exit 0
