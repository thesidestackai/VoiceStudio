"""SideStack VS-23 — first-run setup requires the profile's default engine.

With SIDESTACK_DEFAULT_TTS_BACKEND set, the default engine's catalogue weights
are the required first-run model instead of upstream's OmniVoice, and
GET /setup/status also waits for the engine itself. Nothing is downloaded.
"""
from __future__ import annotations

import copy
import importlib
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

os.environ.setdefault("OMNIVOICE_MODEL", "test")
os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

FLAG = "SIDESTACK_DEFAULT_TTS_BACKEND"
VOXCPM2 = "openbmb/VoxCPM2"
KITTEN = "KittenML/kitten-tts-mini-0.8"


class _Ready:
    display_name = "Stub"

    @classmethod
    def is_available(cls):
        return True, "ready"


class _NotReady:
    display_name = "Stub"

    @classmethod
    def is_available(cls):
        return False, "not installed"


@pytest.fixture
def defaults(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    return importlib.import_module("sidestack_fork.defaults")


@pytest.fixture
def setup(monkeypatch, defaults):
    """The wizard over the SideStack catalogue with nothing downloaded; returns (wizard, choose)."""
    wizard = importlib.import_module("api.routers.setup.wizard")
    from services import tts_backend

    cached: set[str] = set()
    monkeypatch.setattr(wizard, "is_cached", lambda repo_id: repo_id in cached)
    monkeypatch.setattr(wizard, "_disk_free_gb", lambda path: 100.0)
    monkeypatch.setenv(FLAG, "voxcpm2")
    rows = copy.deepcopy(wizard.KNOWN_MODELS)
    defaults.apply_required_default(rows)
    monkeypatch.setattr(wizard, "KNOWN_MODELS", rows)

    def choose(engine: str, cls, *, downloaded=()) -> None:
        cached.clear()
        cached.update(downloaded)
        monkeypatch.setattr(tts_backend, "active_backend_id", lambda: engine)
        monkeypatch.setattr(tts_backend, "get_backend_class", lambda backend_id: cls)

    return wizard, choose


def _required(rows):
    return [str(m.get("id") or m["repo_id"]) for m in rows if m.get("required")]


def _missing(status):
    return [m["repo_id"] for m in status["missing"]]


def test_r1_hooks_in_place():
    def read(*parts):
        with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
            return f.read()
    assert read("backend", "services", "model_catalogue.py").count("SideStack fork (VS-23)") == 1
    assert read("backend", "api", "routers", "setup", "wizard.py").count("SideStack fork (VS-23)") == 1


def test_r2_required_follows_the_default_engine(defaults, monkeypatch):
    from services.model_catalogue import KNOWN_MODELS

    upstream = copy.deepcopy(KNOWN_MODELS)
    rows = copy.deepcopy(upstream)
    defaults.apply_required_default(rows)  # flag unset: unchanged
    assert rows == upstream and _required(rows) == ["k2-fsa/OmniVoice"]
    monkeypatch.setenv(FLAG, "voxcpm2")
    defaults.apply_required_default(rows)
    assert _required(rows) == [VOXCPM2]
    monkeypatch.setenv(FLAG, "kittentts")
    defaults.apply_required_default(rows)
    assert _required(rows) == [KITTEN]
    rows = copy.deepcopy(upstream)
    monkeypatch.setenv(FLAG, "sherpa-onnx")  # no catalogue row: left as upstream wrote it
    defaults.apply_required_default(rows)
    assert rows == upstream


def test_r3_fresh_install_waits_for_engine_and_weights(setup):
    wizard, choose = setup
    choose("voxcpm2", _NotReady)
    status = wizard.setup_status()
    assert status["models_ready"] is False
    assert _missing(status) == [VOXCPM2, "engine:voxcpm2"]
    assert status["missing"][1]["label"] == "Stub engine"


def test_r4_each_half_alone_is_not_enough(setup):
    wizard, choose = setup
    choose("voxcpm2", _Ready)  # engine installed, weights not downloaded
    assert _missing(wizard.setup_status()) == [VOXCPM2]
    choose("voxcpm2", _NotReady, downloaded={VOXCPM2})  # weights, no engine
    assert _missing(wizard.setup_status()) == ["engine:voxcpm2"]
    choose("voxcpm2", _Ready, downloaded={VOXCPM2})
    status = wizard.setup_status()
    assert status["models_ready"] is True and status["missing"] == []


def test_r5_another_ready_engine_still_lifts_the_requirement(setup, monkeypatch):
    from services import tts_backend

    wizard, choose = setup
    choose("kittentts", _Ready, downloaded={KITTEN})  # upstream's #3581 rule
    # Only KittenTTS is ready: VoxCPM2 itself is not installed.
    monkeypatch.setattr(tts_backend, "get_backend_class",
                        lambda backend_id: _Ready if backend_id == "kittentts" else _NotReady)
    status = wizard.setup_status()
    assert status["models_ready"] is True and status["missing"] == []


def test_r6_missing_engine_rules(defaults, monkeypatch):
    from services import tts_backend

    monkeypatch.setattr(tts_backend, "active_backend_id", lambda: "voxcpm2")
    monkeypatch.setattr(tts_backend, "get_backend_class", lambda backend_id: _NotReady)
    assert defaults.missing_default_engine() == []  # flag unset
    monkeypatch.setenv(FLAG, "voxcpm2")
    assert [m["repo_id"] for m in defaults.missing_default_engine()] == ["engine:voxcpm2"]

    def boom(backend_id):
        raise RuntimeError("probe failed")
    monkeypatch.setattr(tts_backend, "get_backend_class", boom)  # doubt keeps the requirement
    assert defaults.missing_default_engine() == [
        {"repo_id": "engine:voxcpm2", "label": "voxcpm2 engine"}
    ]


def test_r7_status_response_keeps_the_engine_entry(setup):
    from api.schemas import SetupStatusResponse

    wizard, choose = setup
    choose("voxcpm2", _NotReady, downloaded={VOXCPM2})
    response = SetupStatusResponse(**wizard.setup_status())
    assert [m.repo_id for m in response.missing] == ["engine:voxcpm2"]


def test_r8_recommendations_mark_the_default_engine_required(setup, monkeypatch):
    models = importlib.import_module("api.routers.setup.models")
    wizard, _ = setup
    monkeypatch.setattr(models, "KNOWN_MODELS", wizard.KNOWN_MODELS)
    flags = {m["repo_id"]: m["required"] for m in models.recommendations()["models"]}
    assert flags[VOXCPM2] is True
    assert flags.get("k2-fsa/OmniVoice") is not True


def test_r9_catalogue_load_applies_the_profile():
    code = (
        "import json, sys; sys.path.insert(0, 'backend');"
        "from services.model_catalogue import KNOWN_MODELS, model_key;"
        "print(json.dumps([model_key(m) for m in KNOWN_MODELS if m.get('required')]))"
    )

    def required_at_load(flag):
        env = {k: v for k, v in os.environ.items() if k != FLAG}
        if flag:
            env[FLAG] = flag
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                             capture_output=True, text=True, check=True).stdout
        return json.loads(out.strip().splitlines()[-1])
    assert required_at_load(None) == ["k2-fsa/OmniVoice"]
    assert required_at_load("voxcpm2") == [VOXCPM2]
