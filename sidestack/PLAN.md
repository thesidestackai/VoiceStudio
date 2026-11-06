# SideStack Voice Studio — Plan

- **Owner:** thesidestackai
- **Written:** 2026-11-05
- **Branch:** `sidestack/foundation-001`
- **Builder:** DeepSeek Harness on the ODS model, with lane specs written and checked by a reviewer agent

## 1. Goal

A voice studio for SideStack, with voice cloning, text-to-speech, dubbing, transcription and audiobooks, that:

1. runs locally on the SideStack workstation (RTX 5090, 32 GB);
2. uses **ODS** for language-model work (dub translation, script polish, director) through the
   ODS local model relay, and for speech recognition through **ODS Whisper**, so it never loads a
   second LLM or a second Whisper onto the GPU;
3. appears in **ODS → Applications** with a health check, like SideStack Meetings and the
   DeepSeek Harness;
4. exposes its OpenAI-compatible speech API (`/v1/audio/speech`) so other SideStack apps can use
   it, such as Meetings reading a summary aloud;
5. is built in small, verified lanes by the **DeepSeek Harness** (`dsh web`, ODS provider).

**Out of scope for now:** mobile apps, Electron desktop packaging, VoiceStudio Pro/Cloud,
telephony, and any cloud LLM or cloud ASR provider. Cloud calls stay off.

## 2. Starting point (verified 2026-11-05 by reading the code)

| Need | Already in the fork | Where |
|---|---|---|
| LLM via an OpenAI-compatible endpoint | Provider registry with a `custom` provider (`TRANSLATE_BASE_URL`/`_API_KEY`/`_MODEL`) and env pin `LLM_DEFAULT_PROVIDER`. A keyed endpoint over plain HTTP is accepted **only on loopback**. | `backend/services/llm_providers.py` (`credential_transport_error`, `active_provider_id`) |
| Remote ASR | Backend `openai-compat-asr`, selected with `OMNIVOICE_ASR_BACKEND`. URL, model and key come from `ASR_OPENAI_COMPAT_*`. Plain HTTP is accepted **only on loopback**. | `backend/services/asr_backend.py` (around line 2364) |
| Serve TTS to other apps | OpenAI-compatible router on `/v1`: `audio/speech`, `audio/transcriptions`, `audio/translations`, `models`, `audio/voices` | `backend/api/routers/openai_compat.py` |
| Agent/automation access | MCP server mounted in the backend | `backend/mcp_server.py` |
| Headless web UI | `bun run build:web` → `frontend/dist`, served by the backend on port 3900 (`OMNIVOICE_SERVER_MODE=1`, `OMNIVOICE_API_KEY`) | `deploy/Dockerfile`, `backend/docker_entrypoint.py` |
| GPU awareness | Memory budget, GPU gateway and engine memory modules | `backend/services/memory_budget.py`, `gpu_gateway.py`, `engine_memory.py` |

**What this means:** connecting Voice Studio to ODS is mostly **configuration, a launcher, an ODS
manifest and a GPU admission check**. The first version needs little or no new product code.

**Fork facts:**
- The fork is public, with parent `debpalash/VoiceStudio`, licensed AGPL-3.0-only, with one submodule (`omnivoice-gallery`).
- The upstream `AGENTS.md`/`CLAUDE.md` contain upstream-maintainer rules. [AGENTS-SIDESTACK.md](AGENTS-SIDESTACK.md) says which of those apply here.

**Workstation facts:**
- Windows has Python 3.11, Node and Git. **`uv` and `bun` are not installed.**
- The DeepSeek Harness works on the ODS model with a 128k context.
- Its *Workspace Write* sandbox failed on the root workspace `E:\SideStackAI` because of a Windows ACL error. A narrower workspace is untested.

## 3. Target shape (Phase 1–3)

```
Browser ──► ODS dashboard ─ Applications ─► http://localhost:3900  (Voice Studio web UI)
                                                │
Windows host                                    ▼
  Voice Studio backend (uvicorn, 127.0.0.1:3900, serves frontend/dist + /v1 speech API + MCP)
     │ LLM  : custom provider → http://127.0.0.1:4007/v1  (ODS local model relay, Bearer key)
     │ ASR  : openai-compat-asr → http://127.0.0.1:9000/v1 (ODS Whisper)
     │ TTS  : local engines on the RTX 5090 (admission-checked against free VRAM)
     ▼
ODS (WSL2 + Docker): relay → model-router → llama-server (Qwen 3.8 27B) ; ods-whisper
```

