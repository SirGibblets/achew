/**
 * Chapter Search store — manages dedicated WebSocket connection to /ws/chapter-search
 * and all state for the Chapter Search feature.
 */

import {writable, get} from 'svelte/store';
import {WebSocketManager} from '../utils/websocket.js';

const WS_BASE = window.location.origin.replace(/^http/, 'ws').replace(/^https/, 'wss');

function createChapterSearchStore() {
    const {subscribe, set, update} = writable({
        // Page: 'landing' | 'searching' | 'results'
        page: 'landing',

        // Landing page state
        libraries: [],
        rootRuleset: null,          // null until loaded from backend

        // Searching page state
        currentTask: null,          // 'full-sync' | 'incremental-sync' | 'search'
        progress: null,             // {current, total}

        // Results page state
        count: 0,
        libraryName: null,
        results: [],                // [{id, name, author, series, has_cover, is_ignored, chapters, matched_rule_ids}]

        // Stats page state
        stats: null,

        // Frontend-only state (not synced)
        highlightedBookId: null,
        showIgnored: false,
    });

    let ws = null;

    function _buildWsUrl() {
        return `${WS_BASE}/ws/chapter-search`;
    }

    function connect() {
        if (ws && ws.isConnected()) return;

        ws = new WebSocketManager();
        ws.url = _buildWsUrl();

        ws.on('message', (msg) => {
            // Chapter search WS sends page-scoped JSON directly (not typed like main WS)
            // The message is the raw parsed object with {page, state}
        });

        // Override handleMessage to handle our page-scoped format
        ws.handleMessage = (raw) => {
            try {
                const {page, state} = raw;
                if (!page || !state) return;

                if (page === 'landing') {
                    update(s => ({
                        ...s,
                        page: 'landing',
                        libraries: state.libraries || [],
                        rootRuleset: state.root_ruleset || null,
                        // Reset results state
                        results: [],
                        count: 0,
                        libraryName: null,
                        highlightedBookId: null,
                    }));
                } else if (page === 'searching') {
                    update(s => ({
                        ...s,
                        page: 'searching',
                        currentTask: state.current_task || null,
                        progress: state.progress || null,
                    }));
                } else if (page === 'stats') {
                    update(s => ({
                        ...s,
                        page: 'stats',
                        stats: state.stats || null,
                        libraryName: state.library_name || null,
                    }));
                } else if (page === 'results') {
                    const results = state.results || [];
                    const firstNonIgnored = results.find(b => !b.is_ignored) || null;
                    update(s => {
                        const alreadyOnResults = s.page === 'results';
                        const prevBookStillExists = alreadyOnResults && s.highlightedBookId
                            && results.some(b => b.id === s.highlightedBookId);
                        return {
                            ...s,
                            page: 'results',
                            count: state.count || 0,
                            libraryName: state.library_name || null,
                            results,
                            rootRuleset: state.root_ruleset || s.rootRuleset,
                            highlightedBookId: prevBookStillExists
                                ? s.highlightedBookId
                                : (firstNonIgnored ? firstNonIgnored.id : null),
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

    function _send(action, extra = {}) {
        if (ws && ws.isConnected()) {
            ws.send(JSON.stringify({action, ...extra}));
        } else {
            console.warn('Chapter search WS not connected');
        }
    }

    function startSearch(libraryId, libraryName) {
        _send('start_search', {library_id: libraryId, library_name: libraryName});
    }

    function startStats(libraryId, libraryName) {
        _send('start_stats', {library_id: libraryId, library_name: libraryName});
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

    async function saveRuleset(ruleset) {
        try {
            const resp = await fetch('/api/chapter-search/ruleset', {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ruleset}),
            });
            if (!resp.ok) {
                console.error('Failed to save ruleset:', resp.status);
            }
        } catch (e) {
            console.error('Error saving ruleset:', e);
        }
    }

    async function toggleIgnore(bookId) {
        try {
            await fetch(`/api/chapter-search/ignore/${bookId}`, {method: 'POST'});
        } catch (e) {
            console.error('Error toggling ignore:', e);
        }
    }

    async function clearCache(libraryId = null) {
        try {
            const resp = await fetch('/api/chapter-search/clear-cache', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({library_id: libraryId}),
            });
            return resp.ok;
        } catch (e) {
            console.error('Error clearing cache:', e);
            return false;
        }
    }

    function setHighlightedBook(bookId) {
        update(s => ({...s, highlightedBookId: bookId}));
    }

    function setShowIgnored(show) {
        update(s => {
            const newState = {...s, showIgnored: show};
            // If hiding ignored and highlighted book is ignored, shift focus
            if (!show && s.highlightedBookId) {
                const highlighted = s.results.find(b => b.id === s.highlightedBookId);
                if (highlighted && highlighted.is_ignored) {
                    const visible = s.results.filter(b => !b.is_ignored);
                    const idx = s.results.findIndex(b => b.id === s.highlightedBookId);
                    // Find next non-ignored after current position, or previous
                    const after = s.results.slice(idx + 1).find(b => !b.is_ignored);
                    const before = s.results.slice(0, idx).reverse().find(b => !b.is_ignored);
                    newState.highlightedBookId = (after || before)?.id || null;
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
