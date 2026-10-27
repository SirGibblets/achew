import { render, screen, waitFor } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '../stores/session';
import ConfigureASR from './ConfigureASR.svelte';

vi.mock('../utils/api', () => ({
  api: {
    session: {
      get: vi.fn(),
      getStatus: vi.fn(),
      getASROptions: vi.fn(),
      updateASROptions: vi.fn(),
      configureASR: vi.fn(),
      getSelectedCues: vi.fn(),
    },
    config: {
      getASRPreferences: vi.fn(),
      setASRPreferences: vi.fn(),
    },
  },
  handleApiError: (err: unknown) => (err instanceof Error ? err.message : String(err)),
}));

vi.mock('../utils/websocket', () => ({
  WS_MESSAGE_TYPES: {
    STATUS: 'status',
    PROGRESS_UPDATE: 'progress_update',
    STEP_CHANGE: 'step_change',
    CHAPTER_UPDATE: 'chapter_update',
    HISTORY_UPDATE: 'history_update',
    BATCH_OPERATION: 'batch_operation',
    TRANSCRIBING_UPDATE: 'transcribing_update',
    REFERENCES_UPDATE: 'references_update',
    ERROR: 'error',
    SELECTION_STATS: 'selection_stats',
  },
  connectWebSocket: vi.fn(),
  disconnectWebSocket: vi.fn(),
  onWebSocketMessage: () => () => {},
}));

import { api } from '../utils/api';

async function setup(realignPending: boolean) {
  vi.mocked(api.session.get).mockResolvedValue({
    step: 'configure_asr',
    item_id: 'item-1',
    progress: { step: 'configure_asr', percent: 0, message: '', details: {} },
    selection_stats: { total: 0, selected: 0, unselected: 0 },
    can_undo: false,
    can_redo: false,
    chapter_refs: [],
    title_refs: [],
    book: null,
    restart_options: [],
    audio_unsupported_codec: false,
    audio_info: null,
    realign_pending: realignPending,
  } as never);
  vi.mocked(api.config.getASRPreferences).mockResolvedValue({
    available_services: [],
    current_service: '',
    current_variant: '',
    current_language: 'en',
    book_language: null,
  } as never);
  vi.mocked(api.session.getASROptions).mockResolvedValue({
    options: { trim: true, use_bias_words: false, bias_words: '', segment_length: 8 },
  } as never);
  vi.mocked(api.session.getSelectedCues).mockResolvedValue({ cues: [10, 20, 30] } as never);
  vi.mocked(api.session.configureASR).mockResolvedValue({} as never);

  await session.loadSession();
  return { user: userEvent.setup(), ...render(ConfigureASR) };
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  session.resetToIdle();
});

describe('ConfigureASR for a transcription-enhanced realignment', () => {
  it('asks to confirm settings for realignment instead of titling cues', async () => {
    await setup(true);
    expect(screen.getByRole('heading', { name: /Transcription Settings/ })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /Transcribe Titles/ })).not.toBeInTheDocument();
    expect(api.session.getSelectedCues).not.toHaveBeenCalled();
  });

  it('starts the realignment with transcription', async () => {
    const { user } = await setup(true);
    await user.click(screen.getByRole('button', { name: 'Start Realignment' }));
    expect(api.session.configureASR).toHaveBeenCalledWith('transcribe', []);
  });

  it('can realign without transcription', async () => {
    const { user } = await setup(true);
    await user.click(screen.getByRole('button', { name: 'Realign Without Transcription' }));
    expect(api.session.configureASR).toHaveBeenCalledWith('skip', []);
  });
});

describe('ConfigureASR for titling cues', () => {
  it('keeps the usual transcription screen', async () => {
    await setup(false);
    expect(screen.getByRole('heading', { name: /Transcribe Titles/ })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Transcribe 3 Titles' })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Skip Transcription' })).toBeInTheDocument();
  });
});
