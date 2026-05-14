<script lang="ts">
  import { slide, fade } from 'svelte/transition';
  import { session } from '../stores/session';
  import { api } from '../utils/api';
  import AudiobookCard from './AudiobookCard.svelte';
  import DocLink from './DocLink.svelte';
  import ChapterSearch from './chapter_search/ChapterSearch.svelte';

  // Icons
  import ArrowRight from '@lucide/svelte/icons/arrow-right';
  import Check from '@lucide/svelte/icons/check';
  import CircleQuestionMark from '@lucide/svelte/icons/circle-question-mark';

  interface LibraryInfo {
    id: string;
    name: string;
    [key: string]: unknown;
  }

  interface BookInfo {
    title: string;
    duration: number;
    coverUrl: string;
    fileCount: number;
  }

  let inputMode = $state('search');
  let isChapterSearch = $derived(inputMode === 'chapterSearch');
  let itemId = $state('');
  let validationError = $state('');
  let isValidating = $state(false);
  let isDebouncing = $state(false);
  let showHelp = $state(false);
  let bookInfo = $state<BookInfo | null>(null);
  let isValidItem = $state(false);

  let itemIdInput: HTMLInputElement | undefined = $state();
  let searchInput: HTMLInputElement | undefined = $state();

  let libraries = $state<LibraryInfo[]>([]);
  let selectedLibrary = $state<LibraryInfo | null>(null);
  let searchQuery = $state('');
  let searchResults = $state<unknown[]>([]);
  let isLoadingLibraries = $state(false);
  let isSearching = $state(false);
  let searchError = $state('');

  let validationTimeout: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    validationError = '';
    bookInfo = null;
    isValidItem = false;

    if (itemId.length > 0) {
      if (itemId.length < 10) {
        validationError = 'Item ID seems too short';
        isDebouncing = false;
      } else if (!/^[a-f0-9-]+$/i.test(itemId)) {
        validationError = 'Item ID should contain only letters, numbers, and hyphens';
        isDebouncing = false;
      } else {
        clearTimeout(validationTimeout);
        isDebouncing = true;
        validationTimeout = setTimeout(() => {
          isDebouncing = false;
          void validateItemId(itemId.trim());
        }, 800);
      }
    } else {
      isDebouncing = false;
    }
  });

  async function validateItemId(id: string) {
    if (!id || validationError) return;

    isValidating = true;

    try {
      const response = await api.session.validateItem(id);

      if (response.valid) {
        bookInfo = {
          title: response.book_title ?? '',
          duration: response.book_duration ?? 0,
          coverUrl: response.cover_url ?? '',
          fileCount: response.file_count || 1,
        };
        isValidItem = true;
        validationError = '';
      } else {
        bookInfo = null;
        isValidItem = false;
        validationError = response.error_message || 'Invalid item ID';
      }
    } catch (error) {
      console.error('Failed to validate item:', error);
      bookInfo = null;
      isValidItem = false;
      validationError = 'Failed to validate item. Please check your connection and try again.';
    } finally {
      isValidating = false;
      // Restore focus to input after validation
      if (itemIdInput) {
        setTimeout(() => itemIdInput?.focus(), 0);
      }
    }
  }

  async function handleSubmit() {
    if (!itemId.trim()) {
      validationError = 'Please enter an item ID';
      return;
    }

    if (validationError || !isValidItem) {
      return;
    }

    isValidating = true;

    try {
      await session.createSession(itemId.trim());
    } catch (error) {
      console.error('Failed to create session:', error);
      const message = error instanceof Error ? error.message : String(error);
      validationError = message || 'Failed to create session';
    } finally {
      isValidating = false;
    }
  }

  function handleKeyDown(event: KeyboardEvent) {
    if (event.key === 'Enter') {
      handleSubmit();
    }
  }

  // Handle paste - clean up common formatting issues
  function handlePaste(_event: ClipboardEvent) {
    setTimeout(() => {
      itemId = itemId.trim().replace(/\s+/g, '');
    }, 0);
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
    if (inputMode === 'search' && selectedLibrary && searchQuery.length >= 2) {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        void performSearch();
      }, 500);
    } else if (inputMode === 'search' && searchQuery.length < 2) {
      searchResults = [];
      searchError = '';
    }
  });

  async function performSearch() {
    if (!selectedLibrary || !searchQuery.trim()) {
      searchResults = [];
      return;
    }

    isSearching = true;
    searchError = '';

    try {
      const results = (await api.audiobookshelf.searchLibrary(selectedLibrary.id, searchQuery.trim())) as unknown[];
      searchResults = results;

      if (results.length === 0) {
        searchError = 'No audiobooks found matching your search.';
      }
    } catch (error) {
      console.error('Search failed:', error);
      searchError = 'Search failed. Please try again.';
      searchResults = [];
    } finally {
      isSearching = false;
      // Restore focus to search input after search
      if (searchInput) {
        setTimeout(() => searchInput?.focus(), 0);
      }
    }
  }

  // Handle library change - save preference and trigger new search if query exists
  async function handleLibraryChange() {
    if (selectedLibrary) {
      localStorage.setItem('achew-last-library-id', selectedLibrary.id);
    }
    if (searchQuery.length >= 2) {
      await performSearch();
    }
  }

  // Handle starting session from search result
  async function startSessionFromBook(book: { id: string }) {
    isValidating = true;

    try {
      await session.createSession(book.id);
    } catch (error) {
      console.error('Failed to create session from search result:', error);
      const message = error instanceof Error ? error.message : String(error);
      searchError = message || 'Failed to create session';
    } finally {
      isValidating = false;
    }
  }

  // Mode switching
  function switchToItemIdMode() {
    inputMode = 'itemId';
  }

  function switchToSearchMode() {
    inputMode = 'search';
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
  }

  function clearAllState() {
    // Clear search state
    searchQuery = '';
    searchResults = [];
    searchError = '';
    // Clear item ID state
    itemId = '';
    validationError = '';
    bookInfo = null;
    isValidItem = false;
    api.audiobookshelf.clearAllCache().catch(console.error);
  }

  // Load libraries on component mount if starting in search mode
  import { onMount } from 'svelte';

  onMount(() => {
    if (inputMode === 'search') {
      loadLibraries();
    }
  });

  // Show different content based on session state
  let showCompletedMessage = $derived($session.step === 'completed');
