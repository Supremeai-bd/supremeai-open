# ============================================================================
# SupremeAI Gateway — E2E smoke: 10 real-world calls (5 non-stream + 5 SSE)
# Issue #403 · PowerShell mirror of run_e2e_smoke.sh (same subcommands, same
# output contract, same exit codes — repo house style, WO #251 pattern).
#
# Usage:
#   pwsh -File run_e2e_smoke.ps1                # full matrix (default)
#   pwsh -File run_e2e_smoke.ps1 -NonStream     # only 5 non-streaming calls
#   pwsh -File run_e2e_smoke.ps1 -Stream        # only 5 SSE streaming calls
#
# Environment overrides (identical to the sh mirror):
#   GATEWAY_URL           default: https://supremeai-api-ulw0.onrender.com
#                         (README SSOT — ghost host retired #2355/#2365/#2377)
#   SUPREMEAI_API_KEY     required — monolith key-plane key (vault/env only)
#   MODELS                space-separated model rotation, default: "auto"
#   MAX_TOKENS            default: 32
#   CURL_TIMEOUT          default: 30 (seconds per request)
#
# Exit codes: 0 = all requested calls passed; 1 = at least one failed
# (fail-closed — a skipped check does not exist).
# ============================================================================
[CmdletBinding()]
param(
    [switch]$NonStream,
    [switch]$Stream
)

$ErrorActionPreference = 'Stop'

$GatewayUrl = ($env:GATEWAY_URL ?? 'https://supremeai-api-ulw0.onrender.com').TrimEnd('/')
$ApiKey     = $env:SUPREMEAI_API_KEY
$Models     = @($env:MODELS ?? 'auto')
$MaxTokens  = [int]($env:MAX_TOKENS ?? '32')
$TimeoutS   = [int]($env:CURL_TIMEOUT ?? '30')
$Prompt     = 'Reply with exactly: SUPREME-E2E-OK'

$script:Failures = 0
$script:Passed   = 0

function Fail([string]$Label, [string]$Reason) {
    $script:Failures++
    Write-Output "FAIL ${Label}: $Reason"
}

function Pass([string]$Label, [string]$Detail) {
    $script:Passed++
    Write-Output "PASS ${Label}: $Detail"
}

if (-not $ApiKey) {
    Write-Output 'FAIL setup: SUPREMEAI_API_KEY is not set — key-plane key required (docs/CONSUMERS.md). No live calls attempted.'
    exit 1
}

function Invoke-NonStreamCall([string]$Label, [string]$Model) {
    $payload = @{ model = $Model; stream = $false; max_tokens = $MaxTokens
                  messages = @(@{ role = 'user'; content = $Prompt }) } | ConvertTo-Json -Depth 5
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $resp = Invoke-WebRequest -Uri "$GatewayUrl/v1/chat/completions" -Method Post `
            -Headers @{ 'X-SupremeAI-Key' = $ApiKey; 'Content-Type' = 'application/json' } `
            -Body $payload -TimeoutSec $TimeoutS -UseBasicParsing
    } catch {
        $code = try { [int]$_.Exception.Response.StatusCode } catch { 'transport' }
        Fail $Label "honest error — HTTP $code : $($_.Exception.Message.Split("`n")[0])"
        return
    }
    $sw.Stop()
    $obj = $resp.Content | ConvertFrom-Json
    $content = $obj.choices[0].message.content
    if (-not $content) { Fail $Label 'empty choices[0].message.content — contract violation'; return }
    if (-not $obj.PSObject.Properties['usage']) { Fail $Label 'usage object missing — Honest Ledger contract violation'; return }
    Pass $Label "model=$Model non-stream 200, content+usage present, $([math]::Round($sw.Elapsed.TotalSeconds,3))s"
}

function Invoke-StreamCall([string]$Label, [string]$Model) {
    $payload = @{ model = $Model; stream = $true; max_tokens = $MaxTokens
                  messages = @(@{ role = 'user'; content = $Prompt }) } | ConvertTo-Json -Depth 5
    $client = [System.Net.Http.HttpClient]::new()
    $client.Timeout = [TimeSpan]::FromSeconds($TimeoutS)
    try {
        $req = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Post, "$GatewayUrl/v1/chat/completions")
        $req.Headers.Add('X-SupremeAI-Key', $ApiKey)
        $req.Content = [System.Net.Http.StringContent]::new($payload, [Text.Encoding]::UTF8, 'application/json')
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $resp = $client.SendAsync($req, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
        if ([int]$resp.StatusCode -ne 200) {
            $errBody = $resp.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            Fail $Label "honest error — HTTP $([int]$resp.StatusCode): $($errBody.Substring(0, [Math]::Min(200, $errBody.Length)))"
            return
        }
        $stream = $resp.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $reader = [System.IO.StreamReader]::new($stream)
        $ttft = $null; $frames = [System.Collections.Generic.List[string]]::new()
        while ($null -ne ($line = $reader.ReadLine())) {
            if ($line -like 'data:*') {
                if ($null -eq $ttft) { $ttft = $sw.Elapsed.TotalSeconds }
                $frames.Add(($line -replace '^data:\s*', '').TrimEnd("`r"))
            }
        }
        if ($frames.Count -eq 0) { Fail $Label 'no SSE data: frames — streaming contract violation'; return }
        $terminal = $frames[$frames.Count - 1]
        if ($terminal -ne '[DONE]') {
            Fail $Label "stream ended without exact 'data: [DONE]' terminal frame (mid-stream drop is an honest failure): last='$terminal'"
            return
        }
        $bad = 0
        foreach ($f in ($frames | Select-Object -SkipLast 1)) {
            $obj = $null
            try { $obj = $f | ConvertFrom-Json } catch { $bad++; continue }
            if (-not $obj.choices[0].delta) { $bad++ }
        }
        if ($bad -gt 0) { Fail $Label "$bad SSE frame(s) missing choices[0].delta — frame contract violation"; return }
        Pass $Label "model=$Model SSE 200, frames valid, terminal [DONE] exact, TTFT=$([math]::Round($ttft,3))s"
    } catch {
        Fail $Label "transport error: $($_.Exception.Message.Split("`n")[0])"
    } finally {
        $client.Dispose()
    }
}

Write-Output "SupremeAI E2E smoke — gateway=$GatewayUrl models=[$($Models -join ' ')] subset=$(if ($Stream) {'stream'} elseif ($NonStream) {'nonstream'} else {'all'})"

for ($i = 0; $i -lt 5; $i++) {
    $m = $Models[$i % $Models.Count]
    if (-not $Stream)  { Invoke-NonStreamCall "ns$($i + 1)" $m }
    if (-not $NonStream) { Invoke-StreamCall "st$($i + 1)" $m }
}

$total = $script:Passed + $script:Failures
Write-Output "RESULT: $($script:Passed)/$total calls passed (fail-closed — failures listed above are honest)"
if ($script:Failures -gt 0) { exit 1 }
exit 0
