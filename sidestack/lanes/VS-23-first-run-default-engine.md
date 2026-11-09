# VS-23 — First-run setup requires the default engine

- **Phase:** 4
- **Run by:** dsh does Part A (code and offline tests). The Operator does Part B (live read of the setup status, no downloads).
- **Gate:**
  - none for Part A;
  - **real run approval** for Part B.
- **Depends on:** VS-19, VS-21
- **Status:** verified (Part B PASS, 2026-11-08)

## Goal

With `SIDESTACK_DEFAULT_TTS_BACKEND` set (the SideStack profile sets `voxcpm2`), first-run setup requires the **default engine** instead of upstream's OmniVoice: the engine's catalogue weights **and** the engine itself. Unset, upstream is unchanged.

**Why (decided 2026-11-08):**
- Upstream marks `k2-fsa/OmniVoice` as the one required model. `GET /setup/status` waits for it unless the chosen engine is ready and its weights are downloaded (upstream #3581).
- On a fresh SideStack install, the VoxCPM2 engine is not installed yet. So setup waits for OmniVoice, which commercial-only mode refuses to download (VS-21), and first run cannot finish.
- The user chose to make the profile's default engine the requirement.

**Fix:**
- `services/model_catalogue.py`: when the catalogue loads, `apply_required_default()` marks the default engine's TTS rows `required` and clears `required` on every other TTS row. Everything that reads `required` follows: `/setup/status`, `/setup/recommendations`, curated picks, and the `/models` rows. If no row names the default engine, the catalogue is unchanged.
- `api/routers/setup/wizard.py` `setup_status`: adds `missing_default_engine()`. While the default engine is the chosen engine and is not ready, `missing` gains `{"repo_id": "engine:<id>", "label": "<display name> engine"}`, so `models_ready` stays false.
  - The `engine:` prefix marks it: it is not a catalogue key. The response schema is unchanged; upstream's mobile OpenAPI contract test pins it.
  - A failed probe counts as missing.
  - Choosing another ready engine still lifts the requirement (upstream #3581).

## Files

| Path | Change |
|---|---|
| `backend/sidestack_fork/defaults.py` | edit: add `apply_required_default()`, `missing_default_engine()` |
| `backend/services/model_catalogue.py` | edit: hook after `KNOWN_MODELS` loads |
| `backend/api/routers/setup/wizard.py` | edit: hook in `setup_status` |
| `tests/test_sidestack_first_run.py` | new: R1–R9 |
| `sidestack/lanes/VS-23-first-run-default-engine.md`, `sidestack/lanes/README.md` | builder report / status |

## Preflight

Start with the environment block from AGENTS-SIDESTACK.md Hard law 9, run from the worktree root.

```powershell
git status --short     # expect: only this spec (new) and sidestack/lanes/README.md (its row)
Select-String backend\services\model_catalogue.py -Pattern '^KNOWN_MODELS = _load_models_from_yaml\(\)$'   # expect: 1 match
Select-String backend\api\routers\setup\wizard.py -Pattern '^    cache = hf_cache_dir\(\)$'   # expect: 2 matches (Step 3's three-line block is unique)
Test-Path tests\test_sidestack_first_run.py   # expect: False
& $py -m pytest tests/test_sidestack_defaults.py -q -p no:cacheprovider   # expect: 0 failed
```

## Steps

Each "replace" below names text that occurs exactly once in its file. Keep the file's line endings. Do not run `git checkout`, `git stash`, `git reset` or `git clean`.

1. At the end of `backend/sidestack_fork/defaults.py`, after `default_tts_backend`, append (two blank lines before it, as between functions):
   ```python
   def apply_required_default(models: list[dict]) -> None:
       """VS-23: the default engine's weights become the required first-run model.

       With the flag set, the TTS catalogue rows the default engine loads become
       ``required``, and every other TTS row stops being required (upstream requires
       OmniVoice). When no row names the default engine, the catalogue is left as
       upstream wrote it. Changes the rows in place.
       """
       engine = os.environ.get(ENV_FLAG, "").strip()
       if not engine:
           return
       tts = [m for m in models if str(m.get("role", "")).upper() == "TTS"]
       if not any(engine in (m.get("engines") or []) for m in tts):
           return
       for m in tts:
           if engine in (m.get("engines") or []):
               m["required"] = True
           elif m.get("required"):
               m["required"] = False


   def missing_default_engine() -> list[dict]:
       """VS-23: the default engine as a first-run gap while it is chosen but not ready.

       Empty when the flag is unset, when another engine is chosen (upstream's
       #3581 rule decides then), or when the engine is ready. A failed probe
       reports the engine as missing, so setup never finishes without a voice.
       The entry's repo_id is "engine:<id>", which is not a catalogue key.
       """
       engine = os.environ.get(ENV_FLAG, "").strip()
       if not engine:
           return []
       from services import tts_backend

       label = f"{engine} engine"
       try:
           if tts_backend.active_backend_id() != engine:
               return []
           cls = tts_backend.get_backend_class(engine)
           label = f"{cls.display_name} engine"
           if cls.is_available()[0]:
               return []
       except Exception:  # noqa: BLE001 — doubt keeps the requirement
           pass
       return [{"repo_id": f"engine:{engine}", "label": label}]
   ```
   Keep one newline at the end of the file.
2. In `backend/services/model_catalogue.py`, replace:
   ```python
   KNOWN_MODELS = _load_models_from_yaml()
   ```
   with:
   ```python
   KNOWN_MODELS = _load_models_from_yaml()
   # SideStack fork (VS-23): with SIDESTACK_DEFAULT_TTS_BACKEND set, the default
   # engine's weights are the required first-run model instead of OmniVoice.
   from sidestack_fork.defaults import apply_required_default  # noqa: E402
   apply_required_default(KNOWN_MODELS)
   ```
3. In `backend/api/routers/setup/wizard.py`, in `setup_status`, replace:
   ```python
           if not is_cached(model["repo_id"])
       ]
       cache = hf_cache_dir()
   ```
   with:
   ```python
           if not is_cached(model["repo_id"])
       ]
       # SideStack fork (VS-23): the profile's default engine must be installed too,
       # not only its weights.
       from sidestack_fork.defaults import missing_default_engine
       missing += missing_default_engine()
       cache = hf_cache_dir()
   ```
4. Create `tests/test_sidestack_first_run.py` with exactly this content:
   ```python
   """SideStack VS-23 — first-run setup requires the profile's default engine.

   With SIDESTACK_DEFAULT_TTS_BACKEND set, the default engine's catalogue weights
   are the required first-run model instead of upstream's OmniVoice, and
   GET /setup/status also waits for the engine itself. Nothing is downloaded.
   """
   from __future__ import annotations

   import copy
   import importlib
   import json
   import os
   import subprocess
   import sys

   import pytest

   ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
   sys.path.insert(0, os.path.join(ROOT, "backend"))

   os.environ.setdefault("OMNIVOICE_MODEL", "test")
   os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

   FLAG = "SIDESTACK_DEFAULT_TTS_BACKEND"
   VOXCPM2 = "openbmb/VoxCPM2"
   KITTEN = "KittenML/kitten-tts-mini-0.8"


   class _Ready:
       display_name = "Stub"

       @classmethod
       def is_available(cls):
           return True, "ready"


   class _NotReady:
       display_name = "Stub"

       @classmethod
       def is_available(cls):
           return False, "not installed"


   @pytest.fixture
   def defaults(monkeypatch):
       monkeypatch.delenv(FLAG, raising=False)
       return importlib.import_module("sidestack_fork.defaults")


   @pytest.fixture
   def setup(monkeypatch, defaults):
       """The wizard over the SideStack catalogue with nothing downloaded; returns (wizard, choose)."""
       wizard = importlib.import_module("api.routers.setup.wizard")
       from services import tts_backend

       cached: set[str] = set()
       monkeypatch.setattr(wizard, "is_cached", lambda repo_id: repo_id in cached)
       monkeypatch.setattr(wizard, "_disk_free_gb", lambda path: 100.0)
       monkeypatch.setenv(FLAG, "voxcpm2")
       rows = copy.deepcopy(wizard.KNOWN_MODELS)
       defaults.apply_required_default(rows)
       monkeypatch.setattr(wizard, "KNOWN_MODELS", rows)

       def choose(engine: str, cls, *, downloaded=()) -> None:
           cached.clear()
           cached.update(downloaded)
           monkeypatch.setattr(tts_backend, "active_backend_id", lambda: engine)
           monkeypatch.setattr(tts_backend, "get_backend_class", lambda backend_id: cls)

       return wizard, choose


   def _required(rows):
       return [str(m.get("id") or m["repo_id"]) for m in rows if m.get("required")]


   def _missing(status):
       return [m["repo_id"] for m in status["missing"]]


   def test_r1_hooks_in_place():
       def read(*parts):
           with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
               return f.read()
       assert read("backend", "services", "model_catalogue.py").count("SideStack fork (VS-23)") == 1
       assert read("backend", "api", "routers", "setup", "wizard.py").count("SideStack fork (VS-23)") == 1


   def test_r2_required_follows_the_default_engine(defaults, monkeypatch):
       from services.model_catalogue import KNOWN_MODELS

       upstream = copy.deepcopy(KNOWN_MODELS)
       rows = copy.deepcopy(upstream)
       defaults.apply_required_default(rows)  # flag unset: unchanged
       assert rows == upstream and _required(rows) == ["k2-fsa/OmniVoice"]
       monkeypatch.setenv(FLAG, "voxcpm2")
       defaults.apply_required_default(rows)
       assert _required(rows) == [VOXCPM2]
       monkeypatch.setenv(FLAG, "kittentts")
       defaults.apply_required_default(rows)
       assert _required(rows) == [KITTEN]
       rows = copy.deepcopy(upstream)
       monkeypatch.setenv(FLAG, "sherpa-onnx")  # no catalogue row: left as upstream wrote it
       defaults.apply_required_default(rows)
       assert rows == upstream


   def test_r3_fresh_install_waits_for_engine_and_weights(setup):
       wizard, choose = setup
       choose("voxcpm2", _NotReady)
       status = wizard.setup_status()
       assert status["models_ready"] is False
       assert _missing(status) == [VOXCPM2, "engine:voxcpm2"]
       assert status["missing"][1]["label"] == "Stub engine"


   def test_r4_each_half_alone_is_not_enough(setup):
       wizard, choose = setup
       choose("voxcpm2", _Ready)  # engine installed, weights not downloaded
       assert _missing(wizard.setup_status()) == [VOXCPM2]
       choose("voxcpm2", _NotReady, downloaded={VOXCPM2})  # weights, no engine
       assert _missing(wizard.setup_status()) == ["engine:voxcpm2"]
       choose("voxcpm2", _Ready, downloaded={VOXCPM2})
       status = wizard.setup_status()
       assert status["models_ready"] is True and status["missing"] == []


   def test_r5_another_ready_engine_still_lifts_the_requirement(setup, monkeypatch):
       from services import tts_backend

       wizard, choose = setup
       choose("kittentts", _Ready, downloaded={KITTEN})  # upstream's #3581 rule
       # Only KittenTTS is ready: VoxCPM2 itself is not installed.
       monkeypatch.setattr(tts_backend, "get_backend_class",
                           lambda backend_id: _Ready if backend_id == "kittentts" else _NotReady)
       status = wizard.setup_status()
       assert status["models_ready"] is True and status["missing"] == []


   def test_r6_missing_engine_rules(defaults, monkeypatch):
       from services import tts_backend

       monkeypatch.setattr(tts_backend, "active_backend_id", lambda: "voxcpm2")
       monkeypatch.setattr(tts_backend, "get_backend_class", lambda backend_id: _NotReady)
       assert defaults.missing_default_engine() == []  # flag unset
       monkeypatch.setenv(FLAG, "voxcpm2")
       assert [m["repo_id"] for m in defaults.missing_default_engine()] == ["engine:voxcpm2"]

       def boom(backend_id):
           raise RuntimeError("probe failed")
       monkeypatch.setattr(tts_backend, "get_backend_class", boom)  # doubt keeps the requirement
       assert defaults.missing_default_engine() == [
           {"repo_id": "engine:voxcpm2", "label": "voxcpm2 engine"}
       ]


   def test_r7_status_response_keeps_the_engine_entry(setup):
       from api.schemas import SetupStatusResponse

       wizard, choose = setup
       choose("voxcpm2", _NotReady, downloaded={VOXCPM2})
       response = SetupStatusResponse(**wizard.setup_status())
       assert [m.repo_id for m in response.missing] == ["engine:voxcpm2"]


   def test_r8_recommendations_mark_the_default_engine_required(setup, monkeypatch):
       models = importlib.import_module("api.routers.setup.models")
       wizard, _ = setup
       monkeypatch.setattr(models, "KNOWN_MODELS", wizard.KNOWN_MODELS)
       flags = {m["repo_id"]: m["required"] for m in models.recommendations()["models"]}
       assert flags[VOXCPM2] is True
       assert flags.get("k2-fsa/OmniVoice") is not True


   def test_r9_catalogue_load_applies_the_profile():
       code = (
           "import json, sys; sys.path.insert(0, 'backend');"
           "from services.model_catalogue import KNOWN_MODELS, model_key;"
           "print(json.dumps([model_key(m) for m in KNOWN_MODELS if m.get('required')]))"
       )

       def required_at_load(flag):
           env = {k: v for k, v in os.environ.items() if k != FLAG}
           if flag:
               env[FLAG] = flag
           out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                                capture_output=True, text=True, check=True).stdout
           return json.loads(out.strip().splitlines()[-1])
       assert required_at_load(None) == ["k2-fsa/OmniVoice"]
       assert required_at_load("voxcpm2") == [VOXCPM2]
   ```
   Keep one newline at the end of the file.
5. Run Acceptance and report in the AGENTS-SIDESTACK §4 format, listing every command. Append the report at the very end of this spec under a `## Builder report` heading, and set this lane's tracker status to `running (dsh done)`. The Reviewer notes are for the reviewer: do not run them.

## Acceptance

```powershell
& $py -m pytest tests/test_sidestack_first_run.py -q -p no:cacheprovider   # expect: 9 passed
& $py -m pytest tests/test_setup_status_engine_choice_3581.py tests/test_setup_recommendations.py tests/test_catalogue_packages.py tests/test_install_disk_space.py tests/test_sidestack_defaults.py tests/test_sidestack_ui_refusal.py tests/test_router_smoke.py -q -p no:cacheprovider   # expect: 0 failed
git status --short    # expect: exactly the files in "Files"
Get-ChildItem -Force | Where-Object Name -match '^(pytest-of-|omnivoice-test-data-)'   # expect: nothing
python sidestack/scripts/check_sidestack.py           # expect: OK
```

## Part B — live check (Operator, after approval)

No step may start a download.

1. Start Voice Studio with the worktree launcher, default profile.
2. `GET /setup/status`: `models_ready` is true on this machine (VoxCPM2 installed, weights cached), with no `missing` entries.
3. `GET /setup/recommendations`: `openbmb/VoxCPM2` has `required: true`, and `k2-fsa/OmniVoice` (if listed) does not. `GET /models`: the same `required` flags.
4. `-Stop`, then record the results here.

A fresh install (no engine, no weights) is covered by R3–R4. Simulating one live would need a second data folder and is not part of this lane.

## Out of scope (VS-24)

- The first-run screen's model packs. They are upstream's fixed lists around OmniVoice, NLLB and two sherpa-onnx models, all refused in commercial-only mode.
- An install button for an `engine:` entry on the first-run screen. Today the Advanced view's engine list installs VoxCPM2.
- The engine notice's "Set up" fix. It downloads the required weights (now VoxCPM2's) but does not install the engine.
- `/setup/recommendations`' rationale text, which still says "VoiceStudio (required)".

## Reviewer notes

- **Mutation checks.** Each of these was caught when the lane was written:
  - the catalogue hook replaced by `pass`;
  - other TTS rows keep `required`;
  - the no-row guard removed;
  - the wizard's `missing +=` removed;
  - the "another engine is chosen" early return removed;
  - the "engine is ready" early return removed;
  - a failed probe returning `[]`.
- **Equivalent mutants (not catchable):** removing either function's `if not engine` check. An empty engine id matches no row and is never the chosen engine.
- `tests/test_mobile_contract.py` has 7 baseline failures; its `test_openapi_contract_matches_backend` passes. That is why the schema is unchanged.
- **Checked while writing this lane (2026-11-08):** the spec text was applied to HEAD in a scratch run; R1–R9 and the Acceptance tests passed, and all 7 mutations were caught.

## Builder report

```
LANE: VS-23
STATUS: DONE
FILES CHANGED: backend/sidestack_fork/defaults.py (9117ee4298e0) backend/services/model_catalogue.py (d6ebf991d94b) backend/api/routers/setup/wizard.py (ccf92d838f6f) tests/test_sidestack_first_run.py (260808e7037e) sidestack/lanes/README.md (status row)
COMMANDS RUN: git status --short → 0; Select-String model_catalogue hook → 1 match; Select-String wizard hook → 2 matches (both `cache = hf_cache_dir()`; Step-3 replacement text unique); Test-Path tests\test_sidestack_first_run.py → False; pytest tests/test_sidestack_defaults.py → 6 passed; pytest tests/test_sidestack_first_run.py → 9 passed; pytest tests/test_setup_status_engine_choice_3581.py tests/test_setup_recommendations.py tests/test_catalogue_packages.py tests/test_install_disk_space.py tests/test_sidestack_defaults.py tests/test_sidestack_ui_refusal.py tests/test_router_smoke.py → 72 passed, 0 failed; git status --short → 0 (exactly the Files table); Get-ChildItem residue check → nothing; python sidestack/scripts/check_sidestack.py → OK
NOT DONE / UNSURE: none (Part B is the operator's; no downloads, no app start)
```

## Reviewer verification (2026-11-08)

**Part A PASS.** The builder finished in about 3 minutes with a clean report.
- **Spec match:** all four files match this spec applied to HEAD, byte for byte.
- **Acceptance (re-run by the reviewer):** R1–R9 passed (9); the related setup tests passed (72, 0 failed); no stray test folders; `check_sidestack.py` OK.
- **Mutation checks:** all 7 were caught on the builder's files.
- **Full backend suite** (`-n 8`): 13,056 passed, 93 failed, 20 errors. Every failing id is in the baseline (`pytmp\base.txt`); none is new.
- **Preflight correction:** the builder noted that `^    cache = hf_cache_dir\(\)$` matches twice in `wizard.py`, not once. Step 3's three-line block is unique, so the edit was right. The Preflight line now expects 2 matches.
- Part B is not run yet. It needs real run approval.

## Part B results (Operator, 2026-11-08)

**PASS.** Part A was committed first (da60b6125). It was run together with VS-24 Part B (web UI rebuilt), with the worktree launcher in the default profile.
- **`GET /setup/status`:** `models_ready: true`, no `missing` entries. On this machine VoxCPM2 is installed and its weights are cached.
- **`GET /setup/recommendations`:** `openbmb/VoxCPM2` has `required: true` (installed). `k2-fsa/OmniVoice` has `required: false`, and every other row is `false`.
  - The optional picks still include OmniVoice and `sherpa-onnx-whisper-tiny`, which commercial-only mode refuses. That list is not filtered by licence: a later lane, if it matters.
- **`GET /models`:** the only `required` row is `openbmb/VoxCPM2`; the OmniVoice row is `required: false`. `tts.active` is `voxcpm2`.
- **Nothing downloaded:** the Hugging Face cache stayed at 17 files / 5,042,286,722 bytes, and there were no install jobs.
