# VS-16 — Voice cloning and voice design with VoxCPM2 (commercial-use engine)

- **Phase:** 4
- **Run by:** Operator (Parts A and B). A follow-up dsh lane sets the VRAM floor from Part B's measurement.
- **Gate:**
  - **Part A, install approval:** Voice Studio's one-click sidecar install of VoxCPM2. About 10 GB on E: (a Python 3.11 venv with CUDA PyTorch 2.11 and `voxcpm==2.0.3`), downloaded from PyPI and the PyTorch index.
  - **Part B, real run approval:**
    - the first synthesis downloads the `openbmb/VoxCPM2` weights from Hugging Face (2.29B parameters, several GB) into the data dir's HF cache;
    - VoxCPM2 is loaded on the GPU while ODS's LLM is unloaded;
    - a handful of ODS Whisper transcriptions.
- **Depends on:** VS-07 (launcher), VS-09, VS-15 (decision D3)
- **Status:** verified (Parts A and B PASS 2026-11-06, including the user's listening verdict)

## Goal

Prove Voice Studio can **design** a voice from a text description and **clone** a voice from a reference clip with an engine whose licence allows commercial use (for example, monetized YouTube videos), on this machine, beside ODS.

**Why VoxCPM2:**
- Apache-2.0 (Voice Studio's licence registry: category `commercial`, from the model card; not legal advice).
- It does both voice design (no reference audio) and zero-shot cloning.
- 48 kHz output, 30 languages.
- One-click sidecar install into its own venv, so nothing it installs touches Voice Studio's environment or another engine.

OmniVoice, the default engine, is CC-BY-NC (decision D2), so it stays personal/internal only.

**Only synthetic voices.** The cloning reference is the voice VoxCPM2 itself designs in this run. No real person's voice is used, recorded or stored.

**Known gap this lane measures:** VoxCPM2 declares no VRAM floor (`min_vram_gb = 0.0`). The admission gate therefore counts only the 1 GB margin for it, and would admit it even with ODS's LLM loaded (about 4.8 GB free). Part B measures its real VRAM; a follow-up dsh lane sets a SideStack floor from that number.

## Files

| Path | Change |
|---|---|
| `sidestack/lanes/VS-16-voxcpm2-cloning.md`, `sidestack/lanes/README.md` | results / status |
| `sidestack/work/VS-16/` (gitignored) | report, clips, raw JSON |
| `E:\SideStackAI\data\voice-studio\engines\voxcpm2\` (outside git) | the sidecar install (Part A) |
| `E:\SideStackAI\data\voice-studio\huggingface\` (outside git) | the VoxCPM2 weights (Part B) |

No source code changes in this lane.

## Preflight

```powershell
Get-PSDrive E          # expect: well over 25 GB free
Test-Path E:\SideStackAI\data\voice-studio\engines\voxcpm2   # expect: False (not installed yet)
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader   # record
```

Also check the Windows per-process counter `\GPU Process Memory(*)\Dedicated Usage` for ODS's WSL VM (`vmwp`). If it holds ODS's LLM (about 20 GB or more), stop and tell the user. Voice Studio never unloads ODS models (decision D3); the user frees the LLM in ODS or waits until ODS unloads it.

## Steps

**Part A — install (after install approval).**
1. Start Voice Studio with the launcher.
2. `POST /engines/sidecar/voxcpm2/install`, then poll `GET /engines/sidecar/voxcpm2/install/status` until it finishes. Record the duration, the final status, and the folder size.
3. Confirm the engine is available: `GET /engines` lists `voxcpm2` as available.

**Part B — design and clone (after real run approval).**
4. Start sampling every 0.5 s: total `memory.used`, and the per-process GPU memory of Voice Studio's process and of any VoxCPM2 sidecar child process.
5. **Voice design:** `POST /generate`, multipart, with:
   - `engine=voxcpm2`;
   - `instruct`: "A calm, warm adult narrator with a neutral accent, speaking clearly at a moderate pace.";
   - `text`: "Welcome to the SideStack channel. Today we build a voice studio that runs on your own computer.";
   - `language=en`.
   Save the WAV as `designed.wav`. This first call downloads the weights; record the time and the download size.
6. **Voice design again (warm):** the same request. Record the latency.
7. **Clone:** `POST /generate` with `engine=voxcpm2`, `ref_audio=designed.wav`, `ref_text` set to the step 5 text, and a new `text`: "This second sentence was never spoken by the reference voice, so it tests real cloning." Save `cloned.wav`. Then run the same request a second time and record both latencies.
8. **Intelligibility:** transcribe `designed.wav` and `cloned.wav` through `POST /v1/audio/transcriptions` (ODS Whisper). Score word accuracy with the VS-05 rules. Pass if ≥ 0.9 each.
9. **Similarity:** the operator does not score speaker similarity. The user listens to `designed.wav` and `cloned.wav` and judges.
10. Stop sampling. Record:
    - the peak VRAM of Voice Studio plus its sidecar;
    - the free VRAM at that peak;
    - the HF cache size added;
    - any refusal from the admission gate.
11. `-Stop`. Check that no sidecar process is left behind, and record the VRAM after stop. Write `sidestack/work/VS-16/report.md`.

## Acceptance

- Part A: the install finishes, and `voxcpm2` is listed as available.
- Part B:
  - design and clone both return 200 with 48 kHz audio;
  - both clips score transcription accuracy ≥ 0.9;
  - the peak VRAM is recorded;
  - no sidecar is left after `-Stop`;
  - no keys appear in the logs.
- The user's listening verdict on the clone is recorded in the report (pass, or not good enough).

## Out of scope

- Changing VoxCPM2's VRAM floor or the gate (a follow-up dsh lane, using Part B's number).
- CosyVoice 3 and MOSS-TTS v1.5, the other Apache-2.0 cloning engines (later, if VoxCPM2 falls short).
- Cloning any real voice, including the user's own. When the user later clones their own voice for their videos, that is their choice and their data. It stays in the data dir, never in git.
- Legal clearance of the model licence. The registry entry comes from the model card.

## Reviewer notes

Checked in the code while writing this lane (2026-11-06):
- The sidecar spec is `services/sidecar_install.py` `"voxcpm2"`: Python 3.11, `voxcpm==2.0.3`, `torch==2.11.0`, required 10 GiB; weights download on first synthesis.
- `POST /engines/sidecar/{engine_id}/install` is in `api/routers/engines.py`.
- `/generate` takes `ref_audio`, `ref_text`, `instruct` and `engine`, and streams `audio/wav`.
- The checkpoint is `OMNIVOICE_VOXCPM_MODEL`, defaulting to `openbmb/VoxCPM2` (2.29B parameters, Apache-2.0 on the Hub).
- `docs/licensing/model-license-data.json` lists `openbmb/VoxCPM2` as category `commercial`. Commercial inference and outputs are marked `unknown` there, and the note says the identifier comes from the model card.
- `VoxCPM2SubprocessBackend` has `gpu_compat = ("cuda", "mps", "cpu")` and no `min_vram_gb`, so its floor is 0.0.

## Part A result (Operator, 2026-11-06, install approved): PASS

- `POST /engines/sidecar/voxcpm2/install` succeeded in 106 s. Steps:
  - preflight, create_venv, install_deps, verify (`import voxcpm` OK) and persist: done;
  - fetch_weights: skipped ("engine has no bundled-weights requirement"), so the weights still download at first synthesis (Part B).
- Install dir: `E:\SideStackAI\data\voice-studio\engines\voxcpm2\voxcpm2`, 5.17 GB (below the 10 GiB the installer reserves). Its venv has `torch 2.11.0+cu128` and `voxcpm==2.0.3`. The installer persisted `OMNIVOICE_VOXCPM2_DIR`, and no restart was needed.
- `GET /engines`: `voxcpm2` available, `supports_cloning` and `supports_voice_design` true, `max_ref_seconds` 30.
- The HF cache is unchanged (KittenTTS only). No keys in the logs. `-Stop` was clean, with no sidecar process left.
- VRAM after stop: 25,051 MiB, which looks like ODS's LLM + Whisper resident. **Part B needs ODS's LLM unloaded first** (decision D3).

## Part B blocker: ODS keeps its LLM loaded (read-only ODS inspection, 2026-11-06, user-approved)

ODS does not idle-unload its LLM; it stays resident until its container stops. Found read-only:
- `ods-llama-server` is its own container (llama.cpp `server-cuda-b11429`, `restart: unless-stopped`), separate from `ods-whisper`, the relay and Hermes. It serves one model (`--model`, not router mode), so there is no HTTP unload endpoint.
- The build supports `--sleep-idle-seconds` (default -1, disabled), which unloads the model after that many idle seconds. It is a command-line flag with no `LLAMA_ARG_*` env var, so turning it on means editing ODS's compose `command` (`docker-compose.base.yml`), which an ODS update may revert.
- `ods-hermes` and `ods-litellm` list `llama-server` as a dependency with `required: false`.
- The 28 GB free seen in VS-06 was therefore most likely a time the container was stopped.

## Part B result (Operator, 2026-11-06, user-approved): PASS

- **Freeing the GPU:** with the user's approval, only `ods-llama-server` was stopped (VRAM went from 25.3 to 3.3 GB). It was started again afterwards and was healthy in 100 s. ODS Whisper, Hermes and LiteLLM stayed up.
- **Voice design** (`/generate`, `instruct` only):
  - 200, 48 kHz;
  - 95 s cold, including the 4.62 GB weights download into the data-dir HF cache;
  - **20 s warm** for about 6 s of speech.
- **Clone** (`ref_audio` = the designed clip): 200, 48 kHz; 57 s the first time, **19 s warm**.
- **ODS Whisper** transcription accuracy 1.0 on both clips.
- **VRAM:** the VoxCPM2 sidecar holds **6.64 GB** and Voice Studio 0.43 GB, together **7.1 GB**. That does not fit beside ODS's loaded LLM (about 4.8 GB free). The gate counts 1 GB for VoxCPM2 today, so the follow-up is a SideStack floor of about 7 GB.
- No gate refusals, no keys in the logs, no sidecar left after `-Stop`. The report is in `sidestack/work/VS-16/report.md` (gitignored).
- **Listening verdict (user, 2026-11-06):** the clone sounds like the same speaker as the designed voice. PASS.
