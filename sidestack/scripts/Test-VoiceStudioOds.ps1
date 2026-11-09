<#
.SYNOPSIS
  Read-only preflight for SideStack Voice Studio on ODS.

.DESCRIPTION
  Checks, without changing anything:
    - ODS local model relay (127.0.0.1:4007): /health, and /v1/models with the relay key
    - ODS Whisper (127.0.0.1:9000): /health and /v1/models
    - Ollama (127.0.0.1:11435): whether a model is loaded (the single-runtime rule)
    - GPU memory (nvidia-smi)
    - Voice Studio port (default 3900): free or in use
    - Toolchain: uv, bun, Python
  The relay key is read from the Windows USER env var ODS_LOCAL_MODEL_RELAY_KEY (falls back to
  the process env). It is never printed or written anywhere.

  The ODS checks are GET requests only. Run them only when the user has approved ODS probes, or
  pass -SkipOds.

.PARAMETER SkipOds
  Skip every request to ODS and Ollama; check only the local GPU, port and toolchain.

.PARAMETER Port
  Voice Studio port to check (default 3900).

.PARAMETER Json
  Print the results as JSON instead of a table.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File sidestack\scripts\Test-VoiceStudioOds.ps1 -SkipOds
#>
[CmdletBinding()]
param(
    [switch]$SkipOds,
    [int]$Port = 3900,
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RelayBase   = 'http://127.0.0.1:4007'
$WhisperBase = 'http://127.0.0.1:9000'
$OllamaBase  = 'http://127.0.0.1:11435'
$results = New-Object System.Collections.Generic.List[object]

function Add-Result([string]$Check, [string]$Status, [string]$Detail) {
    $results.Add([pscustomobject]@{ Check = $Check; Status = $Status; Detail = $Detail })
}

function Invoke-Get([string]$Url, [hashtable]$Headers = @{}, [int]$TimeoutSec = 5) {
    try {
        $r = Invoke-WebRequest -Uri $Url -Headers $Headers -TimeoutSec $TimeoutSec -UseBasicParsing
        return [pscustomobject]@{ Code = [int]$r.StatusCode; Body = $r.Content; Error = $null }
    } catch {
        $code = $null
        if ($_.Exception.PSObject.Properties['Response'] -and $_.Exception.Response) {
            try { $code = [int]$_.Exception.Response.StatusCode } catch { $code = $null }
        }
        return [pscustomobject]@{ Code = $code; Body = $null; Error = $_.Exception.Message }
    }
}

function Get-ModelIds([string]$Body) {
    try {
        $o = $Body | ConvertFrom-Json
        if ($o.PSObject.Properties['data']) { return @($o.data | ForEach-Object { $_.id }) }
        if ($o.PSObject.Properties['models']) { return @($o.models | ForEach-Object { $_.name }) }
    } catch { }
    return @()
}

# ── ODS + Ollama (GET only) ────────────────────────────────────────────────────────────
if ($SkipOds) {
    Add-Result 'ODS checks' 'SKIP' '-SkipOds given'
} else {
    $h = Invoke-Get "$RelayBase/health"
    if ($h.Code -eq 200) { Add-Result 'Relay /health' 'OK' '200' }
    else { Add-Result 'Relay /health' 'FAIL' ("code={0} {1}" -f $h.Code, $h.Error) }

    $key = [Environment]::GetEnvironmentVariable('ODS_LOCAL_MODEL_RELAY_KEY', 'User')
    if (-not $key) { $key = $env:ODS_LOCAL_MODEL_RELAY_KEY }
    if (-not $key) {
        Add-Result 'Relay key' 'FAIL' 'ODS_LOCAL_MODEL_RELAY_KEY not set (User or process env)'
    } else {
        Add-Result 'Relay key' 'OK' 'present (not shown)'
        $m = Invoke-Get "$RelayBase/v1/models" @{ Authorization = "Bearer $key" }
        if ($m.Code -eq 200) {
            $ids = Get-ModelIds $m.Body
            $ctx = ''
            try {
                $o = $m.Body | ConvertFrom-Json
                if ($o.PSObject.Properties['ods'] -and $o.ods.PSObject.Properties['contextLength']) {
                    $ctx = " ctx=$($o.ods.contextLength)"
                }
            } catch { }
            $st = if ($ids -contains 'ods/current') { 'OK' } else { 'WARN' }
            Add-Result 'Relay /v1/models' $st (("ids=" + ($ids -join ',')) + $ctx)
        } else {
            Add-Result 'Relay /v1/models' 'FAIL' ("code={0} {1}" -f $m.Code, $m.Error)
        }
        Remove-Variable key
    }

    $wh = Invoke-Get "$WhisperBase/health"
    if ($wh.Code -eq 200) { Add-Result 'Whisper /health' 'OK' '200' }
    else { Add-Result 'Whisper /health' 'FAIL' ("code={0} {1}" -f $wh.Code, $wh.Error) }
    $wm = Invoke-Get "$WhisperBase/v1/models"
    if ($wm.Code -eq 200) { Add-Result 'Whisper /v1/models' 'OK' ("ids=" + ((Get-ModelIds $wm.Body) -join ',')) }
    else { Add-Result 'Whisper /v1/models' 'WARN' ("code={0} {1}" -f $wm.Code, $wm.Error) }

    $op = Invoke-Get "$OllamaBase/api/ps" @{} 3
    if ($op.Code -eq 200) {
        $loaded = @(Get-ModelIds $op.Body)   # @(): an empty return unrolls to $null
        if ($loaded.Count -gt 0) { Add-Result 'Ollama loaded models' 'WARN' ("loaded: " + ($loaded -join ',') + ' (one runtime at a time)') }
        else { Add-Result 'Ollama loaded models' 'OK' 'none loaded' }
    } else {
        Add-Result 'Ollama loaded models' 'OK' 'Ollama not reachable (not running)'
    }
}

# ── GPU ───────────────────────────────────────────────────────────────────────────────────
$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($smi) {
    $line = & $smi.Source --query-gpu=name,memory.used,memory.total --format=csv,noheader,nounits 2>$null | Select-Object -First 1
    if ($line) {
        $parts = $line -split ',\s*'
        $used = [double]$parts[1]; $total = [double]$parts[2]
        $free = [math]::Round(($total - $used) / 1024, 1)
        $st = if ($free -ge 4) { 'OK' } else { 'WARN' }
        Add-Result 'GPU free VRAM' $st ("{0}: {1} GB free of {2} GB" -f $parts[0], $free, [math]::Round($total / 1024, 1))
    } else { Add-Result 'GPU free VRAM' 'WARN' 'nvidia-smi returned nothing' }
} else { Add-Result 'GPU free VRAM' 'WARN' 'nvidia-smi not found' }

# ── Port ──────────────────────────────────────────────────────────────────────────────────
$listen = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listen) {
    $procIds = @($listen | Select-Object -ExpandProperty OwningProcess -Unique)
    Add-Result "Port $Port" 'INFO' ("in use by pid " + ($procIds -join ','))
} else { Add-Result "Port $Port" 'OK' 'free' }

# ── Toolchain ─────────────────────────────────────────────────────────────────────────────
foreach ($tool in 'uv', 'bun', 'python') {
    $c = Get-Command $tool -ErrorAction SilentlyContinue
    if ($c) {
        $v = (& $c.Source --version 2>&1 | Select-Object -First 1) -as [string]
        Add-Result "Tool $tool" 'OK' $v.Trim()
    } else {
        $st = if ($tool -eq 'python') { 'FAIL' } else { 'WARN' }
        Add-Result "Tool $tool" $st 'not installed (lane VS-01)'
    }
}

if ($Json) { $results | ConvertTo-Json -Depth 3 }
else { $results | Format-Table -AutoSize | Out-String -Width 200 }

if ($results | Where-Object Status -eq 'FAIL') { exit 1 } else { exit 0 }
