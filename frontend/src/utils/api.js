// API utilities for making requests to the backend
const API_BASE = window.location.origin;

class APIError extends Error {
    constructor(message, status, details) {
        super(message);
        this.name = 'APIError';
        this.status = status;
        this.details = details;
    }
}

// Helper function to make API requests
async function apiRequest(endpoint, options = {}) {
    const url = `${API_BASE}/api${endpoint}`;

    const config = {
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
        ...options,
    };

    if (config.body && typeof config.body === 'object') {
        config.body = JSON.stringify(config.body);
    }

    try {
        const response = await fetch(url, config);

        if (!response.ok) {
            let errorMessage = `HTTP ${response.status}`;
            let errorDetails = null;

            try {
                const errorData = await response.json();
                errorMessage = errorData.detail || errorData.message || errorMessage;
                errorDetails = errorData;
            } catch {
                errorMessage = await response.text() || errorMessage;
            }

            throw new APIError(errorMessage, response.status, errorDetails);
        }

        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            return await response.json();
        }

        return await response.text();
    } catch (error) {
        if (error instanceof APIError) {
            throw error;
        }

        // Network or other errors
        throw new APIError(
            `Network error: ${error.message}`,
            0,
            {originalError: error}
        );
    }
}

// Session API
export const session = {
    async create(itemId) {
        return apiRequest('/pipeline', {
            method: 'POST',
            body: {item_id: itemId},
        });
    },

    async get() {
        return apiRequest('/pipeline/state');
    },

    async delete() {
        return apiRequest('/pipeline', {
            method: 'DELETE',
        });
    },

    async submit() {
        return apiRequest('/pipeline/submit', {
            method: 'POST',
        });
    },

    async gotoReview() {
        return apiRequest('/pipeline/goto-review', {
            method: 'POST',
        });
    },

    async getStatus() {
        return apiRequest('/status');
    },

    async selectCueSource(option) {
        return apiRequest('/pipeline/cue-source', {
            method: 'POST',
            body: {option},
        });
    },

    async getCueSets() {
        return apiRequest('/pipeline/cue-sets');
    },

    async selectCueSet(chapterCount, includeUnaligned = []) {
        return apiRequest('/pipeline/select-cue-set', {
            method: 'POST',
            body: {
                chapter_count: chapterCount,
                include_unaligned: includeUnaligned
            },
        });
    },

    async validateItem(itemId) {
        return apiRequest('/validate-item', {
            method: 'POST',
            body: {item_id: itemId},
        });
    },

    async restart(restartAtStep) {
        return apiRequest('/pipeline/restart', {
            method: 'POST',
            body: {restart_step: restartAtStep},
        });
    },

    async getCueSources() {
        return apiRequest('/pipeline/cue-sources');
    },

    async getSmartDetectConfig() {
        return apiRequest('/pipeline/smart-detect-config');
    },

    async updateSmartDetectConfig(config) {
        return apiRequest('/pipeline/smart-detect-config', {
            method: 'PUT',
            body: config,
        });
    },

    async getASROptions() {
        return apiRequest('/pipeline/asr-options');
    },

    async updateASROptions(options) {
        return apiRequest('/pipeline/asr-options', {
            method: 'PUT',
            body: options,
        });
    },

    async cancel() {
        return apiRequest('/pipeline/cancel', {
            method: 'POST',
        });
    },

    async configureASR(action) {
        return apiRequest('/pipeline/configure-asr', {
            method: 'POST',
            body: {action},
        });
    },

    async getSegmentCount() {
        return apiRequest('/pipeline/segment-count');
    },
};

// Chapters API
export const chapters = {
    async getAll() {
        return apiRequest('/chapters');
    },

    async updateTitle(chapterId, title) {
        return apiRequest(`/chapters/${chapterId}/title`, {
            method: 'PUT',
            body: {title},
        });
    },

    async toggleSelection(chapterId, selected) {
        return apiRequest(`/chapters/${chapterId}/select`, {
            method: 'PUT',
            body: {selected},
        });
    },

    async delete(chapterId) {
        return apiRequest(`/chapters/${chapterId}`, {
            method: 'DELETE',
        });
    },

    async undo() {
        return apiRequest('/chapters/undo', {
            method: 'POST',
            body: {},
        });
    },

    async redo() {
        return apiRequest('/chapters/redo', {
            method: 'POST',
            body: {},
        });
    },

    async export(format) {
        const response = await fetch(`${API_BASE}/api/chapters/export/${format}`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            },
        });

        if (!response.ok) {
            throw new APIError(`Failed to export ${format}`, response.status);
        }

        const contentDisposition = response.headers.get('content-disposition');
        let filename = `chapters.${format}`;
        if (contentDisposition) {
            const filenameMatch = contentDisposition.match(/filename="(.+)"/);
            if (filenameMatch) {
                filename = filenameMatch[1];
            }
        }

        const contentType = response.headers.get('content-type');
        const data = await response.text();

        return {
            data,
            filename,
            mimeType: contentType || 'text/plain'
        };
    },
};

