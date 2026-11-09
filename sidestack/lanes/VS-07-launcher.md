# VS-07 — `Start-VoiceStudio-ODS.ps1` launcher

- **Phase:** 2
- **Run by:** dsh writes the launcher and its tests; the reviewer runs one real start afterwards
- **Gate:** none for the builder (its tests use `-DryRun` only: no process starts, no network). **Live run approval** for the reviewer's real start, whose preflight sends read-only GETs to ODS.
- **Depends on:** VS-06
- **Status:** verified (attempt 3, live run passed)

## Goal

One command starts Voice Studio natively on `http://127.0.0.1:3900/` with the SideStack ODS
profile, after a read-only ODS preflight. The relay key comes from the Windows user environment
and is never printed, logged or copied into another variable. `-Stop` stops it again, and only
it.

This lane also fixes three profile problems found while designing it:

1. **`OMNIVOICE_SERVER_MODE=1` is removed.** Upstream uses it for Docker, where the client
   address is hidden. It **turns off** the loopback gate on admin routes (`api/dependencies.py`
   `_server_mode`). Natively on 127.0.0.1 that gate works and must stay on.
2. **`LLM_DEFAULT_PROVIDER=ods`** (the VS-04 provider) replaces `custom`. The provider reads
   `ODS_LOCAL_MODEL_RELAY_KEY` itself, so no `TRANSLATE_API_KEY` copy is needed.
3. **`TRANSLATE_PROVIDER=openai`** is new. Dub translation defaults to `google`, an online service.
   `openai` is the LLM engine, which resolves through the active provider, so it uses ODS. This was
   checked: `translation_engines._configured({"id": "openai"}) == (True, "ODS (SideStack local)")`.

It also adds `OMNIVOICE_ENV_FILE`. Upstream `core/user_env.py` keeps in-app settings in
`~/.config/omnivoice/env` and loads them with override. Pointing it inside the SideStack data dir
keeps SideStack's durable settings separate from any other OmniVoice install.

## Files

| Path | Change |
|---|---|
| `sidestack/scripts/Start-VoiceStudio-ODS.ps1` | create: the contract in step 2 |
| `sidestack/config/ods.env.example` | edit: the exact replacements in step 1 |
| `tests/test_sidestack_launcher.py` | create: tests L1–L9 (step 3) |

Only these files may change. Anything else in `git status` fails the lane.

## Preflight

Start with the environment block from AGENTS-SIDESTACK.md Hard law 9, run from the worktree root.

```powershell
git status --short                                                         # expect: empty
Select-String sidestack\config\ods.env.example -Pattern '^LLM_DEFAULT_PROVIDER=custom$','^OMNIVOICE_SERVER_MODE=1$'   # expect: 2 matches
Test-Path sidestack\scripts\Start-VoiceStudio-ODS.ps1                      # expect: False
$PSVersionTable.PSVersion.Major                                            # note it; the script must also run on Windows PowerShell 5.1
& $py -m pytest tests/test_sidestack_ods_provider.py tests/test_sidestack_ods_asr.py tests/test_sidestack_admission.py -q -p no:cacheprovider   # expect: 22 passed
```

## Steps

1. **Profile (`sidestack/config/ods.env.example`).** Make exactly these replacements, and nothing else:
   - Replace the three lines
     ```
     # Phase 2 starts with the built-in "custom" provider. VS-04 adds a first-class "ods" provider.
     # TRANSLATE_API_KEY is set by the launcher from user env ODS_LOCAL_MODEL_RELAY_KEY.
     LLM_DEFAULT_PROVIDER=custom
     ```
     with
     ```
     # VS-07: the first-class "ods" provider (VS-04) reads user env ODS_LOCAL_MODEL_RELAY_KEY itself;
     # nothing copies the key. TRANSLATE_* below stay as the legacy fallback.
     LLM_DEFAULT_PROVIDER=ods
     # Dub translation uses the LLM engine through the active provider (ODS), never an online service.
     TRANSLATE_PROVIDER=openai
     ```
   - Replace the line `# OMNIVOICE_API_KEY is set by the launcher from user env SIDESTACK_VOICESTUDIO_API_KEY.` with
     `# OMNIVOICE_SERVER_MODE stays unset: it is for Docker and turns off the loopback admin gate.`
   - Replace `# VERIFY [VS-02]: it also serves frontend/dist when run natively on Windows.` with
     `# Verified 2026-11-05 (VS-02): it also serves frontend/dist when run natively on Windows.`
   - Delete the line `OMNIVOICE_SERVER_MODE=1`.
   - Directly after the line `HF_HOME=E:\SideStackAI\data\voice-studio\huggingface`, add
     `OMNIVOICE_ENV_FILE=E:\SideStackAI\data\voice-studio\omnivoice-user.env`.
