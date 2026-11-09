# VS-29 — Verify existing features: dubbing, voice changer, long-form, streaming, pronunciation, Khmer

- **Phase:** 4
- **Run by:** Operator
- **Gate:** **real run approval** (given 2026-11-08): one window with ODS's LLM stopped and restarted, and the Demucs `htdemucs` weights download (MIT). AudioSeal (watermark detection) is skipped.
- **Depends on:** VS-28 (Voice Studio runs from the main checkout)
- **Status:** verified (Khmer listening PASS, 2026-11-08)

## Goal

Run, end to end and in the default commercial-only profile, the upstream features the SideStack lanes have not exercised yet. Record what works, what fails and why. **No code changes.**

These features came out of the ElevenLabs comparison (2026-11-08): dubbing, voice changer, long-form/audiobook, streaming TTS, pronunciation dictionary, batch, and Khmer speech (VoxCPM2 lists `km` among its 30 languages).

## Files

| Path | Change |
|---|---|
| `sidestack/lanes/VS-29-feature-verification.md`, `sidestack/lanes/README.md` | spec / results / status |

The audio, JSON and logs go to `sidestack/work/VS-29/`, which is gitignored.

## Preflight

```powershell
Invoke-WebRequest http://127.0.0.1:3900/health -UseBasicParsing   # expect: 200 (main checkout, commercial-only)
(curl.exe -s http://127.0.0.1:3900/engines | ConvertFrom-Json).tts.active   # expect: voxcpm2
nvidia-smi --query-gpu=memory.free --format=csv,noheader   # expect: about 7 GB with ODS's LLM loaded
```

## Steps

The driver is the Operator's script (`vs29.py`, kept outside the repo). It writes to `sidestack/work/VS-29/results.json`, and every input is synthetic: KittenTTS or VoxCPM2 speech from fixed sentences.

