# VS-26 — "Set up" in the SideStack profile

- **Phase:** 4
- **Run by:** dsh does Part A (code and offline tests). Part B is optional (see below).
- **Gate:** none for Part A.
- **Depends on:** VS-22, VS-23
- **Status:** verified (Part A; optional Part B not run)

## Goal

The engine notice's "Set up" action (`useEngineSetup().fix` in `components/engine-notice.tsx`) works in the SideStack profile:
- When the active TTS engine is not ready, has a one-click install and is not refused, "Set up" **reinstalls that engine** (`POST /engines/sidecar/<id>/install`) and waits for it. It does not switch to another engine.
- When it does fall back to another installed engine (`activateAvailableEngine`), it **never picks one that commercial-only mode refuses**.

**Why:**
- Upstream's fallback prefers `omnivoice`. In commercial-only mode, `POST /engines/select` refuses it with a 403 (VS-22). So "Set up" ends in an error and opens the repair agent.
- Upstream never reinstalls a missing sidecar engine. Since VS-23, VoxCPM2's weights are the required model, so "Set up" would download weights for an engine that is still missing, then switch engines.

**Fix:**
- A new `installEngine(id)` helper starts the install, shows the existing "Installing…" toast, and polls `/install/status` every 2 s, up to 30 minutes.
  - Installed: it refreshes readiness.
  - Job not running: it hands the error to the repair agent.
- `fix` calls it before the recommendations step, for an active engine that is unavailable, has `one_click_install` and has no `commercial_only_refusal`. `one_click_install` is false for non-loopback clients, so remote clients keep upstream's path.
- `activateAvailableEngine` filters out engines with a `commercial_only_refusal`.

## Files

| Path | Change |
|---|---|
| `electron/src/renderer/src/components/engine-notice.tsx` | edit: 4 replacements |
| `electron/src/renderer/src/components/sidestack-engine-setup.test.tsx` | new: N1–N5 |
| `sidestack/lanes/VS-26-engine-setup-sidestack.md`, `sidestack/lanes/README.md` | builder report / status |

## Preflight

Run from the worktree root.

```powershell
git status --short     # expect: only this spec (new) and sidestack/lanes/README.md (its row)
Select-String electron\src\renderer\src\components\engine-notice.tsx -Pattern '^  const fix = async \(\) => \{$'   # expect: 1 match
Test-Path electron\src\renderer\src\components\sidestack-engine-setup.test.tsx   # expect: False
```

## Steps

Each "replace" below names text that occurs exactly once in its file. Keep the file's line endings. Do not run `git checkout`, `git stash`, `git reset`, `git clean` or `git restore`.

1. In `electron/src/renderer/src/components/engine-notice.tsx`, make 4 replacements.
   - Replace:
     ```tsx
     interface ModelRecommendations {
       models: RecommendedModel[];
     }
     ```
     with:
     ```tsx
     interface ModelRecommendations {
       models: RecommendedModel[];
     }

     // SideStack fork (VS-26): how long "Set up" waits for a one-click engine install.
     const ENGINE_INSTALL_POLL_MS = 2000;
     const ENGINE_INSTALL_POLLS = 900;
     ```
   - In `activateAvailableEngine`, replace:
     ```tsx
           const available = engines.tts.backends.filter(
             (backend) => backend.available && backend.routing_status !== 'unavailable',
           );
     ```
     with:
     ```tsx
           const available = engines.tts.backends.filter(
             (backend) =>
               backend.available &&
               backend.routing_status !== 'unavailable' &&
               // SideStack fork (VS-26): never pick an engine commercial-only mode refuses.
               !backend.commercial_only_refusal,
           );
     ```
   - Replace:
     ```tsx
       const fix = async () => {
     ```
     with:
     ```tsx
       // SideStack fork (VS-26): reinstall an engine that one click installs (the
       // profile's VoxCPM2) and wait for it, instead of switching to another engine.
       const installEngine = async (id: string) => {
         const path = `/engines/sidecar/${encodeURIComponent(id)}/install`;
         await apiJson(path, { method: 'POST' });
         toast.success(t('modelMaintenance.installing'));
         for (let poll = 0; poll < ENGINE_INSTALL_POLLS; poll += 1) {
           const status = await apiJson<{
             installed: boolean;
             job: null | { state: string; error?: string | null };
           }>(`${path}/status`);
           if (status.installed) {
             await refreshReadiness();
             return;
           }
           if (status.job?.state !== 'running') {
             repair(
               `The ${id} engine install stopped: ${status.job?.error || status.job?.state || 'no job'}.`,
             );
             return;
           }
           await new Promise((resolve) => setTimeout(resolve, ENGINE_INSTALL_POLL_MS));
         }
         repair(`The ${id} engine install did not finish in time.`);
       };
       const fix = async () => {
     ```
   - In `fix`, replace:
     ```tsx
           const recommendation = await apiJson<ModelRecommendations>('/setup/recommendations');
     ```
     with:
     ```tsx
           // SideStack fork (VS-26): see installEngine.
           if (
             active &&
             !active.available &&
             active.one_click_install &&
             !active.commercial_only_refusal
           ) {
             await installEngine(active.id);
             return;
           }
           const recommendation = await apiJson<ModelRecommendations>('/setup/recommendations');
     ```