2. **Create `sidestack/scripts/Start-VoiceStudio-ODS.ps1`.** It must run on Windows PowerShell 5.1: no `??`, no ternary, no `-AsHashtable`, no `&&`. Start it with comment-based help (`.SYNOPSIS`, `.PARAMETER` for each parameter, `.EXAMPLE`), `Set-StrictMode -Version Latest` and `$ErrorActionPreference = 'Stop'`.
   - **Parameters:**
     - `[string]$ProfilePath`
     - `[switch]$DryRun`, `[switch]$Json`, `[switch]$SkipPreflight`, `[switch]$Stop`, `[switch]$NoUserEnv`
     - `[int]$TimeoutSec = 90`
   - **Paths:**
     - Repo root = `(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path`.
     - Default `$ProfilePath` = `<root>\sidestack\config\ods.env` if that file exists, otherwise `<root>\sidestack\config\ods.env.example`.
   - **Profile parsing:** trim each line and skip blanks and lines starting with `#`. Every other line must be `KEY=VALUE` with KEY matching `^[A-Z][A-Z0-9_]*$`. Otherwise write `profile line <n>: not KEY=VALUE` to stderr and `exit 2`.
   - **Profile validation** (each failure: one clear stderr line, then `exit 2`; never echo a value from a secret-named key):
     - `OMNIVOICE_BIND_HOST` must be `127.0.0.1`.
     - `OMNIVOICE_PORT` must be an integer from 1 to 65535.
     - `UV_PROJECT_ENVIRONMENT` and `OMNIVOICE_DATA_DIR` must be present.
     - `OMNIVOICE_SERVER_MODE`, if present, must be empty, `0`, `false`, `no` or `off`.
     - No key matching `KEY|TOKEN|SECRET|PASSWORD` may have a non-empty value. Message: `<KEY> must not have a value in the profile; secrets come from user env`.
   - **Relay key:**
     - `$relay` = process env `ODS_LOCAL_MODEL_RELAY_KEY`. If that is empty and `-NoUserEnv` is not set, use `[Environment]::GetEnvironmentVariable('ODS_LOCAL_MODEL_RELAY_KEY','User')`.
     - `relay_key` is the string `present` or `missing`. The value itself is never written to output, a file, a log or another variable name.
   - **Plan:** an ordered object with:
     - `repo_root`, `profile`
     - `python` (`<UV_PROJECT_ENVIRONMENT>\Scripts\python.exe`) and `python_exists`
     - `dist_exists` (`<root>\frontend\dist\index.html`)
     - `data_dir`, `log_dir` (`<OMNIVOICE_DATA_DIR>\logs`)
     - `port`, `url` (`http://127.0.0.1:<port>/`)
     - `relay_key`
     - `env` (the profile's KEY→VALUE map, which never contains the relay key)
     - `warnings` (string array)

     Add these warnings when they apply: `ODS_LOCAL_MODEL_RELAY_KEY missing: LLM features will need setup`, `frontend/dist missing: run bun run build:web`, `python not found: <path>`.
   - **`-DryRun`:** print the plan (`ConvertTo-Json -Depth 4` with `-Json`, readable `key: value` lines without it) and `exit 0`. Never contact the network and never start a process.
   - **`-Stop`:**
     - If nothing listens on the port: print `not running` and `exit 0`.
     - Otherwise take the owning PID. Only if `(Get-CimInstance Win32_Process -Filter "ProcessId=<pid>").CommandLine` matches `main\.py`, run `Stop-Process -Id <pid>`, print `stopped pid <pid>` and `exit 0`.
     - Otherwise print `port <port> is used by another program (pid <pid>); not stopping it` and `exit 3`.
   - **Start** (the default):
     1. If `python_exists` or `dist_exists` is false: print the matching warning and `exit 2`. If the relay key is missing, print its warning and continue.
     2. If something listens on the port: when `GET <url>health` returns 200, print `already running: <url>` and `exit 0`; otherwise print the in-use message and `exit 3`.
     3. Unless `-SkipPreflight`, run `powershell -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\Test-VoiceStudioOds.ps1" -Port <port> -Json`. If its exit code is not 0, print every row whose `Status` is `FAIL` as `<Check>: <Detail>` and `exit 4`.
     4. In `try`/`finally`:
        - Save the current values, then set each profile key in `$env:`, plus `$env:ODS_LOCAL_MODEL_RELAY_KEY = $relay` when it is present.
        - Remove `$env:OMNIVOICE_SERVER_MODE` and `$env:OMNIVOICE_API_KEY` for the child.
        - Create `log_dir` and run `Start-Process -FilePath <python> -ArgumentList 'backend\main.py' -WorkingDirectory <root> -WindowStyle Hidden -PassThru` with `-RedirectStandardOutput` and `-RedirectStandardError` going to `<log_dir>\voicestudio-<yyyyMMdd-HHmmss>.out.log` and `.err.log`.
        - In `finally`, restore every saved value, removing the ones that did not exist before.
     5. Poll `GET <url>health` once a second until it returns 200 or `$TimeoutSec` passes.
        - On 200: print `Voice Studio is running: <url> (pid <pid>)` and the log paths, then `exit 0`.
        - If the process exited first, or on timeout: print the last 20 lines of the `.err.log` and `exit 5`.
   - **Exit codes:** 0 ok, 2 configuration, 3 port conflict, 4 preflight failed, 5 start failed.
3. **Create `tests/test_sidestack_launcher.py`.**
   - A helper runs `["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", SCRIPT, *args]` with `capture_output=True, text=True, timeout=60` and a given env dict (a copy of `os.environ`, adjusted), and returns `(code, stdout + stderr)`.
   - `win_only = pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"), reason="Windows launcher")`.
   - Profiles for L4–L7 are written to `tmp_path` and passed with `-ProfilePath`.
   - Tests:
     - **L1** (`win_only`) `-DryRun -Json` with the default profile: exit 0, and the JSON shows:
       - `url == "http://127.0.0.1:3900/"`;
       - `env["LLM_DEFAULT_PROVIDER"] == "ods"`, `env["TRANSLATE_PROVIDER"] == "openai"` and `env["SIDESTACK_VRAM_ADMISSION"] == "1"`;
       - `"OMNIVOICE_SERVER_MODE" not in env`;
       - `python` ends with `\Scripts\python.exe`.
     - **L2** (`win_only`) With env `ODS_LOCAL_MODEL_RELAY_KEY=test-relay-key-7f3a9c`, run `-DryRun -Json` and also plain `-DryRun`.
       - In both runs, `relay_key` is `present` (JSON case), and the marker string does not appear in the output.
       - Assert through a precomputed bool (`leaked = marker in out; assert not leaked, "relay key printed"`), so a failure cannot echo output.
     - **L3** (`win_only`) `-DryRun -Json -NoUserEnv` with `ODS_LOCAL_MODEL_RELAY_KEY` removed from env: exit 0, `relay_key == "missing"`, and one warning mentions `ODS_LOCAL_MODEL_RELAY_KEY`.
     - **L4** (`win_only`) A profile containing `NOT A KV LINE`: exit 2, and the output mentions `line`.
     - **L5** (`win_only`) A copy of the example profile with `OMNIVOICE_BIND_HOST=0.0.0.0`: exit 2.
     - **L6** (`win_only`) A copy with `OMNIVOICE_SERVER_MODE=1` added: exit 2.
     - **L7** (`win_only`) A copy with `TRANSLATE_API_KEY=zz-secret-41` added: exit 2. The string `zz-secret-41` is not in the output (checked through a precomputed bool).
     - **L8** (any OS) Parse `sidestack/config/ods.env.example` the way `_profile()` in `tests/test_sidestack_ods_asr.py` does. Check:
       - `LLM_DEFAULT_PROVIDER == "ods"` and `TRANSLATE_PROVIDER == "openai"`;
       - `OMNIVOICE_SERVER_MODE` is absent;
       - `OMNIVOICE_ENV_FILE` starts with the `OMNIVOICE_DATA_DIR` value.
     - **L9** (any OS) Dub translation resolves to ODS. Copy the `lp` fixture from `tests/test_llm_providers.py` lines 22–42, which uses `clean_llm_env` and an in-memory `settings_store`. Set `LLM_DEFAULT_PROVIDER`, `TRANSLATE_PROVIDER`, `TRANSLATE_BASE_URL` and `TRANSLATE_MODEL` from the profile, and `ODS_LOCAL_MODEL_RELAY_KEY=dummy`. Then `importlib.import_module("services.translation_engines")._configured({"id": "openai"}) == (True, "ODS (SideStack local)")`.

## Acceptance

```powershell
# (environment block from AGENTS-SIDESTACK Hard law 9 first)
& $py -m pytest tests/test_sidestack_launcher.py -q -p no:cacheprovider      # expect: 9 passed
& $py -m pytest tests/test_sidestack_ods_provider.py tests/test_sidestack_ods_asr.py tests/test_sidestack_admission.py -q -p no:cacheprovider   # expect: 22 passed
powershell -NoProfile -ExecutionPolicy Bypass -File sidestack\scripts\Start-VoiceStudio-ODS.ps1 -DryRun   # expect: exit 0, readable plan, relay_key present
git status --short    # expect: exactly the 3 files above
python sidestack/scripts/check_sidestack.py           # expect: OK
```

The reviewer also:
- runs PSScriptAnalyzer if it is installed (otherwise reads the script for 5.1 incompatibilities), and runs the script under Windows PowerShell 5.1;
- mutation-checks the tests: drop the BIND_HOST check → L5 fails; print `$relay` in the plan → L2 fails; drop the secret-key check → L7 fails;
- with approval, runs one real start and stop: `Start-VoiceStudio-ODS.ps1` (with preflight), then `/health`, `/` and the bind address, then `-Stop`. It records the log paths and confirms that the key appears in neither log.

## Out of scope

- The ODS Applications entry (VS-08), and anything that changes ODS.
- Loading TTS models, desktop shortcuts and autostart.
- Docs (`ARCHITECTURE.md`, `ods/APPLY.md`). The reviewer updates them.

## Attempt 2 — rework (builder runs this section only)

The worktree holds attempt 1's uncommitted work. Start with the environment block from
AGENTS-SIDESTACK.md Hard law 9; note that it now also sets `TMPDIR`. Before the first pytest,
print `$env:TEMP` and `$env:TMPDIR` and include both in the report.

1. **Preflight.** `git status --short` must show exactly these lines, in any order; otherwise report BLOCKED:
   ```
    M sidestack/config/ods.env.example
    M sidestack/scripts/Test-VoiceStudioOds.ps1
   ?? sidestack/scripts/Start-VoiceStudio-ODS.ps1
   ?? tests/test_sidestack_launcher.py
   ```
2. **Revert** the out-of-scope edit: `git checkout -- sidestack/scripts/Test-VoiceStudioOds.ps1`. That script never calls `Write-Error`, so it did not have the problem.
3. **`Start-VoiceStudio-ODS.ps1`.** Make only these changes:
   1. **`-Stop` is broken.** `$pid` is PowerShell's read-only automatic `$PID`. The reviewer reproduced it: "Cannot overwrite variable PID", exit 3, with the Voice Studio stand-in left running. Rename the variable to `$ownerPid` everywhere in the `-Stop` block.
   2. Rename the variable `$profile` (it shadows the automatic `$PROFILE`) to `$cfg` everywhere.
   3. Restore `$ErrorActionPreference = 'Stop'` directly after `Set-StrictMode -Version Latest`, in place of the comment that explains its removal. Replace **both** `Write-Error ...` calls (the line-parse failure and `Fail-Profile`) with `[Console]::Error.WriteLine(...)` and the same message, so the next `exit 2` runs.
   4. **Run the preflight once.** Use `$preflightOut = & powershell -NoProfile -ExecutionPolicy Bypass -File $preflight -Port $port -Json` and `$preflightCode = $LASTEXITCODE`. On a non-zero code, parse `($preflightOut -join "`n") | ConvertFrom-Json` and print the `FAIL` rows, then `exit 4`. Delete the second invocation, and do not print the JSON on success.
4. **Tests.** Add these to `tests/test_sidestack_launcher.py`, all `win_only`, each in `try`/`finally` that kills the child it started:
   - A helper writes a stand-in server to `tmp_path / <name>`. It is an `http.server` that answers 200 on any GET and binds `127.0.0.1` on the port in `sys.argv[1]`.
   - Get a free port from `socket.socket().bind(("127.0.0.1", 0))`.
   - Write a profile copy with `OMNIVOICE_PORT=<port>`.
   - Start the stand-in with `subprocess.Popen([sys.executable, str(script), str(port)])`, and wait up to 10 s until the port accepts a connection.
   - Tests:
     - **L10** Stand-in named `main.py`: `-Stop -ProfilePath <copy>` exits 0, the output contains `stopped pid`, and `proc.wait(timeout=10)` returns.
     - **L11** Stand-in named `server.py`: `-Stop` exits 3, the output contains `another program`, and `proc.poll() is None` afterwards (it is untouched).
     - **L12** Nothing on the free port: `-Stop` exits 0, and the output contains `not running`.
5. **Acceptance:**
   ```powershell
   & $py -m pytest tests/test_sidestack_launcher.py -q -p no:cacheprovider      # expect: 12 passed
   & $py -m pytest tests/test_sidestack_ods_provider.py tests/test_sidestack_ods_asr.py tests/test_sidestack_admission.py -q -p no:cacheprovider   # expect: 22 passed
   powershell -NoProfile -ExecutionPolicy Bypass -File sidestack\scripts\Start-VoiceStudio-ODS.ps1 -DryRun   # expect: exit 0
   git status --short    # expect: exactly M ods.env.example, ?? Start-VoiceStudio-ODS.ps1, ?? tests/test_sidestack_launcher.py
   Get-ChildItem -Force | Where-Object Name -match '^(pytest-of-|omnivoice-test-data-)'   # expect: nothing
   python sidestack/scripts/check_sidestack.py           # expect: OK
   ```
   Finish with the AGENTS-SIDESTACK §4 report format (LANE / STATUS / FILES CHANGED / COMMANDS RUN / NOT DONE) and nothing else.

## Attempt 3 — rework (builder runs this section only)

The live run (approved, 2026-11-06) worked, but it exposed one defect. `Start-Process` with
`-RedirectStandardOutput`/`-RedirectStandardError` starts the child with inherited handles. So a caller
that **captures** the launcher's output (`$x = & powershell -File ...`, a scheduled task, a future
ODS launcher) waits until Voice Studio exits. The reviewer's captured start returned only after
`-Stop`, 269 s later. A prototype confirmed it: the old way took 20.4 s against a 20 s stand-in,
while `cmd /c` with its own redirection returned in 2.4 s, with the env inherited and both logs written.

