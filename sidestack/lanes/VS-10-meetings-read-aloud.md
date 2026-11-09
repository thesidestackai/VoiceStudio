# VS-10 — Meetings "read summary aloud" through Voice Studio

- **Phase:** 4
- **Run by:** built in the **SideStack Meetings repo**, as two Meetings lanes (backend, then frontend). This file is the design; the Meetings lane specs are written after the design OK.
- **Gate:** **Design OK** (this document), then **real run approval** for the end-to-end check.
- **Depends on:** VS-09 (`/v1/audio/speech` is gated and verified with KittenTTS).
- **Status:** **parked** (2026-11-06). Kept as a reference for a possible future integration between Voice Studio, ODS and other SideStack apps. Voice Studio stays a standalone app; its speech API, which this design would use, already works (VS-09). Nothing here is planned to be built, and the decisions below are open.

## Goal

On a meeting page that has a summary, a **Read aloud** button plays the summary and the action
items as speech. The speech comes from Voice Studio's OpenAI-compatible `POST /v1/audio/speech`
on `127.0.0.1:3900`. Nothing leaves the machine, and nothing new is stored.

## Recommended design

```
browser ──POST /meetings/{id}/summary/speech──▶ Meetings backend (:8901)
                                                  │ builds the text from the stored summary
                                                  │ splits it into parts of ≤ 1,500 characters
                                                  ▼
                                   Voice Studio (:3900) POST /v1/audio/speech, once per part
                                   {"model": "kittentts", "voice": "default",
                                    "response_format": "pcm", "input": <part>}
                                                  │ raw 24 kHz 16-bit mono per part
                                                  ▼
                                   Meetings joins the parts (0.4 s of silence between),
                                   wraps them as WAV with the stdlib `wave` module
browser ◀── audio/wav, Cache-Control: no-store ──┘
```

1. **The backend calls Voice Studio; the browser never does.**
   - Voice Studio needs no CORS change, and the page talks to one origin as it does today.
   - Errors become Meetings' own fixed messages.
   - The call is one loopback request per part, keyless. Voice Studio's key check always lets loopback through, and the launcher removes the key anyway.
2. **The engine is KittenTTS**, as verified in VS-09:
   - it runs on the CPU, so it adds no VRAM next to ODS;
   - it is Apache-2.0;
   - a warm request took 6.3 s for 8.3 s of audio.

   The engine and voice are settings, so a GPU engine can be tried later. A GPU engine is then refused by the VS-06 gate when memory is short.
3. **`pcm`, not `mp3`.** Voice Studio always resamples `pcm` to 24 kHz 16-bit mono, so parts join byte for byte, and no ffmpeg is needed on either side. A WAV of a 2-minute summary is about 5.8 MB, which is fine over loopback.
4. **On demand, not stored.** Audio is made per click and sent with `no-store`. Nothing about it goes into the Meetings database or upload folder. Voice Studio's speech route writes no history; the real run checks its logs for the text as well.
5. **One job at a time.** The route takes Meetings' existing GPU job lock without waiting, the same as transcribe, summarise and ask. If another job is running, it answers 409. That follows Meetings AGENTS §2 even though KittenTTS itself is CPU.

### What is read

Read in this order:
1. "Summary of *title*."
2. Each summary point as a sentence.
3. "Action items." Then each item as: *detail*, then "Owner: *name*." and "Due: *date*." when they are set.

- Speaker labels are replaced with the speaker names, using the export's `apply_speaker_names`.
- Markdown characters are stripped.
- Evidence quotes and timestamps are not read.
- The text is capped at 6,000 characters (4 parts). Above that, the route answers 422 "summary is too long to read aloud". Real summaries are 10 points at most, so this should not happen.

## Files

All of these are in the Meetings repo, split into two lanes that follow that repo's workflow.

**Lane A, backend:**

| Path | Change |
|---|---|
| `backend/adapters/base.py` | `SpeechAdapter` (`synthesize(text) -> bytes` of 24 kHz mono PCM, `status()`), `SpeechError(code)` |
| `backend/adapters/fake_speech.py` | new: deterministic PCM (a short tone per part), for tests and development |
| `backend/adapters/voicestudio_speech.py` | new: httpx client with an injectable transport, like `ods_whisper.py` |
| `backend/speech_text.py` | new: pure functions that build the spoken text from the summary, items and names, and split it into parts |
| `backend/config.py` | `SIDESTACK_SPEECH_ADAPTER` `off` (default) / `fake` / `voicestudio`; `SIDESTACK_SPEECH_URL` (default `http://127.0.0.1:3900`, loopback-only, validated like the other URLs); `SIDESTACK_SPEECH_MODEL` (default `kittentts`); `SIDESTACK_SPEECH_VOICE` (default `default`); `SIDESTACK_SPEECH_TIMEOUT_S` (default 300, range 30–1800, per part) |
| `backend/app.py` | `POST /meetings/{id}/summary/speech`; `/health` gains `adapters.speech` |
| `tests/test_speech_*.py` | new |
| `README.md`, `AGENTS.md` §1 | the new setting and route; **AGENTS §1 gains a "TTS" line (a user decision, see below)** |

**Route answers.** Every message is fixed text and never contains summary text:

