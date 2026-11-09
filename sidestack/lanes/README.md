# Lane tracker

Update this table when a lane changes status. Statuses: `planned` → `ready` (spec written) →
`running` → `verified` (reviewer re-ran acceptance) → `committed`.

| Lane | Title | Run by | Gate | Status | Commit |
|---|---|---|---|---|---|
| VS-F0 | Foundation: `sidestack/` folder, AGENTS pointer, validator | Reviewer | Commit OK | committed | first commit on `sidestack/foundation-001` |
| [VS-00](VS-00-harness-preflight.md) | Harness workspace + sandbox probe | Operator | — | verified | — |
| [VS-01](VS-01-windows-toolchain.md) | Install `uv` + `bun`; sync deps in the worktree | Operator | Install approval | verified | — |
| [VS-02](VS-02-baseline-and-web-mode.md) | Offline test baseline + headless web mode on :3900 | dsh | — | verified | — |
| [VS-03](VS-03-ods-env-profile.md) | Verify the ODS env profile against live ODS | Operator | ODS probe approval | verified | — |
| [VS-04](VS-04-ods-llm-provider.md) | First-class `ods` LLM provider + tests | dsh | — | verified | — |
| [VS-05](VS-05-ods-whisper-asr.md) | ODS Whisper as ASR + one synthetic transcription | dsh + Operator | Real run approval | verified | — |
| [VS-06](VS-06-vram-admission-gate.md) | GPU admission gate for TTS loads beside ODS | dsh | — | verified | — |
| [VS-07](VS-07-launcher.md) | `Start-VoiceStudio-ODS.ps1` launcher + local-only profile fixes | dsh + Reviewer | Live run approval (reviewer's real start) | verified | — |
| [VS-08](VS-08-ods-applications-entry.md) | ODS Applications entry | Operator | ODS change approval | verified | — |
| [VS-09](VS-09-e2e-acceptance.md) | Gate fixes + end-to-end synthetic acceptance (KittenTTS → ODS Whisper → ODS translation) | dsh + Operator | Real run approval (Part B) | verified | — |
| [VS-10](VS-10-meetings-read-aloud.md) | Meetings "read summary aloud" via `/v1/audio/speech` (would be built in the Meetings repo) | — | — | parked (reference design) | — |
| VS-11 | In-app branding (21 locales) | dsh | Decision D4 | dropped (D4, 2026-11-08) | — |
| [VS-12](VS-12-upstream-sync.md) | Upstream sync runbook + first merge | Operator | — | verified | — |
| VS-13 | Optional ODS Docker extension + private-network HTTP allowlist | dsh | Decision D1 | dropped (D1, 2026-11-08) | — |
| [VS-14](VS-14-dictation-ods-whisper.md) | Dictation (capture ASR) through ODS Whisper instead of a local Whisper | dsh + Operator | Design OK (given), then real run approval (Part B) | verified | — |
| [VS-15](VS-15-voice-studio-first-vram.md) | "Voice Studio first" GPU policy (VS-06 open issue, decision D3) | dsh | — (decided 2026-11-06) | verified | — |
| [VS-16](VS-16-voxcpm2-cloning.md) | Voice design + cloning with VoxCPM2 (Apache-2.0), measured beside ODS | Operator | Install approval (Part A, given), real run approval (Part B) | verified | — |
| [VS-17](VS-17-voxcpm2-vram-floor.md) | Measured VRAM floor for VoxCPM2 in the admission gate (7 GB) | dsh + Operator | Real run approval (Part B live refusal) | verified (Part B PASS after VS-20) | — |
| [VS-18](VS-18-commercial-only-mode.md) | Commercial-only mode (default on) + `-AllowNonCommercial` for private non-commercial engines (decision D2) | dsh + Operator | Real run approval (Part B); Part C needs the user's licence acceptance | verified (Part C optional) | — |
| [VS-19](VS-19-commercial-default-engine.md) | Commercial-licence default TTS engine (VoxCPM2) from the SideStack profile | dsh + Operator | Real run approval (Part B, with VS-17 Part B) | verified | — |
| [VS-20](VS-20-gate-driver-vram.md) | Admission gate reads free VRAM from the driver (NVML) too, so it sees ODS in WSL (VS-17 Part B fix) | dsh + Operator | Real run approval (Part B, closes VS-17 Part B) | verified | — |
| [VS-21](VS-21-download-commercial-only.md) | Commercial-only mode refuses downloads too (model installs, sidecar installs, OmniVoice GGUF) | dsh + Operator | Real run approval (Part B live refusal, no downloads) | verified | — |
| [VS-22](VS-22-model-library-commercial-only.md) | Commercial-only mode in the Model Library: no Download/Select/setup for refused models and engines, refused engines folded, `/engines/select` refuses them | dsh + Operator | Real run approval (Part B: rebuild web UI, live look, no downloads) | verified | — |
| [VS-23](VS-23-first-run-default-engine.md) | First-run setup requires the profile's default engine (VoxCPM2 weights + engine) instead of OmniVoice | dsh + Operator | Real run approval (Part B: live read of setup status) | verified | — |
| [VS-24](VS-24-first-run-screen.md) | First-run screen: packs lead with the required TTS model and skip refused models; install button for the default engine | dsh + Operator | Real run approval (Part B: rebuild web UI, live look) | verified | — |
| [VS-25](VS-25-recommendations-commercial-only.md) | Commercial-only mode leaves refused picks out of `/setup/recommendations` | dsh + Operator | Real run approval (Part B: one live read) | verified | — |
| [VS-26](VS-26-engine-setup-sidestack.md) | "Set up" reinstalls a one-click engine (VoxCPM2) and never falls back to a refused engine | dsh + Operator | — (Part B optional) | verified (Part B PASS 2026-11-08) | — |

Order: VS-00 → VS-01 → VS-02 → (VS-03, VS-04 in either order) → VS-05 → VS-06 → VS-07 → VS-08 → VS-09.
Phase 4 lanes are independent of each other.

## Goal: 100% (set 2026-11-08)

"100%" means every item below is done. **Reached 2026-11-08.** Decisions from 2026-11-08: VS-11 and VS-13 are dropped. VS-18 Part C and VS-26 Part B stay optional. VS-10 stays parked (Meetings work).

| # | Item | Done when |
|---|---|---|
| G1 | VS-17 – VS-26 verified and committed | done |
| G2 | Commercial-only mode on the remaining engine choices outside Settings | **done, audit only (2026-11-08):** nothing left to change. The Dub page's only engine switch picks a commercial Faster-Whisper model. Every "Set up" goes through the engine notice (VS-26). The dictation, translation and diarisation lists draw their Download/Select through `ModelActions` (VS-22). Translation engine installs are pip packages, not models (VS-21, out of scope). |
| G3 | Recommendations rationale text in the SideStack profile | **done, audit only (2026-11-08):** no change needed. The desktop and web UI never display `rationale`: only `shared/api/setup.ts` types it, and `SystemRecommendations` is exported but not rendered. Only the mobile app reads it, and SideStack does not use the mobile app. |
| G4 | Final regression: full backend and frontend suites on the final tree, no new failing ids against the baseline | **done (2026-11-08, tree at VS-26):** backend `-n 8`: 13,061 passed, 93 failed, 20 errors, with every failing id in the baseline and none new. Frontend `bun run test`: 396 files / 2,852 passed (12 skipped) and 339 files / 3,091 passed, 0 failed. |
| G5 | Clean history: squash the local commits into reviewed commits with no private data, then force-push `sidestack/foundation-001` | **done (2026-11-08, approved by the user):** one commit on upstream 6bb3fbc5e. It has the same tree as the tested branch and no Windows username, and it replaced 13936657d with a force-push with lease. The step-by-step history is kept in a local-only backup branch. |

Recurring, not part of 100%: monthly upstream sync (D5, next about 2026-12-06).