Start with the Hard law 9 environment block.

1. **Preflight.** `git status --short` must show exactly these lines, in any order; otherwise report BLOCKED:
   ```
    M sidestack/config/ods.env.example
    M sidestack/lanes/VS-07-launcher.md
   ?? sidestack/scripts/Start-VoiceStudio-ODS.ps1
   ?? tests/test_sidestack_launcher.py
   ```
2. **`Start-VoiceStudio-ODS.ps1`.** Make only these changes.
   1. Replace the one `$proc = Start-Process -FilePath $pythonPath ... -RedirectStandardOutput $outLog -RedirectStandardError $errLog` line with:
      ```powershell
          # Start through cmd.exe, without Start-Process redirection: with -Redirect*, Start-Process
          # passes inherited handles, so a caller capturing this script's output would wait until
          # Voice Studio exits. cmd.exe writes the logs; ShellExecute still passes the environment.
          $inner = '"{0}" backend\main.py 1>"{1}" 2>"{2}"' -f $pythonPath, $outLog, $errLog
          $proc = Start-Process -FilePath $env:ComSpec -ArgumentList '/d', '/s', '/c', ('"' + $inner + '"') -WorkingDirectory $root -WindowStyle Hidden -PassThru
      ```
   2. In the `if ($healthy)` block, before printing, set `$listenPid = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)[0]`. Print `Voice Studio is running: <url> (pid <listenPid>)` instead of `$proc.Id`. `$proc.Id` is now `cmd.exe`, not the listener `-Stop` targets.
