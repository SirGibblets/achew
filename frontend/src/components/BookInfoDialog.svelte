<script lang="ts">
  import { slide } from 'svelte/transition';
  import { tooltip } from '../actions/tooltip';
  import { session } from '../stores/session';
  import { api } from '../utils/api';
  import { formatBytes, formatDuration, formatNameList } from '../utils/format';
  import CopyButton from './CopyButton.svelte';

  import ChevronDown from '@lucide/svelte/icons/chevron-down';
  import ExternalLink from '@lucide/svelte/icons/external-link';
  import X from '@lucide/svelte/icons/x';

  interface Props {
    isOpen?: boolean;
  }

  let { isOpen = $bindable(false) }: Props = $props();

  let codecExpanded = $state(false);
  let absUrl = $state('');
  let absFetched = $state(false);

  let book = $derived($session.book);
  let metadata = $derived(book?.media.metadata ?? null);
  let audioFiles = $derived(book?.media.audioFiles ?? []);
  let audioInfo = $derived($session.audioInfo);
  let itemId = $derived($session.itemId);

  let coverImageUrl = $derived(itemId ? `/api/audiobookshelf/covers/${itemId}` : null);

  let authorNames = $derived.by(() => {
    if (!metadata) return [];
    if (metadata.authors && metadata.authors.length) {
      return metadata.authors.map((a) => a.name);
    }
    return (metadata.authorName ?? '').split(',');
  });
  let narratorNames = $derived.by(() => {
    if (!metadata) return [];
    if (metadata.narrators && metadata.narrators.length) {
      return metadata.narrators;
    }
    return (metadata.narratorName ?? '').split(',');
  });

  let authors = $derived(formatNameList(authorNames));
  let narrators = $derived(formatNameList(narratorNames));

  let codecLabel = $derived.by(() => {
    if (!audioInfo) return null;
    const codec = audioInfo.codec ? audioInfo.codec.toUpperCase() : null;
    const container = audioInfo.container ? audioInfo.container.toUpperCase() : null;
    if (codec && container && codec !== container) return `${codec} (${container})`;
    return codec ?? container ?? null;
  });

  let totalSize = $derived(audioFiles.reduce((sum, f) => sum + (f.metadata?.size ?? 0), 0));

  let absBase = $derived(absUrl ? absUrl.replace(/\/$/, '') : '');
  let bookUrl = $derived(absBase && itemId ? `${absBase}/audiobookshelf/item/${itemId}` : '');

  $effect(() => {
    if (isOpen && !absFetched) {
      absFetched = true;
      api.config
        .getABS()
        .then((data) => (absUrl = data.url))
        .catch((error) => console.error('Failed to load ABS config:', error));
    }
  });

  function close() {
    codecExpanded = false;
    isOpen = false;
  }

  function handleBackdropClick(event: MouseEvent) {
    if (event.target === event.currentTarget) {
      close();
    }
  }

  function handleBackdropKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      close();
    }
  }
</script>

