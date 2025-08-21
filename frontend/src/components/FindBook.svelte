<script>
    import {session} from "../stores/session.js";
    import {api} from "../utils/api.js";
    import AudiobookCard from "./AudiobookCard.svelte";
    import Icon from "./Icon.svelte";

    // Icons
    import ArrowRight from "@lucide/svelte/icons/arrow-right";
    import Check from "@lucide/svelte/icons/check";
    import CircleQuestionMark from "@lucide/svelte/icons/circle-question-mark";
    import RefreshCw from "@lucide/svelte/icons/refresh-cw";

    // Input mode - 'itemId', 'search', or 'missingChapters'
    let inputMode = "search";

    // Item ID mode variables
    let itemId = "";
    let validationError = "";
    let isValidating = false;
    let isDebouncing = false;
    let showHelp = false;
    let bookInfo = null;
    let isValidItem = false;

    // Element references for focus management
    let itemIdInput;
    let searchInput;

    // Search mode variables
    let libraries = [];
    let selectedLibrary = null;
    let searchQuery = "";
    let searchResults = [];
    let isLoadingLibraries = false;
    let isSearching = false;
    let searchError = "";

    // Missing Chapters mode variables
    let missingChaptersLibrary = null;
    let maxChapters = 0;
    let missingChaptersBooks = [];
    let filteredMissingChaptersBooks = [];
    let isFetchingMissingChapters = false;
    let isRefreshingCache = false;
    let missingChaptersError = "";

    // Format duration for display
    function formatDuration(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);

        if (hours > 0) {
            return `${hours}h ${minutes}m ${secs}s`;
        }
        return `${minutes}m ${secs}s`;
    }

    // Reactive validation with debounce for API calls
    let validationTimeout;
    $: {
        validationError = "";
        bookInfo = null;
        isValidItem = false;

        if (itemId.length > 0) {
            if (itemId.length < 10) {
                validationError = "Item ID seems too short";
                isDebouncing = false;
            } else if (!/^[a-f0-9-]+$/i.test(itemId)) {
                validationError =
                    "Item ID should contain only letters, numbers, and hyphens";
                isDebouncing = false;
            } else {
                // Clear any existing timeout
                clearTimeout(validationTimeout);

                // Set debouncing state
                isDebouncing = true;

                // Debounce API validation
                validationTimeout = setTimeout(async () => {
                    isDebouncing = false;
                    await validateItemId(itemId.trim());
                }, 800);
            }
        } else {
            isDebouncing = false;
        }
    }

    async function validateItemId(id) {
        if (!id || validationError) return;

        isValidating = true;

        try {
            const response = await api.session.validateItem(id);

            if (response.valid) {
                bookInfo = {
                    title: response.book_title,
                    duration: response.book_duration,
                    coverUrl: response.cover_url,
                    fileCount: response.file_count || 1,
                };
                isValidItem = true;
                validationError = "";
            } else {
                bookInfo = null;
                isValidItem = false;
                validationError = response.error_message || "Invalid item ID";
            }
        } catch (error) {
            console.error("Failed to validate item:", error);
            bookInfo = null;
            isValidItem = false;
            validationError =
                "Failed to validate item. Please check your connection and try again.";
        } finally {
            isValidating = false;
            // Restore focus to input after validation
            if (itemIdInput) {
                setTimeout(() => itemIdInput.focus(), 0);
            }
        }
    }

    async function handleSubmit() {
        if (!itemId.trim()) {
            validationError = "Please enter an item ID";
            return;
        }

        if (validationError || !isValidItem) {
            return;
        }

        isValidating = true;

        try {
            await session.createSession(itemId.trim());
        } catch (error) {
            console.error("Failed to create session:", error);
            validationError = error.message || "Failed to create session";
        } finally {
            isValidating = false;
        }
    }

    function handleKeyDown(event) {
        if (event.key === "Enter") {
            handleSubmit();
        }
    }

    // Handle paste - clean up common formatting issues
    function handlePaste(event) {
        setTimeout(() => {
            itemId = itemId.trim().replace(/\s+/g, "");
        }, 0);
    }

    // Search functionality
    let searchTimeout;

    async function loadLibraries() {
        if (libraries.length > 0) return; // Already loaded

        isLoadingLibraries = true;
        searchError = "";

        try {
            const librariesData = await api.audiobookshelf.getLibraries();
            libraries = librariesData;

            // Auto-select first library if available
            if (libraries.length > 0) {
                selectedLibrary = libraries[0];
            }
        } catch (error) {
            console.error("Failed to load libraries:", error);
            searchError = "Failed to load libraries. Please check your connection.";
            libraries = [];
        } finally {
            isLoadingLibraries = false;
        }
    }

    // Reactive search with debounce
    $: {
        if (inputMode === "search" && selectedLibrary && searchQuery.length >= 2) {
            // Clear existing timeout
            clearTimeout(searchTimeout);

            // Set debounce
            searchTimeout = setTimeout(async () => {
                await performSearch();
            }, 500);
        } else if (inputMode === "search" && searchQuery.length < 2) {
            searchResults = [];
            searchError = "";
        }
    }

    async function performSearch() {
        if (!selectedLibrary || !searchQuery.trim()) {
            searchResults = [];
            return;
        }

        isSearching = true;
        searchError = "";

        try {
            const results = await api.audiobookshelf.searchLibrary(
                selectedLibrary.id,
                searchQuery.trim(),
            );
            searchResults = results;

            if (results.length === 0) {
                searchError = "No audiobooks found matching your search.";
            }
        } catch (error) {
            console.error("Search failed:", error);
            searchError = "Search failed. Please try again.";
            searchResults = [];
        } finally {
            isSearching = false;
            // Restore focus to search input after search
            if (searchInput) {
                setTimeout(() => searchInput.focus(), 0);
            }
        }
    }

    // Handle library change - trigger new search if query exists
    async function handleLibraryChange() {
        if (searchQuery.length >= 2) {
            await performSearch();
        }
    }

    // Handle starting session from search result
    async function startSessionFromBook(book) {
        isValidating = true;

        try {
            await session.createSession(book.id);
        } catch (error) {
            console.error("Failed to create session from search result:", error);
            searchError = error.message || "Failed to create session";
        } finally {
            isValidating = false;
        }
    }

    async function loadMissingChaptersBooks() {
        if (!missingChaptersLibrary) return;

        isFetchingMissingChapters = true;
        missingChaptersError = "";

        try {
            const books = await api.audiobookshelf.getLibraryItems(missingChaptersLibrary.id);
            missingChaptersBooks = books;
            filterMissingChaptersBooks();
        } catch (error) {
            console.error("Failed to load missing chapters books:", error);
            missingChaptersError = "Failed to load books. Please check your connection.";
            missingChaptersBooks = [];
            filteredMissingChaptersBooks = [];
        } finally {
            isFetchingMissingChapters = false;
        }
    }

    function filterMissingChaptersBooks() {
        if (!missingChaptersBooks.length) {
            filteredMissingChaptersBooks = [];
            return;
        }

        filteredMissingChaptersBooks = missingChaptersBooks.filter(
            book => (book.media.numChapters || 0) <= maxChapters
        );
    }

    $: if (inputMode === "missingChapters" && missingChaptersBooks.length > 0 && maxChapters !== undefined) {
        filterMissingChaptersBooks();
    }

    async function handleMissingChaptersLibraryChange() {
        if (missingChaptersLibrary) {
            await loadMissingChaptersBooks();
        }
    }

    async function refreshMissingChaptersCache() {
        if (!missingChaptersLibrary) return;

        isRefreshingCache = true;
        missingChaptersError = "";

        try {
            const books = await api.audiobookshelf.getLibraryItems(missingChaptersLibrary.id, true);
            missingChaptersBooks = books;
            filterMissingChaptersBooks();
        } catch (error) {
            console.error("Failed to refresh cache:", error);
            missingChaptersError = "Failed to refresh cache. Please try again.";
        } finally {
            isRefreshingCache = false;
        }
    }

    // Mode switching
    function switchToItemIdMode() {
        inputMode = "itemId";
    }

    function switchToSearchMode() {
        inputMode = "search";
        loadLibraries();
    }

    function switchToMissingChaptersMode() {
        inputMode = "missingChapters";
        loadLibrariesForMissingChapters();
    }

    async function loadLibrariesForMissingChapters() {
        if (libraries.length > 0) {
            if (!missingChaptersLibrary && libraries.length > 0) {
                missingChaptersLibrary = libraries[0];
                await loadMissingChaptersBooks();
            }
            return;
        }

        isLoadingLibraries = true;
        missingChaptersError = "";

        try {
            const librariesData = await api.audiobookshelf.getLibraries();
            libraries = librariesData;

            if (libraries.length > 0) {
                missingChaptersLibrary = libraries[0];
                await loadMissingChaptersBooks();
            }
        } catch (error) {
            console.error("Failed to load libraries:", error);
            missingChaptersError = "Failed to load libraries. Please check your connection.";
            libraries = [];
        } finally {
            isLoadingLibraries = false;
        }
    }

    function clearAllState() {
        // Clear search state
        searchQuery = "";
        searchResults = [];
        searchError = "";
        // Clear item ID state
        itemId = "";
        validationError = "";
        bookInfo = null;
        isValidItem = false;
        // Clear missing chapters state
        missingChaptersBooks = [];
        filteredMissingChaptersBooks = [];
        missingChaptersError = "";
        maxChapters = 0;
        api.audiobookshelf.clearAllCache().catch(console.error);
    }

    // Load libraries on component mount if starting in search mode
    import {onMount} from "svelte";

    onMount(() => {
        if (inputMode === "search") {
            loadLibraries();
        }
    });

    // Show different content based on session state
    $: showCompletedMessage = $session.step === "completed";