3. **Test L13** (any OS) in `tests/test_sidestack_launcher.py`: the launcher's source text contains neither `-RedirectStandardOutput` nor `-RedirectStandardError`, and does contain `$env:ComSpec`.
4. **Acceptance:** `tests/test_sidestack_launcher.py` gives 13 passed, the other 22 SideStack tests pass, and `-DryRun` exits 0. `git status --short` shows the same 4 lines as the preflight. There are no `pytest-of-*`/`omnivoice-test-data-*` entries in the root, and `check_sidestack.py` is OK. Do **not** start Voice Studio; the reviewer re-runs the live start. Finish with the §4 report format and list every acceptance command under COMMANDS RUN.

## Reviewer notes

**Attempt 1, 2026-11-06: FAIL (rework).**

- **Builder (dsh on ODS, full access):** 30 m 47 s, 100 steps, about 4.6M tokens, with two context compactions.
  - It stopped once to ask about a preflight mismatch. Its grep tool missed `OMNIVOICE_SERVER_MODE=1` because of CRLF endings; `Select-String` finds both lines. The reviewer answered "proceed".
  - It found and fixed a real PowerShell precedence bug in its own code: `-not @(...) -contains x` parses as `(-not @(...)) -contains x`.
  - It did not use the §4 report format.
- **Good:**
  - The profile diff is exactly step 1.
  - The script structure, help, validation, relay-key handling and env save/restore follow the contract.
  - Tests L1–L9 match the spec. The reviewer's re-run: 31 passed across the four SideStack test files.
