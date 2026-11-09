# VS-24 — First-run screen in the SideStack profile

- **Phase:** 4
- **Run by:** dsh does Part A (code and offline tests). The Operator does Part B (rebuild the web UI, live look at the first-run screen, no downloads).
- **Gate:**
  - none for Part A;
  - **real run approval** for Part B.
- **Depends on:** VS-22, VS-23
- **Status:** verified (Part B PASS, 2026-11-08)

## Goal

The first-run screen's models step works in the SideStack profile:
- Its model packs lead with the catalogue's required TTS model (VoxCPM2 after VS-23) and skip what commercial-only mode refuses.
- An `engine:<id>` gap from `/setup/status` (VS-23) gets an install button on that step.

With upstream data (OmniVoice required, nothing refused) the packs are unchanged.

**Why (VS-23):**
- Upstream's packs are fixed lists that start with OmniVoice. Three of their models are refused in commercial-only mode: OmniVoice, NLLB and `sherpa-onnx-whisper-tiny`; the sherpa-onnx Parakeet model has an unknown licence too.
- So "Install pack" would ask for refused downloads and never fetch VoxCPM2, the model setup now waits for.
- The VoxCPM2 engine could only be installed from the Advanced view.

**Fix:**
- `performance-model-packs.ts` `resolvePerformanceModelPack`:
  - prepends the catalogue rows marked `required` with role TTS, de-duplicated;
  - drops rows with a `commercial_only_refusal` (VS-22).
- `setup-gate.tsx`, models step: for each `missing` entry whose `repo_id` starts with `engine:`, it renders upstream's `EngineInstall` (`POST /engines/sidecar/<id>/install`, with progress), under the existing "still needed" line.

## Files

| Path | Change |
|---|---|
| `electron/src/renderer/src/features/settings/performance-model-packs.ts` | edit: 2 replacements |
| `electron/src/renderer/src/components/setup-gate.tsx` | edit: import + install buttons |
| `electron/src/renderer/src/components/sidestack-first-run.test.tsx` | new: G1–G2, P1–P3 |
| `sidestack/lanes/VS-24-first-run-screen.md`, `sidestack/lanes/README.md` | builder report / status |

## Preflight

Run from the worktree root.

```powershell
git status --short     # expect: only this spec (new) and sidestack/lanes/README.md (its row)
Select-String electron\src\renderer\src\features\settings\performance-model-packs.ts -Pattern '^  const selected = performancePackRepos\[tier\]$'   # expect: 1 match
Select-String electron\src\renderer\src\components\setup-gate.tsx -Pattern "^import \{ ModelSettings \} from '@/features/settings/model-settings';$"   # expect: 1 match
Test-Path electron\src\renderer\src\components\sidestack-first-run.test.tsx   # expect: False
```

## Steps

Each "replace" below names text that occurs exactly once in its file. Keep the file's line endings. Do not run `git checkout`, `git stash`, `git reset`, `git clean` or `git restore`.

1. In `electron/src/renderer/src/features/settings/performance-model-packs.ts`, make 2 replacements.
   - In `resolvePerformanceModelPack`, replace:
     ```ts
       const selected = performancePackRepos[tier]
         .map((repoId) => {
     ```
     with:
     ```ts
       // SideStack fork (VS-24): lead with the catalogue's required TTS model (the
       // profile's default engine, VS-23) and skip what commercial-only mode refuses.
       const required = models
         .filter((model) => model.required && model.role.toLowerCase() === 'tts')
         .map((model) => model.repo_id);
       const selected = [...new Set([...required, ...performancePackRepos[tier]])]
         .map((repoId) => {
     ```
   - In the same function, replace:
     ```ts
         .filter((model): model is CatalogueModel => Boolean(model?.supported));
     ```
     with:
     ```ts
         .filter(
           (model): model is CatalogueModel =>
             Boolean(model?.supported) && !model?.commercial_only_refusal,
         );
     ```