// Batch operations API
export const batch = {
    async selectAll() {
        return apiRequest('/chapters/select-all', {
            method: 'POST',
            body: {},
        });
    },

    async deselectAll() {
        return apiRequest('/chapters/deselect-all', {
            method: 'POST',
            body: {},
        });
    },

    async processSelected(aiOptions = {}) {
        return apiRequest('/chapters/ai-cleanup', {
            method: 'POST',
            body: {
                ai_options: aiOptions
            },
        });
    },

    async getAIOptions() {
        return apiRequest('/chapters/ai-options');
    },

    async updateAIOptions(aiOptions) {
        return apiRequest('/chapters/ai-options', {
            method: 'PUT',
            body: aiOptions,
        });
    },
};

// Audio API
export const audio = {
    getSegmentUrl(segmentId) {
        // Add cache-busting timestamp to prevent stale audio cache
        const timestamp = Date.now();
        return `${API_BASE}/api/audio/segment/${segmentId}?t=${timestamp}`;
    },

    async listSegments() {
        return apiRequest('/audio/segments');
    },
};

// Health check
export const health = {
    async check() {
        return apiRequest('/health', {
            method: 'GET',
            // Don't throw on health check failures
            headers: {}
        });
    },
};

// Error handling helper
export function handleApiError(error) {
    console.error('API Error:', error);

    if (error instanceof APIError) {
        if (error.message) {
            return error.message;
        }
        // Handle specific HTTP status codes
        switch (error.status) {
            case 401:
                return 'Authentication required. Please check your API credentials.';
            case 403:
                return 'Access forbidden. Please check your permissions.';
            case 404:
                return 'Resource not found. It may have been deleted or moved.';
            case 409:
                return 'Conflict. The resource may be in use or have been modified.';
            case 422:
                return 'Invalid input data. Please check your request.';
            case 429:
                return 'Too many requests. Please wait before trying again.';
            case 500:
                return 'Server error. Please try again later.';
            case 503:
                return 'Service unavailable. The server may be under maintenance.';
            default:
                return 'An unexpected error occurred.';
        }
    }

    // Network or other errors
    return 'Network error. Please check your connection and try again.';
}

// Config API
export const config = {
    async getASRPreferences() {
        return apiRequest('/asr/preferences');
    },

    async setASRPreferences(serviceId, variantId = '', language = '') {
        return apiRequest('/asr/preferences', {
            method: 'POST',
            body: {service_id: serviceId, variant_id: variantId, language: language},
        });
    },

    async getEditorSettings() {
        return apiRequest('/config/editor-settings');
    },

    async updateEditorSettings(settings) {
        return apiRequest('/config/editor-settings', {
            method: 'PATCH',
            body: settings,
        });
    },
};

// LLM API
export const llm = {
    async getProviders() {
        return apiRequest('/llm/providers');
    },

    async getModels(providerId) {
        return apiRequest(`/llm/providers/${providerId}/models`);
    },

    async validateProvider(providerId, config) {
        return apiRequest(`/llm/providers/${providerId}/validate`, {
            method: 'POST',
            body: {provider_id: providerId, config},
        });
    },

    async updateProviderConfig(providerId, config) {
        return apiRequest(`/llm/providers/${providerId}/config`, {
            method: 'POST',
            body: {provider_id: providerId, config},
        });
    },

    async setProviderEnabled(providerId, enabled) {
        return apiRequest(`/llm/providers/${providerId}/enable`, {
            method: 'POST',
            body: {enabled},
        });
    },

    async cancelProviderChanges(providerId) {
        return apiRequest(`/llm/providers/${providerId}/cancel`, {
            method: 'POST',
        });
    },

    async getProviderConfig(providerId) {
        return apiRequest(`/llm/providers/${providerId}/config`, {
            method: 'GET',
        });
    },
};

// Audiobookshelf API
export const audiobookshelf = {
    async getLibraries() {
        return apiRequest('/audiobookshelf/libraries');
    },

    async searchLibrary(libraryId, query) {
        return apiRequest(`/audiobookshelf/libraries/${libraryId}/search?q=${encodeURIComponent(query)}`);
    },

    async getLibraryItems(libraryId, refresh = false) {
        const params = new URLSearchParams();
        if (refresh) {
            params.append('refresh', 'true');
        }
        
        const queryString = params.toString();
        const url = `/audiobookshelf/libraries/${libraryId}/items${queryString ? `?${queryString}` : ''}`;
        
        return apiRequest(url);
    },

    async clearAllCache() {
        return apiRequest('/audiobookshelf/cache/clear', {
            method: 'POST',
        });
    },
};

// Export the main API object
export const api = {
    session,
    chapters,
    batch,
    audio,
    health,
    config,
    llm,
    audiobookshelf,
};

export default api;