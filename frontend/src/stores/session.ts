import { writable, derived, get } from 'svelte/store';
import { api, handleApiError } from '../utils/api';
import { connectWebSocket, disconnectWebSocket, onWebSocketMessage, WS_MESSAGE_TYPES } from '../utils/websocket';
import type { ChapterData, SelectionStats } from '../types/chapter';
import type { ExistingCueSource, ExistingTitleSource } from '../types/sources';
import type { Book } from '../types/book';
import type {
  ChapterUpdateData,
  ErrorData,
  HistoryUpdateData,
  ProgressUpdateData,
  SelectionStatsData,
  SourcesUpdateData,
  StatusData,
  StepChangeData,
  TranscribingUpdateData,
} from '../types/websocket';

export interface SessionProgress {
  step: string;
  percent: number;
  message: string;
  details: Record<string, unknown>;
}

export interface SessionState {
  step: string;
  itemId: string;
  progress: SessionProgress;
  chapters: ChapterData[];
  selectionStats: SelectionStats;
  canUndo: boolean;
  canRedo: boolean;
  book: Book | null;
  cueSources: ExistingCueSource[];
  titleSources: ExistingTitleSource[];
  audioUnsupportedCodec: boolean;
  restartOptions: string[];
  transcriptionStatuses: Record<string, string>;
  version: string | null;
  buildMeta: string | null;
  loading: boolean;
  error: string | null;
}

interface PendingAddChapterDialog {
  chapter_id: string;
  open_tab: string;
}

interface ActiveSessionInfo {
  hasSession: boolean;
  sessionId?: string;
  step?: string;
}

function initialState(): SessionState {
  return {
    step: 'idle',
    itemId: '',
    progress: { step: 'idle', percent: 0, message: '', details: {} },
    chapters: [],
    selectionStats: { total: 0, selected: 0, unselected: 0 },
    canUndo: false,
    canRedo: false,
    book: null,
    cueSources: [],
    titleSources: [],
    audioUnsupportedCodec: false,
    restartOptions: [],
    transcriptionStatuses: {},
    version: null,
    buildMeta: null,
    loading: false,
    error: null,
  };
}

