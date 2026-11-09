# VS-17 — Measured VRAM floor for VoxCPM2 in the admission gate

- **Phase:** 4
- **Run by:** dsh does Part A (code and offline tests). The Operator does Part B (one live refusal check).
- **Gate:**
  - none for Part A;
  - **real run approval** for Part B: start Voice Studio while ODS's LLM is loaded and send one VoxCPM2 request that the gate should refuse before anything loads.
- **Depends on:** VS-06, VS-15, VS-16
- **Status:** verified (Part B PASS after VS-20, 2026-11-08)

## Goal

The admission gate refuses VoxCPM2 when it cannot fit, instead of letting it load and spill into shared system memory.

**Why:**
- The gate compares an engine's declared VRAM floor plus a 1 GB margin with free VRAM.
- VoxCPM2 declares no floor (`min_vram_gb = 0.0` on both its in-process and sidecar classes), so the gate asks for only 1 GB.
- VS-16 measured the VoxCPM2 sidecar at **6.64 GB** resident on the RTX 5090.
- With ODS's LLM loaded, 4.8–6.9 GB is free (depending on whether ODS Whisper is warm). Today the gate admits VoxCPM2 there.

**Fix:** a SideStack table of measured floors, keyed by engine id, used when it is larger than the declared floor. VoxCPM2 gets **7.0 GB** (6.64 GB rounded up), so the gate asks for 8.0 GB with the margin. Upstream engine classes stay unchanged, which keeps merges cheap.

## Files

| Path | Change |
|---|---|
| `backend/sidestack_fork/admission.py` | edit: `MEASURED_FLOOR_GB`, `effective_floor_gb()`, used in `tts_admission_error` |
| `tests/test_sidestack_admission.py` | edit: add G15–G17 |
| `sidestack/lanes/VS-17-voxcpm2-vram-floor.md`, `sidestack/lanes/README.md` | builder report / status |

## Preflight

Start with the environment block from AGENTS-SIDESTACK.md Hard law 9, run from the worktree root.

```powershell
git status --short     # expect: empty
Select-String backend\sidestack_fork\admission.py -Pattern '^    return admission_error\(selected, getattr\(cls, "min_vram_gb", 0\.0\),$'   # expect: 1 match
Select-String backend\sidestack_fork\admission.py -Pattern '^def required_gb\(min_vram_gb\) -> float:$'   # expect: 1 match
& $py -m pytest tests/test_sidestack_admission.py -q -p no:cacheprovider   # expect: 14 passed
```

## Steps

1. In `backend/sidestack_fork/admission.py`, directly before the line `def required_gb(min_vram_gb) -> float:`, insert (two blank lines after it, as between the other functions):
   ```python
   # Measured resident VRAM for engines that declare no floor (VS-17).
   # VoxCPM2's sidecar held 6.64 GB on an RTX 5090 (VS-16), rounded up.
   MEASURED_FLOOR_GB = {"voxcpm2": 7.0}


   def effective_floor_gb(engine_id, declared) -> float:
       """The larger of the engine's declared floor and SideStack's measured one."""
       try:
           floor = max(0.0, float(declared or 0.0))
       except (TypeError, ValueError):
           floor = 0.0
       return max(floor, MEASURED_FLOOR_GB.get(str(engine_id or ""), 0.0))
   ```
2. In the same file, in `tts_admission_error`, replace these two lines:
   ```python
       return admission_error(selected, getattr(cls, "min_vram_gb", 0.0),
                              resident=is_resident(cls), mem=mem)
   ```
   with:
   ```python
       floor = effective_floor_gb(selected, getattr(cls, "min_vram_gb", 0.0))
       return admission_error(selected, floor, resident=is_resident(cls), mem=mem)
   ```
