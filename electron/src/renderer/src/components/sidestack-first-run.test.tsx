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
