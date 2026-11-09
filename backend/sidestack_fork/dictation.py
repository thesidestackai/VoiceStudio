"""SideStack fork (VS-14): dictation through Voice Studio's configured
OpenAI-compatible ASR server (ODS Whisper in the SideStack profile), so
dictation never loads a second, local Whisper beside ODS.

Opt-in with SIDESTACK_DICTATION_ODS=1. An explicitly selected sherpa-onnx
dictation model still wins: it runs on the CPU and is the user's choice.
"""
from __future__ import annotations

import os

ENV_FLAG = "SIDESTACK_DICTATION_ODS"
CAPTURE_KEY = "sidestack:openai-compat-asr"


def enabled() -> bool:
    return os.environ.get(ENV_FLAG, "").strip() == "1"


def remote_capture_active() -> bool:
    """True when dictation should use the openai-compat-asr backend."""
    if not enabled():
        return False
    from services.asr_backend import OpenAICompatASRBackend, active_backend_id

    if active_backend_id() != "openai-compat-asr":
        return False
    ok, _reason = OpenAICompatASRBackend.is_available()
    return ok
