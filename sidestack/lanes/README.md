# Lane tracker

Update this table when a lane changes status. Statuses: `planned` → `ready` (spec written) →
`running` → `verified` (reviewer re-ran acceptance) → `committed`.

| Lane | Title | Run by | Gate | Status | Commit |
|---|---|---|---|---|---|
| VS-F0 | Foundation: `sidestack/` folder, AGENTS pointer, validator | Reviewer | Commit OK | committed | first commit on `sidestack/foundation-001` |
| [VS-00](VS-00-harness-preflight.md) | Harness workspace + sandbox probe | Operator | — | ready | — |
| [VS-01](VS-01-windows-toolchain.md) | Install `uv` + `bun`; sync deps in the worktree | Operator | Install approval | ready | — |
| [VS-02](VS-02-baseline-and-web-mode.md) | Offline test baseline + headless web mode on :3900 | dsh | — | ready | — |
| [VS-03](VS-03-ods-env-profile.md) | Verify the ODS env profile against live ODS | dsh + Operator | ODS probe approval | ready | — |
| [VS-04](VS-04-ods-llm-provider.md) | First-class `ods` LLM provider + tests | dsh | — | ready | — |
| VS-05 | ODS Whisper as ASR + one synthetic transcription | dsh + Operator | Real run approval | planned | — |
| VS-06 | ODS admission gate (relay `/v1/models` + free VRAM) | dsh | — | planned | — |
| VS-07 | `Start-VoiceStudio-ODS.ps1` launcher | dsh | — | planned | — |
| VS-08 | ODS Applications entry | Operator | ODS change approval | planned | — |
| VS-09 | End-to-end synthetic acceptance | Operator | Real run approval | planned | — |
| VS-10 | Meetings "read summary aloud" via `/v1/audio/speech` | dsh | Design OK | planned | — |
| VS-11 | In-app branding (21 locales) | dsh | Decision D4 | planned | — |
| VS-12 | Upstream sync runbook + first merge | Operator | — | planned | — |
| VS-13 | Optional ODS Docker extension + private-network HTTP allowlist | dsh | Decision D1 | planned | — |

Order: VS-00 → VS-01 → VS-02 → (VS-03, VS-04 in either order) → VS-05 → VS-06 → VS-07 → VS-08 → VS-09.
Phase 4 lanes are independent of each other.
