# VS-06 — GPU admission gate for TTS loads beside ODS

- **Phase:** 2
- **Run by:** dsh
- **Gate:** none (code + offline tests; the reviewer reads free VRAM locally, which needs no ODS contact)
- **Depends on:** VS-05
- **Status:** verified (attempt 2)

## Goal

When ODS has its LLM loaded on the shared RTX 5090, Voice Studio refuses to **start** a TTS engine
load that would not fit. The check is the engine's declared VRAM floor plus a 1 GB margin against
free VRAM. Instead of paging to system RAM or running out of memory, it answers with
"Not enough GPU memory while ODS is loaded: need X GB, have Y GB". It never unloads ODS models
(ARCHITECTURE §4 rule 2).

Upstream's own memory check (`services/memory_budget.py`) is advisory by design, and its
`check_gpu_admission` is a queue check, not a VRAM check. So the gate is a new SideStack module.
It is **opt-in**: it is active only when `SIDESTACK_VRAM_ADMISSION=1`, which the SideStack env
profile sets. With the variable unset, upstream behaviour is unchanged.

## Files

| Path | Change |
|---|---|
| `backend/sidestack_fork/__init__.py` | create: one line, `"""SideStack fork additions; kept out of upstream packages (see VS-06)."""` |
| `backend/sidestack_fork/admission.py` | create: the exact code in step 1 |
| `backend/api/routers/generation.py` | edit: insert the step 2 block (anchor below) |
| `backend/api/routers/tts_stream.py` | edit: insert the step 3 block (anchor below) |
| `sidestack/config/ods.env.example` | edit: add the step 4 lines |
| `tests/test_sidestack_admission.py` | create: tests G1–G11 (step 5) |

Only these files may change. Anything else in `git status` fails the lane.

**Why not `backend/services/`:** attempt 1 put the module there. That made upstream
`tests/test_structure_doc.py::test_service_count_matches_the_tree` fail, because `docs/STRUCTURE.md`
pins the number of service modules at 116. Bumping that upstream line would conflict on every
upstream sync that adds a service. SideStack code that is not a patch to an upstream file lives in
`backend/sidestack_fork/`, a package name that no upstream test or doc counts.

## Attempt 2 — rework (builder runs this section instead of Preflight/Steps)

The worktree still holds attempt 1's uncommitted changes. Start with the environment block from
AGENTS-SIDESTACK.md Hard law 9.

1. **Preflight.** `git status --short` must show exactly these lines, in any order. Otherwise report BLOCKED:
   ```
    M backend/api/routers/generation.py
    M backend/api/routers/tts_stream.py
    M sidestack/config/ods.env.example
   ?? backend/services/sidestack_admission.py
   ?? tests/test_sidestack_admission.py
   ```
2. Create `backend/sidestack_fork/__init__.py` with the one line from the Files table. Create
   `backend/sidestack_fork/admission.py` with **exactly** the content of
   `backend/services/sidestack_admission.py`, using a byte copy (`Copy-Item`), not retyped. Check
   that both files have the same SHA-256, then delete `backend/services/sidestack_admission.py`.
3. In `generation.py` and `tts_stream.py`, change only the hook's import line to
   `from sidestack_fork.admission import tts_admission_error`.
4. In `tests/test_sidestack_admission.py`, change only the import target to
   `importlib.import_module("sidestack_fork.admission")`.
5. Run the Acceptance commands below, plus:
   ```powershell
   & $py -m pytest tests/test_structure_doc.py -q -p no:cacheprovider    # expect: 0 failed
   Test-Path backend\services\sidestack_admission.py                     # expect: False
   ```

## Preflight (attempt 1)

Start with the environment block from AGENTS-SIDESTACK.md Hard law 9, run from the worktree root.

