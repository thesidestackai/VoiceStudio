# VS-00 — Harness workspace and sandbox probe

- **Phase:** 1
- **Run by:** Operator (the user, with the reviewer guiding)
- **Gate:** none (no installs, no ODS changes; the harness talks to ODS through the relay as it already does)
- **Depends on:** VS-F0 committed on `sidestack/foundation-001`
- **Status:** ready

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
3. Fallback: create the worktree under `C:\Users\ssam8\SideStack\worktrees\voicestudio-001`
   (a profile path, where the sandbox can set ACLs) and repeat steps 3–5. Record which one worked
   in Reviewer notes and update `harness/README.md`.

## Out of scope

- Changing harness config (`cordis.patch.yml`), ODS, or Ollama.

## Reviewer notes

—
