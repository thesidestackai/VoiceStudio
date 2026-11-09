# VS-09 — End-to-end synthetic acceptance

- **Phase:** 3
- **Run by:** dsh does Part A (offline gate fixes); the Operator does Part B (the real run)
- **Gate:** none for Part A. **Real run approval** for Part B:
  - downloading KittenTTS mini 0.8 (about 80 MB, Apache-2.0) from Hugging Face on first use;
  - one transcription through ODS Whisper and one dub translation through the ODS relay;
  - the launcher's read-only ODS preflight.
- **Depends on:** VS-08
- **Status:** verified (Part A and Part B, 2026-11-06)

## Goal

Synthetic text goes all the way through the installed app, with every model call local:

**text → speech** (`/v1/audio/speech`, KittenTTS on the CPU) → **speech → text** (Voice Studio's
`/v1/audio/transcriptions` → ODS Whisper) → **translation** (`/dub/translate`, LLM engine → ODS
relay).

The run records latencies, VRAM before and after, and word accuracy, and confirms the relay key is
never written. Two gate gaps found while preparing this lane are fixed first, in Part A.

**Why KittenTTS** (decision D3: small or CPU engines while ODS runs at 128k):
- It is CPU-only, so it adds no VRAM next to the 24.7 GB ODS LLM.
- Its download is 80 MB, against 2.4 GB plus a tokenizer for OmniVoice.
- It is Apache-2.0, so it needs no non-commercial licence acceptance (decision D2).
- Its package is already installed. Upstream's licence record for it is still marked "unreviewed".

## Part A — gate fixes (builder)

Found while preparing this lane:
1. The VS-06 gate ignores the engine's device. A **CPU-only** engine (`gpu_compat` without `cuda`/`rocm`, as with KittenTTS) is refused whenever free VRAM drops below the 1 GB margin, although it never touches the GPU.
2. **`/v1/audio/speech` is not gated.** The hooks cover `/generate` and the WS stream only. VS-10 (Meetings "read aloud") will use `/v1/audio/speech`.

## Files

| Path | Change |
|---|---|
| `backend/sidestack_fork/admission.py` | edit: the CPU-only skip in `tts_admission_error` |
| `backend/api/routers/openai_compat.py` | edit: the gate hook at the top of `create_speech` |
| `tests/test_sidestack_admission.py` | edit: update G9 and G10, add G12 and G13 |

## Preflight

Start with the environment block from AGENTS-SIDESTACK.md Hard law 9, run from the worktree root.

```powershell
git status --short     # expect: empty
Select-String backend\api\routers\openai_compat.py -Pattern '^async def create_speech\(req: SpeechRequest\):$'   # expect: 1 match
& $py -m pytest tests/test_sidestack_admission.py tests/test_openai_sdk_contract.py tests/test_openai_speech_binary_guard_1172.py tests/test_openai_speech_engine_cache.py tests/test_openai_speech_extension_controls.py tests/test_openai_voice_by_name_2617.py -q -p no:cacheprovider   # expect: 0 failed (record the count)
```

## Steps

1. In `backend/sidestack_fork/admission.py`, inside `tts_admission_error`, directly after the `try`/`except` that resolves `selected` and `cls` and before the final `return`, insert:
   ```python
       # CPU-only engines (no CUDA/ROCm in gpu_compat) never use the GPU ODS shares.
       if not ({"cuda", "rocm"} & set(getattr(cls, "gpu_compat", ()) or ())):
           return None
   ```
2. In `backend/api/routers/openai_compat.py`, in `create_speech`, insert this as the first statements of the function body, directly after the docstring and before `from services.model_acceptance import ModelLicenceNotAccepted`:
   ```python
       # SideStack fork (VS-09): the VS-06 GPU admission gate on the OpenAI speech
       # route too. OpenAI model ids ("tts-1") mean the active engine.
       from sidestack_fork.admission import tts_admission_error
       _admission = tts_admission_error(None if is_openai_tts_model(req.model) else req.model)
       if _admission:
           raise OpenAIError(503, _admission, param="model", code="insufficient_gpu_memory")
   ```
