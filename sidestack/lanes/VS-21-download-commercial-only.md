# VS-21 — Commercial-only mode refuses downloads too

- **Phase:** 4
- **Run by:** dsh does Part A (code and offline tests). The Operator does Part B (live refusal check, no downloads).
- **Gate:**
  - none for Part A;
  - **real run approval** for Part B: start Voice Studio in its default profile and ask it to download non-commercial models, which must be refused before any transfer starts.
- **Depends on:** VS-18
- **Status:** verified (Part B PASS, 2026-11-08)

## Goal

With `SIDESTACK_COMMERCIAL_ONLY=1` (the SideStack profile's default), Voice Studio refuses to **download** a model it would refuse to use. Without the flag, upstream behaviour is unchanged.

**Why (VS-18 Part B, 2026-11-08):**
- VS-18 refuses non-commercial models when they are loaded or used, but downloads are not checked.
- So the Design page's "Set up" button, the Model Library and the first-run wizard can still fetch OmniVoice (several GB) that the app then refuses to run. VS-18 Part B could not click "Set up" for that reason.

**Fix:** the three download routes call the VS-18 check before anything starts.

| Route | What it downloads | Check |
|---|---|---|
| `POST /models/install` (Model Library, wizard, "Set up", download retry) | one catalogue entry and its dependencies | `ensure_commercial_only([catalogue key, *dependency repos])` |
| `POST /engines/sidecar/{engine_id}/install` | a sidecar engine and its weights | `ensure_engine_commercial_only(engine_id)` (new) |
| `POST /engines/omnivoice-gguf/quants/download` | OmniVoice GGUF weights | `ensure_engine_commercial_only("omnivoice-gguf")` |

- A refusal is VS-18's `CommercialOnlyRefused`, so `main.py`'s existing handler answers **403** with code `commercial_only_mode`.
- **The catalogue key, not the Hub repo, is the licence record.** A package entry such as `audio-cpp/audio.cpp-gguf:dots-tts-soar-q8_0` (apache-2.0) has its own registry row inside the non-commercial `audio-cpp/audio.cpp-gguf` repo. Checking the Hub repo would refuse a commercial package.
- `ensure_engine_commercial_only` fails closed: an unreadable registry refuses, as upstream's `ensure_engine_accepted` does.

**What the profile now refuses to download** (registry categories, checked 2026-11-08; categories come from model cards and are not legal advice):
- `/models/install`: `k2-fsa/OmniVoice`, `audio-cpp/audio.cpp-gguf` (the whole repo), `facebook/nllb-200-distilled-600M`, `mlx-community/Llama-OuteTTS-1.0-1B-4bit` (non-commercial); `mlx-community/whisper-large-v3-turbo`, `mlx-community/whisper-tiny-mlx`, `mlx-community/whisper-large-v3-turbo-asr-fp16`, `mlx-community/Chatterbox-TTS-4bit`, `csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8`, `csukuangfj/sherpa-onnx-whisper-tiny` (unknown).
- Sidecars: `indextts2` (unknown), `supertonic3` (conditions).
- GGUF: `Serveurperso/OmniVoice-GGUF` (non-commercial).
- Every other catalogue entry and sidecar is commercial, including VoxCPM2, CosyVoice3, KittenTTS, MOSS-TTS, the Systran faster-whisper models and pyannote.
- VS-18 already refuses all of these at load time, so nothing that works today stops working.

## Files

| Path | Change |
|---|---|
| `backend/sidestack_fork/licensing.py` | edit: add `ensure_engine_commercial_only()` |
| `backend/api/routers/setup/download.py` | edit: hook in `install_model` |
| `backend/api/routers/engines.py` | edit: hooks in `install_sidecar_engine` and `download_omnivoice_gguf_quant` |
| `tests/test_sidestack_downloads.py` | new: W1–W8 |
| `sidestack/lanes/VS-21-download-commercial-only.md`, `sidestack/lanes/README.md` | builder report / status |

## Preflight

Start with the environment block from AGENTS-SIDESTACK.md Hard law 9, run from the worktree root.

```powershell
git status --short     # expect: only `?? sidestack/lanes/VS-21-download-commercial-only.md` and ` M sidestack/lanes/README.md` (the spec is not committed yet)
Select-String backend\api\routers\setup\download.py -Pattern "^    # Cooldown guard — don't retry if the same model just failed\.$"   # expect: 1 match
Select-String backend\api\routers\engines.py -Pattern '^        return sidecar_install\.start_install\(engine_id\)$'   # expect: 1 match
Select-String backend\api\routers\engines.py -Pattern '^def download_omnivoice_gguf_quant\(req: GGUFQuantRequest\):$'   # expect: 1 match
Test-Path tests\test_sidestack_downloads.py   # expect: False
& $py -m pytest tests/test_sidestack_licensing.py -q -p no:cacheprovider   # expect: 8 passed
```

## Steps

1. At the end of `backend/sidestack_fork/licensing.py`, after `ensure_commercial_only`, append (two blank lines before it, as between the other functions):
   ```python
   def ensure_engine_commercial_only(engine_id: str) -> None:
       """ensure_commercial_only for the registry models an engine loads."""
       if not enabled():
           return
       from services.model_acceptance import repos_for_engine

       try:
           repos = repos_for_engine(engine_id)
       except Exception as exc:  # noqa: BLE001 — an unreadable registry must not open the gate
           raise ModelLicenceNotAccepted([], reason="registry_unreadable") from exc
       ensure_commercial_only(repos)
   ```
   Keep one newline at the end of the file.
2. In `backend/api/routers/setup/download.py`, in `install_model`, replace these three lines:
   ```python
               detail="Remote model installation is unavailable; target must be 'local'.",
           )
       # Cooldown guard — don't retry if the same model just failed.
   ```
   with:
   ```python
               detail="Remote model installation is unavailable; target must be 'local'.",
           )
       # SideStack fork (VS-21): commercial-only mode refuses the download too. The
       # catalogue key (req.repo_id) is the licence record: a package such as
       # dots-tts has its own row inside a non-commercial Hub repo.
       from sidestack_fork.licensing import ensure_commercial_only
       ensure_commercial_only([req.repo_id, *(d["repo_id"] for d in model_spec.get("dependencies") or ())])
       # Cooldown guard — don't retry if the same model just failed.
   ```
3. In `backend/api/routers/engines.py`, make two replacements.
   - In `install_sidecar_engine`, replace these three lines:
     ```python
         from services import sidecar_install
         try:
             return sidecar_install.start_install(engine_id)
     ```
     with:
     ```python
         # SideStack fork (VS-21): commercial-only mode refuses the install too.
         from sidestack_fork.licensing import ensure_engine_commercial_only
         ensure_engine_commercial_only(engine_id)
         from services import sidecar_install
         try:
             return sidecar_install.start_install(engine_id)
     ```
   - Replace these two lines:
     ```python
     def download_omnivoice_gguf_quant(req: GGUFQuantRequest):
         from api.routers.setup.models import disk_space_error
     ```
     with:
     ```python
     def download_omnivoice_gguf_quant(req: GGUFQuantRequest):
         # SideStack fork (VS-21): commercial-only mode refuses the download too.
         from sidestack_fork.licensing import ensure_engine_commercial_only
         ensure_engine_commercial_only("omnivoice-gguf")
         from api.routers.setup.models import disk_space_error
     ```
4. Create `tests/test_sidestack_downloads.py` with exactly this content:
   ```python
   """SideStack VS-21 — commercial-only mode refuses downloads too.

   Covers POST /models/install, POST /engines/sidecar/{id}/install and
   POST /engines/omnivoice-gguf/quants/download. Route functions are called
   directly; nothing is downloaded. Acceptance records are kept in memory.
   """
   from __future__ import annotations

   import asyncio
   import importlib
   import os
   import sys
   import time

   import pytest

   sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

   os.environ.setdefault("OMNIVOICE_MODEL", "test")
   os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

   from fastapi import HTTPException  # noqa: E402

   ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

   pytestmark = pytest.mark.model_licence_gate


   @pytest.fixture
   def lic(monkeypatch):
       """sidestack_fork.licensing with an in-memory settings store; the flag starts unset."""
       _ss = importlib.import_module("services.settings_store")
       text: dict[str, str] = {}
       monkeypatch.setattr(_ss, "get_text", lambda k, default=None: text.get(k, default))
       monkeypatch.setattr(_ss, "set_text", lambda k, v: text.__setitem__(k, v))
       monkeypatch.setattr(_ss, "get_license_accepted", lambda engine: False)
       monkeypatch.setattr(_ss, "set_license_accepted", lambda engine, accepted: None)
       monkeypatch.delenv("SIDESTACK_COMMERCIAL_ONLY", raising=False)
       return importlib.import_module("sidestack_fork.licensing")


   @pytest.fixture
   def dl():
       return importlib.import_module("api.routers.setup.download")


   @pytest.fixture
   def eng():
       return importlib.import_module("api.routers.engines")


   def _install(dl, repo_id):
       return asyncio.run(dl.install_model(dl.InstallModelRequest(repo_id=repo_id)))


   def _cooling(dl, monkeypatch, repo_id):
       """Make the upstream cooldown answer 429 for repo_id: proof the gate let it through."""
       monkeypatch.setitem(dl._install_cooldowns, repo_id, time.time())


   def test_w1_hooks_in_place():
       def read(*parts):
           with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
               return f.read()
       assert read("backend", "api", "routers", "setup", "download.py").count("SideStack fork (VS-21)") == 1
       assert read("backend", "api", "routers", "engines.py").count("SideStack fork (VS-21)") == 2
       assert "def ensure_engine_commercial_only(" in read("backend", "sidestack_fork", "licensing.py")


   def test_w2_install_refuses_noncommercial(lic, dl, monkeypatch):
       _cooling(dl, monkeypatch, "k2-fsa/OmniVoice")
       with pytest.raises(HTTPException) as off:  # flag unset: upstream path (cooldown 429)
           _install(dl, "k2-fsa/OmniVoice")
       assert off.value.status_code == 429
       monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
       with pytest.raises(lic.CommercialOnlyRefused) as on:
           _install(dl, "k2-fsa/OmniVoice")
       detail = on.value.detail()
       assert detail["code"] == "commercial_only_mode"
       assert [m["repo_id"] for m in detail["models"]] == ["k2-fsa/OmniVoice"]


   def test_w3_install_package_uses_catalogue_key(lic, dl, monkeypatch):
       monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
       package = "audio-cpp/audio.cpp-gguf:dots-tts-soar-q8_0"  # apache-2.0 row in a non-commercial repo
       _cooling(dl, monkeypatch, package)
       with pytest.raises(HTTPException) as passed:
           _install(dl, package)
       assert passed.value.status_code == 429
       with pytest.raises(lic.CommercialOnlyRefused):
           _install(dl, "audio-cpp/audio.cpp-gguf")


   def test_w4_install_checks_dependencies(lic, dl, monkeypatch):
       monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
       original = dl.KNOWN_MODELS
       fake = {"repo_id": "openbmb/VoxCPM2", "dependencies": [{"repo_id": "k2-fsa/OmniVoice"}]}
       monkeypatch.setattr(dl, "KNOWN_MODELS", [fake])
       with pytest.raises(lic.CommercialOnlyRefused) as exc:
           _install(dl, "openbmb/VoxCPM2")
       assert [m["repo_id"] for m in exc.value.models] == ["k2-fsa/OmniVoice"]
       monkeypatch.setattr(dl, "KNOWN_MODELS", original)
       _cooling(dl, monkeypatch, "pyannote/speaker-diarization-3.1")
       with pytest.raises(HTTPException) as passed:  # commercial model, commercial dependencies
           _install(dl, "pyannote/speaker-diarization-3.1")
       assert passed.value.status_code == 429


   def test_w5_sidecar_install(lic, eng, monkeypatch):
       sidecar_install = importlib.import_module("services.sidecar_install")
       started = []

       def start(eid):
           if eid not in sidecar_install.SPECS:
               raise KeyError(eid)  # as upstream: the route answers 404
           started.append(eid)
           return {"status": "started"}

       monkeypatch.setattr(sidecar_install, "start_install", start)
       monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
       for eid in ("indextts2", "supertonic3"):  # unknown and conditions categories
           with pytest.raises(lic.CommercialOnlyRefused):
               eng.install_sidecar_engine(eid)
       assert started == []
       assert eng.install_sidecar_engine("voxcpm2") == {"status": "started"}
       with pytest.raises(HTTPException) as missing:  # no registry rows, no installer: upstream 404
           eng.install_sidecar_engine("no-such-engine")
       assert missing.value.status_code == 404
       monkeypatch.delenv("SIDESTACK_COMMERCIAL_ONLY")
       eng.install_sidecar_engine("indextts2")
       assert started == ["voxcpm2", "indextts2"]


   def test_w6_gguf_download(lic, eng, monkeypatch):
       quants = importlib.import_module("engines.omnivoice_gguf.quants")
       models = importlib.import_module("api.routers.setup.models")
       started = []
       monkeypatch.setattr(quants, "start_download", lambda target: started.append(target) or {"status": "started"})
       monkeypatch.setattr(models, "disk_space_error", lambda *a, **k: None)
       monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
       with pytest.raises(lic.CommercialOnlyRefused) as exc:
           eng.download_omnivoice_gguf_quant(eng.GGUFQuantRequest(quant="auto"))
       assert [m["repo_id"] for m in exc.value.models] == ["Serveurperso/OmniVoice-GGUF"]
       assert started == []
       monkeypatch.delenv("SIDESTACK_COMMERCIAL_ONLY")
       assert eng.download_omnivoice_gguf_quant(eng.GGUFQuantRequest(quant="auto")) == {"status": "started"}
       assert started == [None]


   def test_w7_registry_unreadable_fails_closed(lic, monkeypatch):
       ma = importlib.import_module("services.model_acceptance")

       def broken(engine_id, identity=None):
           raise OSError("registry unreadable")

       monkeypatch.setattr(ma, "repos_for_engine", broken)
       lic.ensure_engine_commercial_only("voxcpm2")  # flag unset: no-op, upstream unchanged
       monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
       with pytest.raises(ma.ModelLicenceNotAccepted) as exc:
           lic.ensure_engine_commercial_only("voxcpm2")
       assert exc.value.reason == "registry_unreadable"
       assert not isinstance(exc.value, lic.CommercialOnlyRefused)


   def test_w8_every_installer_engine_has_registry_rows():
       """An installer engine with no registry rows would pass the gate unchecked."""
       ma = importlib.import_module("services.model_acceptance")
       sidecar_install = importlib.import_module("services.sidecar_install")
       for eid in [*sidecar_install.SPECS, "omnivoice-gguf"]:
           assert ma.repos_for_engine(eid), eid
   ```
   Keep one newline at the end of the file.
5. Run Acceptance and report in the AGENTS-SIDESTACK §4 format, listing every command. Append the report at the very end of this spec under a `## Builder report` heading, and set this lane's tracker status to `running (dsh done)`.

## Acceptance

```powershell
& $py -m pytest tests/test_sidestack_downloads.py -q -p no:cacheprovider   # expect: 8 passed
& $py -m pytest tests/test_sidestack_licensing.py tests/test_sidestack_defaults.py tests/test_sidestack_admission.py tests/test_sidecar_install.py tests/test_catalogue_packages.py tests/test_model_install_cancel.py tests/test_model_install_dedup.py tests/test_install_disk_space.py tests/test_model_license_workflow.py tests/test_admin_route_policy.py -q -p no:cacheprovider   # expect: 0 failed
git status --short    # expect: exactly the files in "Files"
Get-ChildItem -Force | Where-Object Name -match '^(pytest-of-|omnivoice-test-data-)'   # expect: nothing
python sidestack/scripts/check_sidestack.py           # expect: OK
```

## Part B — live refusal (Operator, after approval)

No step may start a download. If any transfer starts, `-Stop` at once and report.

1. Start Voice Studio with the worktree launcher, default profile (commercial-only, VoxCPM2 default). Record the size of the Hugging Face cache under the data folder.
2. `POST /models/install` with `{"repo_id": "k2-fsa/OmniVoice"}` → **403**, code `commercial_only_mode`, naming `k2-fsa/OmniVoice (noncommercial)`. `GET /models/install/status` shows no job for it.
3. `POST /engines/sidecar/indextts2/install` → **403** `commercial_only_mode`. `GET /engines/sidecar/indextts2/install/status` shows no new run.
4. `POST /engines/omnivoice-gguf/quants/download` with `{"quant": "auto"}` → **403** `commercial_only_mode`.
5. In the web UI, try once to set up OmniVoice (the Design page's "Set up" button with OmniVoice picked, or the Model Library). Record the message the UI shows. If picking OmniVoice changes the saved engine, set it back to VoxCPM2 afterwards and confirm `/engines` `tts.active` is `voxcpm2`.
6. Check that the Hugging Face cache size has not changed, then `-Stop`. Record the results here.

## Out of scope

- Translation engine installs (`/engines/translation/{id}/install`, Argos packs). They install pip packages, not registry models.
- `POST /models/install/commit`, the reviewed-transfer route. Upstream has no reviewed rows enabled. Revisit if it gains any.
- How the UI presents a `commercial_only_mode` 403 on a download. The frontend opens its licence dialog only for `model_licence_required`. If Part B finds the message poor, a later lane changes the frontend.
- Hiding non-commercial engines in the engine picker.

## Reviewer notes

- **Mutation checks** (each was caught when the lane was written):
  - delete the Step 2 `ensure_commercial_only([...])` line → W2, W3 and W4 fail;
  - `[req.repo_id,` → `[hub_repo,` → W3 fails (the dots-tts package is refused);
  - drop the dependency list from the Step 2 call → W4 fails;
  - delete `ensure_engine_commercial_only(engine_id)` → W5 fails;
  - delete `ensure_engine_commercial_only("omnivoice-gguf")` → W6 fails;
  - in Step 1, `raise ModelLicenceNotAccepted(...)` → `return` → W7 fails;
  - in Step 1, delete the `if not enabled(): return` lines → W7 fails.
- W2 and W3 prove "the gate let it through" without downloading: a recent failure is planted in upstream's install cooldown, so a request that passes the gate stops at upstream's 429.
- W8 guards against a silent pass: an installer engine with no registry rows would never be checked.
- **Checked while writing this lane (2026-11-08):** the spec text was applied to HEAD in a scratch run, and W1–W8 passed with all seven mutations caught. The category list above came from the live registry.

## Builder report

```
LANE: VS-21
STATUS: DONE
FILES CHANGED: backend/sidestack_fork/licensing.py (A3013708D263) backend/api/routers/setup/download.py (F72CE4FFA9B8) backend/api/routers/engines.py (7DE8BDC7FFEA) tests/test_sidestack_downloads.py (A9F65F70A8CD, new) sidestack/lanes/README.md (FD13C28A41E8, status → running (dsh done))
COMMANDS RUN:
  git status --short → exit 0 (preflight matched: M sidestack/lanes/README.md, ?? VS-21 spec)
  Select-String download.py cooldown comment → found line 614; engines.py start_install return → line 587; GGUF def → line 508; tests/test_sidestack_downloads.py absent — all as expected
  & $py -m pytest tests/test_sidestack_licensing.py -q -p no:cacheprovider → exit 0, 8 passed
  & $py -m pytest tests/test_sidestack_downloads.py -q -p no:cacheprovider → exit 0, 8 passed (13.97 s)
  & $py -m pytest tests/test_sidestack_licensing.py tests/test_sidestack_defaults.py tests/test_sidestack_admission.py tests/test_sidecar_install.py tests/test_catalogue_packages.py tests/test_model_install_cancel.py tests/test_model_install_dedup.py tests/test_install_disk_space.py tests/test_model_license_workflow.py tests/test_admin_route_policy.py -q -p no:cacheprovider → exit 0, 319 passed, 4 subtests passed (34.04 s)
  git status --short → exit 0, no extra residue in worktree root
  Get-ChildItem -Force | Where-Object Name -match '^(pytest-of-|omnivoice-test-data-)' → empty (no residue)
  python sidestack/scripts/check_sidestack.py → exit 0, "OK: 14 required files, 20 lane specs, links, manifest, env profile, secret scan"
NOT DONE / UNSURE: none (Part B is the operator's; no Voice Studio start, no container, no downloads)
```

## Reviewer verification (Part A, 2026-11-08)

- **Builder:** finished in under 5 minutes. All four code files match the spec applied to HEAD exactly, and the report is complete.
- **Acceptance re-run (Hard law 9 environment):**
  - `test_sidestack_downloads.py`: 8 passed;
  - the related routes and licence tests: 319 passed, 0 failed.
- **Mutation checks on the builder's files**, all caught by the intended test:
  - drop the install hook → W2, W3 and W4 fail;
  - `hub_repo` instead of the catalogue key → W3 fails;
  - drop the dependencies → W4 fails;
  - drop the sidecar hook → W5 fails;
  - drop the GGUF hook → W6 fails;
  - registry error opens the gate → W7 fails;
  - helper ignores the flag → W7 fails.
- **Full suite** (`-n 8`, 13 min 39 s): 94 failed, 13,028 passed, 136 skipped and 31 errors.
  - Outside the baseline: only the 11 known `test_no_audio_track` order-leak ids, and the known random `test_relock_cache_identity::test_sweep_keeps_a_retired_file...` flake.
  - Run on their own, the `test_no_audio_track` ids pass. The relock file failed 2 of 3 times, passing once, with no VS-21 code involved.
  - 4 baseline failures now pass.
- **Next:** Part B, the live refusal, needs real run approval. Nothing is downloaded.

## Part B results (Operator, 2026-11-08)

**PASS.** Part A was committed first (0f54f16b9). Voice Studio was started with the worktree launcher in the default profile (commercial-only, VoxCPM2 default). Before the run, the Hugging Face cache held only `KittenML/kitten-tts-mini-0.8` and `openbmb/VoxCPM2`, and the engines folder held only `voxcpm2`.

- **`POST /models/install` `k2-fsa/OmniVoice`:** 403 `commercial_only_mode`, "k2-fsa/OmniVoice (noncommercial) is not licensed for commercial use. …". `/models/install/status` showed no jobs.
- **`POST /engines/sidecar/indextts2/install`:** 403 `commercial_only_mode`, naming `IndexTeam/IndexTTS-2.5 (unknown)`. Its install status showed `job: null`, not installed.
- **`POST /engines/omnivoice-gguf/quants/download` `{"quant": "auto"}`:** 403 `commercial_only_mode`, naming `Serveurperso/OmniVoice-GGUF (noncommercial)`.
- **Web UI:** in Settings → Models → TTS, the OmniVoice rows carry upstream's "Non-commercial" badge. One click on "Download" for k2-fsa/OmniVoice showed a red pop-up with the full message, including the "-AllowNonCommercial" hint. No progress bar appeared and no job started. The Model Library was used so the saved engine did not change: `prefs.json` has no `tts_backend`, and `/engines` `tts.active` stayed `voxcpm2`.
- **Nothing downloaded:**
  - the cache's model folders are unchanged (17 non-log files, the same two models);
  - the only new file is the Hugging Face transfer library's startup log, written at launch before any request;
  - the engines folder is unchanged.
- **Still offered in the UI:** the OmniVoice rows keep their "Download" and "Select" buttons; only the server refuses. A later lane could hide or disable them in commercial-only mode (out of scope here).
- `-Stop` stopped the server.
