# VS-01 — Windows toolchain (`uv`, `bun`) and dependency sync

- **Phase:** 1
- **Run by:** Operator (long downloads, which exceed the harness's 600 s turn limit)
- **Gate:** **Install approval.** This installs two tools and downloads several GB of Python wheels (CUDA torch) and JS packages.
- **Depends on:** VS-00
- **Status:** verified

## Goal

The worktree has a working Python environment (`uv sync`) and JS dependencies (`bun install`), so
backend tests and the web build can run on Windows.

## Files

| Path | Change |
|---|---|
| `<worktree>\.venv\` | created by `uv sync` (gitignored upstream) |
| `<worktree>\node_modules\` | created by `bun install` (gitignored upstream) |

No tracked file changes. If `uv.lock` or `bun.lock` show as modified afterwards, revert them and
report it. The locks are upstream-owned.

## Preflight

```powershell
python --version                       # expect: Python 3.11.x
Get-Command uv, bun -ErrorAction SilentlyContinue   # expect: nothing (not installed yet)
nvidia-smi --query-gpu=name,driver_version,memory.used,memory.total --format=csv
```

## Steps (after the user approves)

1. Install `uv` and `bun` from their official installers. Read each install script before running it:
   - uv: `https://astral.sh/uv/install.ps1` (or `winget install astral-sh.uv`)
   - bun: `https://bun.sh/install.ps1` (or `winget install Oven-sh.Bun`)
2. Open a new terminal so PATH updates, then check `uv --version` and `bun --version`.
3. In the worktree, run the upstream setup, which picks the right torch build:
   ```powershell
   cd E:\SideStackAI\worktrees\deepseek\voicestudio-001
   bun install --frozen-lockfile
   bun run setup:api
   ```
   If `setup:api` asks for a GPU flavour, choose CUDA. Note the torch version it installs.
4. Check that torch sees the GPU **without loading a model**:
   ```powershell
   .\.venv\Scripts\python.exe -c "import torch;print(torch.__version__, torch.cuda.is_available())"
   ```

## Acceptance

```powershell
uv --version; bun --version                                 # expect: versions print
.\.venv\Scripts\python.exe -c "import fastapi, torch; print('ok', torch.cuda.is_available())"   # expect: ok True
git -C E:\SideStackAI\worktrees\deepseek\voicestudio-001 status --short   # expect: empty
```

## Out of scope

- Downloading TTS/ASR model weights (the app asks; nothing here triggers it).
- Starting the backend (VS-02).

## Reviewer notes

**PASS, 2026-11-05 (installs approved by the user).**

- **Preflight:** Python 3.11.2 matches `.python-version`. The VC++ runtime was already present, so setup did not install it. The NVIDIA driver is 610.88.
- **Tools:** installed with winget (`astral-sh.uv` → uv 0.13.7, `Oven-sh.Bun` → bun 1.4.4), into `%LOCALAPPDATA%\Microsoft\WinGet\Links`.
- **`bun install --frozen-lockfile`:** 1145 packages in 158 s (`node_modules` 0.8 GB).
- **`bun run setup:api`:**
  - The first run failed with a temporary DNS error resolving pypi.org on the ISP resolver.
  - The retry passed in 1279 s: 308 packages resolved, 230 installed, `.venv` 8.1 GB. It copied files because the uv cache on C: cannot hardlink to E:.
- **torch:** 2.8.0+cu128, CUDA 12.8, `cuda.is_available()` True, RTX 5090 at capability (12, 0); sm_120 is in the arch list.
- **git status:** empty, so the locks are unchanged.
- **Known, non-blocking:** `scripts/setup.py` failed to add the cuDNN 8 compatibility libraries. Its nested `uv pip install` could not lock `%LOCALAPPDATA%\uv\cache\.lock` (Access denied), because the outer `uv run` held it. Only local CTranslate2/faster-whisper on CUDA needs these, and SideStack uses ODS Whisper (Hard law 3), so it is skipped. If it is ever needed, run `uv pip install --no-deps --target .venv\Lib\site-packages\cudnn8_compat nvidia-cudnn-cu12==8.9.7.29` on its own.
- **Correction (during VS-02):** the real cause of the cuDNN failure, and of VS-02 attempt 1 failing, was the harness sandbox's Low integrity label. The in-worktree `.venv` inherited it, so its `python.exe` ran at low integrity. The venv was rebuilt with
  `UV_PROJECT_ENVIRONMENT=E:\SideStackAI\data\voice-studio\venvs\voicestudio-001 bun run setup:api`.
  - That took 117 s from the cache, and the cuDNN 8 compat step **now succeeds** (7 libraries).
  - Python runs at normal integrity, and torch 2.8.0+cu128 has CUDA True.
  - The old `.venv` was deleted, and `git status` is empty.
