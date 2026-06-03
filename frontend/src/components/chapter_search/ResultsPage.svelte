<script lang="ts">
  import { onMount } from 'svelte';
  import { get } from 'svelte/store';
  import ArrowLeft from '@lucide/svelte/icons/arrow-left';
  import ArrowRight from '@lucide/svelte/icons/arrow-right';
  import RotateCw from '@lucide/svelte/icons/rotate-cw';
  import { tooltip } from '../../actions/tooltip';
  import { chapterSearch } from '../../stores/chapterSearch';
  import { session } from '../../stores/session';
  import { formatDuration } from '../../utils/format';
  import SeriesPill from '../SeriesPill.svelte';
  import { autoRuleName, autoRuleSetName } from './ruleUtils';
  import type { Rule, RuleSet } from '../../types/rules';

  interface ResultChapter {
    start_time: number;
    title?: string;
  }

  interface ResultBook {
    id: string;
    name: string;
    author?: string;
    series?: string;
    series_sequence?: string;
    subtitle?: string;
    duration?: number;
    num_audio_files?: number;
    has_cover?: boolean;
    is_ignored: boolean;
    chapters?: ResultChapter[];
    matched_rule_ids?: string[];
  }

  let panelsEl: HTMLDivElement | undefined = $state();
  let bookListEl: HTMLDivElement | undefined = $state();
  let panelMaxHeight = $state('');

  function measurePanels() {
    if (!panelsEl) return;
    const top = panelsEl.getBoundingClientRect().top;
    panelMaxHeight = `${window.innerHeight - top - 44}px`;
  }

  function navigateList(delta: number) {
    if (visibleResults.length === 0) return;
    const currentId = highlightedBook?.id;
    const currentIndex = currentId ? visibleResults.findIndex((b) => b.id === currentId) : -1;
    const nextIndex =
      currentIndex === -1
        ? delta > 0
          ? 0
          : visibleResults.length - 1
        : Math.min(Math.max(currentIndex + delta, 0), visibleResults.length - 1);
    const next = visibleResults[nextIndex];
    if (next) {
      selectBook(next.id);
      bookListEl?.querySelector(`[data-book-id="${CSS.escape(next.id)}"]`)?.scrollIntoView({ block: 'nearest' });
    }
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    const target = e.target as HTMLElement | null;
    if (target && (/^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName) || target.isContentEditable)) return;
    e.preventDefault();
    navigateList(e.key === 'ArrowDown' ? 1 : -1);
  }

  onMount(() => {
    requestAnimationFrame(measurePanels);
    window.addEventListener('resize', measurePanels);
    window.addEventListener('keydown', handleKeydown);
    return () => {
      window.removeEventListener('resize', measurePanels);
      window.removeEventListener('keydown', handleKeydown);
    };
  });

  let results = $derived(($chapterSearch.results as ResultBook[] | undefined) || []);
  let count = $derived($chapterSearch.count || 0);
  let libraryName = $derived($chapterSearch.libraryName);
  let highlightedId = $derived($chapterSearch.highlightedBookId);
  let showIgnored = $derived($chapterSearch.showIgnored);

  let ignoredCount = $derived(results.filter((b) => b.is_ignored).length);
  let hasIgnored = $derived(ignoredCount > 0);

  let visibleResults = $derived(showIgnored ? results : results.filter((b) => !b.is_ignored));

  let highlightedBook = $derived(results.find((b) => b.id === highlightedId) || visibleResults[0] || null);

  function selectBook(bookId: string) {
    chapterSearch.setHighlightedBook(bookId);
  }

  function handleShowIgnoredChange(e: Event) {
    const target = e.target as HTMLInputElement;
    chapterSearch.setShowIgnored(target.checked);
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

  function formatTime(seconds: number): string {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    return `${m}:${String(s).padStart(2, '0')}`;
  }

  function collectMatchedLines(ruleset: RuleSet, ids: Set<string>, depth: number): string[] {
    const lines: string[] = [];
    const indent = '  '.repeat(depth);
    for (const item of ruleset.items || []) {
      if (Array.isArray((item as RuleSet).items)) {
        const childLines = collectMatchedLines(item as RuleSet, ids, depth + 1);
        if (childLines.length > 0) {
          lines.push(`${indent}• ${autoRuleSetName(item as RuleSet)}:`);
          lines.push(...childLines);
        }
      } else if (ids.has(item.id)) {
        lines.push(`${indent}• ${autoRuleName(item as Rule)}`);
      }
    }
    return lines;
  }

  function buildTooltip(book: ResultBook): string {
    const ids = new Set(book.matched_rule_ids || []);
    if (ids.size === 0) return 'No rules matched';
    const rootRuleset = get(chapterSearch).rootRuleset;
    if (!rootRuleset) return `${ids.size} rule${ids.size === 1 ? '' : 's'} matched`;
    const lines = collectMatchedLines(rootRuleset, ids, 0);
    return lines.length > 0
      ? `Matched rules:\n${lines.join('\n')}`
      : `${ids.size} rule${ids.size === 1 ? '' : 's'} matched`;
  }

  function coverUrl(book: ResultBook): string | null {
    if (!book.has_cover) return null;
    return `/api/audiobookshelf/covers/${book.id}`;
  }
</script>

<div class="results-page">
  <!-- Top bar -->
  <div class="top-bar">
    <button class="back-btn" onclick={() => chapterSearch.backToLanding()}>
      <ArrowLeft size="16" /> Back
    </button>
    <div class="count-row">
      <span class="result-count">
        {count} book{count === 1 ? '' : 's'} matched
        {#if libraryName}<span class="library-name">in {libraryName}</span>{/if}
      </span>
      <button
        class="refresh-btn"
        onclick={() => chapterSearch.refreshResults()}
        use:tooltip={'Re-sync these books from Audiobookshelf and re-run the search'}
        aria-label="Refresh results"
      >
        <RotateCw size="12" />
      </button>
    </div>
    {#if hasIgnored}
      <label class="show-ignored">
        <input type="checkbox" checked={showIgnored} onchange={handleShowIgnoredChange} />
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
        <div class="book-list" bind:this={bookListEl}>
          {#each visibleResults as book (book.id)}
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <div
              class="book-item"
              class:highlighted={book.id === highlightedId}
              class:is-ignored={book.is_ignored}
              data-book-id={book.id}
              onclick={() => selectBook(book.id)}
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
          <div class="detail-cover">
            {#if coverUrl(highlightedBook)}
              <img src={coverUrl(highlightedBook)} alt="" loading="lazy" />
            {:else}
              <div class="cover-placeholder"></div>
            {/if}
          </div>
          <div class="detail-info">
            <div class="detail-title-row">
              <strong class="detail-title" title={highlightedBook.name}>{highlightedBook.name}</strong>
              <span class="chapter-count">
                {highlightedBook.chapters?.length || 0} Chapter{highlightedBook.chapters?.length === 1 ? '' : 's'}
              </span>
            </div>
            {#if highlightedBook.subtitle}
              <span class="detail-subtitle" title={highlightedBook.subtitle}>{highlightedBook.subtitle}</span>
            {/if}
            <div class="detail-pills">
              {#if highlightedBook.duration}
                <span class="detail-pill">{formatDuration(highlightedBook.duration)}</span>
              {/if}
              {#if (highlightedBook.num_audio_files ?? 0) > 1}
                <span class="detail-pill">{highlightedBook.num_audio_files} files</span>
              {/if}
              {#if highlightedBook.series}
                <SeriesPill name={highlightedBook.series} sequence={highlightedBook.series_sequence} themed={false} />
              {/if}
            </div>
          </div>
        </div>

        <div class="chapter-list">
          {#if (highlightedBook.chapters || []).length === 0}
            <div class="empty-state"><p>No chapter data available.</p></div>
          {:else}
            {#each highlightedBook.chapters ?? [] as ch}
              <div class="chapter-row">
                <span class="col-time">{formatTime(ch.start_time)}</span>
                <span class="col-title">{ch.title || `[No Title]`}</span>
              </div>
            {/each}
          {/if}
        </div>

        <div class="detail-actions">
          <pre class="matched-rules">{buildTooltip(highlightedBook)}</pre>
          <div class="action-buttons">
            <button class="btn btn-secondary ignore-btn" onclick={handleToggleIgnore}>
              {highlightedBook.is_ignored ? 'Unignore' : 'Ignore'}
            </button>
            <button class="btn start-btn" onclick={handleStart} disabled={$session.loading}>
              {$session.loading ? 'Starting…' : 'Start'}
              {#if !$session.loading}<ArrowRight size="14" />{/if}
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
  .back-btn:hover {
    color: var(--text-primary);
  }

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
  .refresh-btn:hover {
    color: var(--text-primary);
  }

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

  .book-item:hover {
    background: var(--bg-secondary);
  }
  .book-item.highlighted {
    background: var(--bg-tertiary);
  }
  .book-item.is-ignored {
    opacity: 0.5;
  }

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
    align-items: flex-start;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--border-color);
    background: var(--bg-secondary);
    flex-shrink: 0;
  }

  .detail-cover {
    width: 72px;
    height: 72px;
    flex-shrink: 0;
    border-radius: 4px;
    overflow: hidden;
  }

  .detail-cover img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .detail-info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }

  .detail-title-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 0.75rem;
  }

  .detail-title {
    font-size: 0.9375rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
    min-width: 0;
    line-height: 1;
  }

  .chapter-count {
    font-size: 0.75rem;
    color: var(--text-secondary);
    flex-shrink: 0;
  }

  .detail-subtitle {
    font-size: 0.8125rem;
    color: var(--text-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .detail-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 0.375rem;
    align-items: center;
    margin-top: 0.25rem;
  }

  .detail-pill {
    padding: 0.2rem 0.45rem;
    border-radius: 100px;
    font-size: 0.7rem;
    font-weight: 500;
    color: var(--text-primary);
    border: 1px solid var(--pill-border);
    white-space: nowrap;
  }

  .chapter-list {
    flex: 1;
    overflow-y: auto;
    font-size: 0.875rem;
  }

  .chapter-row {
    display: flex;
    gap: 1rem;
    padding: 0.4rem 1rem;
  }

  .chapter-row:nth-child(even) {
    background: var(--bg-secondary);
  }
  .chapter-row:hover {
    background: transparent;
  }
  .chapter-row:nth-child(even):hover {
    background: var(--bg-secondary);
  }

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
    padding: 0.1rem 0.3rem 0.1rem 0.3rem;
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

  .empty-state .hint {
    font-size: 0.8125rem;
    margin-top: 0.25rem;
  }

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