Full detail is in [ARCHITECTURE.md](ARCHITECTURE.md).

## 4. Decisions needed (recommendation first)

| ID | Decision | Recommendation | Why |
|---|---|---|---|
| D1 | Where Voice Studio runs | **Windows host first** (like Meetings). Treat an ODS Docker extension as optional, in Phase 4. | Loopback URLs to the relay (:4007) and Whisper (:9000) pass the fork's HTTP safety rules with no code change. Inside Docker the same calls are non-loopback HTTP and get refused, so the code would need a patch (VS-13). |
| D2 | Default TTS engines and licensing | Use OmniVoice for **personal and internal** work only. Before any commercial output, pick engines whose weight licences allow it, and record each in `backend/config/model_licenses.json`. | The default OmniVoice weights are CC-BY-NC, and the audio tokenizer carries extra terms. |
| D3 | ODS context size while Voice Studio is active | **Keep 128k and use small or CPU TTS engines.** If the budget check fails, switch ODS back to 64k with the existing rollback script, operated by the user. | At 128k plus Whisper, about 5 GB of VRAM is left; at 64k, about 9 GB. See ARCHITECTURE §4. |
| D4 | Product name in the UI | Show **"SideStack Voice Studio"** in the ODS entry and launcher only. Leave in-app strings alone until Phase 4 (VS-11). | Renaming touches 21 locale catalogs and upstream tests, so it costs a lot during merges. The AGPL notices must stay either way. |
| D5 | Upstream sync | Merge upstream `main` **monthly**, or on a security fix, in its own lane (VS-12). | SideStack edits stay in `sidestack/` plus a few named files, so merges stay cheap. |
| D6 | Commit attribution | Follow the fork's `commit-identity` rule: commits carry the human identity only, with no agent trailers. | The upstream CI check enforces it, and keeping it avoids red CI after merges. |
| D7 | Repository visibility | Keep the fork **public**, because AGPL makes the source available anyway. Keep everything private out of git. | It is already public. Secrets, ODS internals and recordings go in `E:\SideStackAI\data\voice-studio` or `sidestack/work/` (gitignored). |

None of D1–D7 blocks Phase 0 or the first two lanes of Phase 1.

## 5. Phases and lanes

Each lane is one spec in [`lanes/`](lanes/) and one harness session, ideally under 30 minutes. The
**Run by** column names who executes the lane: Operator means the user or the reviewer agent,
and dsh means the DeepSeek Harness. Lanes that need approval stop at their gate.

| Phase | Lane | Outcome | Run by | Gate |
|---|---|---|---|---|
| 0 Foundation | VS-F0 | This `sidestack/` folder, AGENTS pointer, validator | Reviewer | Commit OK |
| 1 Harness + toolchain | [VS-00](lanes/VS-00-harness-preflight.md) | Harness workspace on a worktree; the sandbox can write; the test file round-trips | Operator | — |
| | [VS-01](lanes/VS-01-windows-toolchain.md) | `uv` + `bun` installed; `uv sync` and `bun install` succeed in the worktree | Operator | **Install approval** |
| | [VS-02](lanes/VS-02-baseline-and-web-mode.md) | Baseline offline backend test count recorded; headless web mode on 127.0.0.1:3900 confirmed | dsh | — |
| 2 ODS wiring | [VS-03](lanes/VS-03-ods-env-profile.md) | `config/ods.env.example` verified live: the LLM answers through the relay and the model id is confirmed | dsh + Operator probe | **ODS probe approval** |
| | [VS-04](lanes/VS-04-ods-llm-provider.md) | First-class `ods` LLM provider (loopback default, relay key env, `ods/current`) + tests | dsh | — |
| | VS-05 | ODS Whisper as ASR: config + one synthetic transcription (TTS-generated clip, no real voices) | dsh + Operator run | **Real run approval** |
| | VS-06 | ODS admission gate: before a TTS engine loads or an LLM call starts, check the relay `/v1/models` and free VRAM; refuse with a clear message | dsh | — |
| 3 ODS Applications | VS-07 | `Start-VoiceStudio-ODS.ps1` (start/stop/check, data in `E:\SideStackAI\data\voice-studio`, key from user env, never printed) | dsh | — |
| | VS-08 | ODS Applications entry ([ods/manifest.yaml](ods/manifest.yaml)) installed per [ods/APPLY.md](ods/APPLY.md) | Operator | **ODS change approval** |
| | VS-09 | End-to-end acceptance on synthetic text: speech via `/v1/audio/speech`, a dub translation through ODS, a transcription through ODS Whisper; report in `sidestack/work/` | Operator | **Real run approval** |
| 4 SideStack | VS-10 | Meetings "read summary aloud" through Voice Studio's `/v1/audio/speech` (lane in the Meetings repo) | dsh | Design OK |
| | VS-11 | Branding: "SideStack Voice Studio" in-app (all 21 locales, parity tests) | dsh | D4 |
| | VS-12 | Upstream sync runbook + first merge | Operator | — |
| | VS-13 | Optional: ODS Docker extension (GPU compose) + an explicit private-network HTTP allowlist patch | dsh | D1 |

