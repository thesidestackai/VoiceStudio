"""SideStack VS-06 — GPU admission gate for TTS loads beside ODS.

The module is opt-in (SIDESTACK_VRAM_ADMISSION=1) and never raises. Every test
passes mem= explicitly, so none of them reads the real GPU.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

os.environ.setdefault("OMNIVOICE_MODEL", "test")
os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("SIDESTACK_VRAM_ADMISSION", raising=False)
    monkeypatch.delenv("SIDESTACK_VRAM_MARGIN_GB", raising=False)


def _mod(monkeypatch, *, on: bool = True, margin: str | None = None):
    if on:
        monkeypatch.setenv("SIDESTACK_VRAM_ADMISSION", "1")
    if margin is not None:
        monkeypatch.setenv("SIDESTACK_VRAM_MARGIN_GB", margin)
    return importlib.import_module("sidestack_fork.admission")


# ── G1: gate off (env unset) ──────────────────────────────────────────────


def test_g1_gate_off_env_unset(monkeypatch):
    sa = _mod(monkeypatch, on=False)
    assert sa.admission_error("x", 6.0, resident=False, mem={"vram_free_gb": 0.5}) is None


# ── G2: warm/resident engine is never refused ─────────────────────────────


def test_g2_resident_engine_passes(monkeypatch):
    sa = _mod(monkeypatch)
    assert sa.admission_error("x", 6.0, resident=True, mem={"vram_free_gb": 0.5}) is None


# ── G3: no CUDA GPU (no vram_free_gb) — nothing to guard ─────────────────


def test_g3_no_vram_key(monkeypatch):
    sa = _mod(monkeypatch)
    assert sa.admission_error("x", 6.0, resident=False, mem={"ram_available_gb": 8.0}) is None


# ── G4: refused with a clear message ──────────────────────────────────────


def test_g4_refusal_message(monkeypatch):
    sa = _mod(monkeypatch)
    msg = sa.admission_error("omnivoice", 6.0, resident=False, mem={"vram_free_gb": 5.0})
    assert msg is not None
    assert "need 7.0 GB, have 5.0 GB" in msg
    assert "ODS" in msg


# ── G5: exactly at the requirement passes ─────────────────────────────────


def test_g5_exactly_at_requirement_passes(monkeypatch):
    sa = _mod(monkeypatch)
    assert sa.admission_error("omnivoice", 6.0, resident=False, mem={"vram_free_gb": 7.0}) is None


# ── G6: zero floor still costs the margin ─────────────────────────────────


def test_g6_zero_floor_costs_margin(monkeypatch):
    sa = _mod(monkeypatch)
    msg = sa.admission_error("x", 0.0, resident=False, mem={"vram_free_gb": 0.5})
    assert msg is not None
    assert "need 1.0 GB" in msg
    assert sa.admission_error("x", 0.0, resident=False, mem={"vram_free_gb": 1.5}) is None


# ── G7: configurable margin, invalid values fall back ─────────────────────


def test_g7_margin_config(monkeypatch):
    sa = _mod(monkeypatch, margin="2.5")
    msg = sa.admission_error("x", 2.0, resident=False, mem={"vram_free_gb": 4.0})
    assert msg is not None
    assert "need 4.5 GB" in msg

    assert _mod(monkeypatch, margin="abc").margin_gb() == 1.0
    assert _mod(monkeypatch, margin="-3").margin_gb() == 1.0


# ── G8: residency detection ───────────────────────────────────────────────


def test_g8_residency(monkeypatch):
    sa = _mod(monkeypatch)
    from services import model_manager, tts_backend

    monkeypatch.setattr(model_manager, "model", object())
    assert sa.is_resident(tts_backend.OmniVoiceBackend) is True
    monkeypatch.setattr(model_manager, "model", None)
    assert sa.is_resident(tts_backend.OmniVoiceBackend) is False

    class _Dummy:
        pass

    assert sa.is_resident(_Dummy) is False
    monkeypatch.setitem(tts_backend._ENGINE_INSTANCES, _Dummy, object())
    assert sa.is_resident(_Dummy) is True


# ── G9: route-level entry never raises ────────────────────────────────────


def test_g9_route_entry(monkeypatch):
    sa = _mod(monkeypatch)
    assert sa.tts_admission_error("no-such-engine", mem={"vram_free_gb": 0.1}) is None

    class _Eng:
        min_vram_gb = 6.0
        gpu_compat = ("cuda", "cpu")

    msg = sa.tts_admission_error("eng", _Eng, mem={"vram_free_gb": 2.0})
    assert msg is not None
    assert "need 7.0 GB" in msg


# ── G10: the route hooks are present ──────────────────────────────────────


def test_g10_hooks_present():
    root = Path(__file__).resolve().parents[1] / "backend" / "api" / "routers"
    gen = (root / "generation.py").read_text(encoding="utf-8")
    stream = (root / "tts_stream.py").read_text(encoding="utf-8")
    for text in (gen, stream):
        assert "tts_admission_error(" in text
        assert "SideStack fork (VS-06)" in text
    speech = (root / "openai_compat.py").read_text(encoding="utf-8")
    assert "tts_admission_error(" in speech
    assert "SideStack fork (VS-09)" in speech


# ── G11: the ODS profile turns the gate on ────────────────────────────────


def test_g11_profile_enables_gate():
    env_file = Path(__file__).resolve().parents[1] / "sidestack" / "config" / "ods.env.example"
    profile: dict[str, str] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        profile[key.strip()] = value.strip()
    assert profile["SIDESTACK_VRAM_ADMISSION"] == "1"
    assert profile["SIDESTACK_VRAM_MARGIN_GB"] == "1.0"


# ── G12: CPU-only engines are never refused ───────────────────────────────


def test_g12_cpu_only_engine_passes(monkeypatch):
    sa = _mod(monkeypatch)

    class _CpuEng:
        min_vram_gb = 0.0
        gpu_compat = ("cpu",)

    assert sa.tts_admission_error("cpu-eng", _CpuEng,
                                  mem={"vram_free_gb": 0.1}) is None

    class _CudaEng:
        min_vram_gb = 0.0
        gpu_compat = ("cuda", "cpu")

    msg = sa.tts_admission_error("cuda-eng", _CudaEng,
                                 mem={"vram_free_gb": 0.1})
    assert msg is not None
    assert "need 1.0 GB" in msg


# ── G13: the OpenAI speech route returns the gate's refusal ───────────────


def test_g13_speech_route_gate_refusal(monkeypatch):
    import asyncio

    monkeypatch.setattr(
        importlib.import_module("sidestack_fork.admission"),
        "tts_admission_error",
        lambda *a, **k: "refused by test",
    )
    import api.routers.openai_compat as oc

    with pytest.raises(oc.OpenAIError) as exc:
        asyncio.run(oc.create_speech(
            oc.SpeechRequest(model="kittentts", input="x",
                             response_format="wav")))
    assert exc.value.status_code == 503
    assert exc.value.code == "insufficient_gpu_memory"
    assert exc.value.detail == "refused by test"


# ── G14: VS-15 "Voice Studio first" advice ─────────────────────────────────
def test_g14_refusal_advice_voice_studio_first(monkeypatch):
    """VS-15: Voice Studio runs on its own, so the advice is to free ODS's
    LLM or use a CPU engine, never to shrink ODS's context."""
    sa = _mod(monkeypatch)
    msg = sa.admission_error("voxcpm2", 6.0, resident=False, mem={"vram_free_gb": 5.0})
    assert msg is not None
    assert "need 7.0 GB, have 5.0 GB" in msg
    assert "64k" not in msg
    assert "unload it in ODS" in msg
    assert "CPU engine" in msg
    assert "never unloads ODS models" in msg


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
