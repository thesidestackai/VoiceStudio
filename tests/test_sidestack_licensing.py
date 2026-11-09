"""SideStack VS-18 — commercial-only mode.

Acceptance records are kept in memory (no SQLite); the registry is the real one.
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

# tests/conftest.py stubs ensure_accepted to "accepted" unless a test opts in.
pytestmark = pytest.mark.model_licence_gate


@pytest.fixture
def ma(monkeypatch):
    """services.model_acceptance (live module) with an in-memory settings store."""
    _ss = importlib.import_module("services.settings_store")

    text: dict[str, str] = {}
    monkeypatch.setattr(_ss, "get_text", lambda k, default=None: text.get(k, default))
    monkeypatch.setattr(_ss, "set_text", lambda k, v: text.__setitem__(k, v))
    monkeypatch.setattr(_ss, "get_license_accepted", lambda engine: False)
    monkeypatch.setattr(_ss, "set_license_accepted", lambda engine, accepted: None)
    monkeypatch.delenv("SIDESTACK_COMMERCIAL_ONLY", raising=False)
    return importlib.import_module("services.model_acceptance")


@pytest.fixture
def lic(ma):
    return importlib.import_module("sidestack_fork.licensing")


def _accept(ma, repo_id):
    ma.accept(repo_id, ma.status(repo_id)["fingerprint"])


def test_c1_flag_off_upstream_unchanged(ma, lic):
    lic.ensure_commercial_only(["k2-fsa/OmniVoice"])  # no-op
    _accept(ma, "k2-fsa/OmniVoice")
    ma.ensure_accepted(["k2-fsa/OmniVoice"])  # accepted: upstream lets it through


def test_c2_noncommercial_refused_even_when_accepted(ma, lic, monkeypatch):
    monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
    _accept(ma, "k2-fsa/OmniVoice")
    with pytest.raises(lic.CommercialOnlyRefused) as exc:
        ma.ensure_accepted(["k2-fsa/OmniVoice"])
    assert isinstance(exc.value, ma.ModelLicenceNotAccepted)
    detail = exc.value.detail()
    assert detail["code"] == "commercial_only_mode"
    assert detail["models"][0]["category"] == "noncommercial"
    assert "-AllowNonCommercial" in detail["message"]


def test_c3_commercial_passes(ma, lic, monkeypatch):
    monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
    ma.ensure_accepted(["openbmb/VoxCPM2", "KittenML/kitten-tts-mini-0.8"])


def test_c4_unknown_and_conditions_refused(ma, lic, monkeypatch):
    monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
    for repo in ("IndexTeam/IndexTTS-2.5", "Supertone/supertonic-3", "no-such/model"):
        with pytest.raises(lic.CommercialOnlyRefused):
            ma.ensure_accepted([repo])


def test_c5_engine_level(ma, lic, monkeypatch):
    monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
    with pytest.raises(lic.CommercialOnlyRefused):
        ma.ensure_engine_accepted("omnivoice")
    for engine in ("voxcpm2", "kittentts", "cosyvoice"):
        ma.ensure_engine_accepted(engine)


def test_c6_generator_input_still_checked_upstream(ma, lic, monkeypatch):
    monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "0")
    with pytest.raises(ma.ModelLicenceNotAccepted) as exc:
        ma.ensure_accepted(r for r in ["k2-fsa/OmniVoice"])
    assert not isinstance(exc.value, lic.CommercialOnlyRefused)
    assert exc.value.detail()["code"] == "model_licence_required"


def test_c7_profile_and_hook():
    with open(os.path.join(ROOT, "sidestack", "config", "ods.env.example"), encoding="utf-8") as f:
        assert "SIDESTACK_COMMERCIAL_ONLY=1" in f.read().splitlines()
    with open(os.path.join(ROOT, "backend", "services", "model_acceptance.py"), encoding="utf-8") as f:
        src = f.read()
    assert src.count("SideStack fork (VS-18)") == 1
    assert src.count("ensure_commercial_only(repo_ids)") == 1


def test_c8_message_grammar(lic):
    one = lic.CommercialOnlyRefused([{"repo_id": "a/one", "license": None, "category": "noncommercial"}])
    two = lic.CommercialOnlyRefused([
        {"repo_id": "a/one", "license": None, "category": "noncommercial"},
        {"repo_id": "b/two", "license": None, "category": "unknown"},
    ])
    assert "a/one (noncommercial) is not licensed" in str(one)
    assert "b/two (unknown) are not licensed" in str(two)