Specs for VS-05 onward are written when their turn comes, from [harness/LANE-TEMPLATE.md](harness/LANE-TEMPLATE.md).
Writing them earlier would let them go stale.

## 6. How a lane runs (DeepSeek Harness loop)

1. **Spec:** the reviewer writes `lanes/VS-xx-*.md`, with exact files, exact acceptance commands and expected test counts. Long code or fixtures are staged in `sidestack/work/VS-xx/` with SHA-256 hashes.
2. **Run:** the operator opens dsh on the worktree workspace and pastes [harness/KICKOFF-PROMPT.md](harness/KICKOFF-PROMPT.md) with the lane id. Each harness turn stays well under 600 s (see §8).
3. **Verify on disk:** the reviewer re-runs the acceptance commands, checks hashes and `git status`, and runs `python sidestack/scripts/check_sidestack.py`. **The harness's own PASS report is never accepted alone.**
4. **Commit:** human identity, one lane per commit, with a message that names the lane. Push only when the user says so.
5. **Track:** update [lanes/README.md](lanes/README.md).

## 7. Gates (always ask first)

- Installing anything on Windows (`uv`, `bun`, Python wheels, models).
- Any ODS inspection or change: probes against the relay or Whisper, manifests, `docker restart`, context-size changes.
- Any real inference run, including synthetic runs. Real voices and private recordings are never used as fixtures.
- Downloading model weights. VoiceStudio already asks before downloads; keep `HF_HUB_OFFLINE=1` in tests.
- Pushing, opening PRs, or changing repository settings.

## 8. Risks and how the plan handles them

| Risk | Handling |
|---|---|
| GPU out of memory, because the LLM, Whisper and TTS share 32 GB | VS-06 admission gate; small engines by default; D3 fallback to 64k; one heavy job at a time |
| Harness limits: the router returns tool calls as one chunk, and turns over 600 s fail | Lanes are small and staged; specs give exact commands; long installs run by the operator, not dsh |
| Harness sandbox ACL failure on `E:\SideStackAI` | VS-00 tests a narrow worktree workspace first; fallback is a workspace under `C:\Users\ssam8` |
| Agent reports are inaccurate (seen with OpenCode) | Verify on disk; hash-pinned staged files; tests counted, not trusted |
| Upstream churn (large repo, frequent releases) | SideStack code isolated in `sidestack/`; monthly sync lane |
| Leaking secrets to a public repo | `check_sidestack.py` secret scan; keys only in user env vars; `.gitleaks.toml` already in CI |
| Licences of model weights | D2; the licence records in `backend/config/model_licenses.json` |

## 9. Done means

- Voice Studio opens from ODS → Applications and shows healthy while running.
- A dub translation uses the ODS model, and a transcription uses ODS Whisper, with no second LLM or ASR model on the GPU.
- Speech generation works with the admission gate active, and an over-budget load is refused cleanly.
- Another SideStack app can call `POST http://127.0.0.1:3900/v1/audio/speech` with the API key.
- All lanes are committed, tests are green offline, and `check_sidestack.py` passes.
