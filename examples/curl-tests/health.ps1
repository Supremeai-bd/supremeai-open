# ============================================================================
# SupremeAI MCP Tower - HTTP endpoint smoke tests (PowerShell 5.1+/7+)
# Issue #49 - Windows mirror of health.sh (same subcommands, same contract).
#
# Usage:
#   .\health.ps1                 # health check (default)
#   .\health.ps1 health
#   .\health.ps1 sse
#   .\health.ps1 tools-list
#   .\health.ps1 tool-call system_summary
#   .\health.ps1 tool-call bridge_guide
#   .\health.ps1 all
#
# Environment overrides:
#   $env:BASE_URL              default: https://supremeai-mcp-tower.onrender.com
#   $env:MCP_PROTOCOL_VERSION  default: 2025-03-26
#   $env:CURL_TIMEOUT          default: 20 (seconds per request)
#
# Exit codes: 0 = all requested checks passed; 1 = at least one failed
# (fail-closed, matching repo doctrine).
# ============================================================================
param(
    [Parameter(Position = 0)]
    [ValidateSet('health', 'sse', 'tools-list', 'tool-call', 'gateway', 'all')]
    [string]$Command = 'health',

    [Parameter(Position = 1)]
    [string]$ToolName = 'system_summary'
)

$ErrorActionPreference = 'Stop'

$BaseUrl = if ($env:BASE_URL) { $env:BASE_URL.TrimEnd('/') } else { 'https://supremeai-mcp-tower.onrender.com' }
$GwBaseUrl = if ($env:GW_BASE_URL) { $env:GW_BASE_URL.TrimEnd('/') } else { 'http://127.0.0.1:8080' }
$GwKey = if ($env:GW_KEY) { $env:GW_KEY } else { 'supremeai-key-local-dev' }
$ProtocolVersion = if ($env:MCP_PROTOCOL_VERSION) { $env:MCP_PROTOCOL_VERSION } else { '2025-03-26' }
$TimeoutSec = if ($env:CURL_TIMEOUT) { [int]$env:CURL_TIMEOUT } else { 20 }

$script:Failures = 0
$script:McpSession = $null
$script:JsonRpcId = 100

function Write-Pass([string]$Message) { Write-Output "PASS  $Message" }
function Write-Fail([string]$Message) { Write-Output "FAIL  $Message"; $script:Failures++ }

function Invoke-Health {
    Write-Output "== GET $BaseUrl/health =="
    try {
        $resp = Invoke-WebRequest -Uri "$BaseUrl/health" -Method GET -TimeoutSec $TimeoutSec -UseBasicParsing
        Write-Pass "health: HTTP $([int]$resp.StatusCode) - $($resp.Content)"
    } catch {
        $code = try { [int]$_.Exception.Response.StatusCode } catch { '?' }
        Write-Fail "health: HTTP $code - $($_.Exception.Message)"
    }
}

function Invoke-Sse {
    Write-Output "== GET $BaseUrl/sse (bounded $TimeoutSec s read) =="
    $frames = ''
    try {
        $task = [System.Net.Http.HttpClient]::new().GetStringAsync("$BaseUrl/sse")
        if ($task.Wait([TimeSpan]::FromSeconds($TimeoutSec))) { $frames = $task.Result }
        else { $frames = '' }
    } catch {
        if ($_.Exception.InnerException) { $frames = $_.Exception.InnerException.Message } else { $frames = $_.Exception.Message }
    }
    if ($frames -match 'event:' -and $frames -match 'data:') {
        $endpoint = ($frames -split "`n" | Where-Object { $_ -like 'data:*' } | Select-Object -First 1) -replace '^data:\s*', ''
        Write-Pass "sse: stream opened, endpoint frame: $endpoint"
    } else {
        Write-Fail "sse: no event/data frames within ${TimeoutSec}s ($frames)"
    }
}

