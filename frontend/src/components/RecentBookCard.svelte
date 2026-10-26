<script lang="ts">
  import ArrowRight from '@lucide/svelte/icons/arrow-right';
  import BookHeadphones from '@lucide/svelte/icons/book-headphones';
  import { formatDuration, formatTimeAgo } from '../utils/format';

  // A pared-down AudiobookCard for the Recently Added list: one clickable row
  // with a small cover, the title, and a single line of detail.
  interface Props {
    title: string;
    authors?: string[] | null;
    duration?: number;
    coverImageUrl?: string | null;
    /** Epoch milliseconds, as Audiobookshelf reports it. */
    addedAt: number;
    disabled?: boolean;
    busy?: boolean;
    onselect?: () => void;
  }

  let {
    title,
    authors = null,
    duration = 0,
    coverImageUrl = null,
    addedAt,
    disabled = false,
    busy = false,
    onselect,
  }: Props = $props();

  let detail = $derived([authors?.join(', '), formatDuration(duration)].filter(Boolean).join(' · '));
</script>

<button type="button" class="recent-card" {disabled} aria-label="Start {title}" onclick={() => onselect?.()}>
  <span class="recent-cover">
    {#if coverImageUrl}
      <img src={coverImageUrl} alt="" />
    {:else}
      <BookHeadphones size="22" />
    {/if}
  </span>
  <span class="recent-text">
    <span class="recent-title" {title}>{title}</span>
    {#if detail}
      <span class="recent-detail" title={detail}>{detail}</span>
    {/if}
  </span>
  <span class="recent-meta">
    <span class="recent-added">{formatTimeAgo(addedAt)}</span>
    {#if busy}
      <span class="btn-spinner recent-spinner"></span>
    {:else}
      <span class="recent-arrow"><ArrowRight size="14" /></span>
    {/if}
  </span>
</button>

<style>
  .recent-card {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    width: 100%;
    min-width: 0;
    padding: 0.45rem 0.6rem 0.45rem 0.45rem;
    border: 1px solid transparent;
    border-radius: 10px;
    background: color-mix(in srgb, var(--accent-1) 6%, transparent);
    color: var(--text-primary);
    font: inherit;
    text-align: left;
    cursor: pointer;
    transition:
      border-color 0.15s ease,
      background-color 0.15s ease;
  }

  .recent-card:hover:not(:disabled),
  .recent-card:focus-visible {
    border-color: color-mix(in srgb, var(--accent-1) 45%, transparent);
    background: color-mix(in srgb, var(--accent-1) 8%, var(--bg-secondary));
    outline: none;
  }

  .recent-card:disabled {
    cursor: default;
    opacity: 0.6;
  }

  .recent-cover {
    flex-shrink: 0;
    width: 44px;
    height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 6px;
    overflow: hidden;
    background: var(--bg-tertiary);
    color: var(--text-muted);
  }

  .recent-cover img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .recent-text {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
  }

  .recent-title,
  .recent-detail {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .recent-title {
    font-size: 0.875rem;
    font-weight: 600;
    line-height: 1.3;
  }

  .recent-detail {
    font-size: 0.75rem;
    color: var(--text-secondary);
  }

  .recent-meta {
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 0.2rem;
  }

  .recent-added {
    font-size: 0.7rem;
    color: var(--text-muted);
    white-space: nowrap;
  }

  .recent-arrow {
    display: flex;
    color: var(--text-muted);
    transition:
      color 0.15s ease,
      transform 0.15s ease;
  }

  .recent-card:hover:not(:disabled) .recent-arrow,
  .recent-card:focus-visible .recent-arrow {
    color: var(--accent-1);
    transform: translateX(2px);
  }

  .recent-spinner {
    width: 14px;
    height: 14px;
    margin-right: 0;
    border-top-color: var(--accent-1);
  }
</style>
