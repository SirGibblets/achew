<script>
    import ChevronDown from "@lucide/svelte/icons/chevron-down";

    export let cueSources = [];
    export let titleSources = [];
    export let showCueSources = false;
    export let onAddSource;

    $: nonEmptyTitleSources = titleSources.filter(s => s.type !== 'custom' || s.titles?.length > 0);

    let expanded = false;
</script>

<div class="source-footer">
    {#if nonEmptyTitleSources.length > 0 || showCueSources}
        <div class="collapsible-section" class:compact={showCueSources}>
            <button
                class="collapsible-toggle"
                type="button"
                on:click={() => expanded = !expanded}
            >
                {#if showCueSources}
                    {cueSources.length === 0 ? "No" : cueSources.length} chapter source{cueSources.length === 1 ? '' : 's'} available for comparison
                {:else}
                    {nonEmptyTitleSources.length} title-only source{nonEmptyTitleSources.length === 1 ? '' : 's'}
                {/if}
                <span class="chevron" class:expanded>
                    <ChevronDown size="12"/>
                </span>
            </button>

            {#if expanded}
                <div class="collapsible-panel">
                    {#if showCueSources}
                        <p class="sources-note">
                            Chapter sources with timestamps can be used to compare against detected cues. This is helpful when determining which cues are most likely to be accurate chapter markers.
                        </p>
                        <p class="sources-note emphasized">
                            {#if cueSources.length > 0}
                                The following chapter sources include timestamps and can be used for comparison:
                            {:else}
                                No sources are currently available for cue comparison. Use the button below to add a source.
                            {/if}
                        </p>
                        {#if cueSources.length > 0}
                            <ul class="sources-list">
                                {#each cueSources as s}
                                    <li class="emphasized">{s.name}</li>
                                {/each}
                            </ul>
                        {/if}
                    {/if}

                    {#if nonEmptyTitleSources.length > 0}
                        <p class="sources-note">The following sources do not include timestamps, but can be used later when editing titles:</p>
                        <ul class="sources-list">
                            {#each nonEmptyTitleSources as s}
                                <li>{s.name}</li>
                            {/each}
                        </ul>
                    {/if}
                </div>

                {#if showCueSources}
                    <button class="add-source-link panel-button" on:click={onAddSource}>+ Add Chapter Source</button>
                {/if}
            {/if}
        </div>
    {/if}
    {#if !showCueSources}
        <button class="add-source-link" on:click={onAddSource}>+ Add Chapter Source</button>
    {/if}

</div>

<style>
    .source-footer {
        display: flex;
        flex-direction: column;
        align-items: center;
        max-width: 640px;
        margin-left: auto;
        margin-right: auto;
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

    .collapsible-section.compact {
        margin-top: -1.5rem;
    }

    .panel-button {
        margin-top: 0.75rem;
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
        padding: 0.25rem 1.25rem 1rem 1.25rem;
        text-align: center;
        border: 1px solid var(--border-color);
        border-radius: 0.75rem;
        margin-top: 0.5rem;
    }

    .sources-note {
        margin: 0.75rem 0 0.25rem;
        font-size: 0.8rem;
        color: var(--text-secondary);
        line-height: 1.4;
    }

    .emphasized {
        color: var(--text-primary);
    }

    .sources-list {
        margin: 0 auto;
        padding-left: 1.25rem;
        font-size: 0.8rem;
        color: var(--text-secondary);
        list-style: disc;
        display: inline-block;
        text-align: left;
    }

    .sources-list li {
        margin: 0.1rem 0;
    }
</style>
