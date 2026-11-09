# VS-00 — Harness workspace and sandbox probe

- **Phase:** 1
- **Run by:** Operator (the user, with the reviewer guiding)
- **Gate:** none (no installs, no ODS changes; the harness talks to ODS through the relay as it already does)
- **Depends on:** VS-F0 committed on `sidestack/foundation-001`
- **Status:** verified

## Goal

The DeepSeek Harness has a workspace on a dedicated VoiceStudio worktree, can write inside it
with the normal Workspace Write sandbox, and runs on the ODS provider.

## Files

| Path | Change |
|---|---|
| `sidestack/work/VS-00/probe.txt` | created by the harness (gitignored) |

No tracked file changes.

## Preflight

```powershell
git -C E:\SideStackAI\repositories\VoiceStudio rev-parse --abbrev-ref HEAD   # expect: sidestack/foundation-001
git -C E:\SideStackAI\repositories\VoiceStudio status --short                 # expect: empty
E:\SideStackAI\tools\deepseek-harness\Start-DeepSeekHarness-ODS.ps1 -CheckOnly  # expect: relay OK
```

## Steps

1. Create the worktree:
   ```powershell
   git -C E:\SideStackAI\repositories\VoiceStudio worktree add E:\SideStackAI\worktrees\deepseek\voicestudio-001 -b dsh/voicestudio-001 sidestack/foundation-001
   ```
2. Start the harness (desktop shortcut "DeepSeek Harness (ODS)").
3. In the harness, *Choose a workspace* → `E:\SideStackAI\worktrees\deepseek\voicestudio-001`.
4. Confirm that the header shows provider `ods` and model `default`.
5. Send this message (replace the nonce with a fresh random word):
   > Create `sidestack/work/VS-00/probe.txt` containing exactly `nonce=<NONCE>`, then read it back and print its contents. Do nothing else.

## Acceptance

```powershell
Get-Content E:\SideStackAI\worktrees\deepseek\voicestudio-001\sidestack\work\VS-00\probe.txt   # expect: nonce=<NONCE>
git -C E:\SideStackAI\worktrees\deepseek\voicestudio-001 status --short                         # expect: empty (work/ is ignored)
```

## If the sandbox refuses (ACL error like `SetNamedSecurityInfoW failed (Win32 5)`)

1. Do **not** grant `danger-full-access`.
2. Check who owns the worktree folder: `icacls E:\SideStackAI\worktrees\deepseek\voicestudio-001`.
3. Fallback: create the worktree under `%USERPROFILE%\SideStack\worktrees\voicestudio-001`
   (a profile path, where the sandbox can set ACLs) and repeat steps 3–5. Record which one worked
   in Reviewer notes and update `harness/README.md`.

## Out of scope

- Changing harness config (`cordis.patch.yml`), ODS, or Ollama.

## Reviewer notes

**PASS, 2026-11-05.**

- **Preflight:** the foundation branch was clean. The relay was up, routing to Qwen3.8-27B-UD-IQ4_XS at ctx 131072. The worktree was created at `E:\SideStackAI\worktrees\deepseek\voicestudio-001`, branch `dsh/voicestudio-001`, at the foundation commit.
- **Adding the workspace:**
  - The harness's native folder picker ("Select Workspace Directory") ended with the `dsh web` process exiting (code 255), and the browser showed `directoryPicker/pick failed: Failed to fetch`.
  - The workspace was instead added to `~/.dsh/storages/workspace.json` while the harness was stopped. The backup is `workspace.json.bak-20261105-vs00`.
  - The harness was then restarted with the launcher.
- **Probe 1** (`probe.txt`, nonce `vs00-edde42b2`):
  - The sandbox failed with `SetNamedSecurityInfoW failed (Win32 5): grantWrite(<worktree>)`, the same error seen on `E:\SideStackAI`.
  - The harness's built-in skill `diagnose-windows-sandbox-acl` then ran, **with the user's approval in the harness UI**. It found that the user lacked effective WRITE_DAC/WRITE_OWNER and added a Full Control allow ACE for the user on the worktree root and on `sidestack/` only.
  - It saved backups and restore scripts in `<worktree>/.acl-recovery/`.
  - After that, the sandbox's own grant was applied and the file was written: 19 bytes, exact.
- **Probe 2** (`probe2.txt`, nonce `vs00-2-91c4`, with ACL repair forbidden): done in 15 s with no sandbox error. The file is 17 bytes, exact.
- **git status:** empty. `/.acl-recovery/` was added to the shared `.git/info/exclude`, which is local and not committed.
- **Rollback for the ACL change:** run the `.ps1` script beside each `acl-backup-*.json` in `.acl-recovery/`. Rolling back makes the sandbox fail again.
