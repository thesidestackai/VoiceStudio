# VS-18 — Commercial-only mode, with non-commercial engines for private work

- **Phase:** 4
- **Run by:**
  - dsh does Part A (code, launcher switch, offline tests);
  - the Operator does Part B (live check);
  - Part C is the user plus the Operator (OmniVoice for private use; later and optional).
- **Gate:**
  - none for Part A;
  - **real run approval** for Part B: start Voice Studio twice and send a few requests, with no model downloads (KittenTTS is already cached; OmniVoice is refused before anything loads);
  - Part C: the **user** accepts OmniVoice's licence in the app, plus **real run approval** for its weights download and a GPU run with ODS's LLM stopped.
- **Depends on:** VS-07 (launcher), VS-16
- **Status:** ready

## Goal

The user wants both kinds of engine (decision D2, 2026-11-06):
- **commercial-licence engines** (VoxCPM2, CosyVoice 3, MOSS-TTS, KittenTTS) for anything published or monetized, such as YouTube videos;
- **non-commercial engines** (OmniVoice) for private experiments, drafts and listening.

**The risk:** a non-commercial clip ends up in a monetized video.

**The two safeguards:**
1. **The rule:** anything that might be published uses a commercial-licence engine. A reference clip of the user's own voice is theirs, so the same voice can be cloned with VoxCPM2. This is recorded in D2.
2. **The switch:** `SIDESTACK_COMMERCIAL_ONLY=1`, on by default in the SideStack profile. While it is on, Voice Studio refuses every model whose licence category in its model-licence registry is not `commercial`: `noncommercial` (OmniVoice), `conditions`, or `unknown`. An accepted licence does not override it. For private work, the user starts the launcher with `-AllowNonCommercial`.

**How it works:**
- Upstream already routes every model's licence check through `ensure_accepted()` in `backend/services/model_acceptance.py`: TTS, dictation ASR, dubbing and batch.
- One marked hook there calls the fork module. The refusal is a subclass of upstream's `ModelLicenceNotAccepted`, so every route and upstream's global handler answer it the same way (HTTP 403). Its own error code, `commercial_only_mode`, keeps the app from showing the "accept this licence" dialog, which could not help here.

Registry categories come from model cards; they are not legal advice. Engines and their registry categories (checked 2026-11-06):

| Engine | Models | Category |
|---|---|---|
| voxcpm2, kittentts, cosyvoice, moss-tts-v15, pockettts | one model each | commercial |
| omnivoice | `k2-fsa/OmniVoice` + `eustlb/higgs-audio-v2-tokenizer` | noncommercial + unknown |
| indextts2 | `IndexTeam/IndexTTS-2.5` | unknown |
| supertonic3 | `Supertone/supertonic-3` | conditions |
| sherpa-onnx | none in the registry (per-model) | not gated (same as upstream) |

## Files

| Path | Change |
|---|---|
| `backend/sidestack_fork/licensing.py` | create |
| `backend/services/model_acceptance.py` | edit: one hook marked `SideStack fork (VS-18)` in `ensure_accepted` |
| `sidestack/scripts/Start-VoiceStudio-ODS.ps1` | edit: `-AllowNonCommercial` switch, `licence_mode` in the plan |
| `sidestack/config/ods.env.example` | edit: the flag |
| `sidestack/PLAN.md` | edit: the D2 row |
| `tests/test_sidestack_licensing.py` | create: C1–C7 |
| `tests/test_sidestack_launcher.py` | edit: add L14 |
| `sidestack/lanes/VS-18-commercial-only-mode.md`, `sidestack/lanes/README.md` | builder report / status |

## Preflight

Start with the environment block from AGENTS-SIDESTACK.md Hard law 9, run from the worktree root.

