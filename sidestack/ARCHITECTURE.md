# SideStack Voice Studio — Architecture

Covers Phases 1–3: Voice Studio runs on the Windows host, with ODS providing the LLM and ASR.
The optional ODS Docker variant (VS-13) is described in §7.

## 1. Components

| Component | Runs where | Address | Role |
|---|---|---|---|
| Voice Studio backend + web UI | Windows host (uv venv, CUDA torch) | `127.0.0.1:3900` | FastAPI backend. Serves `frontend/dist`, the `/v1` OpenAI-compatible speech API and MCP. Runs the TTS engines on the GPU. |
| ODS local model relay | ODS (Docker in WSL2) | `127.0.0.1:4007/v1` | Authenticated path to ODS model-router → llama-server (Qwen 3.8 27B). Bearer key from the Windows user env `ODS_LOCAL_MODEL_RELAY_KEY`. Model ids `ods/current`, `default`. |
| ODS Whisper | ODS (Docker) | `127.0.0.1:9000/v1` | OpenAI-compatible transcription (faster-whisper large-v3-turbo; diarization endpoint available). |
| Launcher page | Windows host (`pythonw`, started at logon) | `127.0.0.1:3901` | `sidestack/scripts/voice_studio_launcher.py` (VS-27). Forwards to Voice Studio when it is up; otherwise runs `Start-VoiceStudio-ODS.ps1`, then forwards. |
| ODS dashboard | ODS (Docker) | ODS UI | Lists Voice Studio under Applications. Links and health-checks the launcher page from the container via `host.docker.internal:3901`. |
| DeepSeek Harness | Windows host | `localhost:3080` | Build agent for lanes (ODS provider through the same relay). Not used at runtime. |

## 2. Request paths

```
Voice Studio feature          → Voice Studio service              → upstream
─────────────────────────────────────────────────────────────────────────────────────
Dub translate / polish / dir. → services/llm_backend.py           → relay 127.0.0.1:4007/v1/chat/completions
Transcribe / dub ASR / QC     → asr_backend OpenAICompatASRBackend → ODS Whisper 127.0.0.1:9000/v1/audio/transcriptions
Voice clone / TTS / audiobook → services/tts_backend.py + engines  → local GPU (admission gate, VS-06)
Other SideStack apps          → POST 127.0.0.1:3900/v1/audio/speech (Bearer OMNIVOICE_API_KEY)
Agents                        → Voice Studio MCP (backend/mcp_server.py)
```

Both ODS URLs are loopback, so the fork's built-in rule ("credentialed plain HTTP only on
loopback", in `llm_providers.credential_transport_error` and
`asr_backend.normalize_openai_compat_asr_base_url`) passes without code changes.

## 3. Configuration

The env profile lives in [config/ods.env.example](config/ods.env.example). The launcher (VS-07)
loads it. Secrets are **never** written to the file. The launcher copies them from Windows user
env vars into the backend process:

| Voice Studio variable | Value | Source |
|---|---|---|
| `LLM_DEFAULT_PROVIDER` | `custom` (Phase 2 start), then `ods` after VS-04 | profile |
| `TRANSLATE_BASE_URL` | `http://127.0.0.1:4007/v1` | profile |
| `TRANSLATE_MODEL` | `ods/current` | profile, confirmed by VS-03 |
| `TRANSLATE_API_KEY` | relay key | user env `ODS_LOCAL_MODEL_RELAY_KEY` |
| `OMNIVOICE_ASR_BACKEND` | `openai-compat-asr` | profile |
| `ASR_OPENAI_COMPAT_BASE_URL` | `http://127.0.0.1:9000/v1` | profile |
| `ASR_OPENAI_COMPAT_MODEL` | `deepdml/faster-whisper-large-v3-turbo-ct2` (the one SideStack Meetings uses) | confirmed by VS-05 |
| `OMNIVOICE_SERVER_MODE` | `1` | profile |
| `OMNIVOICE_API_KEY` | long random value | user env `SIDESTACK_VOICESTUDIO_API_KEY` |
| `OMNIVOICE_DATA_DIR` | `E:\SideStackAI\data\voice-studio` | profile |
| `HF_HOME` | `E:\SideStackAI\data\voice-studio\huggingface` | profile |