function createSessionStore() {
  const { subscribe, update } = writable<SessionState>(initialState());

  let unsubscribeFunctions: Array<() => void> = [];
  let webSocketHandlersSetup = false;

  const setupWebSocketHandlers = () => {
    unsubscribeFunctions.forEach((fn) => fn());
    unsubscribeFunctions = [];

    unsubscribeFunctions.push(
      onWebSocketMessage(WS_MESSAGE_TYPES.PROGRESS_UPDATE, (raw) => {
        const data = raw as ProgressUpdateData;
        update((state) => ({
          ...state,
          progress: {
            step: data.step,
            percent: data.percent,
            message: data.message,
            details: data.details || {},
          },
        }));
      }),
    );

    unsubscribeFunctions.push(
      onWebSocketMessage(WS_MESSAGE_TYPES.STEP_CHANGE, (raw) => {
        const data = raw as StepChangeData;
        update((state) => ({
          ...state,
          step: data.new_step,
          ...(data.cue_sources && { cueSources: data.cue_sources }),
          ...(data.title_sources && { titleSources: data.title_sources }),
          ...(data.restart_options && { restartOptions: data.restart_options }),
          ...(data.audio_unsupported_codec !== undefined && {
            audioUnsupportedCodec: data.audio_unsupported_codec,
          }),
        }));
        if (data.new_step === 'chapter_editing' && data.chapter_id) {
          pendingAddChapterDialog.set({
            chapter_id: data.chapter_id,
            open_tab: data.open_tab ?? 'detected_cue',
          });
        }
      }),
    );

    unsubscribeFunctions.push(
      onWebSocketMessage(WS_MESSAGE_TYPES.CHAPTER_UPDATE, (raw) => {
        const data = raw as ChapterUpdateData;
        update((state) => ({
          ...state,
          chapters: data.chapters,
          selectionStats: {
            total: data.total_count,
            selected: data.selected_count,
            unselected: data.total_count - data.selected_count,
          },
        }));
      }),
    );

    unsubscribeFunctions.push(
      onWebSocketMessage(WS_MESSAGE_TYPES.HISTORY_UPDATE, (raw) => {
        const data = raw as HistoryUpdateData;
        update((state) => ({
          ...state,
          canUndo: data.can_undo,
          canRedo: data.can_redo,
        }));
      }),
    );

    unsubscribeFunctions.push(
      onWebSocketMessage(WS_MESSAGE_TYPES.SELECTION_STATS, (raw) => {
        const data = raw as SelectionStatsData;
        update((state) => ({
          ...state,
          selectionStats: {
            total: data.total,
            selected: data.selected,
            unselected: data.unselected,
          },
        }));
      }),
    );

    unsubscribeFunctions.push(
      onWebSocketMessage(WS_MESSAGE_TYPES.SOURCES_UPDATE, (raw) => {
        const data = raw as SourcesUpdateData;
        update((state) => ({
          ...state,
          ...(data.cue_sources && { cueSources: data.cue_sources }),
          ...(data.title_sources && { titleSources: data.title_sources }),
        }));
      }),
    );

    unsubscribeFunctions.push(
      onWebSocketMessage(WS_MESSAGE_TYPES.TRANSCRIBING_UPDATE, (raw) => {
        const data = raw as TranscribingUpdateData;
        update((state) => ({
          ...state,
          transcriptionStatuses: data.statuses || {},
        }));
      }),
    );

    unsubscribeFunctions.push(
      onWebSocketMessage(WS_MESSAGE_TYPES.ERROR, (raw) => {
        const data = raw as ErrorData;
        update((state) => ({
          ...state,
          error: data.message,
          loading: false,
        }));
      }),
    );

    unsubscribeFunctions.push(
      onWebSocketMessage(WS_MESSAGE_TYPES.STATUS, (raw) => {
        const data = raw as StatusData;
        console.log('WebSocket status:', data);

        if (data.type === 'book_update' && data.book) {
          update((state) => ({ ...state, book: data.book as Book }));
        }
      }),
    );
  };

  const store = {
    subscribe,

    async createSession(itemId: string): Promise<boolean> {
      update((state) => ({ ...state, loading: true, error: null }));

      try {
        await api.session.create(itemId);

        update((state) => ({ ...state, itemId, loading: false }));

        connectWebSocket();
        if (!webSocketHandlersSetup) {
          setupWebSocketHandlers();
          webSocketHandlersSetup = true;
        }

        return true;
      } catch (error) {
        const errorMessage = handleApiError(error);
        update((state) => ({ ...state, error: errorMessage, loading: false }));
        throw error;
      }
    },

    async loadSession() {
      update((state) => ({ ...state, loading: true, error: null }));

      try {
        const data = await api.session.get();

        update((state) => ({
          ...state,
          step: data.step,
          itemId: data.item_id,
          progress: data.progress,
          selectionStats: data.selection_stats,
          canUndo: data.can_undo,
          canRedo: data.can_redo,
          cueSources: data.cue_sources ?? [],
          titleSources: data.title_sources ?? [],
          book: data.book ?? null,
          restartOptions: data.restart_options ?? [],
          audioUnsupportedCodec: data.audio_unsupported_codec ?? false,
          loading: false,
        }));

        if (!webSocketHandlersSetup) {
          setupWebSocketHandlers();
          webSocketHandlersSetup = true;
        }

        return data;
      } catch (error) {
        const errorMessage = handleApiError(error);
        update((state) => ({ ...state, error: errorMessage, loading: false }));
        throw error;
      }
    },

    async deleteSession(): Promise<void> {
      update((state) => ({ ...state, loading: true, error: null }));
      savedChapterEditorScroll.set(null);

      try {
        await api.session.delete();

        update((state) => ({
          ...initialState(),
          version: state.version,
          buildMeta: state.buildMeta,
        }));
      } catch (error) {
        const errorMessage = handleApiError(error);
        update((state) => ({ ...state, error: errorMessage, loading: false }));
        throw error;
      }
    },

    resetToIdle(): void {
      savedChapterEditorScroll.set(null);
      update((state) => ({
        ...initialState(),
        version: state.version,
        buildMeta: state.buildMeta,
      }));
    },

    async restartSession(restartAtStep: string): Promise<void> {
      update((state) => ({ ...state, loading: true, error: null }));
      if (restartAtStep !== 'chapter_editing') {
        savedChapterEditorScroll.set(null);
      }

      try {
        await api.session.restart(restartAtStep);
        await this.loadSession();

        update((state) => ({ ...state, loading: false }));
      } catch (error) {
        const errorMessage = handleApiError(error);
        update((state) => ({ ...state, error: errorMessage, loading: false }));
        throw error;
      }
    },

    async goBackToPreviousStep(): Promise<boolean> {
      const state = get({ subscribe });
      const options = state.restartOptions || [];
      if (!options.length) {
        return false;
      }
      const previousStep = options[0];
      if (!previousStep) return false;

      try {
        if (previousStep === 'idle') {
          await this.deleteSession();
          return true;
        }
        await this.restartSession(previousStep);
        return true;
      } catch {
        return false;
      }
    },

    async loadChapters(): Promise<void> {
      update((state) => ({ ...state, loading: true }));

      try {
        const data = await api.chapters.getAll();

        update((state) => ({
          ...state,
          chapters: data.chapters,
          selectionStats: data.selection_stats,
          loading: false,
        }));
      } catch (error) {
        const errorMessage = handleApiError(error);
        update((state) => ({ ...state, error: errorMessage, loading: false }));
      }
    },

    setLoading(loading: boolean): void {
      update((state) => ({ ...state, loading }));
    },

    setError(error: string | null): void {
      update((state) => ({ ...state, error }));
    },

    clearError(): void {
      update((state) => ({ ...state, error: null }));
    },

    updateProgress(progressData: SessionProgress): void {
      update((state) => ({ ...state, progress: progressData }));
    },

    updateStep(newStep: string): void {
      update((state) => ({ ...state, step: newStep }));
    },

    updateChapters(chapters: ChapterData[]): void {
      update((state) => ({ ...state, chapters }));
    },

    updateSelectionStats(stats: SelectionStats): void {
      update((state) => ({ ...state, selectionStats: stats }));
    },

    updateHistoryState(canUndo: boolean, canRedo: boolean): void {
      update((state) => ({ ...state, canUndo, canRedo }));
    },

    updateCueSources(cueSources: ExistingCueSource[]): void {
      update((state) => ({ ...state, cueSources }));
    },

    connectWebSocket(): void {
      connectWebSocket();
      if (!webSocketHandlersSetup) {
        setupWebSocketHandlers();
        webSocketHandlersSetup = true;
      }
    },

    async loadActiveSession(): Promise<ActiveSessionInfo | null> {
      update((state) => ({ ...state, loading: true, error: null }));

      try {
        const response = await api.session.getStatus();

        if (response.step) {
          update((state) => ({
            ...state,
            step: response.step!,
            version: response.version ?? null,
            buildMeta: response.build_meta ?? null,
          }));
        }

        if (response.has_pipeline) {
          await this.loadSession();
          return {
            hasSession: true,
            sessionId: response.item_id,
            step: response.step,
          };
        } else {
          update((state) => ({
            ...state,
            loading: false,
            step: response.step ?? 'idle',
          }));
          return {
            hasSession: false,
            step: response.step ?? 'idle',
          };
        }
      } catch (error) {
        console.error('Failed to load active session:', error);
        update((state) => ({ ...state, loading: false }));
        return null;
      }
    },

    destroy(): void {
      unsubscribeFunctions.forEach((fn) => fn());
      disconnectWebSocket();
      webSocketHandlersSetup = false;
    },
  };

  return store;
}

export const session = createSessionStore();

export const pendingAddChapterDialog = writable<PendingAddChapterDialog | null>(null);

export const savedChapterEditorScroll = writable<number | null>(null);

export const step = derived(session, ($session) => $session.step);
export const chapters = derived(session, ($session) => $session.chapters);
export const selectionStats = derived(session, ($session) => $session.selectionStats);
export const canUndo = derived(session, ($session) => $session.canUndo);
export const canRedo = derived(session, ($session) => $session.canRedo);
export const progress = derived(session, ($session) => $session.progress);
export const loading = derived(session, ($session) => $session.loading);
export const error = derived(session, ($session) => $session.error);
export const transcriptionStatuses = derived(session, ($session) => $session.transcriptionStatuses);

export async function initializeSession(): Promise<ActiveSessionInfo | null> {
  try {
    const sessionInfo = await session.loadActiveSession();
    if (sessionInfo && sessionInfo.hasSession) {
      const newUrl = new URL(window.location.href);
      newUrl.searchParams.delete('session');
      window.history.replaceState({}, '', newUrl);

      return sessionInfo;
    }
  } catch (error) {
    console.error('Failed to load active session:', error);
  }

  return null;
}
