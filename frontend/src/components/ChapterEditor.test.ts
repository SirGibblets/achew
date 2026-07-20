import { render, screen, waitFor } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from '../stores/session';
import type { ChapterData, SelectionStats } from '../types/chapter';
import ChapterEditor from './ChapterEditor.svelte';

vi.mock('../utils/api', () => ({
  api: {
    session: {
      get: vi.fn(),
      getStatus: vi.fn(),
      gotoReview: vi.fn(),
    },
    chapters: {
      getAll: vi.fn(),
      undo: vi.fn(),
      redo: vi.fn(),
      delete: vi.fn(),
      deleteBySelection: vi.fn(),
      transcribe: vi.fn(),
      transcribeSelected: vi.fn(),
      cancelTranscriptions: vi.fn(),
      applyTitles: vi.fn(),
      setSelection: vi.fn(),
      updateTitle: vi.fn(),
      updateTimestamp: vi.fn(),
      getNearbyCues: vi.fn(),
      shiftTimestamps: vi.fn(),
    },
    config: {
      getEditorSettings: vi.fn(),
      updateEditorSettings: vi.fn(),
    },
    batch: {
      processSelected: vi.fn(),
      getAIOptions: vi.fn(),
      updateAIOptions: vi.fn(),
    },
    llm: {
      getProviders: vi.fn(),
      getModels: vi.fn(),
    },
    abs: {
      getProviders: vi.fn(),
    },
    references: {},
    audio: {},
  },
  handleApiError: (err: unknown) => (err instanceof Error ? err.message : String(err)),
}));

const wsListeners = new Map<string, Set<(data: unknown) => void>>();

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
  onWebSocketMessage: (type: string, callback: (data: unknown) => void) => {
    if (!wsListeners.has(type)) wsListeners.set(type, new Set());
    wsListeners.get(type)!.add(callback);
    return () => wsListeners.get(type)!.delete(callback);
  },
}));

import { api } from '../utils/api';

function emitWs(type: string, data: unknown) {
  wsListeners.get(type)?.forEach((callback) => callback(data));
}

function makeChapters(): ChapterData[] {
  return [
    { id: 'c1', timestamp: 0, transcript: 'First transcript', title: 'Chapter 1', deleted: false, selected: true },
    { id: 'c2', timestamp: 60, transcript: '', title: 'Chapter 2', deleted: false, selected: true },
    { id: 'c3', timestamp: 120, transcript: '', title: 'Chapter 3', deleted: false, selected: false },
  ];
}

const defaultStats: SelectionStats = { total: 3, selected: 2, unselected: 1 };

interface SetupOptions {
  chapters?: ChapterData[];
  selectionStats?: SelectionStats;
  canUndo?: boolean;
  canRedo?: boolean;
  chapterRefs?: Array<{ id: string; name: string }>;
  editorSettings?: Record<string, unknown>;
}

async function setup(options: SetupOptions = {}) {
  const chapters = options.chapters ?? makeChapters();
  const selectionStats = options.selectionStats ?? defaultStats;

  vi.mocked(api.session.get).mockResolvedValue({
    step: 'chapter_editing',
    item_id: 'item-1',
    progress: { step: 'chapter_editing', percent: 100, message: '', details: {} },
    selection_stats: selectionStats,
    can_undo: options.canUndo ?? true,
    can_redo: options.canRedo ?? false,
    chapter_refs: options.chapterRefs ?? [],
    title_refs: [],
    book: null,
    restart_options: [],
    audio_unsupported_codec: false,
    audio_info: null,
  } as never);
  vi.mocked(api.chapters.getAll).mockResolvedValue({
    chapters,
    selection_stats: selectionStats,
  } as never);
  vi.mocked(api.config.getEditorSettings).mockResolvedValue({
    tab_navigation: false,
    hide_transcriptions: false,
    show_formatted_time: true,
    show_fractional_seconds: true,
    ...options.editorSettings,
  } as never);
  vi.mocked(api.config.updateEditorSettings).mockImplementation(
    async (updates: Record<string, unknown>) =>
      ({
        editor_settings: {
          tab_navigation: false,
          hide_transcriptions: false,
          show_formatted_time: true,
          show_fractional_seconds: true,
          ...options.editorSettings,
          ...updates,
        },
      }) as never,
  );
  vi.mocked(api.batch.getAIOptions).mockResolvedValue({} as never);
  vi.mocked(api.abs.getProviders).mockResolvedValue([] as never);
  vi.mocked(api.llm.getProviders).mockResolvedValue({ providers: [] } as never);
  vi.mocked(api.session.gotoReview).mockResolvedValue({} as never);
  vi.mocked(api.session.getStatus).mockResolvedValue({ has_pipeline: false, step: 'reviewing' } as never);

  await session.loadSession();
  const utils = render(ChapterEditor);
  if (chapters.length > 0) {
    await screen.findByText(`${selectionStats.selected} of ${selectionStats.total} selected`);
  }
  // onMount registers window/document listeners only after loadEditorSettings()
  // and loadChapters() resolve; wait for the full mount before interacting.
  await waitFor(() => expect(api.chapters.getAll).toHaveBeenCalled());
  await new Promise((resolve) => setTimeout(resolve, 0));
  return { user: userEvent.setup(), ...utils };
}