3. In `tests/test_sidestack_admission.py`:
   - **G9:** give the local `_Eng` class `gpu_compat = ("cuda", "cpu")`. Otherwise the new skip makes it pass for the wrong reason.
   - **G10:** also require `tts_admission_error(` and `SideStack fork (VS-09)` in `backend/api/routers/openai_compat.py`.
   - **G12 (new):** with the gate on and `mem={"vram_free_gb": 0.1}`, `tts_admission_error("cpu-eng", _CpuEng)` is None, where `_CpuEng` has `min_vram_gb = 0.0` and `gpu_compat = ("cpu",)`. The same with `gpu_compat = ("cuda", "cpu")` is refused (`need 1.0 GB`).
   - **G13 (new):** the speech route returns the gate's refusal.
     1. Use `monkeypatch.setattr(importlib.import_module("sidestack_fork.admission"), "tts_admission_error", lambda *a, **k: "refused by test")`.
     2. Import `api.routers.openai_compat as oc` (`backend/` is on `sys.path`, as in G1–G11).
     3. Run `asyncio.run(oc.create_speech(oc.SpeechRequest(model="kittentts", input="x", response_format="wav")))` inside `pytest.raises(oc.OpenAIError)`.
     4. Assert `exc.value.status_code == 503`, `exc.value.code == "insufficient_gpu_memory"` and `exc.value.detail == "refused by test"`.
4. Run Acceptance A and report in the §4 format, listing every command.

## Acceptance

```powershell
& $py -m pytest tests/test_sidestack_admission.py -q -p no:cacheprovider      # expect: 13 passed
& $py -m pytest tests/test_openai_sdk_contract.py tests/test_openai_speech_binary_guard_1172.py tests/test_openai_speech_engine_cache.py tests/test_openai_speech_extension_controls.py tests/test_openai_voice_by_name_2617.py -q -p no:cacheprovider   # expect: 0 failed
& $py -m pytest tests/test_sidestack_ods_provider.py tests/test_sidestack_ods_asr.py tests/test_sidestack_launcher.py tests/test_structure_doc.py -q -p no:cacheprovider   # expect: 0 failed
git status --short    # expect: exactly the 3 files above
Get-ChildItem -Force | Where-Object Name -match '^(pytest-of-|omnivoice-test-data-)'   # expect: nothing
python sidestack/scripts/check_sidestack.py           # expect: OK
```

The reviewer also mutation-checks the tests:
- drop the CPU-only skip → G12 fails;
- delete the speech-route hook → G10 and G13 fail;
- drop `_Eng.gpu_compat` → G9 fails.

## Part B — real run (operator, after approval)

All requests go to `http://127.0.0.1:3900`, with Voice Studio started by `Start-VoiceStudio-ODS.ps1`. The text is synthetic: "SideStack Voice Studio end to end test. The quick brown fox jumps over the lazy dog."

1. Record `nvidia-smi` memory.used, then start Voice Studio with the launcher (preflight included).
2. **Speech:** `POST /v1/audio/speech` with `{"model": "kittentts", "input": <text>, "response_format": "wav"}`. The first use downloads KittenTTS.
   - Save the WAV to `sidestack/work/VS-09/speech.wav`.
   - Record the HTTP status, latency, duration, sha256, and memory.used after.
   - Repeat once for a warm latency.
3. **Speech → text:** `POST /v1/audio/transcriptions` with the WAV and `model=whisper-1`. Voice Studio's ASR backend is `openai-compat-asr`, so this goes to ODS Whisper.
   - Record the latency and text, and the word accuracy after normalisation (VS-05 rules). Pass if ≥ 0.9.
   - Compare with VS-05's 17.3 s, which was measured while Meetings was recording.
