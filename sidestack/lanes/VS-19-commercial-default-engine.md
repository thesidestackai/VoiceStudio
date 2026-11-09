# VS-19 — A commercial-licence default TTS engine

- **Phase:** 4
- **Run by:** dsh does Part A (code and offline tests). The Operator does Part B (live check).
- **Gate:**
  - none for Part A;
  - **real run approval** for Part B: start Voice Studio once, with no downloads, and check the web UI. This can also run VS-17 Part B.
- **Depends on:** VS-16, VS-17, VS-18
- **Status:** ready

## Goal

A fresh Voice Studio starts on a commercial-licence engine, so the app's first screen does not point at an engine that commercial-only mode refuses.

**Why (VS-18 Part B):**
- Upstream's default TTS engine is OmniVoice (CC-BY-NC).
- Until an engine is picked in Settings, the Design page says "Text-to-speech is not ready", and its **Set up** button downloads OmniVoice.
- Commercial-only mode refuses OmniVoice when you generate. Downloads are not licence-gated.

**How upstream picks the engine:** `active_backend_id()` in `backend/services/tts_backend.py` takes, in order:
1. `OMNIVOICE_TTS_BACKEND` (it pins the engine, and the Settings picker can no longer change it);
2. the choice saved in Settings (`prefs.json` `tts_backend`);
3. the default `"omnivoice"`.

The web UI's readiness check reads the same value through `/engines`.

**Fix:** one marked hook makes the default (step 3 only) come from `SIDESTACK_DEFAULT_TTS_BACKEND`, set to `voxcpm2` in the SideStack profile. The Settings picker still works, and `OMNIVOICE_TTS_BACKEND` still pins. Unset, upstream behaviour is unchanged.

**Why VoxCPM2:**
- It is Apache-2.0, does voice design and cloning, and is installed and verified (VS-16).
- While ODS's LLM is loaded, the gate refuses it with the VS-17 message, which tells the user to unload the LLM or choose a CPU engine.
- KittenTTS (Apache-2.0, CPU, no design or cloning) is the alternative: change one profile line.

**Also fixed (VS-18 finding):** a refusal that lists two models says "are", not "is".

## Files

| Path | Change |
|---|---|
| `backend/sidestack_fork/defaults.py` | create |
| `backend/services/tts_backend.py` | edit: one hook marked `SideStack fork (VS-19)` in `active_backend_id` |
| `backend/sidestack_fork/licensing.py` | edit: "is"/"are" |
| `sidestack/config/ods.env.example` | edit: the default engine |
| `tests/test_sidestack_defaults.py` | create: D1–D6 |
| `tests/test_sidestack_licensing.py` | edit: add C8 |
| `sidestack/lanes/VS-19-commercial-default-engine.md`, `sidestack/lanes/README.md` | builder report / status |

## Preflight

Start with the environment block from AGENTS-SIDESTACK.md Hard law 9, run from the worktree root.

```powershell
git status --short     # expect: empty
Select-String backend\services\tts_backend.py -Pattern '^    return prefs\.resolve\("tts_backend", env="OMNIVOICE_TTS_BACKEND", default="omnivoice"\)$'   # expect: 1 match
Select-String backend\sidestack_fork\licensing.py -Pattern '^            f"Commercial-only mode is on: \{names\} is not licensed for commercial use\. "$'   # expect: 1 match
Select-String sidestack\config\ods.env.example -Pattern '^SIDESTACK_COMMERCIAL_ONLY=1$'   # expect: 1 match
& $py -m pytest tests/test_sidestack_licensing.py -q -p no:cacheprovider   # expect: 7 passed
```

## Steps

