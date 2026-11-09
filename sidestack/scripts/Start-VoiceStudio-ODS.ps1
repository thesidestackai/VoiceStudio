<#
.SYNOPSIS
  Starts SideStack Voice Studio on the ODS profile (http://127.0.0.1:3900/) after a
  read-only ODS preflight, or stops it again with -Stop.

.DESCRIPTION
  Reads the SideStack profile (KEY=VALUE lines, no secrets), validates it, and:
    - Default: runs the preflight (Test-VoiceStudioOds.ps1) and, if it passes, starts
      backend/main.py with the profile's environment plus the relay key from the Windows
      USER env (ODS_LOCAL_MODEL_RELAY_KEY), which is never printed, logged or copied into
      another variable. Polls /health until it is up or -TimeoutSec passes.
    - -Stop: stops the Voice Studio process listening on the profile port, and only that
      one (its command line must be backend/main.py).
    - -DryRun: prints the start plan and exits without any network or process.
  OMNIVOICE_SERVER_MODE is removed from the child environment: it is for Docker and
  turns off the loopback admin gate, which must stay on natively.

.PARAMETER ProfilePath
  Path to the KEY=VALUE profile file. Default: <repo root>\sidestack\config\ods.env if it
  exists, otherwise sidestack\config\ods.env.example.

.PARAMETER DryRun
  Print the start plan (readable, or JSON with -Json) and exit 0. No network, no process.

.PARAMETER Json
  With -DryRun, print the plan as JSON instead of key: value lines.

.PARAMETER SkipPreflight
  Skip Test-VoiceStudioOds.ps1 before starting (use only if you ran it yourself).

.PARAMETER Stop
  Stop the Voice Studio process listening on the profile port. If the port is free, prints
  'not running'; if another program owns it, exits 3 without touching it.

.PARAMETER NoUserEnv
  Read the relay key only from the process environment, never from the Windows USER env.

.PARAMETER AllowNonCommercial
  Start with commercial-only mode off (SIDESTACK_COMMERCIAL_ONLY=0) for private work, so
  non-commercial engines such as OmniVoice can be used. Do not publish what they make.

.PARAMETER TimeoutSec
  Seconds to wait for /health to answer 200 after starting (default 90).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File sidestack\scripts\Start-VoiceStudio-ODS.ps1 -DryRun

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File sidestack\scripts\Start-VoiceStudio-ODS.ps1

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File sidestack\scripts\Start-VoiceStudio-ODS.ps1 -Stop
#>
[CmdletBinding()]
param(
    [string]$ProfilePath,
    [switch]$DryRun,
    [switch]$Json,
    [switch]$SkipPreflight,
    [switch]$Stop,
    [switch]$NoUserEnv,
    [switch]$AllowNonCommercial,
    [int]$TimeoutSec = 90
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Paths ────────────────────────────────────────────────────────────────────────────
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ([string]::IsNullOrWhiteSpace($ProfilePath)) {
    $candidate = Join-Path $root 'sidestack\config\ods.env'
    if (Test-Path $candidate) { $ProfilePath = $candidate } else { $ProfilePath = Join-Path $root 'sidestack\config\ods.env.example' }
}
$ProfilePath = (Resolve-Path $ProfilePath).Path

# ── Profile parsing ──────────────────────────────────────────────────────────────────
# Every non-blank, non-# line must be KEY=VALUE with KEY ~ ^[A-Z][A-Z0-9_]*$.
$cfg = @{}
$profileLines = @(Get-Content -LiteralPath $ProfilePath)
for ($i = 0; $i -lt $profileLines.Count; $i++) {
    $line = $profileLines[$i].Trim()
    if ($line -eq '' -or $line.StartsWith('#')) { continue }
    $idx = $line.IndexOf('=')
    $ok = $false
    if ($idx -gt 0) {
        $key = $line.Substring(0, $idx)
        if ($key -match '^[A-Z][A-Z0-9_]*$') { $ok = $true }
    }
    if (-not $ok) {
        [Console]::Error.WriteLine(("profile line {0}: not KEY=VALUE" -f ($i + 1)))
        exit 2
    }
    $cfg[$line.Substring(0, $idx)] = $line.Substring($idx + 1)
}

# -AllowNonCommercial (VS-18): this run only, commercial-only mode off.
if ($AllowNonCommercial) { $cfg['SIDESTACK_COMMERCIAL_ONLY'] = '0' }

# ── Profile validation ───────────────────────────────────────────────────────────────
# Failures: one stderr line, exit 2. Never echo the value of a secret-named key.
function Fail-Profile([string]$Message) {
    [Console]::Error.WriteLine($Message)
    exit 2
}

$port = 0
if ($cfg.ContainsKey('OMNIVOICE_BIND_HOST') -and $cfg['OMNIVOICE_BIND_HOST'] -ne '127.0.0.1') {
    Fail-Profile 'OMNIVOICE_BIND_HOST must be 127.0.0.1'
}
if (-not [int]::TryParse($cfg['OMNIVOICE_PORT'], [ref]$port) -or $port -lt 1 -or $port -gt 65535) {
    Fail-Profile 'OMNIVOICE_PORT must be an integer from 1 to 65535'
}
foreach ($required in @('UV_PROJECT_ENVIRONMENT', 'OMNIVOICE_DATA_DIR')) {
    if (-not $cfg.ContainsKey($required) -or $cfg[$required] -eq '') {
        Fail-Profile ("{0} is required in the profile" -f $required)
    }
}
if ($cfg.ContainsKey('OMNIVOICE_SERVER_MODE') -and
    -not (@('', '0', 'false', 'no', 'off') -contains $cfg['OMNIVOICE_SERVER_MODE'].ToLowerInvariant())) {
    Fail-Profile 'OMNIVOICE_SERVER_MODE must stay off natively (empty, 0, false, no or off)'
}
foreach ($key in $cfg.Keys) {
    if ($key -match '(KEY|TOKEN|SECRET|PASSWORD)' -and $cfg[$key] -ne '') {
        Fail-Profile ("{0} must not have a value in the profile; secrets come from user env" -f $key)
    }
}

# ── Relay key (never printed, never copied into another variable name) ──────────────
$relay = $env:ODS_LOCAL_MODEL_RELAY_KEY
if (([string]::IsNullOrEmpty($relay)) -and (-not $NoUserEnv)) {
    $relay = [Environment]::GetEnvironmentVariable('ODS_LOCAL_MODEL_RELAY_KEY', 'User')
}
if ([string]::IsNullOrEmpty($relay)) { $relayKeyState = 'missing' } else { $relayKeyState = 'present' }

# ── Plan ─────────────────────────────────────────────────────────────────────────────
$pythonPath = Join-Path $cfg['UV_PROJECT_ENVIRONMENT'] 'Scripts\python.exe'
$distPath = Join-Path $root 'frontend\dist\index.html'
$logDir = Join-Path $cfg['OMNIVOICE_DATA_DIR'] 'logs'
$warnings = @()
if ($relayKeyState -eq 'missing') { $warnings += 'ODS_LOCAL_MODEL_RELAY_KEY missing: LLM features will need setup' }
if (-not (Test-Path -LiteralPath $distPath)) { $warnings += 'frontend/dist missing: run bun run build:web' }
$pythonExists = Test-Path -LiteralPath $pythonPath
if (-not $pythonExists) { $warnings += ("python not found: {0}" -f $pythonPath) }

$plan = [ordered]@{
    repo_root     = $root
    profile       = $ProfilePath
    python        = $pythonPath
    python_exists = $pythonExists
    dist_exists   = [bool](Test-Path -LiteralPath $distPath)
    data_dir      = $cfg['OMNIVOICE_DATA_DIR']
    log_dir       = $logDir
    port          = $port
    url           = ("http://127.0.0.1:{0}/" -f $port)
    relay_key     = $relayKeyState
    licence_mode  = $(if (@('1', 'true', 'yes', 'on') -contains ([string]$cfg['SIDESTACK_COMMERCIAL_ONLY']).ToLowerInvariant()) { 'commercial-only' } else { 'non-commercial allowed' })
    env           = $cfg
    warnings      = $warnings
}

# ── -DryRun: print the plan, exit 0. No network, no process. ─────────────────────────
if ($DryRun) {
    if ($Json) {
        $plan | ConvertTo-Json -Depth 4
    } else {
        foreach ($key in $plan.Keys) {
            $value = $plan[$key]
            if ($value -is [array]) { $value = $value -join ', ' }
            Write-Output ("{0}: {1}" -f $key, $value)
        }
    }
    exit 0
}

# ── -Stop: stop only this app's process on the port ──────────────────────────────────
if ($Stop) {
    $listen = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if (-not $listen) {
        Write-Output 'not running'
        exit 0
    }
    $ownerPid = @($listen | Select-Object -ExpandProperty OwningProcess -Unique)[0]
    $cmdline = ''
    $proc = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $ownerPid)
    if ($proc) { $cmdline = $proc.CommandLine }
    if ($cmdline -and $cmdline -match 'main\.py') {
        Stop-Process -Id $ownerPid
        Write-Output ("stopped pid {0}" -f $ownerPid)
        exit 0
    }
    Write-Output ("port {0} is used by another program (pid {1}); not stopping it" -f $port, $ownerPid)
    exit 3
}

# ── Start (the default) ──────────────────────────────────────────────────────────────
if (-not $pythonExists) {
    Write-Output ("python not found: {0}" -f $pythonPath)
    exit 2
}
if (-not $plan['dist_exists']) {
    Write-Output 'frontend/dist missing: run bun run build:web'
    exit 2
}
if ($relayKeyState -eq 'missing') {
    Write-Output 'ODS_LOCAL_MODEL_RELAY_KEY missing: LLM features will need setup'
}

$url = $plan['url']
$healthUrl = $url + 'health'
function Test-Health([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -TimeoutSec 3 -UseBasicParsing
        return ($response.StatusCode -eq 200)
    } catch { return $false }
}

$listen = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($listen) {
    if (Test-Health $healthUrl) {
        Write-Output ("already running: {0}" -f $url)
        exit 0
    }
    $otherPid = @($listen | Select-Object -ExpandProperty OwningProcess -Unique)[0]
    Write-Output ("port {0} is used by another program (pid {1}); not starting" -f $port, $otherPid)
    exit 3
}

if (-not $SkipPreflight) {
    $preflight = Join-Path $PSScriptRoot 'Test-VoiceStudioOds.ps1'
    $preflightOut = & powershell -NoProfile -ExecutionPolicy Bypass -File $preflight -Port $port -Json
    $preflightCode = $LASTEXITCODE
    if ($preflightCode -ne 0) {
        $failures = @(($preflightOut -join "`n") | ConvertFrom-Json)
        foreach ($row in $failures) {
            if ($row.PSObject.Properties['Status'] -and $row.Status -eq 'FAIL') {
                Write-Output ("{0}: {1}" -f $row.Check, $row.Detail)
            }
        }
        exit 4
    }
}

if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$outLog = Join-Path $logDir ("voicestudio-{0}.out.log" -f $stamp)
$errLog = Join-Path $logDir ("voicestudio-{0}.err.log" -f $stamp)

# Save the current environment values so the finally block can restore them exactly.
$envSaved = @{}
foreach ($key in $cfg.Keys) {
    $envSaved[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
}
$relayWasSet = -not [string]::IsNullOrEmpty($relay)
$serverModeWas = [Environment]::GetEnvironmentVariable('OMNIVOICE_SERVER_MODE', 'Process')
$apiKeyWas = [Environment]::GetEnvironmentVariable('OMNIVOICE_API_KEY', 'Process')

$proc = $null
try {
    foreach ($key in $cfg.Keys) {
        [Environment]::SetEnvironmentVariable($key, $cfg[$key], 'Process')
    }
    if ($relayWasSet) {
        [Environment]::SetEnvironmentVariable('ODS_LOCAL_MODEL_RELAY_KEY', $relay, 'Process')
    }
    [Environment]::SetEnvironmentVariable('OMNIVOICE_SERVER_MODE', $null, 'Process')
    [Environment]::SetEnvironmentVariable('OMNIVOICE_API_KEY', $null, 'Process')
    # Start through cmd.exe, without Start-Process redirection: with -Redirect*, Start-Process
    # passes inherited handles, so a caller capturing this script's output would wait until
    # Voice Studio exits. cmd.exe writes the logs; ShellExecute still passes the environment.
    $inner = '"{0}" backend\main.py 1>"{1}" 2>"{2}"' -f $pythonPath, $outLog, $errLog
    $proc = Start-Process -FilePath $env:ComSpec -ArgumentList '/d', '/s', '/c', ('"' + $inner + '"') -WorkingDirectory $root -WindowStyle Hidden -PassThru
}
finally {
    foreach ($key in $cfg.Keys) {
        if ($null -eq $envSaved[$key]) {
            [Environment]::SetEnvironmentVariable($key, $null, 'Process')
        } else {
            [Environment]::SetEnvironmentVariable($key, $envSaved[$key], 'Process')
        }
    }
    if ($relayWasSet) { [Environment]::SetEnvironmentVariable('ODS_LOCAL_MODEL_RELAY_KEY', $null, 'Process') }
    [Environment]::SetEnvironmentVariable('OMNIVOICE_SERVER_MODE', $serverModeWas, 'Process')
    [Environment]::SetEnvironmentVariable('OMNIVOICE_API_KEY', $apiKeyWas, 'Process')
}

$deadline = (Get-Date).AddSeconds($TimeoutSec)
$healthy = $false
$exited = $false
while ((Get-Date) -lt $deadline) {
    if ($proc.HasExited) { $exited = $true; break }
    if (Test-Health $healthUrl) { $healthy = $true; break }
    Start-Sleep -Seconds 1
}

function Get-LastLines([string]$Path, [int]$Count) {
    if (-not (Test-Path -LiteralPath $Path)) { return @() }
    return @(Get-Content -LiteralPath $Path -Tail $Count)
}

if ($healthy) {
    $listenPid = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)[0]
    Write-Output ("Voice Studio is running: {0} (pid {1})" -f $url, $listenPid)
    Write-Output ("log: {0}" -f $outLog)
    Write-Output ("err: {0}" -f $errLog)
    exit 0
}
if ($exited) {
    Write-Output 'process exited before /health answered'
} else {
    Write-Output ("timed out after {0} s waiting for /health" -f $TimeoutSec)
}
foreach ($line in (Get-LastLines $errLog 20)) { Write-Output $line }
exit 5
