# VS-04 — First-class `ods` LLM provider

- **Phase:** 2
- **Run by:** dsh
- **Gate:** none (code + mocked tests only)
- **Depends on:** VS-02 (baseline counts); VS-03 if its model id differs from `ods/current`
- **Status:** ready

## Goal

Voice Studio lists **"ODS (SideStack local)"** as an LLM provider. It works out of the box when
the Windows user env var `ODS_LOCAL_MODEL_RELAY_KEY` is set: base URL
`http://127.0.0.1:4007/v1`, model `ods/current`, and the key is sent only over loopback or HTTPS
(the existing `credential_transport_error` rule). The launcher can then use
`LLM_DEFAULT_PROVIDER=ods` instead of the generic `custom` provider.

## Files

| Path | Change |
|---|---|
| `backend/services/llm_providers.py` | edit: add one `Provider(...)` entry to `_PROVIDERS`, directly **before** the `Provider("ollama", ...)` entry |
| `tests/test_sidestack_ods_provider.py` | create: tests below |

No `changelog.d/` fragment (see AGENTS-SIDESTACK §2). The reviewer updates `sidestack/lanes/README.md`.

## Preflight

```powershell
cd E:\SideStackAI\worktrees\deepseek\voicestudio-001
git status --short    # expect: empty
Select-String backend\services\llm_providers.py -Pattern 'Provider\("ollama"'   # expect: exactly 1 match
$env:HF_HUB_OFFLINE="1"; .\.venv\Scripts\python.exe -m pytest tests/test_llm_providers.py tests/test_llm_providers_router.py -q   # expect: the VS-02 baseline count, all pass
```

## Steps

1. Insert before the `ollama` entry (keep the surrounding comment style):
   ```python
       # SideStack fork: ODS local model relay (llama.cpp behind ODS model-router).
       # Keyed, so not ``local``; the key travels only over loopback/HTTPS per
       # credential_transport_error.
       Provider("ods", "ODS (SideStack local)", "http://127.0.0.1:4007/v1", "ods/current",
                key_envs=("ODS_LOCAL_MODEL_RELAY_KEY",), base_url_env="ODS_BASE_URL",
                model_env="ODS_MODEL",
                notes="SideStack ODS through the local model relay. Set ODS_LOCAL_MODEL_RELAY_KEY."),
   ```
2. Create `tests/test_sidestack_ods_provider.py`. Reuse the `lp` fixture pattern from
   `tests/test_llm_providers.py`; read only its first 60 lines to copy the fixture. Tests:
   - **P1** `get_provider("ods")` exists; default base URL `http://127.0.0.1:4007/v1`; default model `ods/current`; `transport == "openai"`; `local is False`.
   - **P2** with `ODS_LOCAL_MODEL_RELAY_KEY=test-key` set: `has_key` is True, `configuration_error(p)` is None, `resolve_api_key(p) == "test-key"`.
   - **P3** with no key env set: `configuration_error(p)` mentions the API key.
   - **P4** with `ODS_BASE_URL=http://192.168.1.50:4007/v1` and a key: `credential_transport_error(p)` is not None (a remote plaintext URL is refused).
   - **P5** with `ODS_BASE_URL=http://localhost:4007/v1` and a key: `credential_transport_error(p)` is None.
   - **P6** with `LLM_DEFAULT_PROVIDER=ods`: `active_provider_id() == "ods"`.
   - **P7** `ODS_MODEL=default` overrides the model (`resolve_model(p) == "default"`), with discovery mocked off if `resolve_model` probes.
   Clear `OPENAI_API_KEY`, `TRANSLATE_*` and `ODS_*` env vars in each test with `monkeypatch.delenv(..., raising=False)`.

## Acceptance

```powershell
$env:HF_HUB_OFFLINE="1"
.\.venv\Scripts\python.exe -m pytest tests/test_sidestack_ods_provider.py -q          # expect: 7 passed
.\.venv\Scripts\python.exe -m pytest tests/test_llm_providers.py tests/test_llm_providers_router.py tests/test_lmstudio_model_discovery.py -q   # expect: baseline count, 0 failed
git status --short    # expect: exactly the 2 files above
python sidestack/scripts/check_sidestack.py           # expect: OK
```

The reviewer also mutation-checks the new tests: remove the entry → P1–P7 fail; change the
default URL host to `0.0.0.0` → P1 fails; drop `key_envs` → P2 fails.

## Out of scope

- UI or locale changes. Provider names come from the backend, so no new i18n strings are needed. If the settings page shows an untranslated label, record it for VS-11.
- Changing `custom`, `openai` or any other provider.

## Reviewer notes

—
