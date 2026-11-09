# VS-14 — Dictation through ODS Whisper

- **Phase:** 4
- **Run by:** dsh does Part A (offline code and tests). The Operator does Part B (the real run).
- **Gate:**
  - **Design OK** before Part A starts.
  - **Real run approval** for Part B: starting Voice Studio, KittenTTS speech on the CPU, and a handful of ODS Whisper transcriptions. Nothing is downloaded.
- **Depends on:** VS-05 (ODS Whisper as Voice Studio's ASR), VS-07 (launcher), VS-09
- **Status:** verified (Part A committed caf2d3b23; Part B real run PASS 2026-11-06). The design OK was given on 2026-11-06: an explicit sherpa-onnx choice keeps priority.

## Goal

Dictation uses ODS Whisper, the same server Voice Studio's other transcription already uses, so it never loads a second Whisper onto the GPU beside ODS. Dictation covers the microphone button, live partials and the capture `/transcribe` route.

**Today (found while writing this lane):**
- The profile pins Voice Studio's main ASR to ODS Whisper (`openai-compat-asr`, VS-05).
- Dictation has its own picker, `get_capture_asr_backend()` in `backend/services/asr_backend.py`. That picker ignores the main ASR choice and only offers local engines: an explicitly selected sherpa-onnx model, then parakeet-mlx, mlx-whisper, faster-whisper and pytorch-whisper.
- On this machine every start logs `Capture ASR backend selected: pytorch-whisper`:
  - faster-whisper is installed, but its cuDNN 8 check fails (VS-01 skipped that step);
  - so the first dictation would download a PyTorch Whisper and load it on the GPU, about 1.6–3 GB beside ODS;
  - the download prompt (`asr_model_missing`) would appear first.
- Every dictation path (the WS socket's Whisper path, its final pass, the silent-model rescue and `POST /capture/transcribe` in fast mode) calls `backend.transcribe(wav_path, word_timestamps=False, …)` on the picker's result. `OpenAICompatASRBackend.transcribe` already takes that call, including `initial_prompt`, which carries the dictation vocabulary hint.

So the change is small: when the opt-in flag is set and the main ASR is the OpenAI-compatible server, the picker hands out that backend instead of a local Whisper, and the "model missing" check stops asking for a download.

## Design

- **Opt-in:** `SIDESTACK_DICTATION_ODS=1`, set in `sidestack/config/ods.env.example`. With the flag unset, upstream behaviour is unchanged, byte for byte.
- **Active only when it can work:**
  - the flag is `1`;
  - `active_backend_id() == "openai-compat-asr"`;
  - `OpenAICompatASRBackend.is_available()` is true (a base URL is configured and the `openai` package is present).

  Otherwise upstream's picker runs as before.
- **An explicitly selected sherpa-onnx model still wins.** It runs on the CPU and is a choice the user made in Settings → Dictation. The new step sits right after the sherpa step and before the local Whisper chain.
- **No silent fallback to a local Whisper.** If ODS Whisper is down, dictation fails with the server's error, the same as Voice Studio's other transcription does today.
- **Live partials stay on.** Every 2 s (`OMNIVOICE_STREAM_INTERVAL`) the legacy socket path re-sends the utterance so far to the server. Part B measures what that costs.
- **The code lives in `backend/sidestack_fork/dictation.py`**, not `backend/services/`, which upstream's `test_structure_doc` counts (VS-06 lesson). There are two marked hooks in `asr_backend.py`.

## Files

| Path | Change |
|---|---|
| `backend/sidestack_fork/dictation.py` | create |
| `backend/services/asr_backend.py` | edit: two hooks marked `SideStack fork (VS-14)` |
| `tests/test_sidestack_dictation.py` | create: D1–D8 |
| `sidestack/config/ods.env.example` | edit: the flag, in the ASR block |
| `sidestack/lanes/VS-14-dictation-ods-whisper.md`, `sidestack/lanes/README.md` | builder report / status |

## Preflight

Start with the environment block from AGENTS-SIDESTACK.md Hard law 9, run from the worktree root.

```powershell
git status --short     # expect: empty
Select-String backend\services\asr_backend.py -Pattern '^def _select_capture_asr_backend\(\*, skip_sherpa: bool\) -> ASRBackend:$'   # expect: 1 match
Select-String backend\services\asr_backend.py -Pattern '^            repo = _capture_whisper_repo\(\)$'   # expect: 1 match
& $py -m pytest tests/test_capture_ws.py tests/test_asr_model_missing.py tests/test_asr_openai_compat_877.py tests/test_capture_asr_idle_release.py tests/test_dictation_router.py tests/test_dictation_prompt.py tests/test_sidestack_ods_asr.py backend/tests/test_dictation_model_demotion.py backend/tests/test_dictation_silent_model.py -q -p no:cacheprovider   # expect: 0 failed (record the count)
```

## Steps

1. Create `backend/sidestack_fork/dictation.py`:
   ```python
   """SideStack fork (VS-14): dictation through Voice Studio's configured
   OpenAI-compatible ASR server (ODS Whisper in the SideStack profile), so
   dictation never loads a second, local Whisper beside ODS.

   Opt-in with SIDESTACK_DICTATION_ODS=1. An explicitly selected sherpa-onnx
   dictation model still wins: it runs on the CPU and is the user's choice.
   """
   from __future__ import annotations

   import os

   ENV_FLAG = "SIDESTACK_DICTATION_ODS"
   CAPTURE_KEY = "sidestack:openai-compat-asr"


   def enabled() -> bool:
       return os.environ.get(ENV_FLAG, "").strip() == "1"


   def remote_capture_active() -> bool:
       """True when dictation should use the openai-compat-asr backend."""
       if not enabled():
           return False
       from services.asr_backend import OpenAICompatASRBackend, active_backend_id

       if active_backend_id() != "openai-compat-asr":
           return False
       ok, _reason = OpenAICompatASRBackend.is_available()
       return ok
   ```
2. In `backend/services/asr_backend.py`, in `_select_capture_asr_backend`, after the whole sherpa block (`# 0. Honor an explicit sherpa dictation model selection.`, which ends with the `logger.info("dictation.model_id=%r selected but sherpa-onnx not installed — " …)` call) and directly before the comment `# Prefer an already-installed Parakeet TDT v3 on Apple Silicon (when`, insert (8-space indent, inside the `with` block):
   ```python
           # SideStack fork (VS-14): dictation through the configured
           # OpenAI-compatible ASR server (ODS Whisper) instead of a local
           # Whisper. An explicit sherpa selection above still wins.
           from sidestack_fork.dictation import CAPTURE_KEY, remote_capture_active
           if remote_capture_active():
               if _capture_backend is None or _capture_backend_key != CAPTURE_KEY:
                   _capture_backend = OpenAICompatASRBackend()
                   _capture_backend_key = CAPTURE_KEY
               return _capture_backend

   ```
3. In the same file, in `asr_model_missing_error`, directly before the line `            repo = _capture_whisper_repo()` (12-space indent, inside `if purpose == "dictation":`), insert:
   ```python
               # SideStack fork (VS-14): nothing to download when dictation uses
               # the ASR server (an explicit sherpa selection was handled above).
               from sidestack_fork.dictation import remote_capture_active
               if remote_capture_active():
                   return None
   ```
4. In `sidestack/config/ods.env.example`, directly after the line `ASR_OPENAI_COMPAT_MODEL=deepdml/faster-whisper-large-v3-turbo-ct2`, add:
   ```
   # VS-14: dictation (mic button, live partials, /capture/transcribe) uses the same ODS Whisper.
   SIDESTACK_DICTATION_ODS=1
   ```
5. Create `tests/test_sidestack_dictation.py`.
   - **Setup:**
     - Copy the header, the `ss` fixture and the `asr_mod` fixture from `tests/test_sidestack_ods_asr.py`. Keep its `skipif` when `openai` is missing.
     - Add a fixture `remote(monkeypatch, asr_mod)` that:
       - sets `SIDESTACK_DICTATION_ODS=1`, `OMNIVOICE_ASR_BACKEND=openai-compat-asr`, `ASR_OPENAI_COMPAT_BASE_URL=http://127.0.0.1:9000/v1` and `ASR_OPENAI_COMPAT_MODEL=test-model`;
       - deletes `OMNIVOICE_SHERPA_ASR_MODEL`;
       - patches `asr_mod.dictation_model_id` to return None;
       - patches `asr_mod._capture_backend` and `asr_mod._capture_backend_key` to None, with `monkeypatch.setattr` so they are restored;
       - makes `PyTorchWhisperBackend.__init__` and `FasterWhisperBackend.__init__` raise `AssertionError("local whisper built")`.
     - A helper `_local_chain_stub(monkeypatch, asr_mod)` for the "not remote" cases:
       - `_capture_prefers_parakeet` returns False;
       - `MLXWhisperBackend.is_available` and `FasterWhisperBackend.is_available` return `(False, "test")`;
       - `PyTorchWhisperBackend.__init__` becomes a no-op (`lambda self, asr_pipe=None: None`).
     - Every test passes `asr_mod` and calls its functions; nothing touches the network or the GPU.
   - **D1:** with `remote`, `asr_mod.get_capture_asr_backend()` is an `OpenAICompatASRBackend`, and a second call returns the same object.
   - **D2:** with `remote` and then `monkeypatch.delenv("SIDESTACK_DICTATION_ODS")` plus `_local_chain_stub`, the picker returns a `PyTorchWhisperBackend`, which is upstream's chain unchanged.
   - **D3:** the same as D2, but with the flag kept and `OMNIVOICE_ASR_BACKEND=faster-whisper`. The picker returns `PyTorchWhisperBackend`, because the main ASR is not the server.
   - **D4:** the same as D2, but with the flag kept and `ASR_OPENAI_COMPAT_BASE_URL` deleted, so the settings store is empty. The picker returns `PyTorchWhisperBackend`, because the server is not configured.
   - **D5:** with `remote`, an explicit sherpa selection still wins.
     - Patch `asr_mod.dictation_model_id` to return `"test-sherpa"`.
     - Replace `asr_mod.SherpaDictationBackend` with a stub class:
       - `is_available` is a classmethod returning `(True, "")`;
       - `__init__(self, model_id)` stores it;
       - `performance_tier` is set to the value `requested_tier("dictation")` returns, from `services.performance_profiles`.
     - Patch `asr_mod.ensure_backend_licence` to a no-op.
     - The picker returns an instance of the stub.
   - **D6:** "model missing" follows the flag.
     - Patch `asr_mod._capture_whisper_repo` with a stub that records each call and returns None. (Not a raising stub: `asr_model_missing_error` catches every exception and fails open, so a raise would pass either way. Reviewer amendment.)
     - With `remote`, `asr_mod.asr_model_missing_error(purpose="dictation")` is None and the stub was never called.
     - With the flag deleted, the same call is None (upstream's fail-open) and the stub was called once.
   - **D7:** the dictation buffer path transcribes through the server.
     - With `remote`, patch `OpenAICompatASRBackend.transcribe` to record its arguments and return `{"chunks": [], "segments": [{"text": "hello there", "start": 0.0, "end": 1.0, "words": []}], "language": "en"}`.
     - Import `api.routers.capture_ws as cw`. Run `asyncio.run(cw._transcribe_buffer([b"\x00\x00" * 16000], pcm_sr=16000, dictation=True))`.
     - Assert the result is `"hello there"`, the recorded path ended in `.wav`, and `word_timestamps` was False.
     - If `_transcribe_buffer` needs `run_transcribe_guarded` or the GPU pool replaced in tests, follow how `tests/test_capture_ws.py` does it, and say so in the report.
   - **D8:**
     - `sidestack/config/ods.env.example` has the line `SIDESTACK_DICTATION_ODS=1`.
     - `backend/services/asr_backend.py` contains `SideStack fork (VS-14)` exactly twice and `remote_capture_active()` exactly twice.
6. Run Acceptance A and report in the §4 format, listing every command.

## Acceptance

**A (builder, offline):**
```powershell
& $py -m pytest tests/test_sidestack_dictation.py -q -p no:cacheprovider      # expect: 8 passed
& $py -m pytest tests/test_capture_ws.py tests/test_asr_model_missing.py tests/test_asr_openai_compat_877.py tests/test_capture_asr_idle_release.py tests/test_dictation_router.py tests/test_dictation_prompt.py tests/test_sidestack_ods_asr.py backend/tests/test_dictation_model_demotion.py backend/tests/test_dictation_silent_model.py -q -p no:cacheprovider   # expect: the preflight count, 0 failed
& $py -m pytest tests/test_sidestack_admission.py tests/test_sidestack_ods_provider.py tests/test_sidestack_launcher.py tests/test_structure_doc.py -q -p no:cacheprovider   # expect: 0 failed
git status --short    # expect: exactly the files in "Files"
Get-ChildItem -Force | Where-Object Name -match '^(pytest-of-|omnivoice-test-data-)'   # expect: nothing
python sidestack/scripts/check_sidestack.py           # expect: OK
```

**The reviewer also:**
- runs the full suite (worktree, short TEMP) against the VS-02 baseline;
- mutation-checks the tests:
  - delete hook 1 → D1 and D7 fail;
  - delete hook 2 → D6 fails;
  - drop the `active_backend_id()` check → D3 fails;
  - drop the `is_available()` check → D4 fails;
  - move hook 1 above the sherpa block → D5 fails.

## Part B — real run (Operator, after approval)

The text is synthetic: "SideStack dictation test. Please schedule the review for Thursday at ten."

1. Record `nvidia-smi` memory.used. Start Voice Studio with the launcher, preflight included.
2. After start, check the log for `Capture ASR backend selected: openai-compat-asr`.
3. Make the clip with `POST /v1/audio/speech` (`kittentts`, `wav`).
4. **REST dictation:** `POST /transcribe` with the clip and `dictation=true` (fast mode), twice. (Amended in the run: the capture router has no prefix; `/capture/transcribe` returns 405.)
   - Record the status, text, latency of each (the second is the warm ODS Whisper latency, open since VS-09), and word accuracy (VS-05 rules). Pass if ≥ 0.9.
5. **Live socket:** connect to `ws://127.0.0.1:3900/ws/transcribe?pcm=1&sr=16000` with no browser `Origin`.
   - Stream the clip as 16 kHz 16-bit PCM in real time, then send the `EOF` text frame and wait for the `final` frame.
   - (Amended in the run: raw PCM needs `pcm=1`, and trailing silence frames count as audio, so they never trigger the silence timeout.)
   - Record the number of partials, the final text and its accuracy, and the time from the last audio to the final frame.
6. Check:
   - the Hugging Face cache under the data dir has no new Whisper repo;
   - memory.used after is within Voice Studio's own CUDA context (about 430 MiB) of the start figure, plus ODS Whisper's resident 2.1 GB if it was unloaded at the start;
   - the log shows no local Whisper load.
7. `-Stop`. Write the report to `sidestack/work/VS-14/report.md` (gitignored).

## Out of scope

- Upstream's sherpa-onnx dictation models (CPU) and their download, which stay as they are.
- The "accurate" `/capture/transcribe` mode, which already uses the main ASR and so already goes to ODS Whisper.
- Making the flag the default upstream, or a UI switch for it.

## Reviewer notes

Checked in the code while writing this lane (2026-11-06):
- `_discover_reference_candidates` (voice-clone reference transcription) already prefers the main ASR, which is ODS. With the flag on, its capture candidate becomes the same backend type, which it de-duplicates.
- `OpenAICompatASRBackend.gpu_compat = ("cpu",)` and it has no `warmup`, so the startup capture preload only logs the selection.

## Builder report (Part A, 2026-11-06)

**LANE:** VS-14 Part A
**STATUS:** DONE — all steps 1–6 and Acceptance A green
**FILES CHANGED:**
- a7df88c82367  backend/sidestack_fork/dictation.py  (created)
- 3ff60e9d83ac  backend/services/asr_backend.py  (two hooks)
- 354bb9dd4066  tests/test_sidestack_dictation.py  (created, D1–D8)
- 70e6fff73ead  sidestack/config/ods.env.example  (VS-14 lines added)

**COMMANDS RUN:**

1. `& $py -m pytest tests/test_sidestack_dictation.py -q -p no:cacheprovider` → 8 passed in 2.11s
2. `& $py -m pytest tests/test_capture_ws.py tests/test_asr_model_missing.py tests/test_asr_openai_compat_877.py tests/test_capture_asr_idle_release.py tests/test_dictation_router.py tests/test_dictation_prompt.py tests/test_sidestack_ods_asr.py backend/tests/test_dictation_model_demotion.py backend/tests/test_dictation_silent_model.py -q -p no:cacheprovider` → 127 passed, 7 warnings in 16.53s (matches preflight count)
3. `& $py -m pytest tests/test_sidestack_admission.py tests/test_sidestack_ods_provider.py tests/test_sidestack_launcher.py tests/test_structure_doc.py -q -p no:cacheprovider` → 36 passed in 23.14s
4. `git status --short` → exactly the 4 files above
5. `Get-ChildItem -Force | Where-Object Name -match '^(pytest-of-|omnivoice-test-data-)'` → nothing
6. `python sidestack/scripts/check_sidestack.py` → OK: 14 required files, 13 lane specs, links, manifest, env profile, secret scan

**NOT DONE:** None for Part A. D7 follows `tests/test_capture_ws.py`'s pattern: `run_transcribe_guarded` is replaced with an inline runner and `services.model_manager._gpu_pool` is stubbed via a fake module so the GPU pool is never imported.

## Reviewer verification (Part A, 2026-11-06)

**Result: verified after two reviewer fixes.**

- **Fix 1 (code):** hook 2 was inserted at a 16-space indent, inside upstream's `if sid:` block, instead of the spec's 12 spaces. It only ran when a sherpa model was selected, so in the normal case the dictation "model missing" check still went on to the local Whisper repo. The reviewer moved it to 12 spaces, directly before `repo = _capture_whisper_repo()`.
- **Fix 2 (test, and this spec's D6 text):** D6 used a raising stub. `asr_model_missing_error` catches every exception and fails open, so D6 passed with hook 2 misplaced or deleted. D6 now records calls and asserts the stub is not reached with the flag on, and reached once with it off.
- **Mutation checks (all caught after the fixes):**
  - delete hook 1 → D1, D7, D8 fail;
  - delete hook 2 → D6, D8 fail;
  - hook 2 back inside `if sid:` → D6 fails;
  - drop the `active_backend_id()` check → D3 fails;
  - drop the `is_available()` check → D4 fails;
  - hook 1 above the sherpa block → D5 fails.
- **Re-run:** `test_sidestack_dictation.py` 8 passed. The 13 dictation, ASR, SideStack and structure test files: 163 passed. `check_sidestack.py` OK.
- **Full suite** (worktree, short TEMP, `-n 8`): 13010 passed, 91 failed, 20 errors in 17 min. All 104 failing ids are in the VS-02 baseline (no new ids); 6 baseline ids now pass.
- **Also checked:** hook 1 sits inside upstream's `_capture_backend_lock`.

## Part B result (Operator, 2026-11-06, user-approved): PASS

- The start log says `Capture ASR backend selected: openai-compat-asr`; every earlier start said `pytorch-whisper`.
- KittenTTS clip: 7.3 s, made in 6.4 s.
- REST dictation (`POST /transcribe`, `dictation=true`): the first call took 22.5 s, a cold load of ODS Whisper. The second took **0.8 s** (warm). Both scored accuracy 1.0, with engine `openai-compat-asr`.
- Live socket: 2 partials. The final scored accuracy 1.0 and arrived 3.8 s after the last audio, because the final waited behind a partial pass that was still in flight. Over the 7.3 s utterance it made 4 ODS Whisper requests: 3 partials and the final.
- No local Whisper:
  - the log shows no local load;
  - the data-dir HF cache has no new repo;
  - Voice Studio's own GPU memory (Windows per-process counter) is 432 MiB, its CUDA context only.
  The +3.2 GB that appeared during the first request is in the WSL VM, where ODS Whisper is resident at about 3.3 GB. It was unloaded at the start.
- No keys in the logs. `-Stop` was clean. The full report is in `sidestack/work/VS-14/report.md` (gitignored). Idle release (`release_idle_capture_backend`) only drops the server client, whose `unload()` is the base no-op.
