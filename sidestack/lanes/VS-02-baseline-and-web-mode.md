# VS-02 — Offline test baseline and headless web mode

- **Phase:** 1
- **Run by:** dsh runs the targeted tests and writes `baseline.md`; the Operator runs the full suite and web mode
- **Gate:** none (no network, no models; the backend starts on loopback with no engines loaded)
- **Depends on:** VS-01
- **Status:** verified

## Goal

1. Record how many offline tests pass on Windows before any SideStack code change. This is the baseline every later lane compares against.
2. Confirm the backend runs natively on `127.0.0.1:3900` and serves the built web UI, which is what the ODS Applications link will open.

## Files

| Path | Change |
|---|---|
| `sidestack/work/VS-02/baseline.md` | create (gitignored): commands, counts, failures with their first error line |

No tracked file changes.

## Preflight

Start with the environment block from AGENTS-SIDESTACK.md Hard law 9, run from the worktree root.

```powershell
git status --short                 # expect: empty
Test-Path .venv                    # expect: False (the venv lives outside the worktree)
& $py -c "import fastapi; print('ok')"   # expect: ok
```

## Steps

1. **Builder (dsh): targeted suites.** Keep each command under 9 minutes, and put the environment block in front of each one:
   ```powershell
   & $py -m pytest tests/test_llm_providers.py tests/test_llm_providers_router.py tests/test_lmstudio_model_discovery.py -q -p no:cacheprovider
   & $py -m pytest backend/tests -q -x -p no:cacheprovider
   ```
2. **Builder (dsh):** write `sidestack/work/VS-02/baseline.md` with:
   - each command, its pass/fail/skip counts and exit code;
   - every failing test id with its first error line;
   - the sections "Full suite (operator)" and "Web mode (operator)", each containing only `PENDING`.
3. **Operator: full suite**, run in the background at normal integrity, with the operator's own temp folder:
   ```powershell
   $env:HF_HUB_OFFLINE="1"; $env:HF_HUB_CACHE="$PWD\sidestack\work\VS-02\empty-hf-cache"
   & $py -m pytest tests -n 8 -q -p no:cacheprovider > sidestack\work\VS-02\full-suite.txt 2>&1
   ```
4. **Operator: web mode.** Run `bun run build:web`, then start the backend with
   `OMNIVOICE_BIND_HOST=127.0.0.1`, `OMNIVOICE_PORT=3900`,
   `OMNIVOICE_DATA_DIR=E:\SideStackAI\data\voice-studio\vs02-scratch` and `HF_HUB_OFFLINE=1`:
   `& $py backend\main.py`. Check `/health`, check that `/` returns the UI's HTML, and check that the
   listener is bound to 127.0.0.1 only. Then stop it.
5. **Operator:** fill in the two PENDING sections of `baseline.md`.

## Acceptance

```powershell
Test-Path sidestack\work\VS-02\baseline.md     # expect: True
Select-String sidestack\work\VS-02\baseline.md -Pattern PENDING   # expect: no match after step 5
git status --short                              # expect: empty
python sidestack/scripts/check_sidestack.py     # expect: OK
```

The reviewer accepts failing upstream tests when they are recorded with their reasons. Known Windows-only failures become the baseline.

## Out of scope

- Fixing upstream test failures.
- Configuring ODS (VS-03), downloading models, or opening the UI in a browser beyond the HTTP checks.

## Reviewer notes

- **Attempt 1, 2026-11-05: BLOCKED.**
  - The `.venv` inside the worktree had inherited the harness sandbox's Low integrity label, so Python ran at low integrity. Its effects: "Access denied" on the backend data dir, a hung full suite, and stray temp folders in the worktree.
  - The builder correctly reported BLOCKED, because preflight found an untracked-file residue.
  - Fixes: the venv was moved to `E:\SideStackAI\data\voice-studio\venvs\voicestudio-001`, the residue was removed, and Hard law 9 was added.
- **Attempt 2, 2026-11-05: PASS.**
  - **Builder (dsh on ODS):** finished in 2 m 29 s and about 469k tokens. It reported DONE.
    - Targeted suites: **117 passed**. `backend/tests -x` stopped at its first failure after 75 passed.
    - It also cleaned stray temp folders from the root itself; a few tests still write to the cwd.
    - The `baseline.md` sha256 starts `88c5d95d25fb`, which matches its report.
  - **Reviewer re-run:** 117 passed, which matches. `backend/tests` in full gave **581 passed, 2 failed, 9 skipped**.
    - The builder's note "host has no CUDA" is wrong: the test also fails at normal integrity with CUDA available.
  - **Full suite (operator):** **12877 passed, 95 failed, 20 errors, 134 skipped** in 383 s.
    - The failures are in 30 files, mostly release, Electron, mobile, CI and Docker tooling, plus ffmpeg missing on Windows.
    - Their ids are in [../tests/baselines/VS-02-failing-tests.txt](../tests/baselines/VS-02-failing-tests.txt). A later lane fails if it adds an id.
    - The file lives under a `tests/` directory on purpose: one parametrized id contains a fake address (`…@abc.googleusercontent.com`), and upstream `tests/test_contact_emails.py` exempts only test paths. Its first location, `sidestack/lanes/baselines/`, made that test fail (found in VS-04 review).
    - When running the full suite, keep `TEMP` short (for example `E:\SideStackAI\data\voice-studio\pytmp`). With a long temp path, `tests/test_identity_gate.py` errors at setup under `-n 8`, because nested git repos exceed the Windows path limit.
  - **Web mode (operator):**
    - `build:web` took 24 s, and the backend started in 4 s on `127.0.0.1:3900` only.
    - `/health` returns 200 with device cuda, `/` serves the UI (`<title>VoiceStudio</title>`), and `/v1/models` returns 200 with no key in desktop mode. No model was loaded.
  - **Result:** `git status` is empty, there are no PENDING sections, and `check_sidestack.py` passes.
