<script lang="ts">
  import { onMount } from 'svelte';
  import { session } from '../stores/session';
  import { api } from '../utils/api';

  import ArrowRight from '@lucide/svelte/icons/arrow-right';
  import Check from '@lucide/svelte/icons/check';
  import ExternalLink from '@lucide/svelte/icons/external-link';

  let absUrl = $state('');

  let book = $derived($session.book);
  let title = $derived(book?.media.metadata.title ?? '');
  let coverImageUrl = $derived($session.itemId ? `/api/audiobookshelf/covers/${$session.itemId}` : null);
  let chapterCount = $derived($session.selectionStats.selected || $session.chapters.length);

  let absBase = $derived(absUrl ? absUrl.replace(/\/$/, '') : '');

  let embedUrl = $derived(
    absBase && $session.itemId ? `${absBase}/audiobookshelf/audiobook/${$session.itemId}/manage?tool=embed` : '',
  );

  let bookUrl = $derived(absBase && $session.itemId ? `${absBase}/audiobookshelf/item/${$session.itemId}` : '');

  onMount(async () => {
    try {
      const data = await api.config.getABS();
      absUrl = data.url;
    } catch (error) {
      console.error('Failed to load ABS config:', error);
    }
  });

  function handleNewAudiobook() {
    session.deleteSession();
    api.audiobookshelf.clearAllCache().catch(console.error);
  }
</script>

<div class="submit-success">
  <div class="success-card">
    {#if book && coverImageUrl}
      <div class="cover-wrap">
        <a
          class="cover-card"
          href={bookUrl || undefined}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={title ? `View ${title} in Audiobookshelf` : 'View in Audiobookshelf'}
        >
          <img class="cover-image" src={coverImageUrl} alt="" />
          {#if bookUrl}
            <div class="cover-hover">
              <span class="cover-hover-text">
                View in Audiobookshelf
                <ExternalLink size="13" color="#ffffff" />
              </span>
            </div>
          {/if}
        </a>
        <div class="success-badge" aria-hidden="true">
          <Check size="22" color="#ffffff" strokeWidth="3" />
        </div>
      </div>
    {/if}

    <header class="success-header">
      <h2 class="success-title">Chapters Submitted</h2>
      <p class="success-subtitle">
        {#if chapterCount > 0}
          {chapterCount}
          {chapterCount === 1 ? 'chapter' : 'chapters'} saved to Audiobookshelf
        {:else}
          Saved to Audiobookshelf
        {/if}
      </p>

      {#if embedUrl}
        <a class="btn btn-cancel embed-btn" href={embedUrl} target="_blank" rel="noopener noreferrer">
          Embed Metadata
          <ExternalLink size="15" />
        </a>
      {/if}

      <button class="btn btn-verify new-book-btn" type="button" onclick={handleNewAudiobook}>
        New Audiobook
        <ArrowRight size="16" />
      </button>
    </header>
  </div>
</div>

<style>
  .submit-success {
    max-width: 720px;
    margin: 0 auto;
    width: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3.5rem;
    padding-bottom: 1rem;
  }

  .success-card {
    display: flex;
    flex-direction: row;
    align-items: center;
    justify-content: center;
    gap: 5rem;
    width: 100%;
  }

  .cover-wrap {
    position: relative;
    flex-shrink: 0;
    margin-top: 0.35rem;
    width: 200px;
  }

  .cover-card {
    position: relative;
    display: block;
    width: 200px;
    height: 200px;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 10px 28px var(--shadow-color);
    background: var(--bg-tertiary);
    text-decoration: none;
    color: inherit;
    transition:
      transform 0.12s ease,
      box-shadow 0.12s ease;
  }

  .cover-card[href]:hover {
    transform: scale(1.02);
    box-shadow: 0 14px 36px var(--shadow-color);
  }

  .cover-image {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  .cover-hover {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: flex-end;
    justify-content: center;
    padding: 0.75rem;
    background: linear-gradient(to top, rgba(0, 0, 0, 0.72) 0%, transparent 55%);
    opacity: 0;
    transition: opacity 0.15s ease;
    pointer-events: none;
  }

  .cover-card[href]:hover .cover-hover,
  .cover-card[href]:focus-visible .cover-hover {
    opacity: 1;
  }

  .cover-hover-text {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    color: #ffffff;
    font-size: 0.85rem;
    font-weight: 600;
  }

  .success-badge {
    position: absolute;
    top: 0;
    right: 0;
    transform: translate(33%, -33%);
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: var(--primary);
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .success-header {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    text-align: center;
    min-width: 0;
  }

  .success-title {
    margin: 0;
    color: var(--text-primary);
    font-size: 1.65rem;
    font-weight: 700;
    line-height: 1.15;
  }

  .success-subtitle {
    margin-bottom: 1.75rem;
    color: var(--text-muted);
    font-size: 0.95rem;
    line-height: 1.3;
  }

  .embed-btn {
    margin-bottom: 0.5rem;
    text-decoration: none;
  }

  .new-book-btn {
    min-width: 200px;
  }

  @media (max-width: 560px) {
    .success-card {
      flex-direction: column;
      gap: 1.5rem;
    }
    .success-header {
      text-align: center;
      align-items: center;
    }
  }

  @media (max-width: 480px) {
    .success-title {
      font-size: 1.5rem;
    }
    .embed-btn,
    .new-book-btn {
      min-width: 0;
      width: 100%;
    }
  }
</style>
