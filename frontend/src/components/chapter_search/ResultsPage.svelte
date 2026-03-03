<script>
    import {onMount} from 'svelte';
    import ArrowLeft from '@lucide/svelte/icons/arrow-left';
    import ArrowRight from '@lucide/svelte/icons/arrow-right';
    import RotateCw from '@lucide/svelte/icons/rotate-cw';
    import {chapterSearch} from '../../stores/chapterSearch.js';
    import {session} from '../../stores/session.js';
    import {autoRuleName, autoRuleSetName} from './ruleUtils.js';

    let panelsEl;
    let panelMaxHeight = '';

    function measurePanels() {
        if (!panelsEl) return;
        const top = panelsEl.getBoundingClientRect().top;
        panelMaxHeight = `${window.innerHeight - top - 44}px`;
    }

    onMount(() => {
        requestAnimationFrame(measurePanels);
        window.addEventListener('resize', measurePanels);
        return () => window.removeEventListener('resize', measurePanels);
    });

    $: results = $chapterSearch.results || [];
    $: count = $chapterSearch.count || 0;
    $: libraryName = $chapterSearch.libraryName;
    $: highlightedId = $chapterSearch.highlightedBookId;
    $: showIgnored = $chapterSearch.showIgnored;

    $: ignoredCount = results.filter(b => b.is_ignored).length;
    $: hasIgnored = ignoredCount > 0;

    $: visibleResults = showIgnored
        ? results
        : results.filter(b => !b.is_ignored);

    $: highlightedBook = results.find(b => b.id === highlightedId) || visibleResults[0] || null;

    function selectBook(bookId) {
        chapterSearch.setHighlightedBook(bookId);
    }

    function handleShowIgnoredChange(e) {
        chapterSearch.setShowIgnored(e.target.checked);
    }

    async function handleToggleIgnore() {
        if (!highlightedBook) return;
        await chapterSearch.toggleIgnore(highlightedBook.id);
    }

    async function handleStart() {
        if (!highlightedBook) return;
        try {
            await session.createSession(highlightedBook.id);
        } catch (e) {
            console.error('Failed to start session:', e);
        }
    }

    function formatTime(seconds) {
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = Math.floor(seconds % 60);
        if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
        return `${m}:${String(s).padStart(2, '0')}`;
    }

    function collectMatchedLines(ruleset, ids, depth) {
        const lines = [];
        const indent = '  '.repeat(depth);
        for (const item of (ruleset.items || [])) {
            if (Array.isArray(item.items)) {
                const childLines = collectMatchedLines(item, ids, depth + 1);
                if (childLines.length > 0) {
                    lines.push(`${indent}• ${autoRuleSetName(item)}:`);
                    lines.push(...childLines);
                }
            } else if (ids.has(item.id)) {
                lines.push(`${indent}• ${autoRuleName(item)}`);
            }
        }
        return lines;
    }

    function buildTooltip(book) {
        const ids = new Set(book.matched_rule_ids || []);
        if (ids.size === 0) return 'No rules matched';
        const rootRuleset = $chapterSearch.rootRuleset;
        if (!rootRuleset) return `${ids.size} rule${ids.size === 1 ? '' : 's'} matched`;
        const lines = collectMatchedLines(rootRuleset, ids, 0);
        return lines.length > 0 ? `Matched rules:\n${lines.join('\n')}` : `${ids.size} rule${ids.size === 1 ? '' : 's'} matched`;
    }

    function coverUrl(book) {
        if (!book.has_cover) return null;
        return `/api/audiobookshelf/covers/${book.id}`;
    }
</script>

