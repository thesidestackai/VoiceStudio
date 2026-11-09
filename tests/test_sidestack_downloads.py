"""SideStack VS-21 — commercial-only mode refuses downloads too.

Covers POST /models/install, POST /engines/sidecar/{id}/install and
POST /engines/omnivoice-gguf/quants/download. Route functions are called
directly; nothing is downloaded. Acceptance records are kept in memory.
"""
from __future__ import annotations

import asyncio
import importlib
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

os.environ.setdefault("OMNIVOICE_MODEL", "test")
os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

from fastapi import HTTPException  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

pytestmark = pytest.mark.model_licence_gate


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
def dl():
    return importlib.import_module("api.routers.setup.download")


@pytest.fixture
def eng():
    return importlib.import_module("api.routers.engines")


def _install(dl, repo_id):
    return asyncio.run(dl.install_model(dl.InstallModelRequest(repo_id=repo_id)))


def _cooling(dl, monkeypatch, repo_id):
    """Make the upstream cooldown answer 429 for repo_id: proof the gate let it through."""
    monkeypatch.setitem(dl._install_cooldowns, repo_id, time.time())


def test_w1_hooks_in_place():
    def read(*parts):
        with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
            return f.read()
    assert read("backend", "api", "routers", "setup", "download.py").count("SideStack fork (VS-21)") == 1
    assert read("backend", "api", "routers", "engines.py").count("SideStack fork (VS-21)") == 2
    assert "def ensure_engine_commercial_only(" in read("backend", "sidestack_fork", "licensing.py")


def test_w2_install_refuses_noncommercial(lic, dl, monkeypatch):
    _cooling(dl, monkeypatch, "k2-fsa/OmniVoice")
    with pytest.raises(HTTPException) as off:  # flag unset: upstream path (cooldown 429)
        _install(dl, "k2-fsa/OmniVoice")
    assert off.value.status_code == 429
    monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
    with pytest.raises(lic.CommercialOnlyRefused) as on:
        _install(dl, "k2-fsa/OmniVoice")
    detail = on.value.detail()
    assert detail["code"] == "commercial_only_mode"
    assert [m["repo_id"] for m in detail["models"]] == ["k2-fsa/OmniVoice"]


def test_w3_install_package_uses_catalogue_key(lic, dl, monkeypatch):
    monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
    package = "audio-cpp/audio.cpp-gguf:dots-tts-soar-q8_0"  # apache-2.0 row in a non-commercial repo
    _cooling(dl, monkeypatch, package)
    with pytest.raises(HTTPException) as passed:
        _install(dl, package)
    assert passed.value.status_code == 429
    with pytest.raises(lic.CommercialOnlyRefused):
        _install(dl, "audio-cpp/audio.cpp-gguf")


def test_w4_install_checks_dependencies(lic, dl, monkeypatch):
    monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
    original = dl.KNOWN_MODELS
    fake = {"repo_id": "openbmb/VoxCPM2", "dependencies": [{"repo_id": "k2-fsa/OmniVoice"}]}
    monkeypatch.setattr(dl, "KNOWN_MODELS", [fake])
    with pytest.raises(lic.CommercialOnlyRefused) as exc:
        _install(dl, "openbmb/VoxCPM2")
    assert [m["repo_id"] for m in exc.value.models] == ["k2-fsa/OmniVoice"]
    monkeypatch.setattr(dl, "KNOWN_MODELS", original)
    _cooling(dl, monkeypatch, "pyannote/speaker-diarization-3.1")
    with pytest.raises(HTTPException) as passed:  # commercial model, commercial dependencies
        _install(dl, "pyannote/speaker-diarization-3.1")
    assert passed.value.status_code == 429


def test_w5_sidecar_install(lic, eng, monkeypatch):
    sidecar_install = importlib.import_module("services.sidecar_install")
    started = []

    def start(eid):
        if eid not in sidecar_install.SPECS:
            raise KeyError(eid)  # as upstream: the route answers 404
        started.append(eid)
        return {"status": "started"}

    monkeypatch.setattr(sidecar_install, "start_install", start)
    monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
    for eid in ("indextts2", "supertonic3"):  # unknown and conditions categories
        with pytest.raises(lic.CommercialOnlyRefused):
            eng.install_sidecar_engine(eid)
    assert started == []
    assert eng.install_sidecar_engine("voxcpm2") == {"status": "started"}
    with pytest.raises(HTTPException) as missing:  # no registry rows, no installer: upstream 404
        eng.install_sidecar_engine("no-such-engine")
    assert missing.value.status_code == 404
    monkeypatch.delenv("SIDESTACK_COMMERCIAL_ONLY")
    eng.install_sidecar_engine("indextts2")
    assert started == ["voxcpm2", "indextts2"]


def test_w6_gguf_download(lic, eng, monkeypatch):
    quants = importlib.import_module("engines.omnivoice_gguf.quants")
    models = importlib.import_module("api.routers.setup.models")
    started = []
    monkeypatch.setattr(quants, "start_download", lambda target: started.append(target) or {"status": "started"})
    monkeypatch.setattr(models, "disk_space_error", lambda *a, **k: None)
    monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
    with pytest.raises(lic.CommercialOnlyRefused) as exc:
        eng.download_omnivoice_gguf_quant(eng.GGUFQuantRequest(quant="auto"))
    assert [m["repo_id"] for m in exc.value.models] == ["Serveurperso/OmniVoice-GGUF"]
    assert started == []
    monkeypatch.delenv("SIDESTACK_COMMERCIAL_ONLY")
    assert eng.download_omnivoice_gguf_quant(eng.GGUFQuantRequest(quant="auto")) == {"status": "started"}
    assert started == [None]


def test_w7_registry_unreadable_fails_closed(lic, monkeypatch):
    ma = importlib.import_module("services.model_acceptance")

    def broken(engine_id, identity=None):
        raise OSError("registry unreadable")

    monkeypatch.setattr(ma, "repos_for_engine", broken)
    lic.ensure_engine_commercial_only("voxcpm2")  # flag unset: no-op, upstream unchanged
    monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
    with pytest.raises(ma.ModelLicenceNotAccepted) as exc:
        lic.ensure_engine_commercial_only("voxcpm2")
    assert exc.value.reason == "registry_unreadable"
    assert not isinstance(exc.value, lic.CommercialOnlyRefused)


def test_w8_every_installer_engine_has_registry_rows():
    """An installer engine with no registry rows would pass the gate unchecked."""
    ma = importlib.import_module("services.model_acceptance")
    sidecar_install = importlib.import_module("services.sidecar_install")
    for eid in [*sidecar_install.SPECS, "omnivoice-gguf"]:
        assert ma.repos_for_engine(eid), eid