4. **Translation:** `POST /dub/translate` with one segment of the text, source `en`, target `es`, and `provider: "openai"`. That is the LLM engine, so the call goes through the active `ods` provider to the relay.
   - Record the HTTP status, latency and translation. Pass if it is non-empty Spanish, not the English input.
5. Stop Voice Studio with `-Stop`. Scan every file written under the data dir for the relay key (shared-read, as in VS-07); expect 0. Record memory.used.
6. Write `sidestack/work/VS-09/report.md` (gitignored) and summarise it in the reviewer notes.

### Acceptance B

- The speech request returns 200 with a WAV over 1 s long.
- Transcription word accuracy is ≥ 0.9 after normalisation.
- The translation is non-empty Spanish.
- No relay key appears in any written file.
- `-Stop` leaves no process behind, and VRAM shows no lasting increase from Voice Studio.

## Out of scope (new lanes in the tracker)

- **VS-14:** dictation through ODS Whisper. Upstream's capture/dictation chain offers only local engines (sherpa-onnx, Parakeet, mlx-whisper, faster-whisper, pytorch-whisper), so this needs a code change and a design OK.
- **VS-15:** VRAM reserve while the ODS LLM is idle-unloaded (VS-06 open issue). Needs a decision.
- OmniVoice, voice cloning, real voices, and anything commercial.

## Reviewer notes

**Part A, 2026-11-06: PASS (first attempt).**

- **Builder (dsh on ODS, full access, fresh session):** 3 m 38 s, 11 steps, about 428k tokens. It reported DONE in the full §4 format, with every command listed.
  - Preflight: 75 passed. Acceptance: 13, 64 and 27 passed. No residue.
  - Hashes: `admission.py` `75D0578E6F08`, `openai_compat.py` `FBB5DF9C49A6`, tests `FC3652F92829`.
- **Diff:** both code blocks match steps 1–2 exactly. The speech hook is the first statement after the docstring. The test changes are exactly G9, G10, G12 and G13 as specified.
- **Reviewer re-run:** 104 passed across the 10 SideStack and OpenAI-route test files.
- **Mutation checks**, all files restored by SHA-256:
  - Drop the CPU-only skip: G12 failed.
  - Delete the speech hook: G10 and G13 failed.
  - Drop `_Eng.gpu_compat`: G9 failed.
- Before Part B: 25.3 GB of 32.6 GB VRAM used (ODS LLM loaded), port 3900 free, KittenTTS weights not cached yet.

**Part B, 2026-11-06: PASS (the real run was approved by the user).** Full report: `sidestack/work/VS-09/report.md` (gitignored).

- **Speech:** `/v1/audio/speech` with KittenTTS returned 200 and 8.29 s of 24 kHz WAV.
  - Cold: 13.87 s, including the 77.8 MB first-use download. Warm: 6.29 s, on the CPU.
- **Speech → text:** Voice Studio's `/v1/audio/transcriptions` → ODS Whisper returned 200 in 13.91 s, with word accuracy **1.000** after normalisation.
- **Translation:** `/dub/translate` with `provider=openai` → the `ods` provider → the relay, with `auto_glossary` and `reflect` off so it was exactly one LLM call. It returned 200 in 5.82 s, in correct Spanish.
- **VRAM:**
  - Voice Studio's own footprint was +431 MiB, which is the CUDA context of the process, released at `-Stop`. KittenTTS added nothing.
  - **+2.1 GB stayed resident in ODS after the stop.** This is most likely ODS Whisper loading for this request, which also explains the 13.9 s transcription (and VS-05's 17.3 s) as a cold load. That supersedes the Meetings-queueing explanation in the VS-05 notes. It is not verified; a warm second transcription was outside the approval.
  - LLM plus Whisper ≈ 27.4 GB, leaving ≈ 5 GB for TTS, which matches ARCHITECTURE §4.
- **Key scan:** 13 written files plus the work dir. The relay key is in none.
- **`-Stop`:** clean, with no process left and no residue.
- **Acceptance B:** all five items met.
