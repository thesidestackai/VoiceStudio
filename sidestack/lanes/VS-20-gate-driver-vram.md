# VS-20 — The admission gate counts ODS's GPU memory (NVML)

- **Phase:** 4
- **Run by:** dsh does Part A (code and offline tests). The Operator does Part B (live refusal check, which also closes VS-17 Part B).
- **Gate:**
  - none for Part A;
  - **real run approval** for Part B: start `ods-llama-server` (it was left stopped on 2026-11-08), start Voice Studio, and send one VoxCPM2 request that must be refused before anything loads.
- **Depends on:** VS-06, VS-15, VS-17
- **Status:** verified (Part B PASS, 2026-11-08)

## Goal

The admission gate sees the GPU memory ODS uses, so it refuses VoxCPM2 while ODS's LLM is loaded.

**Why (VS-17 Part B, 2026-11-08):**
- The gate takes free VRAM from upstream's `services.memory_budget.available_memory()`, which calls `torch.cuda.mem_get_info()`.
- On this Windows host that call does not count GPU memory used inside WSL, where ODS's containers run. With ODS's LLM loaded, torch reported **27.74 GB free** while NVML and `nvidia-smi` reported **7.00 GB**.
- So the gate admitted VoxCPM2, and its sidecar began loading beside the LLM.

**Fix:** when the gate takes a live reading, it also asks the NVIDIA driver (NVML, the `nvidia-ml-py` package, already a dependency) and uses the **lower** of the two free figures.
- The change is in the fork module only. Upstream's `available_memory()` stays unchanged, so other upstream callers keep their behaviour.
- Readings injected through `mem=` (tests, and callers that already measured) are used as given.
- If NVML is missing or fails, or the host has more than one GPU, the torch figure stands. On a multi-GPU host the NVML index may not be torch's device. This host has one GPU.

## Files

| Path | Change |
|---|---|
| `backend/sidestack_fork/admission.py` | edit: `nvml_free_gb()`, `with_driver_free()`, used in `admission_error` for live readings |
| `tests/test_sidestack_admission.py` | edit: add G18–G21 |
| `sidestack/lanes/VS-20-gate-driver-vram.md`, `sidestack/lanes/README.md` | builder report / status |

## Preflight

Start with the environment block from AGENTS-SIDESTACK.md Hard law 9, run from the worktree root.

```powershell
git status --short     # expect: empty
Select-String backend\sidestack_fork\admission.py -Pattern '^def admission_error\(engine_id: str, min_vram_gb, \*, resident: bool,$'   # expect: 1 match
Select-String backend\sidestack_fork\admission.py -Pattern '^            mem = available_memory\(\)$'   # expect: 1 match
& $py -c "import pynvml; print('pynvml ok')"   # expect: pynvml ok
& $py -m pytest tests/test_sidestack_admission.py -q -p no:cacheprovider   # expect: 17 passed
```

## Steps

1. In `backend/sidestack_fork/admission.py`, directly before the line `def admission_error(engine_id: str, min_vram_gb, *, resident: bool,`, insert (two blank lines after it, as between the other functions):
   ```python
   def nvml_free_gb() -> Optional[float]:
       """Free VRAM as the NVIDIA driver counts it (NVML), or None when unknown.

       On Windows, torch.cuda.mem_get_info() does not count GPU memory used inside
       WSL, where ODS runs, so it can report a nearly empty GPU (VS-20). Only a
       single-GPU host is read: with several GPUs the NVML index may not be
       torch's device, so the torch figure stands.
       """
       try:
           import pynvml
       except Exception:  # noqa: BLE001 — nvidia-ml-py missing: keep the torch figure
           return None
       try:
           pynvml.nvmlInit()
       except Exception:  # noqa: BLE001 — no NVIDIA driver
           return None
       try:
           if pynvml.nvmlDeviceGetCount() != 1:
               return None
           info = pynvml.nvmlDeviceGetMemoryInfo(pynvml.nvmlDeviceGetHandleByIndex(0))
           return info.free / (1024 ** 3)
       except Exception:  # noqa: BLE001
           return None
       finally:
           try:
               pynvml.nvmlShutdown()
           except Exception:  # noqa: BLE001
               pass


   def with_driver_free(mem: dict) -> dict:
       """mem with vram_free_gb lowered to NVML's figure when NVML sees less free."""
       free = mem.get("vram_free_gb")
       if free is None:
           return mem  # no CUDA GPU: nothing to guard
       driver = nvml_free_gb()
       if driver is None or driver >= float(free):
           return mem
       return {**mem, "vram_free_gb": round(driver, 2)}
   ```
