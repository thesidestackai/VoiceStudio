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
        # VS-20: torch misses GPU memory used inside WSL (ODS); ask the driver too.
        mem = with_driver_free(mem)
    free = mem.get("vram_free_gb")
    if free is None:
        return None  # no CUDA GPU: nothing to guard
    need = required_gb(min_vram_gb)
    if float(free) >= need:
        return None
    return (
        f"Not enough free GPU memory: need {need:.1f} GB, have {float(free):.1f} GB "
        f"(TTS engine '{engine_id}'). If ODS has its LLM loaded, unload it in ODS "
        "or wait until ODS unloads it, then try again; or choose a CPU engine. "
        "Voice Studio never unloads ODS models."
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
    # CPU-only engines (no CUDA/ROCm in gpu_compat) never use the GPU ODS shares.
    if not ({"cuda", "rocm"} & set(getattr(cls, "gpu_compat", ()) or ())):
        return None
    floor = effective_floor_gb(selected, getattr(cls, "min_vram_gb", 0.0))
    return admission_error(selected, floor, resident=is_resident(cls), mem=mem)
