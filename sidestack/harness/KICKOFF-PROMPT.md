# Kickoff prompt (paste into the DeepSeek Harness)

Replace `VS-xx` with the lane id, then paste everything between the lines.

---

You are the builder for lane **VS-xx** of SideStack Voice Studio, in this workspace (a git
worktree of the VoiceStudio fork).

1. Read `sidestack/AGENTS-SIDESTACK.md` in full. Its rules are binding.
2. Read the lane spec: `sidestack/lanes/VS-xx-*.md` (exactly one file matches). Do not read
   upstream `CLAUDE.md`, `CHANGELOG.md` or other lanes unless the spec tells you to.
3. Run the spec's **Preflight** commands first. If any result differs from what the spec expects,
   stop and report `BLOCKED` with the actual output.
4. Do the **Steps** in order. Change only the files listed under **Files**. If the spec says to
   copy a staged file, copy it byte for byte and check its SHA-256. Do not retype it.
5. Run every **Acceptance** command and keep the real output.
6. Do not commit, push, install packages, download models, or contact any service except the ones
   the spec names.
7. Finish with the report format from AGENTS-SIDESTACK.md §4 and nothing else.

---
