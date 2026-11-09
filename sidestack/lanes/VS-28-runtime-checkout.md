# VS-28 — Run Voice Studio for ODS from the main checkout

- **Phase:** 4
- **Run by:** Operator (Part A: runbook text; Part B: build, task change, live check)
- **Gate:** none for Part A. Part B needs **install approval** (`bun install` in the main checkout, from `bun.lock`) and **real run approval** (re-point the VS-27 logon task, stop and start Voice Studio).
- **Depends on:** VS-27
- **Status:** verified (Part B PASS, 2026-11-08)

## Goal

The ODS link starts and serves Voice Studio from the **main checkout** (`sidestack/foundation-001`), not from the builder worktree.

**Why:**
- VS-27's logon task runs the launcher page from the builder worktree, because only that checkout had a built `frontend/dist`. The page starts the `Start-VoiceStudio-ODS.ps1` next to it, so Voice Studio's backend code and web UI also come from the worktree.
- dsh edits the worktree during every lane. A click on the ODS link mid-lane would start half-built code, and a running instance keeps serving it.
- The main checkout only moves by fast-forward to verified, committed work.

**Fix (no code change):**
- Install the frontend dependencies in the main checkout from the lockfile, then build the web UI there.
- Re-point the logon task to the main checkout's launcher page.
- Add a runbook step: after each fast-forward of the main checkout that touches `electron/`, rebuild with `bun run build:web` there.

The Python venv (`UV_PROJECT_ENVIRONMENT`) and the data folder are outside both checkouts, so they are shared and unchanged.

## Files

| Path | Change |
|---|---|
| `sidestack/ods/APPLY.md` | append: "Runtime checkout (lane VS-28)" |
| `sidestack/lanes/VS-28-runtime-checkout.md`, `sidestack/lanes/README.md` | spec / status |

Outside git (Part B): the main checkout's `node_modules` and `frontend/dist` (both gitignored), and the logon task's action.

## Preflight

```powershell
git -C <main checkout> status --short       # expect: empty
git -C <main checkout> rev-parse HEAD       # expect: equal to the worktree's HEAD
Test-Path <main checkout>rontend\dist\index.html   # expect: False (before Part B)
(Get-ScheduledTask -TaskName "SideStack Voice Studio launcher page").Actions.Arguments   # expect: the worktree's voice_studio_launcher.py
```

## Steps

**Part A (no approval):**
1. Append the "Runtime checkout (lane VS-28)" section to `sidestack/ods/APPLY.md`.
2. Run `check_sidestack.py`.

**Part B (after approval):**
1. In the main checkout, run `bun install --frozen-lockfile`, then `bun run build:web`. Record the time and whether anything came from the network.
2. Run `Start-VoiceStudio-ODS.ps1 -DryRun -Json` from the main checkout. Expect `dist_exists: true`, `python_exists: true` and `licence_mode: commercial-only`.
3. Re-point the logon task: same name, settings and principal, with the action changed to the main checkout's `voice_studio_launcher.py`. Stop the page process on 3901, then start the task.
4. Stop Voice Studio with `-Stop`. Click the ODS link: expect "Starting Voice Studio…", then Voice Studio.
5. Check the running backend's working folder is the main checkout. Check the default profile: `engine=omnivoice` → 403 `commercial_only_mode`.

## Acceptance

```powershell
python sidestack/scripts/check_sidestack.py   # expect: OK
```

Part B passes when steps 2–5 show what they expect.

## Out of scope

- Removing `node_modules` or `frontend/dist` from the builder worktree. The builder still needs them for frontend lanes.
- Rebuilding automatically on fast-forward (a git hook). The runbook step is enough for a one-person setup.
- A separate venv for the main checkout.

## Reviewer notes

- `bun install --frozen-lockfile` fails rather than changing `bun.lock`, so the main checkout stays clean (`git status` empty).
- `frontend/dist` is in `frontend/.gitignore`, and `node_modules` is gitignored too: neither shows in `git status`.
- The page's `HERE` is its own folder, so re-pointing the task's action is the whole switch. The page needs no change.

## Part B results (Operator, 2026-11-08)

The user approved Part B: the install, the task change and the restarts.

**Preflight:** the main checkout is clean, at the same commit as the worktree, and has no `frontend/dist`. The task pointed at the worktree's page. `node_modules`, `electron/node_modules` and `frontend/dist` are gitignored.

1. **Install and build (main checkout):**
   - `bun install --frozen-lockfile`: 1,145 packages in 56 s, exit 0.
   - `bun run build:web`: exit 0 in 30 s.
   - `git status` stays empty.
   - The build is 323 files and 16,103,726 bytes, the same totals as the worktree's build.
2. **Dry run (main checkout):** `repo_root` is the main checkout, with `dist_exists: true`, `python_exists: true`, `licence_mode: commercial-only` and no warnings.
3. **Task:**
   - `Set-ScheduledTask` changed only the action, to the main checkout's `voice_studio_launcher.py`. The name, logon trigger, Limited run level and settings are unchanged.
   - The old page process was stopped and the task started. The new `pythonw` command line has the main checkout's path, and `/health` → 200.
4. **Live:**
   - Voice Studio, then running from the worktree, was stopped with `-Stop`, and port 3900 was free after 2 s.
   - The ODS link → "Starting Voice Studio…" → forwarded to `http://localhost:3900/`. The backend was up about 15 s after the click check began.
   - The backend log shows it loaded `backend\config\models.yaml` from the main checkout, with no worktree path anywhere in the log.
   - `engine=omnivoice` → 403 `commercial_only_mode`.

**Verdict:** PASS.

**Rollback:** set the task's action back to the worktree's page, then restart the page process.
