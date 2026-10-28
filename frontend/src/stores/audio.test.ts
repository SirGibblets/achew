import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { audio } from './audio';
import { session } from './session';
import { api } from '../utils/api';

vi.mock('../utils/api', () => ({
  api: {
    audio: {
      getStreamUrl: vi.fn(() => '/api/audio/stream?t=1'),
      getPreviewUrl: vi.fn((start: number) => `/api/audio/preview?start=${start}&t=1`),
    },
  },
}));

vi.mock('./session', async () => {
  const { writable } = await import('svelte/store');
  return { session: writable({ audioXheAac: false }) };
});

const setXheAac = (audioXheAac: boolean) =>
  (session as unknown as { set: (v: { audioXheAac: boolean }) => void }).set({ audioXheAac });

// jsdom has no media playback; record what the store asks of the element instead
let element: HTMLAudioElement;
beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockImplementation(function (this: HTMLMediaElement) {
    element = this as HTMLAudioElement;
    return Promise.resolve();
  });
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {});
});

afterEach(() => {
  audio.stop();
  vi.restoreAllMocks();
});

describe('audio store with xHE-AAC books', () => {
  it('streams a transcode that starts at the chapter instead of seeking', async () => {
    setXheAac(true);
    await audio.play('chapter-3', 125.5);

    expect(api.audio.getPreviewUrl).toHaveBeenCalledWith(125.5);
    expect(element.getAttribute('src')).toBe('/api/audio/preview?start=125.5&t=1');
    // The transcode already begins at the chapter, so the player starts at 0
    expect(element.currentTime).toBe(0);
  });

  it('drops the transcode on stop so the server stops encoding', async () => {
    setXheAac(true);
    await audio.play('chapter-3', 10);
    const load = vi.mocked(HTMLMediaElement.prototype.load);
    load.mockClear();

    audio.stop();
    await Promise.resolve();

    expect(element.hasAttribute('src')).toBe(false);
    expect(load).toHaveBeenCalled();
  });

  it('keeps the original stream for other books', async () => {
    setXheAac(false);
    await audio.play('chapter-1', null);
    audio.stop();
    await Promise.resolve();

    expect(api.audio.getStreamUrl).toHaveBeenCalled();
    expect(element.getAttribute('src')).toBe('/api/audio/stream?t=1');
  });
});