<div class="results-page">
    <!-- Top bar -->
    <div class="top-bar">
        <button class="back-btn" on:click={() => chapterSearch.backToLanding()}>
            <ArrowLeft size="16"/> Back
        </button>
        <div class="count-row">
            <span class="result-count">
                {count} book{count === 1 ? '' : 's'} matched
                {#if libraryName}<span class="library-name">in {libraryName}</span>{/if}
            </span>
            <button
                class="refresh-btn"
                on:click={() => chapterSearch.refreshResults()}
                title="Re-sync these books from Audiobookshelf and re-run the search"
                aria-label="Refresh results"
            >
                <RotateCw size="12"/>
            </button>
        </div>
        {#if hasIgnored}
            <label class="show-ignored">
                <input
                    type="checkbox"
                    checked={showIgnored}
                    on:change={handleShowIgnoredChange}
                />
                Show {ignoredCount} ignored book{ignoredCount === 1 ? '' : 's'}
            </label>
        {/if}
    </div>

    <!-- Main two-panel layout -->
    <div class="panels" bind:this={panelsEl} style={panelMaxHeight ? `--panel-max-h: ${panelMaxHeight}` : ''}>
        <!-- Left panel: book list -->
        <div class="left-panel">

            {#if visibleResults.length === 0}
                <div class="empty-state">
                    {#if results.length > 0}
                        <p>All results are hidden.</p>
                        <p class="hint">Check "Show ignored books" to see them.</p>
                    {:else}
                        <p>No books matched your rules.</p>
                    {/if}
                </div>
            {:else}
                <div class="book-list">
                    {#each visibleResults as book (book.id)}
                        <!-- svelte-ignore a11y-click-events-have-key-events -->
                        <!-- svelte-ignore a11y-no-static-element-interactions -->
                        <div
                            class="book-item"
                            class:highlighted={book.id === highlightedId}
                            class:is-ignored={book.is_ignored}
                            on:click={() => selectBook(book.id)}
                        >
                            <div class="book-cover">
                                {#if coverUrl(book)}
                                    <img src={coverUrl(book)} alt="" loading="lazy" />
                                {:else}
                                    <div class="cover-placeholder"></div>
                                {/if}
                            </div>
                            <div class="book-meta">
                                <span class="book-title">{book.name}</span>
                                <span class="book-sub">
                                    {[book.author, book.series].filter(Boolean).join(' • ') || '—'}
                                </span>
                            </div>
                        </div>
                    {/each}
                </div>
            {/if}
        </div>

        <!-- Right panel: chapter details -->
        <div class="right-panel">
            {#if highlightedBook}
                <div class="detail-header">
                    <strong class="detail-title">{highlightedBook.name}</strong>
                    <span class="chapter-count">
                        {highlightedBook.chapters?.length || 0} chapter{highlightedBook.chapters?.length === 1 ? '' : 's'}
                    </span>
                </div>

                <div class="chapter-list">
                    {#if (highlightedBook.chapters || []).length === 0}
                        <div class="empty-state"><p>No chapter data available.</p></div>
                    {:else}
                        <div class="chapter-header-row">
                            <span class="col-time">Time</span>
                            <span class="col-title">Title</span>
                        </div>
                        {#each highlightedBook.chapters as ch, i}
                            <div class="chapter-row">
                                <span class="col-time">{formatTime(ch.start_time)}</span>
                                <span class="col-title">{ch.title || `Chapter ${i + 1}`}</span>
                            </div>
                        {/each}
                    {/if}
                </div>

                <div class="detail-actions">
                    <pre class="matched-rules">{buildTooltip(highlightedBook)}</pre>
                    <div class="action-buttons">
                        <button
                            class="btn btn-secondary ignore-btn"
                            on:click={handleToggleIgnore}
                        >
                            {highlightedBook.is_ignored ? 'Unignore' : 'Ignore'}
                        </button>
                        <button
                            class="btn start-btn"
                            on:click={handleStart}
                            disabled={$session.loading}
                        >
                            {$session.loading ? 'Starting…' : 'Start'}
                            {#if !$session.loading}<ArrowRight size="14"/>{/if}
                        </button>
                    </div>
                </div>
            {:else}
                <div class="empty-state"><p>Select a book to see its chapters.</p></div>
            {/if}
        </div>
    </div>
</div>

<style>
    .results-page {
        display: flex;
        flex-direction: column;
        gap: 0.75rem;
        width: 100%;
        height: 100%;
    }

    .top-bar {
        display: flex;
        align-items: center;
        gap: 1rem;
    }

    .back-btn {
        display: flex;
        align-items: center;
        gap: 0.375rem;
        padding: 0.375rem 0.75rem;
        background: var(--bg-secondary);
        border: 1px solid var(--border-color);
        border-radius: 6px;
        color: var(--text-secondary);
        font-size: 0.875rem;
        cursor: pointer;
        flex-shrink: 0;
    }
    .back-btn:hover { color: var(--text-primary); }

    .result-count {
        font-size: 0.9375rem;
        font-weight: 600;
        color: var(--text-primary);
    }

    .library-name {
        font-weight: 400;
        color: var(--text-secondary);
    }

    .panels {
        display: flex;
        gap: 1rem;
        align-items: flex-start;
    }

    /* Left panel */
    .left-panel {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
        width: 280px;
        flex-shrink: 0;
        max-height: var(--panel-max-h, calc(100vh - 8rem));
    }

    .count-row {
        display: flex;
        align-items: center;
        gap: 0.25rem;
    }

    .refresh-btn {
        background: none;
        border: none;
        cursor: pointer;
        color: var(--text-secondary);
        padding: 0.125rem;
        display: flex;
        align-items: center;
        flex-shrink: 0;
    }
    .refresh-btn:hover { color: var(--text-primary); }

    .show-ignored {
        display: flex;
        align-items: center;
        gap: 0.375rem;
        font-size: 0.8125rem;
        color: var(--text-secondary);
        cursor: pointer;
        margin-left: auto;
    }

    .book-list {
        flex: 1;
        min-height: 0;
        overflow-y: auto;
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
        border: 1px solid var(--border-color);
        border-radius: 8px;
        padding: 0.25rem;
    }

    .book-item {
        display: flex;
        align-items: center;
        gap: 0.625rem;
        padding: 0.5rem 0.625rem;
        border-radius: 6px;
        cursor: pointer;
        transition: background 0.1s;
    }

    .book-item:hover { background: var(--bg-secondary); }
    .book-item.highlighted { background: var(--bg-tertiary); }
    .book-item.is-ignored { opacity: 0.5; }

    .book-cover {
        width: 40px;
        height: 40px;
        flex-shrink: 0;
        border-radius: 4px;
        overflow: hidden;
    }

    .book-cover img {
        width: 100%;
        height: 100%;
        object-fit: cover;
    }

    .cover-placeholder {
        width: 100%;
        height: 100%;
        background: var(--bg-tertiary);
    }

    .book-meta {
        flex: 1;
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: 0.1rem;
    }

    .book-title {
        font-size: 0.875rem;
        font-weight: 500;
        color: var(--text-primary);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .book-sub {
        font-size: 0.75rem;
        color: var(--text-secondary);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    /* Right panel */
    .right-panel {
        flex: 1;
        display: flex;
        flex-direction: column;
        min-width: 0;
        border: 1px solid var(--border-color);
        border-radius: 8px;
        overflow: hidden;
        position: sticky;
        top: 0.75rem;
        max-height: var(--panel-max-h, calc(100vh - 8rem));
    }

    .detail-header {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        padding: 0.75rem 1rem;
        border-bottom: 1px solid var(--border-color);
        background: var(--bg-secondary);
        flex-shrink: 0;
    }

    .detail-title {
        font-size: 0.9375rem;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        flex: 1;
        min-width: 0;
    }

    .chapter-count {
        font-size: 0.8125rem;
        color: var(--text-secondary);
        flex-shrink: 0;
        margin-left: 0.75rem;
    }

    .chapter-list {
        flex: 1;
        overflow-y: auto;
        font-size: 0.875rem;
    }

    .chapter-header-row, .chapter-row {
        display: flex;
        gap: 1rem;
        padding: 0.4rem 1rem;
    }

    .chapter-header-row {
        position: sticky;
        top: 0;
        background: var(--bg-secondary);
        border-bottom: 1px solid var(--border-color);
        font-weight: 600;
        font-size: 0.8125rem;
        color: var(--text-secondary);
    }

    .chapter-row:nth-child(even) { background: var(--bg-secondary); }
    .chapter-row:hover { background: transparent; }
    .chapter-row:nth-child(even):hover { background: var(--bg-secondary); }

    .col-time {
        font-size: 0.8125rem;
        color: var(--text-secondary);
        font-family: monospace;
        flex-shrink: 0;
        width: 60px;
    }

    .col-title {
        flex: 1;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .detail-actions {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 0.75rem 1rem;
        border-top: 1px solid var(--border-color);
        background: var(--bg-secondary);
        flex-shrink: 0;
    }

    .matched-rules {
        flex: 1;
        min-width: 0;
        margin: 0;
        font-size: 0.6875rem;
        font-family: inherit;
        color: var(--text-secondary);
        white-space: pre-wrap;
        overflow: hidden;
    }

    .action-buttons {
        display: flex;
        gap: 0.5rem;
        flex-shrink: 0;
    }

    .empty-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        flex: 1;
        padding: 2rem;
        color: var(--text-secondary);
        text-align: center;
        font-size: 0.9rem;
    }

    .empty-state .hint { font-size: 0.8125rem; margin-top: 0.25rem; }

    .start-btn {
        display: inline-flex;
        align-items: center;
        gap: 0.375rem;
        background: linear-gradient(135deg, var(--verify-gradient-start) 0%, var(--verify-gradient-end) 100%);
        color: white;
        border: 0.075rem solid transparent;
        font-weight: 600;
    }
    .start-btn:hover:not(:disabled) {
        background: linear-gradient(135deg, var(--verify-gradient-start-hover), var(--verify-gradient-end-hover));
    }
</style>