{#if isOpen}
  <div
    class="modal-backdrop"
    onclick={handleBackdropClick}
    onkeydown={handleBackdropKeydown}
    role="dialog"
    aria-modal="true"
    tabindex="-1"
  >
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <div class="header-titles">
            <span class="header-eyebrow">Audiobook info</span>
            {#if metadata?.title}
              <h3 class="header-title" title={metadata.title}>{metadata.title}</h3>
            {/if}
            {#if metadata?.subtitle}
              <span class="header-subtitle" title={metadata.subtitle}>{metadata.subtitle}</span>
            {/if}
          </div>
          <button class="close-button" onclick={close} aria-label="Close">
            <X size="20" />
          </button>
        </div>

        <div class="modal-body">
          {#if book && metadata}
            <div class="book-top">
              {#if coverImageUrl}
                <img class="cover" src={coverImageUrl} alt="" />
              {/if}
              <div class="book-meta">
                {#if authors.display}
                  <div class="meta-row">
                    <span class="meta-label">Author</span>
                    <span class="meta-value" use:tooltip={authors.count > 1 ? authors.full : null}>
                      {authors.display}
                    </span>
                  </div>
                {/if}
                {#if narrators.display}
                  <div class="meta-row">
                    <span class="meta-label">Narrator</span>
                    <span class="meta-value" use:tooltip={narrators.count > 1 ? narrators.full : null}>
                      {narrators.display}
                    </span>
                  </div>
                {/if}
                {#if book.duration > 0}
                  <div class="meta-row">
                    <span class="meta-label">Duration</span>
                    <span class="meta-value">{formatDuration(book.duration)}</span>
                  </div>
                {/if}
                {#if codecLabel}
                  <div class="meta-row">
                    <span class="meta-label">Codec</span>
                    <span class="meta-value codec-value">
                      {codecLabel}
                      {#if audioInfo?.ffmpeg_output}
                        <button
                          class="codec-toggle"
                          type="button"
                          onclick={() => (codecExpanded = !codecExpanded)}
                          aria-expanded={codecExpanded}
                          aria-label="Toggle ffmpeg details"
                        >
                          <span class="chevron" class:expanded={codecExpanded}>
                            <ChevronDown size="14" />
                          </span>
                        </button>
                      {/if}
                    </span>
                  </div>
                {/if}
              </div>
            </div>

            {#if codecExpanded && audioInfo?.ffmpeg_output}
              <div class="code-box-wrap" transition:slide={{ duration: 200 }}>
                <div class="code-box-actions">
                  <CopyButton text={audioInfo.ffmpeg_output} label="Copy audio info" />
                </div>
                <pre class="code-box">{audioInfo.ffmpeg_output}</pre>
              </div>
            {/if}

            <div class="section">
              <div class="section-header">
                <span class="section-title">Files</span>
                <span class="section-summary">
                  {audioFiles.length}
                  {audioFiles.length === 1 ? 'file' : 'files'} ({formatBytes(totalSize)})
                </span>
              </div>
              {#if audioFiles.length === 1}
                <div class="single-file" title={audioFiles[0].metadata.filename}>
                  {audioFiles[0].metadata.filename}
                </div>
              {:else if audioFiles.length > 1}
                <div class="file-list">
                  {#each audioFiles as file (file.ino)}
                    <div class="file-row">
                      <span class="file-name" title={file.metadata.filename}>{file.metadata.filename}</span>
                      <span class="file-detail"
                        >{formatDuration(file.duration)} ({formatBytes(file.metadata.size)})</span
                      >
                    </div>
                  {/each}
                </div>
              {/if}
            </div>

            {#if bookUrl}
              <a class="abs-link" href={bookUrl} target="_blank" rel="noopener noreferrer">
                View in Audiobookshelf
                <ExternalLink size="15" />
              </a>
            {/if}
          {:else}
            <div class="empty-state">No book information available.</div>
          {/if}
        </div>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .modal-dialog {
    width: 90%;
    max-width: 560px;
    max-height: 90vh;
    background: var(--bg-card);
    border-radius: 0.5rem;
    box-shadow: 0 0.5rem 1rem rgba(0, 0, 0, 0.15);
    display: flex;
    flex-direction: column;
  }

  .modal-content {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }

  .modal-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    padding: 1rem 1rem 0.5rem 1.5rem;
  }

  .header-titles {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
  }

  .header-eyebrow {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
  }

  .header-title {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-primary);
    line-height: 1.25;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .header-subtitle {
    margin-top: 0.1rem;
    font-size: 0.9rem;
    color: var(--text-secondary);
    line-height: 1.3;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .close-button {
    flex-shrink: 0;
    background: none;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    padding: 0.25rem;
    border-radius: 0.25rem;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .close-button:hover {
    background: var(--hover-bg);
    color: var(--text-primary);
  }

  .modal-body {
    flex: 1;
    overflow-y: auto;
    min-height: 0;
    padding: 0.5rem 1.5rem 1.5rem 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }

  .book-top {
    display: flex;
    gap: 1.25rem;
    align-items: flex-start;
  }

  .cover {
    width: 110px;
    height: 110px;
    object-fit: cover;
    border-radius: 8px;
    flex-shrink: 0;
    background: var(--bg-tertiary);
    box-shadow: 0 4px 12px var(--shadow-color);
  }

  .book-meta {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .meta-row {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    min-width: 0;
  }

  .meta-label {
    flex-shrink: 0;
    width: 4.5rem;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: var(--text-muted);
  }

  .meta-value {
    min-width: 0;
    font-size: 0.9rem;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .codec-value {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    overflow: visible;
  }

  .codec-toggle {
    background: none;
    border: none;
    padding: 0.1rem;
    color: var(--text-secondary);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
  }

  .codec-toggle:hover {
    color: var(--text-primary);
  }

  .chevron {
    display: inline-flex;
    align-items: center;
    transition: transform 0.2s ease;
  }

  .chevron.expanded {
    transform: rotate(180deg);
  }

  .code-box-wrap {
    position: relative;
  }

  .code-box-actions {
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    z-index: 1;
  }

  .code-box {
    margin: 0;
    max-height: 240px;
    overflow: auto;
    padding: 0.75rem;
    padding-right: 3rem;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: 0.375rem;
    font-family: monospace;
    font-size: 0.75rem;
    line-height: 1.5;
    color: var(--text-primary);
    white-space: pre;
  }

  .section {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .section-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.5rem;
  }

  .section-title {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: var(--text-muted);
  }

  .section-summary {
    font-size: 0.85rem;
    color: var(--text-secondary);
  }

  .single-file {
    font-size: 0.9rem;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .file-list {
    max-height: 200px;
    overflow-y: auto;
    border: 1px solid var(--border-color);
    border-radius: 0.375rem;
  }

  .file-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.45rem 0.75rem;
    border-bottom: 1px solid var(--border-color);
  }

  .file-row:last-child {
    border-bottom: none;
  }

  .file-name {
    min-width: 0;
    font-size: 0.85rem;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .file-detail {
    flex-shrink: 0;
    font-size: 0.8rem;
    color: var(--text-secondary);
    white-space: nowrap;
  }

  .abs-link {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    align-self: flex-start;
    font-size: 0.9rem;
    font-weight: 500;
    color: var(--primary);
    text-decoration: none;
  }

  .abs-link:hover {
    text-decoration: underline;
  }

  .empty-state {
    padding: 1rem 0;
    color: var(--text-muted);
    text-align: center;
  }

  @media (max-width: 768px) {
    .book-top {
      flex-direction: column;
      align-items: center;
      text-align: center;
    }

    .meta-row {
      justify-content: center;
    }
  }
</style>