```powershell
git status --short     # expect: empty
Select-String backend\api\routers\generation.py -Pattern 'log_if_low\(f"TTS load \(\{engine_id\}\)"\)'          # expect: 1 match
Select-String backend\api\routers\tts_stream.py -Pattern "log_if_low\(f`"TTS stream load"                     # expect: 1 match
Select-String backend\services\tts_backend.py -Pattern '^_ENGINE_INSTANCES|^_active_instance:'                 # expect: 2 matches
& $py -m pytest tests/test_generate_engine.py tests/test_generate_streaming.py tests/test_engine_memory.py tests/test_engine_load_failure_2298.py tests/test_generation_failure_diagnostics.py -q -p no:cacheprovider   # expect: 54 passed
```

## Steps

1. Create `backend/sidestack_fork/admission.py` with exactly this content (attempt 1 created it at `backend/services/sidestack_admission.py`):
   ```python
   """SideStack fork (VS-06): GPU admission gate for TTS loads beside ODS.

   ODS keeps its LLM (and Whisper) resident on the same GPU. Before Voice Studio
   loads a TTS engine, compare the engine's declared VRAM floor plus a margin with
   free VRAM, and refuse with a clear message instead of paging or running out of
   memory. Never evicts or unloads ODS models: that is the user's call.

   Opt-in: active only when SIDESTACK_VRAM_ADMISSION=1 (set by the SideStack env
   profile). Unset, upstream behaviour is unchanged. Never raises.
   """
   from __future__ import annotations

   import os
   from typing import Optional

   ENV_FLAG = "SIDESTACK_VRAM_ADMISSION"
   MARGIN_ENV = "SIDESTACK_VRAM_MARGIN_GB"
   DEFAULT_MARGIN_GB = 1.0
   _ON = {"1", "true", "yes", "on"}


   def enabled() -> bool:
       return os.environ.get(ENV_FLAG, "").strip().lower() in _ON


   def margin_gb() -> float:
       try:
           value = float(os.environ.get(MARGIN_ENV, DEFAULT_MARGIN_GB))
       except (TypeError, ValueError):
           return DEFAULT_MARGIN_GB
       return value if value >= 0 else DEFAULT_MARGIN_GB


   def required_gb(min_vram_gb) -> float:
       try:
           floor = max(0.0, float(min_vram_gb or 0.0))
       except (TypeError, ValueError):
           floor = 0.0
       return floor + margin_gb()


   def is_resident(backend_cls) -> bool:
       """Whether this engine's model already lives in this process (warm).

       A warm engine needs no new VRAM, so the gate must not refuse it."""
       try:
           from services import tts_backend
           if backend_cls is tts_backend.OmniVoiceBackend:
               import services.model_manager as mm
               return getattr(mm, "model", None) is not None
           if backend_cls in tts_backend._ENGINE_INSTANCES:
               return True
           return isinstance(tts_backend._active_instance, backend_cls)
       except Exception:  # noqa: BLE001 — unknown residency: fall through to the check
           return False


   def admission_error(engine_id: str, min_vram_gb, *, resident: bool,
                       mem: Optional[dict] = None) -> Optional[str]:
       """The refusal message, or None when the load may proceed."""
       if not enabled() or resident:
           return None
       if mem is None:
           try:
               from services.memory_budget import available_memory
               mem = available_memory()
           except Exception:  # noqa: BLE001
               return None
       free = mem.get("vram_free_gb")
       if free is None:
           return None  # no CUDA GPU: nothing to guard
       need = required_gb(min_vram_gb)
       if float(free) >= need:
           return None
       return (
           f"Not enough GPU memory while ODS is loaded: need {need:.1f} GB, "
           f"have {float(free):.1f} GB (TTS engine '{engine_id}'). Choose a smaller "
           "or CPU engine, or switch ODS to 64k context first. Voice Studio never "
           "unloads ODS models."
       )


   def tts_admission_error(engine_id: Optional[str], backend_cls=None, *,
                           mem: Optional[dict] = None) -> Optional[str]:
       """Route-level entry: resolve the engine, then check. Never raises."""
       if not enabled():
           return None
       try:
           from services import tts_backend
           selected = engine_id or tts_backend.active_backend_id()
           cls = backend_cls or tts_backend.get_backend_class(selected)
       except Exception:  # noqa: BLE001 — let the normal path report bad engine ids
           return None
       return admission_error(selected, getattr(cls, "min_vram_gb", 0.0),
                              resident=is_resident(cls), mem=mem)
   ```
2. **`generation.py`.** Find the `try:` block that calls `log_if_low(f"TTS load ({engine_id})")` and ends with `except Exception:` / `pass`. Directly after that block, before the comment line `# VRAM eviction runs in get_model()'s warm-return path now, so every`, insert (4-space indent, one blank line before and after):
   ```python
       # SideStack fork (VS-06): refuse a TTS load that would not fit beside ODS.
       # Runs after the single-engine eviction above, so only ODS and this
       # engine count. Opt-in via SIDESTACK_VRAM_ADMISSION; a no-op upstream.
       from sidestack_fork.admission import tts_admission_error
       _admission = tts_admission_error(engine_id, backend_cls)
       if _admission:
           raise HTTPException(status_code=503, detail=_admission)
   ```
3. **`tts_stream.py`.** Find the `try:` block that calls `log_if_low(f"TTS stream load ({engine_id or 'active engine'})")` and ends with `except Exception:` / `pass`. Directly after it, before the line `from services.tts_backend import engine_in_use`, insert (16-space indent):
   ```python
                   # SideStack fork (VS-06): GPU admission gate before any load.
                   # The default path loads the core inside _resolve_stream_backend.
                   from sidestack_fork.admission import tts_admission_error
                   _admission = tts_admission_error(engine_id)
                   if _admission:
                       await websocket.send_json({"type": "error", "detail": _admission})
                       continue
   ```
   This follows the existing error-frame-then-`continue` pattern; `lease.close()` still runs in the `finally`.
