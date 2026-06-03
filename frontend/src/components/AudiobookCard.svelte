<script lang="ts">
  import type { Snippet } from 'svelte';
  import BookHeadphones from '@lucide/svelte/icons/book-headphones';
  import { formatDuration } from '../utils/format';
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
    size = 'normal',
    metadata,
    actions,
  }: Props = $props();
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
    <h3 class="audiobook-title">{title || 'Audiobook'}</h3>
    {#if subtitle}
      <p class="audiobook-subtitle" title={subtitle}>{subtitle}</p>
    {/if}
    <div class="audiobook-metadata">
      {#if showDuration && duration > 0}
        <div class="audiobook-duration">{formatDuration(duration)}</div>
      {/if}
      {#if showFileCount && fileCount > 1}
        <div class="audiobook-file-count">{fileCount} files</div>
      {/if}
      {#if seriesName}
        <SeriesPill name={seriesName} sequence={seriesSequence} />
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
    margin: 0 0 0.5rem 0;
    color: var(--text-primary);
    font-size: 1.4rem;
    font-weight: 600;
    line-height: 1.3;
    word-wrap: break-word;
  }

  .audiobook-card.compact .audiobook-title {
    font-size: 1rem;
    margin-bottom: 0.25rem;
  }

  .audiobook-subtitle {
    margin: -0.25rem 0 0.5rem 0;
    color: var(--text-secondary);
    font-size: 0.95rem;
    line-height: 1.3;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .audiobook-card.compact .audiobook-subtitle {
    margin-top: 0;
    font-size: 0.85rem;
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
