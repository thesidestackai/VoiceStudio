# VS-30 — Cold ODS Whisper timeout and operations notes

- **Phase:** 4
- **Run by:** dsh does Part A (profile, test, runbook). The Operator does Part B (live cold-Whisper check).
- **Gate:** none for Part A. Part B needs **real run approval**: restart Voice Studio, then one dub transcription after ODS Whisper has been idle for more than 5 minutes. ODS is not stopped or changed.
- **Depends on:** VS-29
- **Status:** verified (Part B PASS, 2026-11-08)

## Goal

The VS-29 follow-ups that need no upstream code change:
- **Timeout:** the SideStack profile allows 300 s per dub transcription chunk (`OMNIVOICE_TRANSCRIBE_CHUNK_TIMEOUT_S=300`). The first dub after ODS Whisper idles out then succeeds, instead of timing out at upstream's 120 s.
- **Runbook:** `APPLY.md` records:
  - the restart order on the shared GPU (stop Voice Studio before restarting ODS's LLM);
  - the cold-Whisper behaviour;
  - `smart_fit` for API dub callers.

**Why:**
- **VS-29, finding 1:** ODS Whisper reloaded its model in 103 s, so the first transcription took 128 s and was abandoned at 120 s.
- **VS-29, finding 3:** llama-server stalled when VoxCPM2 was still resident.
- **VS-29, finding 2:** the API's default dub timing (`concise`) failed both dubs.

## Files

| Path | Change |
|---|---|
| `sidestack/config/ods.env.example` | edit: 1 replacement (new key after `SIDESTACK_DICTATION_ODS=1`) |
| `tests/test_sidestack_launcher.py` | edit: 1 replacement (L8 asserts the timeout) |
| `sidestack/ods/APPLY.md` | append: "Operations notes (lane VS-30)" |
| `sidestack/lanes/VS-30-whisper-timeout-ops.md`, `sidestack/lanes/README.md` | builder report / status |

## Preflight

Run from the worktree root.

```powershell
git status --short     # expect: only this spec (new) and sidestack/lanes/README.md (its row)
Select-String sidestack\config\ods.env.example -Pattern '^SIDESTACK_DICTATION_ODS=1$'   # expect: 1 match
Select-String sidestack\config\ods.env.example -Pattern 'TRANSCRIBE_CHUNK_TIMEOUT'   # expect: no match
```

## Steps

Each "replace" below names text that occurs exactly once in its file. Keep each file's line endings. Do not run `git checkout`, `git stash`, `git reset`, `git clean` or `git restore`.

1. In `sidestack/config/ods.env.example`, make 1 replacement.
   - Replace:
     ```ini
     SIDESTACK_DICTATION_ODS=1
     ```
     with:
     ```ini
     SIDESTACK_DICTATION_ODS=1
     # VS-30: a cold ODS Whisper reloads its model in about 103 s (VS-29), past upstream's 120 s
     # per-chunk dub transcription limit. 300 s matches OMNIVOICE_ASR_TRANSCRIBE_TIMEOUT_S.
     OMNIVOICE_TRANSCRIBE_CHUNK_TIMEOUT_S=300
     ```
2. In `tests/test_sidestack_launcher.py`, make 1 replacement.
   - In `test_l8_profile_content`, replace:
     ```python
         assert profile["OMNIVOICE_ENV_FILE"].startswith(profile["OMNIVOICE_DATA_DIR"])
     ```
     with:
     ```python
         assert profile["OMNIVOICE_ENV_FILE"].startswith(profile["OMNIVOICE_DATA_DIR"])
         # VS-30: room for a cold ODS Whisper model reload (about 103 s measured in VS-29).
         assert float(profile["OMNIVOICE_TRANSCRIBE_CHUNK_TIMEOUT_S"]) >= 300
     ```
3. At the end of `sidestack/ods/APPLY.md`, append this section after one blank line:
   ```markdown
   ## Operations notes (lane VS-30)

   **Restart order on a shared GPU.** VoxCPM2's sidecar stays loaded for 15 minutes after its last use (about 7 GB). Restarting ODS's LLM while it is loaded leaves llama-server short of GPU memory, and its load stalls.
   1. Run `Start-VoiceStudio-ODS.ps1 -Stop`.
   2. Start ODS's LLM and wait until it is healthy.
   3. Click the ODS link to start Voice Studio again.

   Measured in VS-29: 39 s to healthy in this order, against a stall of more than 3 minutes the other way.

   **Cold ODS Whisper.**
   - ODS Whisper unloads its model after 5 idle minutes, and reloading it took about 103 s.
   - The SideStack profile sets `OMNIVOICE_TRANSCRIBE_CHUNK_TIMEOUT_S=300`, so the first dub transcription after an idle spell still finishes. Upstream's default is 120 s.
   - Dictation and the whole-file ASR path already allow 300 s (`OMNIVOICE_ASR_TRANSCRIBE_TIMEOUT_S`).

   **Dub timing for API callers.**
   - `POST /dub/generate` defaults to `timing_strategy: "concise"`. That fails the whole dub when any translated line runs past its slot, which is common from English to Spanish or Khmer.
   - Send `"timing_strategy": "smart_fit"` instead. It stretches lines to fit while keeping the pitch (VS-29).
   - The web UI's default is `strict_slot`, so this only affects direct API, MCP and script callers.
   ```
4. Run Acceptance and report in the AGENTS-SIDESTACK §4 format, listing every command. Append the report at the very end of this spec under a `## Builder report` heading, and set this lane's tracker status to `running (dsh done)`. The Reviewer notes are for the reviewer: do not run them.

## Acceptance

Run from the worktree root, with `$py` and the Hard law 9 environment.

```powershell
& $py -m pytest tests/test_sidestack_launcher.py -q -p no:cacheprovider   # expect: 14 passed
python sidestack/scripts/check_sidestack.py           # expect: OK
git status --short    # expect: exactly the files in "Files"
```

## Part B — live check (Operator, after approval)

1. **Restart Voice Studio** from the main checkout. Its dry-run plan shows `OMNIVOICE_TRANSCRIBE_CHUNK_TIMEOUT_S=300`.
2. **Wait for Whisper to go cold.** Wait until ODS Whisper has been idle for more than 5 minutes; its log shows the model offloaded.
3. **Run one dub.** Upload a synthetic clip, then run `transcribe-stream`. Expect `final` with segments, not `transcription_timeout`, and record the time.

## Out of scope

- Changing upstream's `concise` default in `/dub/generate`. The web UI already defaults to `strict_slot`, and API callers are told to send `smart_fit`.
- Keeping ODS Whisper warm. That is an ODS setting.
- Batch, watermark detection, and Khmer ASR.

## Reviewer notes

- **Mutation checks** (to run after the build):
  - set the profile value to `120` → L8 fails;
  - delete the line → L8 fails (`KeyError`).
- `check_sidestack.py` requires `KEY=VALUE` lines with comments on their own lines. The new lines follow that rule.
- The launcher copies every profile key into the backend's environment, so no launcher change is needed. `dub_core.py` reads the variable at import.

## Builder report

```
LANE: VS-30
STATUS: DONE (Part A; Part B is the Operator's live cold-Whisper check)
FILES CHANGED: sidestack/config/ods.env.example (9215d6ede6a4), tests/test_sidestack_launcher.py (7ccedd58d30f), sidestack/ods/APPLY.md (5d68902c7432), sidestack/lanes/README.md (66a32c7254a7), sidestack/lanes/VS-30-whisper-timeout-ops.md (b93038b0e090)
COMMANDS RUN: git status --short → 0 (preflight clean: only this spec (new) and sidestack/lanes/README.md); Select-String ods.env.example '^SIDESTACK_DICTATION_ODS=1$' → 0 (1 match); Select-String ods.env.example 'TRANSCRIBE_CHUNK_TIMEOUT' → 0 (no match); & $py -m pytest tests/test_sidestack_launcher.py -q -p no:cacheprovider → 0, 14 passed; & $py sidestack/scripts/check_sidestack.py → 0, OK; git status --short → 0 (exactly the files in "Files")
NOT DONE / UNSURE: none (Part B left to the Operator; no mutation checks run)
```

## Reviewer verification (Part A, 2026-11-08)

- **Builder:** dsh (Qwen 3.8 on ODS), 2 minutes. Preflight passed.
- **Exactness:** all three edits match the spec exactly (profile line, L8 assert, `APPLY.md` section).
- **Acceptance (Hard law 9 environment):** `test_sidestack_launcher.py` 14 passed; `check_sidestack.py` OK.
- **Mutation checks (both caught, file restored):**
  - profile value set back to `120` → L8 fails;
  - line deleted → L8 fails.
- **Private data:** none in the diff.
- **Next:** Part B, the live cold-Whisper check, needs real run approval.

## Part B results (Operator, 2026-11-08)

The user approved the commit and the live check. ODS was not stopped or changed.

1. **Restart:**
   - The main checkout's dry-run plan shows `OMNIVOICE_TRANSCRIBE_CHUNK_TIMEOUT_S=300`.
   - Voice Studio was stopped and started again from the main checkout with the committed profile.
2. **Cold Whisper:** ODS Whisper's log shows its model unloaded at 05:26:52 UTC, 39 minutes before the check. ODS's LLM was loaded, with 6.2 GB of GPU memory free.
3. **Dub transcription:**
   - A new upload of the synthetic clip finished prep in 2.0 s (Demucs cached).
   - `transcribe-stream` then returned `final` in 52.3 s: 2 segments, the right text, no `transcription_timeout`.
   - Whisper reloaded its model and transcribed in 14.9 s this time, against 103 s in VS-29.

**Verdict:** PASS. The cold path works with the new profile.

**Note:** this reload was fast, so the run did not get near the old 120 s limit. It does not prove a slow reload would now pass, only that nothing regressed and that the setting is in the live profile.

VS-29's 103 s reload happened while ODS's LLM held most of the GPU, as now. A reload with the LLM stopped took 3.4 s. Reload time varies, and 300 s leaves room for the slow case measured in VS-29.