2. In `electron/src/renderer/src/components/setup-gate.tsx`, make 2 replacements.
   - Replace:
     ```tsx
     import { ModelSettings } from '@/features/settings/model-settings';
     ```
     with:
     ```tsx
     import { ModelSettings } from '@/features/settings/model-settings';
     import { EngineInstall } from '@/features/settings/engine-install';
     ```
   - In step 1, replace:
     ```tsx
                           {status.data?.missing?.map((model) => model.label).join(', ')}
                         </p>
                       )}
                     </>
     ```
     with:
     ```tsx
                           {status.data?.missing?.map((model) => model.label).join(', ')}
                         </p>
                       )}
                       {/* SideStack fork (VS-24): an "engine:<id>" gap (VS-23) is an engine
                           package, so offer its install here, not only in Advanced. */}
                       {status.data?.missing
                         ?.filter((model) => (model.repo_id || '').startsWith('engine:'))
                         .map((model) => (
                           <EngineInstall
                             key={model.repo_id}
                             id={model.repo_id.slice('engine:'.length)}
                           />
                         ))}
                     </>
     ```
3. Create `electron/src/renderer/src/components/sidestack-first-run.test.tsx` with exactly this content (LF line endings):
   ```tsx
   // SideStack fork (VS-24): the first-run screen in the SideStack profile. Packs
   // lead with the required TTS model and skip refused models; an "engine:<id>"
   // gap from /setup/status gets an install button on the models step.
   import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
   import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
   import { afterEach, beforeEach, expect, it, vi } from 'vitest';
   import type { CatalogueModel } from '@/features/settings/model-catalogue-query';

   const mock = vi.hoisted(() => ({
     missing: [] as { repo_id?: string; label: string }[],
   }));
   vi.mock('@/lib/api/client', () => ({
     apiJson: (path: string) =>
       Promise.resolve(
         path.endsWith('/setup/preflight')
           ? { ok: true, checks: [] }
           : { models_ready: mock.missing.length === 0, missing: mock.missing },
       ),
   }));
   vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
   vi.mock('@/features/settings/system-preflight', () => ({
     SystemPreflight: () => <div>Preflight</div>,
   }));
   vi.mock('@/features/settings/model-library', () => ({
     ModelLibrary: () => <div>Models</div>,
     PerformanceModelPacks: () => <div>Model packs</div>,
   }));
   vi.mock('@/features/settings/model-settings', () => ({
     ModelSettings: () => <div>Engine settings</div>,
     modelFamilies: ['tts'],
   }));
   vi.mock('@/features/settings/engine-install', () => ({
     EngineInstall: ({ id }: { id: string }) => <button>Install {id}</button>,
   }));
   vi.mock('@/features/settings/mirror-settings', () => ({ MirrorSettings: () => null }));
   vi.mock('@/features/settings/media-tools', () => ({
     SetupMediaEngine: () => null,
     MediaTools: () => null,
   }));
   vi.mock('@/features/settings/privacy-settings', () => ({
     PrivacySettings: () => <div>Privacy</div>,
   }));
   vi.mock('./analytics-consent', () => ({ AnalyticsConsent: () => null }));
   vi.mock('./account-consent', () => ({ AccountConsent: () => null }));
   vi.mock('@/features/settings/shortcut-settings', () => ({
     ShortcutSettings: () => <div>Shortcuts</div>,
   }));

   import { SetupGate } from './setup-gate';
   import { resolvePerformanceModelPack } from '@/features/settings/performance-model-packs';

   beforeEach(() => localStorage.clear());
   afterEach(() => {
     cleanup();
     mock.missing = [];
   });

   async function modelsStep() {
     render(
       <QueryClientProvider
         client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
       >
         <SetupGate>
           <div>Studio</div>
         </SetupGate>
       </QueryClientProvider>,
     );
     await screen.findByText('Preflight');
     await waitFor(() =>
       expect(screen.getByRole('button', { name: 'setup.continue_ok' })).toBeEnabled(),
     );
     fireEvent.click(screen.getByRole('button', { name: 'setup.continue_ok' }));
     await screen.findByText('Model packs');
   }

   const row = (repo_id: string, extra: Partial<CatalogueModel> = {}): CatalogueModel => ({
     repo_id,
     label: repo_id,
     role: 'ASR',
     size_gb: 1,
     installed: false,
     supported: true,
     ...extra,
   });

   it('G1: an engine gap gets an install button on the models step', async () => {
     mock.missing = [
       { repo_id: 'openbmb/VoxCPM2', label: 'VoxCPM2 weights' },
       { repo_id: 'engine:voxcpm2', label: 'VoxCPM2 engine' },
     ];
     await modelsStep();
     expect(screen.getByRole('button', { name: 'Install voxcpm2' })).toBeInTheDocument();
     expect(screen.getAllByRole('button', { name: /^Install / })).toHaveLength(1);
     expect(screen.getByRole('status')).toHaveTextContent('VoxCPM2 weights, VoxCPM2 engine');
   });

   it('G2: model gaps alone, or entries without a repo id, get no install button', async () => {
     mock.missing = [{ repo_id: 'openbmb/VoxCPM2', label: 'VoxCPM2 weights' }, { label: 'Old entry' }];
     await modelsStep();
     expect(screen.queryByRole('button', { name: /^Install / })).toBeNull();
   });

   it('P1: packs lead with the required TTS model and skip refused models', () => {
     const pack = resolvePerformanceModelPack(
       [
         row('k2-fsa/OmniVoice', { role: 'TTS', commercial_only_refusal: 'refused' }),
         row('openbmb/VoxCPM2', { role: 'TTS', required: true, size_gb: 5 }),
         row('Systran/faster-whisper-base'),
         row('csukuangfj/sherpa-onnx-whisper-tiny', { commercial_only_refusal: 'refused' }),
         // Only a required TTS model leads the pack.
         row('Systran/faster-whisper-large-v3', { required: true }),
       ],
       'fast',
     );
     expect(pack.models.map((model) => model.repo_id)).toEqual([
       'openbmb/VoxCPM2',
       'Systran/faster-whisper-base',
     ]);
     expect(pack.downloadGb).toBe(6);
   });

   it('P2: upstream data keeps upstream packs', () => {
     const pack = resolvePerformanceModelPack(
       [
         row('k2-fsa/OmniVoice', { role: 'TTS', required: true }),
         row('Systran/faster-whisper-base'),
         row('csukuangfj/sherpa-onnx-whisper-tiny'),
       ],
       'fast',
     );
     expect(pack.models.map((model) => model.repo_id)).toEqual([
       'k2-fsa/OmniVoice',
       'Systran/faster-whisper-base',
       'csukuangfj/sherpa-onnx-whisper-tiny',
     ]);
   });

   it('P3: a refused required model is skipped too', () => {
     const pack = resolvePerformanceModelPack(
       [
         row('k2-fsa/OmniVoice', { role: 'TTS', required: true, commercial_only_refusal: 'refused' }),
         row('Systran/faster-whisper-base'),
       ],
       'fast',
     );
     expect(pack.models.map((model) => model.repo_id)).toEqual(['Systran/faster-whisper-base']);
   });
   ```
   Keep one newline at the end of the file.
