# VS-03 — Verify the ODS env profile against live ODS

- **Phase:** 2
- **Run by:** Operator runs the probes; dsh updates the files from the recorded results
- **Gate:** **ODS probe approval.** These are read-only GETs plus **one** tiny chat completion through the relay. No ODS changes.
- **Depends on:** VS-02
- **Status:** verified

## Goal

`sidestack/config/ods.env.example` is confirmed against the running ODS: the relay model id, that
the relay accepts the key over loopback, and that Voice Studio's `custom` provider reaches it
and gets one short answer.

## Files

| Path | Change |
|---|---|
| `sidestack/config/ods.env.example` | edit: replace the `VERIFY [VS-03]` comment with `Verified <date>: <evidence>`; change `TRANSLATE_MODEL` only if `/v1/models` disagrees |
| `sidestack/work/VS-03/probe.md` | create (gitignored): probe outputs **with the key removed** |

## Preflight

```powershell
powershell -ExecutionPolicy Bypass -File sidestack\scripts\Test-VoiceStudioOds.ps1   # expect: relay OK, whisper OK
```

The ODS LLM stack must be up and Ollama must have no model loaded. The script reports both. If
either is wrong, stop: the user switches runtimes, never the agent.

## Steps

1. Model list (the key comes from the user env and is never echoed):
   ```powershell
   $k = [Environment]::GetEnvironmentVariable("ODS_LOCAL_MODEL_RELAY_KEY","User")
   (Invoke-RestMethod http://127.0.0.1:4007/v1/models -Headers @{Authorization="Bearer $k"}).data.id
   ```
   Record the ids. The expected list includes `ods/current` and `default`.
2. Through Voice Studio itself (backend not running, provider code only):
   ```powershell
   $env:LLM_DEFAULT_PROVIDER="custom"; $env:TRANSLATE_BASE_URL="http://127.0.0.1:4007/v1"
   $env:TRANSLATE_MODEL="ods/current"; $env:TRANSLATE_API_KEY=$k
   & $py -c "import sys; sys.path.insert(0,'backend'); from services import llm_providers as lp; p=lp.active_provider(); print(p.id, lp.configuration_error(p))"
   ```
   Expected: `custom None`. A transport error here means the loopback rule rejected the URL.
3. One short completion through the provider path Voice Studio uses for translation. The
   builder finds the smallest public function in `backend/services/llm_backend.py` that sends one
   chat request, and the operator runs it once with the prompt `Reply with the word OK.`
   Record the latency and the reply.
4. Remove `$env:TRANSLATE_API_KEY` from the session afterwards.

## Acceptance

```powershell
Select-String sidestack\config\ods.env.example -Pattern "VERIFY \[VS-03\]"   # expect: no match
Select-String sidestack\config\ods.env.example -Pattern "Verified "          # expect: one match
python sidestack/scripts/check_sidestack.py                                   # expect: OK (secret scan clean)
```

## Out of scope

- Changing ODS context size, models or services.
- Storing the key anywhere, including Voice Studio's settings DB.

## Reviewer notes

**PASS, 2026-11-06 (the ODS probe was approved by the user).**

- **Run entirely by the operator.** The builder's parts (finding one function and editing one comment line) were too small for a harness turn. The user had also just switched the harness to full access, which the harness rules forbid, so it was kept away from a lane that handles the relay key. Afterwards the user chose to keep full access. The harness README rule ("Never grant `danger-full-access`") is unchanged, and the reviewer keeps lanes that touch keys or ODS on the operator side.
- **Preflight:**
  - `Test-VoiceStudioOds.ps1` first threw a StrictMode `.Count` error on Windows PowerShell 5.1, because an empty function return unrolls to `$null`. It was fixed with `@()`.
  - Then all OK: relay 200 with key; models `ods/current` and `default` at ctx 131072; Whisper 200; Ollama none loaded; 7.4 GB VRAM free; port 3900 free.
- **Step 1:** the ids are `ods/current` and `default`. `TRANSLATE_MODEL` is unchanged.
- **Step 2:** `custom None`, resolving to `http://127.0.0.1:4007/v1` and `ods/current`. The loopback rule accepts it.
  - The VS-04 `ods` provider was also checked, configuration only: with the key from `ODS_LOCAL_MODEL_RELAY_KEY` it has a key and no configuration error.
- **Step 3:** the call was `llm_backend.get_active_llm_backend().chat(...)` with backend `openai-compat` and model `ods/current`. It returned `OK` in **4.33 s**. Exactly one completion was made, and the data dir pointed at a scratch folder.
- **Step 4:** both key env vars were removed from the probe session. The key was never printed or written; the probe script refuses to print if its output contains the key.
- **Result:** the evidence is in `sidestack/work/VS-03/probe.md` (gitignored). `ods.env.example` has a `Verified 2026-11-06` line, and `check_sidestack.py` passes.
- **Follow-up for VS-07 (launcher):** prefer `LLM_DEFAULT_PROVIDER=ods`, which needs no `TRANSLATE_API_KEY` copy of the key, over `custom`.