- **Problems:**
  1. **`-Stop` cannot work.** It assigns to the read-only `$PID`. Reproduced against a stand-in `main.py` server: "Cannot overwrite variable PID", exit 3, server left running. The spec had no `-Stop` test; that was a spec gap, now covered by L10–L12.
  2. It removed `$ErrorActionPreference = 'Stop'` from the launcher, against the spec, because `Write-Error` under Stop ends the script with exit 1. The correct fix is writing to stderr directly and keeping Stop.
  3. **Out of scope:** it made the same edit in `Test-VoiceStudioOds.ps1`, which has no `Write-Error`.
  4. The preflight runs twice when it fails (two rounds of ODS GETs).
  5. The `$profile` variable shadows `$PROFILE`.
  6. **Residue:** 15 `omnivoice-test-data-*` folders and `pytest-of-<user>` (12 profile files) in the worktree root, all from this session. The reviewer removed them. The likely cause is an inherited `TMPDIR`, which Python's `tempfile` prefers over `TEMP`. Hard law 9 now sets `TMPDIR` too.

**Attempt 2, 2026-11-06: offline PASS. Live run pending approval.**

- **Builder (fresh session):** 2 m 18 s, 13 steps, about 557k tokens. Report: DONE, 12 passed.
  - It used the §4 headings, but listed only the launcher test run under COMMANDS RUN. It did not show `TEMP`/`TMPDIR` as asked.
  - Hashes: launcher `67F75E4E6CF6`, profile `148101F7EBA2` (unchanged from attempt 1).
