# VS-15 — "Voice Studio first" GPU policy

- **Phase:** 4
- **Run by:** dsh
- **Gate:** none (decision given 2026-11-06; code + offline tests only)
- **Depends on:** VS-06 (admission gate), VS-14
- **Status:** verified

## Goal

Record the user's decision on the open VS-06 question, and make the gate's refusal message match it.

**The question (VS-06 open issue):** the gate compares an engine's VRAM floor plus a 1 GB margin with the VRAM that is free *now*. When ODS has idle-unloaded its LLM, about 28 GB is free, so the gate admits a large engine. ODS may then fail or be slow to reload its LLM.

**The decision (user, 2026-11-06): Voice Studio first. No reserve for ODS.**
- Voice Studio is used on its own: while the user works in it, nothing else uses ODS. So the gate keeps checking free VRAM only.
- No smaller ODS model or context is needed first. If ODS's LLM is still loaded, the gate refuses large engines, and the user unloads it in ODS or waits until ODS unloads it.
- Voice Studio still never unloads ODS models.
- Upstream already gives the memory back: idle engines unload after `OMNIVOICE_IDLE_TIMEOUT` (default 900 s), so ODS can reload later.
- **Accepted risk:** if another app calls ODS while a Voice Studio engine is loaded (Meetings, Hermes, a harness task), ODS may fail or be slow to reload its LLM.

**What changes:** the refusal message today says "switch ODS to 64k context first". Under this decision the advice is to free ODS's LLM or pick a CPU engine. Decision D3 in PLAN.md and ARCHITECTURE §2 change to match.

Measured on this machine (VS-14, 2026-11-06): ODS LLM 21.9 GB + ODS Whisper 3.3 GB, desktop about 2.5 GB, on a 32 GB GPU. With the LLM loaded, about 4.8 GB is left. That is below OmniVoice's floor plus margin (7 GB). The Apache-2.0 cloning engines (VoxCPM2, CosyVoice 3, MOSS-TTS v1.5) declare no VRAM floor, so the gate counts only the 1 GB margin for them and would admit them; VS-16 measures their real use.

## Files

| Path | Change |
|---|---|
| `backend/sidestack_fork/admission.py` | edit: the refusal message only |
| `tests/test_sidestack_admission.py` | edit: add G14 |
| `sidestack/PLAN.md` | edit: D3 row; add VS-14 and VS-15 lane rows |
| `sidestack/ARCHITECTURE.md` | edit: items 2 and 3 of the GPU rules |
| `sidestack/lanes/VS-06-vram-admission-gate.md` | edit: one line under the open design issue |
| `sidestack/lanes/VS-15-voice-studio-first-vram.md`, `sidestack/lanes/README.md` | builder report / status |

## Preflight

Start with the environment block from AGENTS-SIDESTACK.md Hard law 9, run from the worktree root.

```powershell
git status --short     # expect: empty
Select-String backend\sidestack_fork\admission.py -Pattern 'switch ODS to 64k context first'   # expect: 1 match
Select-String sidestack\PLAN.md -Pattern '^\| D3 \|'   # expect: 1 match
Select-String sidestack\ARCHITECTURE.md -Pattern 'Not enough GPU memory while ODS is loaded'   # expect: 1 match
& $py -m pytest tests/test_sidestack_admission.py -q -p no:cacheprovider   # expect: 0 failed (record the count)
```

## Steps

1. In `backend/sidestack_fork/admission.py`, in `admission_error`, replace the whole `return (` … `)` block that builds the refusal message with:
   ```python
       return (
           f"Not enough free GPU memory: need {need:.1f} GB, have {float(free):.1f} GB "
           f"(TTS engine '{engine_id}'). If ODS has its LLM loaded, unload it in ODS "
           "or wait until ODS unloads it, then try again; or choose a CPU engine. "
           "Voice Studio never unloads ODS models."
       )
   ```
   Change nothing else in the file.
