<script lang="ts">
  import { onMount } from 'svelte';
  import { tooltip } from '../actions/tooltip';
  import { session } from '../stores/session';
  import { api } from '../utils/api';
  import AddReferenceDialog from './AddReferenceDialog.svelte';
  import ChapterModal from './ChapterModal.svelte';
  import DocLink from './DocLink.svelte';
  import ReferenceFooter from './ReferenceFooter.svelte';
  // Icons
  import CircleQuestionMark from '@lucide/svelte/icons/circle-question-mark';
  import ExternalLink from '@lucide/svelte/icons/external-link';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';

  import type { ChapterReference } from '../types/references';

  interface LocalChapterRow {
    timestamp: number;
    title: string;
    [key: string]: unknown;
  }

  let loading = $state(false);
  let selectedRegenerateRef = $state('');
  let selectedRealignRef = $state('');
  let selectedQuickEditRef = $state('');
  let activeTab = $state('smart_detect');
  let isDramatized = $state(false);
  let chapterRefs = $state<ChapterReference[]>([]);
  let error = $state<string | null>(null);

  let showAddReference = $state(false);

  let titleRefs = $derived($session.titleRefs || []);

  const DURATION_MISMATCH_WARNING_SECONDS = 180;

  let realignDurationMismatch = $derived.by(() => {
    const bookDuration = $session.book?.duration;
    const ref = chapterRefs.find((r) => r.id === selectedRealignRef);
    if (!ref || bookDuration == null) return false;
    return Math.abs(bookDuration - ref.duration) > DURATION_MISMATCH_WARNING_SECONDS;
  });

  function handleReferenceAdded(newRef: { id: string; chapters?: unknown[] }) {
    if (newRef.chapters) {
      if (activeTab === 'realign') selectedRealignRef = newRef.id;
      else if (activeTab === 'regenerate') selectedRegenerateRef = newRef.id;
      else if (activeTab === 'quick_edit') selectedQuickEditRef = newRef.id;
    }
  }

  let chapterModalOpen = $state(false);
  let chapterModalTitle = $state('');
  let chapterModalData = $state<LocalChapterRow[]>([]);
  let chapterModalLoading = $state(false);

  $effect(() => {
    const refs = $session.chapterRefs;
    if (refs) {
      chapterRefs = refs;
      if (!selectedQuickEditRef) {
        const absRef = refs.find((s) => s.type === 'abs');
        if (absRef) selectedQuickEditRef = absRef.id;
      }
    }
  });

  async function proceedWithSelection() {
    loading = true;
    try {
      if (activeTab === 'smart_detect') {
        await api.session.startWorkflow('smart_detect', undefined, isDramatized);
      } else if (activeTab === 'realign') {
        if (!selectedRealignRef) {
          alert('Please select a Chapter Reference.');
          loading = false;
          return;
        }
        await api.session.startWorkflow('realign', selectedRealignRef, isDramatized);
      } else if (activeTab === 'regenerate') {
        if (!selectedRegenerateRef) {
          alert('Please select a Chapter Reference.');
          loading = false;
          return;
        }
        await api.session.startWorkflow('regenerate', selectedRegenerateRef, undefined);
      } else if (activeTab === 'quick_edit') {
        if (!selectedQuickEditRef) {
          alert('Please select a Chapter Reference.');
          loading = false;
          return;
        }
        await api.session.startWorkflow('quick_edit', selectedQuickEditRef, undefined);
      }
    } catch (error) {
      console.error('Error selecting workflow:', error);
      const message = error instanceof Error ? error.message : String(error);
      session.setError('Failed to select workflow: ' + message);
    } finally {
      loading = false;
    }
  }

  // Fetch detailed chapter data for modal display
  async function fetchChapterData(refId: string) {
    if ($session.step !== 'select_workflow') return [];

    chapterModalLoading = true;
    try {
      // Find the reference in chapterRefs
      const ref = chapterRefs.find((s) => s.id === refId);
      if (ref && ref.chapters) {
        return ref.chapters.map((chapter, index) => ({
          timestamp: chapter.timestamp,
          title: chapter.title || `Chapter ${index + 1}`,
        }));
      }

      return [];
    } catch (error) {
      console.error('Failed to fetch chapter data:', error);
      return [];
    } finally {
      chapterModalLoading = false;
    }
  }

  // Handle chapter count bubble click
  async function handleChapterCountClick(refId: string) {
    const ref = chapterRefs.find((s) => s.id === refId);

    chapterModalTitle = ref ? ref.name : 'Chapter Data';
    chapterModalData = [];
    chapterModalOpen = true;

    chapterModalData = await fetchChapterData(refId);
  }

  // Close chapter modal
  function closeChapterModal() {
    chapterModalOpen = false;
    chapterModalData = [];
    chapterModalTitle = '';
  }

  // Get the option display info
  function getOptionInfo(option: string) {
    // Handle dynamic chapter references
    const chapterRef = chapterRefs.find((r) => r.id === option);
    if (chapterRef) {
      return {
        title: chapterRef.name,
        description: chapterRef.description,
      };
    }

    return {
      title: option,
      description: 'Unknown option',
    };
  }

  onMount(async () => {});