2. Create `electron/src/renderer/src/components/sidestack-engine-setup.test.tsx` with exactly this content (LF line endings):
   ```tsx
   // SideStack fork (VS-26): "Set up" in the SideStack profile. An active engine
   // that one click installs (VoxCPM2) is reinstalled, and a fallback engine is
   // never one that commercial-only mode refuses.
   import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
   import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
   import { afterEach, expect, it, vi } from 'vitest';
   import { EngineNotice } from './engine-notice';

   const mock = vi.hoisted(() => ({ api: vi.fn(), toast: vi.fn() }));
   vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
   vi.mock('sonner', () => ({ toast: { success: mock.toast } }));
   vi.mock('@/hooks/use-tts-readiness', () => ({ useTtsReadiness: () => 'engine' }));
   vi.mock('@/hooks/use-model-install-sync', () => ({
     useModelInstallJobs: () => ({ data: { jobs: [] } }),
     TERMINAL_MODEL_INSTALL_STATES: new Set(['done', 'failed', 'cancelled', 'install_cancelled']),
   }));
   vi.mock('@/lib/api/client', () => ({ apiJson: mock.api, describeError: String }));

   const REFUSED = 'Commercial-only mode is on.';
   const INSTALL = '/engines/sidecar/voxcpm2/install';

   function serve(
     backends: Record<string, unknown>[],
     status: Record<string, unknown>[] = [{ installed: true, job: null }],
   ) {
     const statuses = [...status];
     mock.api.mockImplementation((path: string) => {
       if (path === '/engines') return Promise.resolve({ tts: { active: 'voxcpm2', backends } });
       if (path === '/setup/recommendations')
         return Promise.resolve({
           models: [{ repo_id: 'openbmb/VoxCPM2', role: 'TTS', required: true, installed: true }],
         });
       if (path === `${INSTALL}/status`) return Promise.resolve(statuses.shift() ?? statuses.at(-1));
       return Promise.resolve({});
     });
   }

   const voxcpm2 = { id: 'voxcpm2', available: false, one_click_install: true };
   const omnivoice = { id: 'omnivoice', available: true, commercial_only_refusal: REFUSED };
   const kitten = { id: 'kittentts', available: true };

   function clickSetUp() {
     render(
       <QueryClientProvider
         client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
       >
         <EngineNotice />
       </QueryClientProvider>,
     );
     fireEvent.click(screen.getByRole('button', { name: 'engines.set_up' }));
   }

   const calls = (path: string) => mock.api.mock.calls.filter(([called]) => called === path);

   afterEach(() => {
     cleanup();
     mock.api.mockReset();
     mock.toast.mockReset();
   });

   it('N1: reinstalls the active one-click engine instead of switching engines', async () => {
     serve([voxcpm2, omnivoice, kitten]);
     clickSetUp();
     await waitFor(() => expect(calls(`${INSTALL}/status`)).toHaveLength(1));
     expect(mock.api).toHaveBeenCalledWith(INSTALL, { method: 'POST' });
     expect(mock.toast).toHaveBeenCalledWith('modelMaintenance.installing');
     expect(calls('/engines/select')).toHaveLength(0);
     expect(calls('/setup/recommendations')).toHaveLength(0);
   });

   it('N2: waits while the install runs', async () => {
     serve([voxcpm2, kitten], [{ installed: false, job: { state: 'running' } }, { installed: true }]);
     clickSetUp();
     await waitFor(() => expect(calls(`${INSTALL}/status`)).toHaveLength(2), { timeout: 5000 });
     expect(calls('/engines/select')).toHaveLength(0);
   });

   it('N3: a failed install goes to the repair agent', async () => {
     serve([voxcpm2, kitten], [{ installed: false, job: { state: 'failed', error: 'disk full' } }]);
     const listener = vi.fn();
     window.addEventListener('voicestudio:repair-agent-open', listener);
     clickSetUp();
     await waitFor(() => expect(listener).toHaveBeenCalledOnce());
     const event = listener.mock.calls[0]?.[0] as CustomEvent<{ report: string }>;
     expect(event.detail.report).toContain('voxcpm2 engine install stopped: disk full');
     expect(calls('/engines/select')).toHaveLength(0);
     window.removeEventListener('voicestudio:repair-agent-open', listener);
   });

   it('N4: without one-click install, the fallback skips refused engines', async () => {
     serve([{ ...voxcpm2, one_click_install: false }, omnivoice, kitten]);
     clickSetUp();
     await waitFor(() =>
       expect(mock.api).toHaveBeenCalledWith('/engines/select', {
         method: 'POST',
         body: JSON.stringify({ family: 'tts', backend_id: 'kittentts' }),
       }),
     );
     expect(calls(INSTALL)).toHaveLength(0);
   });

   it('N5: a refused active engine is not reinstalled', async () => {
     serve([{ ...voxcpm2, commercial_only_refusal: REFUSED }, kitten]);
     clickSetUp();
     await waitFor(() => expect(calls('/engines/select')).toHaveLength(1));
     expect(calls(INSTALL)).toHaveLength(0);
   });
   ```
   Keep one newline at the end of the file.