2. In `tests/test_sidestack_admission.py`, add after `test_g13_speech_route_gate_refusal` (end of file):
   ```python


   # ── G14: VS-15 "Voice Studio first" advice ─────────────────────────────────
   def test_g14_refusal_advice_voice_studio_first(monkeypatch):
       """VS-15: Voice Studio runs on its own, so the advice is to free ODS's
       LLM or use a CPU engine, never to shrink ODS's context."""
       sa = _mod(monkeypatch)
       msg = sa.admission_error("voxcpm2", 6.0, resident=False, mem={"vram_free_gb": 5.0})
       assert msg is not None
       assert "need 7.0 GB, have 5.0 GB" in msg
       assert "64k" not in msg
       assert "unload it in ODS" in msg
       assert "CPU engine" in msg
       assert "never unloads ODS models" in msg
   ```
   Keep exactly two blank lines before the comment line, and one newline at the end of the file.
3. In `sidestack/PLAN.md`, replace the whole `| D3 |` row with:
   ```markdown
   | D3 | GPU sharing with ODS while Voice Studio is active | **Decided 2026-11-06 (VS-15): Voice Studio first.** Voice Studio is used on its own; the gate checks free VRAM only, with no reserve for ODS. Large engines need ODS's LLM unloaded (by ODS when idle, or by the user in ODS). Voice Studio never unloads ODS models. | Measured: ODS LLM 21.9 GB + Whisper 3.3 GB leave about 4.8 GB on the 32 GB GPU, below OmniVoice's 7 GB need. Accepted risk: another app calling ODS while a Voice Studio engine is loaded may make ODS's LLM reload fail or slow. Upstream releases idle engines after 15 minutes. |
   ```
4. In `sidestack/PLAN.md`, in the lanes table, directly after the `| | VS-13 |` row, add:
   ```markdown
   | | VS-14 | Dictation through ODS Whisper instead of a local Whisper | dsh + Operator | **Real run approval** |
   | | VS-15 | "Voice Studio first" GPU policy (decision D3); refusal message advises freeing ODS's LLM | dsh | — |
   ```
5. In `sidestack/ARCHITECTURE.md`, replace the two numbered items that start `2. **Admission gate (VS-06):**` and `3. Prefer engines that fit in about 4 GB` (all of their lines) with:
   ```markdown
   2. **Admission gate (VS-06, VS-15):** before a TTS engine loads, compare the engine's
      VRAM floor plus a 1 GB margin against free VRAM. Refuse with "Not enough free GPU memory:
      need X GB, have Y GB", advising the user to free ODS's LLM or pick a CPU engine. Never evict
      or unload ODS models; that is the user's call.
   3. **Voice Studio first (decision D3, VS-15):** Voice Studio is used on its own, so there is no
      reserve for ODS. Large engines run once ODS's LLM is unloaded; upstream releases idle
      Voice Studio engines after 15 minutes so ODS can reload.
   ```
6. In `sidestack/lanes/VS-06-vram-admission-gate.md`, directly after the line that starts `  - A reserve (for example, require`, add:
   ```markdown
     - **Decided in VS-15 (2026-11-06): Voice Studio first, no reserve.** See PLAN.md decision D3.
   ```
7. Run Acceptance and report in the AGENTS-SIDESTACK §4 format, listing every command. Append the report to this spec under `## Builder report`, and set this lane's tracker status in `sidestack/lanes/README.md` to `running (dsh done)`.

## Acceptance

```powershell
& $py -m pytest tests/test_sidestack_admission.py -q -p no:cacheprovider   # expect: preflight count + 1, 0 failed
& $py -m pytest tests/test_sidestack_dictation.py tests/test_sidestack_ods_asr.py tests/test_sidestack_ods_provider.py tests/test_sidestack_launcher.py tests/test_structure_doc.py -q -p no:cacheprovider   # expect: 0 failed
Select-String backend\sidestack_fork\admission.py -Pattern '64k'   # expect: nothing
Select-String sidestack\ARCHITECTURE.md -Pattern 'switches ODS to 64k'   # expect: nothing (the §4 budget table keeps its 64k rows)
git status --short    # expect: exactly the files in "Files"
Get-ChildItem -Force | Where-Object Name -match '^(pytest-of-|omnivoice-test-data-)'   # expect: nothing
python sidestack/scripts/check_sidestack.py           # expect: OK
```

