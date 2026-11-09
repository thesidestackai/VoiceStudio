# VS-25 — Commercial-only mode in the recommendations

- **Phase:** 4
- **Run by:** dsh does Part A (code and offline tests). The Operator does Part B (one live read, no downloads).
- **Gate:**
  - none for Part A;
  - **real run approval** for Part B.
- **Depends on:** VS-21
- **Status:** verified (Part B PASS, 2026-11-08)

## Goal

With `SIDESTACK_COMMERCIAL_ONLY=1`, `GET /setup/recommendations` leaves out every curated pick that the install route refuses (VS-21). Its download totals count only what is left. Unset, upstream's list is unchanged.

**Why (VS-23 Part B, 2026-11-08):**
- The curated picks still listed `k2-fsa/OmniVoice` and `csukuangfj/sherpa-onnx-whisper-tiny`.
- Three UI paths download from this list: the "Install speech-to-text" button, the recommendations panel's "install" action, and the engine notice's "Set up" fix. A refused pick there ends in a 403.
- `download_gb_remaining` also counted OmniVoice's 2.4 GB.

**Fix:** in `recommendations()`, after `curated` is built, keep only the rows for which `sidestack_fork.licensing.refusal([catalogue key, *dependency repos])` is `None`. That is the same check as the install route (VS-21) and the `/models` rows (VS-22).

## Files

| Path | Change |
|---|---|
| `backend/api/routers/setup/models.py` | edit: filter in `recommendations` |
| `tests/test_sidestack_recommendations.py` | new: C1–C5 |
| `sidestack/lanes/VS-25-recommendations-commercial-only.md`, `sidestack/lanes/README.md` | builder report / status |

## Preflight

Start with the environment block from AGENTS-SIDESTACK.md Hard law 9, run from the worktree root.

```powershell
git status --short     # expect: only this spec (new) and sidestack/lanes/README.md (its row)
Select-String backend\api\routers\setup\models.py -Pattern '^        if _model_curated\(m, tags\) and _model_supported\(m\)$'   # expect: 1 match
Test-Path tests\test_sidestack_recommendations.py   # expect: False
```

## Steps

Each "replace" below names text that occurs exactly once in its file. Keep the file's line endings. Do not run `git checkout`, `git stash`, `git reset`, `git clean` or `git restore`.

1. In `backend/api/routers/setup/models.py`, in `recommendations`, replace:
   ```python
       curated = [
           m for m in KNOWN_MODELS
           if _model_curated(m, tags) and _model_supported(m)
       ]
   ```
   with:
   ```python
       curated = [
           m for m in KNOWN_MODELS
           if _model_curated(m, tags) and _model_supported(m)
       ]
       # SideStack fork (VS-25): commercial-only mode leaves out what the install
       # route refuses (VS-21), so no recommendation leads to a refused download.
       from sidestack_fork.licensing import refusal
       curated = [
           m for m in curated
           if refusal([model_key(m), *(d["repo_id"] for d in m.get("dependencies") or ())]) is None
       ]
   ```
