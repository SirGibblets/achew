<script lang="ts">
  import ChevronDown from '@lucide/svelte/icons/chevron-down';
  import type { ChapterReference, TitleReference } from '../types/references';

  interface Props {
    chapterRefs?: ChapterReference[];
    titleRefs?: TitleReference[];
    showRefs?: boolean;
    onAddReference?: () => void;
  }

  let { chapterRefs = [], titleRefs = [], showRefs = false, onAddReference }: Props = $props();

  let nonEmptyTitleReferences = $derived(titleRefs.filter((s) => s.type !== 'custom' || (s.titles?.length ?? 0) > 0));

  let expanded = $state(false);
</script>

<div class="reference-footer">
  {#if nonEmptyTitleReferences.length > 0 || showRefs}
    <div class="collapsible-section" class:compact={showRefs}>
      <button class="collapsible-toggle" type="button" onclick={() => (expanded = !expanded)}>
        {#if showRefs}
          {chapterRefs.length === 0 ? 'No' : chapterRefs.length} Reference{chapterRefs.length === 1 ? '' : 's'} available
          for comparison
        {:else}
          {nonEmptyTitleReferences.length} Title Reference{nonEmptyTitleReferences.length === 1 ? '' : 's'}
        {/if}
        <span class="chevron" class:expanded>
          <ChevronDown size="12" />
        </span>
      </button>

      {#if expanded}
        <div class="collapsible-panel">
          {#if showRefs}
            <p class="references-note">
              Chapter References with timestamps can be used to compare against detected cues. This is helpful when
              determining which cues are most likely to be accurate chapter markers.
            </p>
            <p class="references-note emphasized">
              {#if chapterRefs.length > 0}
                The following Chapter References include timestamps and can be used for comparison:
              {:else}
                No References are currently available for comparison. Use the button below to add one.
              {/if}
            </p>
            {#if chapterRefs.length > 0}
              <ul class="references-list">
                {#each chapterRefs as s}
                  <li class="emphasized">{s.name}</li>
                {/each}
              </ul>
            {/if}
          {/if}

          {#if nonEmptyTitleReferences.length > 0}
            <p class="references-note">
              The following References do not include timestamps, but can be used later when editing titles:
            </p>
            <ul class="references-list">
              {#each nonEmptyTitleReferences as s}
                <li>{s.name}</li>
              {/each}
            </ul>
          {/if}
        </div>

        {#if showRefs}
          <button class="add-reference-link panel-button" onclick={onAddReference}>+ Add Chapter Reference</button>
        {/if}
      {/if}
    </div>
  {/if}
  {#if !showRefs}
    <button class="add-reference-link" onclick={onAddReference}>+ Add Chapter Reference</button>
  {/if}
</div>

<style>
  .reference-footer {
    display: flex;
    flex-direction: column;
    align-items: center;
    max-width: 640px;
    margin-left: auto;
    margin-right: auto;
  }

  .add-reference-link {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--primary-color);
    font-size: 0.875rem;
    padding: 0;
  }

  .add-reference-link:hover {
    opacity: 0.8;
  }

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

  .references-note {
    margin: 0.75rem 0 0.25rem;
    font-size: 0.8rem;
    color: var(--text-secondary);
    line-height: 1.4;
  }

  .emphasized {
    color: var(--text-primary);
  }

  .references-list {
    margin: 0 auto;
    padding-left: 1.25rem;
    font-size: 0.8rem;
    color: var(--text-secondary);
    list-style: disc;
    display: inline-block;
    text-align: left;
  }

  .references-list li {
    margin: 0.1rem 0;
  }
</style>