function Invoke-McpPost([string]$Body) {
    $headers = @{ 'Accept' = 'application/json, text/event-stream' }
    if ($script:McpSession) { $headers['mcp-session-id'] = $script:McpSession }
    $resp = Invoke-WebRequest -Uri "$BaseUrl/mcp" -Method POST -Body $Body `
        -ContentType 'application/json' -Headers $headers -TimeoutSec $TimeoutSec -UseBasicParsing
    $sid = $resp.Headers['mcp-session-id']
    if ($sid) { $script:McpSession = @($sid)[0] }
    return $resp.Content
}

function Invoke-McpInit {
    # Fresh session lifecycle - never re-initialize an existing session
    # (the tower rejects a second initialize on the same Mcp-Session-Id).
    $script:McpSession = $null
    $script:JsonRpcId++
    $body = "{`"jsonrpc`":`"2.0`",`"id`":$($script:JsonRpcId),`"method`":`"initialize`",`"params`":{`"protocolVersion`":`"$ProtocolVersion`",`"capabilities`":{},`"clientInfo`":{`"name`":`"supremeai-curl-tests`",`"version`":`"1.0`"}}}"
    return Invoke-McpPost $body
}

function Invoke-McpInitialized {
    Invoke-McpPost '{"jsonrpc":"2.0","method":"notifications/initialized"}' | Out-Null
}

function Invoke-ToolsList {
    Write-Output "== POST $BaseUrl/mcp (initialize + tools/list) =="
    try {
        $initResp = Invoke-McpInit
        Invoke-McpInitialized
        $script:JsonRpcId++
        $listResp = Invoke-McpPost "{`"jsonrpc`":`"2.0`",`"id`":$($script:JsonRpcId),`"method`":`"tools/list`"}"
        if ($listResp -match '"tools"') {
            $count = ([regex]::Matches($listResp, '"name"')).Count
            Write-Pass "tools-list: tools frame present (~$count name fields)"
        } else {
            Write-Fail "tools-list: no tools frame - $listResp"
        }
    } catch {
        Write-Fail "tools-list: $($_.Exception.Message)"
    }
}

function Invoke-ToolCall([string]$Tool) {
    Write-Output "== POST $BaseUrl/mcp (initialize + tools/call $Tool) =="
    try {
        Invoke-McpInit | Out-Null
        Invoke-McpInitialized
        $script:JsonRpcId++
        $callResp = Invoke-McpPost "{`"jsonrpc`":`"2.0`",`"id`":$($script:JsonRpcId),`"method`":`"tools/call`",`"params`":{`"name`":`"$Tool`",`"arguments`":{}}}"
        if ($callResp -match '"result"') {
            Write-Pass "tool-call ${Tool}: result frame present"
            if ($callResp.Length -gt 400) { Write-Output $callResp.Substring(0, 400) } else { Write-Output $callResp }
        } elseif ($callResp -match '"error"') {
            Write-Fail "tool-call ${Tool}: JSON-RPC error - $callResp"
        } else {
            Write-Fail "tool-call ${Tool}: unexpected response - $callResp"
        }
    } catch {
        Write-Fail "tool-call ${Tool}: $($_.Exception.Message)"
    }
}

# --- gateway (issue #336 AC3): unified provider gateway smoke ---------------
function Invoke-GwHealth {
    Write-Output "== GET $GwBaseUrl/healthz =="
    try {
        $resp = Invoke-WebRequest -Uri "$GwBaseUrl/healthz" -Method GET -TimeoutSec $TimeoutSec -UseBasicParsing
        Write-Pass "gw-health: HTTP $([int]$resp.StatusCode) - $($resp.Content)"
    } catch {
        $code = try { [int]$_.Exception.Response.StatusCode } catch { '?' }
        Write-Fail "gw-health: HTTP $code - $($_.Exception.Message)"
    }
}

function Invoke-GwModelsAuthGate {
    Write-Output "== GET $GwBaseUrl/v1/models (no key -> 401 default-deny) =="
    try {
        $resp = Invoke-WebRequest -Uri "$GwBaseUrl/v1/models" -Method GET -TimeoutSec $TimeoutSec -UseBasicParsing
        Write-Fail "gw-models-auth: expected 401, got $([int]$resp.StatusCode)"
    } catch {
        $code = try { [int]$_.Exception.Response.StatusCode } catch { '?' }
        if ($code -eq 401) { Write-Pass "gw-models-auth: HTTP 401 (default-deny)" }
        else { Write-Fail "gw-models-auth: expected 401, got $code" }
    }
}