async function openMenu(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Additional tools and settings' }));
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  session.resetToIdle();
});

describe('action bar', () => {
  it('shows the selection count badge', async () => {
    await setup();
    expect(screen.getByText('2 of 3 selected')).toBeInTheDocument();
  });

  it('is hidden when there are no chapters and nothing to undo', async () => {
    await setup({ chapters: [], selectionStats: { total: 0, selected: 0, unselected: 0 }, canUndo: false });
    expect(screen.queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Review Selected' })).not.toBeInTheDocument();
  });

  it('is shown when there are no chapters but undo is available, with the menu suppressed', async () => {
    const { user } = await setup({
      chapters: [],
      selectionStats: { total: 0, selected: 0, unselected: 0 },
      canUndo: true,
    });
    expect(screen.getByRole('button', { name: 'Undo' })).toBeInTheDocument();
    await openMenu(user);
    expect(screen.queryByRole('heading', { name: 'Tools' })).not.toBeInTheDocument();
  });

  it('enables Undo/Redo according to history state and calls the API', async () => {
    const { user } = await setup({ canUndo: true, canRedo: false });
    const undoButton = screen.getByRole('button', { name: 'Undo' });
    const redoButton = screen.getByRole('button', { name: 'Redo' });

    expect(undoButton).toBeEnabled();
    expect(redoButton).toBeDisabled();

    await user.click(undoButton);
    expect(api.chapters.undo).toHaveBeenCalledOnce();

    await user.click(redoButton);
    expect(api.chapters.redo).not.toHaveBeenCalled();
  });

  it('supports undo/redo keyboard shortcuts', async () => {
    await setup({ canUndo: true, canRedo: true });

    // ChapterEditor picks the modifier from navigator.platform, which jsdom
    // derives from the host OS.
    const isMac = navigator.platform.toUpperCase().includes('MAC');
    const modifier = isMac ? { metaKey: true } : { ctrlKey: true };

    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'z', ...modifier, bubbles: true }));
    await waitFor(() => expect(api.chapters.undo).toHaveBeenCalledOnce());

    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'y', ...modifier, bubbles: true }));
    await waitFor(() => expect(api.chapters.redo).toHaveBeenCalledOnce());

    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'z', ...modifier, shiftKey: true, bubbles: true }));
    await waitFor(() => expect(api.chapters.redo).toHaveBeenCalledTimes(2));
  });

  it('opens the AI cleanup dialog from Clean Up Selected', async () => {
    const { user } = await setup();
    await user.click(screen.getByRole('button', { name: /Clean Up Selected/ }));
    expect(await screen.findByRole('heading', { name: /AI Chapter Cleanup/ })).toBeInTheDocument();
  });

  it('disables Clean Up Selected and Review Selected when nothing is selected', async () => {
    await setup({
      chapters: makeChapters().map((chapter) => ({ ...chapter, selected: false })),
      selectionStats: { total: 3, selected: 0, unselected: 3 },
    });
    expect(screen.getByRole('button', { name: /Clean Up Selected/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Review Selected' })).toBeDisabled();
  });

  it('goes to review via Review Selected', async () => {
    const { user } = await setup();
    await user.click(screen.getByRole('button', { name: 'Review Selected' }));
    await waitFor(() => expect(api.session.gotoReview).toHaveBeenCalledOnce());
  });
});

describe('action bar menu', () => {
  it('opens and closes via the toggle button', async () => {
    const { user } = await setup();
    await openMenu(user);
    expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Tools' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Actions' })).toBeInTheDocument();

    await openMenu(user);
    expect(screen.queryByRole('heading', { name: 'Tools' })).not.toBeInTheDocument();
  });

  it('closes on outside click but not on inside click', async () => {
    const { user } = await setup();
    await openMenu(user);

    await user.click(screen.getByRole('heading', { name: 'Tools' }));
    expect(screen.getByRole('heading', { name: 'Tools' })).toBeInTheDocument();

    await user.click(document.body);
    expect(screen.queryByRole('heading', { name: 'Tools' })).not.toBeInTheDocument();
  });

  it('only offers "Apply titles from..." when chapter references exist', async () => {
    const { user } = await setup();
    await openMenu(user);
    expect(screen.queryByRole('button', { name: 'Apply titles from...' })).not.toBeInTheDocument();
  });

  it('shows "Apply titles from..." when chapter references exist', async () => {
    const { user } = await setup({ chapterRefs: [{ id: 'r1', name: 'Ref' }] });
    await openMenu(user);
    expect(screen.getByRole('button', { name: 'Apply titles from...' })).toBeInTheDocument();
  });

  it.each([
    ['Edit Titles', 'Edit Titles'],
    ['Shift Titles', 'Shift Titles'],
    ['Shift Timestamps', 'Shift Timestamps'],
  ])('opens the %s dialog', async (buttonName, headingName) => {
    const { user } = await setup();
    await openMenu(user);
    await user.click(screen.getByRole('button', { name: buttonName }));
    expect(await screen.findByRole('heading', { name: new RegExp(headingName) })).toBeInTheDocument();
  });

  it('disables selection-dependent actions when nothing is selected', async () => {
    const { user } = await setup({
      chapters: makeChapters().map((chapter) => ({ ...chapter, selected: false })),
      selectionStats: { total: 3, selected: 0, unselected: 3 },
    });
    await openMenu(user);
    expect(screen.getByRole('button', { name: 'Quick Tidy' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Transcribe' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Delete Selected' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Delete Unselected' })).toBeEnabled();
  });

  it('deletes the current selection', async () => {
    const { user } = await setup();
    await openMenu(user);
    await user.click(screen.getByRole('button', { name: 'Delete Selected' }));
    expect(api.chapters.deleteBySelection).toHaveBeenCalledWith('selected');
  });

  it('transcribes the selection and is disabled while transcription runs', async () => {
    const { user } = await setup();
    await openMenu(user);

    const transcribeButton = screen.getByRole('button', { name: 'Transcribe' });
    expect(transcribeButton).toBeEnabled();

    emitWs('transcribing_update', { statuses: { c1: 'transcribing' } });
    await openMenu(user);
    await openMenu(user);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Transcribe' })).toBeDisabled());

    emitWs('transcribing_update', { statuses: {} });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Transcribe' })).toBeEnabled());

    await user.click(screen.getByRole('button', { name: 'Transcribe' }));
    expect(api.chapters.transcribeSelected).toHaveBeenCalledOnce();
  });

  it('applies Quick Tidy titles to selected chapters', async () => {
    const { user } = await setup({
      chapters: [
        { id: 'c1', timestamp: 0, transcript: '', title: '  chapter one  ', deleted: false, selected: true },
        { id: 'c2', timestamp: 60, transcript: '', title: 'Chapter 2', deleted: false, selected: false },
      ],
      selectionStats: { total: 2, selected: 1, unselected: 1 },
    });
    await openMenu(user);
    await user.click(screen.getByRole('button', { name: 'Quick Tidy' }));
    await waitFor(() => expect(api.chapters.applyTitles).toHaveBeenCalledOnce());
    const mappings = vi.mocked(api.chapters.applyTitles).mock.calls[0][0] as Array<{ chapter_id: string }>;
    expect(mappings).toHaveLength(1);
    expect(mappings[0].chapter_id).toBe('c1');
  });

  it('opens the Edit Titles dialog in tidy mode from the Quick Tidy gear', async () => {
    const { user } = await setup();
    await openMenu(user);
    await user.click(screen.getByRole('button', { name: 'Configure Quick Tidy' }));
    expect(await screen.findByRole('heading', { name: /Edit Titles/ })).toBeInTheDocument();
  });
});

describe('editor settings', () => {
  it('persists checkbox changes', async () => {
    const { user } = await setup();
    await openMenu(user);

    await user.click(screen.getByLabelText(/Tab to Next/));
    await waitFor(() => expect(api.config.updateEditorSettings).toHaveBeenCalledWith({ tab_navigation: true }));
  });

  it('only shows Hide Transcripts when transcripts exist', async () => {
    const { user } = await setup({
      chapters: makeChapters().map((chapter) => ({ ...chapter, transcript: '' })),
    });
    await openMenu(user);
    expect(screen.queryByLabelText(/Hide Transcripts/)).not.toBeInTheDocument();
  });

  it('shows Hide Transcripts when transcripts exist and persists it', async () => {
    const { user } = await setup();
    await openMenu(user);
    await user.click(screen.getByLabelText(/Hide Transcripts/));
    await waitFor(() => expect(api.config.updateEditorSettings).toHaveBeenCalledWith({ hide_transcriptions: true }));
  });

  it('only shows Fractional Seconds while Format Timestamps is enabled', async () => {
    const { user } = await setup();
    await openMenu(user);
    expect(screen.getByLabelText(/Fractional Seconds/)).toBeInTheDocument();

    await user.click(screen.getByLabelText(/Format Timestamps/));
    await waitFor(() => expect(api.config.updateEditorSettings).toHaveBeenCalledWith({ show_formatted_time: false }));
    await waitFor(() => expect(screen.queryByLabelText(/Fractional Seconds/)).not.toBeInTheDocument());
  });
});

describe('action bar docking', () => {
  function setWindowWidth(width: number) {
    Object.defineProperty(window, 'innerWidth', { value: width, configurable: true, writable: true });
    window.dispatchEvent(new Event('resize'));
  }

  afterEach(() => {
    localStorage.removeItem('achew_action_bar_dock');
    localStorage.removeItem('achew_action_bar_expanded');
    setWindowWidth(1024);
  });

  it('restores a saved dock position from localStorage', async () => {
    localStorage.setItem('achew_action_bar_dock', 'left');
    await setup();

    expect(document.body.classList.contains('action-bar-dock-left')).toBe(true);
    // Side dock shows the menu sections inline, without a menu button
    expect(screen.getByRole('heading', { name: 'Tools' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Additional tools and settings' })).not.toBeInTheDocument();
  });

  it('persists dock changes made via the dock buttons', async () => {
    const { user } = await setup();
    expect(document.body.classList.contains('action-bar-dock-left')).toBe(false);

    await user.click(screen.getByRole('button', { name: 'Dock to left side' }));
    await waitFor(() => expect(document.body.classList.contains('action-bar-dock-left')).toBe(true));
    expect(localStorage.getItem('achew_action_bar_dock')).toBe('left');

    await user.click(screen.getByRole('button', { name: 'Dock to bottom' }));
    await waitFor(() => expect(document.body.classList.contains('action-bar-dock-left')).toBe(false));
    expect(localStorage.getItem('achew_action_bar_dock')).toBe('bottom');
  });

  it('persists the collapsed state', async () => {
    localStorage.setItem('achew_action_bar_dock', 'right');
    const { user } = await setup();

    await user.click(screen.getByRole('button', { name: 'Collapse' }));
    await waitFor(() => expect(document.body.classList.contains('action-bar-collapsed')).toBe(true));
    expect(localStorage.getItem('achew_action_bar_expanded')).toBe('0');
    expect(screen.getByText('2/3')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Expand' }));
    await waitFor(() => expect(document.body.classList.contains('action-bar-collapsed')).toBe(false));
    expect(localStorage.getItem('achew_action_bar_expanded')).toBe('1');
  });

  it('forces the bottom dock on small screens while keeping the stored preference', async () => {
    localStorage.setItem('achew_action_bar_dock', 'left');
    setWindowWidth(600);
    await setup();

    expect(document.body.classList.contains('action-bar-dock-left')).toBe(false);
    expect(screen.queryByRole('heading', { name: 'Tools' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Additional tools and settings' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Dock to left side' })).not.toBeInTheDocument();
    expect(localStorage.getItem('achew_action_bar_dock')).toBe('left');
  });

  it('returns to the stored side dock when the window grows again', async () => {
    localStorage.setItem('achew_action_bar_dock', 'left');
    setWindowWidth(600);
    await setup();
    expect(document.body.classList.contains('action-bar-dock-left')).toBe(false);

    setWindowWidth(1200);
    await waitFor(() => expect(document.body.classList.contains('action-bar-dock-left')).toBe(true));
  });

  it('cleans up the body classes on unmount', async () => {
    localStorage.setItem('achew_action_bar_dock', 'left');
    const { unmount } = await setup();
    expect(document.body.classList.contains('action-bar-dock-left')).toBe(true);

    unmount();
    expect(document.body.classList.contains('action-bar-dock-left')).toBe(false);
    expect(document.body.classList.contains('action-bar-collapsed')).toBe(false);
  });
});