4. Run Acceptance and report in the AGENTS-SIDESTACK §4 format, listing every command. Append the report at the very end of this spec under a `## Builder report` heading, and set this lane's tracker status to `running (dsh done)`. The Reviewer notes are for the reviewer: do not run them.

## Acceptance

```powershell
Push-Location electron
bun x vp test --run src/renderer/src/components/sidestack-first-run.test.tsx   # expect: 5 passed
bun x vp test --run src/renderer/src/components/ src/renderer/src/features/settings/   # expect: 0 failed
bun x tsc --noEmit -p tsconfig.web.json --tsBuildInfoFile ..\sidestack\work\tmp\web.tsbuildinfo   # expect: no output, exit 0
Pop-Location
git status --short    # expect: exactly the files in "Files"
python sidestack/scripts/check_sidestack.py           # expect: OK
```

## Part B — live check (Operator, after approval)

No step may start a download or an install.

1. Rebuild the web UI from the worktree: `bun run build:web`.
2. Start Voice Studio with the worktree launcher, default profile.
3. In the browser pane, open the first-run screen by clearing `voicestudio.setup.complete.v1` from localStorage, then go to the models step. On this machine `/setup/status` reports no gaps, so:
   - the pack starts with VoxCPM2 (installed);
   - it lists no OmniVoice, NLLB or sherpa-onnx rows;
   - no engine install button is shown.
4. Set `voicestudio.setup.complete.v1` back to `1`, then `-Stop`. Record the results here.

The `engine:` install button is covered by G1. A live view would need a machine without VoxCPM2.

## Out of scope

- The engine notice's "Set up" fix after setup. It downloads the required weights but does not install the engine. In the SideStack profile, setup now cannot finish without the engine (VS-23).
- `/setup/recommendations`' rationale text ("VoiceStudio (required)").