function Invoke-GwModels {
    Write-Output "== GET $GwBaseUrl/v1/models (keyed) =="
    try {
        $headers = @{ 'X-SupremeAI-Key' = $GwKey }
        $resp = Invoke-WebRequest -Uri "$GwBaseUrl/v1/models" -Headers $headers -Method GET -TimeoutSec $TimeoutSec -UseBasicParsing
        if ($resp.Content -match '"data"') { Write-Pass "gw-models: HTTP $([int]$resp.StatusCode) - model list present" }
        else { Write-Fail "gw-models: model list missing - $($resp.Content)" }
    } catch {
        $code = try { [int]$_.Exception.Response.StatusCode } catch { '?' }
        Write-Fail "gw-models: HTTP $code - $($_.Exception.Message)"
    }
}

function Invoke-GwChatJson {
    Write-Output "== POST $GwBaseUrl/v1/chat/completions (stream:false) =="
    try {
        $headers = @{ 'X-SupremeAI-Key' = $GwKey; 'Content-Type' = 'application/json' }
        $body = '{"model":"auto","messages":[{"role":"user","content":"smoke"}]}'
        $resp = Invoke-WebRequest -Uri "$GwBaseUrl/v1/chat/completions" -Headers $headers -Method POST -Body $body -TimeoutSec $TimeoutSec -UseBasicParsing
        if ($resp.Content -match '"chat.completion"') { Write-Pass "gw-chat: HTTP $([int]$resp.StatusCode) - OpenAI-compatible completion" }
        else { Write-Fail "gw-chat: unexpected payload - $($resp.Content)" }
    } catch {
        $code = try { [int]$_.Exception.Response.StatusCode } catch { '?' }
        Write-Fail "gw-chat: HTTP $code - $($_.Exception.Message)"
    }
}

function Invoke-GwChatSse {
    Write-Output "== POST $GwBaseUrl/v1/chat/completions (stream:true, bounded read) =="
    $frames = ''
    try {
        $headers = @{ 'X-SupremeAI-Key' = $GwKey; 'Content-Type' = 'application/json' }
        $body = '{"stream":true,"messages":[{"role":"user","content":"smoke"}]}'
        $resp = Invoke-WebRequest -Uri "$GwBaseUrl/v1/chat/completions" -Headers $headers -Method POST -Body $body -TimeoutSec $TimeoutSec -UseBasicParsing
        $frames = $resp.Content
    } catch {
        Write-Fail "gw-chat-sse: transport error - $($_.Exception.Message)"
        return
    }
    if ($frames -match '(?m)^event:' -and $frames -match '(?m)^data:') {
        Write-Pass "gw-chat-sse: event:/data: framing present"
    } else {
        Write-Fail "gw-chat-sse: no SSE frames within $TimeoutSec s"
    }
}

function Invoke-Gateway {
    Invoke-GwHealth
    Invoke-GwModelsAuthGate
    Invoke-GwModels
    Invoke-GwChatJson
    Invoke-GwChatSse
}

switch ($Command) {
    'health'      { Invoke-Health }
    'sse'         { Invoke-Sse }
    'tools-list'  { Invoke-ToolsList }
    'tool-call'   { Invoke-ToolCall $ToolName }
    'gateway'     { Invoke-Gateway }
    'all' {
        Invoke-Health
        Invoke-Sse
        Invoke-ToolsList
        Invoke-ToolCall 'system_summary'
        Invoke-ToolCall 'bridge_guide'
    }
}

if ($script:Failures -gt 0) {
    Write-Output ""
    Write-Output "$($script:Failures) check(s) FAILED (fail-closed: no silent skips)."
    exit 1
}
Write-Output ""
Write-Output "All requested checks passed."
exit 0