4. **`ods.env.example`.** After the `OMNIVOICE_SERVER_MODE=1` line, add:
   ```
   
   # ── GPU admission (VS-06): refuse TTS loads that would not fit beside ODS ─────────────────
   SIDESTACK_VRAM_ADMISSION=1
   SIDESTACK_VRAM_MARGIN_GB=1.0
   ```
5. **`tests/test_sidestack_admission.py`.**
   - Put `backend/` on `sys.path` the same way `tests/test_sidestack_ods_asr.py` lines 17–20 do.
   - Import the module inside each test with `importlib.import_module("sidestack_fork.admission")`.
   - Clear `SIDESTACK_VRAM_ADMISSION` and `SIDESTACK_VRAM_MARGIN_GB` with `monkeypatch.delenv(..., raising=False)` in an autouse fixture.
   - Pass `mem=` explicitly in every test, so none of them reads the real GPU.
   - Tests:
     - **G1** Gate off (env unset): `admission_error("x", 6.0, resident=False, mem={"vram_free_gb": 0.5})` is None.
     - **G2** On, `resident=True`, free 0.5, floor 6.0: None.
     - **G3** On, `mem={"ram_available_gb": 8.0}` (no `vram_free_gb`): None.
     - **G4** On, floor 6.0, free 5.0: the message contains `need 7.0 GB, have 5.0 GB` and `ODS`.
     - **G5** On, floor 6.0, free 7.0: None (exactly at the requirement passes).
     - **G6** On, floor 0.0: free 0.5 is refused (`need 1.0 GB`), and free 1.5 gives None.
     - **G7** On, `SIDESTACK_VRAM_MARGIN_GB=2.5`, floor 2.0, free 4.0: refused with `need 4.5 GB`. With the margin `abc`, `margin_gb() == 1.0`; with `-3`, `margin_gb() == 1.0`.
     - **G8** Residency:
       - With `monkeypatch.setattr(services.model_manager, "model", object())`, `is_resident(tts_backend.OmniVoiceBackend)` is True; with `None` it is False.
       - For a local `class _Dummy: pass`, it is False, and True after `monkeypatch.setitem(tts_backend._ENGINE_INSTANCES, _Dummy, object())`.
     - **G9** On, `tts_admission_error("no-such-engine", mem={"vram_free_gb": 0.1})` is None (bad ids are left to the normal path). With `backend_cls` set to a local class with `min_vram_gb = 6.0` (not cached anywhere) and free 2.0, the message contains `need 7.0 GB`.
     - **G10** Hooks present: the text of `backend/api/routers/generation.py` and of `backend/api/routers/tts_stream.py` each contains `tts_admission_error(` and `SideStack fork (VS-06)`.
     - **G11** The profile turns the gate on. Parse `sidestack/config/ods.env.example` the way `_profile()` in `tests/test_sidestack_ods_asr.py` does (KEY=VALUE, skip `#` and blank lines): `SIDESTACK_VRAM_ADMISSION == "1"` and `SIDESTACK_VRAM_MARGIN_GB == "1.0"`.

## Acceptance

```powershell
# (environment block from AGENTS-SIDESTACK Hard law 9 first)
& $py -m pytest tests/test_sidestack_admission.py -q -p no:cacheprovider          # expect: 11 passed
& $py -m pytest tests/test_generate_engine.py tests/test_generate_streaming.py tests/test_engine_memory.py tests/test_engine_load_failure_2298.py tests/test_generation_failure_diagnostics.py -q -p no:cacheprovider   # expect: 54 passed
& $py -m pytest tests/test_sidestack_ods_asr.py tests/test_sidestack_ods_provider.py -q -p no:cacheprovider   # expect: 11 passed
git status --short    # expect: M generation.py, M tts_stream.py, M ods.env.example, ?? backend/sidestack_fork/, ?? tests/test_sidestack_admission.py
python sidestack/scripts/check_sidestack.py           # expect: OK
```

The reviewer also:
- mutation-checks the tests: drop `if float(free) >= need` → G5 and G6 fail; return None for `resident` always False → G2 fails; delete the `generation.py` hook → G10 fails; set the profile to `SIDESTACK_VRAM_ADMISSION=0` → G11 fails;
- runs the full suite (a short TEMP) and compares it with the VS-02 ids;
- reads the real `available_memory()` once, locally, and records what the gate would answer for `omnivoice` (6.0 GB floor) right now. This needs no ODS contact and loads no model.

## Out of scope