```powershell
git status --short     # expect: empty
Select-String backend\services\model_acceptance.py -Pattern '^def ensure_accepted\(repo_ids: Iterable\[str\]\) -> None:$'   # expect: 1 match
Select-String backend\services\model_acceptance.py -Pattern '^    """Raise ``ModelLicenceNotAccepted`` listing every unaccepted gated model."""$'   # expect: 1 match
Select-String sidestack\scripts\Start-VoiceStudio-ODS.ps1 -Pattern '^    \[switch\]\$NoUserEnv,$'   # expect: 1 match
Select-String sidestack\config\ods.env.example -Pattern '^SIDESTACK_VRAM_MARGIN_GB=1\.0$'   # expect: 1 match
& $py -m pytest tests/test_sidestack_launcher.py tests/test_model_acceptance.py -q -p no:cacheprovider   # expect: 0 failed (record the count)
```

## Steps

1. Create `backend/sidestack_fork/licensing.py`:
   ```python
   """SideStack fork (VS-18): commercial-only mode.

   With SIDESTACK_COMMERCIAL_ONLY=1 (the SideStack profile's default), Voice
   Studio refuses every model whose licence category in the model-licence
   registry is not "commercial": non-commercial models such as OmniVoice, and
   models with conditions or an unknown licence. An accepted licence does not
   override it. Start the launcher with -AllowNonCommercial for private work.
   Unset, upstream behaviour is unchanged. Registry categories come from model
   cards; they are not legal advice.
   """
   from __future__ import annotations

   import os
   from typing import Iterable

   from services.model_acceptance import ModelLicenceNotAccepted

   ENV_FLAG = "SIDESTACK_COMMERCIAL_ONLY"
   ERROR_CODE = "commercial_only_mode"
   _ON = {"1", "true", "yes", "on"}


   def enabled() -> bool:
       return os.environ.get(ENV_FLAG, "").strip().lower() in _ON


   class CommercialOnlyRefused(ModelLicenceNotAccepted):
       """A model refused by commercial-only mode (HTTP 403 via the same handler)."""

       def __init__(self, models: list[dict]):
           super().__init__(models, reason="commercial_only")
           names = ", ".join(f"{m['repo_id']} ({m['category']})" for m in models)
           self.args = (
               f"Commercial-only mode is on: {names} is not licensed for commercial use. "
               "Choose a commercial-licence engine such as VoxCPM2, or start Voice Studio "
               "with -AllowNonCommercial for private work.",
           )

       def detail(self) -> dict:
           return {"code": ERROR_CODE, "message": str(self), "models": self.models}


   def ensure_commercial_only(repo_ids: Iterable[str]) -> None:
       """Raise CommercialOnlyRefused when the mode is on and a model is not commercial."""
       if not enabled():
           return
       from services.model_acceptance import status

       refused = []
       for repo_id in dict.fromkeys(r for r in repo_ids if r):
           state = status(repo_id)
           if state.get("category") != "commercial":
               refused.append({
                   "repo_id": repo_id,
                   "license": state.get("license"),
                   "category": state.get("category") or "unknown",
               })
       if refused:
           raise CommercialOnlyRefused(refused)
   ```
2. In `backend/services/model_acceptance.py`, in `ensure_accepted`, directly after its docstring line `    """Raise ``ModelLicenceNotAccepted`` listing every unaccepted gated model."""`, insert:
   ```python
       # SideStack fork (VS-18): commercial-only mode refuses every model whose
       # licence category is not "commercial", even an accepted one.
       repo_ids = list(repo_ids)
       from sidestack_fork.licensing import ensure_commercial_only
       ensure_commercial_only(repo_ids)
   ```
   Change nothing else in that file.
3. In `sidestack/scripts/Start-VoiceStudio-ODS.ps1`:
   - a. In the comment help, directly before the line `.PARAMETER TimeoutSec`, insert:
     ```
     .PARAMETER AllowNonCommercial
       Start with commercial-only mode off (SIDESTACK_COMMERCIAL_ONLY=0) for private work, so
       non-commercial engines such as OmniVoice can be used. Do not publish what they make.

     ```
   - b. In `param(`, directly after the line `    [switch]$NoUserEnv,`, insert the line `    [switch]$AllowNonCommercial,`.
   - c. Directly after the closing `}` of the profile-parsing `for` loop (the line after `    $cfg[$line.Substring(0, $idx)] = $line.Substring($idx + 1)`), insert:
     ```powershell

     # -AllowNonCommercial (VS-18): this run only, commercial-only mode off.
     if ($AllowNonCommercial) { $cfg['SIDESTACK_COMMERCIAL_ONLY'] = '0' }
     ```
   - d. In the `$plan = [ordered]@{` block, directly after the line `    relay_key     = $relayKeyState`, insert:
     ```powershell
         licence_mode  = $(if (@('1', 'true', 'yes', 'on') -contains ([string]$cfg['SIDESTACK_COMMERCIAL_ONLY']).ToLowerInvariant()) { 'commercial-only' } else { 'non-commercial allowed' })
     ```
