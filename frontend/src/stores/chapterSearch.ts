import { writable } from 'svelte/store';
import { WebSocketManager } from '../utils/websocket';
import type { RuleSet } from '../types/rules';

const WS_BASE = window.location.origin.replace(/^http/, 'ws').replace(/^https/, 'wss');

interface SearchProgress {
  current: number;
  total: number;
}

interface SearchResultBook {
  id: string;
  name: string;
  author?: string;
  series?: string;
  has_cover?: boolean;
  is_ignored: boolean;
  chapters?: unknown[];
  matched_rule_ids?: string[];
  [key: string]: unknown;
}

interface ChapterSearchLibrary {
  id: string;
  name: string;
  [key: string]: unknown;
}

interface ChapterSearchState {
  page: 'landing' | 'searching' | 'results' | 'stats';
  libraries: ChapterSearchLibrary[];
  rootRuleset: RuleSet | null;
  currentTask: string | null;
  progress: SearchProgress | null;
  count: number;
  libraryName: string | null;
  results: SearchResultBook[];
  stats: unknown;
  highlightedBookId: string | null;
  showIgnored: boolean;
}

interface PageMessage {
  page?: string;
  state?: Record<string, unknown>;
}

function createChapterSearchStore() {
  const { subscribe, update } = writable<ChapterSearchState>({
    page: 'landing',
    libraries: [],
    rootRuleset: null,
    currentTask: null,
    progress: null,
    count: 0,
    libraryName: null,
    results: [],
    stats: null,
    highlightedBookId: null,
    showIgnored: false,
  });

  let ws: WebSocketManager | null = null;

  function _buildWsUrl() {
    return `${WS_BASE}/ws/chapter-search`;
  }

  function connect() {
    if (ws && ws.isConnected()) return;

    ws = new WebSocketManager();
    ws.url = _buildWsUrl();

    ws.handleMessage = (raw: unknown) => {
      try {
        const { page, state } = (raw ?? {}) as PageMessage;
        if (!page || !state) return;

        if (page === 'landing') {
          update((s) => ({
            ...s,
            page: 'landing',
            libraries: (state.libraries as ChapterSearchLibrary[] | undefined) ?? [],
            rootRuleset: (state.root_ruleset as RuleSet | null | undefined) ?? null,
            results: [],
            count: 0,
            libraryName: null,
            highlightedBookId: null,
          }));
        } else if (page === 'searching') {
          update((s) => ({
            ...s,
            page: 'searching',
            currentTask: (state.current_task as string | null | undefined) ?? null,
            progress: (state.progress as SearchProgress | null | undefined) ?? null,
          }));
        } else if (page === 'stats') {
          update((s) => ({
            ...s,
            page: 'stats',
            stats: state.stats ?? null,
            libraryName: (state.library_name as string | null | undefined) ?? null,
          }));
        } else if (page === 'results') {
          const results = (state.results as SearchResultBook[] | undefined) ?? [];
          const firstNonIgnored = results.find((b) => !b.is_ignored) ?? null;
          update((s) => {
            const alreadyOnResults = s.page === 'results';
            const prevBookStillExists =
              alreadyOnResults && s.highlightedBookId != null && results.some((b) => b.id === s.highlightedBookId);
            return {
              ...s,
              page: 'results',
              count: (state.count as number | undefined) ?? 0,
              libraryName: (state.library_name as string | null | undefined) ?? null,
              results,
              rootRuleset: (state.root_ruleset as RuleSet | null | undefined) ?? s.rootRuleset,
              highlightedBookId: prevBookStillExists
                ? s.highlightedBookId
                : firstNonIgnored
                  ? firstNonIgnored.id
                  : null,
              showIgnored: alreadyOnResults ? s.showIgnored : false,
            };
          });
        }
      } catch (e) {
        console.error('Chapter search WS parse error:', e);
      }
    };

    ws.connect();
  }

  function disconnect() {
    if (ws) {
      ws.disconnect();
      ws = null;
    }
  }

  function _send(action: string, extra: Record<string, unknown> = {}) {
    if (ws && ws.isConnected()) {
      ws.send(JSON.stringify({ action, ...extra }));
    } else {
      console.warn('Chapter search WS not connected');
    }
  }

  function startSearch(libraryId: string, libraryName: string) {
    _send('start_search', { library_id: libraryId, library_name: libraryName });
  }

  function startStats(libraryId: string, libraryName: string) {
    _send('start_stats', { library_id: libraryId, library_name: libraryName });
  }

  function cancel() {
    _send('cancel');
  }

  function backToLanding() {
    _send('back_to_landing');
  }

  function refreshResults() {
    _send('refresh_results');
  }

  async function saveRuleset(ruleset: RuleSet) {
    try {
      const resp = await fetch('/api/chapter-search/ruleset', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ruleset }),
      });
      if (!resp.ok) {
        console.error('Failed to save ruleset:', resp.status);
      }
    } catch (e) {
      console.error('Error saving ruleset:', e);
    }
  }

  async function toggleIgnore(bookId: string) {
    try {
      await fetch(`/api/chapter-search/ignore/${bookId}`, { method: 'POST' });
    } catch (e) {
      console.error('Error toggling ignore:', e);
    }
  }

  async function clearCache(libraryId: string | null = null): Promise<boolean> {
    try {
      const resp = await fetch('/api/chapter-search/clear-cache', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ library_id: libraryId }),
      });
      return resp.ok;
    } catch (e) {
      console.error('Error clearing cache:', e);
      return false;
    }
  }

  function setHighlightedBook(bookId: string | null) {
    update((s) => ({ ...s, highlightedBookId: bookId }));
  }

  function setShowIgnored(show: boolean) {
    update((s) => {
      const newState = { ...s, showIgnored: show };
      if (!show && s.highlightedBookId) {
        const highlighted = s.results.find((b) => b.id === s.highlightedBookId);
        if (highlighted && highlighted.is_ignored) {
          const idx = s.results.findIndex((b) => b.id === s.highlightedBookId);
          const after = s.results.slice(idx + 1).find((b) => !b.is_ignored);
          const before = s.results
            .slice(0, idx)
            .reverse()
            .find((b) => !b.is_ignored);
          newState.highlightedBookId = (after ?? before)?.id ?? null;
        }
      }
      return newState;
    });
  }

  return {
    subscribe,
    connect,
    disconnect,
    startSearch,
    startStats,
    cancel,
    backToLanding,
    refreshResults,
    saveRuleset,
    toggleIgnore,
    clearCache,
    setHighlightedBook,
    setShowIgnored,
  };
}

export const chapterSearch = createChapterSearchStore();
