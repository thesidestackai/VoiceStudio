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
