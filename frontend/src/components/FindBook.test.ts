import { render, screen, waitFor } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import FindBook from './FindBook.svelte';

vi.mock('../utils/api', () => ({
  api: {
    session: {
      validateItem: vi.fn(),
    },
    audiobookshelf: {
      getLibraries: vi.fn(),
      searchLibrary: vi.fn(),
      getRecentlyAdded: vi.fn(),
    },
  },
}));

import { api } from '../utils/api';

const INPUT_MODE_KEY = 'achew-last-input-mode';
const SEARCH_QUERY_KEY = 'achew-last-search-query';

function mockLibraries() {
  vi.mocked(api.audiobookshelf.getLibraries).mockResolvedValue([{ id: 'lib1', name: 'Library 1' }] as never);
}

beforeEach(() => {
  localStorage.clear();
  mockLibraries();
  vi.mocked(api.session.validateItem).mockResolvedValue({ valid: false } as never);
  vi.mocked(api.audiobookshelf.searchLibrary).mockResolvedValue({ hits: [], total: 0 } as never);
  vi.mocked(api.audiobookshelf.getRecentlyAdded).mockResolvedValue([]);
});

function recentBook(id: string, title: string) {
  return {
    id,
    addedAt: Date.now() - 2 * 86_400_000,
    updatedAt: 0,
    duration: 3600,
    media: { metadata: { title, authors: [{ id: 'a', name: 'Some Author' }] }, coverPath: '' },
  } as never;
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('FindBook', () => {
  it('defaults to the Book Search tab with an empty query when nothing was saved', async () => {
    render(FindBook);

    await waitFor(() => expect(screen.getByRole('button', { name: 'Book Search' })).toHaveClass('active'));
    expect(screen.getByPlaceholderText(/Search by title/)).toHaveValue('');
  });

  it('restores a saved search query into the input on mount', async () => {
    localStorage.setItem(INPUT_MODE_KEY, 'search');
    localStorage.setItem(SEARCH_QUERY_KEY, 'dune');

    render(FindBook);

    await waitFor(() => expect(screen.getByPlaceholderText(/Search by title/)).toHaveValue('dune'));
  });

  it('restores the Chapter Search tab as active when it was last selected', async () => {
    localStorage.setItem(INPUT_MODE_KEY, 'chapterSearch');

    render(FindBook);

    await waitFor(() => expect(screen.getByRole('button', { name: 'Chapter Search' })).toHaveClass('active'));
    expect(screen.getByRole('button', { name: 'Book Search' })).not.toHaveClass('active');
  });

  it('persists the query as the user types and clears it via the X button', async () => {
    const user = userEvent.setup();
    render(FindBook);

    const input = screen.getByPlaceholderText(/Search by title/);
    await waitFor(() => expect(input).toBeEnabled());
    await user.type(input, 'dune');

    await waitFor(() => expect(localStorage.getItem(SEARCH_QUERY_KEY)).toBe('dune'));
    const clearBtn = await screen.findByLabelText('Clear search');

    await user.click(clearBtn);

    expect(input).toHaveValue('');
    expect(screen.queryByLabelText('Clear search')).not.toBeInTheDocument();
    await waitFor(() => expect(localStorage.getItem(SEARCH_QUERY_KEY)).toBe(''));
  });

  it('persists the active tab when switching between Book Search and Chapter Search', async () => {
    const user = userEvent.setup();
    render(FindBook);

    await user.click(screen.getByRole('button', { name: 'Chapter Search' }));
    expect(localStorage.getItem(INPUT_MODE_KEY)).toBe('chapterSearch');

    await user.click(screen.getByRole('button', { name: 'Book Search' }));
    expect(localStorage.getItem(INPUT_MODE_KEY)).toBe('search');
  });

  it('shows recently added books for the selected library while the query is blank', async () => {
    vi.mocked(api.audiobookshelf.getRecentlyAdded).mockResolvedValue([
      recentBook('b1', 'Fresh Book'),
      recentBook('b2', 'Another Arrival'),
    ]);
    const user = userEvent.setup();
    render(FindBook);

    const section = await screen.findByRole('group', { name: 'Recently added' });
    expect(api.audiobookshelf.getRecentlyAdded).toHaveBeenCalledWith('lib1');
    expect(screen.getByRole('button', { name: 'Start Fresh Book' })).toBeInTheDocument();
    expect(section).toHaveTextContent('2d ago');

    await user.type(screen.getByPlaceholderText(/Search by title/), 'du');
    await waitFor(() => expect(screen.queryByRole('group', { name: 'Recently added' })).not.toBeInTheDocument());

    await user.clear(screen.getByPlaceholderText(/Search by title/));
    expect(await screen.findByRole('group', { name: 'Recently added' })).toBeInTheDocument();
    // Served from the per-library cache the second time.
    expect(api.audiobookshelf.getRecentlyAdded).toHaveBeenCalledTimes(1);
  });

  it('leaves the recently added section out when nothing was added recently', async () => {
    render(FindBook);

    await waitFor(() => expect(api.audiobookshelf.getRecentlyAdded).toHaveBeenCalled());
    expect(screen.queryByRole('group', { name: 'Recently added' })).not.toBeInTheDocument();
  });

  it('does not show recently added books under a saved query', async () => {
    localStorage.setItem(SEARCH_QUERY_KEY, 'dune');
    vi.mocked(api.audiobookshelf.getRecentlyAdded).mockResolvedValue([recentBook('b1', 'Fresh Book')]);
    render(FindBook);

    await waitFor(() => expect(api.audiobookshelf.getRecentlyAdded).toHaveBeenCalled());
    expect(screen.queryByRole('group', { name: 'Recently added' })).not.toBeInTheDocument();
  });
});