2. In the same file, in `admission_error`, replace these three lines:
   ```python
               mem = available_memory()
           except Exception:  # noqa: BLE001
               return None
   ```
   with:
   ```python
               mem = available_memory()
           except Exception:  # noqa: BLE001
               return None
           # VS-20: torch misses GPU memory used inside WSL (ODS); ask the driver too.
           mem = with_driver_free(mem)
   ```
   The new lines stay inside the `if mem is None:` block (8 spaces), so an injected `mem=` is used as given. Change nothing else in that file.
3. In `tests/test_sidestack_admission.py`, add at the end of the file:
   ```python


   # ── G18–G21: VS-20 driver (NVML) free VRAM ─────────────────────────────────
   class _FakeNvml:
       def __init__(self, free_gib=7.5, count=1, fail_init=False):
           self.free = int(free_gib * 1024 ** 3)
           self.count = count
           self.fail_init = fail_init
           self.shutdowns = 0

       def nvmlInit(self):
           if self.fail_init:
               raise RuntimeError("no NVIDIA driver")

       def nvmlShutdown(self):
           self.shutdowns += 1

       def nvmlDeviceGetCount(self):
           return self.count

       def nvmlDeviceGetHandleByIndex(self, index):
           return ("gpu", index)

       def nvmlDeviceGetMemoryInfo(self, handle):
           class _Info:
               free = self.free
           return _Info()


   def test_g18_driver_figure_lowers_torch_figure(monkeypatch):
       sa = _mod(monkeypatch)
       monkeypatch.setattr(sa, "nvml_free_gb", lambda: 7.0)
       mem = {"vram_free_gb": 27.74, "ram_free_gb": 17.1}
       assert sa.with_driver_free(mem) == {"vram_free_gb": 7.0, "ram_free_gb": 17.1}


   def test_g19_torch_figure_kept_when_driver_sees_more_or_nothing(monkeypatch):
       sa = _mod(monkeypatch)
       monkeypatch.setattr(sa, "nvml_free_gb", lambda: 30.0)
       assert sa.with_driver_free({"vram_free_gb": 27.74}) == {"vram_free_gb": 27.74}
       monkeypatch.setattr(sa, "nvml_free_gb", lambda: None)
       assert sa.with_driver_free({"vram_free_gb": 27.74}) == {"vram_free_gb": 27.74}
       monkeypatch.setattr(sa, "nvml_free_gb", lambda: 7.0)
       assert sa.with_driver_free({"vram_free_gb": None}) == {"vram_free_gb": None}


   def test_g20_live_reading_refuses_beside_ods(monkeypatch):
       """The VS-17 Part B case: torch says 27.74 GB free, the driver 7.0 GB."""
       sa = _mod(monkeypatch)
       mb = importlib.import_module("services.memory_budget")
       monkeypatch.setattr(mb, "available_memory", lambda: {"vram_free_gb": 27.74})
       monkeypatch.setattr(sa, "nvml_free_gb", lambda: 7.0)
       msg = sa.admission_error("voxcpm2", 7.0, resident=False)
       assert msg is not None
       assert "need 8.0 GB, have 7.0 GB" in msg
       # An injected reading is used as given.
       assert sa.admission_error("voxcpm2", 7.0, resident=False, mem={"vram_free_gb": 27.74}) is None


   def test_g21_nvml_free_gb(monkeypatch):
       sa = _mod(monkeypatch)
       fake = _FakeNvml(free_gib=7.5)
       monkeypatch.setitem(sys.modules, "pynvml", fake)
       assert sa.nvml_free_gb() == pytest.approx(7.5)
       assert fake.shutdowns == 1
       monkeypatch.setitem(sys.modules, "pynvml", _FakeNvml(count=2))
       assert sa.nvml_free_gb() is None
       monkeypatch.setitem(sys.modules, "pynvml", _FakeNvml(fail_init=True))
       assert sa.nvml_free_gb() is None
   ```
   Keep one newline at the end of the file.