| Case | Answer |
|---|---|
| Meeting not found | 404 |
| Meeting has no summary | 409 "meeting has no summary" |
| Another job is running | 409 |
| Adapter is `off` | 503 "read aloud is off" |
| Text over 6,000 characters | 422 |
| Voice Studio not listening | 503 "Voice Studio is not running" |
| Voice Studio 503 `insufficient_gpu_memory` | 503 "not enough GPU memory for the voice engine" |
| Voice Studio 429, or any other 503 | 503 "Voice Studio is busy" |
| Voice Studio 403 (licence not accepted) | 502 "accept the voice engine's licence in Voice Studio" |
| Voice Studio returns other non-200, a non-`audio/pcm` body, or an empty or odd-length body | 502 |
| A part times out | 504 |
| Success | 200 `audio/wav`, no filename, `Cache-Control: no-store` |

**Lane B, frontend:**
- `api/meetings.ts` gains `summarySpeech(id, {signal})`, returning a Blob and checking the type is `audio/wav`.
- A `speechView.ts` maps error messages.
- `SummarySection` gets a **Read aloud** button and an `<audio controls>` player:
  - the button is disabled while the audio is being made, with the note "Making the audio. This can take a minute.";
  - the request is aborted when the page unmounts;
  - the object URL is revoked when the player is replaced or the page unmounts;
  - errors appear under the button.
- Tests use the existing `test/` pattern. The lane is browser-checked against the `fake` adapter.

**No Voice Studio code changes.** The Voice Studio side is this design and the tracker row.

## Decisions for the user

1. **Engine:**
   - **KittenTTS** (recommended): CPU, no extra VRAM, already verified.
   - Alternatively, OmniVoice: GPU, better voices. Its weights are CC-BY-NC, for personal use only (D2), and at 128k the VS-06 gate may refuse it.
2. **AGENTS.md in Meetings.** §1 "Inference Routing" lists every endpoint the app may call, and §4 forbids unapproved calls. The design needs a new line there:

   > TTS: SideStack Voice Studio `http://127.0.0.1:3900/v1/audio/speech`, adapter `voicestudio`, opt-in, off by default.

   The user commits AGENTS.md, as with the ODS amendment.
3. **Who builds it.** Recommended: the Meetings repo's usual workflow (prototype → lane spec in its `tmp\` → builder copies → reviewer verifies → user commits). The DeepSeek Harness is set up only for the Voice Studio worktree.
4. **Prerequisite:** the Meetings worktree still has the upload-hardening lane (H-AG) verified but uncommitted. It should be committed first, so these lanes start from a clean tree.

### Alternative considered

- **ODS's own Kokoro TTS.** ODS already serves it, so read-aloud would work without Voice Studio running.
- It is not recommended, because the plan's goal is one SideStack voice app that other apps call (PLAN goal 4), with voice profiles and engine choice there.
- It stays a fallback: the adapter shape would allow a `kokoro` adapter later.

## Preflight

- The design is OK'd, and the decisions below are answered.
- The Meetings worktree is clean (H-AG committed), and its tests pass at their current counts.
- Before the real run:
  - Voice Studio's `/health` returns 200 on `127.0.0.1:3900`;
  - KittenTTS is cached, which it is after VS-09.

## Steps

1. Write lane A (backend) as a Meetings lane spec, with a prototype and mutation checks, and hand it to the Meetings builder. Review it on disk, then the user commits.
2. Do the same for lane B (frontend), adding the browser check with the `fake` adapter.
3. After approval, do the real run below, and record it here under "Reviewer notes".

## Acceptance

**Offline (each lane):**
- New tests pass and existing ones still pass:
  - the spoken-text builder (order, names, markdown stripped, splitting on sentence boundaries, the 6,000 cap);
  - WAV assembly (header, 24 kHz mono, silence between parts);
  - the request body sent to Voice Studio;
  - every row of the error table, using a mock transport;
  - config validation (a non-loopback URL is refused);
  - the lock (409);
  - `/health`.
- Mutation-checked, as in the other Meetings lanes.
- The frontend lane passes typecheck and tests, and is browser-checked with `SIDESTACK_SPEECH_ADAPTER=fake`.

**Real run (after approval):**
- Setup:
  - Voice Studio is started with `Start-VoiceStudio-ODS.ps1`.
  - A scratch Meetings backend runs with a scratch database, `SIDESTACK_SPEECH_ADAPTER=voicestudio`, and the fake LLM, so the summary is synthetic and needs no ODS LLM.
- Steps:
  1. Read the summary aloud and save the WAV.
  2. Transcribe it once through ODS Whisper.
  3. Score the words against the spoken text using the VS-05 rules. Pass if ≥ 0.9.
- Record:
  - the latency per part;
  - VRAM before and after;
  - that Voice Studio's logs do not contain a nonce word planted in the summary.
- Stop both apps afterwards.

## Out of scope

- Streaming playback (the speech route's `sse` mode), and choosing voices or speed in the UI.
- Reading the transcript or Q&A answers aloud.
- Starting Voice Studio from Meetings (it stays a manual launcher start, and ODS never starts it).
- Voice cloning, real voices, and anything commercial.

## Reviewer notes

Checked in Voice Studio's code while writing this design (2026-11-06):
- `create_speech` stores no history, and neither does `_run_tts`.
- `pcm` is returned as `audio/pcm`, resampled to 24 kHz 16-bit mono.
- `input` is capped at 4,096 characters, which is why the text is split into parts of 1,500.
- `BearerKeyMiddleware` always lets loopback callers through.
