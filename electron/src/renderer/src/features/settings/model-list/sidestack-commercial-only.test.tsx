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
