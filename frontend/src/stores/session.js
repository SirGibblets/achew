import {writable, derived, get} from 'svelte/store';
import {api, handleApiError} from '../utils/api.js';
import {connectWebSocket, disconnectWebSocket, onWebSocketMessage, WS_MESSAGE_TYPES} from '../utils/websocket.js';

// Create the main session store
function createSessionStore() {
    const {subscribe, set, update} = writable({
        // Session info
        step: 'idle',
        itemId: '',

        // Progress tracking
        progress: {
            step: 'idle',
            percent: 0,
            message: '',
            details: {}
        },

        // Chapter data
        chapters: [],
        selectionStats: {
            total: 0,
            selected: 0,
            unselected: 0
        },

        // History state
        canUndo: false,
        canRedo: false,

        // Book metadata
        book: null,
        cueSources: [],

        restartOptions: [],

        // Smart Detect Configuration
        smartDetectConfig: {
            segment_length: 8.0,
            min_clip_length: 1.0,
            asr_buffer: 0.25,
        },
        smartDetectConfigLoading: false,

        // App version
        version: null,

        // UI state
        loading: false,
        error: null
    });

    // WebSocket message handlers
    let unsubscribeFunctions = [];
    let webSocketHandlersSetup = false;

    const setupWebSocketHandlers = () => {
        // Clean up existing handlers
        unsubscribeFunctions.forEach(fn => fn());
        unsubscribeFunctions = [];

        // Progress updates
        unsubscribeFunctions.push(
            onWebSocketMessage(WS_MESSAGE_TYPES.PROGRESS_UPDATE, (data) => {
                update(state => ({
                    ...state,
                    progress: {
                        step: data.step,
                        percent: data.percent,
                        message: data.message,
                        details: data.details || {}
                    }
                }));
            })
        );

        // Step changes
        unsubscribeFunctions.push(
            onWebSocketMessage(WS_MESSAGE_TYPES.STEP_CHANGE, (data) => {
                update(state => ({
                    ...state,
                    step: data.new_step,
                    // Handle cue sources data if present
                    ...(data.cue_sources && {cueSources: data.cue_sources}),
                    // Handle restart_options if present
                    ...(data.restart_options && {restartOptions: data.restart_options}),
                }));
                // Re-open the add-chapter dialog if a partial scan just completed
                if (data.new_step === 'chapter_editing' && data.chapter_id) {
                    pendingAddChapterDialog.set({
                        chapter_id: data.chapter_id,
                        open_tab: data.open_tab || 'detected_cue',
                    });
                }
            })
        );

        // Chapter updates
        unsubscribeFunctions.push(
            onWebSocketMessage(WS_MESSAGE_TYPES.CHAPTER_UPDATE, (data) => {
                update(state => ({
                    ...state,
                    chapters: data.chapters,
                    selectionStats: {
                        total: data.total_count,
                        selected: data.selected_count,
                        unselected: data.total_count - data.selected_count
                    }
                }));
            })
        );

        // History updates
        unsubscribeFunctions.push(
            onWebSocketMessage(WS_MESSAGE_TYPES.HISTORY_UPDATE, (data) => {
                update(state => ({
                    ...state,
                    canUndo: data.can_undo,
                    canRedo: data.can_redo
                }));
            })
        );

        // Selection stats updates
        unsubscribeFunctions.push(
            onWebSocketMessage(WS_MESSAGE_TYPES.SELECTION_STATS, (data) => {
                update(state => ({
                    ...state,
                    selectionStats: {
                        total: data.total,
                        selected: data.selected,
                        unselected: data.unselected
                    }
                }));
            })
        );

        // Error messages
        unsubscribeFunctions.push(
            onWebSocketMessage(WS_MESSAGE_TYPES.ERROR, (data) => {
                update(state => ({
                    ...state,
                    error: data.message,
                    loading: false
                }));
            })
        );

        // Status messages
        unsubscribeFunctions.push(
            onWebSocketMessage(WS_MESSAGE_TYPES.STATUS, (data) => {
                console.log('WebSocket status:', data);

                // Handle book updates
                if (data.type === 'book_update' && data.book) {
                    update(state => ({
                        ...state,
                        book: data.book
                    }));
                }
            })
        );
    };

    return {
        subscribe,

        // Session management
        async createSession(itemId) {
            update(state => ({...state, loading: true, error: null}));

            try {
                const response = await api.session.create(itemId);

                update(state => ({
                    ...state,
                    itemId,
                    loading: false
                }));

                // Ensure WebSocket connection is established (but don't force reconnect if already connected)
                connectWebSocket();
                // Setup handlers if not already done
                if (!webSocketHandlersSetup) {
                    setupWebSocketHandlers();
                    webSocketHandlersSetup = true;
                }

                return true;
            } catch (error) {
                const errorMessage = handleApiError(error);
                update(state => ({
                    ...state,
                    error: errorMessage,
                    loading: false
                }));
                throw error;
            }
        },

        async loadSession() {
            update(state => ({...state, loading: true, error: null}));

            try {
                const response = await api.session.get();
                const data = response;

                update(state => ({
                    ...state,
                    step: data.step,
                    itemId: data.item_id,
                    progress: data.progress,
                    selectionStats: data.selection_stats,
                    canUndo: data.can_undo,
                    canRedo: data.can_redo,
                    cueSources: data.cue_sources || [],
                    book: data.book || null,
                    restartOptions: data.restart_options || [],
                    state: data, // Store the full state object for debugging
                    loading: false
                }));

                // WebSocket should already be connected, but ensure handlers are setup
                if (!webSocketHandlersSetup) {
                    setupWebSocketHandlers();
                    webSocketHandlersSetup = true;
                }

                return data;
            } catch (error) {
                const errorMessage = handleApiError(error);
                update(state => ({
                    ...state,
                    error: errorMessage,
                    loading: false
                }));
                throw error;
            }
        },

        async deleteSession() {
            update(state => ({...state, loading: true, error: null}));

            try {
                await api.session.delete();

                // Reset to initial state
                set({
                    step: 'idle',
                    itemId: '',
                    progress: {step: 'idle', percent: 0, message: '', details: {}},
                    chapters: [],
                    selectionStats: {total: 0, selected: 0, unselected: 0},
                    canUndo: false,
                    canRedo: false,
                    book: null,
                    cueSources: [],
                    restartOptions: [],
                    smartDetectConfig: {
                        segment_length: 8.0,
                        min_clip_length: 1.0,
                        asr_buffer: 0.25,
                    },
                    smartDetectConfigLoading: false,
                    version: null,
                    loading: false,
                    error: null
                });

            } catch (error) {
                const errorMessage = handleApiError(error);
                update(state => ({
                    ...state,
                    error: errorMessage,
                    loading: false
                }));
                throw error;
            }
        },

        // Reset session state without making API call (for when backend already deleted session)
        resetToIdle() {
            // Reset to initial state (same as deleteSession but without API call)
            set({
                step: 'idle',
                itemId: '',
                progress: {step: 'idle', percent: 0, message: '', details: {}},
                chapters: [],
                selectionStats: {total: 0, selected: 0, unselected: 0},
                canUndo: false,
                canRedo: false,
                book: null,
                cueSources: [],
                restartOptions: [],
                smartDetectConfig: {
                    segment_length: 8.0,
                    min_clip_length: 1.0,
                    asr_buffer: 0.25,
                },
                smartDetectConfigLoading: false,
                version: null,
                loading: false,
                error: null
            });
        },

        async restartSession(restartAtStep) {
            update(state => ({...state, loading: true, error: null}));

            try {
                await api.session.restart(restartAtStep);

                // Force reload the session data to ensure we have the latest state
                await this.loadSession();

                update(state => ({...state, loading: false}));

            } catch (error) {
                const errorMessage = handleApiError(error);
                update(state => ({
                    ...state,
                    error: errorMessage,
                    loading: false
                }));
                throw error;
            }
        },

        // Restart to the previous step based on available restart options
        async goBackToPreviousStep() {
            // Read current restart options from store state
            const state = get({subscribe});
            const options = state.restartOptions || [];
            if (!options.length) {
                // No restart option available; no-op
                return false;
            }
            const previousStep = options[0]; // Closest previous step per backend ordering

            try {
                if (previousStep == 'idle') {
                    await session.deleteSession();
                    return true;
                }
                await this.restartSession(previousStep);
                return true;
            } catch (error) {
                // Error is already set in restartSession; propagate false
                return false;
            }
        },

        // Chapter management
        async loadChapters() {
            update(state => ({...state, loading: true}));

            try {
                const response = await api.chapters.getAll();
                const data = response;

                update(state => ({
                    ...state,
                    chapters: data.chapters,
                    selectionStats: data.selection_stats,
                    loading: false
                }));
            } catch (error) {
                const errorMessage = handleApiError(error);
                update(state => ({
                    ...state,
                    error: errorMessage,
                    loading: false
                }));
            }
        },

        // UI state management
        setLoading(loading) {
            update(state => ({...state, loading}));
        },

        setError(error) {
            update(state => ({...state, error}));
        },

        clearError() {
            update(state => ({...state, error: null}));
        },

        updateProgress(progressData) {
            update(state => ({
                ...state,
                progress: progressData
            }));
        },

        updateStep(newStep) {
            update(state => ({
                ...state,
                step: newStep
            }));
        },

        updateChapters(chapters) {
            update(state => ({
                ...state,
                chapters
            }));
        },

        updateSelectionStats(stats) {
            update(state => ({
                ...state,
                selectionStats: stats
            }));
        },

        updateHistoryState(canUndo, canRedo) {
            update(state => ({
                ...state,
                canUndo,
                canRedo
            }));
        },

        updateCueSources(cueSources) {
            update(state => ({
                ...state,
                cueSources
            }));
        },

        // Smart Detect Configuration management
        async loadSmartDetectConfig() {
            update(state => ({...state, smartDetectConfigLoading: true, error: null}));

            try {
                const response = await api.session.getSmartDetectConfig();
                update(state => ({
                    ...state,
                    smartDetectConfig: response.config,
                    smartDetectConfigLoading: false
                }));
            } catch (error) {
                console.error('Failed to load smart detect config:', error);
                update(state => ({
                    ...state,
                    smartDetectConfigLoading: false
                }));
            }
        },

        // Debounced smart detect config update
        async updateSmartDetectConfig(config) {
            update(state => ({
                ...state,
                smartDetectConfig: config,
                smartDetectConfigLoading: true
            }));

            try {
                await api.session.updateSmartDetectConfig(config);
                update(state => ({
                    ...state,
                    smartDetectConfigLoading: false
                }));
            } catch (error) {
                console.error('Failed to update smart detect config:', error);
                const errorMessage = handleApiError(error);
                update(state => ({
                    ...state,
                    error: errorMessage,
                    smartDetectConfigLoading: false
                }));
            }
        },

        updateSmartDetectConfigLocal(config) {
            update(state => ({
                ...state,
                smartDetectConfig: config
            }));
        },

        // Connect WebSocket independently of session state
        connectWebSocket() {
            connectWebSocket();
            if (!webSocketHandlersSetup) {
                setupWebSocketHandlers();
                webSocketHandlersSetup = true;
            }
        },

        // Auto-load active session
        async loadActiveSession() {
            update(state => ({...state, loading: true, error: null}));

            try {
                const response = await api.session.getStatus();

                // Update session step based on backend response
                if (response.step) {
                    update(state => ({
                        ...state,
                        step: response.step,
                        version: response.version || null
                    }));
                }

                if (response.has_pipeline) {
                    await this.loadSession();
                    return {
                        hasSession: true,
                        sessionId: response.item_id,
                        step: response.step
                    };
                } else {
                    update(state => ({
                        ...state,
                        loading: false,
                        step: response.step || 'idle'
                    }));
                    return {
                        hasSession: false,
                        step: response.step || 'idle'
                    };
                }
            } catch (error) {
                console.error('Failed to load active session:', error);
                update(state => ({...state, loading: false}));
                return null;
            }
        },

        // Cleanup
        destroy() {
            unsubscribeFunctions.forEach(fn => fn());
            disconnectWebSocket();
            webSocketHandlersSetup = false;
        }
    };
}

export const session = createSessionStore();

// Store for re-opening the add-chapter dialog after a partial scan completes
// Set to { chapter_id, open_tab } when a partial scan returns to chapter_editing
export const pendingAddChapterDialog = writable(null);

// Derived stores for convenience
export const step = derived(session, $session => $session.step);
export const chapters = derived(session, $session => $session.chapters);
export const selectionStats = derived(session, $session => $session.selectionStats);
export const canUndo = derived(session, $session => $session.canUndo);
export const canRedo = derived(session, $session => $session.canRedo);
export const progress = derived(session, $session => $session.progress);
export const loading = derived(session, $session => $session.loading);
export const error = derived(session, $session => $session.error);

// Initialize session on page load - check for active session
export async function initializeSession() {
    // Try to load any active session from the backend
    try {
        const sessionInfo = await session.loadActiveSession();
        if (sessionInfo && sessionInfo.hasSession) {
            // Clean URL of any session parameters
            const newUrl = new URL(window.location);
            newUrl.searchParams.delete('session');
            window.history.replaceState({}, '', newUrl);

            return sessionInfo;
        }
    } catch (error) {
        console.error('Failed to load active session:', error);
    }

    return null;
}
