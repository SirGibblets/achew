<script>
    import ChevronDown from "@lucide/svelte/icons/chevron-down";

    export let titleSources = [];
    export let onAddSource;

    $: nonEmptyTitleSources = titleSources.filter(s => s.type !== 'custom' || s.titles?.length > 0);

    let expanded = false;

    function sourceLabel(s) {
        return s.metadata?.File || s.name;
    }
</script>

<div class="source-footer">
    {#if nonEmptyTitleSources.length > 0}
        <div class="collapsible-section">
            <button
                class="collapsible-toggle"
                type="button"
                on:click={() => expanded = !expanded}
            >
                {nonEmptyTitleSources.length} title-only source{nonEmptyTitleSources.length === 1 ? '' : 's'}
                <span class="chevron" class:expanded>
                    <ChevronDown size="12"/>
                </span>
            </button>

            {#if expanded}
                <div class="collapsible-panel">
                    <p class="title-sources-note">The following sources do not include timestamps, but can be used later when editing titles:</p>
                    <ul class="title-sources-list">
                        {#each nonEmptyTitleSources as s}
                            <li>{sourceLabel(s)}</li>
                        {/each}
                    </ul>
                </div>
            {/if}
        </div>
    {/if}
    <button class="add-source-link" on:click={onAddSource}>+ Add Source</button>
</div>

<style>
    .source-footer {
        display: flex;
        flex-direction: column;
        align-items: center;
    }

    .add-source-link {
        background: none;
        border: none;
        cursor: pointer;
        color: var(--primary-color);
        font-size: 0.875rem;
        padding: 0;
    }

    .add-source-link:hover { opacity: 0.8; }

    .collapsible-section {
        display: flex;
        flex-direction: column;
        align-items: center;
        margin: -0.5rem 0 0.75rem 0;
    }

    .collapsible-toggle {
        background: none;
        border: none;
        color: var(--text-muted);
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.8rem;
        padding: 0.25rem 0;
        transition: color 0.2s ease;
    }

    .collapsible-toggle:hover {
        color: var(--text-primary);
    }

    .collapsible-toggle .chevron {
        transition: transform 0.2s ease;
        display: flex;
        align-items: center;
    }

    .collapsible-toggle .chevron.expanded {
        transform: rotate(180deg);
    }

    .collapsible-panel {
        padding: 0.5rem 0 0;
        text-align: left;
    }

    .title-sources-note {
        margin: 0 0 0.25rem;
        font-size: 0.8rem;
        color: var(--text-muted);
    }

    .title-sources-list {
        margin: 0;
        padding-left: 1.25rem;
        font-size: 0.8rem;
        color: var(--text-muted);
        list-style: disc;
    }

    .title-sources-list li {
        margin: 0.1rem 0;
    }
</style>
