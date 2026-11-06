# VS-01 — Windows toolchain (`uv`, `bun`) and dependency sync

- **Phase:** 1
- **Run by:** Operator (long downloads, which exceed the harness's 600 s turn limit)
- **Gate:** **Install approval.** This installs two tools and downloads several GB of Python wheels (CUDA torch) and JS packages.
- **Depends on:** VS-00
- **Status:** ready

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

—