1. **Phase 1, ODS's LLM up:**
   - Pronunciation: create a `SideStack → Side Stack` respelling, call `/pronunciation/test`, generate with it, then delete the entry.
   - Streaming TTS over `/ws/tts` with KittenTTS: time to first audio.
   - Dub prep: upload a synthetic English WAV with `input_type=audio`. Demucs runs, and downloads `htdemucs` on first use. Then `transcribe-stream` (ODS Whisper, with source-speaker references), then `/dub/translate` to Spanish and Khmer with `provider=openai` (ODS's LLM).
2. **Phase 2, ODS's LLM stopped:**
   - Khmer speech with VoxCPM2 (`language=km`).
   - Dub generate in Spanish and in Khmer, cloning the source speaker, then download MP3 and M4A.
   - Create a voice profile from the synthetic clip.
   - Voice changer (`/convert`) from a VoxCPM2 clip into that profile.
   - A three-chapter audiobook in the profile voice, as MP3.
   - Streaming TTS with VoxCPM2.
   - Record the peak GPU memory used.
3. **Restart ODS's LLM**, wait until it is healthy, then run the Khmer round trip: ODS Whisper transcribes the Khmer WAV.
4. **The user listens** to the Khmer, Spanish dub and Khmer dub files.

## Acceptance

Each feature gets PASS, FAIL (with the error) or NOT RUN (with the reason) in the results below. ODS's LLM ends healthy with 0 restarts. `check_sidestack.py` reports OK.

## Out of scope

- **Batch:** it is a video-dubbing queue (`-map 0:v`), and one job translates (ODS's LLM) and speaks (VoxCPM2, about 8 GB) together. Both do not fit on the GPU at once beside ODS, so it is recorded, not forced.
- **Watermark detection:** AudioSeal is not installed (skipped by the user).
- **Phone calls (Twilio):** they need a Twilio account.
- **Fixes:** any failure becomes a follow-up lane.

## Reviewer notes

- Dub, audiobook and the voice changer always use the **active** engine (VoxCPM2); only `/generate` and `/ws/tts` take an `engine` field.
- The pronunciation dictionary applies in `/generate` only, not in dub, `/ws/tts`, batch or audiobook. Audiobook has its own `lexicon`.
- VoxCPM2 checks `km` against its language list but does not pass the language to the model; it reads the script.
- Dub translation defaults to Google (online) when `TRANSLATE_PROVIDER` is unset. The SideStack profile sets `openai` to ODS, and the driver also passes `provider=openai` explicitly.

## Results, first run (Operator, 2026-11-08)

Voice Studio ran from the main checkout in the commercial-only profile. All inputs were synthetic.

| Feature | Result | Details |
|---|---|---|
| Pronunciation dictionary | **PASS** | Create 200. `/pronunciation/test` turned "SideStack" into "Side Stack" (`applied_terms: [SideStack]`). `/generate` with it: 200 in 3.4 s. The entry was deleted afterwards. |
| Streaming TTS, KittenTTS | **PASS** | `/ws/tts`: first audio after 2.8 s (`ttfa_ms` 2,502), RTF 0.77, 24 kHz. |
| Streaming TTS, VoxCPM2 | **PASS, slow** | First audio after 4.5 s (`ttfa_ms` 4,184), RTF 2.1 (slower than real time), 48 kHz. |
| Dub upload + Demucs | **PASS** | An audio-only WAV (`input_type=audio`) was accepted. Demucs separated it with a background track (`has_bg: true`) in about 32 s, including the first-use `htdemucs` download. |
| Dub transcription (ODS Whisper) | **PASS on retry** | Run 1 timed out after 120 s (see the findings). Run 2 took 32 s: 2 segments, the right text, and a source-speaker clone reference (`auto:speaker_1`). |
| Dub translation, Spanish (ODS LLM) | **PASS** | 102 s, a correct Spanish translation. |
| Dub translation, Khmer (ODS LLM) | **PASS** | 31 s, a plausible Khmer translation (it keeps "SideStack" transliterated). |
| Dub generate, Spanish and Khmer | **FAIL** | `dub_timing_overflow`: "The speech does not fit its time slot". The default `timing_strategy=concise` rejects the whole dub if any line overruns its slot. The Spanish run generated every segment first (256 s) and only failed at assembly. |
| Khmer speech, VoxCPM2 (`km`) | **PASS** (user listened: "Khmer sounds good") | 200, 5.5 s of audio. It took 241 s including the cold sidecar load. |
| Khmer round trip (ODS Whisper, `language=km`) | **FAIL (ASR)** | Whisper returned a repeated-character loop, not text. Whisper large-v3-turbo is known to be weak on Khmer, so this does not show whether the speech is intelligible. The user's listening verdict decides. |
| Voice profile from a synthetic clip | **PASS** | `POST /profiles` 200 (with `ref_text`, so no auto-transcription). |
| Voice changer (`/convert`) | **PASS** | 200 in 18 s. ASR recognised the source sentence exactly; the output is 3.36 s in the profile voice and differs from the source. |
| Audiobook, 3 chapters, MP3 | **PASS** | SSE `started` → 3 × `chapter` → `assembling` → `done`: 37 s, 15.1 s of audio, 242 KB MP3, no failed chapters. |
| Batch | NOT RUN | See Out of scope. |
| Watermark detection | NOT RUN | AudioSeal is not installed (skipped). |

**GPU memory:** the peak during phase 2 was 21.8 GB used, with ODS's LLM stopped.

**Findings:**
1. **Cold ODS Whisper vs the dub timeout.**
   - ODS Whisper unloads its model after 300 s idle. Reloading it took 103 s.
   - With the 5 s decode, the first dub transcription took 128 s, past Voice Studio's 120 s per-chunk limit (`OMNIVOICE_TRANSCRIBE_CHUNK_TIMEOUT_S`).
   - A warm call takes 1.5 s.
   - Fix candidate: raise the timeout in the SideStack profile.
2. **The default dub timing is strict, and fails late.**
   - `concise` fails the whole job when a translated line is longer than its slot, which is common for English → Spanish or Khmer.
   - It only checks after generating every segment.
   - Next: retry with `smart_fit` (pitch-preserving stretch within caps).
3. **Restarting ODS's LLM while VoxCPM2 is warm stalls it.**
   - VoxCPM2's sidecar stays resident (about 7 GB, released after 900 s idle). llama-server's load then had about 0.5 GB of GPU memory free, and it was not healthy after 3 minutes.
   - Stopping Voice Studio freed the memory, and the LLM became healthy 130 s later with 0 restarts.
   - Runbook: stop Voice Studio (or wait for its idle unload) before restarting ODS's LLM.
4. **Whisper cannot check Khmer automatically.** A human listening check is needed, or a Khmer-capable ASR.

## Results, dub retry with `smart_fit` (Operator, 2026-11-08)

The user approved a second window with ODS's LLM stopped. The same dub job, segments, translations and `auto:speaker_1` clone reference were reused, with `timing_strategy: "smart_fit"`.

| Dub | Result | Details |
|---|---|---|
| Spanish | **PASS** | `done` in 202 s. Segment fits: `audio_stretched` ×1.07 and `hybrid` ×1.195. MP3 287 KB. |
| Khmer | **PASS** | `done` in 49 s, with VoxCPM2 already warm. Segment fits: `hybrid` ×1.188 and ×1.176. MP3 downloaded. |
| Both tracks, M4A with the Demucs background | **PASS** | 292 KB. |

- **GPU memory:** the peak was 10.9 GB used during the retry.
- **Restart order:** Voice Studio was stopped first, then ODS's LLM was started. It was healthy in 39 s with 0 restarts (against 130 s+ and a stall in the first run), confirming finding 3.

**Verdict:** dubbing works end to end over HTTP in the commercial-only profile: an audio-only upload, Demucs, ODS Whisper, ODS LLM translation, a VoxCPM2 clone of the source speaker, then export. It needs `smart_fit`, because the default `concise` fails on longer translations.

**Follow-ups (not fixed here):**
- Make `smart_fit` the SideStack default dub timing, or have `concise` fail before generating every segment.
- Raise `OMNIVOICE_TRANSCRIBE_CHUNK_TIMEOUT_S` in the SideStack profile so a cold ODS Whisper reload fits.
- Runbook: stop Voice Studio before restarting ODS's LLM after VoxCPM2 use.

## Listening verdict (user, 2026-11-08)

"Khmer sounds good." This covers `khmer_voxcpm2.wav` (direct Khmer speech) and `dub_km.mp3` (the English → Khmer dub). Khmer is usable in the commercial-only profile with VoxCPM2.
