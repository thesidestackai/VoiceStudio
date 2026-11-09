"""SideStack VS-19 — the default TTS engine comes from the SideStack profile.

prefs.json is replaced by an in-memory store; engine env vars are cleared.
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

os.environ.setdefault("OMNIVOICE_MODEL", "test")
os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def tts(monkeypatch):
    """(services.tts_backend, the in-memory prefs store)."""
    prefs = importlib.import_module("core.prefs")
    store: dict = {}
    monkeypatch.setattr(prefs, "get", lambda key, default=None: store.get(key, default))
    monkeypatch.delenv("OMNIVOICE_TTS_BACKEND", raising=False)
    monkeypatch.delenv("SIDESTACK_DEFAULT_TTS_BACKEND", raising=False)
    return importlib.import_module("services.tts_backend"), store


def test_d1_unset_keeps_upstream_default(tts):
    mod, _ = tts
    assert mod.active_backend_id() == "omnivoice"


def test_d2_profile_default(tts, monkeypatch):
    mod, _ = tts
    monkeypatch.setenv("SIDESTACK_DEFAULT_TTS_BACKEND", "voxcpm2")
    assert mod.active_backend_id() == "voxcpm2"


def test_d3_settings_choice_wins(tts, monkeypatch):
    mod, store = tts
    monkeypatch.setenv("SIDESTACK_DEFAULT_TTS_BACKEND", "voxcpm2")
    store["tts_backend"] = "kittentts"
    assert mod.active_backend_id() == "kittentts"


def test_d4_env_pin_wins(tts, monkeypatch):
    mod, store = tts
    monkeypatch.setenv("SIDESTACK_DEFAULT_TTS_BACKEND", "voxcpm2")
    store["tts_backend"] = "kittentts"
    monkeypatch.setenv("OMNIVOICE_TTS_BACKEND", "cosyvoice")
    assert mod.active_backend_id() == "cosyvoice"


def test_d5_blank_falls_back(tts, monkeypatch):
    mod, _ = tts
    monkeypatch.setenv("SIDESTACK_DEFAULT_TTS_BACKEND", "  ")
    assert mod.active_backend_id() == "omnivoice"


def test_d6_profile_and_hook(tts):
    mod, _ = tts
    with open(os.path.join(ROOT, "sidestack", "config", "ods.env.example"), encoding="utf-8") as f:
        assert "SIDESTACK_DEFAULT_TTS_BACKEND=voxcpm2" in f.read().splitlines()
    assert "voxcpm2" in mod._REGISTRY
    with open(os.path.join(ROOT, "backend", "services", "tts_backend.py"), encoding="utf-8") as f:
        assert f.read().count("SideStack fork (VS-19)") == 1