4. Run Acceptance and report in the AGENTS-SIDESTACK §4 format, listing every command. Append the report at the very end of this spec under a `## Builder report` heading, and set this lane's tracker status to `running (dsh done)`.

## Acceptance

```powershell
& $py -m pytest tests/test_sidestack_admission.py -q -p no:cacheprovider   # expect: 21 passed
& $py -m pytest tests/test_sidestack_defaults.py tests/test_sidestack_licensing.py tests/test_sidestack_dictation.py tests/test_sidestack_launcher.py tests/test_structure_doc.py -q -p no:cacheprovider   # expect: 0 failed
& $py -c "import sys; sys.path.insert(0, 'backend'); import sidestack_fork.admission as a; print('nvml free GB', a.nvml_free_gb())"   # expect: a number (read-only NVML query; record it)
git status --short    # expect: exactly the files in "Files"
Get-ChildItem -Force | Where-Object Name -match '^(pytest-of-|omnivoice-test-data-)'   # expect: nothing
python sidestack/scripts/check_sidestack.py           # expect: OK
```

## Part B — live refusal (Operator, after approval)

1. `docker start ods-llama-server` and wait until it is healthy. Record `nvidia-smi` memory.used and memory.free.
2. Start Voice Studio with the launcher. VoxCPM2 is the default engine (VS-19).
3. `POST /generate` with `engine=voxcpm2` and short synthetic text → **503**, with "Not enough free GPU memory: need 8.0 GB, have X GB (TTS engine 'voxcpm2') …". X should be close to `nvidia-smi`'s free figure.
4. Check that no VoxCPM2 sidecar process spawned and that memory.used did not grow beyond Voice Studio's own CUDA context. If anything starts loading, `-Stop` at once and report.
5. Try once from the Design page, and record the message the UI shows.
6. `-Stop`. Record the results here and in VS-17, and set VS-17 to verified if step 3 passed.

## Out of scope

- Upstream's own users of `available_memory()` and its GPU pool sizing (the "GPU pool sized … 27.8 GB free" log line). They keep the torch figure.
- Multi-GPU hosts (the torch figure stands there).
- Gate hooks on dub, batch and audiobook renders.

## Reviewer notes

- **Mutation checks:**
  - delete the Step 2 `with_driver_free` line → G20 fails;
  - `driver >= float(free)` → `driver <= float(free)` → G18 and G19 fail;
  - delete the `nvmlDeviceGetCount() != 1` check → G21 fails.
- G20 is the regression test for VS-17 Part B: the figures are the ones measured live on 2026-11-08.
- NVML is read in the main process. It needs no CUDA context and does not allocate GPU memory.
- **Checked while writing this lane (2026-11-08):**
  - `nvidia-ml-py>=13.0` is in `pyproject.toml`, and `import pynvml` works in the Voice Studio venv;
  - no other fork module reads free VRAM.

## Builder report

