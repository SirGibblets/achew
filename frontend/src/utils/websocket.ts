const WS_BASE = window.location.origin.replace(/^http/, 'ws').replace(/^https/, 'wss');

type Listener = (data: unknown) => void;

interface ParsedMessage {
  type?: string;
  data?: unknown;
}

export class WebSocketManager {
  ws: WebSocket | null = null;
  url: string = `${WS_BASE}/ws`;
  private readonly listeners = new Map<string, Set<Listener>>();
  reconnectAttempts = 0;
  readonly maxReconnectAttempts = 10;
  private reconnectDelay = 1000;
  isConnecting = false;
  private shouldReconnect = true;

  connect(): void {
    if (this.isConnecting || (this.ws && this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.isConnecting = true;

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = (event) => {
        console.log('WebSocket connected');
        this.isConnecting = false;
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        this.emit('connected', event);
      };

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data as string) as ParsedMessage;
          this.handleMessage(message);
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
          this.emit('error', { type: 'parse_error', error });
        }
      };

      this.ws.onclose = (event) => {
        console.log('WebSocket disconnected', event);
        this.isConnecting = false;
        this.emit('disconnected', event);

        if (this.shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.scheduleReconnect();
        }
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        this.isConnecting = false;
        this.emit('error', { type: 'connection_error', error });
      };
    } catch (error) {
      console.error('Failed to create WebSocket:', error);
      this.isConnecting = false;
      this.emit('error', { type: 'creation_error', error });
    }
  }

  private scheduleReconnect(): void {
    if (!this.shouldReconnect) return;

    this.reconnectAttempts++;
    const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), 30000);

    console.log(`Scheduling WebSocket reconnect attempt ${this.reconnectAttempts} in ${delay}ms`);

    setTimeout(() => {
      if (this.shouldReconnect) {
        this.connect();
      }
    }, delay);
  }

  handleMessage(message: ParsedMessage): void {
    console.log('WebSocket message received:', message);

    const { type, data } = message;

    if (type) {
      this.emit(type, data);
    }
    this.emit('message', message);
  }

  send(message: string | Record<string, unknown>): boolean {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      try {
        const payload = typeof message === 'string' ? message : JSON.stringify(message);
        this.ws.send(payload);
        return true;
      } catch (error) {
        console.error('Failed to send WebSocket message:', error);
        return false;
      }
    }
    console.warn('WebSocket not connected, cannot send message:', message);
    return false;
  }

  on(event: string, callback: Listener): void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(callback);
  }

  off(event: string, callback: Listener): void {
    this.listeners.get(event)?.delete(callback);
  }

  emit(event: string, data: unknown): void {
    const set = this.listeners.get(event);
    if (!set) return;
    set.forEach((callback) => {
      try {
        callback(data);
      } catch (error) {
        console.error(`Error in WebSocket event handler for ${event}:`, error);
      }
    });
  }

  disconnect(): void {
    this.shouldReconnect = false;

    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }
  }

  getState(): 'DISCONNECTED' | 'CONNECTING' | 'CONNECTED' | 'CLOSING' | 'UNKNOWN' {
    if (!this.ws) return 'DISCONNECTED';

    switch (this.ws.readyState) {
      case WebSocket.CONNECTING:
        return 'CONNECTING';
      case WebSocket.OPEN:
        return 'CONNECTED';
      case WebSocket.CLOSING:
        return 'CLOSING';
      case WebSocket.CLOSED:
        return 'DISCONNECTED';
      default:
        return 'UNKNOWN';
    }
  }

  isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }
}

export const MessageType = {
  STATUS: 'status',
  PROGRESS_UPDATE: 'progress_update',
  STEP_CHANGE: 'step_change',
  CHAPTER_UPDATE: 'chapter_update',
  HISTORY_UPDATE: 'history_update',
  BATCH_OPERATION: 'batch_operation',
  ERROR: 'error',
} as const;

export function createWebSocketManager(): WebSocketManager {
  return new WebSocketManager();
}

export const WS_MESSAGE_TYPES = {
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
} as const;

let globalWebSocketManager: WebSocketManager | null = null;

interface ReconnectionInfo {
  isReconnecting: boolean;
  attempts: number;
  maxAttempts: number;
}

export const wsManager = {
  connect(): WebSocketManager {
    return connectWebSocket();
  },
  disconnect(): void {
    disconnectWebSocket();
  },
  isConnected(): boolean {
    return isWebSocketConnected();
  },
  getState(): string {
    return getWebSocketState();
  },
  send(message: string | Record<string, unknown>): boolean {
    return sendWebSocketMessage(message);
  },
  getReconnectionInfo(): ReconnectionInfo {
    if (!globalWebSocketManager) {
      return { isReconnecting: false, attempts: 0, maxAttempts: 0 };
    }
    return {
      isReconnecting: globalWebSocketManager.isConnecting,
      attempts: globalWebSocketManager.reconnectAttempts,
      maxAttempts: globalWebSocketManager.maxReconnectAttempts,
    };
  },
};

type ConnectionListener = (connected: boolean) => void;
const connectionListeners = new Set<ConnectionListener>();

export function onWebSocketConnection(callback: ConnectionListener): () => void {
  connectionListeners.add(callback);
  return () => {
    connectionListeners.delete(callback);
  };
}

function notifyConnectionChange(connected: boolean): void {
  connectionListeners.forEach((callback) => {
    try {
      callback(connected);
    } catch (error) {
      console.error('Error in connection event handler:', error);
    }
  });
}

export function connectWebSocket(): WebSocketManager {
  if (globalWebSocketManager && globalWebSocketManager.isConnected()) {
    return globalWebSocketManager;
  }

  if (globalWebSocketManager) {
    globalWebSocketManager.disconnect();
  }

  globalWebSocketManager = new WebSocketManager();

  globalWebSocketManager.on('connected', () => {
    notifyConnectionChange(true);
  });

  globalWebSocketManager.on('disconnected', () => {
    notifyConnectionChange(false);
  });

  globalWebSocketManager.connect();
  return globalWebSocketManager;
}

export function disconnectWebSocket(): void {
  if (globalWebSocketManager) {
    globalWebSocketManager.disconnect();
    globalWebSocketManager = null;
    notifyConnectionChange(false);
  }
}

export function onWebSocketMessage(messageType: string, callback: Listener): () => void {
  if (!globalWebSocketManager) {
    console.warn('WebSocket not connected, cannot register message handler');
    return () => {};
  }

  globalWebSocketManager.on(messageType, callback);

  return () => {
    if (globalWebSocketManager) {
      globalWebSocketManager.off(messageType, callback);
    }
  };
}

export function sendWebSocketMessage(message: string | Record<string, unknown>): boolean {
  if (globalWebSocketManager) {
    return globalWebSocketManager.send(message);
  }
  return false;
}

export function getWebSocketState(): string {
  return globalWebSocketManager ? globalWebSocketManager.getState() : 'DISCONNECTED';
}

export function isWebSocketConnected(): boolean {
  return globalWebSocketManager !== null && globalWebSocketManager.isConnected();
}

export default WebSocketManager;
