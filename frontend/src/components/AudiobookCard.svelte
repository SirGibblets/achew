<script lang="ts">
  import type { Snippet } from 'svelte';
  import BookHeadphones from '@lucide/svelte/icons/book-headphones';
  import { formatDuration } from '../utils/format';
  import { buildContributorLine } from '../utils/highlight';
  import HighlightedText from './HighlightedText.svelte';
  import SeriesPill from './SeriesPill.svelte';

  interface Props {
    title?: string;
    subtitle?: string | null;
    duration?: number;
    coverImageUrl?: string | null;
    showDuration?: boolean;
    fileCount?: number;
    showFileCount?: boolean;
    seriesName?: string | null;
    seriesSequence?: string | null;
    authors?: string[] | null;
    narrators?: string[] | null;
    /** Substring to mark wherever it appears on this card. */
    highlightQuery?: string;
    size?: 'normal' | 'compact';
    metadata?: Snippet;
    actions?: Snippet;
  }

  let {
    title = '',
    subtitle = null,
    duration = 0,
    coverImageUrl = null,
    showDuration = true,
    fileCount = 1,
    showFileCount = true,
    seriesName = null,
    seriesSequence = null,
    authors = null,
    narrators = null,
    highlightQuery = '',
    size = 'normal',
    metadata,
    actions,
  }: Props = $props();

  let contributorClauses = $derived(buildContributorLine(authors ?? [], narrators ?? [], highlightQuery));

  // The windows hide names, so the full credits stay reachable on hover.
  let contributorTitle = $derived(
    [authors?.length ? `By ${authors.join(', ')}` : '', narrators?.length ? `Narrated by ${narrators.join(', ')}` : '']
      .filter(Boolean)
      .join('\n'),
  );
</script>

<div class="audiobook-card" class:compact={size === 'compact'}>
  <div class="audiobook-icon">
    {#if coverImageUrl}
      <img src={coverImageUrl} alt="Audiobook cover" class="cover-image" />
    {:else}
      <BookHeadphones size="40" />
    {/if}
  </div>
  <div class="audiobook-details">
    <h3 class="audiobook-title"><HighlightedText text={title || 'Audiobook'} query={highlightQuery} /></h3>
    {#if subtitle}
      <p class="audiobook-subtitle" title={subtitle}>
        <HighlightedText text={subtitle} query={highlightQuery} />
      </p>
    {/if}
    {#if contributorClauses.length > 0}
      <p class="audiobook-contributors" title={contributorTitle}>
        {#each contributorClauses as clause}
          <!-- prettier-ignore -->
          <span class="contributor-clause" class:priority={clause.priority}>{#each clause.segments as segment}{#if segment.hit}<mark>{segment.text}</mark>{:else if segment.more}<span class="contributor-more">{segment.text}</span>{:else}{segment.text}{/if}{/each}</span>
        {/each}
      </p>
    {/if}
    <div class="audiobook-metadata">
      {#if showDuration && duration > 0}
        <div class="audiobook-duration">{formatDuration(duration)}</div>
      {/if}
      {#if showFileCount && fileCount > 1}
        <div class="audiobook-file-count">{fileCount} files</div>
      {/if}
      {#if seriesName}
        <SeriesPill name={seriesName} sequence={seriesSequence} {highlightQuery} />
      {/if}
      {@render metadata?.()}
    </div>
  </div>
  {@render actions?.()}
</div>

<style>
  .audiobook-card {
    background: linear-gradient(
      135deg,
      color-mix(in srgb, var(--accent-1) 18%, transparent) 0%,
      color-mix(in srgb, var(--accent-2) 14%, transparent) 100%
    );
    border: 1px solid color-mix(in srgb, var(--accent-1) 35%, transparent);
    border-radius: 16px;
    padding: 1rem;
    display: flex;
    align-items: center;
    gap: 1.25rem;
    width: 100%;
  }

  .audiobook-card.compact {
    padding: 0.75rem;
    gap: 1rem;
  }

  .audiobook-icon {
    font-size: 2.5rem;
    flex-shrink: 0;
    position: relative;
    width: 80px;
    height: 80px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .audiobook-card.compact .audiobook-icon {
    width: 72px;
    height: 72px;
    font-size: 2rem;
  }

  .cover-image {
    width: 100%;
    height: 100%;
    object-fit: cover;
    border-radius: 8px;
  }

  .audiobook-details {
    flex: 1;
    min-width: 0;
  }

  .audiobook-title {
    margin: 0;
    color: var(--text-primary);
    font-size: 1.4rem;
    font-weight: 600;
    line-height: 1.3;
    word-wrap: break-word;
  }

  .audiobook-card.compact .audiobook-title {
    font-size: 1rem;
  }

  .audiobook-subtitle {
    margin: 0 0 0.25rem 0;
    color: var(--text-primary);
    font-size: 0.65rem;
    font-style: italic;
    font-weight: 300;
    line-height: 1.3;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .audiobook-contributors {
    margin: 0 0 0.5rem 0;
    color: var(--text-secondary);
    font-size: 0.85rem;
    line-height: 1.3;
    display: flex;
    min-width: 0;
    overflow: hidden;
  }

  /* Clauses truncate individually rather than as one run, so the clause holding
     the search match can be exempted from giving up space. */
  .contributor-clause {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
  }

  .contributor-clause.priority {
    flex-shrink: 0;
  }

  .audiobook-card.compact .audiobook-contributors {
    font-size: 0.8rem;
    margin-bottom: 0.4rem;
  }

  .contributor-more {
    font-style: italic;
  }

  .audiobook-metadata {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
    align-items: center;
  }

  .audiobook-duration,
  .audiobook-file-count {
    padding: 0.2rem 0.45rem;
    border-radius: 100px;
    font-size: 0.7rem;
    color: var(--text-primary);
    font-weight: 500;
    display: inline-block;
    border: 1px solid var(--pill-border);
  }

  .audiobook-file-count {
    background: color-mix(in srgb, var(--accent-1) 12%, transparent);
    border-color: color-mix(in srgb, var(--accent-1) 45%, transparent);
  }

  /* Responsive design */
  @media (max-width: 768px) {
    .audiobook-card {
      padding: 1rem;
      gap: 1rem;
    }

    .audiobook-title {
      font-size: 1.2rem;
    }
  }

  @media (max-width: 480px) {
    .audiobook-duration,
    .audiobook-file-count {
      font-size: 0.5rem;
    }
  }
</style>