4. In `sidestack/config/ods.env.example`, directly after the line `SIDESTACK_VRAM_MARGIN_GB=1.0`, add:
   ```
   # VS-18: refuse models whose licence is not commercial (for example OmniVoice), even if
   # accepted. Start the launcher with -AllowNonCommercial for private work only.
   SIDESTACK_COMMERCIAL_ONLY=1
   ```
5. In `sidestack/PLAN.md`, replace the whole `| D2 |` row with:
   ```markdown
   | D2 | Default TTS engines and licensing | **Decided 2026-11-06 (VS-18): both kinds, kept apart.** Anything that may be published or monetized (for example YouTube) uses a commercial-licence engine: VoxCPM2, CosyVoice 3, MOSS-TTS or KittenTTS. OmniVoice and other non-commercial engines are for private work only. Commercial-only mode (`SIDESTACK_COMMERCIAL_ONLY=1`) is on by default and refuses non-commercial, conditional and unknown licences; `-AllowNonCommercial` turns it off for one run. | The OmniVoice weights are CC-BY-NC, and the audio tokenizer carries extra terms. Categories come from the licence registry (`backend/config/model_licenses.json`), which records model-card metadata, not legal clearance. |
   ```
6. Create `tests/test_sidestack_licensing.py`:
   ```python
   """SideStack VS-18 — commercial-only mode.

   Acceptance records are kept in memory (no SQLite); the registry is the real one.
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

   # tests/conftest.py stubs ensure_accepted to "accepted" unless a test opts in.
   pytestmark = pytest.mark.model_licence_gate


   @pytest.fixture
   def ma(monkeypatch):
       """services.model_acceptance (live module) with an in-memory settings store."""
       _ss = importlib.import_module("services.settings_store")

       text: dict[str, str] = {}
       monkeypatch.setattr(_ss, "get_text", lambda k, default=None: text.get(k, default))
       monkeypatch.setattr(_ss, "set_text", lambda k, v: text.__setitem__(k, v))
       monkeypatch.setattr(_ss, "get_license_accepted", lambda engine: False)
       monkeypatch.setattr(_ss, "set_license_accepted", lambda engine, accepted: None)
       monkeypatch.delenv("SIDESTACK_COMMERCIAL_ONLY", raising=False)
       return importlib.import_module("services.model_acceptance")


   @pytest.fixture
   def lic(ma):
       return importlib.import_module("sidestack_fork.licensing")


   def _accept(ma, repo_id):
       ma.accept(repo_id, ma.status(repo_id)["fingerprint"])


   def test_c1_flag_off_upstream_unchanged(ma, lic):
       lic.ensure_commercial_only(["k2-fsa/OmniVoice"])  # no-op
       _accept(ma, "k2-fsa/OmniVoice")
       ma.ensure_accepted(["k2-fsa/OmniVoice"])  # accepted: upstream lets it through


   def test_c2_noncommercial_refused_even_when_accepted(ma, lic, monkeypatch):
       monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
       _accept(ma, "k2-fsa/OmniVoice")
       with pytest.raises(lic.CommercialOnlyRefused) as exc:
           ma.ensure_accepted(["k2-fsa/OmniVoice"])
       assert isinstance(exc.value, ma.ModelLicenceNotAccepted)
       detail = exc.value.detail()
       assert detail["code"] == "commercial_only_mode"
       assert detail["models"][0]["category"] == "noncommercial"
       assert "-AllowNonCommercial" in detail["message"]


   def test_c3_commercial_passes(ma, lic, monkeypatch):
       monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
       ma.ensure_accepted(["openbmb/VoxCPM2", "KittenML/kitten-tts-mini-0.8"])


   def test_c4_unknown_and_conditions_refused(ma, lic, monkeypatch):
       monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
       for repo in ("IndexTeam/IndexTTS-2.5", "Supertone/supertonic-3", "no-such/model"):
           with pytest.raises(lic.CommercialOnlyRefused):
               ma.ensure_accepted([repo])


   def test_c5_engine_level(ma, lic, monkeypatch):
       monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
       with pytest.raises(lic.CommercialOnlyRefused):
           ma.ensure_engine_accepted("omnivoice")
       for engine in ("voxcpm2", "kittentts", "cosyvoice"):
           ma.ensure_engine_accepted(engine)


   def test_c6_generator_input_still_checked_upstream(ma, lic, monkeypatch):
       monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "0")
       with pytest.raises(ma.ModelLicenceNotAccepted) as exc:
           ma.ensure_accepted(r for r in ["k2-fsa/OmniVoice"])
       assert not isinstance(exc.value, lic.CommercialOnlyRefused)
       assert exc.value.detail()["code"] == "model_licence_required"


   def test_c7_profile_and_hook():
       with open(os.path.join(ROOT, "sidestack", "config", "ods.env.example"), encoding="utf-8") as f:
           assert "SIDESTACK_COMMERCIAL_ONLY=1" in f.read().splitlines()
       with open(os.path.join(ROOT, "backend", "services", "model_acceptance.py"), encoding="utf-8") as f:
           src = f.read()
       assert src.count("SideStack fork (VS-18)") == 1
       assert src.count("ensure_commercial_only(repo_ids)") == 1
   ```