1. Create `backend/sidestack_fork/defaults.py`:
   ```python
   """SideStack fork (VS-19): the default TTS engine comes from the SideStack profile.

   SIDESTACK_DEFAULT_TTS_BACKEND names the engine used while neither
   OMNIVOICE_TTS_BACKEND nor a choice saved in Settings names one. Unlike
   OMNIVOICE_TTS_BACKEND it does not pin the engine, so the Settings picker
   still works. Unset or blank, upstream's default is unchanged.
   """
   from __future__ import annotations

   import os

   ENV_FLAG = "SIDESTACK_DEFAULT_TTS_BACKEND"


   def default_tts_backend(upstream_default: str) -> str:
       """The profile's default engine id, or upstream's when none is set."""
       return os.environ.get(ENV_FLAG, "").strip() or upstream_default
   ```
2. In `backend/services/tts_backend.py`, in `active_backend_id`, replace this line:
   ```python
       return prefs.resolve("tts_backend", env="OMNIVOICE_TTS_BACKEND", default="omnivoice")
   ```
   with:
   ```python
       # SideStack fork (VS-19): the SideStack profile names the default engine.
       from sidestack_fork.defaults import default_tts_backend
       return prefs.resolve("tts_backend", env="OMNIVOICE_TTS_BACKEND",
                            default=default_tts_backend("omnivoice"))
   ```
   Change nothing else in that file.
3. In `backend/sidestack_fork/licensing.py`, replace these two lines:
   ```python
           self.args = (
               f"Commercial-only mode is on: {names} is not licensed for commercial use. "
   ```
   with:
   ```python
           verb = "is" if len(models) == 1 else "are"
           self.args = (
               f"Commercial-only mode is on: {names} {verb} not licensed for commercial use. "
   ```
4. In `sidestack/config/ods.env.example`, directly after the line `SIDESTACK_COMMERCIAL_ONLY=1`, add:
   ```
   # VS-19: the TTS engine used until one is picked in Settings. VoxCPM2 has a commercial
   # licence and does cloning and voice design. Unlike OMNIVOICE_TTS_BACKEND it does not pin.
   SIDESTACK_DEFAULT_TTS_BACKEND=voxcpm2
   ```
5. Create `tests/test_sidestack_defaults.py`:
   ```python
   """SideStack VS-19 — the default TTS engine comes from the SideStack profile.

   prefs.json is replaced by an in-memory store; engine env vars are cleared.
   """
   from __future__ import annotations

   import importlib
   import os
   import sys

   import pytest

   sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

   os.environ.setdefault("OMNIVOICE_MODEL", "test")
   os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

   ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


   @pytest.fixture
   def tts(monkeypatch):
       """(services.tts_backend, the in-memory prefs store)."""
       prefs = importlib.import_module("core.prefs")
       store: dict = {}
       monkeypatch.setattr(prefs, "get", lambda key, default=None: store.get(key, default))
       monkeypatch.delenv("OMNIVOICE_TTS_BACKEND", raising=False)
       monkeypatch.delenv("SIDESTACK_DEFAULT_TTS_BACKEND", raising=False)
       return importlib.import_module("services.tts_backend"), store


   def test_d1_unset_keeps_upstream_default(tts):
       mod, _ = tts
       assert mod.active_backend_id() == "omnivoice"


   def test_d2_profile_default(tts, monkeypatch):
       mod, _ = tts
       monkeypatch.setenv("SIDESTACK_DEFAULT_TTS_BACKEND", "voxcpm2")
       assert mod.active_backend_id() == "voxcpm2"


   def test_d3_settings_choice_wins(tts, monkeypatch):
       mod, store = tts
       monkeypatch.setenv("SIDESTACK_DEFAULT_TTS_BACKEND", "voxcpm2")
       store["tts_backend"] = "kittentts"
       assert mod.active_backend_id() == "kittentts"


   def test_d4_env_pin_wins(tts, monkeypatch):
       mod, store = tts
       monkeypatch.setenv("SIDESTACK_DEFAULT_TTS_BACKEND", "voxcpm2")
       store["tts_backend"] = "kittentts"
       monkeypatch.setenv("OMNIVOICE_TTS_BACKEND", "cosyvoice")
       assert mod.active_backend_id() == "cosyvoice"


   def test_d5_blank_falls_back(tts, monkeypatch):
       mod, _ = tts
       monkeypatch.setenv("SIDESTACK_DEFAULT_TTS_BACKEND", "  ")
       assert mod.active_backend_id() == "omnivoice"


   def test_d6_profile_and_hook(tts):
       mod, _ = tts
       with open(os.path.join(ROOT, "sidestack", "config", "ods.env.example"), encoding="utf-8") as f:
           assert "SIDESTACK_DEFAULT_TTS_BACKEND=voxcpm2" in f.read().splitlines()
       assert "voxcpm2" in mod._REGISTRY
       with open(os.path.join(ROOT, "backend", "services", "tts_backend.py"), encoding="utf-8") as f:
           assert f.read().count("SideStack fork (VS-19)") == 1
   ```
