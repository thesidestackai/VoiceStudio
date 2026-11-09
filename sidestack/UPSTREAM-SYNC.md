# Upstream sync runbook

How SideStack's fork takes in new commits from the original project. The fork is
`thesidestackai/VoiceStudio` (`origin`); the original project is `debpalash/VoiceStudio` (`upstream`).

## Rules

- `upstream` is **fetch-only**. Its push URL is set to `DISABLED-no-push-to-upstream`, so a push
  to it cannot happen by accident.
- Always merge (`--no-ff`), never rebase. SideStack history stays intact, and each sync is one
  commit that is easy to find and revert.
- Merge on a side branch `sidestack/sync-YYYYMMDD`. `sidestack/foundation-001` fast-forwards to
  it only after the checks below pass.
- Commits carry the human identity only, with no agent trailers (decision D6).
- Pushing to `origin` is a separate decision made by the user.

## One-time setup

```powershell
git remote add upstream https://github.com/debpalash/VoiceStudio.git
git remote set-url --push upstream DISABLED-no-push-to-upstream
```

## Each sync

1. **Fetch and measure** (read-only):
   ```powershell
   git fetch upstream main
   $base = git merge-base sidestack/foundation-001 upstream/main
   git rev-list --count sidestack/foundation-001..upstream/main            # upstream commits to take in
   git diff --name-only $base upstream/main                                 # what upstream changed
   ```
   Check four things:
   - **Overlap:** do any of these upstream files also carry SideStack edits? `AGENTS.md`, `backend/api/routers/generation.py`, `backend/api/routers/tts_stream.py`, `backend/api/routers/openai_compat.py`, `backend/services/llm_providers.py`. Every SideStack hook is marked `SideStack fork (VS-xx)`.
   - **Dependencies:** did `pyproject.toml`, `uv.lock`, `package.json` or `bun.lock` change? If so, the venv or `node_modules` need an update, which needs install approval.
   - **Frontend:** did anything under `frontend/` change? If so, rebuild the UI with `bun run build:web` where the launcher runs.
   - **Counted docs:** did `docs/STRUCTURE.md` change? It pins module counts (see VS-06).
2. **Dry merge:** `git merge-tree --write-tree --name-only sidestack/foundation-001 upstream/main`.
   It prints a tree id alone when the merge is clean, and the conflicting paths when it is not.
3. **Merge on a side branch:**
   ```powershell
   git switch -c sidestack/sync-YYYYMMDD sidestack/foundation-001
   git merge --no-ff upstream/main -m "sidestack: sync upstream main (<n> commits, YYYY-MM-DD)"
   ```
   **Conflicts in a hooked file:** keep upstream's version, re-apply the `SideStack fork (VS-xx)` block at the same anchor, and re-run the lane's tests (G10 checks that the hooks are present).
4. **Check:**
   - All SideStack tests: `tests/test_sidestack_*.py` and `tests/test_structure_doc.py`.
   - `python sidestack/scripts/check_sidestack.py`.
   - The full suite with a short `TEMP`, compared with `sidestack/tests/baselines/VS-02-failing-tests.txt`. Run it in a checkout that has
     `node_modules` (the harness worktree; the baseline was recorded there). Without it, the
     Node-based tests such as `test_macos_notarization_api` fail with `ERR_MODULE_NOT_FOUND`. A new failing id must be explained, either as SideStack's or as upstream's; known flakes are listed in the VS-06 notes. If upstream fixed baseline ids, record them, but do not edit the baseline file in the sync commit.
5. **Land:** `git switch sidestack/foundation-001`, `git merge --ff-only sidestack/sync-YYYYMMDD`, then fast-forward the harness worktree branch `dsh/voicestudio-001`. Delete the side branch.
6. **Record** the counts, test results and anything notable in the sync's lane notes, or in a dated line under "Sync log" below.

## Sync log

| Date | Upstream commits | Files | Conflicts | Result |
|---|---|---|---|---|
| 2026-11-06 | 53 (to `6bb3fbc5e`) | 54, no overlap, no deps/frontend | none | merge `1bcc059d9`; SideStack tests 40 passed; full suite adds no real failures (see VS-12) |
| 2026-11-08 | 489 measured (to `73cba3d6d`), **deferred** | 891 | 3 dry-merge conflicts (`setup/models.py`, `model-catalogue-query.ts`, `engine-family-list.tsx`) | not merged. Upstream main is 0.5.8-beta.2 with torch 2.8 → 2.10 and vitest 4 → 5. The user chose to wait for the 0.5.8 release (or the monthly date). |