</script>

<div class="chapter-options">
  {#if error}
    <div class="alert alert-danger">
      {error}
      <button type="button" class="btn btn-sm btn-outline float-right" onclick={() => (error = null)}> Dismiss </button>
    </div>
  {/if}

  {#if $session.audioUnsupportedCodec}
    <div class="codec-warning-card">
      <TriangleAlert size="20" color="var(--warning)" />
      <div class="codec-warning-content">
        <p class="codec-warning-title">
          Unsupported Audio Codec (xHE-AAC) <DocLink
            path="/reference/supported-formats/#audio"
            featureName="Supported Formats"
          />
        </p>
        <p class="codec-warning-text">
          This audiobook uses a codec that is not currently supported by Achew. Features like Smart Detect, chapter
          realignment, transcription, audio playback, etc. may not work as expected.
        </p>
      </div>
    </div>
  {/if}

  <div class="header">
    <h2>
      Select a Workflow <DocLink
        path="/getting-started/workflows-overview/"
        featureName="Workflow Selection"
        size="16"
      />
    </h2>
  </div>

  {#if loading}
    <div class="text-center p-4">
      <div class="spinner"></div>
      <p class="mt-2">Loading Chapter References…</p>
    </div>
  {:else}
    <div class="mode-selector">
      <button
        class="mode-btn {activeTab === 'smart_detect' ? 'active' : ''}"
        onclick={() => (activeTab = 'smart_detect')}
        type="button"
      >
        Smart Detect
      </button>
      <button
        class="mode-btn {activeTab === 'realign' ? 'active' : ''}"
        onclick={() => (activeTab = 'realign')}
        type="button"
      >
        Realign Chapters
      </button>
      <button
        class="mode-btn {activeTab === 'regenerate' ? 'active' : ''}"
        onclick={() => (activeTab = 'regenerate')}
        type="button"
      >
        Regenerate Titles
      </button>
      <button
        class="mode-btn {activeTab === 'quick_edit' ? 'active' : ''}"
        onclick={() => (activeTab = 'quick_edit')}
        type="button"
      >
        Quick Edit
      </button>
    </div>

    <div class="options-grid">
      {#if activeTab === 'smart_detect'}
        <p class="tab-description">
          The <b>Smart Detect</b> workflow uses audio analysis to locate potential chapter cues within the audiobook.
          After detection, you'll choose which cues to use as your initial chapters.
          <DocLink path="/workflows/smart-detect/" featureName="Smart Detect" />
        </p>

        <ReferenceFooter {chapterRefs} {titleRefs} showRefs={true} onAddReference={() => (showAddReference = true)} />

        <div class="dramatized-toggle">
          <label>
            <input type="checkbox" bind:checked={isDramatized} disabled={loading} />
            <span>Dramatized</span>
          </label>
          <div
            class="help-icon"
            use:tooltip={{
              text: 'Select this if your audiobook contains non-speech elements like music and sound effects. Detection will be slower but more accurate.',
              delay: 0,
            }}
          >
            <CircleQuestionMark size="14" />
          </div>
        </div>

        <div class="actions">
          <button class="btn btn-verify" onclick={proceedWithSelection} disabled={loading}>
            {#if loading}
              <span class="btn-spinner"></span>
              Processing…
            {:else}
              Start Smart Detect
            {/if}
          </button>
        </div>
      {:else if activeTab === 'realign'}
        <p class="tab-description">
          The <b>Realign Chapters</b> workflow attempts to realign the timestamps of a Chapter Reference to better match
          the book's audio, preserving the chapter titles. This is useful for cases where a Reference has correct
          titles, but the timestamps are off by a few seconds.
          <DocLink path="/workflows/realign-chapters/" featureName="Chapter Realignment" />
        </p>

        {#if chapterRefs.length > 0}
          {#each chapterRefs as ref}
            <div class="option-card" class:selected={selectedRealignRef === ref.id}>
              <label>
                <div class="option-layout">
                  <input type="radio" bind:group={selectedRealignRef} value={ref.id} disabled={loading} />
                  <div class="option-content">
                    <div class="option-header">
                      <b>{getOptionInfo(ref.id).title}</b>
                      <div class="chapter-count-container">
                        <button
                          class="chapter-count clickable"
                          onclick={() => handleChapterCountClick(ref.id)}
                          use:tooltip={'Click to view chapter details'}
                        >
                          {ref.chapters.length} chapters
                          <ExternalLink size="12" />
                        </button>
                      </div>
                    </div>
                    <p class="description">
                      {getOptionInfo(ref.id).description}
                    </p>
                  </div>
                </div>
              </label>
            </div>
          {/each}

          <ReferenceFooter {titleRefs} onAddReference={() => (showAddReference = true)} />

          <div class="dramatized-toggle">
            <label>
              <input type="checkbox" bind:checked={isDramatized} disabled={loading} />
              <span>Dramatized</span>
            </label>
            <div
              class="help-icon"
              use:tooltip={{
                text: 'Select this if your audiobook contains non-speech elements like music and sound effects. Detection will be slower but more accurate.',
                delay: 0,
              }}
            >
              <CircleQuestionMark size="14" />
            </div>
          </div>

          {#if realignDurationMismatch}
            <div class="duration-warning-card">
              <TriangleAlert size="20" color="var(--warning)" />
              <p class="duration-warning-text">
                The duration of the selected reference differs significantly from your book's duration. Realignment may
                fail or produce inaccurate results.
              </p>
            </div>
          {/if}

          <div class="actions">
            <button class="btn btn-verify" onclick={proceedWithSelection} disabled={loading || !selectedRealignRef}>
              {#if loading}
                <span class="btn-spinner"></span>
                Processing…
              {:else if selectedRealignRef}
                Realign {getOptionInfo(selectedRealignRef).title}
              {:else}
                Select a Chapter Reference
              {/if}
            </button>
          </div>
        {:else}
          <div class="no-references-card">
            <TriangleAlert size="16" />
            <p>No existing chapters to realign</p>
          </div>
          <button class="empty-add-reference" onclick={() => (showAddReference = true)}>+ Add Chapter Reference</button>
        {/if}
      {:else if activeTab === 'regenerate'}
        <p class="tab-description">
          The <b>Regenerate Titles</b> workflow transcribes new titles at the timestamps of a Chapter Reference. This is
          useful for cases where a Reference has correct timestamps, but the titles are missing or incorrect.
          <DocLink path="/workflows/regenerate-titles/" featureName="Title Regeneration" />
        </p>

        {#if chapterRefs.length > 0}
          {#each chapterRefs as ref}
            <div class="option-card" class:selected={selectedRegenerateRef === ref.id}>
              <label>
                <div class="option-layout">
                  <input type="radio" bind:group={selectedRegenerateRef} value={ref.id} disabled={loading} />
                  <div class="option-content">
                    <div class="option-header">
                      <b>{getOptionInfo(ref.id).title}</b>
                      <div class="chapter-count-container">
                        <button
                          class="chapter-count clickable"
                          onclick={() => handleChapterCountClick(ref.id)}
                          use:tooltip={'Click to view chapter details'}
                        >
                          {ref.chapters.length} chapters
                          <ExternalLink size="12" />
                        </button>
                      </div>
                    </div>
                    <p class="description">
                      {getOptionInfo(ref.id).description}
                    </p>
                  </div>
                </div>
              </label>
            </div>
          {/each}

          <ReferenceFooter {titleRefs} onAddReference={() => (showAddReference = true)} />

          <div class="actions" style="margin-top: 1.5rem;">
            <button class="btn btn-verify" onclick={proceedWithSelection} disabled={loading || !selectedRegenerateRef}>
              {#if loading}
                <span class="btn-spinner"></span>
                Processing…
              {:else if selectedRegenerateRef}
                Continue with {getOptionInfo(selectedRegenerateRef).title}
              {:else}
                Select a Chapter Reference
              {/if}
            </button>
          </div>
        {:else}
          <div class="no-references-card">
            <TriangleAlert size="16" />
            <p>No existing chapters to regenerate</p>
          </div>
          <button class="empty-add-reference" onclick={() => (showAddReference = true)}>+ Add Chapter Reference</button>
        {/if}
      {:else if activeTab === 'quick_edit'}
        <p class="tab-description">
          The <b>Quick Edit</b> workflow skips audio analysis and loads chapters from a Chapter Reference directly into
          the editor. Use this when you only need to make quick changes, like using AI Cleanup or adding a missing
          chapter.
          <DocLink path="/workflows/quick-edit/" featureName="Quick Edit" />
        </p>

        {#if chapterRefs.length > 0}
          {#each chapterRefs as ref}
            <div class="option-card" class:selected={selectedQuickEditRef === ref.id}>
              <label>
                <div class="option-layout">
                  <input type="radio" bind:group={selectedQuickEditRef} value={ref.id} disabled={loading} />
                  <div class="option-content">
                    <div class="option-header">
                      <b>{getOptionInfo(ref.id).title}</b>
                      <div class="chapter-count-container">
                        <button
                          class="chapter-count clickable"
                          onclick={() => handleChapterCountClick(ref.id)}
                          use:tooltip={'Click to view chapter details'}
                        >
                          {ref.chapters.length} chapters
                          <ExternalLink size="12" />
                        </button>
                      </div>
                    </div>
                    <p class="description">
                      {getOptionInfo(ref.id).description}
                    </p>
                  </div>
                </div>
              </label>
            </div>
          {/each}

          <ReferenceFooter {titleRefs} onAddReference={() => (showAddReference = true)} />

          <div class="actions" style="margin-top: 1.5rem;">
            <button class="btn btn-verify" onclick={proceedWithSelection} disabled={loading || !selectedQuickEditRef}>
              {#if loading}
                <span class="btn-spinner"></span>
                Loading…
              {:else if selectedQuickEditRef}
                Open in Editor
              {:else}
                Select a Chapter Reference
              {/if}
            </button>
          </div>
        {:else}
          <div class="no-references-card">
            <TriangleAlert size="16" />
            <p>No existing chapters to edit</p>
          </div>
          <button class="empty-add-reference" onclick={() => (showAddReference = true)}>+ Add Chapter Reference</button>
        {/if}
      {/if}
    </div>
  {/if}
</div>

<!-- Chapter Data Modal -->
<ChapterModal
  bind:isOpen={chapterModalOpen}
  title={chapterModalTitle}
  chapters={chapterModalData}
  loading={chapterModalLoading}
  onclose={closeChapterModal}
/>

<AddReferenceDialog bind:isOpen={showAddReference} expectChapterRef={true} onReferenceAdded={handleReferenceAdded} />

<style>
  .chapter-options {
    max-width: 900px;
    width: 100%;
    margin: 0 auto;
  }

  .header {
    text-align: center;
    margin-bottom: 2rem;
  }

  .header h2 {
    margin-bottom: 0.75rem;
    font-size: 2rem;
    font-weight: 600;
  }

  .options-grid {
    display: grid;
    gap: 1rem;
  }

  .option-card {
    border: 2px solid var(--border-color);
    border-radius: 12px;
    padding: 0;
    background: var(--bg-secondary);
    transition: all 0.1s ease;
    cursor: pointer;
  }

  .option-card:hover {
    border-color: var(--primary-hover);
  }

  .option-card.selected {
    border-color: var(--primary-color);
  }

  .option-card label {
    display: block;
    padding: 0.75rem;
    cursor: pointer;
    margin: 0;
  }

  .option-card input[type='radio'] {
    width: 20px;
    height: 20px;
    flex-shrink: 0;
    accent-color: var(--primary-contrast);
    margin: 0 0.5rem;
    cursor: pointer;
  }

  .option-layout {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    width: 100%;
  }

  .option-content {
    flex: 1;
    min-width: 0;
  }

  .option-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.25rem;
    position: relative;
    flex-wrap: wrap;
  }

  .description {
    color: var(--text-secondary);
    margin-bottom: 0;
    line-height: 1.5;
  }

  .chapter-count {
    background: var(--bg-tertiary);
    padding: 0.25rem 0.75rem;
    border-radius: 60px;
    font-size: 0.75rem;
    color: var(--text-primary);
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    border: none;
    cursor: default;
  }

  .chapter-count.clickable {
    cursor: pointer;
    transition: all 0.2s ease;
    border: 1px solid transparent;
  }

  .chapter-count.clickable:hover {
    background: var(--primary-color);
    color: white;
    transform: translateY(-1px);
  }

  .chapter-count.clickable:active {
    transform: translateY(0);
  }

  .chapter-count-container {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .actions {
    display: flex;
    justify-content: center;
    margin-top: 0rem;
  }

  .spinner {
    width: 16px;
    height: 16px;
    border: 2px solid transparent;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    display: inline-block;
    margin-right: 0.5rem;
  }

  @keyframes spin {
    0% {
      transform: rotate(0deg);
    }
    100% {
      transform: rotate(360deg);
    }
  }

  .text-center {
    text-align: center;
  }

  .p-4 {
    padding: 2rem;
  }

  .mt-2 {
    margin-top: 0.5rem;
  }

  .float-right {
    float: right;
    margin-left: 1rem;
  }

  .help-icon {
    border: none;
    display: inline-flex;
    background: transparent;
    color: var(--text-secondary);
    cursor: pointer;
    padding: 2px;
    border-radius: 50%;
    transition: all 0.2s ease;
  }

  .help-icon {
    position: relative;
    cursor: help;
  }

  .help-icon:hover {
    color: var(--primary-color);
    background: var(--bg-tertiary);
  }

  @media (max-width: 768px) {
    .chapter-options {
      padding: 1rem;
    }

    .option-card label {
      padding: 1rem;
    }

    .option-header {
      flex-wrap: wrap;
    }

    .chapter-count-container {
      flex-wrap: wrap;
      gap: 0.25rem;
    }
  }

  .mode-selector {
    display: flex;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    width: fit-content;
    min-width: 620px;
    margin-left: auto;
    margin-right: auto;
    overflow: hidden;
    margin-bottom: 2rem;
  }

  .mode-btn {
    flex: 1;
    padding: 0.5rem 1rem;
    border: none;
    background: transparent;
    color: var(--text-muted);
    font-weight: 500;
    font-size: 0.875rem;
    border-radius: 0;
    cursor: pointer;
    position: relative;
    border-right: 1px solid var(--border-color);
    white-space: nowrap;
  }

  .mode-btn:first-child {
    border-top-left-radius: 7px;
    border-bottom-left-radius: 7px;
  }

  .mode-btn:last-child {
    border-top-right-radius: 7px;
    border-bottom-right-radius: 7px;
    border-right: none;
  }

  .mode-btn:hover:not(.active) {
    color: var(--text-primary);
    background: var(--hover-bg);
  }

  .mode-btn.active {
    background: linear-gradient(135deg, var(--accent-gradient-start) 0%, var(--accent-gradient-end) 100%);
    color: white;
    font-weight: 600;
  }

  .tab-description {
    color: var(--text-secondary);
    font-size: 1rem;
    line-height: 1.5;
    margin-bottom: 1rem;
    text-align: center;
    max-width: 700px;
    margin-left: auto;
    margin-right: auto;
  }

  .tab-description b {
    color: var(--text-primary);
  }

  .dramatized-toggle {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    margin-top: 1.5rem;
  }

  .dramatized-toggle label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
    font-weight: 500;
    color: var(--text-primary);
    margin: 0;
  }

  .dramatized-toggle input[type='checkbox'] {
    width: 16px;
    height: 16px;
    accent-color: var(--primary-color);
    cursor: pointer;
  }

  .no-references-card {
    display: flex;
    flex-direction: row;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    padding: 1rem 1.5rem;
    background: rgba(245, 158, 11, 0.1);
    border: 0.5px solid var(--warning);
    border-radius: 8px;
    color: var(--warning);
    text-align: left;
    margin: 1rem auto;
    width: fit-content;
    max-width: 100%;
  }

  .no-references-card p {
    margin: 0;
    font-weight: 400;
    font-size: 0.95rem;
    color: var(--warning);
  }

  .empty-add-reference {
    display: block;
    margin: 0 auto;
    background: none;
    border: none;
    cursor: pointer;
    color: var(--primary-color);
    font-size: 0.875rem;
    padding: 0;
  }

  .empty-add-reference:hover {
    opacity: 0.8;
  }

  .codec-warning-card {
    display: flex;
    flex-direction: row;
    align-items: flex-start;
    gap: 0.75rem;
    padding: 1rem 1.25rem;
    background: rgba(245, 158, 11, 0.1);
    border: 0.5px solid var(--warning);
    border-radius: 8px;
    margin: 0 0 2rem 0;
  }

  .codec-warning-card :global(svg) {
    flex-shrink: 0;
    margin-top: 2px;
  }

  .codec-warning-content {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .codec-warning-title {
    margin: 0;
    font-weight: 600;
    font-size: 0.95rem;
    color: var(--warning);
  }

  .codec-warning-text {
    margin: 0;
    font-size: 0.9rem;
    line-height: 1.4;
  }

  .duration-warning-card {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 0.75rem;
    padding: 1rem 1.25rem;
    background: rgba(245, 158, 11, 0.1);
    border: 0.5px solid var(--warning);
    border-radius: 8px;
    margin: 1.5rem auto 0.5rem;
    max-width: 700px;
  }

  .duration-warning-card :global(svg) {
    flex-shrink: 0;
  }

  .duration-warning-text {
    margin: 0;
    font-size: 0.9rem;
    line-height: 1.4;
  }
</style>