6. In `tests/test_sidestack_licensing.py`, add at the end of the file:
   ```python


   def test_c8_message_grammar(lic):
       one = lic.CommercialOnlyRefused([{"repo_id": "a/one", "license": None, "category": "noncommercial"}])
       two = lic.CommercialOnlyRefused([
           {"repo_id": "a/one", "license": None, "category": "noncommercial"},
           {"repo_id": "b/two", "license": None, "category": "unknown"},
       ])
       assert "a/one (noncommercial) is not licensed" in str(one)
       assert "b/two (unknown) are not licensed" in str(two)
   ```
   Keep one newline at the end of the file.
7. Run Acceptance and report in the AGENTS-SIDESTACK §4 format, listing every command. Append the report at the very end of this spec under a `## Builder report` heading, and set this lane's tracker status to `running (dsh done)`.

## Acceptance

```powershell
& $py -m pytest tests/test_sidestack_defaults.py tests/test_sidestack_licensing.py -q -p no:cacheprovider   # expect: 14 passed
& $py -m pytest tests/test_sidestack_launcher.py tests/test_sidestack_admission.py tests/test_sidestack_dictation.py tests/test_structure_doc.py -q -p no:cacheprovider   # expect: 0 failed
& $py -m pytest tests -q -p no:cacheprovider -k "tts_backend or engine_select or active_backend" --continue-on-collection-errors -rfE   # expect: only baseline failures and the baseline collection error in test_ci_change_detection.py (record the count)
git status --short    # expect: exactly the files in "Files"
Get-ChildItem -Force | Where-Object Name -match '^(pytest-of-|omnivoice-test-data-)'   # expect: nothing
python sidestack/scripts/check_sidestack.py           # expect: OK
```

## Part B — live check (Operator, after approval)

No downloads. ODS's LLM stays loaded. Nothing is saved in Settings (`prefs.json` has no `tts_backend`), so the profile default applies.
1. Start with the launcher. Its dry-run plan shows `SIDESTACK_DEFAULT_TTS_BACKEND=voxcpm2`.
2. `GET /engines` → `tts.active == "voxcpm2"`.
3. Open the web UI → Design. Expect no "Text-to-speech is not ready" and no **Set up** button. Record what it shows.
4. **VS-17 Part B (same run):**
   - record `nvidia-smi` memory.used;
   - `POST /generate` with `engine=voxcpm2` and short synthetic text → **503** "Not enough free GPU memory: need 8.0 GB, have X GB (TTS engine 'voxcpm2') …";
   - no VoxCPM2 sidecar process starts, and memory.used does not grow beyond Voice Studio's own CUDA context.
   - Also try once from the Design page, and record the message the UI shows.
   - If anything starts loading, stop at once (`-Stop`) and report: the gate missed the path.
5. `-Stop`. Check that the HF cache's model folders are unchanged, and record the results here and in VS-17.

## Out of scope

- Licence-gating model downloads (upstream does not gate them; a separate lane if wanted).
- Hiding non-commercial engines in the picker, or changing the first-run wizard's model packs.
- The AMD/Intel "use your GPU?" offer (`omnivoice_gguf/gpu_offer.py`), which never shows on this NVIDIA host.