```
LANE: VS-20 (Part A)
STATUS: DONE
FILES CHANGED: backend/sidestack_fork/admission.py (fb19c1c69e1d), tests/test_sidestack_admission.py (8b42283fcce3)
COMMANDS RUN:
  Preflight (Hard law 9 block, worktree root):
    git status --short → exit 0 (empty, as expected)
    Select-String admission.py '^def admission_error\(engine_id: str, min_vram_gb, \*, resident: bool,$' → 1 match (as expected)
    Select-String admission.py '^            mem = available_memory\(\)$' → 1 match (as expected)
    & $py -c "import pynvml; print('pynvml ok')" → exit 0, printed "pynvml ok"
    & $py -m pytest tests/test_sidestack_admission.py -q -p no:cacheprovider → exit 0, 17 passed
  Steps 1-4: file edits only (no commands).
  Acceptance (Hard law 9 block, worktree root):
    & $py -m pytest tests/test_sidestack_admission.py -q -p no:cacheprovider → exit 0, 21 passed
    & $py -m pytest tests/test_sidestack_defaults.py tests/test_sidestack_licensing.py tests/test_sidestack_dictation.py tests/test_sidestack_launcher.py tests/test_structure_doc.py -q -p no:cacheprovider → exit 0, 39 passed
    & $py -c "import sys; sys.path.insert(0, 'backend'); import sidestack_fork.admission as a; print('nvml free GB', a.nvml_free_gb())" → exit 0, printed "nvml free GB 6.826602935791016" (6.83, not None)
    git status --short → exit 0, only the two code files modified; no pytest-of- or omnivoice-test-data- folders in the worktree root
    & $py sidestack/scripts/check_sidestack.py → exit 0, "OK: 14 required files, 19 lane specs, links, manifest, env profile, secret scan"
NOT DONE / UNSURE: Part B (live refusal check; closes VS-17 Part B) is the operator's — not started, as instructed.
```

## Reviewer verification (Part A, 2026-11-08)

- **Builder:** it finished in under 15 minutes.
  - `admission.py` matches the spec applied to HEAD exactly.
  - The test file had one extra blank line after the G18–G21 comment. The reviewer removed it, and the file now matches exactly.
- **Acceptance re-run (Hard law 9 environment):**
  - `test_sidestack_admission.py`: 21 passed;
  - defaults, licensing, dictation, launcher and structure doc: 39 passed.
  - The builder's real NVML read gave 6.83 GB free with ODS's LLM loaded. In the reviewer's dry run before the build, NVML gave 6.63 GB while `nvidia-smi` showed 6,766 MiB free.
- **Mutation checks:**
  - drop the `with_driver_free` line → G20 fails;
  - `>=` → `<=` → G18, G19 and G20 fail;
  - drop the GPU-count check → G21 fails.
  - All files were restored afterwards.
- **Full suite** (`-n 8`, 13 min 16 s): 93 failed, 13,031 passed, 137 skipped and 20 errors.
  - No failure outside the VS-02 baseline, and 4 baseline failures now pass.
  - An earlier run stopped at 45% with no summary and no error. A plain re-run completed, so it is recorded as an interrupted run, not a test result.
- **Next:** Part B, the live refusal, needs real run approval. It also closes VS-17 Part B.

## Part B results (Operator, 2026-11-08)

**PASS.** Part A was committed first (18895cde1). `ods-llama-server` was already up and healthy, with the LLM loaded, so step 1 needed no start.

- **Before:** 25,130 MiB used and 7,061 MiB free per `nvidia-smi`. Voice Studio was started with the worktree launcher, default profile (commercial-only, VoxCPM2 default).
- **API:** one `POST /generate` with `engine=voxcpm2` and a short synthetic sentence returned **503**: "Not enough free GPU memory: need 8.0 GB, have 6.5 GB (TTS engine 'voxcpm2'). …". At that moment `nvidia-smi` showed 6,632 MiB (6.48 GiB) free, so the gate's figure matches the driver's.
- **Nothing loaded:** no VoxCPM2 sidecar or other child process of the server spawned. `memory.used` stayed at 25,559–25,581 MiB from before the request to after the UI try. The roughly 430 MiB above the starting figure is Voice Studio's own CUDA context, and it was released on `-Stop` (25,139 MiB used afterwards).
- **Design page:** one click on "Synthesize audio" showed the same message in a red error banner, with "Open docs" and "Copy diagnostic" buttons. No take was produced.
- **Still the torch figure:** upstream's startup log line still reads "GPU pool sized to 4 worker(s) — 27.8 GB free". This is out of scope here, as the spec says.
- `-Stop` stopped the server. `ods-llama-server` stayed up and healthy throughout.