2. Create `tests/test_sidestack_recommendations.py` with exactly this content:
   ```python
   """SideStack VS-25 — commercial-only mode in GET /setup/recommendations.

   With SIDESTACK_COMMERCIAL_ONLY=1, the curated picks leave out every model the
   install route refuses (VS-21), and the download totals count only what is
   left. Unset, upstream's list is unchanged. Nothing is downloaded.
   """
   from __future__ import annotations

   import importlib
   import os
   import sys

   import pytest

   ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
   sys.path.insert(0, os.path.join(ROOT, "backend"))

   os.environ.setdefault("OMNIVOICE_MODEL", "test")
   os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

   pytestmark = pytest.mark.model_licence_gate

   FLAG = "SIDESTACK_COMMERCIAL_ONLY"


   @pytest.fixture
   def models(monkeypatch):
       """The models router with in-memory acceptance records; the flag starts unset."""
       _ss = importlib.import_module("services.settings_store")
       text: dict[str, str] = {}
       monkeypatch.setattr(_ss, "get_text", lambda k, default=None: text.get(k, default))
       monkeypatch.setattr(_ss, "set_text", lambda k, v: text.__setitem__(k, v))
       monkeypatch.setattr(_ss, "get_license_accepted", lambda engine: False)
       monkeypatch.delenv(FLAG, raising=False)
       return importlib.import_module("api.routers.setup.models")


   def _picks(models):
       return {m["repo_id"]: m for m in models.recommendations()["models"]}


   def test_c1_hook_in_place():
       with open(os.path.join(ROOT, "backend", "api", "routers", "setup", "models.py"), encoding="utf-8") as f:
           assert f.read().count("SideStack fork (VS-25)") == 1


   def test_c2_refused_picks_are_left_out(models, monkeypatch):
       off = _picks(models)
       assert "k2-fsa/OmniVoice" in off and "KittenML/kitten-tts-mini-0.8" in off
       monkeypatch.setenv(FLAG, "1")
       on = _picks(models)
       assert "k2-fsa/OmniVoice" not in on
       assert "KittenML/kitten-tts-mini-0.8" in on
       assert set(on) < set(off)
       lic = importlib.import_module("sidestack_fork.licensing")
       assert all(lic.refusal([repo_id]) is None for repo_id in on)
       # Only refused picks were dropped.
       assert all(lic.refusal([repo_id]) is not None for repo_id in set(off) - set(on))


   def test_c3_totals_count_only_what_is_left(models, monkeypatch):
       monkeypatch.setenv(FLAG, "1")
       body = models.recommendations()
       entries = body["models"]
       assert body["total_gb"] == round(sum(m["size_gb"] for m in entries), 2)
       assert body["download_gb_remaining"] == round(
           sum(m["size_gb"] for m in entries if not m["installed"]), 2
       )


   def test_c4_dependencies_count(models, monkeypatch):
       """A commercial pick that depends on a refused model is left out too."""
       kitten = "KittenML/kitten-tts-mini-0.8"
       rows = [
           {**m, "dependencies": [{"repo_id": "k2-fsa/OmniVoice"}]} if m["repo_id"] == kitten else m
           for m in models.KNOWN_MODELS
       ]
       monkeypatch.setattr(models, "KNOWN_MODELS", rows)
       assert kitten in _picks(models)
       monkeypatch.setenv(FLAG, "1")
       assert kitten not in _picks(models)


   def test_c5_catalogue_key_is_the_licence_record(models, monkeypatch):
       """A commercial package inside a non-commercial repo stays recommended."""
       package = next(m for m in models.KNOWN_MODELS if m.get("id") == "audio-cpp/audio.cpp-gguf:dots-tts-soar-q8_0")
       monkeypatch.setattr(models, "KNOWN_MODELS", [*models.KNOWN_MODELS, {**package, "curated_on": ["all"]}])
       monkeypatch.setenv(FLAG, "1")
       assert "audio-cpp/audio.cpp-gguf:dots-tts-soar-q8_0" in _picks(models)
   ```
   Keep one newline at the end of the file.
3. Run Acceptance and report in the AGENTS-SIDESTACK §4 format, listing every command. Append the report at the very end of this spec under a `## Builder report` heading, and set this lane's tracker status to `running (dsh done)`. The Reviewer notes are for the reviewer: do not run them.

## Acceptance

```powershell
& $py -m pytest tests/test_sidestack_recommendations.py -q -p no:cacheprovider   # expect: 5 passed
& $py -m pytest tests/test_setup_recommendations.py tests/test_setup_status_engine_choice_3581.py tests/test_sidestack_first_run.py tests/test_sidestack_ui_refusal.py tests/test_sidestack_downloads.py tests/test_router_smoke.py -q -p no:cacheprovider   # expect: 0 failed
git status --short    # expect: exactly the files in "Files"
Get-ChildItem -Force | Where-Object Name -match '^(pytest-of-|omnivoice-test-data-)'   # expect: nothing
python sidestack/scripts/check_sidestack.py           # expect: OK
```

## Part B — live check (Operator, after approval)

1. Start Voice Studio with the worktree launcher, default profile.
2. `GET /setup/recommendations`:
   - no `k2-fsa/OmniVoice` and no `csukuangfj/sherpa-onnx-whisper-tiny`;
   - VoxCPM2 stays (`required: true`);
   - `download_gb_remaining` equals the sum of the listed picks not installed.
3. `-Stop`, then record the results here. Nothing is downloaded.

## Out of scope