</script>

<div class="session-start">
  {#if showCompletedMessage}
    <div class="success-card">
      <div class="card-body text-center">
        <div class="success-icon">
          <Check size="72" color="var(--success)" />
        </div>

        <h2 class="text-success">Chapters Submitted!</h2>
        <p>Your audiobook chapters have been successfully saved to Audiobookshelf.</p>
        <div class="actions">
          <button
            class="btn btn-verify"
            onclick={() => {
              session.deleteSession();
              clearAllState();
              inputMode = 'search';
            }}
          >
            New Audiobook
          </button>
        </div>
      </div>
    </div>
  {:else}
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
          Title Search
        </button>
        <button class="mode-btn {inputMode === 'itemId' ? 'active' : ''}" onclick={switchToItemIdMode} type="button">
          Item ID
        </button>
        <button
          class="mode-btn {inputMode === 'chapterSearch' ? 'active' : ''}"
          onclick={switchToChapterSearchMode}
          type="button"
        >
          Chapter Search
        </button>
      </div>

      {#if inputMode === 'itemId'}
        <!-- Item ID Input Form -->
        <form
          onsubmit={(e) => {
            e.preventDefault();
            void handleSubmit();
          }}
          class="item-form"
        >
          <div class="form-group">
            <div class="input-container">
              <input
                id="itemId"
                type="text"
                class="form-control {validationError ? 'is-invalid' : ''} {isDebouncing
                  ? 'is-debouncing'
                  : ''} {isValidating ? 'is-validating' : ''}"
                bind:value={itemId}
                bind:this={itemIdInput}
                onkeydown={handleKeyDown}
                onpaste={handlePaste}
                placeholder="Enter an Audiobookshelf item ID"
                disabled={$session.loading}
                autocomplete="off"
                spellcheck="false"
              />
              <button
                type="button"
                class="help-icon"
                onclick={() => (showHelp = !showHelp)}
                onmouseenter={() => (showHelp = true)}
                onmouseleave={() => (showHelp = false)}
                aria-label="Where to find the Item ID"
              >
                <CircleQuestionMark size="16" color="var(--text-muted)" />
              </button>

              {#if showHelp}
                <div class="help-tooltip">
                  <div class="help-tooltip-content">
                    <p>
                      When viewing a book in Audiobookshelf, the Item ID can be found in the URL after <em>"/item/"</em>
                    </p>
                    <code
                      >https://your-abs-server.com/library/item/<span class="url-id-highlight"
                        >6f0aa6e5-684a-4823-aaeb-1a15c7084902</span
                      ></code
                    >
                  </div>
                </div>
              {/if}
            </div>
            {#if validationError}
              <div class="invalid-feedback">
                {validationError}
              </div>
            {/if}
          </div>
        </form>

        <!-- Item ID Result -->
        {#if bookInfo && isValidItem}
          <div class="item-result">
            <div class="results-list">
              <AudiobookCard
                title={bookInfo.title}
                duration={bookInfo.duration}
                coverImageUrl={bookInfo.coverUrl}
                fileCount={bookInfo.fileCount || 1}
                size="compact"
              >
                {#snippet actions()}
                  <div class="search-result-actions">
                    <button
                      type="submit"
                      class="btn btn-verify start-btn"
                      disabled={$session.loading}
                      onclick={handleSubmit}
                    >
                      {#if isValidating || $session.loading}
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
      {:else if inputMode === 'search'}
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
            <input
              type="text"
              class="search-input {searchError ? 'is-invalid' : ''} {isSearching ? 'is-searching' : ''}"
              bind:value={searchQuery}
              bind:this={searchInput}
              placeholder="Search for audiobooks…"
              disabled={!selectedLibrary || $session.loading}
              autocomplete="off"
              spellcheck="false"
            />
          </div>

          {#if searchError}
            <div class="invalid-feedback">
              {searchError}
            </div>
          {/if}
        </div>

        <!-- Search Results -->
        {#if searchResults.length > 0}
          <div class="search-results">
            <div class="results-list">
              {#each searchResults as bookRaw}
                {@const book = bookRaw as {
                  id: string;
                  duration: number;
                  media: { metadata: { title: string }; coverPath: string; audioFiles?: unknown[] };
                }}
                <AudiobookCard
                  title={book.media.metadata.title}
                  duration={book.duration}
                  coverImageUrl={book.media.coverPath}
                  fileCount={book.media.audioFiles?.length || 0}
                  size="compact"
                >
                  {#snippet actions()}
                    <div class="search-result-actions">
                      <button
                        class="btn btn-verify start-btn"
                        disabled={$session.loading}
                        onclick={() => startSessionFromBook(book)}
                      >
                        {#if isValidating || $session.loading}
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
          </div>
        {/if}
      {:else if inputMode === 'chapterSearch'}
        <ChapterSearch />
      {/if}

      <div class="start-docs">
        <DocLink path="/getting-started/" text="Getting Started" featureName="Getting Started" />
        &nbsp;·&nbsp;
        <DocLink path="/getting-started/finding-a-book/" text="Finding a Book" featureName="Finding a Book" />
      </div>
    </div>
  {/if}
</div>

<style>
  .session-start {
    max-width: 800px;
    margin: 0 auto;
    width: 100%;
  }

  .actions {
    display: flex;
    justify-content: center;
    margin-top: 1.5rem;
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

  .success-card p {
    margin-bottom: 4rem;
    max-width: 360px;
    margin-left: auto;
    margin-right: auto;
  }

  .start-docs {
    margin-top: 1.5rem;
    font-size: 0.85rem;
    text-align: center;
  }

  .success-card .card-body {
    padding: 3rem;
  }

  .item-form {
    width: 100%;
    max-width: 600px;
    text-align: center;
  }

  .input-container {
    position: relative;
    display: inline-block;
    width: 100%;
    margin: 0 auto;
  }

  .form-control.is-invalid {
    border-color: var(--danger);
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

  .help-icon {
    position: absolute;
    right: 12px;
    top: 50%;
    transform: translateY(-50%);
    background: none;
    border: none;
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background-color 0.2s ease;
    z-index: 2;
  }

  .help-icon:hover {
    background-color: var(--bg-secondary);
  }

  .help-tooltip {
    position: absolute;
    bottom: 100%;
    left: 50%;
    transform: translateX(-50%);
    margin-bottom: 8px;
    width: 650px;
    max-width: 90vw;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    z-index: 10;
    animation: fadeInDown 0.2s ease-out;
  }

  @keyframes fadeInDown {
    from {
      opacity: 0;
      transform: translateX(-50%) translateY(8px);
    }
    to {
      opacity: 1;
      transform: translateX(-50%) translateY(0);
    }
  }

  .help-tooltip-content {
    padding: 1rem;
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

  /* Loading states for input field */
  .form-control.is-debouncing {
    border-color: var(--text-muted);
    background-image: url("data:image/svg+xml;charset=utf-8,%3Csvg width='16' height='16' viewBox='0 0 16 16' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Ccircle cx='8' cy='8' r='6' stroke='%23999999' stroke-width='2' opacity='0.3'/%3E%3Cpath d='M8 2A6 6 0 0 1 14 8' stroke='%23666666' stroke-width='2' stroke-linecap='round'%3E%3CanimateTransform attributeName='transform' type='rotate' dur='2s' values='0 8 8;360 8 8' repeatCount='indefinite'/%3E%3C/path%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 40px center;
    background-size: 16px 16px;
  }

  .form-control.is-validating {
    border-color: var(--primary);
    background-image: url("data:image/svg+xml;charset=utf-8,%3Csvg width='16' height='16' viewBox='0 0 16 16' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Ccircle cx='8' cy='8' r='6' stroke='%234a90e2' stroke-width='2' opacity='0.3'/%3E%3Cpath d='M8 2A6 6 0 0 1 14 8' stroke='%234a90e2' stroke-width='2' stroke-linecap='round'%3E%3CanimateTransform attributeName='transform' type='rotate' dur='1s' values='0 8 8;360 8 8' repeatCount='indefinite'/%3E%3C/path%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 40px center;
    background-size: 16px 16px;
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
    min-width: 480px;
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

    .form-control {
      width: 100%;
      font-size: 0.9rem;
    }

    .input-container {
      max-width: 100%;
    }

    .help-tooltip {
      width: 95vw;
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

    .success-card .card-body {
      padding: 2rem 1rem;
    }
  }

  @media (max-width: 480px) {
    .start-btn {
      min-width: 80px;
    }
  }
</style>
