# SideStack Voice Studio

This folder holds everything SideStack adds to this VoiceStudio fork. The goal is
**SideStack Voice Studio**: VoiceStudio (voice cloning, TTS, dubbing, transcription,
audiobooks) running on the SideStack workstation, using ODS for its language model and
speech recognition, listed in ODS → Applications, and built lane by lane with the
**DeepSeek Harness** (`dsh`) on the ODS model.

Upstream code stays where it is. SideStack changes live here, plus small, named edits to
upstream files that are listed in [PLAN.md](PLAN.md). Keeping them in one place makes
upstream merges easy.

## Start here

| File | Read it when |
|---|---|
| [PLAN.md](PLAN.md) | You want the goal, the decisions still open, the phases and lanes, and the approval gates. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | You need ports, data paths, the GPU budget or the security boundary. |
| [AGENTS-SIDESTACK.md](AGENTS-SIDESTACK.md) | You are an agent (DeepSeek Harness, OpenCode, Claude, Codex) working on this fork. **Required reading.** |
| [harness/README.md](harness/README.md) | You are running a lane with the DeepSeek Harness. |
| [lanes/README.md](lanes/README.md) | You want the lane tracker or the next lane spec. |
| [ods/APPLY.md](ods/APPLY.md) | You are adding Voice Studio to ODS → Applications (needs approval). |
| [config/ods.env.example](config/ods.env.example) | You are wiring Voice Studio to ODS's LLM and Whisper. |

## Layout

```
sidestack/
├── README.md               this file
├── PLAN.md                 master plan: decisions, phases, lanes, gates
├── ARCHITECTURE.md         topology, ports, GPU budget, data, security
├── AGENTS-SIDESTACK.md     binding rules for agents on this fork
├── .gitignore              keeps work/ (staged specs, run logs) out of git
├── config/
│   └── ods.env.example     env profile: ODS relay (LLM) + ODS Whisper (ASR)
├── harness/
│   ├── README.md           DeepSeek Harness setup and the lane loop
│   ├── KICKOFF-PROMPT.md   the prompt pasted into dsh for each lane
│   └── LANE-TEMPLATE.md    template for new lane specs
├── lanes/
│   ├── README.md           lane tracker (status, owner, gate)
│   └── VS-xx-*.md          one spec per lane
├── ods/
│   ├── manifest.yaml       draft ODS Applications entry (windows-host)
│   └── APPLY.md            approved steps + rollback for the ODS entry
├── scripts/
│   ├── Test-VoiceStudioOds.ps1   read-only preflight (relay, Whisper, GPU, ports)
│   └── check_sidestack.py        validates this folder (lanes, manifest, no secrets)
└── work/                   (gitignored) staged specs and harness run logs
```

## Status

Phase 0 (foundation) is this folder. Nothing is wired to ODS yet. See the tracker in
[lanes/README.md](lanes/README.md).

## Licence

This fork is AGPL-3.0-only, like upstream. See [`../LICENSE`](../LICENSE) and
[`../LICENSE-NOTICE.md`](../LICENSE-NOTICE.md). The repository is public. Every SideStack
change is therefore published source, so **never commit keys, tokens, private hostnames or
private recordings**. Model weights carry their own licences. The default OmniVoice
weights are CC-BY-NC, so check [PLAN.md](PLAN.md) decision D2 before any commercial use.
