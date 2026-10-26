import { get } from 'svelte/store';
import { describe, expect, it, vi } from 'vitest';
import { createSnippetTranscriber, snippetStatus, SNIPPET_DEDUPE_WINDOW } from './snippetTranscripts';

vi.mock('../utils/api', () => ({
  api: { chapters: { transcribeSnippet: vi.fn() } },
  handleApiError: (err: unknown) => (err instanceof Error ? err.message : String(err)),
}));

// A transcribe fn whose calls resolve only when the test says so, to observe queue order
function deferredTranscribe() {
  const calls: { timestamp: number; resolve: (t: string) => void; reject: (e: Error) => void }[] = [];
  const fn = vi.fn(
    (timestamp: number) =>
      new Promise<string>((resolve, reject) => {
        calls.push({ timestamp, resolve, reject });
      }),
  );
  return { fn, calls };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

describe('createSnippetTranscriber', () => {
  it('transcribes the auto-queue one at a time, top to bottom', async () => {
    const { fn, calls } = deferredTranscribe();
    const t = createSnippetTranscriber(fn);
    t.setCacheKey('key');
    t.setAutoQueue([30, 10, 20]);

    expect(calls.map((c) => c.timestamp)).toEqual([30]);
    expect(snippetStatus(get(t), 30)).toEqual({ state: 'active' });
    expect(snippetStatus(get(t), 10)).toEqual({ state: 'queued' });

    calls[0].resolve('Chapter One');
    await flush();
    expect(calls.map((c) => c.timestamp)).toEqual([30, 10]);
    expect(snippetStatus(get(t), 30)).toEqual({ state: 'done', transcript: 'Chapter One' });
  });

  it('dedupes timestamps within the window, in the queue and the cache', async () => {
    const { fn, calls } = deferredTranscribe();
    const t = createSnippetTranscriber(fn);
    t.setCacheKey('key');
    t.setAutoQueue([100, 100 + SNIPPET_DEDUPE_WINDOW - 0.1, 200]);
    expect(get(t).queue).toEqual([200]);

    calls[0].resolve('');
    await flush();
    // A nearby timestamp in another tab reuses the cached (no-speech) result
    expect(snippetStatus(get(t), 100.3)).toEqual({ state: 'done', transcript: '' });
    t.setAutoQueue([100.3, 200]);
    expect(calls.map((c) => c.timestamp)).toEqual([100, 200]);
  });

  it('moves a manual request to the front, even with auto disabled', async () => {
    const { fn, calls } = deferredTranscribe();
    const t = createSnippetTranscriber(fn);
    t.setCacheKey('key');
    t.setAutoQueue([1, 2, 3]);
    t.enqueue(3);
    expect(get(t).queue).toEqual([3, 2]);

    // Disabling auto drops auto items but keeps manual ones
    t.setAutoQueue([]);
    expect(get(t).queue).toEqual([3]);

    calls[0].resolve('a');
    await flush();
    expect(calls.map((c) => c.timestamp)).toEqual([1, 3]);
  });

  it('lets an in-flight transcription finish and cache after the queue is cleared', async () => {
    const { fn, calls } = deferredTranscribe();
    const t = createSnippetTranscriber(fn);
    t.setCacheKey('key');
    t.setAutoQueue([5, 6]);
    t.clearQueue();

    calls[0].resolve('kept');
    await flush();
    expect(calls).toHaveLength(1);
    expect(snippetStatus(get(t), 5)).toEqual({ state: 'done', transcript: 'kept' });
    expect(snippetStatus(get(t), 6)).toEqual({ state: 'idle' });
  });

  it('stops auto-queueing after a failure and retries on manual request', async () => {
    const { fn, calls } = deferredTranscribe();
    const t = createSnippetTranscriber(fn);
    t.setCacheKey('key');
    t.setAutoQueue([1, 2]);

    calls[0].reject(new Error('No ASR service'));
    await flush();
    expect(calls).toHaveLength(1);
    expect(snippetStatus(get(t), 1)).toEqual({ state: 'error', error: 'No ASR service' });

    // Re-enabling auto skips the failed item; a manual click retries it
    t.setAutoQueue([1, 2]);
    expect(calls.map((c) => c.timestamp)).toEqual([1, 2]);
    calls[1].resolve('two');
    await flush();
    t.enqueue(1);
    expect(calls.map((c) => c.timestamp)).toEqual([1, 2, 1]);
  });

  it('clears the cache on cache-key change and drops stale in-flight results', async () => {
    const { fn, calls } = deferredTranscribe();
    const t = createSnippetTranscriber(fn);
    t.setCacheKey('key-a');
    t.setAutoQueue([7]);
    t.setCacheKey('key-b');

    calls[0].resolve('under key A');
    await flush();
    expect(snippetStatus(get(t), 7)).toEqual({ state: 'idle' });
  });
});