- The engine notice's "Set up" fix. It still downloads only the required weights, not the engine.
- The `rationale` text ("VoiceStudio (required)").

## Reviewer notes

- **Mutation checks.** Each of these was caught when the lane was written:
  - the filter replaced by `if True`;
  - `m["repo_id"]` instead of `model_key(m)`;
  - the dependencies dropped;
  - the condition inverted.
- C4 gives the commercial KittenTTS row a dependency on OmniVoice. A fake row with an unknown repo id would be refused on its own, so it could not show that dependencies count.
- **Live list on this host with the flag on** (2026-11-08):
  - Systran large-v3, deepdml Turbo, KittenTTS, VoxCPM2, CosyVoice 3 and GPT-SoVITS;
  - 21.38 GB in total. The offline run had an empty Hugging Face cache, so all of it counted as "to download". Part B gives the real figure.
- **Checked while writing this lane (2026-11-08):** the spec text was applied to HEAD in a scratch run; C1–C5 and the Acceptance tests passed, and all 4 mutations were caught.

## Builder report

LANE: VS-25
STATUS: DONE
FILES CHANGED: backend/api/routers/setup/models.py (5b0bc45889a0), tests/test_sidestack_recommendations.py (9edc7f618a00), sidestack/lanes/README.md (status cell → running (dsh done)), sidestack/lanes/VS-25-recommendations-commercial-only.md (this report)
COMMANDS RUN:
- Preflight: git status --short (only this spec + README.md), Select-String models.py curated line (1 match), Test-Path tests/test_sidestack_recommendations.py (False) → exit 0, all expectations met
- python -m pytest tests/test_sidestack_recommendations.py -q → exit 0, 5 passed
- python -m pytest tests/test_setup_recommendations.py tests/test_setup_status_engine_choice_3581.py tests/test_sidestack_first_run.py tests/test_sidestack_ui_refusal.py tests/test_sidestack_downloads.py tests/test_router_smoke.py -q → exit 0, 62 passed, 0 failed
- git status --short (post) → exit 0, only the 4 allowed changes
- Get-ChildItem temp residue → none
- python sidestack/scripts/check_sidestack.py → OK: 14 required files, 24 lane specs, links, manifest, env profile, secret scan
NOT DONE / UNSURE: Part B (live read) is the Operator's; not started, nothing downloaded. NOTE: the spec's Step 1 code block is indented one level deeper (8/12/12/8) than the file's actual indentation (4/8/8/4) for `recommendations()`; the block was inserted at the file's real indentation so it lands as valid Python inside the 4-space function body — the code content, relative structure and comment are exactly as specified.

## Reviewer verification (2026-11-08)

**Part A PASS.** The builder finished in under 6 minutes with a clean report.
- **Spec match:** both files match this spec applied to HEAD, byte for byte.
- **The builder's indentation note:** it read the Step 1 block as one level too deep. The extra spaces are the Markdown list indent; the inserted code is exactly what the spec meant.
- **Mutation checks:** all 4 were caught on the builder's files.
- **Full backend suite** (`-n 8`): 13,048 passed, 94 failed, 31 errors. Every failing id is in the baseline except the known order-dependent ones:
  - 11 `test_no_audio_track` ids;
  - the `test_relock_cache_identity` sweep flake.
  Run alone, those two files give 11 passed, 11 skipped, 0 failed.
- Part B is not run yet. It needs real run approval.

## Part B results (Operator, 2026-11-08)

**PASS.** Part A was committed first (93f2e4c7c). Voice Studio was started with the worktree launcher in the default profile.
- **`GET /setup/recommendations`** lists six picks:
  - Systran faster-whisper-large-v3, 2.9 GB;
  - deepdml large-v3 Turbo, 1.6 GB;
  - KittenTTS, installed;
  - VoxCPM2, `required: true`, installed;
  - CosyVoice 3, 9.8 GB;
  - GPT-SoVITS, 2 GB.
- There is no `k2-fsa/OmniVoice` and no `csukuangfj/sherpa-onnx-whisper-tiny`.
- **Totals:** `download_gb_remaining` is 16.3, which equals the sum of the picks not installed. `total_gb` is 21.38.
- **Nothing downloaded:** no install jobs, and the Hugging Face cache stayed at 17 files / 5,042,286,722 bytes.
- `-Stop` stopped the server.
