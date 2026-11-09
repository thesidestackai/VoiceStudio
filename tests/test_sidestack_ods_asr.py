"""SideStack VS-05 — the ODS env profile pins Voice Studio's ASR to ODS
Whisper via the existing openai-compat-asr backend, keyless on loopback.

Fixtures and the fake OpenAI client are copied from
tests/test_asr_openai_compat_877.py (house convention: direct handler calls,
OpenAI client faked at the SDK boundary, no network).
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

os.environ.setdefault("OMNIVOICE_MODEL", "test")
os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

_HAS_OPENAI = __import__("importlib").util.find_spec("openai") is not None
pytestmark = pytest.mark.skipif(not _HAS_OPENAI, reason="openai package not installed")


@pytest.fixture
def ss(monkeypatch):
    """services.settings_store, resolved fresh (no module-level import — see
    asr_mod's docstring for why staleness across sys.modules reimports is a
    real risk in this suite) and patched to in-memory dicts (no SQLite)."""
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
    """services.asr_backend with settings_store in-memory (no SQLite).

    Resolved via importlib.import_module INSIDE the fixture (not a top-level
    `import` in this file) so it's the module object actually live in
    sys.modules at test-run time — other test files in this ~2400-test suite
    pop+reimport shared service modules (services.model_manager,
    services.tts_backend), and a module-level import captured once at file
    COLLECTION time can go stale by the time an individual test in this file
    finally runs, hours of test-order later. A collection-time reference
    calling .set_text() and a fixture-time reference reading via .get_text()
    can silently be two different module objects — the write and the read
    land in different in-memory dicts, and the test fails with no obvious
    cause. Every test below takes `ss` as a fixture (not a module-level
    `from services import settings_store`) for the same reason.
    """
    for var in ("OMNIVOICE_ASR_BACKEND", "ASR_OPENAI_COMPAT_BASE_URL", "ASR_OPENAI_COMPAT_MODEL", "ASR_OPENAI_COMPAT_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    import importlib
    return importlib.import_module("services.asr_backend")


def _fake_openai_transcribe(monkeypatch, *, verbose_ok=True, response=None, raise_exc=None):
    """Fake openai.OpenAI whose audio.transcriptions.create() either returns
    a canned response or raises. verbose_ok=False simulates a minimal server
    that rejects response_format="verbose_json" on the first call, forcing
    the plain-json fallback."""
    captured_kwargs = []
    calls = []

    class _FakeClient:
        def __init__(self, **kwargs):
            captured_kwargs.append(kwargs)
            self.audio = types.SimpleNamespace(
                transcriptions=types.SimpleNamespace(create=self._create)
            )

        def _create(self, **kw):
            calls.append(kw)
            if raise_exc is not None:
                raise raise_exc
            if kw.get("response_format") == "verbose_json" and not verbose_ok:
                raise RuntimeError("response_format not supported")
            return response

    import openai
    monkeypatch.setattr(openai, "OpenAI", _FakeClient)
    return captured_kwargs, calls


def _profile() -> dict[str, str]:
    """KEY=VALUE lines of sidestack/config/ods.env.example, skipping blanks
    and #-comment lines."""
    env_file = Path(__file__).resolve().parents[1] / "sidestack" / "config" / "ods.env.example"
    profile: dict[str, str] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        profile[key.strip()] = value.strip()
    return profile


def _apply_asr_profile(monkeypatch) -> dict[str, str]:
    profile = _profile()
    monkeypatch.setenv("OMNIVOICE_ASR_BACKEND", profile["OMNIVOICE_ASR_BACKEND"])
    monkeypatch.setenv("ASR_OPENAI_COMPAT_BASE_URL", profile["ASR_OPENAI_COMPAT_BASE_URL"])
    monkeypatch.setenv("ASR_OPENAI_COMPAT_MODEL", profile["ASR_OPENAI_COMPAT_MODEL"])
    return profile


# ── A1: the profile pins ODS Whisper ─────────────────────────────────────────


def test_a1_profile_pins_ods_whisper():
    profile = _profile()
    assert profile["OMNIVOICE_ASR_BACKEND"] == "openai-compat-asr"
    assert profile["ASR_OPENAI_COMPAT_BASE_URL"] == "http://127.0.0.1:9000/v1"
    assert profile["ASR_OPENAI_COMPAT_MODEL"] == "deepdml/faster-whisper-large-v3-turbo-ct2"
    assert "ASR_OPENAI_COMPAT_API_KEY" not in profile


# ── A2: the profile selects OpenAICompatASRBackend ───────────────────────────


def test_a2_profile_selects_openai_compat_backend(asr_mod, monkeypatch):
    profile = _apply_asr_profile(monkeypatch)
    assert asr_mod.active_backend_id() == "openai-compat-asr"
    backend = asr_mod.get_active_asr_backend()
    assert isinstance(backend, asr_mod.OpenAICompatASRBackend)
    assert backend._base_url == profile["ASR_OPENAI_COMPAT_BASE_URL"]
    assert backend._model == profile["ASR_OPENAI_COMPAT_MODEL"]
    ok, reason = asr_mod.OpenAICompatASRBackend.is_available()
    assert ok is True
    assert reason == "ready"


# ── A3: keyless transcription through Voice Studio's backend ─────────────────


def test_a3_keyless_transcription_with_profile(asr_mod, monkeypatch, tmp_path):
    profile = _apply_asr_profile(monkeypatch)

    class _Seg:
        def model_dump(self):
            return {"text": "the quick brown fox", "start": 0.0, "end": 1.2}

    resp = types.SimpleNamespace(segments=[_Seg()], language="en")
    captured_kwargs, calls = _fake_openai_transcribe(monkeypatch, response=resp)

    assert asr_mod.resolve_openai_compat_asr_api_key() is None

    audio = tmp_path / "seg.wav"
    audio.write_bytes(b"RIFF....WAVEfmt ")  # content is never read by the fake client
    out = asr_mod.OpenAICompatASRBackend().transcribe(str(audio))

    assert captured_kwargs[0]["api_key"] == "not-needed"
    assert captured_kwargs[0]["base_url"] == profile["ASR_OPENAI_COMPAT_BASE_URL"]
    assert calls[0]["model"] == profile["ASR_OPENAI_COMPAT_MODEL"]
    assert calls[0]["response_format"] == "verbose_json"
    assert out["segments"][0]["text"] == "the quick brown fox"


# ── A4: a LAN plaintext Whisper is refused ───────────────────────────────────


def test_a4_lan_plaintext_whisper_refused(asr_mod, monkeypatch):
    _apply_asr_profile(monkeypatch)
    monkeypatch.setenv("ASR_OPENAI_COMPAT_BASE_URL", "http://192.168.1.50:9000/v1")
    ok, _reason = asr_mod.OpenAICompatASRBackend.is_available()
    assert ok is False
    with pytest.raises(ValueError):
        asr_mod.OpenAICompatASRBackend()
