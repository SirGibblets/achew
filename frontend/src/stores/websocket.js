import {writable, derived} from 'svelte/store';
import {wsManager, onWebSocketConnection} from '../utils/websocket.js';

// Create WebSocket connection store
function createWebSocketStore() {
    const {subscribe, set, update} = writable({
        connected: false,
        reconnecting: false,
        reconnectAttempts: 0,
        maxReconnectAttempts: 5,
        lastError: null
    });

    // Listen for connection changes
    const unsubscribeConnection = onWebSocketConnection((connected) => {
        const reconnectionInfo = wsManager.getReconnectionInfo();

        update(state => ({
            ...state,
            connected,
            reconnecting: reconnectionInfo.isReconnecting,
            reconnectAttempts: reconnectionInfo.attempts,
            maxReconnectAttempts: reconnectionInfo.maxAttempts,
            lastError: connected ? null : state.lastError
        }));
    });

    return {
        subscribe,

        connect(sessionId) {
            wsManager.connect(sessionId);
        },

        disconnect() {
            wsManager.disconnect();
        },

        isConnected() {
            return wsManager.isConnected();
        },

        setError(error) {
            update(state => ({
                ...state,
                lastError: error
            }));
        },

        clearError() {
            update(state => ({
                ...state,
                lastError: null
            }));
        },

        // Cleanup
        destroy() {
            unsubscribeConnection();
            wsManager.disconnect();
        }
    };
}

export const websocket = createWebSocketStore();

// Derived stores
export const isConnected = derived(websocket, $ws => $ws.connected);
export const isReconnecting = derived(websocket, $ws => $ws.reconnecting);
export const connectionStatus = derived(websocket, $ws => {
    if ($ws.connected) return 'connected';
    if ($ws.reconnecting) return 'reconnecting';
    return 'disconnected';
});