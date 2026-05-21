<script lang="ts">
  import { onMount } from 'svelte';
  import { chapters, session } from '../stores/session';
  import { api, handleApiError } from '../utils/api';
  import DocLink from './DocLink.svelte';

  // Icons
  import BookMarked from '@lucide/svelte/icons/book-marked';
  import BookmarkPlus from '@lucide/svelte/icons/bookmark-plus';
  import Check from '@lucide/svelte/icons/check';
  import ChevronDown from '@lucide/svelte/icons/chevron-down';
  import ChevronLeft from '@lucide/svelte/icons/chevron-left';
  import Code from '@lucide/svelte/icons/code';
  import FileSpreadsheet from '@lucide/svelte/icons/file-spreadsheet';
  import ListMusic from '@lucide/svelte/icons/list-music';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import Upload from '@lucide/svelte/icons/upload';
  import X from '@lucide/svelte/icons/x';

  import type { ChapterData } from '../types/chapter';
  import type { EditorSettings } from '../types/api';

  let loading = $state(false);
  let error = $state<string | null>(null);
  let selectedChapters = $state<ChapterData[]>([]);
  let hasEmptyChapters = $state(false);
  let emptyChapterNumbers = $state<number[]>([]);

  let editorSettings = $state<EditorSettings>({
    show_formatted_time: true,
  });

  $effect(() => {
    if ($chapters) {
      selectedChapters = $chapters.filter((chapter) => chapter.selected);
    }
  });

  $effect(() => {
    const emptyChapters = selectedChapters
      .map((chapter, index) => ({ chapter, index }))
      .filter(({ chapter }) => !chapter.title || chapter.title.trim() === '');
    hasEmptyChapters = emptyChapters.length > 0;
    emptyChapterNumbers = emptyChapters.map(({ index }) => index + 1);
  });

  function isChapterEmpty(chapter: ChapterData) {
    return !chapter.title || chapter.title.trim() === '';
  }

  // Format timestamp
  function formatTimestamp(seconds: number) {
    if (!editorSettings.show_formatted_time) {
      return seconds.toFixed(2);
    }

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    } else {
      return `${minutes}:${secs.toString().padStart(2, '0')}`;
    }
  }

  async function loadEditorSettings() {
    try {
      editorSettings = await api.config.getEditorSettings();
    } catch (err) {
      console.warn('Failed to load editor settings:', err);
    }
  }

  // Calculate total duration
  function getTotalDuration() {
    return $session.book?.duration || 0;
  }

  function getChapterLength(index: number) {
    if (selectedChapters.length === 0) return 0;

    if (selectedChapters.length === 1) return getTotalDuration();

    if (index === 0) {
      return selectedChapters[1].timestamp;
    } else if (index === selectedChapters.length - 1) {
      return getTotalDuration() - selectedChapters[index].timestamp;
    } else {
      return selectedChapters[index + 1].timestamp - selectedChapters[index].timestamp;
    }
  }

  function goBackToEditor() {
    session
      .goBackToPreviousStep()
      .then((success) => {
        if (success) {
          return session.loadActiveSession();
        }
      })
      .catch((err) => {
        error = handleApiError(err);
      });
  }

  // Submit to Audiobookshelf
  async function submitToAudiobookshelf() {
    if (selectedChapters.length === 0) return;

    loading = true;
    error = null;

    try {
      await api.session.submit();
      // Session manager will handle the progress updates via WebSocket
    } catch (err) {
      error = handleApiError(err);
      console.error('Error submitting chapters:', err);
    } finally {
      loading = false;
    }
  }

  // Export functionality
  let exportExpanded = $state(false);
  let exportLoading = $state(false);
  let referenceExportInfo = $state<string | null>(null);
  let exportSection = $state<HTMLElement | undefined>();

  function toggleExportSection() {
    exportExpanded = !exportExpanded;
    if (exportExpanded) {
      requestAnimationFrame(() => {
        exportSection?.scrollIntoView({ behavior: 'smooth', block: 'end' });
      });
    }
  }

  async function exportFormat(format: string) {
    if (selectedChapters.length === 0) return;

    exportLoading = true;
    try {
      const response = await api.chapters.export(format);

      // Create a download link
      const blob = new Blob([response.data], { type: response.mimeType });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = response.filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      error = handleApiError(err);
      console.error(`Error exporting ${format}:`, err);
    } finally {
      exportLoading = false;
    }
  }

  async function exportAsSnapshot() {
    if (selectedChapters.length === 0) return;

    exportLoading = true;
    referenceExportInfo = null;
    try {
      const newRef = (await api.chapters.exportAsSnapshot()) as { name: string };
      referenceExportInfo = `Created Chapter Reference "${newRef.name}" with ${selectedChapters.length} chapter${selectedChapters.length === 1 ? '' : 's'}`;
    } catch (err) {
      error = handleApiError(err);
      console.error('Error exporting as snapshot:', err);
    } finally {
      exportLoading = false;
    }
  }

  // Ensure chapters are loaded when arriving at reviewing step
  onMount(async () => {
    try {
      await loadEditorSettings();

      if ($session.step === 'reviewing' && (!$chapters || $chapters.length === 0)) {
        await session.loadChapters();
      }
    } catch (err) {
      console.error('Failed to load chapters for review:', err);
    }
  });
