import { render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ASRSettings from './ASRSettings.svelte';

vi.mock('../utils/api', () => ({
  api: {
    session: {
      getASROptions: vi.fn(),
      updateASROptions: vi.fn(),
    },
    config: {
      getASRPreferences: vi.fn(),
      setASRPreferences: vi.fn(),
    },
  },
  handleApiError: (err: unknown) => (err instanceof Error ? err.message : String(err)),
}));

import { api } from '../utils/api';

const WHISPER_LANGS = [
  ['auto', 'Auto', 'Auto'],
  ['de', 'German', 'Deutsch'],
  ['en', 'English', 'English'],
];
const EN_LANG = [['en', 'English', 'English']];

const whisper = {
  service_id: 'whisper_cpp',
  name: 'Whisper',
  desc: '',
  variants: [
    { model_id: 'tiny', name: 'Tiny', desc: '', languages: WHISPER_LANGS },
    { model_id: 'tiny_en', name: 'Tiny (EN)', desc: '', languages: EN_LANG },
    { model_id: 'base', name: 'Base', desc: '', languages: WHISPER_LANGS },
    { model_id: 'base_en', name: 'Base (EN)', desc: '', languages: EN_LANG },
  ],
};

const parakeet = {
  service_id: 'parakeet_cpu',
  name: 'Parakeet',
  desc: '',
  variants: [
    { model_id: '0.6b_v2', name: '0.6B v2 [English Only]', desc: '', languages: EN_LANG },
    { model_id: '0.6b_v3', name: '0.6B v3 [Multilingual]', desc: '', languages: [['auto', 'Auto', 'Auto']] },
  ],
};

function mockPreferences(service: typeof whisper, variant: string, language: string, bookLanguage: string | null) {
  vi.mocked(api.config.getASRPreferences).mockResolvedValue({
    available_services: [service],
    current_service: service.service_id,
    current_variant: variant,
    current_language: language,
    book_language: bookLanguage,
  } as never);
}

async function renderSettings() {
  render(ASRSettings, { showOptions: false });
  return (await screen.findByLabelText('Model Variant')) as HTMLSelectElement;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.config.setASRPreferences).mockResolvedValue({});
});

describe('ASRSettings model variant with a book loaded', () => {
  it('keeps a saved English-only variant other than the first for an English book (#145)', async () => {
    mockPreferences(whisper, 'base_en', 'en', 'en');
    const select = await renderSettings();
    await waitFor(() => expect(select.value).toBe('base_en'));
    expect(api.config.setASRPreferences).not.toHaveBeenCalled();
  });

  it('keeps a saved multilingual variant for an English book', async () => {
    mockPreferences(whisper, 'base', 'en', 'en');
    const select = await renderSettings();
    await waitFor(() => expect(select.value).toBe('base'));
    expect(api.config.setASRPreferences).not.toHaveBeenCalled();
  });

  it('keeps an auto-detecting variant for an English book', async () => {
    mockPreferences(parakeet, '0.6b_v3', 'auto', 'en');
    const select = await renderSettings();
    await waitFor(() => expect(select.value).toBe('0.6b_v3'));
    expect(api.config.setASRPreferences).not.toHaveBeenCalled();
  });

  it('switches away from a variant that cannot transcribe the book language', async () => {
    mockPreferences(whisper, 'base_en', 'en', 'de');
    const select = await renderSettings();
    await waitFor(() => expect(select.value).toBe('tiny'));
    expect(api.config.setASRPreferences).toHaveBeenLastCalledWith('whisper_cpp', 'tiny', 'de');
  });

  it('switches an English-only Parakeet to the multilingual one for a German book', async () => {
    mockPreferences(parakeet, '0.6b_v2', 'en', 'de');
    const select = await renderSettings();
    await waitFor(() => expect(select.value).toBe('0.6b_v3'));
    expect(api.config.setASRPreferences).toHaveBeenLastCalledWith('parakeet_cpu', '0.6b_v3', 'auto');
  });

  it('picks a variant for the book language when none is saved', async () => {
    mockPreferences(whisper, '', '', 'en');
    const select = await renderSettings();
    await waitFor(() => expect(select.value).toBe('tiny_en'));
    expect(api.config.setASRPreferences).toHaveBeenLastCalledWith('whisper_cpp', 'tiny_en', 'en');
  });
});

describe('ASRSettings model variant without a book', () => {
  it('keeps the saved variant', async () => {
    mockPreferences(whisper, 'base_en', 'en', null);
    const select = await renderSettings();
    await waitFor(() => expect(select.value).toBe('base_en'));
    expect(api.config.setASRPreferences).not.toHaveBeenCalled();
  });

  it('replaces a saved variant the service no longer offers', async () => {
    mockPreferences(whisper, 'gone', 'en', null);
    const select = await renderSettings();
    await waitFor(() => expect(select.value).toBe('tiny'));
    expect(api.config.setASRPreferences).toHaveBeenCalledWith('whisper_cpp', 'tiny', 'en');
  });
});
