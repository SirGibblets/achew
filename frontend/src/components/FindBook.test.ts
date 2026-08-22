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
});

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
});
