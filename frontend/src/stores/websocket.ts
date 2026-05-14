import { writable, derived } from 'svelte/store';
import { wsManager, onWebSocketConnection } from '../utils/websocket';

interface WebSocketState {
  connected: boolean;
  reconnecting: boolean;
  reconnectAttempts: number;
  maxReconnectAttempts: number;
  lastError: string | null;
}

function createWebSocketStore() {
  const { subscribe, update } = writable<WebSocketState>({
    connected: false,
    reconnecting: false,
    reconnectAttempts: 0,
    maxReconnectAttempts: 5,
    lastError: null,
  });

  const unsubscribeConnection = onWebSocketConnection((connected) => {
    const reconnectionInfo = wsManager.getReconnectionInfo();

    update((state) => ({
      ...state,
      connected,
      reconnecting: reconnectionInfo.isReconnecting,
      reconnectAttempts: reconnectionInfo.attempts,
      maxReconnectAttempts: reconnectionInfo.maxAttempts,
      lastError: connected ? null : state.lastError,
    }));
  });

  return {
    subscribe,

    connect(): void {
      wsManager.connect();
    },

    disconnect(): void {
      wsManager.disconnect();
    },

    isConnected(): boolean {
      return wsManager.isConnected();
    },

    setError(error: string | null): void {
      update((state) => ({ ...state, lastError: error }));
    },

    clearError(): void {
      update((state) => ({ ...state, lastError: null }));
    },

    destroy(): void {
      unsubscribeConnection();
      wsManager.disconnect();
    },
  };
}

export const websocket = createWebSocketStore();

export const isConnected = derived(websocket, ($ws) => $ws.connected);
export const isReconnecting = derived(websocket, ($ws) => $ws.reconnecting);
export const connectionStatus = derived(websocket, ($ws) => {
  if ($ws.connected) return 'connected';
  if ($ws.reconnecting) return 'reconnecting';
  return 'disconnected';
});
