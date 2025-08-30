import {writable, derived} from 'svelte/store';
import {api} from '../utils/api.js';

// Create audio playback store
function createAudioStore() {
    const {subscribe, set, update} = writable({
        // Current playback state
        currentSegmentId: null,
        isPlaying: false,
        currentTime: 0,
        duration: 0,
        volume: 1.0,

        // Audio element reference
        audioElement: null,

        // Loading state
        loading: false,
        error: null,

        // Segment info
        segments: [],
        segmentUrls: new Map()
    });

    let audioElement = null;
    let currentPlayPromise = null;

    // Create audio element
    const createAudioElement = () => {
        if (audioElement) return audioElement;

        audioElement = new Audio();
        audioElement.preload = 'metadata';

        // Event listeners
        audioElement.addEventListener('loadstart', () => {
            update(state => ({...state, loading: true, error: null}));
        });

        audioElement.addEventListener('loadedmetadata', () => {
            update(state => ({
                ...state,
                duration: audioElement.duration,
                loading: false
            }));
        });

        audioElement.addEventListener('timeupdate', () => {
            update(state => ({
                ...state,
                currentTime: audioElement.currentTime
            }));
        });

        audioElement.addEventListener('play', () => {
            update(state => ({...state, isPlaying: true}));
        });

        audioElement.addEventListener('pause', () => {
            update(state => ({...state, isPlaying: false}));
        });

        audioElement.addEventListener('ended', () => {
            update(state => ({
                ...state,
                isPlaying: false,
                currentTime: 0,
                currentSegmentId: null
            }));
        });

        audioElement.addEventListener('error', (e) => {
            const error = `Audio error: ${e.target.error?.message || 'Unknown error'}`;
            update(state => ({
                ...state,
                loading: false,
                error,
                isPlaying: false
            }));
        });

        return audioElement;
    };

    return {
        subscribe,

        // Playback controls
        async play(segmentId, chapterTimestamp = null) {
            const audio = createAudioElement();

            update(state => ({
                ...state,
                loading: true,
                error: null
            }));

            try {
                // Cancel any current play promise
                if (currentPlayPromise) {
                    currentPlayPromise = null;
                }

                // Stop current audio if playing
                if (audioElement && !audioElement.paused) {
                    audioElement.pause();
                    audioElement.currentTime = 0;
                }

                // Force clear audio source and reload to avoid cache issues
                audio.src = '';
                audio.load();

                // Get streaming URL
                const streamUrl = api.audio.getStreamUrl();

                // Set new source
                audio.src = streamUrl;

                // Update state with new segment
                update(state => ({
                    ...state,
                    currentSegmentId: segmentId,
                    audioElement: audio,
                    isPlaying: false,
                    currentTime: 0
                }));

                if (chapterTimestamp !== null) {
                    await new Promise((resolve, reject) => {
                        const onLoadedMetadata = () => {
                            audio.removeEventListener('loadedmetadata', onLoadedMetadata);
                            audio.removeEventListener('error', onError);
                            resolve();
                        };
                        const onError = (e) => {
                            audio.removeEventListener('loadedmetadata', onLoadedMetadata);
                            audio.removeEventListener('error', onError);
                            reject(e);
                        };
                        audio.addEventListener('loadedmetadata', onLoadedMetadata);
                        audio.addEventListener('error', onError);
                    });

                    audio.currentTime = chapterTimestamp;
                }

                // Start playback
                currentPlayPromise = audio.play();
                await currentPlayPromise;
                currentPlayPromise = null;

                // Update loading state
                update(state => ({
                    ...state,
                    loading: false
                }));

            } catch (error) {
                currentPlayPromise = null;
                const errorMessage = `Failed to play audio: ${error.message}`;
                update(state => ({
                    ...state,
                    loading: false,
                    error: errorMessage,
                    isPlaying: false,
                    currentSegmentId: null
                }));
                throw error;
            }
        },

        // Changed from pause to stop - resets playback progress
        stop() {
            // Wait for any current play promise to complete before stopping
            if (currentPlayPromise) {
                currentPlayPromise.then(() => {
                    if (audioElement) {
                        audioElement.pause();
                        audioElement.currentTime = 0;
                    }
                }).catch(() => {
                    // Ignore errors from interrupted promises
                    if (audioElement) {
                        audioElement.pause();
                        audioElement.currentTime = 0;
                    }
                });
                currentPlayPromise = null;
            } else if (audioElement) {
                audioElement.pause();
                audioElement.currentTime = 0;
            }

            update(state => ({
                ...state,
                isPlaying: false,
                currentTime: 0,
                currentSegmentId: null
            }));
        },


        // Volume control
        setVolume(volume) {
            if (audioElement) {
                audioElement.volume = Math.max(0, Math.min(1, volume));
            }

            update(state => ({
                ...state,
                volume: Math.max(0, Math.min(1, volume))
            }));
        },

        // Seek controls
        seek(time) {
            if (audioElement) {
                audioElement.currentTime = Math.max(0, Math.min(audioElement.duration || 0, time));
            }
        },

        seekPercent(percent) {
            if (audioElement && audioElement.duration) {
                const time = (percent / 100) * audioElement.duration;
                this.seek(time);
            }
        },

        // State management
        clearError() {
            update(state => ({...state, error: null}));
        },

        // Clear segment cache when chapters change
        clearSegmentCache() {
            // Stop any current playback
            if (audioElement) {
                audioElement.pause();
                audioElement.currentTime = 0;
            }

            // Clear cached segment data
            update(state => ({
                ...state,
                isPlaying: false,
                currentTime: 0,
                currentSegmentId: null,
                segments: [],
                segmentUrls: new Map(),
                error: null
            }));

            // Force clear audio element cache
            if (audioElement) {
                audioElement.src = '';
                audioElement.load();
            }
        },

        // Cleanup
        destroy() {
            if (audioElement) {
                audioElement.pause();
                audioElement.src = '';
                audioElement = null;
            }

            set({
                currentSegmentId: null,
                isPlaying: false,
                currentTime: 0,
                duration: 0,
                volume: 1.0,
                audioElement: null,
                loading: false,
                error: null,
                segments: [],
                segmentUrls: new Map()
            });
        }
    };
}

export const audio = createAudioStore();

// Derived stores
export const isPlaying = derived(audio, $audio => $audio.isPlaying);
export const currentSegmentId = derived(audio, $audio => $audio.currentSegmentId);
export const playbackProgress = derived(audio, $audio => {
    if ($audio.duration > 0) {
        return ($audio.currentTime / $audio.duration) * 100;
    }
    return 0;
});