## Out of scope

- A VRAM reserve for ODS, or asking ODS whether its LLM is loaded (the user chose not to).
- Unloading ODS models from Voice Studio, or a "studio mode" button that would.
- Changing `OMNIVOICE_IDLE_TIMEOUT` (upstream default 900 s stays).
- The cloning lane (VS-16), which is written next.

## Reviewer notes

- **Mutation checks:**
  - restore the old message → G14 fails;
  - drop the "CPU engine" clause → G14 fails.
- Check the D3 row still renders as one table row (no line breaks inside it).
- Checked while writing this lane (2026-11-06):
  - `release_idle_engines` in `services/tts_backend.py` pops idle instances from `_ENGINE_INSTANCES`, so a released engine no longer counts as resident for the gate.
  - Only `OmniVoiceBackend` (and the OmniVoice subprocess engine) declare `min_vram_gb` (6.0). VoxCPM2, CosyVoice and MOSS-TTS inherit 0.0, so the gate checks only the margin for them. Measuring their real VRAM is part of VS-16; any floor change follows from that.

## Builder report

**Builder (dsh), 2026-11-06: DONE.** All steps applied as specified; tracker status set to `running (dsh done)`.

```
LANE: VS-15
STATUS: DONE
FILES CHANGED:
  backend/sidestack_fork/admission.py (ccd27633a518)
  tests/test_sidestack_admission.py (a06eabe2f7e4)
  sidestack/PLAN.md (ab4260844091)
  sidestack/ARCHITECTURE.md (e7a7e61a46cd)
  sidestack/lanes/VS-06-vram-admission-gate.md (cf9f27f53d4b)
  sidestack/lanes/VS-15-voice-studio-first-vram.md (97da0b0a3d45)
  sidestack/lanes/README.md (cdedf4d2141c)
COMMANDS RUN:
  & $py -m pytest tests/test_sidestack_admission.py -q -p no:cacheprovider → exit 0, 14 passed (preflight 13 + G14)
  & $py -m pytest tests/test_sidestack_dictation.py tests/test_sidestack_ods_asr.py tests/test_sidestack_ods_provider.py tests/test_sidestack_launcher.py tests/test_structure_doc.py -q -p no:cacheprovider → exit 0, 35 passed
  Select-String backend\sidestack_fork\admission.py -Pattern '64k' → no matches
  Select-String sidestack\ARCHITECTURE.md -Pattern 'switches ODS to 64k' → no matches (the §4 budget table keeps its 64k rows)
  git status --short → exactly the 5 files above minus this spec and README (README updated after the status check)
  Get-ChildItem -Force | Where-Object Name -match '^(pytest-of-|omnivoice-test-data-)' → no matches
  & $py sidestack\scripts\check_sidestack.py → exit 0, "OK: 14 required files, 14 lane specs, links, manifest, env profile, secret scan"
NOT DONE / UNSURE: none
```

## Reviewer verification (2026-11-06)

**Result: verified, no fixes needed.**
- The diff matches Steps 1–6 exactly. Nothing else in the repo uses the old message text.
- Mutation checks, both caught by G14:
  - restore the old "switch ODS to 64k" advice;
  - drop the "CPU engine" clause.
- Re-run: SideStack tests + `test_structure_doc` 49 passed. `check_sidestack.py` OK.
- **Full suite** (worktree, short TEMP, `-n 8`): 12998 passed, 93 failed, 31 errors. The only new ids are the 11 in `tests/test_no_audio_track.py`, the known test-order leak from `test_media_tool_missing` (VS-06 notes). On its own that file gives 4 passed, 11 skipped. 4 baseline ids now pass.
