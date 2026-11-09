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
