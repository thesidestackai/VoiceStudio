# VS-22 — Commercial-only mode in the Model Library

- **Phase:** 4
- **Run by:** dsh does Part A (code and offline tests). The Operator does Part B (rebuild the web UI, live look, no downloads).
- **Gate:**
  - none for Part A;
  - **real run approval** for Part B: rebuild `frontend/dist`, start Voice Studio in its default profile, read the listings, try one refused select, and look at Settings → Models.
- **Depends on:** VS-21
- **Status:** verified (Part B PASS, 2026-11-08)

## Goal

With `SIDESTACK_COMMERCIAL_ONLY=1` (the SideStack profile's default), Settings → Models stops offering what the server refuses. Refused models get no Download, Repair or Select, and refused engines get no Select or setup. Refused engines and stand-alone models fold into the existing "Unavailable" group. Without the flag, nothing changes.

**Why (VS-21 Part B, 2026-11-08):**
- VS-21 made the server refuse non-commercial downloads.
- The Model Library still showed "Download" and "Select" on the OmniVoice rows. A click only produced a red error.
- "Select" also still saved a refused engine as the TTS engine, which every generation then refused.

**Fix:**

| Where | Change |
|---|---|
| `GET /models` rows | new `commercial_only_refusal`: the refusal message, or `null`. It checks the same models as the install route (catalogue key + dependencies, VS-21). |
| `GET /engines` backends (tts, asr, llm) | new `commercial_only_refusal`: set when the mode refuses **every** registry model the engine loads. |
| `POST /engines/select` | refuses such an engine with **403** `commercial_only_mode`, before upstream's "not ready" check. |
| Model Library (`model-actions.tsx`, `engine-family-list.tsx`, `model-line.tsx`) | a refused model: Download/Repair disabled and labelled "Unavailable" (tooltip: the refusal), no Select. A refused engine: no Select, no setup (one-click install, licence, audio.cpp runtime), no GGUF quant picker, an "Unavailable" badge (tooltip: the refusal), the refusal as its summary, folded into "Unavailable" unless it is the active engine. |

**Rules:**
- **An engine is refused only when all its registry models are.** A multi-model engine with at least one commercial model is not refused. Examples are sherpa-onnx-asr, mlx-audio and mlx-whisper. Each of its models carries its own refusal instead, and loading still checks the model in use (VS-18).
- An engine with no registry rows is never refused here, for example openai-compat.
- An unreadable registry refuses every engine (fail closed), as VS-18 and VS-21 do.
- The tooltip and summary show the server's English message. Labels reuse the existing "Unavailable" string, so no locale catalogue changes.

**What the profile now marks as refused** (registry checked 2026-11-08; categories come from model cards and are not legal advice):
- Engines: `omnivoice`, `omnivoice-subprocess`, `omnivoice-gguf`, `indextts2`, `supertonic3`, `audiocpp` (TTS); `funasr` (ASR).
- Catalogue rows: the VS-21 list (`k2-fsa/OmniVoice`, the whole `audio-cpp/audio.cpp-gguf` repo, `facebook/nllb-200-distilled-600M`, the MLX and sherpa-onnx models with unknown licences, …).
- VoxCPM2, KittenTTS, CosyVoice3, the dots-tts package, Systran faster-whisper and pyannote stay usable.

## Files

| Path | Change |
|---|---|
| `backend/sidestack_fork/licensing.py` | edit: add `refusal()`, `engine_refusal()`, `refusal_text()` |
| `backend/api/routers/setup/models.py` | edit: `commercial_only_refusal` on `GET /models` rows |
| `backend/api/routers/engines.py` | edit: `commercial_only_refusal` on `GET /engines` backends; refusal in `select_engine` |
| `electron/src/renderer/src/lib/api/types.ts`, `electron/src/renderer/src/features/settings/model-catalogue-query.ts` | edit: the field's type |
| `electron/src/renderer/src/features/settings/model-list/model-actions.tsx`, `model-line.tsx`, `engine-family-list.tsx` | edit: the UI rules above |
| `tests/test_sidestack_ui_refusal.py` | new: U1–U7 |
| `electron/src/renderer/src/features/settings/model-list/sidestack-commercial-only.test.tsx` | new: F1–F6 |
| `sidestack/lanes/VS-22-model-library-commercial-only.md`, `sidestack/lanes/README.md` | builder report / status |

## Preflight

Start with the environment block from AGENTS-SIDESTACK.md Hard law 9, run from the worktree root.

```powershell
git status --short     # expect: only this spec (new) and sidestack/lanes/README.md (its row)
Select-String backend\api\routers\setup\models.py -Pattern '^            "license_acceptance": _model_licence_acceptance\(key\),$'   # expect: 1 match
Select-String backend\api\routers\engines.py -Pattern '^    backends = public_backends\(module\.list_backends\(\)\)$'   # expect: 1 match
Select-String backend\api\routers\engines.py -Pattern '^    entry = available\[req\.backend_id\]$'   # expect: 1 match
Select-String electron\src\renderer\src\features\settings\model-list\engine-family-list.tsx -Pattern '^  const engineSelect = engine\.available \? \($'   # expect: 1 match
Test-Path tests\test_sidestack_ui_refusal.py   # expect: False
Test-Path electron\src\renderer\src\features\settings\model-list\sidestack-commercial-only.test.tsx   # expect: False
& $py -m pytest tests/test_sidestack_downloads.py -q -p no:cacheprovider   # expect: 8 passed
```

## Steps

Each "replace" below names text that occurs exactly once in its file. Keep the file's line endings.

1. At the end of `backend/sidestack_fork/licensing.py`, after `ensure_engine_commercial_only`, append (two blank lines before it, as between the other functions):
   ```python
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
   ```
   Keep one newline at the end of the file.
2. In `backend/api/routers/setup/models.py`, make 2 replacements.
   - In `list_models`, replace:
     ```python
         out = []
         host_tags = set(platform_tags)
     ```
     with:
     ```python
         out = []
         host_tags = set(platform_tags)
         # SideStack fork (VS-22): each row says why commercial-only mode refuses it, so
         # the UI offers no download. It checks what the install route checks (VS-21).
         from sidestack_fork.licensing import refusal, refusal_text
     ```
   - In the same function's row dict, replace:
     ```python
                 "license_acceptance": _model_licence_acceptance(key),
             })
     ```
     with:
     ```python
                 "license_acceptance": _model_licence_acceptance(key),
                 "commercial_only_refusal": refusal_text(
                     refusal([key, *(d["repo_id"] for d in m.get("dependencies") or ())])
                 ),
             })
     ```
3. In `backend/api/routers/engines.py`, make 2 replacements.
   - In `_family_payload`, replace:
     ```python
         backends = public_backends(module.list_backends())
     ```
     with:
     ```python
         backends = public_backends(module.list_backends())
         # SideStack fork (VS-22): engines commercial-only mode refuses outright, so the
         # UI offers no Select or setup for them.
         from sidestack_fork.licensing import engine_refusal, refusal_text
         for backend in backends:
             backend["commercial_only_refusal"] = refusal_text(engine_refusal(backend.get("id") or ""))
     ```
   - In `select_engine`, replace:
     ```python
         entry = available[req.backend_id]
         if not entry["available"]:
     ```
     with:
     ```python
         entry = available[req.backend_id]
         # SideStack fork (VS-22): commercial-only mode refuses to save an engine it would
         # refuse to load (403 commercial_only_mode).
         from sidestack_fork.licensing import engine_refusal
         refused = engine_refusal(req.backend_id)
         if refused is not None:
             raise refused
         if not entry["available"]:
     ```
4. In `electron/src/renderer/src/lib/api/types.ts`, in `EngineBackend`, replace:
   ```ts
     license_accepted?: boolean;
     effective_device?: string;
   ```
   with:
   ```ts
     license_accepted?: boolean;
     /** SideStack fork (VS-22): why commercial-only mode refuses this engine, or null. */
     commercial_only_refusal?: string | null;
     effective_device?: string;
   ```
5. In `electron/src/renderer/src/features/settings/model-catalogue-query.ts`, in `CatalogueModel`, replace:
   ```ts
     license_acceptance?: ModelLicenceAcceptance;
   }
   ```
   with:
   ```ts
     license_acceptance?: ModelLicenceAcceptance;
     /** SideStack fork (VS-22): why commercial-only mode refuses this entry, or null. */
     commercial_only_refusal?: string | null;
   }
   ```
6. In `electron/src/renderer/src/features/settings/model-list/model-actions.tsx`, make 4 replacements.
   - In `ModelActions`, replace:
     ```tsx
       const busy = Boolean(ops.pending);
     ```
     with:
     ```tsx
       const busy = Boolean(ops.pending);
       // SideStack fork (VS-22): commercial-only mode refuses this entry's download and use.
       const refusal = model.commercial_only_refusal ?? undefined;
     ```
   - Replace:
     ```tsx
               {select}
     ```
     with:
     ```tsx
               {!refusal && select}
     ```
   - Replace the Repair button's opening:
     ```tsx
               <Button
                 size="sm"
                 variant="outline"
                 disabled={busy || !model.supported}
                 onClick={() => void ops.install(model.repo_id)}
               >
                 <WrenchIcon />
     ```
     with:
     ```tsx
               <Button
                 size="sm"
                 variant="outline"
                 disabled={busy || !model.supported || Boolean(refusal)}
                 title={refusal}
                 onClick={() => void ops.install(model.repo_id)}
               >
                 <WrenchIcon />
     ```
   - Replace the Download button:
     ```tsx
             <Button
               size="sm"
               variant="outline"
               disabled={busy || !model.supported}
               onClick={() => void ops.install(model.repo_id)}
             >
               <DownloadIcon />
               {t(model.supported ? 'modelMaintenance.download' : 'modelSettings.unavailable')}
             </Button>
     ```
     with:
     ```tsx
             <Button
               size="sm"
               variant="outline"
               disabled={busy || !model.supported || Boolean(refusal)}
               title={refusal}
               onClick={() => void ops.install(model.repo_id)}
             >
               <DownloadIcon />
               {t(
                 model.supported && !refusal ? 'modelMaintenance.download' : 'modelSettings.unavailable',
               )}
             </Button>
     ```
7. In `electron/src/renderer/src/features/settings/model-list/model-line.tsx`, in `modelFamilyItem`, replace:
   ```tsx
       folded: model.supported === false,
   ```
   with:
   ```tsx
       folded: model.supported === false || Boolean(model.commercial_only_refusal),
   ```
8. In `electron/src/renderer/src/features/settings/model-list/engine-family-list.tsx`, make 7 replacements.
   - In `engineItem`, replace:
     ```tsx
       const licenseId = licensedEngine(engine.id, engine.license_required, engine.license_accepted);
       const engineSelect = engine.available ? (
     ```
     with:
     ```tsx
       const licenseId = licensedEngine(engine.id, engine.license_required, engine.license_accepted);
       // SideStack fork (VS-22): commercial-only mode refuses this engine outright.
       const refusal = engine.commercial_only_refusal ?? undefined;
       const usable = engine.available && !refusal;
       // No setup either: the server refuses that install too (VS-21).
       const noSetup = engine.available || Boolean(refusal);
       const engineSelect = usable ? (
     ```
   - Replace:
     ```tsx
       const setup: ReactNode = engine.available ? null : licenseId ? (
     ```
     with:
     ```tsx
       const setup: ReactNode = noSetup ? null : licenseId ? (
     ```
   - Replace:
     ```tsx
               {engine.id === GGUF_ENGINE && engine.available && <GgufQuantPicker />}
     ```
     with:
     ```tsx
               {engine.id === GGUF_ENGINE && usable && <GgufQuantPicker />}
     ```
   - Replace:
     ```tsx
         summary: engineSummary(ctx, engine, active),
     ```
     with:
     ```tsx
         summary: refusal ?? engineSummary(ctx, engine, active),
     ```
   - Replace:
     ```tsx
             {!engine.available && (
               <StatusBadge tone="muted" title={engineUnavailableReason(engine.reason, t) || undefined}>
     ```
     with:
     ```tsx
             {(!engine.available || refusal) && (
               <StatusBadge
                 tone="muted"
                 title={refusal ?? (engineUnavailableReason(engine.reason, t) || undefined)}
               >
     ```
   - Replace:
     ```tsx
           ready: engine.available,
     ```
     with:
     ```tsx
           ready: usable,
     ```
   - Replace:
     ```tsx
         folded:
           !engine.available &&
           !engine.one_click_install &&
           !licenseId &&
           linked.length > 0 &&
           linked.every((model) => model.supported === false),
     ```
     with:
     ```tsx
         folded:
           (Boolean(refusal) && !active) ||
           (!engine.available &&
             !engine.one_click_install &&
             !licenseId &&
             linked.length > 0 &&
             linked.every((model) => model.supported === false)),
     ```
9. Create `tests/test_sidestack_ui_refusal.py` with exactly this content:
   ```python
   """SideStack VS-22 — commercial-only mode in the listings the UI reads.

   GET /models rows and GET /engines backends carry `commercial_only_refusal`
   (the refusal message, or None), and POST /engines/select refuses an engine the
   mode refuses outright. Route functions are called directly; nothing is
   downloaded or saved. Acceptance records are kept in memory.
   """
   from __future__ import annotations

   import importlib
   import os
   import sys

   import pytest

   sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

   os.environ.setdefault("OMNIVOICE_MODEL", "test")
   os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

   from fastapi import HTTPException  # noqa: E402

   ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

   pytestmark = pytest.mark.model_licence_gate

   # Engines whose every registry model is not commercial (registry checked 2026-11-08).
   REFUSED_ENGINES = {
       "omnivoice", "omnivoice-subprocess", "omnivoice-gguf", "indextts2",
       "supertonic3", "audiocpp", "funasr",
   }


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
   def models(monkeypatch):
       mod = importlib.import_module("api.routers.setup.models")
       monkeypatch.setattr(mod, "_cache", {})
       return mod


   @pytest.fixture
   def eng(monkeypatch):
       mod = importlib.import_module("api.routers.engines")
       saved: list[tuple[str, str]] = []
       monkeypatch.setattr(mod.prefs, "set_", lambda key, value: saved.append((key, value)))
       monkeypatch.setattr(mod, "saved", saved, raising=False)
       return mod


   def _rows(models):
       models._cache.clear()
       return {row["repo_id"]: row for row in models.list_models()["models"]}


   def _select(eng, family, backend_id):
       return eng.select_engine(eng.SelectEngineRequest(family=family, backend_id=backend_id))


   def test_u1_hooks_in_place():
       def read(*parts):
           with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
               return f.read()
       assert read("backend", "api", "routers", "setup", "models.py").count("SideStack fork (VS-22)") == 1
       assert read("backend", "api", "routers", "engines.py").count("SideStack fork (VS-22)") == 2
       assert "def engine_refusal(" in read("backend", "sidestack_fork", "licensing.py")


   def test_u2_catalogue_rows(lic, models, monkeypatch):
       fake = {"repo_id": "sidestack-test/needs-omnivoice", "label": "Test", "role": "tts",
               "size_gb": 0.1, "dependencies": [{"repo_id": "k2-fsa/OmniVoice"}]}
       monkeypatch.setattr(models, "KNOWN_MODELS", [*models.KNOWN_MODELS, fake])
       rows = _rows(models)  # flag unset: no row is refused
       assert all(row["commercial_only_refusal"] is None for row in rows.values())
       monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
       rows = _rows(models)
       assert "k2-fsa/OmniVoice (noncommercial)" in rows["k2-fsa/OmniVoice"]["commercial_only_refusal"]
       assert "audio-cpp/audio.cpp-gguf (noncommercial)" in rows["audio-cpp/audio.cpp-gguf"]["commercial_only_refusal"]
       # The catalogue key is the licence record: a commercial package in that repo passes.
       assert rows["audio-cpp/audio.cpp-gguf:dots-tts-soar-q8_0"]["commercial_only_refusal"] is None
       assert rows["openbmb/VoxCPM2"]["commercial_only_refusal"] is None
       # Dependencies count, as on the install route.
       assert "k2-fsa/OmniVoice" in rows["sidestack-test/needs-omnivoice"]["commercial_only_refusal"]


   def test_u3_engine_rows(lic, eng, monkeypatch):
       def refused(family, module):
           payload = eng._family_payload(family, module)
           return {b["id"] for b in payload["backends"] if b["commercial_only_refusal"]}
       assert refused("tts", eng.tts_backend) == set()  # flag unset
       monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
       tts = refused("tts", eng.tts_backend)
       assert {"omnivoice", "indextts2", "supertonic3"} <= tts
       assert not tts & {"voxcpm2", "kittentts", "mlx-audio"}
       asr = refused("asr", eng.asr_backend)
       assert "funasr" in asr and not asr & {"sherpa-onnx-asr", "faster-whisper", "pytorch-whisper"}
       assert refused("llm", eng.llm_backend) == set()


   def test_u4_select_refuses(lic, eng, monkeypatch):
       with pytest.raises(HTTPException) as off:  # flag unset: upstream's "not ready" 400
           _select(eng, "tts", "indextts2")
       assert off.value.status_code == 400
       monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
       for engine_id in ("omnivoice", "indextts2"):  # the refusal comes before "not ready"
           with pytest.raises(lic.CommercialOnlyRefused) as on:
               _select(eng, "tts", engine_id)
           assert on.value.detail()["code"] == "commercial_only_mode"
       assert eng.saved == []
       _select(eng, "tts", "kittentts")
       assert eng.saved == [("tts_backend", "kittentts")]
       with pytest.raises(HTTPException) as unknown:
           _select(eng, "tts", "no-such-engine")
       assert unknown.value.status_code == 400


   def test_u5_engine_refusal_rules(lic, monkeypatch):
       assert lic.engine_refusal("omnivoice") is None  # flag unset
       monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
       refused = lic.engine_refusal("omnivoice")
       assert isinstance(refused, lic.CommercialOnlyRefused)
       assert "k2-fsa/OmniVoice" in [m["repo_id"] for m in refused.models]
       assert lic.engine_refusal("sherpa-onnx-asr") is None  # has commercial models too
       assert lic.engine_refusal("openai-compat") is None  # no registry rows
       assert lic.engine_refusal("voxcpm2") is None
       assert lic.refusal(["openbmb/VoxCPM2"]) is None
       assert lic.refusal_text(None) is None
       assert lic.refusal_text(lic.refusal(["k2-fsa/OmniVoice"])) == str(lic.refusal(["k2-fsa/OmniVoice"]))


   def test_u6_registry_unreadable_fails_closed(lic, monkeypatch):
       _ma = importlib.import_module("services.model_acceptance")

       def boom(engine_id, identity=None):
           raise OSError("registry unreadable")
       monkeypatch.setattr(_ma, "repos_for_engine", boom)
       assert lic.engine_refusal("voxcpm2") is None  # flag unset
       monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
       refused = lic.engine_refusal("voxcpm2")
       assert isinstance(refused, _ma.ModelLicenceNotAccepted)
       assert refused.reason == "registry_unreadable"
       assert lic.refusal_text(refused) == str(refused)


   def test_u7_refused_engine_set(lic, monkeypatch):
       """Which engines the mode refuses outright. A registry change shows up here."""
       eng = importlib.import_module("api.routers.engines")
       monkeypatch.setenv("SIDESTACK_COMMERCIAL_ONLY", "1")
       ids = [b["id"] for b in eng.tts_backend.list_backends(include_hidden=True)]
       ids += [b["id"] for b in eng.asr_backend.list_backends()]
       ids += [b["id"] for b in eng.llm_backend.list_backends()]
       assert {i for i in ids if lic.engine_refusal(i) is not None} == REFUSED_ENGINES
   ```
   Keep one newline at the end of the file.
10. Create `electron/src/renderer/src/features/settings/model-list/sidestack-commercial-only.test.tsx` with exactly this content (LF line endings, like the other new files):
   ```tsx
   // SideStack fork (VS-22): commercial-only mode in Settings -> Models. A refused
   // engine or model offers no Download, Select or setup; refused engines fold
   // into "Unavailable" unless active.
   import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
   import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
   import type { ReactNode } from 'react';
   import { afterEach, expect, it, vi } from 'vitest';

   const mock = vi.hoisted(() => ({
     api: vi.fn(),
     t: vi.fn<(key: string, options?: Record<string, unknown>) => string>((key) => key),
     toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
   }));
   vi.mock('@/lib/api/client', () => ({ apiJson: mock.api, describeError: String }));
   vi.mock('sonner', () => ({ toast: mock.toast }));
   vi.mock('@/hooks/use-backend-status', () => ({ useBackendStatus: () => ({ stage: 'ready' }) }));
   vi.mock('@tanstack/react-router', () => ({
     Link: ({ to, children }: { to: string; children: ReactNode }) => <a href={to}>{children}</a>,
   }));
   vi.mock('react-i18next', () => ({
     useTranslation: () => ({ t: mock.t }),
   }));

   import { EngineFamilyList } from './engine-family-list';

   afterEach(() => {
     cleanup();
     vi.clearAllMocks();
   });

   const REFUSED = 'Commercial-only mode is on: k2-fsa/OmniVoice (noncommercial) is not licensed.';
   const base = { role: 'TTS', size_gb: 1, installed: false, supported: true };

   function serve({ active = 'voxcpm2', refuse = true } = {}) {
     const refusal = refuse ? REFUSED : null;
     mock.api.mockImplementation((path: string) => {
       if (path === '/models')
         return Promise.resolve({
           models: [
             {
               ...base,
               repo_id: 'k2-fsa/OmniVoice',
               label: 'OmniVoice weights',
               engines: ['omnivoice'],
               installed: active === 'omnivoice',
               commercial_only_refusal: refusal,
             },
             {
               ...base,
               repo_id: 'openbmb/VoxCPM2',
               label: 'VoxCPM2 weights',
               engines: ['voxcpm2'],
               installed: true,
               commercial_only_refusal: null,
             },
             {
               ...base,
               repo_id: 'mlx/kokoro',
               label: 'Kokoro',
               engines: ['mlx-audio'],
               commercial_only_refusal: refusal,
             },
             {
               ...base,
               repo_id: 'mlx/csm',
               label: 'CSM',
               engines: ['mlx-audio'],
               installed: true,
               commercial_only_refusal: null,
             },
             {
               ...base,
               repo_id: 'mlx/outetts',
               label: 'OuteTTS',
               engines: ['mlx-audio'],
               installed: true,
               commercial_only_refusal: refusal,
             },
             {
               ...base,
               repo_id: 'mlx/chatterbox',
               label: 'Chatterbox',
               engines: ['mlx-audio'],
               incomplete: true,
               commercial_only_refusal: refusal,
             },
             { ...base, repo_id: 'owner/loose', label: 'Loose model', commercial_only_refusal: refusal },
           ],
         });
       if (path === '/engines')
         return Promise.resolve({
           tts: {
             active,
             active_model: null,
             backends: [
               {
                 id: 'omnivoice',
                 display_name: 'OmniVoice',
                 available: true,
                 reason: null,
                 commercial_only_refusal: refusal,
               },
               {
                 id: 'voxcpm2',
                 display_name: 'VoxCPM2',
                 available: true,
                 reason: null,
                 commercial_only_refusal: null,
               },
               {
                 id: 'mlx-audio',
                 display_name: 'MLX-Audio',
                 available: true,
                 reason: null,
                 commercial_only_refusal: null,
                 curated_models: [
                   { key: 'kokoro', label: 'Kokoro', repo_id: 'mlx/kokoro' },
                   { key: 'csm', label: 'CSM', repo_id: 'mlx/csm' },
                   { key: 'outetts', label: 'OuteTTS', repo_id: 'mlx/outetts' },
                   { key: 'chatterbox', label: 'Chatterbox', repo_id: 'mlx/chatterbox' },
                 ],
               },
               {
                 id: 'omnivoice-gguf',
                 display_name: 'OmniVoice GGUF',
                 available: true,
                 reason: null,
                 commercial_only_refusal: refusal,
               },
               {
                 id: 'indextts2',
                 display_name: 'IndexTTS2',
                 available: false,
                 reason: null,
                 one_click_install: true,
                 commercial_only_refusal: refusal,
               },
             ],
           },
         });
       if (path === '/models/install/status') return Promise.resolve({ jobs: [] });
       if (path === '/model/loaded') return Promise.resolve({ models: [], count: 0 });
       if (path === '/engines/select') return Promise.resolve({ active: 'voxcpm2' });
       return Promise.resolve({});
     });
   }

   function renderList() {
     render(
       <QueryClientProvider client={new QueryClient()}>
         <EngineFamilyList family="tts" />
       </QueryClientProvider>,
     );
   }

   /** The whole row: name, badges and summary sit outside its actions group. */
   const row = (group: HTMLElement) => group.closest('[data-slot="model-row"]') as HTMLElement;

   const called = (prefix: string) =>
     mock.api.mock.calls.some(([path]) => String(path).startsWith(prefix));

   it('F1: a refused engine folds away and offers no download or select', async () => {
     serve();
     renderList();
     const omnivoice = await screen.findByRole('group', { name: 'OmniVoice' });
     expect(omnivoice.closest('details')).not.toBeNull();
     const download = await within(omnivoice).findByRole('button', {
       name: 'modelSettings.unavailable',
     });
     expect(download).toBeDisabled();
     expect(download).toHaveAttribute('title', REFUSED);
     expect(within(omnivoice).queryByRole('button', { name: 'modelSettings.select' })).toBeNull();
     expect(within(row(omnivoice)).getAllByText(REFUSED).length).toBeGreaterThan(0);
     fireEvent.click(download);
     expect(mock.api).not.toHaveBeenCalledWith('/models/install', expect.anything());
     // A refused model no engine claims folds away too.
     const loose = screen.getByRole('group', { name: 'Loose model' });
     expect(loose.closest('details')).not.toBeNull();
   });

   it('F2: a commercial engine stays in view with its select', async () => {
     serve({ active: 'omnivoice' });
     renderList();
     const voxcpm = await screen.findByRole('group', { name: 'VoxCPM2' });
     expect(voxcpm.closest('details')).toBeNull();
     fireEvent.click(await within(voxcpm).findByRole('button', { name: 'modelSettings.select' }));
     await waitFor(() =>
       expect(mock.api).toHaveBeenCalledWith(
         '/engines/select',
         expect.objectContaining({ body: JSON.stringify({ family: 'tts', backend_id: 'voxcpm2' }) }),
       ),
     );
   });

   it('F3: a refused active engine stays in view, marked unavailable, with no select', async () => {
     serve({ active: 'omnivoice' });
     renderList();
     const omnivoice = await screen.findByRole('group', { name: 'OmniVoice' });
     expect(omnivoice.closest('details')).toBeNull();
     expect(within(row(omnivoice)).getByText('modelSettings.unavailable')).toHaveAttribute(
       'title',
       REFUSED,
     );
     expect(within(omnivoice).queryByRole('button', { name: 'modelSettings.select' })).toBeNull();
   });

   it('F4: in a multi-model engine only the refused models lose download and select', async () => {
     serve({ active: 'omnivoice' });
     renderList();
     fireEvent.click(await screen.findByRole('button', { name: 'MLX-Audio' }));
     const csm = await screen.findByRole('group', { name: 'CSM' });
     expect(within(csm).getByRole('button', { name: 'modelSettings.select' })).toBeEnabled();
     const outetts = screen.getByRole('group', { name: 'OuteTTS' });
     expect(within(outetts).queryByRole('button', { name: 'modelSettings.select' })).toBeNull();
     const kokoro = screen.getByRole('group', { name: 'Kokoro' });
     expect(within(kokoro).getByRole('button', { name: 'modelSettings.unavailable' })).toBeDisabled();
     const chatterbox = screen.getByRole('group', { name: 'Chatterbox' });
     expect(within(chatterbox).getByRole('button', { name: 'modelMaintenance.repair' })).toBeDisabled();
   });

   it('F5: a refused engine offers no one-click install; unrefused, it does', async () => {
     serve();
     renderList();
     await screen.findByRole('group', { name: 'IndexTTS2' });
     expect(called('/engines/sidecar/')).toBe(false);
     cleanup();
     serve({ refuse: false });
     renderList();
     await screen.findByRole('group', { name: 'IndexTTS2' });
     await waitFor(() => expect(called('/engines/sidecar/')).toBe(true));
   });

   it('F6: a refused GGUF engine shows no quant picker; unrefused, it does', async () => {
     serve();
     renderList();
     fireEvent.click(await screen.findByRole('button', { name: 'OmniVoice GGUF' }));
     await screen.findByRole('group', { name: 'OmniVoice GGUF' });
     expect(called('/engines/omnivoice-gguf/quants')).toBe(false);
     cleanup();
     serve({ refuse: false });
     renderList();
     fireEvent.click(await screen.findByRole('button', { name: 'OmniVoice GGUF' }));
     await waitFor(() => expect(called('/engines/omnivoice-gguf/quants')).toBe(true));
   });
   ```
   Keep one newline at the end of the file.
11. Run Acceptance and report in the AGENTS-SIDESTACK §4 format, listing every command. Append the report at the very end of this spec under a `## Builder report` heading, and set this lane's tracker status to `running (dsh done)`.

## Acceptance

```powershell
& $py -m pytest tests/test_sidestack_ui_refusal.py -q -p no:cacheprovider   # expect: 7 passed
& $py -m pytest tests/test_sidestack_licensing.py tests/test_sidestack_downloads.py tests/test_sidestack_defaults.py tests/test_sidestack_admission.py tests/test_catalogue_packages.py tests/test_engine_install_capability.py tests/test_active_cloning_capability.py tests/test_router_smoke.py tests/test_api_route_inventory.py tests/test_model_license_workflow.py -q -p no:cacheprovider   # expect: 0 failed
Push-Location electron
bun x vp test --run src/renderer/src/features/settings/model-list/sidestack-commercial-only.test.tsx   # expect: 6 passed
bun x vp test --run src/renderer/src/features/settings/   # expect: 0 failed
bun x tsc --noEmit -p tsconfig.web.json --tsBuildInfoFile ..\sidestack\work\tmp\web.tsbuildinfo   # expect: no output, exit 0
Pop-Location
git status --short    # expect: exactly the files in "Files"
Get-ChildItem -Force | Where-Object Name -match '^(pytest-of-|omnivoice-test-data-)'   # expect: nothing
python sidestack/scripts/check_sidestack.py           # expect: OK
```

`--tsBuildInfoFile` keeps tsc's build cache out of `node_modules\.tmp`, which the sandbox does not let it create.

## Part B — live check (Operator, after approval)

No step may start a download. If any transfer starts, `-Stop` at once and report.

1. Rebuild the web UI from the worktree: `bun run build:web`. It writes `frontend/dist`, which git ignores.
2. Start Voice Studio with the worktree launcher, default profile (commercial-only, VoxCPM2 default). Record the size of the Hugging Face cache under the data folder.
3. `GET /engines`: `commercial_only_refusal` is set on the engines listed in Goal that the host lists, and `null` on `voxcpm2` and `kittentts`. `GET /models`: set on `k2-fsa/OmniVoice`, `null` on `openbmb/VoxCPM2`.
4. `POST /engines/select` with `{"family": "tts", "backend_id": "omnivoice"}` → **403** `commercial_only_mode`. `/engines` `tts.active` stays `voxcpm2`.
5. In the web UI, Settings → Models → TTS:
   - the refused engines sit in the "Unavailable" fold;
   - OmniVoice's button reads "Unavailable", is disabled and has the refusal as its tooltip;
   - OmniVoice has no "Select" button;
   - VoxCPM2 is still shown as selected.
   Take a screenshot.
6. Check that the Hugging Face cache size has not changed, then `-Stop`. Record the results here.

## Out of scope

- Other places that start a download or a selection. They still get the server's 403 (VS-21, and this lane's select refusal):
  - the first-run wizard;
  - system recommendations;
  - the download-activity retry;
  - the Design page's engine picker and "Set up" button;
  - the Dub page's engine choice;
  - the engine notice.
