# VS-12 — Upstream sync runbook and first merge

- **Phase:** 4
- **Run by:** Operator
- **Gate:** none. Fetching is read-only; the merge stays local and lands only after the checks pass; nothing is pushed.
- **Depends on:** VS-09
- **Status:** verified (first sync 2026-11-06)

## Goal

The fork takes in upstream's new commits by a repeatable procedure,
[../UPSTREAM-SYNC.md](../UPSTREAM-SYNC.md), and the first sync is done.

Measured before writing this lane (2026-11-06):
- upstream `main` is **53 commits / 54 files** ahead of the foundation's base `c88bf7006`;
- there is **no overlap** with SideStack's edited upstream files;
- **no** dependency, lock, frontend or `docs/STRUCTURE.md` changes;
- the dry merge is clean.

## Files

| Path | Change |
|---|---|
| `sidestack/UPSTREAM-SYNC.md` | create: the runbook |
| `sidestack/lanes/VS-12-upstream-sync.md`, `sidestack/lanes/README.md` | create / edit |
| *(git)* remote `upstream` | added, fetch-only (push URL disabled) |
| *(git)* the merge commit | upstream's 53 commits, merged `--no-ff` on `sidestack/sync-20261106` |

## Preflight

```powershell
git status --short                                   # expect: empty
git remote get-url --push upstream                   # expect: DISABLED-no-push-to-upstream
git merge-tree --write-tree --name-only sidestack/foundation-001 upstream/main   # expect: one tree id, no paths
```

## Steps

Follow the runbook's "Each sync" steps 1–6, using the branch name `sidestack/sync-20261106`.

## Acceptance

- The merge commit exists, with exactly two parents: the foundation and `upstream/main`.
- SideStack tests and `test_structure_doc` pass, and `check_sidestack.py` is OK.
- The full suite adds no failing id over the VS-02 list that is not explained.
- `sidestack/foundation-001` and `dsh/voicestudio-001` are fast-forwarded to the merge, and `git status` is clean in both checkouts.
- Nothing was pushed.

## Out of scope

- Pushing, and the history question about the already-pushed foundation commit (a user decision).
- Changing the VS-02 baseline file.

## Reviewer notes

**PASS, 2026-11-06 (Operator).**

- **Remote:** `upstream` = `https://github.com/debpalash/VoiceStudio.git`, push URL `DISABLED-no-push-to-upstream`.
- **Fetch:** upstream `main` = `6bb3fbc5e` (2026-11-07 01:52 +0530). 53 commits and 54 files ahead of the foundation's base `c88bf7006`, mostly electron (12), backend (9), docs (9), changelog.d (8), tests (8) and .github (7).
  - No overlap with SideStack-hooked files.
  - No dependency, lock or frontend changes, and `docs/STRUCTURE.md` unchanged.
- **Merge:** the dry run was clean. `sidestack/sync-20261106`: `git merge --no-ff upstream/main` gave **`1bcc059d9`**, with parents `0b00c0786` (foundation) and `6bb3fbc5e`. Human identity.
- **Checks on the merge:**
  - SideStack tests + `test_structure_doc`: 40 passed. `check_sidestack.py` passes.
  - Full suite (main checkout, `-n 8`, short TEMP): 12994 passed, 98 failed, 22 errors in 815 s.
    - Against the VS-02 ids, 6 new: all `tests/test_macos_notarization_api.py`. They are environment, not code. The main checkout has no `node_modules` (`bun install` was only run in the worktree), so Node cannot resolve `builder-util`. The test, `electron-builder.config.mjs` and `native-helper-build.mjs` are unchanged by the merge, and in the worktree, which has `node_modules`, the file gives 7 passed, 6 skipped.
    - The runbook now says to run the suite where `node_modules` exists.
  - Upstream fixed one baseline id: `tests/test_mobile_contract.py::test_mobile_tokens_match_electron_theme`. The `test_profile_delete_regression` pair passed again (flaky). The baseline file is unchanged, as the runbook says.
- **Landed:** `sidestack/foundation-001` and `dsh/voicestudio-001` were fast-forwarded to `1bcc059d9`, the side branch was deleted, and both checkouts are clean. Upstream ahead: 0.
- **Not pushed.** Local is now 73 commits ahead of `origin/sidestack/foundation-001` (the foundation commit alone), including upstream's 53.
