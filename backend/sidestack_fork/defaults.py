"""SideStack fork (VS-19): the default TTS engine comes from the SideStack profile.

SIDESTACK_DEFAULT_TTS_BACKEND names the engine used while neither
OMNIVOICE_TTS_BACKEND nor a choice saved in Settings names one. Unlike
OMNIVOICE_TTS_BACKEND it does not pin the engine, so the Settings picker
still works. Unset or blank, upstream's default is unchanged.
"""
from __future__ import annotations

import os

ENV_FLAG = "SIDESTACK_DEFAULT_TTS_BACKEND"


def default_tts_backend(upstream_default: str) -> str:
    """The profile's default engine id, or upstream's when none is set."""
    return os.environ.get(ENV_FLAG, "").strip() or upstream_default


def apply_required_default(models: list[dict]) -> None:
    """VS-23: the default engine's weights become the required first-run model.

    With the flag set, the TTS catalogue rows the default engine loads become
    ``required``, and every other TTS row stops being required (upstream requires
    OmniVoice). When no row names the default engine, the catalogue is left as
    upstream wrote it. Changes the rows in place.
    """
    engine = os.environ.get(ENV_FLAG, "").strip()
    if not engine:
        return
    tts = [m for m in models if str(m.get("role", "")).upper() == "TTS"]
    if not any(engine in (m.get("engines") or []) for m in tts):
        return
    for m in tts:
        if engine in (m.get("engines") or []):
            m["required"] = True
        elif m.get("required"):
            m["required"] = False


def missing_default_engine() -> list[dict]:
    """VS-23: the default engine as a first-run gap while it is chosen but not ready.

    Empty when the flag is unset, when another engine is chosen (upstream's
    #3581 rule decides then), or when the engine is ready. A failed probe
    reports the engine as missing, so setup never finishes without a voice.
    The entry's repo_id is "engine:<id>", which is not a catalogue key.
    """
    engine = os.environ.get(ENV_FLAG, "").strip()
    if not engine:
        return []
    from services import tts_backend

    label = f"{engine} engine"
    try:
        if tts_backend.active_backend_id() != engine:
            return []
        cls = tts_backend.get_backend_class(engine)
        label = f"{cls.display_name} engine"
        if cls.is_available()[0]:
            return []
    except Exception:  # noqa: BLE001 — doubt keeps the requirement
        pass
    return [{"repo_id": f"engine:{engine}", "label": label}]
