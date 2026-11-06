# VS-02 — Offline test baseline and headless web mode

- **Phase:** 1
- **Run by:** dsh (targeted commands) + Operator (the full suite, if it runs longer than 10 minutes)
- **Gate:** none (no network, no models; the backend starts on loopback with no engines loaded)
- **Depends on:** VS-01
- **Status:** ready

## Goal

1. Record how many offline backend tests pass on Windows before any SideStack code change. This is the baseline every later lane compares against.
2. Confirm the backend runs natively on `127.0.0.1:3900` and serves the built web UI, which is what the ODS Applications link will open.

## Files

| Path | Change |
|---|---|
| `sidestack/work/VS-02/baseline.md` | create (gitignored): commands, counts, failures with their first error line |

No tracked file changes.

## Preflight

```powershell
cd E:\SideStackAI\worktrees\deepseek\voicestudio-001
git status --short                    # expect: empty
.\.venv\Scripts\python.exe -c "import fastapi"   # expect: no error
```

## Steps

1. Offline test environment for every test command in this lane:
   ```powershell
   $env:HF_HUB_OFFLINE = "1"
   $env:HF_HUB_CACHE = "$PWD\sidestack\work\VS-02\empty-hf-cache"
   New-Item -ItemType Directory -Force $env:HF_HUB_CACHE | Out-Null
   ```
2. Targeted suites first, so each turn stays under 600 s:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_llm_providers.py tests/test_llm_providers_router.py -q
   .\.venv\Scripts\python.exe -m pytest backend/tests -q -x --timeout=300
   ```
   (If `--timeout` is unknown, drop it.)
3. Full suite (`tests/`): the **operator** runs it in the background, because it can take longer than 10 minutes:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider > sidestack\work\VS-02\full-suite.txt 2>&1
   ```
4. Web build, then the backend on loopback with **no** model loads:
   ```powershell
   bun run build:web
   $env:OMNIVOICE_BIND_HOST = "127.0.0.1"; $env:OMNIVOICE_PORT = "3900"
   $env:OMNIVOICE_DATA_DIR = "$PWD\sidestack\work\VS-02\data"
   .\.venv\Scripts\python.exe backend\main.py
   ```
   In a second terminal: `curl.exe -s http://127.0.0.1:3900/health` and
   `curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:3900/`. Then stop the backend.
5. Write `baseline.md`: pass/fail/skip counts per command, each failing test id with its first
   error line, whether `/` served the UI (HTTP 200 + HTML) or a different path is needed.

## Acceptance

```powershell
Test-Path sidestack\work\VS-02\baseline.md     # expect: True
git status --short                              # expect: empty
python sidestack/scripts/check_sidestack.py     # expect: OK
```

The reviewer accepts failing upstream tests when they are recorded with their reasons. Known Windows-only failures become the baseline.

## Out of scope

- Fixing upstream test failures.
- Configuring ODS (VS-03), downloading models, or opening the UI in a browser beyond the curl checks.

## Reviewer notes

—