</script>

<div class="chapter-review">
  <div class="header">
    <h2>
      Review Final Chapters <DocLink path="/editor/review-submit-export/" featureName="Review & Submit" size="16" />
    </h2>
    <p>Review your final chapter list before submitting to Audiobookshelf</p>
  </div>

  <div class="summary-card">
    <h3>Summary</h3>
    {#key editorSettings.show_formatted_time}
      <div class="summary-grid">
        <div class="summary-item">
          <span class="value">{selectedChapters.length}</span>
          <span class="label">Chapters</span>
        </div>
        <div class="summary-item">
          <span class="value">{formatTimestamp(getTotalDuration())}</span>
          <span class="label">Audiobook Length</span>
        </div>
        <div class="summary-item">
          <span class="value">
            {selectedChapters.length > 0
              ? formatTimestamp(getTotalDuration() / selectedChapters.length)
              : formatTimestamp(0)}
          </span>
          <span class="label">Avg Chapter Length</span>
        </div>
      </div>
    {/key}
  </div>

  {#if selectedChapters.length === 0}
    <div class="empty-state">
      <div class="empty-icon">
        <BookMarked size="48" />
      </div>
      <h3>No chapters selected</h3>
      <p>Please go back to the editor and select chapters to submit.</p>
    </div>
  {:else}
    <div class="chapters-list">
      <div class="table-container">
        <table class="table">
          <thead>
            <tr>
              <th style="width: 1px; padding-left: 1rem; text-align: center">#</th>
              <th style="width: 1px; text-align: center">Start</th>
              <th>Title</th>
              <th style="text-align: center">Duration</th>
            </tr>
          </thead>
          <tbody>
            {#each selectedChapters as chapter, index (chapter.id)}
              {#key editorSettings.show_formatted_time}
                <tr class="chapter-row" class:empty-chapter={isChapterEmpty(chapter)}>
                  <td class="chapter-number">
                    {index + 1}
                  </td>
                  <td class="timestamp">
                    {#if index == 0}
                      {formatTimestamp(0)}
                    {:else}
                      {formatTimestamp(chapter.timestamp)}
                    {/if}
                  </td>
                  <td class="chapter-title">
                    {#if isChapterEmpty(chapter)}
                      <div class="empty-title-container">
                        <TriangleAlert size="16" />
                        <span class="empty-title-text">Empty title</span>
                      </div>
                    {:else}
                      {chapter.title}
                    {/if}
                  </td>
                  <td class="chapter-length">
                    {formatTimestamp(getChapterLength(index))}
                  </td>
                </tr>
              {/key}
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {/if}

  {#if hasEmptyChapters}
    <div class="validation-error">
      <div class="validation-error-content">
        <div class="warning-icon">
          <TriangleAlert size="20" />
        </div>
        <div>
          <strong>Chapter titles cannot be empty</strong>
          <p>
            {#if emptyChapterNumbers.length === 1}
              Chapter {emptyChapterNumbers[0]} has an empty title.
            {:else}
              Chapters {emptyChapterNumbers.join(', ')} have empty titles.
            {/if}
            Please provide valid titles for all chapters.
          </p>
        </div>
      </div>
    </div>
  {/if}

  {#if error}
    <div class="alert alert-danger">
      {error}
      <button type="button" class="btn btn-sm btn-outline float-right" onclick={() => (error = null)}> Dismiss </button>
    </div>
  {/if}

  <div class="actions">
    <button class="btn btn-cancel btn-lg" onclick={goBackToEditor} disabled={loading}>
      <ChevronLeft size="16" />
      Back to Editor
    </button>

    <button
      class="btn btn-verify btn-lg"
      onclick={submitToAudiobookshelf}
      disabled={selectedChapters.length === 0 || loading || hasEmptyChapters}
    >
      {#if loading}
        <span class="btn-spinner"></span>
        Submitting…
      {:else}
        <Upload size="16" />
        Submit to Audiobookshelf
      {/if}
    </button>
  </div>

  <!-- Export Section -->
  {#if selectedChapters.length > 0}
    <div class="export-section" bind:this={exportSection}>
      <div class="export-toggle-row">
        <button class="export-toggle" onclick={toggleExportSection} aria-expanded={exportExpanded}>
          Export
          <div class="chevron {exportExpanded ? 'expanded' : ''}">
            <ChevronDown size="16" />
          </div>
        </button>
      </div>

      {#if exportExpanded}
        <div class="export-content">
          <div class="export-group">
            <p class="export-group-label">
              Download to file &nbsp;<DocLink path="/editor/review-submit-export/#export" featureName="File Export" />
            </p>
            <div class="export-buttons">
              <button class="btn btn-cancel export-button" onclick={() => exportFormat('csv')} disabled={exportLoading}>
                <FileSpreadsheet size="16" />
                CSV
              </button>

              <button
                class="btn btn-cancel export-button"
                onclick={() => exportFormat('json')}
                disabled={exportLoading}
              >
                <Code size="16" />
                JSON
              </button>

              <button class="btn btn-cancel export-button" onclick={() => exportFormat('cue')} disabled={exportLoading}>
                <ListMusic size="16" />
                CUE Sheet
              </button>
            </div>
          </div>

          <div class="export-group">
            <p class="export-group-label">
              Save as Chapter Reference &nbsp;<DocLink
                path="/editor/review-submit-export/#snapshot"
                featureName="Snapshot"
              />
            </p>
            <div class="export-buttons">
              <button
                class="btn btn-cancel export-button"
                onclick={exportAsSnapshot}
                disabled={exportLoading}
                title="Save a snapshot of these chapters as an in-session Chapter Reference"
              >
                <BookmarkPlus size="16" />
                Create Snapshot
              </button>
            </div>
          </div>

          {#if referenceExportInfo}
            <div class="export-info">
              <Check size="16" />
              <span>{referenceExportInfo}</span>
              <button class="dismiss-btn" onclick={() => (referenceExportInfo = null)} aria-label="Dismiss">
                <X size="14" />
              </button>
            </div>
          {/if}

          {#if exportLoading}
            <div class="export-loading">
              <span class="btn-spinner"></span>
              Exporting…
            </div>
          {/if}
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .chapter-review {
    max-width: 700px;
    margin: 0 auto;
  }

  .header {
    text-align: center;
    margin-bottom: 2rem;
    font-size: 2rem;
    font-weight: 600;
  }

  .header p {
    color: var(--text-secondary);
    font-size: 1rem;
  }

  .summary-card {
    padding-top: 0.5rem;
    padding-bottom: 1rem;
    margin-bottom: 1.5rem;
  }

  .summary-card h3 {
    margin: 0 0 0.75rem 0;
    color: var(--text-primary);
    font-size: 1rem;
    text-align: center;
  }

  .summary-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 2rem;
  }

  .summary-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 0.5rem 0.75rem;
    background-color: color-mix(in srgb, var(--text-primary) 3%, transparent);
    border-radius: 6px;
    backdrop-filter: blur(2px);
  }

  .summary-item .label {
    font-weight: 400;
    font-size: 0.8rem;
    margin-top: -0.125rem;
    color: var(--text-primary);
  }

  .summary-item .value {
    font-family: monospace;
    color: var(--text-primary);
    font-weight: 600;
    font-size: 1.1rem;
  }

  .table-container {
    background: linear-gradient(
      135deg,
      color-mix(in srgb, var(--accent-1) 4%, transparent) 0%,
      color-mix(in srgb, var(--accent-2) 2%, transparent) 100%
    );
    border: 1px solid color-mix(in srgb, var(--accent-1) 20%, transparent);
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 2rem;
  }

  .table thead th {
    background-color: color-mix(in srgb, var(--text-primary) 7%, transparent);
    border-bottom: none;
    border-top: none;
    text-align: left;
    font-size: 0.875rem;
  }

  .table td {
    border-top: 1px solid color-mix(in srgb, var(--accent-1) 10%, transparent);
    padding-top: 0.5rem;
    padding-bottom: 0.5rem;
  }

  .chapter-row {
    transition: background-color 0.2s ease;
  }

  .chapter-row:hover {
    background-color: transparent;
  }

  .chapter-row.empty-chapter {
    color: var(--warning);
  }

  .chapter-row.empty-chapter .chapter-number,
  .chapter-row.empty-chapter .timestamp,
  .chapter-row.empty-chapter .chapter-title,
  .chapter-row.empty-chapter .chapter-length {
    color: var(--warning);
  }

  .chapter-number {
    font-weight: 600;
    color: var(--text-primary);
    padding-left: 1rem;
    vertical-align: middle;
    text-align: center;
  }

  .timestamp {
    font-family: monospace;
    color: var(--text-secondary);
    font-size: 0.875rem;
    vertical-align: middle;
    text-align: center;
  }

  .chapter-title {
    color: var(--text-primary);
    word-wrap: break-word;
    font-size: 0.9rem;
    padding-right: 2rem;
  }

  .chapter-length {
    font-family: monospace;
    color: var(--text-secondary);
    font-size: 0.875rem;
    vertical-align: middle;
    text-align: center;
  }

  .empty-title-container {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .empty-title-text {
    font-style: italic;
    color: var(--warning);
  }

  .empty-state {
    text-align: center;
    padding: 4rem 2rem;
    color: var(--text-secondary);
  }

  .empty-icon {
    font-size: 4rem;
    margin-bottom: 1rem;
  }

  .validation-error {
    background: linear-gradient(
      145deg,
      color-mix(in srgb, var(--danger) 12%, transparent) 0%,
      color-mix(in srgb, var(--danger) 4%, transparent) 100%
    );
    border: 1px solid color-mix(in srgb, var(--danger) 25%, transparent);
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1.5rem;
  }

  .validation-error-content {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
  }

  .warning-icon {
    color: var(--danger);
    margin-top: 0.125rem;
  }

  .validation-error strong {
    color: var(--text-primary);
    font-weight: 600;
    display: block;
    margin-bottom: 0.25rem;
  }

  .validation-error p {
    color: var(--text-secondary);
    margin: 0;
    font-size: 0.875rem;
    line-height: 1.4;
  }

  .actions {
    display: flex;
    gap: 1rem;
    justify-content: center;
    flex-wrap: wrap;
  }

  .actions .btn {
    min-width: 200px;
  }

  .export-section {
    margin-top: 1rem;
  }

  .export-toggle-row {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.4rem;
  }

  .export-toggle {
    padding: 1rem 1.5rem 1rem 0.5rem;
    background: none;
    border: none;
    color: var(--text-secondary);
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    display: flex;
    justify-items: center;
    gap: 0.25rem;
    margin: 0 auto;
    width: auto;
    transition: background-color 0.2s ease;
  }

  .export-toggle:hover {
    color: var(--text-primary);
  }

  .chevron {
    display: flex;
    margin: 0;
    padding: 0;
    transition: transform 0.2s ease;
  }

  .chevron.expanded {
    transform: rotate(180deg);
  }

  .export-content {
    padding: 0.5rem 1.5rem 1.5rem 1.5rem;
  }

  .export-group {
    margin-top: 0.5rem;
    margin-bottom: 2rem;
  }

  .export-group-label {
    margin: 0 0 0.8rem 0;
    font-size: 0.8rem;
    color: var(--text-secondary);
    text-align: center;
  }

  .export-button {
    padding: 0.5rem 1rem;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.875rem;
  }

  .export-buttons {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    justify-content: center;
  }

  .export-info {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
    margin-top: 1rem;
    padding: 0.75rem 1rem;
    border: 1px solid color-mix(in srgb, var(--primary-color) 30%, transparent);
    background: color-mix(in srgb, var(--primary-color) 8%, transparent);
    border-radius: 8px;
    color: var(--text-primary);
    font-size: 0.85rem;
    line-height: 1.4;
  }

  .export-info > :global(svg) {
    flex-shrink: 0;
    margin-top: 0.1rem;
    color: var(--primary-color);
  }

  .export-info span {
    flex: 1;
  }

  .dismiss-btn {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-secondary);
    padding: 0;
    display: flex;
    margin-top: 0.15rem;
    flex-shrink: 0;
    opacity: 0.7;
  }

  .dismiss-btn:hover {
    opacity: 1;
  }

  .export-loading {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    margin-top: 1rem;
    color: var(--text-secondary);
    font-size: 0.875rem;
  }

  @keyframes spin {
    0% {
      transform: rotate(0deg);
    }
    100% {
      transform: rotate(360deg);
    }
  }

  .btn-spinner {
    display: inline-block;
    width: 16px;
    height: 16px;
    border: 2px solid transparent;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-right: 0.5rem;
  }

  .float-right {
    float: right;
    margin-left: 1rem;
  }

  /* Responsive design */
  @media (max-width: 768px) {
    .chapter-review {
      padding: 1rem;
    }

    .summary-grid {
      grid-template-columns: 1fr;
    }

    .table-container {
      overflow-x: auto;
    }

    .chapter-title {
      font-size: 0.8rem;
    }

    .chapter-length {
      font-size: 0.8rem;
    }

    .actions {
      flex-direction: column;
    }

    .actions .btn {
      min-width: 100%;
      font-size: 1rem;
    }

    .export-buttons {
      flex-direction: column;
      gap: 0.75rem;
    }

    .export-toggle {
      padding: 0.75rem 1rem;
      font-size: 0.9rem;
    }

    .validation-error {
      margin: 1rem;
    }

    .validation-error-content {
      flex-direction: column;
      gap: 0.5rem;
    }

    .warning-icon {
      align-self: flex-start;
    }
  }
</style>
