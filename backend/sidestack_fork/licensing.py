"""SideStack fork (VS-18): commercial-only mode.

With SIDESTACK_COMMERCIAL_ONLY=1 (the SideStack profile's default), Voice
Studio refuses every model whose licence category in the model-licence
registry is not "commercial": non-commercial models such as OmniVoice, and
models with conditions or an unknown licence. An accepted licence does not
override it. Start the launcher with -AllowNonCommercial for private work.
Unset, upstream behaviour is unchanged. Registry categories come from model
cards; they are not legal advice.
"""
from __future__ import annotations

import os
from typing import Iterable

from services.model_acceptance import ModelLicenceNotAccepted

ENV_FLAG = "SIDESTACK_COMMERCIAL_ONLY"
ERROR_CODE = "commercial_only_mode"
_ON = {"1", "true", "yes", "on"}


def enabled() -> bool:
    return os.environ.get(ENV_FLAG, "").strip().lower() in _ON


class CommercialOnlyRefused(ModelLicenceNotAccepted):
    """A model refused by commercial-only mode (HTTP 403 via the same handler)."""

    def __init__(self, models: list[dict]):
        super().__init__(models, reason="commercial_only")
        names = ", ".join(f"{m['repo_id']} ({m['category']})" for m in models)
        verb = "is" if len(models) == 1 else "are"
        self.args = (
            f"Commercial-only mode is on: {names} {verb} not licensed for commercial use. "
            "Choose a commercial-licence engine such as VoxCPM2, or start Voice Studio "
            "with -AllowNonCommercial for private work.",
        )

    def detail(self) -> dict:
        return {"code": ERROR_CODE, "message": str(self), "models": self.models}


def ensure_commercial_only(repo_ids: Iterable[str]) -> None:
    """Raise CommercialOnlyRefused when the mode is on and a model is not commercial."""
    if not enabled():
        return
    from services.model_acceptance import status

    refused = []
    for repo_id in dict.fromkeys(r for r in repo_ids if r):
        state = status(repo_id)
        if state.get("category") != "commercial":
            refused.append({
                "repo_id": repo_id,
                "license": state.get("license"),
                "category": state.get("category") or "unknown",
            })
    if refused:
        raise CommercialOnlyRefused(refused)


def ensure_engine_commercial_only(engine_id: str) -> None:
    """ensure_commercial_only for the registry models an engine loads."""
    if not enabled():
        return
    from services.model_acceptance import repos_for_engine

    try:
        repos = repos_for_engine(engine_id)
    except Exception as exc:  # noqa: BLE001 — an unreadable registry must not open the gate
        raise ModelLicenceNotAccepted([], reason="registry_unreadable") from exc
    ensure_commercial_only(repos)


def refusal(repo_ids: Iterable[str]) -> CommercialOnlyRefused | None:
    """The refusal ensure_commercial_only would raise for these models, or None."""
    try:
        ensure_commercial_only(repo_ids)
    except CommercialOnlyRefused as exc:
        return exc
    return None


def engine_refusal(engine_id: str) -> ModelLicenceNotAccepted | None:
    """The refusal for an engine when the mode refuses every registry model it loads.

    An engine with no registry rows, or with at least one commercial model (a
    multi-model engine such as sherpa-onnx-asr), is not refused here: its models
    carry their own refusal, and loading still checks the model in use (VS-18).
    """
    if not enabled():
        return None
    from services.model_acceptance import repos_for_engine

    try:
        repos = repos_for_engine(engine_id)
    except Exception:  # noqa: BLE001 — an unreadable registry must not open the gate
        return ModelLicenceNotAccepted([], reason="registry_unreadable")
    if repos and all(refusal([repo]) is not None for repo in repos):
        return refusal(repos)
    return None


def refusal_text(refused: ModelLicenceNotAccepted | None) -> str | None:
    """The `commercial_only_refusal` listing field: the refusal's message, or None."""
    return None if refused is None else str(refused)