3. Run Acceptance and report in the AGENTS-SIDESTACK §4 format, listing every command. Append the report at the very end of this spec under a `## Builder report` heading, and set this lane's tracker status to `running (dsh done)`. The Reviewer notes are for the reviewer: do not run them.

## Acceptance

```powershell
Push-Location electron
bun x vp test --run src/renderer/src/components/sidestack-engine-setup.test.tsx   # expect: 5 passed
bun x vp test --run src/renderer/src/components/   # expect: 0 failed
bun x tsc --noEmit -p tsconfig.web.json --tsBuildInfoFile ..\sidestack\work\tmp\web.tsbuildinfo   # expect: no output, exit 0
Pop-Location
git status --short    # expect: exactly the files in "Files"
python sidestack/scripts/check_sidestack.py           # expect: OK
```

## Part B (optional)

A live check would need the VoxCPM2 engine to be missing: moving `engines\voxcpm2` aside, then letting "Set up" reinstall about 5 GB. That changes the installed engine, so it is **not run** unless the user asks for it. N1–N5 cover the paths, with the API mocked.

## Out of scope

- Progress for the engine install inside the notice. The button shows its busy spinner until the install ends; Settings → Models shows the steps.
- `/setup/recommendations`' rationale text.

## Reviewer notes

- **Mutation checks.** Each of these was caught when the lane was written:
  - the fallback filter replaced by `true`;
  - the install branch removed;
  - the refusal check dropped from the install branch;
  - the one-click check dropped;
  - the "running" wait broken;
  - the failure not sent to the repair agent.
- Upstream's `engine-notice.test.tsx` passes unchanged: none of its engines has `one_click_install` or a refusal.
- **Checked while writing this lane (2026-11-08):** the spec text was applied to HEAD in a scratch run; N1–N5, every `components/` test, tsc and the formatter were clean, and all 6 mutations were caught.

## Builder report

```
LANE: VS-26
STATUS: DONE
FILES CHANGED: electron/src/renderer/src/components/engine-notice.tsx (4393b08feb2f), electron/src/renderer/src/components/sidestack-engine-setup.test.tsx (ed3f4017540b), sidestack/lanes/VS-26-engine-setup-sidestack.md (this report appended), sidestack/lanes/README.md (status → running (dsh done))
COMMANDS RUN:
  git status --preflight → 0 (only spec + README)
  Select-String engine-notice.tsx -Pattern '^  const fix = async \(\) => \{$' → 1 match (line 108)
  Test-Path sidestack-engine-setup.test.tsx → False
  Push-Location electron; bun x vp test --run src/renderer/src/components/sidestack-engine-setup.test.tsx; Pop-Location → 0 (5 passed)
  Push-Location electron; bun x vp test --run src/renderer/src/components/; Pop-Location → 0 (300 passed, 49 files, 0 failed)
  Push-Location electron; bun x tsc --noEmit -p tsconfig.web.json --tsBuildInfoFile ..\sidestack\work\tmp\web.tsbuildinfo; Pop-Location → 0 (no output)
  git status --short → exactly the files in "Files"
  python sidestack/scripts/check_sidestack.py → OK: 14 required files, 25 lane specs, links, manifest, env profile, secret scan
NOT DONE / UNSURE: none (Part B not run — optional, requires moving engines\voxcpm2 aside)
```

## Reviewer verification (2026-11-08)

**Part A PASS.** The builder finished in under 3 minutes with a clean report.
- **Spec match:** both files match this spec applied to HEAD, byte for byte.
- **Mutation checks:** all 6 were caught on the builder's files.
- **Full frontend suite** (`bun run test`, including the locale checks): 396 files / 2,852 passed (12 skipped) and 339 files / 3,091 passed. No failures.
- The backend is unchanged, so the backend suite was not re-run.
- Part B (optional, reinstalls about 5 GB) was not run.