- Loading any TTS model, downloading weights, and starting the backend.
- Unloading or evicting anything in ODS.
- **Known gaps, recorded for VS-09:**
  - Dub, audiobook and batch renders do not pass through these two routes.
  - An engine instance whose weights an idle sweeper unloaded still counts as resident, so the gate fails open.
  - On the streaming path, VRAM held by another Voice Studio engine that would be evicted later counts as used.
- A relay `/v1/models` check before LLM calls. LLM errors already surface per call, and VS-07's launcher runs `Test-VoiceStudioOds.ps1` before start-up.

## Reviewer notes

**Attempt 1, 2026-11-06: FAIL (a spec design error, not a builder error).**

- **Builder (dsh on ODS, full access):** finished in 2 m 46 s and about 495k tokens, and reported DONE.
  - The module was byte-identical to step 1, and both hooks sat exactly at their anchors.
  - Tests: 11, 54 and 11 passed. The reviewer's re-run matched.
- **Mutation checks:** all caught.
  - Drop the free≥need pass: G5 and G6 failed.
  - Ignore residency: G2 failed.
  - Delete the generation hook: G10 failed.
  - Profile gate set to 0: G11 failed.
- **Full suite:** 12900 passed, 94 failed, 20 errors. One id was new against VS-02: `tests/test_structure_doc.py::test_service_count_matches_the_tree` (doc says 116, tree has 117).
  - Fix: the module moves to `backend/sidestack_fork/` (attempt 2 section above).
  - Two baseline `test_profile_delete_regression` ids passed this time, which looks flaky.
- **Residue:** 12 `omnivoice-test-data-*` folders in the worktree root were removed (56 files, 4 MB of upstream test fixtures). They dated from VS-02 attempt 1 and the VS-04 run, not VS-06, and were missed then because `git status` does not show them. VS-06's temp files correctly went to `sidestack\work\tmp`.
- **Live VRAM read (local, no model load):** 28.07 GB free of 31.84 GB, so the ODS LLM was not resident at that moment (it was 7.4 GB free in the morning). Probably an idle unload; ODS was not inspected. The gate admits both `omnivoice` (needs 7.0 GB) and 0-floor engines.
  - **Open design issue:** while ODS's LLM is unloaded, the gate can admit a large engine whose VRAM ODS later needs to reload its LLM. The gate protects Voice Studio's loads, not ODS's reloads.
  - A reserve (for example, require `free − ODS footprint ≥ need` when the relay reports the model as not loaded) needs a design decision. It is recorded for VS-09 and not changed here.
  - **Decided in VS-15 (2026-11-06): Voice Studio first, no reserve.** See PLAN.md decision D3.

**Attempt 2, 2026-11-06: PASS.**

- **Builder (dsh on ODS, full access, fresh session):** finished in 1 m 37 s and about 549k tokens, and reported DONE.
  - It ran only the rework section. `backend/sidestack_fork/admission.py` is a byte copy (SHA-256 `8FB59EE2C34D` before and after), and the old file is deleted.
  - Only the two hook import lines and the test's import target changed.
  - `__init__.py` holds the one specified line.
- **Reviewer:**
  - Diff: both hooks are exactly the step 2/3 blocks with the new import.
  - Tests: `test_structure_doc` + `test_sidestack_admission` gave 14 passed.
  - Mutation checks, re-run on the new path: all four were caught again (G5+G6, G2, G10, G11), and the files were restored by SHA-256.
  - `api.routers.generation` and `api.routers.tts_stream` import cleanly with the gate.
  - No residue in the worktree root.
- **Full suite:** 12890 passed, 93 failed, 31 errors in 763 s. `test_service_count_matches_the_tree` passes now.
  - The 11 new ids are all `tests/test_no_audio_track.py`. They are a test-order leak, not VS-06:
    - An `ffprobe.exe` shim left in the xdist worker's shared test data dir by `test_media_tool_missing.py` (already on the VS-02 list) pointed into another test's deleted `tmp_path`, so these tests hit `FileNotFoundError` on a dangling link.
    - Run alone, serially and with `-n 8`, the file gives 4 passed and 11 skipped (no ffmpeg on Windows), as in the baseline.
    - It depends on how xdist schedules tests, so later lanes should treat `test_no_audio_track` ids as baseline noise when that shim leak is present.
  - The 2 `test_profile_delete_regression` baseline ids passed again, which looks flaky.
- **Open for a decision (VS-09 or a follow-up):** reserve VRAM for an idle-unloaded ODS LLM (see attempt 1).
- **Context (user-reported, 2026-11-06):** the user was recording a meeting in SideStack Meetings, which shares ODS, during these runs. That plausibly explains:
  - the slow full suites (763–855 s, against 383 s in VS-02);
  - the 28 GB-free reading, which is a moment of a GPU shared with live Meetings work, not a steady state.

  The pass/fail verdicts stand, because every gate test is offline and passes `mem=` explicitly. The ODS-reload question above still needs measuring on an idle system.
