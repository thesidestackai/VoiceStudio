"""SideStack VS-14 — with the opt-in flag, dictation (the capture picker and
the "model missing" check) goes through Voice Studio's configured
OpenAI-compatible ASR server instead of loading a second, local Whisper.

Header, the ss fixture and the asr_mod fixture are copied from
tests/test_sidestack_ods_asr.py (same staleness rationale). No test touches
the network or the GPU; every backend that would build a model is stubbed.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

os.environ.setdefault("OMNIVOICE_MODEL", "test")
os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

_HAS_OPENAI = __import__("importlib").util.find_spec("openai") is not None
pytestmark = pytest.mark.skipif(not _HAS_OPENAI, reason="openai package not installed")


@pytest.fixture
def ss(monkeypatch):
    """services.settings_store, in-memory (no SQLite)."""
    from services import settings_store as _ss

    text: dict[str, str] = {}
    secrets: dict[str, str] = {}
    monkeypatch.setattr(_ss, "get_text", lambda k, default=None: text.get(k, default))
    monkeypatch.setattr(_ss, "set_text", lambda k, v: text.__setitem__(k, v))
    monkeypatch.setattr(_ss, "get_secret", lambda n: secrets.get(n))
    monkeypatch.setattr(
        _ss, "set_secret", lambda n, v: secrets.__setitem__(n, v) if v else secrets.pop(n, None)
    )
    monkeypatch.setattr(_ss, "list_secret_names", lambda: list(secrets))
    return _ss


@pytest.fixture
def asr_mod(ss, monkeypatch):
    """services.asr_backend, resolved live in sys.modules (see the same
    fixture's docstring in tests/test_sidestack_ods_asr.py for the staleness
    rationale) with the ASR env vars cleared."""
    for var in ("OMNIVOICE_ASR_BACKEND", "ASR_OPENAI_COMPAT_BASE_URL", "ASR_OPENAI_COMPAT_MODEL", "ASR_OPENAI_COMPAT_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    import importlib
    return importlib.import_module("services.asr_backend")


@pytest.fixture
def remote(asr_mod, monkeypatch):
    """The ODS dictation profile: flag set, main ASR is the OpenAI-compatible
    server, no sherpa selection, and the local Whisper chain is armed to fail
    the moment any test would actually build a local model."""
    monkeypatch.setenv("SIDESTACK_DICTATION_ODS", "1")
    monkeypatch.setenv("OMNIVOICE_ASR_BACKEND", "openai-compat-asr")
    monkeypatch.setenv("ASR_OPENAI_COMPAT_BASE_URL", "http://127.0.0.1:9000/v1")
    monkeypatch.setenv("ASR_OPENAI_COMPAT_MODEL", "test-model")
    monkeypatch.delenv("OMNIVOICE_SHERPA_ASR_MODEL", raising=False)
    monkeypatch.setattr(asr_mod, "dictation_model_id", lambda: None)
    monkeypatch.setattr(asr_mod, "_capture_backend", None)
    monkeypatch.setattr(asr_mod, "_capture_backend_key", None)

    def _no_local_whisper(self, *args, **kwargs):
        raise AssertionError("local whisper built")

    monkeypatch.setattr(asr_mod.PyTorchWhisperBackend, "__init__", _no_local_whisper)
    monkeypatch.setattr(asr_mod.FasterWhisperBackend, "__init__", _no_local_whisper)


def _local_chain_stub(monkeypatch, asr_mod):
    """Make the upstream local chain deterministic: no Parakeet, no MLX, no
    faster-whisper, and a no-op PyTorchWhisperBackend (no model loaded)."""
    monkeypatch.setattr(asr_mod, "_capture_prefers_parakeet", lambda: False)
    monkeypatch.setattr(asr_mod.MLXWhisperBackend, "is_available",
                        classmethod(lambda cls: (False, "test")))
    monkeypatch.setattr(asr_mod.FasterWhisperBackend, "is_available",
                        classmethod(lambda cls: (False, "test")))
    monkeypatch.setattr(asr_mod.PyTorchWhisperBackend, "__init__",
                        lambda self, asr_pipe=None: None)


def test_d1_remote_picker_hands_out_server_backend(remote, asr_mod):
    backend = asr_mod.get_capture_asr_backend()
    assert isinstance(backend, asr_mod.OpenAICompatASRBackend)
    assert asr_mod.get_capture_asr_backend() is backend


def test_d2_flag_unset_runs_upstream_chain(remote, asr_mod, monkeypatch):
    monkeypatch.delenv("SIDESTACK_DICTATION_ODS")
    _local_chain_stub(monkeypatch, asr_mod)
    backend = asr_mod.get_capture_asr_backend()
    assert isinstance(backend, asr_mod.PyTorchWhisperBackend)


def test_d3_main_asr_not_server(remote, asr_mod, monkeypatch):
    monkeypatch.setenv("OMNIVOICE_ASR_BACKEND", "faster-whisper")
    _local_chain_stub(monkeypatch, asr_mod)
    backend = asr_mod.get_capture_asr_backend()
    assert isinstance(backend, asr_mod.PyTorchWhisperBackend)


def test_d4_server_not_configured(remote, asr_mod, monkeypatch):
    monkeypatch.delenv("ASR_OPENAI_COMPAT_BASE_URL")
    _local_chain_stub(monkeypatch, asr_mod)
    backend = asr_mod.get_capture_asr_backend()
    assert isinstance(backend, asr_mod.PyTorchWhisperBackend)


def test_d5_explicit_sherpa_selection_still_wins(remote, asr_mod, monkeypatch):
    monkeypatch.setattr(asr_mod, "dictation_model_id", lambda: "test-sherpa")
    from services.performance_profiles import requested_tier

    class _StubSherpa:
        @classmethod
        def is_available(cls):
            return (True, "")

        def __init__(self, model_id):
            self.model_id = model_id
            self.performance_tier = requested_tier("dictation")

    monkeypatch.setattr(asr_mod, "SherpaDictationBackend", _StubSherpa)
    monkeypatch.setattr(asr_mod, "ensure_backend_licence", lambda _backend: None)
    backend = asr_mod.get_capture_asr_backend()
    assert isinstance(backend, _StubSherpa)
    assert backend.model_id == "test-sherpa"


def test_d6_model_missing_follows_flag(remote, asr_mod, monkeypatch):
    # asr_model_missing_error swallows every exception (fail-open), so a
    # raising stub would pass either way: record calls and assert on them.
    reached = []

    def _stub_repo():
        reached.append(True)
        return None

    monkeypatch.setattr(asr_mod, "_capture_whisper_repo", _stub_repo)
    assert asr_mod.asr_model_missing_error(purpose="dictation") is None
    assert reached == []  # the hook answered before the local Whisper check

    monkeypatch.delenv("SIDESTACK_DICTATION_ODS")
    assert asr_mod.asr_model_missing_error(purpose="dictation") is None
    assert reached == [True]  # flag off: upstream's local Whisper check runs


def test_d7_dictation_buffer_transcribes_through_server(remote, asr_mod, monkeypatch, tmp_path):
    """Follows tests/test_capture_ws.py: patch `_pcm16_to_wav`, `run_transcribe_guarded`
    to run inline, and stub `services.model_manager._gpu_pool` to avoid pulling in
    the real GPU pool. The dictation buffer path (`dictation=True`) must reach the
    OpenAI-compatible server's `transcribe` and return its text."""
    import asyncio
    import types
    from api.routers import capture_ws as cw

    recorded = {}

    def _fake_transcribe(self, path, **kwargs):
        recorded["path"] = path
        recorded.update(kwargs)
        return {"chunks": [],
                "segments": [{"text": "hello there", "start": 0.0, "end": 1.0, "words": []}],
                "language": "en"}

    monkeypatch.setattr(asr_mod.OpenAICompatASRBackend, "transcribe", _fake_transcribe)
    monkeypatch.setattr(cw, "_pcm16_to_wav", lambda _pcm, _sr: str(tmp_path / "partial.wav"))

    async def run_inline(_executor, fn, **_kwargs):
        return fn()

    monkeypatch.setattr(asr_mod, "run_transcribe_guarded", run_inline)

    # _run() does `from services.model_manager import _gpu_pool` — stub that
    # module so the import never reaches the real (heavy) one.
    fake_mm = types.ModuleType("services.model_manager")
    fake_mm._gpu_pool = object()
    monkeypatch.setitem(sys.modules, "services.model_manager", fake_mm)

    result = asyncio.run(
        cw._transcribe_buffer([b"\x00\x00" * 16000], pcm_sr=16000, dictation=True)
    )
    assert result == "hello there"
    assert recorded["path"].endswith(".wav")
    assert recorded["word_timestamps"] is False


def test_d8_profile_and_hooks():
    profile = (
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        + "/sidestack/config/ods.env.example"
    )
    with open(profile, encoding="utf-8") as f:
        assert "SIDESTACK_DICTATION_ODS=1" in f.read()

    with open(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        + "/backend/services/asr_backend.py",
        encoding="utf-8",
    ) as f:
        source = f.read()
    assert source.count("SideStack fork (VS-14)") == 2
    assert source.count("remote_capture_active()") == 2
