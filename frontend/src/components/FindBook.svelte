<script lang="ts">
  import { slide, fade } from 'svelte/transition';
  import { tooltip } from '../actions/tooltip';
  import { session } from '../stores/session';
  import { api } from '../utils/api';
  import type { LibrarySearchHit } from '../types/book';
  import AudiobookCard from './AudiobookCard.svelte';
  import DocLink from './DocLink.svelte';
  import ChapterSearch from './chapter_search/ChapterSearch.svelte';

  // Icons
  import ArrowRight from '@lucide/svelte/icons/arrow-right';
  import CircleQuestionMark from '@lucide/svelte/icons/circle-question-mark';
  import X from '@lucide/svelte/icons/x';

  interface LibraryInfo {
    id: string;
    name: string;
    [key: string]: unknown;
  }

  interface BookInfo {
    title: string;
    subtitle: string | null;
    duration: number;
    coverUrl: string;
    fileCount: number;
    authors: string[];
    narrators: string[];
    seriesName: string | null;
    seriesSequence: string | null;
  }

  // Audiobookshelf item IDs are UUIDs; installs predating that migration use an
  // `li_` prefix instead. Anything else is treated as free text.
  const ITEM_ID_PATTERN = /^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|li_[0-9a-z]+)$/i;

  const MIN_QUERY_LENGTH = 2;
  const SEARCH_DEBOUNCE_MS = 500;

  // How many results to render at once. Searching a prolific author or narrator
  // can match well over a hundred books, so the rest are revealed on demand.
  const PAGE_SIZE = 36;

  const INPUT_MODE_STORAGE_KEY = 'achew-last-input-mode';
  const SEARCH_QUERY_STORAGE_KEY = 'achew-last-search-query';

  let inputMode = $state(localStorage.getItem(INPUT_MODE_STORAGE_KEY) === 'chapterSearch' ? 'chapterSearch' : 'search');
  let isChapterSearch = $derived(inputMode === 'chapterSearch');

  let searchInput: HTMLInputElement | undefined = $state();

  let libraries = $state<LibraryInfo[]>([]);
  let selectedLibrary = $state<LibraryInfo | null>(null);
  let searchQuery = $state(localStorage.getItem(SEARCH_QUERY_STORAGE_KEY) ?? '');
  let searchResults = $state<LibrarySearchHit[]>([]);
  let searchTotal = $state(0);
  let visibleCount = $state(PAGE_SIZE);
  let visibleResults = $derived(searchResults.slice(0, visibleCount));
  // Held back locally and revealable without another request.
  let revealable = $derived(searchResults.length - visibleCount);
  // Matched but never fetched, so only a narrower query can reach them.
  let unreachable = $derived(searchTotal - searchResults.length);
  let isLoadingLibraries = $state(false);
  let isSearching = $state(false);
  let isDebouncing = $state(false);
  let isStarting = $state(false);
  let searchError = $state('');

  // Populated only when the query resolved to a real item ID.
  let itemPreview = $state<BookInfo | null>(null);
  let itemPreviewId = $state('');

  // The query the current results were produced from, so highlighting cannot
  // drift ahead of the results while a new search is in flight.
  let resultQuery = $state('');

  function looksLikeItemId(query: string): boolean {
    return ITEM_ID_PATTERN.test(query);
  }

  /**
   * Look an item ID up directly. Returns false when the ID is well-formed but
   * unknown to the server, so the caller can fall back to a text search rather
   * than dead-ending on a query that merely looks like an ID.
   */
  async function tryItemId(id: string): Promise<boolean> {
    const response = await api.session.validateItem(id);
    if (!response.valid) return false;

    itemPreview = {
      title: response.book_title ?? '',
      subtitle: response.book_subtitle ?? null,
      duration: response.book_duration ?? 0,
      coverUrl: response.cover_url ?? '',
      fileCount: response.file_count || 1,
      authors: response.authors ?? [],
      narrators: response.narrators ?? [],
      seriesName: response.series_name ?? null,
      seriesSequence: response.series_sequence ?? null,
    };
    itemPreviewId = id;
    return true;
  }

  async function runQuery(query: string) {
    isSearching = true;
    searchError = '';
    itemPreview = null;
    itemPreviewId = '';
    visibleCount = PAGE_SIZE;

    try {
      if (looksLikeItemId(query) && (await tryItemId(query))) {
        searchResults = [];
        searchTotal = 0;
        resultQuery = query;
        return;
      }

      if (!selectedLibrary) {
        searchError = 'Select a library to search.';
        return;
      }

      const response = await api.audiobookshelf.searchLibrary(selectedLibrary.id, query);
      searchResults = response.hits;
      searchTotal = response.total;
      resultQuery = query;

      if (response.hits.length === 0) {
        searchError = 'No audiobooks found matching your search.';
      }
    } catch (error) {
      console.error('Search failed:', error);
      searchError = 'Search failed. Please try again.';
      searchResults = [];
      searchTotal = 0;
    } finally {
      isSearching = false;
      // Restore focus to search input after search
      if (searchInput) {
        setTimeout(() => searchInput?.focus(), 0);
      }
    }
  }

  // Handle starting a session from either an item-ID lookup or a search result
  async function startSession(bookId: string) {
    isStarting = true;

    try {
      await session.createSession(bookId);
    } catch (error) {
      console.error('Failed to create session:', error);
      const message = error instanceof Error ? error.message : String(error);
      searchError = message || 'Failed to create session';
    } finally {
      isStarting = false;
    }
  }

  // Search functionality
  let searchTimeout: ReturnType<typeof setTimeout> | undefined;

  async function loadLibraries() {
    if (libraries.length > 0) return; // Already loaded

    isLoadingLibraries = true;
    searchError = '';

    try {
      libraries = (await api.audiobookshelf.getLibraries()) as LibraryInfo[];

      // Auto-select last-used library, or first if unavailable
      if (libraries.length > 0) {
        const savedId = localStorage.getItem('achew-last-library-id');
        const saved = savedId && libraries.find((l) => l.id === savedId);
        selectedLibrary = saved || libraries[0];
      }
    } catch (error) {
      console.error('Failed to load libraries:', error);
      searchError = 'Failed to load libraries. Please check your connection.';
      libraries = [];
    } finally {
      isLoadingLibraries = false;
    }
  }

  $effect(() => {
    const query = searchQuery.trim();

    if (inputMode !== 'search') return;

    if (query.length < MIN_QUERY_LENGTH) {
      clearTimeout(searchTimeout);
      isDebouncing = false;
      searchResults = [];
      searchTotal = 0;
      visibleCount = PAGE_SIZE;
      itemPreview = null;
      searchError = '';
      return;
    }

    // Reference the library so switching it re-runs the query.
    void selectedLibrary;

    clearTimeout(searchTimeout);
    isDebouncing = true;
    searchTimeout = setTimeout(() => {
      isDebouncing = false;
      void runQuery(query);
    }, SEARCH_DEBOUNCE_MS);
  });

  $effect(() => {
    localStorage.setItem(SEARCH_QUERY_STORAGE_KEY, searchQuery);
  });

  function clearSearchQuery() {
    searchQuery = '';
    searchInput?.focus();
  }

  // Handle library change - save preference; the search effect re-runs the query
  function handleLibraryChange() {
    if (selectedLibrary) {
      localStorage.setItem('achew-last-library-id', selectedLibrary.id);
    }
  }

  function switchToSearchMode() {
    inputMode = 'search';
    localStorage.setItem(INPUT_MODE_STORAGE_KEY, 'search');
    loadLibraries();
    restoreSavedLibrary();
  }

  function restoreSavedLibrary() {
    if (libraries.length === 0) return;
    const savedId = localStorage.getItem('achew-last-library-id');
    const saved = savedId && libraries.find((l) => l.id === savedId);
    if (saved && saved !== selectedLibrary) {
      selectedLibrary = saved;
    }
  }

  function switchToChapterSearchMode() {
    inputMode = 'chapterSearch';
    localStorage.setItem(INPUT_MODE_STORAGE_KEY, 'chapterSearch');
  }

  // Load libraries on component mount if starting in search mode
  import { onMount } from 'svelte';

  onMount(() => {
    if (inputMode === 'search') {
      loadLibraries();
    }
  });
