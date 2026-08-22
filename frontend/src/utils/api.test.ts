import { afterEach, describe, expect, it, vi } from 'vitest';

import { APIError, handleApiError, references } from './api';

const CHUNK_BYTES = 512 * 1024;

/** A file whose bytes follow a known pattern, so reassembly can be verified. */
function makeFile(size: number, name = 'book.epub') {
  const bytes = new Uint8Array(size);
  for (let i = 0; i < size; i++) {
    bytes[i] = i % 251;
  }
  return { file: new File([bytes], name), bytes };
}

function mockFetch(res: Response) {
  const fn = vi.fn().mockResolvedValue(res);
  vi.stubGlobal('fetch', fn);
  return fn;
}

interface SeenChunk {
  index: number;
  total: number;
  uploadId: string;
  blob: File;
}

/** Mock fetch as a chunk-assembling server, recording what each request carried. */
function mockChunkedServer(finalBody: unknown) {
  const seen: SeenChunk[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: string, init: RequestInit) => {
      const form = init.body as FormData;
      const index = Number(form.get('index'));
      const total = Number(form.get('total'));
      seen.push({ index, total, uploadId: String(form.get('upload_id')), blob: form.get('file') as File });

      const body = index + 1 < total ? { received: index + 1, total } : finalBody;
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    }),
  );
  return seen;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('chunked reference upload', () => {
  it('splits a large file into ordered chunks that reassemble exactly', async () => {
    const { file, bytes } = makeFile(CHUNK_BYTES * 2 + 100);
    const seen = mockChunkedServer({ id: 'ref-1', titles: ['Chapter One'] });

    await references.upload(file);

    expect(seen.map((c) => c.index)).toEqual([0, 1, 2]);
    expect(seen.every((c) => c.total === 3)).toBe(true);
    // One id for the whole upload, so the backend appends to a single part file.
    expect(new Set(seen.map((c) => c.uploadId)).size).toBe(1);

    const reassembled = new Uint8Array(await new Blob(seen.map((c) => c.blob)).arrayBuffer());
    expect(reassembled).toEqual(bytes);
  }, 15000);

  it('keeps the filename on every chunk, since the backend parses by extension', async () => {
    const { file } = makeFile(CHUNK_BYTES + 1, 'novel.epub');
    const seen = mockChunkedServer({ id: 'ref-1' });

    await references.upload(file);

    expect(seen.map((c) => c.blob.name)).toEqual(['novel.epub', 'novel.epub']);
  });

  it('returns the reference from the final chunk', async () => {
    const { file } = makeFile(CHUNK_BYTES * 2);
    mockChunkedServer({ id: 'ref-1', titles: ['Chapter One'] });

    await expect(references.upload(file)).resolves.toEqual({ id: 'ref-1', titles: ['Chapter One'] });
  });

  it('reports progress across chunks', async () => {
    const { file } = makeFile(CHUNK_BYTES * 4);
    mockChunkedServer({ id: 'ref-1' });
    const progress: number[] = [];

    await references.upload(file, (fraction) => progress.push(fraction));

    expect(progress).toEqual([0.25, 0.5, 0.75, 1]);
  });

  it('sends a small file as a single chunk and reports no progress', async () => {
    const { file } = makeFile(1024);
    const seen = mockChunkedServer({ id: 'ref-1' });
    const progress: number[] = [];

    await references.upload(file, (fraction) => progress.push(fraction));

    expect(seen).toHaveLength(1);
    expect(seen[0].total).toBe(1);
    expect(progress).toEqual([]);
  });

  it('stops uploading once a chunk fails', async () => {
    const { file } = makeFile(CHUNK_BYTES * 3);
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Upload chunks arrived out of order' }), {
        status: 409,
        headers: { 'content-type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(references.upload(file)).rejects.toMatchObject({ status: 409 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe('apiRequest error handling', () => {
  it('surfaces the FastAPI detail message', async () => {
    const { file } = makeFile(64);
    mockFetch(
      new Response(JSON.stringify({ detail: 'Could not extract any chapter titles from EPUB' }), {
        status: 400,
        headers: { 'content-type': 'application/json' },
      }),
    );

    await expect(references.upload(file)).rejects.toMatchObject({
      status: 400,
      message: 'Could not extract any chapter titles from EPUB',
    });
  });

  it('reports the status of a non-JSON error body instead of failing to re-read it', async () => {
    // A reverse proxy rejecting a large upload returns an HTML page, not JSON.
    const { file } = makeFile(64);
    mockFetch(new Response('<html><body><h1>413 Request Entity Too Large</h1></body></html>', { status: 413 }));

    const err = await references.upload(file).catch((e: unknown) => e);

    expect(err).toBeInstanceOf(APIError);
    expect((err as APIError).status).toBe(413);
    // Regression: reading the body twice used to raise "body stream already read",
    // which was reported to the user as a network error and hid the real status.
    expect((err as APIError).message).not.toContain('already read');
  });

  it('falls back to the status line for an empty error body', async () => {
    const { file } = makeFile(64);
    mockFetch(new Response(null, { status: 502, statusText: 'Bad Gateway' }));

    await expect(references.upload(file)).rejects.toMatchObject({
      status: 502,
      message: 'HTTP 502 Bad Gateway',
    });
  });

  it('explains a 413 in terms of the proxy that produced it', () => {
    expect(handleApiError(new APIError('HTTP 413', 413))).toContain('reverse proxy');
  });
});