7. In `tests/test_sidestack_launcher.py`, add at the end of the file:
   ```python


   # ── L14: commercial-only mode and -AllowNonCommercial (VS-18) ───────────────────────
   @win_only
   def test_l14_commercial_only_switch():
       code, out = _run(["-DryRun", "-Json"], _env())
       assert code == 0, out
       plan = json.loads(out)
       assert plan["env"]["SIDESTACK_COMMERCIAL_ONLY"] == "1"
       assert plan["licence_mode"] == "commercial-only"

       code, out = _run(["-DryRun", "-Json", "-AllowNonCommercial"], _env())
       assert code == 0, out
       plan = json.loads(out)
       assert plan["env"]["SIDESTACK_COMMERCIAL_ONLY"] == "0"
       assert plan["licence_mode"] == "non-commercial allowed"
   ```
8. Run Acceptance and report in the AGENTS-SIDESTACK §4 format, listing every command. Append the report at the very end of this spec under a `## Builder report` heading, and set this lane's tracker status to `running (dsh done)`.

## Acceptance

```powershell
& $py -m pytest tests/test_sidestack_licensing.py -q -p no:cacheprovider   # expect: 7 passed
& $py -m pytest tests/test_sidestack_launcher.py -q -p no:cacheprovider   # expect: preflight count + 1, 0 failed
& $py -m pytest tests/test_sidestack_admission.py tests/test_sidestack_dictation.py tests/test_sidestack_ods_asr.py tests/test_sidestack_ods_provider.py tests/test_structure_doc.py -q -p no:cacheprovider   # expect: 0 failed
& $py -m pytest tests -q -p no:cacheprovider -k "licen or acceptance" --continue-on-collection-errors -rfE   # expect: only the 3 baseline failures (test_mas_python_runtime, test_mobile_contract, test_mobile_mp3_source) and the baseline collection error in test_ci_change_detection.py (record the count)
git status --short    # expect: exactly the files in "Files"
Get-ChildItem -Force | Where-Object Name -match '^(pytest-of-|omnivoice-test-data-)'   # expect: nothing
python sidestack/scripts/check_sidestack.py           # expect: OK
```

## Part B — live check (Operator, after approval)

No downloads. ODS's LLM stays as it is (KittenTTS runs on the CPU, and OmniVoice is refused before it loads).
1. Start with the launcher (default, commercial-only):
   - `POST /generate` with `engine=kittentts` and short synthetic text → **200**;
   - `POST /generate` with `engine=omnivoice` → **403** with `detail.code == "commercial_only_mode"`, and nothing downloads (HF cache unchanged).
   Open the web UI, pick OmniVoice and try to generate. Record what the UI shows (a message, not the licence dialog). `-Stop`.