</script>

<div class="session-start">
  <div class="start-content">
    {#if !isChapterSearch}
      <div class="header-area" transition:slide={{ duration: 200 }}>
        <div class="header-section" transition:fade={{ duration: 33 }}>
          <img class="header-image header-image-light" src="/img/hero-light.webp" alt="Achew header" />
          <img class="header-image header-image-dark" src="/img/hero-dark.webp" alt="Achew header" />
        </div>
      </div>
    {/if}

    <!-- Mode Selector -->
    <div class="mode-selector">
      <button class="mode-btn {inputMode === 'search' ? 'active' : ''}" onclick={switchToSearchMode} type="button">
        Book Search
      </button>
      <button
        class="mode-btn {inputMode === 'chapterSearch' ? 'active' : ''}"
        onclick={switchToChapterSearchMode}
        type="button"
      >
        Chapter Search
      </button>
    </div>

    {#if inputMode === 'search'}
      <!-- Search Interface -->
      <div class="search-form">
        <div class="search-input-container">
          <!-- Library Dropdown -->
          <select
            class="library-select"
            bind:value={selectedLibrary}
            onchange={handleLibraryChange}
            disabled={isLoadingLibraries || $session.loading}
          >
            {#if isLoadingLibraries}
              <option>Loading libraries…</option>
            {:else if libraries.length === 0}
              <option>No libraries found</option>
            {:else}
              {#each libraries as library}
                <option value={library}>{library.name}</option>
              {/each}
            {/if}
          </select>

          <!-- Search Input -->
          <div class="search-input-wrap">
            <input
              type="text"
              class="search-input {searchError ? 'is-invalid' : ''} {isSearching ? 'is-searching' : ''} {isDebouncing
                ? 'is-debouncing'
                : ''}"
              bind:value={searchQuery}
              bind:this={searchInput}
              placeholder="Search by title, author, series, narrator, or item ID…"
              disabled={!selectedLibrary || $session.loading}
              autocomplete="off"
              spellcheck="false"
            />

            {#if searchQuery}
              <button
                type="button"
                class="search-clear-icon"
                aria-label="Clear search"
                disabled={$session.loading}
                onclick={clearSearchQuery}
              >
                <X size="16" color="var(--text-muted)" />
              </button>
            {/if}

            {#snippet helpContent()}
              <div class="help-tooltip-content">
                <p>
                  Search the selected library by book title, subtitle, series, author, or narrator. Matching authors,
                  series and narrators are expanded into their books, and results are ordered by how closely they match.
                </p>
                <p>
                  You can also paste an Audiobookshelf item ID to go straight to one book. The item ID appears in the
                  URL for a book, after <em>"/item/"</em>:
                </p>
                <code
                  >https://your-abs-server.com/library/item/<span class="url-id-highlight"
                    >6f0aa6e5-684a-4823-aaeb-1a15c7084902</span
                  ></code
                >
              </div>
            {/snippet}
            <button
              type="button"
              class="search-help-icon"
              aria-label="What you can search for"
              use:tooltip={{ content: helpContent, maxWidth: 650, delay: 0 }}
            >
              <CircleQuestionMark size="16" color="var(--text-muted)" />
            </button>
          </div>
        </div>

        {#if searchError}
          <div class="invalid-feedback">
            {searchError}
          </div>
        {/if}
      </div>

      <!-- Item ID Result -->
      {#if itemPreview}
        <div class="item-result">
          <div class="results-list">
            <AudiobookCard
              title={itemPreview.title}
              subtitle={itemPreview.subtitle}
              duration={itemPreview.duration}
              coverImageUrl={itemPreview.coverUrl}
              fileCount={itemPreview.fileCount || 1}
              seriesName={itemPreview.seriesName}
              seriesSequence={itemPreview.seriesSequence}
              authors={itemPreview.authors}
              narrators={itemPreview.narrators}
              size="compact"
            >
              {#snippet actions()}
                <div class="search-result-actions">
                  <button
                    class="btn btn-verify start-btn"
                    disabled={$session.loading}
                    onclick={() => startSession(itemPreviewId)}
                  >
                    {#if isStarting || $session.loading}
                      <span class="btn-spinner"></span>
                      Processing…
                    {:else}
                      Start
                      <ArrowRight size="14" />
                    {/if}
                  </button>
                </div>
              {/snippet}
            </AudiobookCard>
          </div>
        </div>
      {/if}

      <!-- Search Results -->
      {#if searchResults.length > 0}
        <div class="search-results">
          <div class="results-list">
            {#each visibleResults as hit (hit.book.id)}
              {@const book = hit.book}
              {@const meta = book.media.metadata}
              {@const firstSeries = meta.series?.[0]}
              <AudiobookCard
                title={meta.title}
                subtitle={meta.subtitle}
                duration={book.duration}
                coverImageUrl={book.media.coverPath}
                fileCount={book.media.numAudioFiles ?? book.media.audioFiles?.length ?? 1}
                seriesName={firstSeries?.name ?? meta.seriesName}
                seriesSequence={firstSeries?.sequence}
                authors={meta.authors?.map((a) => a.name)}
                narrators={meta.narrators}
                highlightQuery={resultQuery}
                size="compact"
              >
                {#snippet actions()}
                  <div class="search-result-actions">
                    <button
                      class="btn btn-verify start-btn"
                      disabled={$session.loading}
                      onclick={() => startSession(book.id)}
                    >
                      {#if isStarting || $session.loading}
                        <span class="btn-spinner"></span>
                        Processing…
                      {:else}
                        Start
                        <ArrowRight size="14" />
                      {/if}
                    </button>
                  </div>
                {/snippet}
              </AudiobookCard>
            {/each}
          </div>
          {#if revealable > 0 || unreachable > 0}
            <div class="results-footer">
              <p class="results-count">
                Showing {visibleResults.length} of {searchTotal} matches
              </p>
              {#if revealable > 0}
                <button
                  type="button"
                  class="btn btn-secondary show-more-btn"
                  onclick={() => (visibleCount += PAGE_SIZE)}
                >
                  Show {Math.min(PAGE_SIZE, revealable)} more
                </button>
              {:else}
                <p class="results-count">Narrow your search to see the remaining {unreachable}.</p>
              {/if}
            </div>
          {/if}
        </div>
      {/if}
    {:else if inputMode === 'chapterSearch'}
      <ChapterSearch />
    {/if}

    {#if !isChapterSearch}
      <div class="start-docs">
        <DocLink path="/getting-started/" text="Getting Started" featureName="Getting Started" />
        &nbsp;·&nbsp;
        <DocLink path="/getting-started/finding-a-book/" text="Finding a Book" featureName="Finding a Book" />
      </div>
    {/if}
  </div>
</div>

<style>
  .session-start {
    max-width: 800px;
    margin: 0 auto;
    width: 100%;
  }

  .start-content {
    display: flex;
    flex-direction: column;
    align-items: center;
  }

  .header-area {
    width: 100%;
    max-width: 600px;
    display: flex;
    align-items: center;
    justify-content: center;
    padding-bottom: 2rem;
  }

  .header-section {
    text-align: center;
    padding: 0 2rem 3rem 2rem;
    width: 100%;
  }

  .start-docs {
    margin-top: 1.5rem;
    font-size: 0.85rem;
    text-align: center;
  }

  .header-image {
    width: 100%;
    max-width: 440px;
  }

  .header-image-dark {
    display: none;
  }

  :global([data-theme='dark']) .header-image-dark {
    display: inline-block;
  }

  :global([data-theme='dark']) .header-image-light {
    display: none;
  }

  .search-help-icon {
    flex-shrink: 0;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0 0.75rem;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background-color 0.2s ease;
  }

  .search-help-icon:hover {
    background-color: var(--bg-secondary);
  }

  .search-clear-icon {
    flex-shrink: 0;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0 0.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background-color 0.2s ease;
  }

  .search-clear-icon:hover:not(:disabled) {
    background-color: var(--bg-secondary);
  }

  .search-clear-icon:disabled {
    cursor: default;
    opacity: 0.5;
  }

  .help-tooltip-content p {
    margin: 0 0 0.5rem 0;
    color: var(--text-primary);
    font-size: 0.875rem;
    line-height: 1.4;
  }

  .help-tooltip-content code {
    display: block;
    background-color: var(--bg-tertiary);
    border-radius: 0.25rem;
    padding: 0.5rem;
    font-size: 0.75rem;
    color: var(--text-muted);
    overflow-x: auto;
    word-break: break-all;
    font-family: monospace;
  }

  .invalid-feedback {
    display: block;
    color: var(--danger);
    font-size: 0.875rem;
    margin-top: 0.25rem;
  }

  .start-btn {
    padding: 0.5rem 0.75rem;
    font-weight: 600;
    min-width: 100px;
  }

  .url-id-highlight {
    font-weight: 600;
    color: var(--text-primary);
  }

  .mode-selector {
    display: inline-flex;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    margin-bottom: 2rem;
    min-width: 360px;
    margin-left: auto;
    margin-right: auto;
    overflow: hidden;
  }

  .mode-btn {
    flex: 1;
    padding: 0.5rem 1rem;
    border: none;
    background: transparent;
    color: var(--text-muted);
    font-weight: 500;
    font-size: 0.875rem;
    border-radius: 0;
    cursor: pointer;
    position: relative;
    border-right: 1px solid var(--border-color);
  }

  .mode-btn:first-child {
    border-top-left-radius: 7px;
    border-bottom-left-radius: 7px;
  }

  .mode-btn:last-child {
    border-top-right-radius: 7px;
    border-bottom-right-radius: 7px;
    border-right: none;
  }

  .mode-btn:hover:not(.active) {
    color: var(--text-primary);
    background: var(--hover-bg);
  }

  .mode-btn.active {
    background: linear-gradient(135deg, var(--verify-gradient-start) 0%, var(--verify-gradient-end) 100%);
    color: white;
    font-weight: 600;
    border-right-color: transparent;
  }

  .mode-btn.active + .mode-btn {
    border-left: 1px solid transparent;
  }

  /* Search Form Styles */
  .search-form {
    width: 100%;
    max-width: 600px;
    text-align: center;
  }

  .search-input-container {
    font-size: 1rem;
    width: 100%;
    display: flex;
    overflow: hidden;
    border-radius: 8px;
    border: 1px solid var(--border-color);
    transition: border-color 0.2s ease;
    background: var(--bg-primary);
    color: var(--text-primary);
  }

  .search-input-container:focus-within {
    border-color: var(--primary);
  }

  .library-select {
    background: var(--bg-tertiary);
    border: none;
    padding: 0.75rem 1rem;
    color: var(--text-primary);
    font-weight: 500;
    min-width: 150px;
    border-right: 1px solid var(--border-color);
    outline: none;
  }

  /* Keeps the help icon beside the input, including in the stacked mobile layout */
  .search-input-wrap {
    flex: 1;
    display: flex;
    min-width: 0;
    background: var(--bg-primary);
  }

  .search-input {
    flex: 1;
    border: none;
    padding: 0.75rem 1rem;
    background: var(--bg-primary);
    color: var(--text-primary);
    font-size: 1rem;
    outline: none;
    min-width: 0;
  }

  .search-input.is-searching {
    background-image: url("data:image/svg+xml;charset=utf-8,%3Csvg width='16' height='16' viewBox='0 0 16 16' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Ccircle cx='8' cy='8' r='6' stroke='%234a90e2' stroke-width='2' opacity='0.3'/%3E%3Cpath d='M8 2A6 6 0 0 1 14 8' stroke='%234a90e2' stroke-width='2' stroke-linecap='round'%3E%3CanimateTransform attributeName='transform' type='rotate' dur='1s' values='0 8 8;360 8 8' repeatCount='indefinite'/%3E%3C/path%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 12px center;
    background-size: 16px 16px;
    padding-right: 2.5rem;
  }

  .search-input.is-debouncing {
    background-image: url("data:image/svg+xml;charset=utf-8,%3Csvg width='16' height='16' viewBox='0 0 16 16' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Ccircle cx='8' cy='8' r='6' stroke='%23999999' stroke-width='2' opacity='0.3'/%3E%3Cpath d='M8 2A6 6 0 0 1 14 8' stroke='%23666666' stroke-width='2' stroke-linecap='round'%3E%3CanimateTransform attributeName='transform' type='rotate' dur='2s' values='0 8 8;360 8 8' repeatCount='indefinite'/%3E%3C/path%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 12px center;
    background-size: 16px 16px;
    padding-right: 2.5rem;
  }

  .results-footer {
    margin-top: 1.25rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.6rem;
  }

  .results-count {
    margin: 0;
    text-align: center;
    color: var(--text-secondary);
    font-size: 0.85rem;
  }

  .show-more-btn {
    padding: 0.5rem 1.25rem;
    font-size: 0.85rem;
  }

  /* Search Results Styles */
  .search-results,
  .item-result {
    width: 100%;
    max-width: 600px;
    margin-top: 0;
  }

  .results-list {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    margin-top: 2rem;
  }

  .search-result-actions {
    flex-shrink: 0;
  }

  /* Responsive design */
  @media (max-width: 768px) {
    .session-start {
      padding: 1rem 0.5rem;
    }

    .header-area {
      min-height: 120px;
    }

    .header-section {
      padding: 0;
    }

    .help-tooltip-content code {
      font-size: 0.7rem;
      padding: 0.375rem;
    }

    .mode-selector {
      min-width: 240px;
      max-width: 100%;
    }

    .search-input-container {
      flex-direction: column;
    }

    .library-select {
      border-right: none;
      border-bottom: 1px solid var(--border-color);
      min-width: auto;
    }

    .search-input {
      min-width: auto;
    }
  }

  @media (max-width: 480px) {
    .start-btn {
      min-width: 80px;
    }
  }
</style>
