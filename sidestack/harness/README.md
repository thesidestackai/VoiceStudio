# Building Voice Studio with the DeepSeek Harness

The DeepSeek Harness (`dsh web`, npm `@deepseek-ai/dsh`) is the builder for SideStack lanes. It
runs on Windows at `http://localhost:3080` and uses the **ODS** provider: the local model relay
`127.0.0.1:4007`, model `default` (Qwen 3.8 27B, 128k context). A reviewer agent writes each
lane spec and verifies the result on disk.

## Roles

| Role | Who | Does |
|---|---|---|
| Owner | the user | Approves gates (installs, ODS probes/changes, real runs, pushes). Starts ODS and the harness. |
| Reviewer | Claude Code / Codex | Writes lane specs, stages exact files with hashes, verifies on disk, drafts commit messages. |
| Builder | DeepSeek Harness (ODS) | Executes one lane spec in its worktree and reports in the AGENTS-SIDESTACK §4 format. |

## One-time setup (lane VS-00)

1. **Worktree** (outside the main checkout, one per lane series):
   ```powershell
   cd E:\SideStackAI\repositories\VoiceStudio
   git worktree add E:\SideStackAI\worktrees\deepseek\voicestudio-001 -b dsh/voicestudio-001 sidestack/foundation-001
   ```
2. **Start the harness** with the desktop shortcut "DeepSeek Harness (ODS)", or
   `E:\SideStackAI\tools\deepseek-harness\Start-DeepSeekHarness-ODS.ps1`.
   Check first with `-CheckOnly`.
3. **Add the workspace** in the harness UI: *Choose a workspace* →
   `E:\SideStackAI\worktrees\deepseek\voicestudio-001`. Use the worktree itself, **not**
   `E:\SideStackAI`, where the Workspace Write sandbox failed with an ACL error.
4. **Sandbox probe:** ask the harness to create `sidestack/work/VS-00/probe.txt` with a nonce you
   give it, then read it back. If the sandbox refuses, see the VS-00 fallback. Never grant
   `danger-full-access`.
5. **Model check:** the harness header must show provider `ods`, model `default`, and a context
   of 131072 (or 65536 if ODS was switched back to 64k).

## Lane loop

```
Reviewer: write lanes/VS-xx-*.md  ──►  stage long files in sidestack/work/VS-xx/ (+ SHA-256)
Owner:    open dsh on the worktree, paste KICKOFF-PROMPT.md with LANE=VS-xx
Builder:  read AGENTS-SIDESTACK.md + the lane spec → change files → run acceptance → report
Reviewer: re-run acceptance, compare hashes, git status, check_sidestack.py → PASS/FAIL notes
Owner:    approve commit → one commit per lane (human identity) → push only when you choose
```

## Working within the harness limits

| Limit | Consequence | Rule |
|---|---|---|
| The router returns tool-bearing turns as **one chunk** | No live streaming; long turns look frozen | Expect silence; judge progress by files on disk |
| Turns over **600 s** fail | Big installs or full test suites in one turn break the run | Give exact *targeted* test commands; the operator runs full suites and installs |
| **128k** context, and the repo is large (`CLAUDE.md` alone is ~24 KB) | The model drifts or compacts if it reads widely | The spec names exact files and line anchors; the builder reads only those plus AGENTS-SIDESTACK.md |
| One GPU, shared with ODS Whisper and later TTS | Generation slows when other models are resident | Don't run Voice Studio TTS while a harness lane is active |
| Agent reports can be wrong | False PASS | Reviewer verification is the only PASS |

## Useful extras

- **REA MCP** is already loaded in the harness (23 tools). It is not needed for Voice Studio lanes.
- **Voice Studio MCP** (`backend/mcp_server.py`) can be added to the harness later (VS-09 or
  after) for synthetic acceptance runs, through an `- insert:` entry in
  `~/.dsh/profiles/web/cordis.patch.yml`. Back up that file first.