- Translated refusal text. The tooltip and summary show the server's English message, as upstream's engine reasons do.
- Refusing a refused `model_id` on `POST /engines/select`. The only routes that take one are faster-whisper (all commercial) and mlx-audio (macOS). Loading checks the model in use (VS-18).

## Reviewer notes

- **Mutation checks.** Each of these was caught when the lane was written:
  - Backend (U-tests):
    - the `/models` row uses `m["repo_id"]` instead of the catalogue key, or drops the dependencies;
    - the `_family_payload` loop sets `None`;
    - `select_engine` does not raise the refusal;
    - `engine_refusal` uses `any` instead of `all`;
    - `engine_refusal` returns `None` for an unreadable registry, or loses its `if not enabled()` check.
  - Frontend (F-tests):
    - `{select}` is kept for a refused model;
    - Download or Repair stays enabled;
    - `usable` ignores the refusal;
    - `noSetup` ignores the refusal;
    - the GGUF picker uses `engine.available`;
    - refused engines are not folded, or the active one is folded too;
    - the badge or the summary loses the refusal;
    - stand-alone refused models are not folded.
- **Cost:** with the flag on, `GET /engines` spends about 5 ms per engine on `engine_refusal`, about 150 ms on a listing that already takes about 2.4 s here. With the flag off, nothing extra runs.
- **Known noise:**
  - `tests/test_engine_language_options.py` has two order-dependent failures under `-n 8`. They fail on HEAD too and pass alone.
  - `vp fmt --check` reports every CRLF file in this checkout (HEAD's too). To check formatting, copy the files with LF endings first; the edits above are formatted.
- U7 pins the set of refused engines, so a registry change after an upstream sync shows up as a test failure to review.
- **Checked while writing this lane (2026-11-08):** the spec text was applied to HEAD in a scratch run; U1–U7 and F1–F6 passed, the settings tests and tsc were clean, and all 18 mutations were caught. The engine list above came from the live registry.

## Builder run (dsh, 2026-11-08) — stopped, no report

The builder (Qwen 3.8 on ODS) was **stopped by the reviewer after 41 minutes**, before Acceptance and before it wrote a report. What happened:
- **Before reading the whole spec:** it wrote its own version of Steps 1–3. The 38 KB spec needed several context compactions to read. It then rewrote those steps from the spec.
- **Deviations left in its edits:**
  - In `models.py`, it moved the import above `out = []`.
  - It relabelled the Repair button, then reverted that.
  - It reworded one comment and dropped another in `engine-family-list.tsx`.
  - It left the badge unformatted.
- **What stopped the run:** it went past its brief and ran the Reviewer notes' mutation checks itself. Its own script ran `git checkout -- .`, which **wiped every tracked edit**: all of Steps 1–8, plus the reviewer's uncommitted tracker row.
- **When stopped:** it was re-applying the backend steps piecemeal. Its two new test files matched the spec byte for byte.

**Recovery (reviewer):**
- reset the three backend files to HEAD and removed the two test files;
- applied Steps 1–10 from this spec's text with the scratch dry-run tool (19 edits, 2 new files; each replace target matched once);
- re-added the tracker row.

The applied files match the spec applied to HEAD exactly. Lesson for later lanes: keep a lane spec small enough to read in one pass. Say in the builder prompt that Reviewer notes are not steps, and that `git checkout`, `git stash` and `git reset` are forbidden.

## Reviewer verification (2026-11-08)

**Part A PASS** (applied by the reviewer from this spec's text; see above).
- **Spec match:** all 8 edited files and both new test files match this spec applied to HEAD, byte for byte (line endings kept). The diff is 87 insertions and 17 deletions across the 8 files, plus the two new test files.
- **Acceptance, every line:**
  - U-tests: 7 passed.
  - Related backend tests: 170 passed, 0 failed.
  - F-tests: 6 passed.
  - Settings tests: 48 files, 263 passed.
  - `tsc` (web): exit 0.
  - No `pytest-of-*` or `omnivoice-test-data-*` folders.
  - `check_sidestack.py`: OK.
- **Full backend suite** (`-n 8`): 13,046 passed, 93 failed, 20 errors.
  - Every failing id is in the baseline (`pytmp\base.txt`); none is new.
  - 4 baseline failures now pass. They are order-dependent.
- **Full frontend suite** (`bun run test`: locale checks + both vitest configs): 394 files / 2,842 passed (12 skipped) and 339 files / 3,091 passed. No failures.
- **Mutation checks:** the 18 mutations in Reviewer notes were run on this exact code when the lane was written, and all 18 were caught.
- Part B is not run yet. It needs real run approval.

## Part B results (Operator, 2026-11-08)

**PASS.** Part A was committed first (bf6e8ef7c).
- **Setup:**
  - The web UI was rebuilt with `bun run build:web` (exit 0, 13 s). The new field is in the bundle, and git stayed clean.
  - Voice Studio was started with the worktree launcher in the default profile (commercial-only, VoxCPM2 default).
  - Hugging Face cache before: 17 files, 5,042,286,722 bytes (KittenTTS, VoxCPM2). The engines folder held only `voxcpm2`.
- **`GET /engines`:** `commercial_only_refusal` was set on exactly `omnivoice`, `omnivoice-subprocess`, `omnivoice-gguf`, `indextts2`, `supertonic3`, `audiocpp` (TTS) and `funasr` (ASR).
  - It was `null` on every other engine, including `voxcpm2`, `kittentts`, `sherpa-onnx-asr` (mixed models), `audiocpp-dots`, `openai-compat-asr` and both LLM entries.
  - The OmniVoice message names `k2-fsa/OmniVoice (noncommercial)` and `eustlb/higgs-audio-v2-tokenizer (unknown)`.
- **`GET /models`:** 10 of 42 rows were refused, including `k2-fsa/OmniVoice`. `openbmb/VoxCPM2`, `KittenML/kitten-tts-mini-0.8` and the dots-tts package were `null`.
- **`POST /engines/select` `{"family": "tts", "backend_id": "omnivoice"}`:** **403** `commercial_only_mode` with both models listed. `tts.active` stayed `voxcpm2`, and `prefs.json` has no `tts_backend`.
- **Web UI, Settings → Models → TTS:**
  - The "Unavailable (7)" fold holds the six refused TTS engines, plus MLX-Audio, which upstream already folds on Windows (macOS only).
  - Each refused engine shows its refusal as its summary.
  - OmniVoice, OmniVoice (subprocess) and audio.cpp Breeze-TTS-2 show a disabled "Unavailable" button. Its tooltip is the refusal (for example "Commercial-only mode is on: k2-fsa/OmniVoice (noncommercial) is not licensed for commercial use. …").
  - No refused engine has a Select, Install or Download button.
  - VoxCPM2 stays selected, and KittenTTS keeps its Select button.
  - The commercial engines keep their Install/Download buttons.
  - Screenshot taken.
- **Nothing downloaded:** no install jobs, the cache was the same 17 files and bytes afterwards, and the engines folder was unchanged.
- `-Stop` stopped the server.