3. In `tests/test_sidestack_admission.py`, add at the end of the file:
   ```python


   # ── G15–G17: VS-17 measured floors ────────────────────────────────────────
   def test_g15_voxcpm2_measured_floor_refuses_beside_ods(monkeypatch):
       """VoxCPM2 declares no floor; the measured 7 GB applies (8 GB with margin)."""
       sa = _mod(monkeypatch)

       class _Vox:
           min_vram_gb = 0.0
           gpu_compat = ("cuda", "mps", "cpu")

       monkeypatch.setattr(sa, "is_resident", lambda _cls: False)
       msg = sa.tts_admission_error("voxcpm2", _Vox, mem={"vram_free_gb": 6.9})
       assert msg is not None
       assert "need 8.0 GB, have 6.9 GB" in msg
       assert sa.tts_admission_error("voxcpm2", _Vox, mem={"vram_free_gb": 8.0}) is None


   def test_g16_measured_floor_skips_resident_and_other_engines(monkeypatch):
       sa = _mod(monkeypatch)

       class _Eng:
           min_vram_gb = 0.0
           gpu_compat = ("cuda", "cpu")

       monkeypatch.setattr(sa, "is_resident", lambda _cls: True)
       assert sa.tts_admission_error("voxcpm2", _Eng, mem={"vram_free_gb": 0.5}) is None
       monkeypatch.setattr(sa, "is_resident", lambda _cls: False)
       assert sa.tts_admission_error("other-engine", _Eng, mem={"vram_free_gb": 1.5}) is None


   def test_g17_effective_floor(monkeypatch):
       sa = _mod(monkeypatch)
       assert sa.effective_floor_gb("voxcpm2", 0.0) == 7.0
       assert sa.effective_floor_gb("voxcpm2", 9.0) == 9.0
       assert sa.effective_floor_gb("omnivoice", 6.0) == 6.0
       assert sa.effective_floor_gb(None, "bad") == 0.0
   ```
   Keep one newline at the end of the file.
4. Run Acceptance and report in the AGENTS-SIDESTACK §4 format, listing every command. Append the report to this spec under `## Builder report`, and set this lane's tracker status to `running (dsh done)`.

## Acceptance

```powershell
& $py -m pytest tests/test_sidestack_admission.py -q -p no:cacheprovider   # expect: 17 passed
& $py -m pytest tests/test_sidestack_dictation.py tests/test_sidestack_ods_asr.py tests/test_sidestack_ods_provider.py tests/test_sidestack_launcher.py tests/test_structure_doc.py -q -p no:cacheprovider   # expect: 0 failed
git status --short    # expect: exactly the files in "Files"
Get-ChildItem -Force | Where-Object Name -match '^(pytest-of-|omnivoice-test-data-)'   # expect: nothing
python sidestack/scripts/check_sidestack.py           # expect: OK
```

## Part B — live refusal check (Operator, after approval)

ODS's LLM is loaded, as it normally is. Voice Studio is started with the launcher and VoxCPM2 is not loaded.
1. Record `nvidia-smi` memory.used.
2. `POST /generate` with `engine=voxcpm2` and a short synthetic `text`. Expect **503**, with the message "Not enough free GPU memory: need 8.0 GB, have X GB (TTS engine 'voxcpm2') …".
3. Check that no VoxCPM2 sidecar process was spawned and memory.used did not grow beyond Voice Studio's own CUDA context.
4. `-Stop`, then record the result in this spec.

If step 2 returns 200 or starts loading, stop at once (`-Stop`) and report: the gate missed the path.

## Out of scope

- Floors for other engines (CosyVoice 3, MOSS-TTS) until each is measured.
- Gate hooks on dub, batch and audiobook renders (VS-06 covers `/generate`, the TTS socket and `/v1/audio/speech`).
- A launcher "studio mode" that stops and starts `ods-llama-server` (a separate lane if wanted).

## Reviewer notes

- **Mutation checks:**
  - empty `MEASURED_FLOOR_GB` → G15 and G17 fail;
  - revert Step 2 → G15 fails;
  - `max` → `min` in `effective_floor_gb` → G17 fails.
