import { writable, derived, get } from 'svelte/store';
import { api } from '../utils/api';
import { session } from './session';

interface AudioState {
  currentSegmentId: string | null;
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  volume: number;
  audioElement: HTMLAudioElement | null;
  loading: boolean;
  error: string | null;
  segments: unknown[];
  segmentUrls: Map<string, string>;
}

function createAudioStore() {
  const { subscribe, set, update } = writable<AudioState>({
    currentSegmentId: null,
    isPlaying: false,
    currentTime: 0,
    duration: 0,
    volume: 1.0,
    audioElement: null,
    loading: false,
    error: null,
    segments: [],
    segmentUrls: new Map(),
  });

  let audioElement: HTMLAudioElement | null = null;
  let currentPlayPromise: Promise<void> | null = null;

  // Pause and rewind. A transcoded preview is a live server-side encode, so drop its
  // source instead: that closes the request, and the server stops encoding.
  const halt = (): void => {
    if (!audioElement) return;
    audioElement.pause();
    if (audioElement.src.includes('/api/audio/preview')) {
      audioElement.removeAttribute('src');
      audioElement.load();
    } else {
      audioElement.currentTime = 0;
    }
  };

  const createAudioElement = (): HTMLAudioElement => {
    if (audioElement) return audioElement;

    audioElement = new Audio();
    audioElement.preload = 'metadata';

    audioElement.addEventListener('loadstart', () => {
      update((state) => ({ ...state, loading: true, error: null }));
    });

    audioElement.addEventListener('loadedmetadata', () => {
      update((state) => ({
        ...state,
        duration: audioElement?.duration ?? 0,
        loading: false,
      }));
    });

    audioElement.addEventListener('timeupdate', () => {
      update((state) => ({
        ...state,
        currentTime: audioElement?.currentTime ?? 0,
      }));
    });

    audioElement.addEventListener('play', () => {
      update((state) => ({ ...state, isPlaying: true }));
    });

    audioElement.addEventListener('pause', () => {
      update((state) => ({ ...state, isPlaying: false }));
    });

    audioElement.addEventListener('ended', () => {
      update((state) => ({
        ...state,
        isPlaying: false,
        currentTime: 0,
        currentSegmentId: null,
      }));
    });

    audioElement.addEventListener('error', (e) => {
      const target = e.target as HTMLAudioElement | null;
      const error = `Audio error: ${target?.error?.message ?? 'Unknown error'}`;
      update((state) => ({
        ...state,
        loading: false,
        error,
        isPlaying: false,
      }));
    });

    return audioElement;
  };

  return {
    subscribe,

    async play(segmentId: string, chapterTimestamp: number | null = null): Promise<void> {
      const audio = createAudioElement();

      update((state) => ({ ...state, loading: true, error: null }));

      try {
        if (currentPlayPromise) {
          currentPlayPromise = null;
        }

        if (audioElement && !audioElement.paused) {
          audioElement.pause();
          audioElement.currentTime = 0;
        }

        audio.src = '';
        audio.load();

        // Few browsers decode xHE-AAC, so those books stream a server-side transcode
        // that already starts at the chapter instead of seeking into the original file
        const transcoded = get(session).audioXheAac;
        const streamUrl = transcoded ? api.audio.getPreviewUrl(chapterTimestamp ?? 0) : api.audio.getStreamUrl();
        audio.src = streamUrl;

        update((state) => ({
          ...state,
          currentSegmentId: segmentId,
          audioElement: audio,
          isPlaying: false,
          currentTime: 0,
        }));

        if (chapterTimestamp !== null && !transcoded) {
          await new Promise<void>((resolve, reject) => {
            const onLoadedMetadata = () => {
              audio.removeEventListener('loadedmetadata', onLoadedMetadata);
              audio.removeEventListener('error', onError);
              resolve();
            };
            const onError = (e: Event) => {
              audio.removeEventListener('loadedmetadata', onLoadedMetadata);
              audio.removeEventListener('error', onError);
              reject(e instanceof Error ? e : new Error('Audio load error'));
            };
            audio.addEventListener('loadedmetadata', onLoadedMetadata);
            audio.addEventListener('error', onError);
          });

          audio.currentTime = chapterTimestamp;
        }

        currentPlayPromise = audio.play();
        await currentPlayPromise;
        currentPlayPromise = null;

        update((state) => ({ ...state, loading: false }));
      } catch (error) {
        currentPlayPromise = null;
        const message = error instanceof Error ? error.message : String(error);
        const errorMessage = `Failed to play audio: ${message}`;
        update((state) => ({
          ...state,
          loading: false,
          error: errorMessage,
          isPlaying: false,
          currentSegmentId: null,
        }));
        throw error;
      }
    },

    stop(): void {
      if (currentPlayPromise) {
        currentPlayPromise.then(halt).catch(halt);
        currentPlayPromise = null;
      } else {
        halt();
      }

      update((state) => ({
        ...state,
        isPlaying: false,
        currentTime: 0,
        currentSegmentId: null,
      }));
    },

    setVolume(volume: number): void {
      const clamped = Math.max(0, Math.min(1, volume));
      if (audioElement) {
        audioElement.volume = clamped;
      }

      update((state) => ({ ...state, volume: clamped }));
    },

    seek(time: number): void {
      if (audioElement) {
        audioElement.currentTime = Math.max(0, Math.min(audioElement.duration || 0, time));
      }
    },

    seekPercent(percent: number): void {
      if (audioElement && audioElement.duration) {
        const time = (percent / 100) * audioElement.duration;
        this.seek(time);
      }
    },

    clearError(): void {
      update((state) => ({ ...state, error: null }));
    },

    clearSegmentCache(): void {
      if (audioElement) {
        audioElement.pause();
        audioElement.currentTime = 0;
      }

      update((state) => ({
        ...state,
        isPlaying: false,
        currentTime: 0,
        currentSegmentId: null,
        segments: [],
        segmentUrls: new Map(),
        error: null,
      }));

      if (audioElement) {
        audioElement.src = '';
        audioElement.load();
      }
    },

    destroy(): void {
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
        segmentUrls: new Map(),
      });
    },
  };
}

export const audio = createAudioStore();

export const isPlaying = derived(audio, ($audio) => $audio.isPlaying);
export const currentSegmentId = derived(audio, ($audio) => $audio.currentSegmentId);
export const playbackProgress = derived(audio, ($audio) => {
  if ($audio.duration > 0) {
    return ($audio.currentTime / $audio.duration) * 100;
  }
  return 0;
});