## 4. GPU budget (RTX 5090, 32 GB)

Figures measured on ODS on 2026-11-05. Re-measure with `nvidia-smi` before relying on them.

| Resident | VRAM |
|---|---|
| Qwen 3.8 27B IQ4_XS at 64k context | ~20.2 GB |
| Qwen 3.8 27B IQ4_XS at 128k context | ~24.5 GB |
| + ODS Whisper loaded (kept for 24 h by default) | +~2 GB |
| Windows desktop / other | ~0.5–1 GB |
| **Left for Voice Studio TTS at 128k** | **~4.5–5 GB** |
| **Left for Voice Studio TTS at 64k** | **~8.5–9 GB** |

Rules:

1. Voice Studio never loads its own LLM or Whisper. ASR is pinned to `openai-compat-asr`.
2. **Admission gate (VS-06, VS-15):** before a TTS engine loads, compare the engine's
   VRAM floor plus a 1 GB margin against free VRAM. Refuse with "Not enough free GPU memory:
   need X GB, have Y GB", advising the user to free ODS's LLM or pick a CPU engine. Never evict
   or unload ODS models; that is the user's call.
3. **Voice Studio first (decision D3, VS-15):** Voice Studio is used on its own, so there is no
   reserve for ODS. Large engines run once ODS's LLM is unloaded; upstream releases idle
   Voice Studio engines after 15 minutes so ODS can reload.
4. One heavy job at a time. Long audiobook or dub renders are queued, not run in parallel.

## 5. Data and files

| What | Where | In git? |
|---|---|---|
| App data (projects, voices, settings DB, outputs) | `E:\SideStackAI\data\voice-studio\` | No |
| Model cache | `E:\SideStackAI\data\voice-studio\huggingface\` | No |
| Python environment (uv, CUDA torch) | `E:\SideStackAI\data\voice-studio\venvs\voicestudio-001\` (never inside a harness workspace; see harness/README.md) | No |
| Launcher state, logs, pid | `E:\SideStackAI\data\voice-studio\run\` | No |
| Lane staging, harness run notes | `sidestack/work/` | No (gitignored) |
| Plans, specs, scripts, manifest draft | `sidestack/` | Yes (public) |
| Harness worktree | `E:\SideStackAI\worktrees\deepseek\voicestudio-<lane>` | Branch only |

## 6. Security boundary

- Everything binds to `127.0.0.1`. Nothing listens on the LAN. ODS reaches Voice Studio
  through `host.docker.internal`, as it does for Meetings.
- `OMNIVOICE_SERVER_MODE=1` requires `OMNIVOICE_API_KEY` for admin and settings routes. Callers of
  `/v1/audio/speech` send it as a Bearer token.
- Keys come from Windows user env vars and are passed to the child process only. They are never
  printed, logged, written to `sidestack/`, or committed.
- No cloud LLM, ASR or analytics. Voice Studio Cloud and Pro stay off, and cloud providers are
  left unconfigured.
- Voice cloning needs consent. Fixtures are TTS-generated synthetic voices only, never
  recordings of real people.

## 7. Optional later: ODS Docker extension (VS-13)

In this variant, Voice Studio runs as a GPU container on `ods-network`, built from this fork's
`deploy/Dockerfile`. It would reach the router or relay and Whisper by service name. Those
are non-loopback HTTP URLs, so the fork refuses them. VS-13 adds an **explicit opt-in allowlist**
(for example `OMNIVOICE_TRUSTED_HTTP_HOSTS=local-model-relay,ods-whisper`), with tests, rather
than loosening the rule globally. Choose this only if decision D1 changes.
