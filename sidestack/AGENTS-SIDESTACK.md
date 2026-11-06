# Agent rules: SideStack fork

These rules bind every agent working on SideStack lanes in this fork: DeepSeek Harness,
OpenCode, Claude, Codex and others. For SideStack work they **override** the upstream
`AGENTS.md`/`CLAUDE.md` where the two conflict. Every upstream rule not overridden here still
applies.

## 1. Scope

- Do only the lane you were given (`sidestack/lanes/VS-xx-*.md`). Touch only the files that lane
  lists. If you think another file must change, stop and say so.
- Put new SideStack code, scripts and docs under `sidestack/` unless the lane names an upstream file.
- Do not refactor, reformat or "clean up" upstream code.

## 2. Upstream rules: what changes for SideStack

| Upstream rule | For SideStack lanes |
|---|---|
| Issues and PRs on `debpalash/VoiceStudio` | Use the fork `thesidestackai/VoiceStudio`. Never open issues or PRs upstream. |
| `changelog.d/<PR#>.<type>.md` fragment per PR | **Do not add fragments.** They need upstream PR numbers and are style-tested. Record the change in `sidestack/lanes/README.md` instead. |
| Every UI string in all 21 locales | Still applies to any UI string a lane adds (VS-11 especially). |
| Merge protocol (CodeRabbit/Greptile, watch main) | Replaced by the reviewer's on-disk verification (PLAN §6). |
| Attribution: human identity only, no agent trailers | **Applies.** |
| Cross-platform parity | Applies to upstream code changes. Scripts under `sidestack/scripts/` are Windows-only by design. |

## 3. Hard laws (SideStack)

1. **No secrets in files.** Keys come from env vars (`ODS_LOCAL_MODEL_RELAY_KEY`,
   `SIDESTACK_VOICESTUDIO_API_KEY`). Never print, log, echo or commit them. This repo is public.
2. **LLM = ODS only.** Use the relay `http://127.0.0.1:4007/v1`. Do not use cloud providers,
   LiteLLM, or Ollama for Voice Studio features.
3. **ASR = ODS Whisper only** (`http://127.0.0.1:9000/v1`). Never load a local Whisper in Voice Studio.
4. **Never start, stop, load, unload or resize ODS or Ollama models or services.** If the
   runtime is wrong or busy, report it and stop.
5. **No network in tests.** Run with `HF_HUB_OFFLINE=1` and an empty `HF_HUB_CACHE`. Mock HTTP
   to the relay and Whisper.
6. **No model downloads, package installs or real inference runs** unless the lane says the user
   approved them.
7. **Synthetic audio only.** Never use real people's voices or private recordings as fixtures,
   and never read folders outside the worktree looking for audio.
8. **Keep turns short.** The ODS router fails turns over 600 s. Run long commands (installs,
   full test suites) in the background, or leave them to the operator.

## 4. How to finish a lane

End with a report in this exact shape and nothing else:

```
LANE: VS-xx
STATUS: DONE | BLOCKED (<one line why>)
FILES CHANGED: <path> (<sha256 first 12>) ...
COMMANDS RUN: <command> → <exit code>, <tests passed/failed>
NOT DONE / UNSURE: <list or "none">
```

Do not claim a PASS you did not see in command output. The reviewer re-runs everything.