</script>

<div class="session-start">
    {#if showCompletedMessage}
        <div class="success-card">
            <div class="card-body text-center">
                <div class="success-icon">
                    <Check size="72" color="var(--success)"/>
                </div>

                <h2 class="text-success">Chapters Submitted!</h2>
                <p>
                    Your audiobook chapters have been successfully saved to
                    Audiobookshelf.
                </p>
                <div class="actions">
                    <button
                            class="btn btn-verify"
                            on:click={() => {
              session.deleteSession();
              clearAllState();
              inputMode = "search";
            }}
                    >
                        New Audiobook
                    </button>
                </div>
            </div>
        </div>
    {:else}
        <div class="start-content">
            <div class="header-area">
                <div class="header-section">
                    <div class="title-row">
                        <div class="logo-container">
                            <Icon
                                    name="achew-logo"
                                    size="86"
                                    color="linear-gradient(135deg, var(--accent-gradient-start) 0%, var(--accent-gradient-end) 100%)"
                            />
                        </div>
                        <div class="title-stack">
                            <h2 class="main-title">achew</h2>
                            <p class="subtitle">
                                <strong>a</strong>udiobook <strong>ch</strong>apter
                                <strong>e</strong>xtraction <strong>w</strong>izard
                            </p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Mode Selector -->
            <div class="mode-selector">
                <button
                        class="mode-btn {inputMode === 'search' ? 'active' : ''}"
                        on:click={switchToSearchMode}
                        type="button"
                >
                    Search
                </button>
                <button
                        class="mode-btn {inputMode === 'itemId' ? 'active' : ''}"
                        on:click={switchToItemIdMode}
                        type="button"
                >
                    Item ID
                </button>
                <button
                        class="mode-btn {inputMode === 'missingChapters' ? 'active' : ''}"
                        on:click={switchToMissingChaptersMode}
                        type="button"
                >
                    Missing Chapters
                </button>
            </div>

            {#if inputMode === "itemId"}
                <!-- Item ID Input Form -->
                <form on:submit|preventDefault={handleSubmit} class="item-form">
                    <div class="form-group">
                        <div class="input-container">
                            <input
                                    id="itemId"
                                    type="text"
                                    class="form-control {validationError
                  ? 'is-invalid'
                  : ''} {isDebouncing ? 'is-debouncing' : ''} {isValidating
                  ? 'is-validating'
                  : ''}"
                                    bind:value={itemId}
                                    bind:this={itemIdInput}
                                    on:keydown={handleKeyDown}
                                    on:paste={handlePaste}
                                    placeholder="Enter an Audiobookshelf item ID"
                                    disabled={$session.loading}
                                    autocomplete="off"
                                    spellcheck="false"
                            />
                            <button
                                    type="button"
                                    class="help-icon"
                                    on:click={() => (showHelp = !showHelp)}
                                    on:mouseenter={() => (showHelp = true)}
                                    on:mouseleave={() => (showHelp = false)}
                                    aria-label="Where to find the Item ID"
                            >
                                <CircleQuestionMark size="16" color="var(--text-muted)"/>
                            </button>

                            {#if showHelp}
                                <div class="help-tooltip">
                                    <div class="help-tooltip-content">
                                        <p>
                                            When viewing a book in Audiobookshelf, the Item ID can be
                                            found in the URL after <em>"/item/"</em>
                                        </p>
                                        <code
                                        >https://your-abs-server.com/library/item/<span
                                                class="url-id-highlight"
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
                                <div slot="actions" class="search-result-actions">
                                    <button
                                            type="submit"
                                            class="btn btn-verify start-btn"
                                            disabled={$session.loading}
                                            on:click={handleSubmit}
                                    >
                                        {#if isValidating || $session.loading}
                                            <span class="btn-spinner"></span>
                                            Processing...
                                        {:else}
                                            Start
                                            <ArrowRight size="14"/>
                                        {/if}
                                    </button>
                                </div>
                            </AudiobookCard>
                        </div>
                    </div>
                {/if}
            {:else if inputMode === "search"}
                <!-- Search Interface -->
                <div class="search-form">
                    <div class="search-input-container">
                        <!-- Library Dropdown -->
                        <select
                                class="library-select"
                                bind:value={selectedLibrary}
                                on:change={handleLibraryChange}
                                disabled={isLoadingLibraries || $session.loading}
                        >
                            {#if isLoadingLibraries}
                                <option>Loading libraries...</option>
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
                                class="search-input {searchError ? 'is-invalid' : ''} {isSearching
                ? 'is-searching'
                : ''}"
                                bind:value={searchQuery}
                                bind:this={searchInput}
                                placeholder="Search for audiobooks..."
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
                            {#each searchResults as book}
                                <AudiobookCard
                                        title={book.media.metadata.title}
                                        duration={book.duration}
                                        coverImageUrl={book.media.coverPath}
                                        fileCount={book.media.audioFiles?.length || 0}
                                        size="compact"
                                >
                                    <div slot="actions" class="search-result-actions">
                                        <button
                                                class="btn btn-verify start-btn"
                                                disabled={$session.loading}
                                                on:click={() => startSessionFromBook(book)}
                                        >
                                            {#if isValidating || $session.loading}
                                                <span class="btn-spinner"></span>
                                                Processing...
                                            {:else}
                                                Start
                                                <ArrowRight size="14"/>
                                            {/if}
                                        </button>
                                    </div>
                                </AudiobookCard>
                            {/each}
                        </div>
                    </div>
                {/if}
            {:else if inputMode === "missingChapters"}
                <div class="missing-chapters-form">
                    <div class="missing-chapters-controls">
                        <!-- Library Selection -->
                        <div class="library-controls">
                            <select
                                    class="library-select"
                                    bind:value={missingChaptersLibrary}
                                    on:change={handleMissingChaptersLibraryChange}
                                    disabled={isLoadingLibraries || isFetchingMissingChapters || $session.loading}
                            >
                                {#if isLoadingLibraries}
                                    <option>Loading libraries...</option>
                                {:else if libraries.length === 0}
                                    <option>No libraries found</option>
                                {:else}
                                    {#each libraries as library}
                                        <option value={library}>{library.name}</option>
                                    {/each}
                                {/if}
                            </select>
                            
                            <button
                                    class="refresh-btn"
                                    on:click={refreshMissingChaptersCache}
                                    disabled={!missingChaptersLibrary || isRefreshingCache || $session.loading}
                                    title="Refresh library cache"
                            >
                                <RefreshCw size="16" class={isRefreshingCache ? 'spinning' : ''}/>
                            </button>
                        </div>

                        <!-- Chapter Count Filter -->
                        <div class="chapter-filter">
                            <label for="maxChapters" class="filter-label">
                                Show books with
                            </label>
                            <input
                                    id="maxChapters"
                                    type="number"
                                    class="chapter-input"
                                    bind:value={maxChapters}
                                    min="0"
                                    max="999"
                                    disabled={isFetchingMissingChapters || $session.loading}
                            />
                            <span class="filter-label">chapter(s) or fewer</span>
                        </div>
                    </div>

                    {#if missingChaptersError}
                        <div class="invalid-feedback">
                            {missingChaptersError}
                        </div>
                    {/if}
                </div>

                <!-- Missing Chapters Results -->
                {#if isFetchingMissingChapters}
                    <div class="loading-indicator">
                        <span class="loading-spinner"></span>
                        Loading books...
                    </div>
                {:else if filteredMissingChaptersBooks.length > 0}
                    <div class="missing-chapters-results">
                        <div class="results-header">
                            <p class="results-count">
                                Found {filteredMissingChaptersBooks.length} book{filteredMissingChaptersBooks.length === 1 ? '' : 's'}
                                with {maxChapters} chapter{maxChapters === 1 ? '' : 's'} or fewer
                            </p>
                        </div>
                        <div class="results-list">
                            {#each filteredMissingChaptersBooks as book}
                                <AudiobookCard
                                        title={book.media.metadata.title}
                                        duration={book.duration}
                                        coverImageUrl={book.media.coverPath}
                                        fileCount={book.media.numAudioFiles || 0}
                                        size="compact"
                                >
                                    <div slot="metadata" class="chapter-info">
                                        {book.media.numChapters || 'No'} chapter{book.media.numChapters === 1 ? '' : 's'}
                                    </div>
                                    <div slot="actions" class="search-result-actions">
                                        <button
                                                class="btn btn-verify start-btn"
                                                disabled={$session.loading}
                                                on:click={() => startSessionFromBook(book)}
                                        >
                                            {#if isValidating || $session.loading}
                                                <span class="btn-spinner"></span>
                                                Processing...
                                            {:else}
                                                Start
                                                <ArrowRight size="14"/>
                                            {/if}
                                        </button>
                                    </div>
                                </AudiobookCard>
                            {/each}
                        </div>
                    </div>
                {:else if missingChaptersBooks.length > 0}
                    <div class="no-results">
                        <p>No books found with {maxChapters} chapter{maxChapters === 1 ? '' : 's'} or fewer.</p>
                        <p class="hint">Try increasing the chapter count or clicking the refresh button.</p>
                    </div>
                {/if}
            {/if}
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
        gap: 2rem;
    }

    .header-area {
        width: 100%;
        max-width: 600px;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .header-section {
        text-align: center;
        padding: 0 2rem 3rem 2rem;
        width: 100%;
    }

    .title-row {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 1rem;
        margin-bottom: 1rem;
    }

    .logo-container {
        margin-top: 0.5rem;
    }

    .title-stack {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 0;
    }

    .main-title {
        margin-top: -0.8rem;
        margin-bottom: -0.75rem;
        margin-left: 0.5rem;
        font-size: 5rem;
        font-weight: 100;
        color: var(--text-primary);
        letter-spacing: 0.12em;
    }

    .subtitle {
        margin: 0;
        color: var(--text-secondary);
        font-size: 0.95rem;
        font-weight: 200;
        white-space: nowrap;
    }

    .subtitle strong {
        font-weight: 700;
    }

    .success-card p {
        margin-bottom: 4rem;
        max-width: 360px;
        margin-left: auto;
        margin-right: auto;
    }

    .success-card .card-body {
        padding: 3rem;
    }

    .item-form {
        width: 100%;
        max-width: 600px;
        text-align: center;
    }

    .form-group {
        margin-bottom: 0.5rem;
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
        background: linear-gradient(
                135deg,
                var(--verify-gradient-start) 0%,
                var(--verify-gradient-end) 100%
        );
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

        .title-stack {
            align-items: center;
        }

        .main-title {
            font-size: 3.75rem;
        }

        .subtitle {
            font-size: 0.75rem;
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

    /* Missing Chapters Styles */
    .missing-chapters-form {
        width: 100%;
        max-width: 600px;
        text-align: center;
    }

    .missing-chapters-controls {
        display: flex;
        flex-direction: column;
        gap: 1rem;
    }

    .library-controls {
        display: flex;
        align-items: center;
        gap: 0.25rem;
        justify-content: center;
    }

    .library-controls .library-select {
        flex: 1;
        max-width: 300px;
        background: var(--bg-tertiary);
        border: 1px solid var(--border-color);
        padding: 0.75rem 1rem;
        color: var(--text-primary);
        font-weight: 500;
        border-radius: 8px;
        outline: none;
    }

    .refresh-btn {
        background: transparent;
        border: none;
        border-radius: 100em;
        padding: 0.75rem;
        color: var(--text-muted);
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.2s ease;
    }

    .refresh-btn:hover:not(:disabled) {
        background: var(--hover-bg);
        color: var(--text-primary);
    }

    .refresh-btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    .refresh-btn :global(.spinning) {
        animation: spin 1s linear infinite;
    }

    @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }

    .chapter-filter {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.5rem;
        flex-wrap: wrap;
    }

    .filter-label {
        color: var(--text-primary);
        font-weight: 500;
        font-size: 0.95rem;
    }

    .chapter-input {
        background: var(--bg-primary);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        padding: 0.5rem 0.75rem;
        color: var(--text-primary);
        font-size: 0.95rem;
        text-align: center;
        width: 80px;
        outline: none;
        transition: border-color 0.2s ease;
    }

    .chapter-input:focus {
        border-color: var(--primary);
    }

    .chapter-input:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }

    .missing-chapters-results {
        width: 100%;
        max-width: 600px;
        margin-top: 0;
    }

    .results-header {
        margin-bottom: 1rem;
        text-align: center;
    }

    .results-count {
        color: var(--text-secondary);
        font-size: 0.9rem;
        margin: 0;
        font-weight: 500;
    }

    .chapter-info {
        color: var(--text-secondary);
        font-size: 0.8rem;
        font-weight: 500;
        margin-top: 0.25rem;
    }

    .loading-indicator {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.5rem;
        color: var(--text-secondary);
        font-size: 0.9rem;
        padding: 2rem;
    }

    .loading-spinner {
        width: 16px;
        height: 16px;
        border: 2px solid var(--border-color);
        border-top: 2px solid var(--primary);
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }

    .no-results {
        text-align: center;
        padding: 2rem;
        color: var(--text-secondary);
    }

    .no-results p {
        margin: 0.5rem 0;
    }

    .no-results .hint {
        font-size: 0.85rem;
        opacity: 0.8;
    }

    /* Missing Chapters Responsive Design */
    @media (max-width: 768px) {
        .chapter-filter {
            text-align: center;
            line-height: 1.5;
        }

        .filter-label {
            font-size: 0.9rem;
        }

        .chapter-input {
            width: 70px;
            font-size: 0.9rem;
        }
    }

    @media (max-width: 480px) {
        .chapter-filter {
            gap: 0.4rem;
        }

        .filter-label {
            font-size: 0.85rem;
        }

        .chapter-input {
            width: 60px;
            padding: 0.4rem 0.6rem;
            font-size: 0.85rem;
        }
    }
</style>
