<script>
    import BarChart3 from '@lucide/svelte/icons/bar-chart-3';
    import CircleQuestionMark from '@lucide/svelte/icons/circle-question-mark';
    import Search from '@lucide/svelte/icons/search';
    import Trash2 from '@lucide/svelte/icons/trash-2';

    import {chapterSearch} from '../../stores/chapterSearch.js';
    import {hasEnabledRules} from './ruleUtils.js';
    import RuleEditor from './RuleEditor.svelte';
    import HelpDialog from './HelpDialog.svelte';

    let helpOpen = false;
    let clearingCache = false;
    let selectedLibraryId = null;

    $: libraries = $chapterSearch.libraries || [];
    $: rootRuleset = $chapterSearch.rootRuleset;
    $: selectedLibrary = libraries.find(lib => lib.id === selectedLibraryId) || null;
    $: canSearch = selectedLibrary && rootRuleset && hasEnabledRules(rootRuleset);

    // Auto-select last-used library, or first if unavailable
    $: if (libraries.length > 0 && !selectedLibraryId) {
        const savedId = localStorage.getItem('achew-last-library-id');
        const saved = savedId && libraries.some(l => l.id === savedId);
        selectedLibraryId = saved ? savedId : libraries[0].id;
    }

    // Persist library selection on change
    $: if (selectedLibraryId) {
        localStorage.setItem('achew-last-library-id', selectedLibraryId);
    }

    async function handleSearch() {
        if (!canSearch) return;
        chapterSearch.startSearch(selectedLibrary.id, selectedLibrary.name);
    }

    async function handleRulesetChange(newRuleset) {
        await chapterSearch.saveRuleset(newRuleset);
    }

    async function handleResetToDefaults() {
        try {
            await fetch('/api/chapter-search/ruleset/reset', {method: 'POST'});
        } catch (e) {
            console.error('Error resetting ruleset:', e);
        }
    }

    function handleStats() {
        if (!selectedLibrary) return;
        chapterSearch.startStats(selectedLibrary.id, selectedLibrary.name);
    }

    async function clearCache() {
        clearingCache = true;
        try {
            await chapterSearch.clearCache(selectedLibrary?.id || null);
        } finally {
            clearingCache = false;
        }
    }
</script>

<div class="landing-page">
    <!-- Header row -->
    <div class="header-row">
        <div class="library-row">
            <select
                class="library-select"
                bind:value={selectedLibraryId}
                disabled={libraries.length === 0}
            >
                {#if libraries.length === 0}
                    <option value={null}>Loading libraries…</option>
                {:else}
                    {#each libraries as lib}
                        <option value={lib.id}>{lib.name}</option>
                    {/each}
                {/if}
            </select>

            <button
                class="search-btn"
                on:click={handleSearch}
                disabled={!canSearch}
                title={!selectedLibrary ? 'Select a library' : !rootRuleset || !hasEnabledRules(rootRuleset) ? 'Enable at least one rule' : ''}
            >
                <Search size="15"/> Search
            </button>

            <button
                class="help-btn"
                on:click={() => helpOpen = true}
                aria-label="Help"
                title="How does Chapter Search work?"
            >
                <CircleQuestionMark size="18"/>
            </button>
        </div>
    </div>

    <!-- Rule editor -->
    {#if rootRuleset}
        <div class="editor-wrap">
            <RuleEditor
                ruleset={rootRuleset}
                isRoot={true}
                onchange={handleRulesetChange}
                onresetToDefaults={handleResetToDefaults}
            />
        </div>
    {:else}
        <div class="loading-rules">Loading rules…</div>
    {/if}

    <!-- Bottom controls -->
    <div class="cache-row">
        <button
            class="stats-btn"
            on:click={handleStats}
            disabled={!selectedLibrary}
            title="View library statistics"
        >
            <BarChart3 size="14"/>
            Library Stats
        </button>
        <button
            class="cache-btn"
            on:click={clearCache}
            disabled={clearingCache}
            title="Clear cached chapter data for this library. The next search will re-sync all books."
        >
            <Trash2 size="14"/>
            {clearingCache ? 'Clearing…' : `Clear Cache${selectedLibrary ? ` for ${selectedLibrary.name}` : ''}`}
        </button>
    </div>
</div>

<HelpDialog bind:open={helpOpen} />

<style>
    .landing-page {
        display: flex;
        flex-direction: column;
        gap: 1rem;
        width: 100%;
        padding-top: 0.5rem;
    }

    .header-row {
        display: flex;
        flex-direction: column;
        gap: 0.75rem;
    }

    .library-row {
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    .library-select {
        flex: 1;
        padding: 0.5rem 0.75rem;
        border: 1px solid var(--border-color);
        border-radius: 6px;
        background: var(--bg-secondary);
        color: var(--text-primary);
        font-size: 0.9375rem;
        min-width: 0;
    }

    .search-btn {
        display: flex;
        align-items: center;
        gap: 0.375rem;
        padding: 0.5rem 1rem;
        background: var(--primary);
        color: white;
        border: none;
        border-radius: 6px;
        font-size: 0.9375rem;
        cursor: pointer;
        white-space: nowrap;
        flex-shrink: 0;
    }

    .search-btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    .search-btn:not(:disabled):hover { opacity: 0.9; }

    .help-btn {
        background: none;
        border: none;
        cursor: pointer;
        color: var(--text-secondary);
        padding: 0.25rem;
        display: flex;
        align-items: center;
        flex-shrink: 0;
    }
    .help-btn:hover { color: var(--text-primary); }

    .editor-wrap {
        width: 100%;
    }

    .loading-rules {
        color: var(--text-secondary);
        font-size: 0.9rem;
        text-align: center;
        padding: 1rem;
    }

    .cache-row {
        display: flex;
        justify-content: space-between;
    }

    .stats-btn {
        display: flex;
        align-items: center;
        gap: 0.375rem;
        padding: 0.375rem 0.75rem;
        background: none;
        border: 1px solid var(--border-color);
        border-radius: 6px;
        color: var(--text-secondary);
        font-size: 0.8125rem;
        cursor: pointer;
    }
    .stats-btn:hover { color: var(--primary); border-color: var(--primary); }
    .stats-btn:disabled { opacity: 0.5; cursor: not-allowed; }

    .cache-btn {
        display: flex;
        align-items: center;
        gap: 0.375rem;
        padding: 0.375rem 0.75rem;
        background: none;
        border: 1px solid var(--border-color);
        border-radius: 6px;
        color: var(--text-secondary);
        font-size: 0.8125rem;
        cursor: pointer;
    }
    .cache-btn:hover { color: var(--danger); border-color: var(--danger); }
    .cache-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