## Reviewer notes

- **Mutation checks.** Each of these was caught when the lane was written:
  - the required TTS rows not prepended;
  - the required filter ignoring role;
  - refused rows kept;
  - an install button for every gap;
  - the full `engine:` id passed as the engine id;
  - the install button removed.
- Upstream's own `performance-model-packs`, `model-library` and `setup-gate` tests pass unchanged. Their fixtures mark no row `required`, and one `missing` entry has no `repo_id`, which G2 covers.
- **Formatting:** `vp fmt --check` needs LF copies in this CRLF checkout. The blocks above are formatted.
- **Checked while writing this lane (2026-11-08):** the spec text was applied to HEAD in a scratch run. The 5 new tests, 96 test files under `components/` and `features/settings/`, and tsc were clean, and all 6 mutations were caught.

## Builder report

LANE: VS-24
STATUS: DONE
FILES CHANGED: electron/src/renderer/src/features/settings/performance-model-packs.ts (0F5F796546F5), electron/src/renderer/src/components/setup-gate.tsx (4DA5556CA49D), electron/src/renderer/src/components/sidestack-first-run.test.tsx (B99E81C1B626), sidestack/lanes/README.md
COMMANDS RUN:
- git status --short -> 0 (pre: spec + README only)
- Select-String performance-model-packs.ts '^  const selected = performancePackRepos\[tier\]$' -> 0, 1 match
- Select-String setup-gate.tsx "^import \{ ModelSettings \} from '@/features/settings/model-settings';$" -> 0, 1 match
- Test-Path sidestack-first-run.test.tsx -> 0, False
- bun x vp test --run src/renderer/src/components/sidestack-first-run.test.tsx -> 0, 5 passed / 0 failed
- bun x vp test --run src/renderer/src/components/ src/renderer/src/features/settings/ -> 0, 558 passed / 0 failed
- bun x tsc --noEmit -p tsconfig.web.json --tsBuildInfoFile ..\sidestack\work\tmp\web.tsbuildinfo -> 0, clean
- git status --short -> 0 (post: 2M + 1 new + README + spec)
- python sidestack/scripts/check_sidestack.py -> 0, OK: 14 required files, 23 lane specs, links, manifest, env profile, secret scan
NOT DONE / UNSURE: none

## Reviewer verification (2026-11-08)

**Part A PASS.** The builder finished in about 4 minutes with a clean report.
- **Spec match:** all three files match this spec applied to HEAD, byte for byte.
- **Mutation checks:** all 6 were caught on the builder's files.
- **Full frontend suite** (`bun run test`, including the locale checks): 395 files / 2,847 passed (12 skipped) and 339 files / 3,091 passed. No failures.
- The backend is unchanged, so the backend suite was not re-run.
- Part B is not run yet. It needs real run approval.

## Part B results (Operator, 2026-11-08)

**PASS.** Part A was committed first (9f04e363c).
- **Setup:** `bun run build:web` (exit 0). The worktree launcher was started in the default profile; VS-23 Part B ran in the same session.
- **First-run screen:** in the browser pane, `voicestudio.setup.complete.v1` was removed and the page reloaded, which opened the first-run screen.
  - The system check passed: RTX 5090, CUDA ready, `voxcpm2 → cuda`.
  - "Continue" led to the models step.
- **Every tier** (previewed with the toggle, nothing installed) leads with **VoxCPM2 (installed)**, then one commercial Whisper model:
  - Fast: Whisper base, 0.1 GB;
  - Balanced: Whisper large-v3 Turbo, 1.6 GB;
  - Quality and Max: Whisper large-v3, 2.9 GB.
  - No OmniVoice, NLLB or sherpa-onnx rows appear.
  - Screenshot taken.
- **No engine install button**, as expected: `/setup/status` reported no gaps. G1 covers the button.
- **Restored afterwards:** `voicestudio.setup.complete.v1` is back to `1`, the in-progress marker is removed, and the studio opens normally.
- **Nothing downloaded or installed:**
  - the cache was unchanged (17 files, same bytes), with no install jobs;
  - the engines folder was unchanged.
  - `prefs.json` was written at 15:09:45, by the server's own startup profile reconcile. That was before the first-run screen was opened; tier previews do not save.
- `-Stop` stopped the server.