- **Residency:** the gate treats a warm engine as resident (`_ENGINE_INSTANCES` / `_active_instance`). Part B covers the cold refusal only. A warm VoxCPM2 with ODS's LLM restarted behind it is not tested here.
- **Checked while writing this lane (2026-11-06):**
  - `get_backend_class("voxcpm2")` resolves to `VoxCPM2SubprocessBackend` when its venv exists, and to the in-process `VoxCPM2Backend` otherwise. Both have `min_vram_gb` 0.0 and the engine id `voxcpm2`.
  - The gate is called with the engine id in `generation.py` (`tts_admission_error(engine_id, backend_cls)`) and `openai_compat.py`.

## Builder report

```
LANE: VS-17 (Part A)
STATUS: DONE
FILES CHANGED: backend/sidestack_fork/admission.py (sha below), tests/test_sidestack_admission.py (sha below)
COMMANDS RUN:
  git status --short → 0, empty (preflight)
  Select-String admission.py 'return admission_error(selected, getattr(cls, "min_vram_gb", 0.0),' → 0, 1 match
  Select-String admission.py 'def required_gb(min_vram_gb) -> float:' → 0, 1 match
  & $py -m pytest tests/test_sidestack_admission.py -q -p no:cacheprovider → 0, 14 passed (preflight)
  & $py -m pytest tests/test_sidestack_admission.py -q -p no:cacheprovider → 0, 17 passed
  & $py -m pytest tests/test_sidestack_dictation.py tests/test_sidestack_ods_asr.py tests/test_sidestack_ods_provider.py tests/test_sidestack_launcher.py tests/test_structure_doc.py -q -p no:cacheprovider → 0, 35 passed, 0 failed
  git status --short → 0, exactly the two Files
  Get-ChildItem -Force | Where Name -match '^(pytest-of-|omnivoice-test-data-)' → 0, nothing
  & $py sidestack/scripts/check_sidestack.py → 0, OK (again after appending this report: OK, exit 0)
NOT DONE / UNSURE: none (Part B is the operator's live refusal check)
```

## Reviewer verification (Part A, 2026-11-06)

**Result: verified, no code fixes.**
- The diff matches Steps 1–3 exactly. The builder placed its report before "Out of scope"; the reviewer moved it to the end.
- Mutation checks, all caught:
  - empty `MEASURED_FLOOR_GB` → G15, G17;
  - revert Step 2 → G15;
  - `max` → `min` → G9, G15, G17.
- Re-run: SideStack tests + `test_structure_doc` 52 passed.
- **Full suite** (worktree, short TEMP, `-n 8`): 13001 passed, 93 failed, 36 errors. The only new ids are the 11 known `tests/test_no_audio_track.py` order-leak ids (VS-06, VS-15). 4 baseline ids now pass.
- Part B (live refusal) is not run yet; it needs real run approval.

## Part B results (Operator, 2026-11-08, run with VS-19 Part B)

**FAIL.** ODS's LLM was loaded: 25.5 GB used, 6.7 GB free per `nvidia-smi`. A `POST /generate` with `engine=voxcpm2` was admitted, and the sidecar spawned and began loading. The run was stopped at once, and ODS stayed healthy.

- **The floor is right:** the gate needs 8.0 GB.
- **The free-memory reading is wrong:** `torch.cuda.mem_get_info()` reported 27.74 GB free while NVML reported 7.00 GB. Windows CUDA does not count GPU memory used inside WSL, which is where ODS's containers run.
- So the VS-06/VS-15 gate has never seen ODS's memory on this host. Its offline tests pass because they inject `mem`.
- **Fix:** take free VRAM from NVML (the lower of NVML and torch), in a new lane. Details are in VS-19 "Part B results".

## Part B re-run (Operator, 2026-11-08, after VS-20)

**PASS.** With VS-20 in place and ODS's LLM loaded (6,632 MiB free per `nvidia-smi`), `POST /generate` with `engine=voxcpm2` returned 503 "need 8.0 GB, have 6.5 GB". Nothing spawned and GPU memory did not grow. The Design page showed the same message. Details are in VS-20 "Part B results".