2. Start with `-AllowNonCommercial`:
   - `POST /generate` with `engine=omnivoice` → **403** with `detail.code == "model_licence_required"` (the licence has not been accepted). This is upstream's normal path, and nothing downloads.
   `-Stop`.
3. Record the results in this spec.

## Part C — OmniVoice for private work (later, optional)

1. **The user** starts with `-AllowNonCommercial`, opens Model Catalogue → OmniVoice, reads the licence and accepts it. Accepting terms is the user's own act.
2. With **real run approval**, and ODS's LLM stopped (OmniVoice needs about 7 GB: a 6 GB floor plus the margin):
   - the first OmniVoice generation downloads its weights;
   - record the size, the latency and the VRAM.
3. Restart without the switch, and confirm OmniVoice is refused again.

## Out of scope

- Hiding non-commercial engines from the engine picker (the refusal message is the signal; a UI change touches the frontend and 21 locale catalogs).
- Labelling or watermarking audio by licence.
- Gating `sherpa-onnx` dictation models, which have no rows in the registry (upstream does not gate them either).
- Legal review of any licence.

## Reviewer notes

- **Mutation checks:**
  - delete the hook → C2, C4, C5 and C7 fail;
  - `!= "commercial"` → `== "noncommercial"` → C4 fails;
  - drop the launcher override line → L14 fails.