- **Fixes, all checked in the source:**
  - No `$pid` or `$profile` assignments remain (`$ownerPid`, `$cfg`).
  - `$ErrorActionPreference = 'Stop'` is restored. Both failure paths write through `[Console]::Error.WriteLine` and no `Write-Error` remains.
  - The preflight is invoked once.
  - `Test-VoiceStudioOds.ps1` is identical to HEAD.
  - It parses with zero errors under Windows PowerShell 5.1.26100. PSScriptAnalyzer is not installed.
- **Reviewer fix-ups (tests only):**
  - L11 did not assert that the other program survives `-Stop`. The reviewer added `time.sleep(1); assert proc.poll() is None`.
  - L10 polled immediately, which races the venv python launcher, and leaked the stand-in on failure. The reviewer changed it to `proc.wait(timeout=10)` inside `try`/`finally`.
- **Reviewer re-run:** launcher tests 12 passed, the other SideStack tests 22 passed. `-DryRun` exits 0 with `relay_key: present` and no warnings.
  - The relay key is referenced only where it is read and where it is set into the child's environment.
  - No residue in the root. `check_sidestack.py` passes.
- **Mutation checks** on the launcher, restored by SHA-256:
  - Drop the BIND_HOST check: L5 failed.
  - Print `$relay` in the plan: L2 and L3 failed.
  - Drop the secret-key check: L7 failed.
  - Stop any owner: L11 failed (only with the reviewer's fix-up).
  - Never stop: L10 failed.
- The full suite was not re-run. The lane adds no upstream code; the profile change is covered by the 22 SideStack tests.

**Live run 1 (attempt 2 launcher, user-approved), 2026-11-06:**

- **Start:** the preflight passed, and the launcher exited 0 with "Voice Studio is running: http://127.0.0.1:3900/ (pid 35288)" and both log paths.
  - 35288 is the venv `python.exe` launcher. The listener is its child, 40196.
- **Checks:**
  - Listener on `127.0.0.1:3900` only.
  - `/health` 200 (`cuda (NVIDIA GeForce RTX 5090)`, 0.5.7).
  - `/` 200 text/html, 7264 bytes, `<title>VoiceStudio</title>`.
  - `/v1/models`: the first call timed out at 5 s during deferred start-up (GPU pool sizing); the retry gave 200 in 2 s.
- **Key scan:** the relay key was in **none** of the 10 files written under the data dir, read with shared access while the app ran, nor in the two launcher logs and `omnivoice.log` after the stop.
- **`-Stop`:** exit 0, `stopped pid 40196`. The port was free and no `main.py` process was left. A second `-Stop` gave exit 0 and `not running`.
- **Side effects:**
  - The real data dir was initialised: database migrated to 0017, demo voice profile seeded, `prefs.json`.
  - No model was loaded ("Preload skipped: the OmniVoice model licence is not accepted yet").
  - Free VRAM was 28.1 GB at start-up.
- **Defect (fixed by attempt 3):** the captured start returned only after `-Stop`, because of inherited handles. See attempt 3.
- **Gaps for VS-09:**
  - The dictation (capture) ASR auto-selected `pytorch-whisper`, a local Whisper. Nothing loaded, but using dictation would break Hard law 3. Pin it to ODS Whisper if upstream supports that.
  - The stored translation preference reconciled to `argos` (offline), which overrides `TRANSLATE_PROVIDER=openai` in the UI default.

**Attempt 3, 2026-11-06: PASS.**

- **Builder (fresh session):** 1 m 28 s, 15 steps, about 606k tokens. It reported DONE in the full §4 format, with every acceptance command listed: 13 passed, 22 passed, `-DryRun` exit 0, the same 4 status lines, no residue, validator OK.
  - Hashes: launcher `EC85AF1EA4FA`, tests `F892EE7CAC5E`.
- **Diff:** exactly the step 2 block (`cmd.exe /d /s /c` with its own redirection, and `$listenPid` in the success message), plus L13. The reviewer's L10/L11 fix-ups are intact.
- **Reviewer re-run:** 35 passed across the four SideStack test files. All five launcher mutations were caught again, and the file was restored by SHA-256.
- **Live run 2 (same approval, re-run on the fixed launcher):**
  - The **captured** start returned in 11 s, including the ODS preflight and `/health` wait; before the fix it hung until stopped. Exit 0, with "Voice Studio is running: http://127.0.0.1:3900/ (pid 47036)", where 47036 is the listener itself.
  - Checks: `127.0.0.1:3900` only; `/health`, `/` and `/v1/models` all 200.
  - The relay key was in none of the 7 new files.
  - `-Stop`: exit 0, `stopped pid 47036`. The port was free afterwards, and no `cmd.exe`/`main.py` process was left.
- No residue. `check_sidestack.py` passes.
