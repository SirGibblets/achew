import { writable } from 'svelte/store';
import { api, handleApiError } from '../utils/api';

// Two timestamps closer than this share one transcript, so a reference chapter sitting next to a
// detected cue (or the same cue listed in several tabs) is only transcribed once.
export const SNIPPET_DEDUPE_WINDOW = 0.5;

export interface SnippetResult {
  timestamp: number;
  // "" when the snippet held no speech; undefined when transcription failed
  transcript?: string;
  error?: string;
}

export interface SnippetSnapshot {
  results: SnippetResult[];
  queue: number[];
  active: number | null;
}

export type SnippetStatus =
  | { state: 'idle' }
  | { state: 'queued' }
  | { state: 'active' }
  | { state: 'done'; transcript: string }
  | { state: 'error'; error: string };

function near(a: number, b: number) {
  return Math.abs(a - b) <= SNIPPET_DEDUPE_WINDOW;
}

export function snippetStatus(snapshot: SnippetSnapshot, timestamp: number): SnippetStatus {
  const result = snapshot.results.find((r) => near(r.timestamp, timestamp));
  if (snapshot.active !== null && near(snapshot.active, timestamp)) return { state: 'active' };
  if (snapshot.queue.some((t) => near(t, timestamp))) return { state: 'queued' };
  if (result) {
    return result.transcript !== undefined
      ? { state: 'done', transcript: result.transcript }
      : { state: 'error', error: result.error ?? 'Transcription failed' };
  }
  return { state: 'idle' };
}

/**
 * Session-scoped, one-at-a-time snippet transcription queue for the Add Chapter dialog.
 *
 * Lives at module level so an in-flight transcription survives the dialog closing and its result
 * is still cached when the dialog reopens. The queue holds manual requests (front, most recent
 * first) followed by the auto-queue, which the dialog replaces wholesale as its visible list changes.
 */
export function createSnippetTranscriber(transcribe: (timestamp: number) => Promise<string>) {
  let results: SnippetResult[] = [];
  let manual: number[] = [];
  let auto: number[] = [];
  let active: number | null = null;
  let cacheKey: string | null = null;
  // Bumped on cache-key change so a result computed under the old key is dropped when it lands
  let generation = 0;

  const store = writable<SnippetSnapshot>({ results: [], queue: [], active: null });

  function publish() {
    store.set({ results: [...results], queue: [...manual, ...auto], active });
  }

  function isKnown(timestamp: number) {
    return (active !== null && near(active, timestamp)) || results.some((r) => near(r.timestamp, timestamp));
  }

  async function pump() {
    if (active !== null) return;
    const next = manual.shift() ?? auto.shift();
    if (next === undefined) {
      publish();
      return;
    }

    active = next;
    const startedGeneration = generation;
    publish();

    let result: SnippetResult;
    try {
      result = { timestamp: next, transcript: await transcribe(next) };
    } catch (err) {
      result = { timestamp: next, error: handleApiError(err) };
    }

    if (startedGeneration === generation) {
      results.push(result);
      // Stop auto-queueing after a failure: the cause (no ASR configured, wrong step, …) usually
      // affects every item. Manual requests still run, and re-enabling Auto resumes the rest.
      if (result.error !== undefined) auto = [];
    }
    active = null;
    void pump();
  }

  return {
    subscribe: store.subscribe,

    /**
     * Clear the cache when the backend's transcript cache key changes (new pipeline, or different
     * ASR model/language/options), since every cached transcript may now be wrong.
     */
    setCacheKey(key: string | null) {
      if (key === cacheKey) return;
      cacheKey = key;
      generation++;
      results = [];
      manual = [];
      auto = [];
      publish();
    },

    /** Replace the auto-queue with the visible items (top to bottom), skipping anything already handled. */
    setAutoQueue(timestamps: number[]) {
      auto = [];
      for (const t of timestamps) {
        if (isKnown(t) || manual.some((m) => near(m, t)) || auto.some((a) => near(a, t))) continue;
        auto.push(t);
      }
      publish();
      void pump();
    },

    /** Transcribe an item next, ahead of everything else queued; retries a failed item. */
    enqueue(timestamp: number) {
      if (active !== null && near(active, timestamp)) return;
      const existing = results.find((r) => near(r.timestamp, timestamp));
      if (existing && existing.error === undefined) return;
      results = results.filter((r) => r !== existing);
      manual = [timestamp, ...manual.filter((m) => !near(m, timestamp))];
      auto = auto.filter((a) => !near(a, timestamp));
      publish();
      void pump();
    },

    /** Drop everything queued; an in-flight transcription still finishes and is cached. */
    clearQueue() {
      manual = [];
      auto = [];
      publish();
    },
  };
}

export const snippetTranscripts = createSnippetTranscriber(
  async (timestamp) => (await api.chapters.transcribeSnippet(timestamp)).transcript,
);