## Reviewer notes

- **Mutation checks:**
  - revert Step 2's `return` (`default="omnivoice"`) → D2 fails (D6 fails only if the marker comment goes too: it counts the marker);
  - `.strip()` removed in `default_tts_backend` → D5 fails;
  - `verb` fixed to `"is"` → C8 fails.
- D3 and D4 pass with or without the hook. They pin the precedence (a Settings choice and `OMNIVOICE_TTS_BACKEND` still win), so the hook cannot become a pin.
- An unknown id in the profile fails the same way as an unknown `OMNIVOICE_TTS_BACKEND` (upstream's "Unknown TTS backend" error). No silent fallback.
- `performance_inventory.py` and `performance_profiles.py` read `active_backend_id()` too. A performance profile the user applies writes `tts_backend` to prefs, which then wins over the default, as any Settings choice does.
- **Checked while writing this lane (2026-11-08):**
  - `prefs.json` holds no `tts_backend`;
  - `get_backend_class("voxcpm2")` resolves to the VS-16 sidecar;
  - the UI's readiness check (`use-tts-readiness.ts`) uses `/engines` `tts.active`.

## Builder report

```
LANE: VS-19
STATUS: DONE (Part A; Part B awaits operator real-run approval)
FILES CHANGED: backend\sidestack_fork\defaults.py (9436aba94a6c), backend\services\tts_backend.py (b2b245a3eea9), backend\sidestack_fork\licensing.py (93540af9d2e2), sidestack\config\ods.env.example (bd03ad60e777), tests\test_sidestack_defaults.py (91f899f9c1f9), tests\test_sidestack_licensing.py (cfcd9b5187d3), sidestack\lanes\VS-19-commercial-default-engine.md (this report), sidestack\lanes\README.md (status)
COMMANDS RUN:
- Preflight (Hard law 9 block from worktree root): git status --short → 0 (empty); 3× Select-String → 1 match each; & $py -m pytest tests/test_sidestack_licensing.py -q -p no:cacheprovider → 0 (7 passed)
- Acceptance 1: & $py -m pytest tests/test_sidestack_defaults.py tests/test_sidestack_licensing.py -q -p no:cacheprovider → 0 (14 passed: D1-D6, C1-C8)
- Acceptance 2: & $py -m pytest tests/test_sidestack_launcher.py tests/test_sidestack_admission.py tests/test_sidestack_dictation.py tests/test_structure_doc.py -q -p no:cacheprovider → 0 (42 passed)
- Acceptance 3: & $py -m pytest tests -q -p no:cacheprovider -k "tts_backend or engine_select or active_backend" --continue-on-collection-errors -rfE → 1 (107 passed, 1 failed, 1 skipped, 1 error)
- git status --short → 0 (only Files-list changes); temp-residue check → 0 (none)
- python sidestack/scripts/check_sidestack.py → 0 (OK: 14 required files, 18 lane specs, links, manifest, env profile, secret scan)
NOT DONE / UNSURE:
- Part B (operator): real-run approval, no downloads, web UI check (also runs VS-17 Part B).
- Acceptance 3's single failure tests/backend/services/test_indextts_sidecar.py::test_no_indextts_import_in_tts_backend is a pre-existing Windows cp1252-locale read of tts_backend.py (non-UTF-8 bytes already in the baseline file), not caused by the VS-19 edit: it passes with PYTHONUTF8=1 (re-run → 1 passed); the collection error in test_ci_change_detection.py (missing grep on PATH) is likewise environmental.
```

## Reviewer verification (Part A, 2026-11-08)

- **Builder run:** the builder finished in under 15 minutes. Every edit matches the spec text; `tests/test_sidestack_defaults.py` matches the spec block exactly.
- **Acceptance re-run (Hard law 9 environment):**
  - defaults and licensing tests: 14 passed;
  - launcher, admission, dictation and structure doc: 42 passed.
  - The builder's one failure under `-k`, `test_indextts_sidecar.py::test_no_indextts_import_in_tts_backend`, is in the VS-02 baseline and also fails on HEAD. It is a cp1252 read of `tts_backend.py`.
- **Mutation checks:**
  - revert Step 2's `return` → D2 fails;
  - drop `.strip()` → D5 fails;
  - fix `verb` to `"is"` → C8 fails.
  - All files were restored afterwards.
  - The spec note said D6 would also fail on the first mutation. It does not, because the marker comment stays, so the note is corrected above.
- **Full suite** (`-n 8`, 15 min 3 s): 93 failed, 13,026 passed, 138 skipped and 20 errors.
  - 5 baseline failures now pass.
  - One failure is outside the baseline: `test_job_store.py::test_concurrent_same_job_events_have_unique_monotonic_sequences`, with `sqlite3.OperationalError: database is locked` under 8 workers. Run alone it passed 5 of 5, and the file does not reference any VS-19 code. Recorded as a load flake, not a VS-19 regression.
- **Next:** Part B, the live check, needs real run approval. It also runs VS-17 Part B.

## Part B results (Operator, 2026-11-08)

The user gave real run approval. Later the same day they also asked for ODS's LLM to be unloaded. The prefs file has no `tts_backend`, so the profile default applies.

1. The dry-run plan shows `SIDESTACK_DEFAULT_TTS_BACKEND=voxcpm2` and `licence_mode: commercial-only`.
2. `GET /engines` → `tts.active == "voxcpm2"`, available. Startup added only Voice Studio's own CUDA context (+0.4 GB); nothing was preloaded. Upstream's startup preload is for OmniVoice only and skips itself when another engine is selected.
3. **Design page:**
   - **Synthesize audio** is shown, with no "Text-to-speech is not ready" and no **Set up**. PASS.
   - The analytics consent prompt was answered "No thanks", so `analytics_enabled` is false.
4. **VS-17 Part B (ODS's LLM loaded): FAIL.**
   - Before: 25.5 GB used, 6.7 GB free.
   - `POST /generate`, `engine=voxcpm2` → **admitted**. The sidecar spawned and started loading weights, so the run was stopped at once (`-Stop`). The sidecar exited, ODS stayed healthy, and GPU memory went back to 25.0 GB.
   - **Root cause:** the gate takes free VRAM from `torch.cuda.mem_get_info()`. That call does not see GPU memory used inside WSL, where ODS runs. Same moment, same GPU:

     | Source | Free |
     |---|---|
     | `torch.cuda.mem_get_info()` | 27.74 GB |
     | NVML | 7.00 GB |
     | `nvidia-smi` | 7.0 GB |

     Upstream's "GPU pool sized … 27.8 GB free" log line has the same blind spot.
   - The UI attempt was not made, because the API path already failed.
   - A fix needs its own lane: read free VRAM from NVML, or take the lower of NVML and torch.
5. **Default engine with ODS's LLM unloaded** (`docker stop ods-llama-server`, as the user asked; GPU then 3.1 GB used, 29.1 GB free):
   - `POST /generate` with `text` and `instruct` only, no `engine` → **200**: 5.46 s at 48 kHz (VoxCPM2) in 63.5 s cold (sidecar load included), then 3.54 s of audio in 12.1 s warm. The sidecar added about 6.6 GB of GPU memory.
   - The ODS Whisper transcript matches the script word for word.
   - **Design page:** a synthetic description and script → **Synthesize audio** → a 4.3 s take at 48 kHz, "rendered in 18.0 s". PASS.
6. `-Stop`. The HF cache model folders are unchanged (KittenTTS and VoxCPM2 only), and no engine was saved to prefs. `ods-llama-server` was left stopped, pending the user's decision.

**Verdict:** VS-19 PASS (the default engine works and the UI is ready). VS-17's live refusal fails because of the VRAM source; see VS-17.