- `repo_ids = list(repo_ids)` is defensive and not mutation-checked: with the mode off, the fork returns before reading the input; with it on, any non-commercial model is refused by the fork itself. So consuming a generator early changes no outcome. C6 only proves upstream's path is intact with the mode off.
- `tests/conftest.py` stubs `ensure_accepted` to "accepted" in every test not marked `model_licence_gate`. So the hook never runs in the rest of the suite, and the VS-18 tests carry the marker (as upstream's `test_model_acceptance.py` does).
- Upstream's global handler (`main.py`, `@app.exception_handler(ModelLicenceNotAccepted)`) returns 403 with `exc.detail()`, so the subclass needs no new handler.
- Routes that catch `ModelLicenceNotAccepted` themselves (capture, dub, batch) treat a commercial-only refusal like an unaccepted licence. That is the intended behaviour: the model is not used.
- The desktop/web client opens the licence dialog for `model_licence_required`. Part B checks what it does with `commercial_only_mode`.

## Builder report

The builder (dsh, Qwen 3.8 27B on ODS) did not finish. It passed Preflight (40 passed), wrote all seven files and ran an Acceptance subset (48 passed). It then reasoned for about 28 minutes without a tool call and never wrote its report. The reviewer stopped it on 2026-11-08.

Its `licensing.py` and `tests/test_sidestack_licensing.py` matched the spec exactly. Four other files did not:
- **Step 2:** it dropped `repo_ids = list(repo_ids)`. A generator passed to `ensure_accepted` would be used up by the fork, so upstream's acceptance check would see no models.
- **Step 3:**
  - it did not add the help text;
  - `-AllowNonCommercial` set the variable only at start, so the dry-run plan still showed `SIDESTACK_COMMERCIAL_ONLY=1`;
  - `licence_mode` came from the switch instead of the effective value, and used the spelling `noncommercial-allowed`.
- **Steps 4, 5 and 7:** it changed the profile comment, the D2 wording and L14. Its L14 did not check the env override.

The reviewer restored those four files from HEAD and applied Steps 2, 3, 4, 5 and 7 exactly as written.

## Reviewer verification (Part A, 2026-11-08)

- **Acceptance (Hard law 9 environment):**
  - `test_sidestack_licensing.py`: 7 passed;
  - `test_sidestack_launcher.py`: 14 passed (13 + L14);
  - admission, dictation, ODS ASR, ODS provider and structure doc: 39 passed;
  - `-k "licen or acceptance"`: 250 passed and 3 failed. HEAD gives 243 passed with the same 3 failures, all in the VS-02 baseline. The extra 7 passes are C1–C7.
  - The spec's command stops at a baseline collection error in `test_ci_change_detection.py`, so it now uses `--continue-on-collection-errors`.
  - `git status` shows exactly the files in Files. There are no stray test directories, and `check_sidestack.py` reports OK.
- **Mutation checks (all caught, files restored):**
  - delete the hook → C2, C4, C5 and C7 fail;
  - `!= "commercial"` → `== "noncommercial"` → C4 fails;
  - drop the launcher override → L14 fails.
- **Full suite** (`-n 8`, 14 min 48 s): 94 failed, 13,019 passed, 137 skipped and 20 errors.
  - 9 baseline failures now pass.
  - Exactly one failure is outside the baseline: `test_relock_cache_identity.py::test_sweep_keeps_a_retired_file_a_profile_references_again`. Run alone with VS-18 it failed 1 of 3 times; on HEAD it passed 5 of 5. Its failure is `.retired` not yet empty after a profile sweep. That code path does not call `model_acceptance`, and VS-18 changes nothing it uses. Recorded as a timing flake, not a VS-18 regression.
- **Launcher:** the start path copies `$cfg` into the process environment and its `finally` block restores it, so the `$cfg` override covers both the dry-run plan and a real start.
- **Next:** Part B, the live check, needs real run approval.

## Part B results (Operator, 2026-11-08)

The user gave real run approval. ODS's LLM stayed loaded (GPU memory used was 24.8 GB before and after). Voice Studio was started with the launcher from the worktree, because the main checkout has no built `frontend/dist`.

1. **Default start (commercial-only):**
   - The dry-run plan shows `licence_mode: commercial-only` and `SIDESTACK_COMMERCIAL_ONLY=1`.
   - `POST /generate`, `engine=kittentts` → **200**: a 5.1 s WAV, 24 kHz mono, in 13.1 s on a cold start.
   - `POST /generate`, `engine=omnivoice` → **403** in 0.01 s, with `detail.code == "commercial_only_mode"`. The refusal lists both `k2-fsa/OmniVoice` (noncommercial) and `eustlb/higgs-audio-v2-tokenizer` (unknown), and names VoxCPM2 and `-AllowNonCommercial`.
   - **Web UI:**
     - The browser pane's first-run wizard was skipped by setting its local `voicestudio.setup.complete.v1` flag. No model packs were chosen, and no privacy or analytics setting was changed.
     - The Design page shows "Text-to-speech is not ready" and a **Set up** button, because the default engine is OmniVoice and it has not been downloaded.
     - **Set up** would download the recommended model. Upstream's download route has no licence check, and commercial-only mode does not block downloads either. Not clicked, because Part B allows no downloads.
     - So the on-screen refusal message was not seen live. The frontend opens the licence dialog only for `model_licence_required` (`model-license-contract.ts`), so `commercial_only_mode` does not open it, as designed.
   - `-Stop`.
2. **`-AllowNonCommercial`:**
   - The dry-run plan shows `licence_mode: non-commercial allowed` and `SIDESTACK_COMMERCIAL_ONLY=0`.
   - `engine=omnivoice` → **403** with `detail.code == "model_licence_required"`, upstream's normal path.
   - `engine=kittentts` → **200** in 5.8 s.
   - `-Stop`; nothing is listening on port 3900.
3. **No downloads:** the HF cache still holds only `KittenML/kitten-tts-mini-0.8` and `openbmb/VoxCPM2`. Its size grew by 2,520 bytes, exactly the two startup logs in `xet/logs` (1,260 bytes each).

**Verdict:** PASS for the server side. The UI message is not verified live.

**Findings (follow-ups, not fixed here):**
- **Default engine:** upstream's default engine is OmniVoice. In commercial-only mode a fresh install shows "not ready" and offers to download a model the mode will refuse. A SideStack default of a commercial engine (VoxCPM2 or KittenTTS) would fix this.
- **Downloads:** downloads are not licence-gated, upstream or here.
- **Cosmetic:** with two models, the refusal reads "… (unknown) is not licensed"; it should say "are".