// WebSocket utilities for real-time communication
const WS_BASE = window.location.origin.replace(/^https?/, 'ws');

export class WebSocketManager {
    constructor() {
        this.ws = null;
        this.url = `${WS_BASE}/ws`;
        this.listeners = new Map();
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 1000; // Start with 1 second
        this.isConnecting = false;
        this.shouldReconnect = true;
    }

    connect() {
        if (this.isConnecting || (this.ws && this.ws.readyState === WebSocket.CONNECTING)) {
            return;
        }

        this.isConnecting = true;

        try {
            this.ws = new WebSocket(this.url);

            this.ws.onopen = (event) => {
                console.log(`WebSocket connected`);
                this.isConnecting = false;
                this.reconnectAttempts = 0;
                this.reconnectDelay = 1000;
                this.emit('connected', event);
            };

            this.ws.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    this.handleMessage(message);
                } catch (error) {
                    console.error('Failed to parse WebSocket message:', error);
                    this.emit('error', {type: 'parse_error', error});
                }
            };

            this.ws.onclose = (event) => {
                console.log(`WebSocket disconnected`, event);
                this.isConnecting = false;
                this.emit('disconnected', event);

                if (this.shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.scheduleReconnect();
                }
            };

            this.ws.onerror = (error) => {
                console.error(`WebSocket error:`, error);
                this.isConnecting = false;
                this.emit('error', {type: 'connection_error', error});
            };

        } catch (error) {
            console.error('Failed to create WebSocket:', error);
            this.isConnecting = false;
            this.emit('error', {type: 'creation_error', error});
        }
    }

    scheduleReconnect() {
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

    handleMessage(message) {
        console.log('WebSocket message received:', message);

        const {type, data} = message;

        // Emit specific event types
        this.emit(type, data);

        // Also emit a general 'message' event
        this.emit('message', message);
    }

    send(message) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            try {
                const payload = typeof message === 'string' ? message : JSON.stringify(message);
                this.ws.send(payload);
                return true;
            } catch (error) {
                console.error('Failed to send WebSocket message:', error);
                return false;
            }
        } else {
            console.warn('WebSocket not connected, cannot send message:', message);
            return false;
        }
    }

    on(event, callback) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, new Set());
        }
        this.listeners.get(event).add(callback);
    }

    off(event, callback) {
        if (this.listeners.has(event)) {
            this.listeners.get(event).delete(callback);
        }
    }

    emit(event, data) {
        if (this.listeners.has(event)) {
            this.listeners.get(event).forEach(callback => {
                try {
                    callback(data);
                } catch (error) {
                    console.error(`Error in WebSocket event handler for ${event}:`, error);
                }
            });
        }
    }

    disconnect() {
        this.shouldReconnect = false;

        if (this.ws) {
            this.ws.close(1000, 'Client disconnect');
            this.ws = null;
        }
    }

    getState() {
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

    isConnected() {
        return this.ws && this.ws.readyState === WebSocket.OPEN;
    }
}

// Message types (matching backend)
export const MessageType = {
    STATUS: 'status',
    PROGRESS_UPDATE: 'progress_update',
    STEP_CHANGE: 'step_change',
    CHAPTER_UPDATE: 'chapter_update',
    HISTORY_UPDATE: 'history_update',
    BATCH_OPERATION: 'batch_operation',
    ERROR: 'error'
};

// Factory function to create WebSocket manager
export function createWebSocketManager() {
    return new WebSocketManager();
}

// Helper for testing WebSocket connectivity
export async function testWebSocketConnection() {
    return new Promise((resolve, reject) => {
        const testWs = new WebSocket(`${WS_BASE}/ws`);
        const timeout = setTimeout(() => {
            testWs.close();
            reject(new Error('WebSocket connection test timeout'));
        }, 5000);

        testWs.onopen = () => {
            clearTimeout(timeout);
            testWs.close();
            resolve(true);
        };

        testWs.onerror = (error) => {
            clearTimeout(timeout);
            reject(error);
        };

        testWs.onclose = (event) => {
            clearTimeout(timeout);
            if (event.wasClean) {
                resolve(true);
            } else {
                reject(new Error(`WebSocket closed unexpectedly: ${event.code} ${event.reason}`));
            }
        };
    });
}

// Global WebSocket manager instance
let globalWebSocketManager = null;

// Export the manager instance for direct access
export const wsManager = {
    connect() {
        return connectWebSocket();
    },
    disconnect() {
        return disconnectWebSocket();
    },
    isConnected() {
        return isWebSocketConnected();
    },
    getState() {
        return getWebSocketState();
    },
    send(message) {
        return sendWebSocketMessage(message);
    },
    getReconnectionInfo() {
        if (!globalWebSocketManager) {
            return {isReconnecting: false, attempts: 0, maxAttempts: 0};
        }
        return {
            isReconnecting: globalWebSocketManager.isConnecting,
            attempts: globalWebSocketManager.reconnectAttempts,
            maxAttempts: globalWebSocketManager.maxReconnectAttempts
        };
    }
};

// Connection event handlers
const connectionListeners = new Set();

export function onWebSocketConnection(callback) {
    connectionListeners.add(callback);

    // Return unsubscribe function
    return () => {
        connectionListeners.delete(callback);
    };
}

function notifyConnectionChange(connected) {
    connectionListeners.forEach(callback => {
        try {
            callback(connected);
        } catch (error) {
            console.error('Error in connection event handler:', error);
        }
    });
}

// Message types for compatibility (matching backend)
export const WS_MESSAGE_TYPES = {
    STATUS: 'status',
    PROGRESS_UPDATE: 'progress_update',
    STEP_CHANGE: 'step_change',
    CHAPTER_UPDATE: 'chapter_update',
    HISTORY_UPDATE: 'history_update',
    BATCH_OPERATION: 'batch_operation',
    ERROR: 'error',
    SELECTION_STATS: 'selection_stats'
};

export function connectWebSocket() {
    // If we already have a connected WebSocket, don't disconnect it
    if (globalWebSocketManager && globalWebSocketManager.isConnected()) {
        return globalWebSocketManager;
    }

    // Only disconnect if we have a manager that's not connected (e.g., in error state)
    if (globalWebSocketManager) {
        globalWebSocketManager.disconnect();
    }

    globalWebSocketManager = new WebSocketManager();

    // Set up connection event handlers
    globalWebSocketManager.on('connected', () => {
        notifyConnectionChange(true);
    });

    globalWebSocketManager.on('disconnected', () => {
        notifyConnectionChange(false);
    });

    globalWebSocketManager.connect();
    return globalWebSocketManager;
}

export function disconnectWebSocket() {
    if (globalWebSocketManager) {
        globalWebSocketManager.disconnect();
        globalWebSocketManager = null;
        notifyConnectionChange(false);
    }
}

export function onWebSocketMessage(messageType, callback) {
    if (!globalWebSocketManager) {
        console.warn('WebSocket not connected, cannot register message handler');
        return () => {
        }; // Return empty unsubscribe function
    }

    globalWebSocketManager.on(messageType, callback);

    // Return unsubscribe function
    return () => {
        if (globalWebSocketManager) {
            globalWebSocketManager.off(messageType, callback);
        }
    };
}

export function sendWebSocketMessage(message) {
    if (globalWebSocketManager) {
        return globalWebSocketManager.send(message);
    }
    return false;
}

export function getWebSocketState() {
    return globalWebSocketManager ? globalWebSocketManager.getState() : 'DISCONNECTED';
}

export function isWebSocketConnected() {
    return globalWebSocketManager ? globalWebSocketManager.isConnected() : false;
}

export default WebSocketManager;