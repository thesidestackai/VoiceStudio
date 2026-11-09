"""SideStack VS-22 — commercial-only mode in the listings the UI reads.

GET /models rows and GET /engines backends carry `commercial_only_refusal`
(the refusal message, or None), and POST /engines/select refuses an engine the
mode refuses outright. Route functions are called directly; nothing is
downloaded or saved. Acceptance records are kept in memory.
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

os.environ.setdefault("OMNIVOICE_MODEL", "test")
os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

from fastapi import HTTPException  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

pytestmark = pytest.mark.model_licence_gate

# Engines whose every registry model is not commercial (registry checked 2026-11-08).
REFUSED_ENGINES = {
    "omnivoice", "omnivoice-subprocess", "omnivoice-gguf", "indextts2",
    "supertonic3", "audiocpp", "funasr",
}


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
def models(monkeypatch):
    mod = importlib.import_module("api.routers.setup.models")
    monkeypatch.setattr(mod, "_cache", {})
    return mod


@pytest.fixture
def eng(monkeypatch):
    mod = importlib.import_module("api.routers.engines")
    saved: list[tuple[str, str]] = []
    monkeypatch.setattr(mod.prefs, "set_", lambda key, value: saved.append((key, value)))
    monkeypatch.setattr(mod, "saved", saved, raising=False)
    return mod


def _rows(models):
    models._cache.clear()
    return {row["repo_id"]: row for row in models.list_models()["models"]}


def _select(eng, family, backend_id):
    return eng.select_engine(eng.SelectEngineRequest(family=family, backend_id=backend_id))


def test_u1_hooks_in_place():
    def read(*parts):
        with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
            return f.read()
    assert read("backend", "api", "routers", "setup", "models.py").count("SideStack fork (VS-22)") == 1
    assert read("backend", "api", "routers", "engines.py").count("SideStack fork (VS-22)") == 2
    assert "def engine_refusal(" in read("backend", "sidestack_fork", "licensing.py")


def test_u2_catalogue_rows(lic, models, monkeypatch):
    fake = {"repo_id": "sidestack-test/needs-omnivoice", "label": "Test", "role": "tts",
            "size_gb": 0.1, "dependencies": [{"repo_id": "k2-fsa/OmniVoice"}]}
    monkeypatch.setattr(models, "KNOWN_MODELS", [*models.KNOWN_MODELS, fake])
    rows = _rows(models)  # flag unset: no row is refused
    assert all(row["commercial_only_refusal"] is None for row in rows.values())
    monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
    rows = _rows(models)
    assert "k2-fsa/OmniVoice (noncommercial)" in rows["k2-fsa/OmniVoice"]["commercial_only_refusal"]
    assert "audio-cpp/audio.cpp-gguf (noncommercial)" in rows["audio-cpp/audio.cpp-gguf"]["commercial_only_refusal"]
    # The catalogue key is the licence record: a commercial package in that repo passes.
    assert rows["audio-cpp/audio.cpp-gguf:dots-tts-soar-q8_0"]["commercial_only_refusal"] is None
    assert rows["openbmb/VoxCPM2"]["commercial_only_refusal"] is None
    # Dependencies count, as on the install route.
    assert "k2-fsa/OmniVoice" in rows["sidestack-test/needs-omnivoice"]["commercial_only_refusal"]


def test_u3_engine_rows(lic, eng, monkeypatch):
    def refused(family, module):
        payload = eng._family_payload(family, module)
        return {b["id"] for b in payload["backends"] if b["commercial_only_refusal"]}
    assert refused("tts", eng.tts_backend) == set()  # flag unset
    monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
    tts = refused("tts", eng.tts_backend)
    assert {"omnivoice", "indextts2", "supertonic3"} <= tts
    assert not tts & {"voxcpm2", "kittentts", "mlx-audio"}
    asr = refused("asr", eng.asr_backend)
    assert "funasr" in asr and not asr & {"sherpa-onnx-asr", "faster-whisper", "pytorch-whisper"}
    assert refused("llm", eng.llm_backend) == set()


def test_u4_select_refuses(lic, eng, monkeypatch):
    with pytest.raises(HTTPException) as off:  # flag unset: upstream's "not ready" 400
        _select(eng, "tts", "indextts2")
    assert off.value.status_code == 400
    monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
    for engine_id in ("omnivoice", "indextts2"):  # the refusal comes before "not ready"
        with pytest.raises(lic.CommercialOnlyRefused) as on:
            _select(eng, "tts", engine_id)
        assert on.value.detail()["code"] == "commercial_only_mode"
    assert eng.saved == []
    _select(eng, "tts", "kittentts")
    assert eng.saved == [("tts_backend", "kittentts")]
    with pytest.raises(HTTPException) as unknown:
        _select(eng, "tts", "no-such-engine")
    assert unknown.value.status_code == 400


def test_u5_engine_refusal_rules(lic, monkeypatch):
    assert lic.engine_refusal("omnivoice") is None  # flag unset
    monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
    refused = lic.engine_refusal("omnivoice")
    assert isinstance(refused, lic.CommercialOnlyRefused)
    assert "k2-fsa/OmniVoice" in [m["repo_id"] for m in refused.models]
    assert lic.engine_refusal("sherpa-onnx-asr") is None  # has commercial models too
    assert lic.engine_refusal("openai-compat") is None  # no registry rows
    assert lic.engine_refusal("voxcpm2") is None
    assert lic.refusal(["openbmb/VoxCPM2"]) is None
    assert lic.refusal_text(None) is None
    assert lic.refusal_text(lic.refusal(["k2-fsa/OmniVoice"])) == str(lic.refusal(["k2-fsa/OmniVoice"]))


def test_u6_registry_unreadable_fails_closed(lic, monkeypatch):
    _ma = importlib.import_module("services.model_acceptance")

    def boom(engine_id, identity=None):
        raise OSError("registry unreadable")
    monkeypatch.setattr(_ma, "repos_for_engine", boom)
    assert lic.engine_refusal("voxcpm2") is None  # flag unset
    monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
    refused = lic.engine_refusal("voxcpm2")
    assert isinstance(refused, _ma.ModelLicenceNotAccepted)
    assert refused.reason == "registry_unreadable"
    assert lic.refusal_text(refused) == str(refused)


def test_u7_refused_engine_set(lic, monkeypatch):
    """Which engines the mode refuses outright. A registry change shows up here."""
    eng = importlib.import_module("api.routers.engines")
    monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
    ids = [b["id"] for b in eng.tts_backend.list_backends(include_hidden=True)]
    ids += [b["id"] for b in eng.asr_backend.list_backends()]
    ids += [b["id"] for b in eng.llm_backend.list_backends()]
    assert {i for i in ids if lic.engine_refusal(i) is not None} == REFUSED_ENGINES
