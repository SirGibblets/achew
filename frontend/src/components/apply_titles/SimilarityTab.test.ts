import { render, screen, waitFor } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import type { Writable } from 'svelte/store';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ChapterData } from '../../types/chapter';
import type { ChapterReference } from '../../types/references';
import SimilarityTab from './SimilarityTab.svelte';

vi.mock('../../stores/session', async () => {
  const { writable } = await import('svelte/store');
  return { chapters: writable([]) };
});
vi.mock('../../stores/audio', async () => {
  const { writable } = await import('svelte/store');
  return { audio: { play: vi.fn(), stop: vi.fn() }, currentSegmentId: writable(null), isPlaying: writable(false) };
});
vi.mock('../../utils/api', () => ({
  api: { chapters: { matchTitlesBySimilarity: vi.fn() } },
  handleApiError: (err: unknown) => String(err),
}));

import { chapters } from '../../stores/session';
import { api } from '../../utils/api';

const chapterStore = chapters as unknown as Writable<ChapterData[]>;

function chapter(id: string, timestamp: number, title: string, transcript = ''): ChapterData {
  return { id, timestamp, title, transcript, deleted: false, selected: true };
}

const REF: ChapterReference = {
  id: 'ref-1',
  name: 'Audible',
  short_name: 'Audible',
  description: '',
  type: 'audnexus',
  duration: 3600,
  chapters: [
    { timestamp: 0, title: 'Chapter 1: Owl Post' },
    { timestamp: 600, title: 'Harpies' },
  ],
} as unknown as ChapterReference;

function match(chapter_id: string, ref_index: number, title: string, confident: boolean) {
  return { chapter_id, ref_index, title, score: confident ? 0.9 : 0.6, confident, source: 'transcript' as const };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('SimilarityTab', () => {
  it('checks confident matches and leaves weaker ones unchecked', async () => {
    chapterStore.set([
      chapter('a', 0, 'Chapter one. Owl post.'),
      chapter('b', 600, 'Harpies flew over the city'),
      chapter('c', 900, 'It was late'),
    ]);
    vi.mocked(api.chapters.matchTitlesBySimilarity).mockResolvedValue({
      matches: [match('a', 0, 'Chapter 1: Owl Post', true), match('b', 1, 'Harpies', false)],
    });

    render(SimilarityTab, { ref: REF });

    await waitFor(() => expect(screen.getByText(/2 of 3 chapters match/)).toBeInTheDocument());
    expect(api.chapters.matchTitlesBySimilarity).toHaveBeenCalledWith('ref-1');
    expect(screen.getByText(/1 weaker match starts unchecked/)).toBeInTheDocument();
    const boxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
    expect(boxes.map((b) => b.checked)).toEqual([true, false]);
    // The weaker match still shows what it would apply
    expect(screen.getByText('Match: Harpies')).toBeInTheDocument();
  });

  it('keeps the user’s choices when the chapters change and the match is re-run', async () => {
    const user = userEvent.setup();
    chapterStore.set([chapter('a', 0, 'Chapter one. Owl post.'), chapter('b', 600, 'Harpies')]);
    vi.mocked(api.chapters.matchTitlesBySimilarity).mockResolvedValue({
      matches: [match('a', 0, 'Chapter 1: Owl Post', true), match('b', 1, 'Harpies', true)],
    });

    render(SimilarityTab, { ref: REF });
    await waitFor(() => expect(screen.getAllByRole('checkbox')).toHaveLength(2));

    await user.click(screen.getByText('Chapter 1: Owl Post'));
    expect((screen.getAllByRole('checkbox') as HTMLInputElement[]).map((b) => b.checked)).toEqual([false, true]);

    // A transcription finishing elsewhere changes a chapter while the dialog is open
    chapterStore.set([chapter('a', 0, 'Chapter one. Owl post.'), chapter('b', 600, 'Harpies', 'Harpies.')]);
    await waitFor(() => expect(api.chapters.matchTitlesBySimilarity).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect((screen.getAllByRole('checkbox') as HTMLInputElement[]).map((b) => b.checked)).toEqual([false, true]),
    );
  });

  it('says so when nothing matches', async () => {
    chapterStore.set([chapter('a', 0, 'It was late')]);
    vi.mocked(api.chapters.matchTitlesBySimilarity).mockResolvedValue({ matches: [] });

    render(SimilarityTab, { ref: REF });

    await waitFor(() => expect(screen.getByText(/No chapters match a title/)).toBeInTheDocument());
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
  });

  it('shows a failed match as an error', async () => {
    chapterStore.set([chapter('a', 0, 'Chapter one')]);
    vi.mocked(api.chapters.matchTitlesBySimilarity).mockRejectedValue('Reference not found');

    render(SimilarityTab, { ref: REF });

    await waitFor(() => expect(screen.getByText('Reference not found')).toBeInTheDocument());
  });
});
