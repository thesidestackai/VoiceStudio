"""SideStack fork — VS-04: first-class ``ods`` LLM provider.

The ``ods`` provider is the SideStack local model relay (llama.cpp behind the
ODS model-router): loopback base URL, ``ods/current`` model, keyed via
``ODS_LOCAL_MODEL_RELAY_KEY``. The key travels only over loopback/HTTPS
(``credential_transport_error``), which is why the provider is keyed rather
than ``local``.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def lp(monkeypatch, clean_llm_env):
    """llm_providers with settings_store backed by in-memory dicts (no SQLite).

    clean_llm_env (conftest) clears the FULL provider env surface — a partial
    list left other providers' keys standing when an earlier `main` import
    dotenv-loaded them into os.environ, breaking precedence asserts (#878).
    """
    from services import settings_store as ss
    from services import llm_providers as _lp

    text: dict[str, str] = {}
    secrets: dict[str, str] = {}

    monkeypatch.setattr(ss, "get_text", lambda k, default=None: text.get(k, default))
    monkeypatch.setattr(ss, "set_text", lambda k, v: text.__setitem__(k, v))
    monkeypatch.setattr(ss, "get_secret", lambda n: secrets.get(n))
    monkeypatch.setattr(ss, "set_secret", lambda n, v: secrets.__setitem__(n, v) if v else secrets.pop(n, None))
    monkeypatch.setattr(ss, "list_secret_names", lambda: list(secrets))
    _lp._text, _lp._secrets = text, secrets  # handles for the test to seed
    return _lp


def test_ods_provider_defaults(lp):
    """P1: the ods provider exists with the relay defaults."""
    p = lp.get_provider("ods")
    assert p is not None
    assert p.id == "ods"
    assert p.default_base_url == "http://127.0.0.1:4007/v1"
    assert p.default_model == "ods/current"
    assert p.transport == "openai"
    assert p.local is False


def test_ods_env_key_resolves(lp, monkeypatch):
    """P2: ODS_LOCAL_MODEL_RELAY_KEY is the provider's key source."""
    p = lp.get_provider("ods")
    monkeypatch.setenv("ODS_LOCAL_MODEL_RELAY_KEY", "test-key")
    assert lp.has_key(p) is True
    assert lp.configuration_error(p) is None
    assert lp.resolve_api_key(p) == "test-key"


def test_ods_missing_key_configuration_error(lp):
    """P3: without a key env the configuration error mentions the API key."""
    p = lp.get_provider("ods")
    err = lp.configuration_error(p)
    assert err is not None
    assert "API key" in err


def test_ods_remote_plaintext_url_refused(lp, monkeypatch):
    """P4: a non-loopback plaintext HTTP URL is refused for a keyed provider."""
    p = lp.get_provider("ods")
    monkeypatch.setenv("ODS_LOCAL_MODEL_RELAY_KEY", "test-key")
    monkeypatch.setenv("ODS_BASE_URL", "http://192.168.1.50:4007/v1")
    assert lp.credential_transport_error(p) is not None


def test_ods_loopback_url_allowed(lp, monkeypatch):
    """P5: a loopback plaintext HTTP URL is allowed."""
    p = lp.get_provider("ods")
    monkeypatch.setenv("ODS_LOCAL_MODEL_RELAY_KEY", "test-key")
    monkeypatch.setenv("ODS_BASE_URL", "http://localhost:4007/v1")
    assert lp.credential_transport_error(p) is None


def test_ods_llm_default_provider_pin(lp, monkeypatch):
    """P6: LLM_DEFAULT_PROVIDER=ods activates the provider."""
    monkeypatch.setenv("LLM_DEFAULT_PROVIDER", "ods")
    assert lp.active_provider_id() == "ods"


def test_ods_model_env_override(lp, monkeypatch):
    """P7: ODS_MODEL overrides the default model (discovery must not probe)."""
    p = lp.get_provider("ods")
    monkeypatch.setattr(lp, "discover_model", lambda prov: pytest.fail("discovery probed"))
    monkeypatch.setenv("ODS_MODEL", "default")
    assert lp.resolve_model(p) == "default"
