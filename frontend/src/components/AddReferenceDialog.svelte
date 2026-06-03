<script lang="ts">
  import { tooltip } from '../actions/tooltip';
  import { session } from '../stores/session';
  import { api, handleApiError } from '../utils/api';
  import ChapterModal from './ChapterModal.svelte';

  import AddReferenceHelpDialog from './AddReferenceHelpDialog.svelte';

  import BookOpen from '@lucide/svelte/icons/book-open';
  import CircleQuestionMark from '@lucide/svelte/icons/circle-question-mark';
  import Eye from '@lucide/svelte/icons/eye';
  import Plus from '@lucide/svelte/icons/plus';
  import Search from '@lucide/svelte/icons/search';
  import Upload from '@lucide/svelte/icons/upload';
  import X from '@lucide/svelte/icons/x';

  import type { AudnexusProviderOption } from '../types/api';
  import type { ChapterReference, TitleReference } from '../types/references';
  type NewReference = ChapterReference | TitleReference;

  interface Props {
    isOpen?: boolean;
    /** If true, the caller expects a chapter reference. */
    expectChapterRef?: boolean;
    /** Called with the newly added reference object on success. */
    onReferenceAdded?: ((ref: NewReference) => void) | null;
  }

  let { isOpen = $bindable(false), expectChapterRef = false, onReferenceAdded = null }: Props = $props();

  let providers = $state<AudnexusProviderOption[]>([]);

  async function loadProviders() {
    try {
      providers = await api.abs.getProviders();
    } catch (e) {
      console.error('Failed to load providers', e);
      providers = [];
    }
  }

  loadProviders();

  const CHAPTER_EXTS = '.json, .csv, .cue';
  const TITLE_EXTS = '.txt, .epub';
  const ALL_EXTS = `${CHAPTER_EXTS}, ${TITLE_EXTS}`;

  let showHelp = $state(false);
  let activeTab = $state('upload');

  /* ── Upload tab state ── */
  let isDragging = $state(false);
  let uploading = $state(false);
  let uploadError = $state<string | null>(null);
  let uploadInfo = $state<string | null>(null); // non-null string = title-only success message

  /* ── Search tab state ── */
  let provider = $state(loadProvider());
  let searchQuery = $state('');
  let searchAuthor = $state('');

  let addedAsins = $derived(
    new Set(($session.chapterRefs || []).map((s) => (s.metadata as Record<string, string>)?.ASIN).filter(Boolean)),
  );
  let searching = $state(false);
  let searchError = $state<string | null>(null);
  interface SearchResultBook {
    asin?: string;
    title?: string;
    author?: string;
    narrators?: string[];
    cover?: string;
    duration?: number;
    descriptionPlain?: string;
    series?: { series: string; sequence?: string | null }[];
    matchConfidence?: number;
    chapters?: { timestamp: number; title: string }[];
    [key: string]: unknown;
  }

  let searchResults = $state<SearchResultBook[]>([]);

  // Per-result add state: { [asin]: 'adding' | 'done' | 'error' }
  let addingState = $state<Record<string, string>>({});

  // Chapter preview modal state
  let showChapterModal = $state(false);
  let chapterModalTitle = $state('');
  let chapterModalData = $state<Array<{ timestamp: number; title: string }>>([]);

  /* ── Helpers ── */
  function loadProvider() {
    try {
      return localStorage.getItem('achew_search_provider') || 'audible';
    } catch {
      return 'audible';
    }
  }

  function saveProvider(p: string) {
    try {
      localStorage.setItem('achew_search_provider', p);
    } catch {
      // localStorage may be unavailable (private mode, quota); ignore.
    }
  }

  $effect(() => {
    saveProvider(provider);
  });

  function close() {
    if (uploading) return;
    isOpen = false;
  }

  function resetUploadState() {
    uploadError = null;
    uploadInfo = null;
  }

  function resetSearchState() {
    searchError = null;
    searchResults = [];
    addingState = {};
  }

  $effect(() => {
    if (isOpen) {
      searchQuery = $session.book?.media?.metadata?.title || '';
      searchAuthor = $session.book?.media?.metadata?.authorName || '';
    } else {
      resetUploadState();
      resetSearchState();
      searchQuery = '';
      searchAuthor = '';
      activeTab = 'upload';
    }
  });

  /* ── Scroll lock ── */
  $effect(() => {
    if (isOpen) {
      const origOverflow = document.body.style.overflow;
      const origPosition = document.body.style.position;
      const origTop = document.body.style.top;
      const origWidth = document.body.style.width;
      const scrollY = window.scrollY;
      document.body.style.overflow = 'hidden';
      document.body.style.position = 'fixed';
      document.body.style.top = `-${scrollY}px`;
      document.body.style.width = '100%';
      return () => {
        document.body.style.overflow = origOverflow;
        document.body.style.position = origPosition;
        document.body.style.top = origTop;
        document.body.style.width = origWidth;
        window.scrollTo(0, scrollY);
      };
    }
  });

  /* ── File upload ── */
  async function handleFile(file: File) {
    if (!file) return;
    resetUploadState();
    uploading = true;

    const formData = new FormData();
    formData.append('file', file);

    try {
      const newRef = await api.references.upload(formData);
      const isTitleRef = 'titles' in newRef;

      if (expectChapterRef && isTitleRef) {
        uploadInfo = `The file "${file.name}" doesn't contain timestamps, but has been added as a Title Reference. You can use it when editing chapter titles later.`;
      } else {
        isOpen = false;
        onReferenceAdded?.(newRef);
      }
    } catch (err) {
      uploadError = handleApiError(err);
    } finally {
      uploading = false;
    }
  }

  function onFileInput(e: Event) {
    const target = e.target as HTMLInputElement;
    const file = target.files?.[0];
    target.value = '';
    if (file) handleFile(file);
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    isDragging = false;
    const file = e.dataTransfer?.files?.[0];
    if (file) handleFile(file);
  }

  function onDragOver(e: DragEvent) {
    e.preventDefault();
    isDragging = true;
  }

  function onDragLeave() {
    isDragging = false;
  }

  /* ── Audnexus search ── */
  async function doSearch() {
    if (!searchQuery.trim() && !searchAuthor.trim()) return;
    resetSearchState();
    searching = true;
    try {
      searchResults = (await api.abs.searchBooks({
        provider,
        title: searchQuery.trim(),
        author: searchAuthor.trim(),
      })) as unknown as SearchResultBook[];
      if (searchResults.length === 0) {
        searchError = 'No results found. Try a different title or author.';
      }
    } catch (err) {
      searchError = handleApiError(err);
    } finally {
      searching = false;
    }
  }

  function handleSearchKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') doSearch();
  }

  function openChapterPreview(result: SearchResultBook) {
    if (!result.chapters?.length) return;
    chapterModalTitle = result.title ?? '';
    chapterModalData = result.chapters.map((ch) => ({ timestamp: ch.timestamp, title: ch.title }));
    showChapterModal = true;
  }

  async function addAudnexusReference(result: SearchResultBook) {
    if (!result.asin) return;
    addingState = { ...addingState, [result.asin]: 'adding' };
    try {
      const newRef = await api.references.addAudnexus(result.asin, provider);
      addingState = { ...addingState, [result.asin]: 'done' };
      isOpen = false;
      onReferenceAdded?.(newRef);
    } catch {
      addingState = { ...addingState, [result.asin]: 'error' };
    }
  }

  function formatDuration(minutes: number | undefined) {
    if (!minutes) return '';
    const h = Math.floor(minutes / 60);
    const m = Math.round(minutes % 60);
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
  }

  function seriesLabel(series: { series: string; sequence?: string | null }[] | undefined) {
    if (!series?.length) return null;
    const s = series[0];
    return s.sequence ? `${s.series} #${s.sequence}` : s.series;
  }

  function narratorLabel(narrators: string[] | undefined) {
    if (!narrators?.length) return null;
    if (narrators.length === 1) return `Narrated by ${narrators[0]}`;
    if (narrators.length === 2) return `Narrated by ${narrators[0]} and ${narrators[1]}`;
    return `Narrated by ${narrators[0]}, ${narrators[1]}, and ${narrators.length - 2} other${narrators.length - 2 === 1 ? '' : 's'}`;
  }

  function truncate(str: string | undefined, max: number) {
    if (!str) return null;
    return str.length > max ? str.slice(0, max).trimEnd() + '…' : str;
  }
</script>

{#if isOpen}
  <div class="backdrop" onclick={close} role="presentation">
    <div
      class="dialog"
      role="dialog"
      aria-modal="true"
      aria-label="Add Chapter Reference"
      tabindex="-1"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
    >
      <!-- Header -->
      <div class="modal-header">
        <div class="header-title">
          <h3>Add Chapter Reference</h3>
          <button
            class="help-btn"
            onclick={() => (showHelp = true)}
            aria-label="About References"
            use:tooltip={{ text: 'Click to learn about References', delay: 0 }}
          >
            <CircleQuestionMark size="16" />
          </button>
        </div>
        {#if !uploading}
          <button class="close-btn" onclick={close} aria-label="Close">
            <X size="20" />
          </button>
        {/if}
      </div>

      <!-- Tabs -->
      <div class="tab-bar">
        <button
          class="tab-btn"
          class:active={activeTab === 'upload'}
          onclick={() => {
            if (!uploading) {
              activeTab = 'upload';
              resetUploadState();
            }
          }}>Upload File</button
        >
        <button
          class="tab-btn"
          class:active={activeTab === 'search'}
          onclick={() => {
            if (!uploading) {
              activeTab = 'search';
            }
          }}>Audnexus Search</button
        >
      </div>

      <!-- Body -->
      <div class="modal-body">
        {#if activeTab === 'upload'}
          <!-- Upload area -->
          <div
            class="drop-zone"
            class:dragging={isDragging}
            class:busy={uploading}
            ondragover={onDragOver}
            ondragleave={onDragLeave}
            ondrop={onDrop}
            role="presentation"
          >
            {#if uploading}
              <div class="upload-status">
                <div class="spinner"></div>
                <p>Processing file…</p>
              </div>
            {:else}
              <Upload size="36" color="var(--text-secondary)" />
              <p class="drop-hint">
                Drag &amp; drop a file here, or <label class="file-link"
                  >browse<input type="file" accept={ALL_EXTS} onchange={onFileInput} style="display:none" /></label
                >
              </p>
              <p class="supported-types">
                {#if expectChapterRef}
                  Supported: {CHAPTER_EXTS}
                {:else}
                  Supported: {ALL_EXTS}
                {/if}
              </p>
            {/if}
          </div>

          {#if uploadError}
            <div class="message error">
              <span>{uploadError}</span>
              <button class="dismiss-btn" onclick={resetUploadState} aria-label="Dismiss">
                <X size="14" />
              </button>
            </div>
          {/if}

          {#if uploadInfo}
            <div class="message info">
              <span>{uploadInfo}</span>
              <button class="dismiss-btn" onclick={resetUploadState} aria-label="Dismiss">
                <X size="14" />
              </button>
            </div>
          {/if}
        {:else}
          <!-- Audnexus search -->
          <div class="search-form">
            <div class="search-row">
              <div class="field-col provider-col">
                <label class="field-label" for="search-provider">Provider</label>
                <select id="search-provider" class="field-input" bind:value={provider}>
                  {#each providers as p}
                    <option value={p.value}>{p.label}</option>
                  {/each}
                </select>
              </div>
              <div class="field-col">
                <label class="field-label" for="search-title">Title</label>
                <input
                  id="search-title"
                  class="field-input"
                  type="text"
                  placeholder="e.g. The Name of the Wind or B003P2WGIG"
                  bind:value={searchQuery}
                  onkeydown={handleSearchKeydown}
                />
              </div>
              <div class="field-col">
                <label class="field-label" for="search-author">Author</label>
                <input
                  id="search-author"
                  class="field-input"
                  type="text"
                  placeholder="Optional"
                  bind:value={searchAuthor}
                  onkeydown={handleSearchKeydown}
                />
              </div>
              <div class="field-col search-btn-col">
                <span class="field-label">&nbsp;</span>
                <button
                  class="search-btn"
                  onclick={doSearch}
                  disabled={searching || (!searchQuery.trim() && !searchAuthor.trim())}
                >
                  {#if searching}
                    <div class="spinner small"></div>
                    Searching…
                  {:else}
                    <Search size="14" /> Search
                  {/if}
                </button>
              </div>
            </div>
          </div>

          {#if searchError}
            <div class="message error">
              <span>{searchError}</span>
              <button class="dismiss-btn" onclick={() => (searchError = null)} aria-label="Dismiss">
                <X size="14" />
              </button>
            </div>
          {/if}

          {#if searchResults.length > 0}
            <div class="results-list">
              {#each searchResults as result (result.asin ?? result.title)}
                <div class="result-card">
                  {#if result.cover}
                    <img class="cover" src={result.cover} alt="Cover" loading="lazy" />
                  {:else}
                    <div class="cover cover-placeholder">
                      <BookOpen size="24" color="var(--text-secondary)" />
                    </div>
                  {/if}
                  <div class="result-info">
                    <p class="result-title">{result.title}</p>
                    {#if result.author || result.narrators?.length}
                      <p class="result-meta">
                        {#if result.author}{result.author}{/if}{#if result.author && result.narrators?.length}&ensp;·&ensp;{/if}{#if result.narrators?.length}<span
                            class="muted">{narratorLabel(result.narrators)}</span
                          >{/if}
                      </p>
                    {/if}
                    {#if truncate(result.descriptionPlain, 240)}
                      <p class="result-description">{truncate(result.descriptionPlain, 240)}</p>
                    {/if}
                    <div class="result-tags">
                      {#if result.duration != null}
                        <span class="tag">{formatDuration(result.duration)}</span>
                      {/if}
                      {#if result.chapter_count != null}
                        <span class="tag">{result.chapter_count} chapters</span>
                      {/if}
                      {#if seriesLabel(result.series)}
                        <span class="tag">{seriesLabel(result.series)}</span>
                      {/if}
                    </div>
                  </div>
                  <div class="result-actions">
                    {#if result.chapters?.length}
                      <button
                        class="icon-btn"
                        aria-label="Preview chapters"
                        use:tooltip={'Preview chapters'}
                        onclick={() => openChapterPreview(result)}
                      >
                        <Eye size="16" />
                      </button>
                    {/if}
                    <div class="result-actions-bottom">
                      {#if result.asin}
                        {@const alreadyAdded = addedAsins.has(result.asin)}
                        {#if addingState[result.asin] === 'done' || alreadyAdded}
                          <span class="add-done"
                            >{alreadyAdded && addingState[result.asin] !== 'done' ? 'Already Added' : 'Added'}</span
                          >
                        {:else}
                          <button
                            class="add-btn"
                            disabled={addingState[result.asin] === 'adding'}
                            onclick={() => addAudnexusReference(result)}
                            use:tooltip={'Add as Reference'}
                          >
                            {#if addingState[result.asin] === 'adding'}
                              <div class="spinner small"></div>
                            {:else if addingState[result.asin] === 'error'}
                              Retry
                            {:else}
                              <Plus size="14" /> Add
                            {/if}
                          </button>
                        {/if}
                      {/if}
                    </div>
                  </div>
                </div>
              {/each}
            </div>
          {/if}
        {/if}
      </div>
    </div>
  </div>
{/if}

<ChapterModal bind:isOpen={showChapterModal} title={chapterModalTitle} chapters={chapterModalData} />

<AddReferenceHelpDialog bind:isOpen={showHelp} />

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(2px);
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1rem;
  }

  .dialog {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    width: 100%;
    max-width: 800px;
    max-height: 88vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.25rem 1.5rem;
    border-bottom: 1px solid var(--border-color);
    flex-shrink: 0;
  }

  .modal-header h3 {
    margin: 0;
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--text-primary);
  }

  .header-title {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .help-btn {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-secondary);
    padding: 0.2rem;
    border-radius: 6px;
    display: flex;
    align-items: center;
    transition:
      background 0.15s,
      color 0.15s;
  }

  .help-btn:hover {
    background: var(--bg-tertiary);
    color: var(--text-primary);
  }

  .close-btn {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-secondary);
    padding: 0.25rem;
    border-radius: 6px;
    display: flex;
    align-items: center;
    transition: background 0.15s;
  }

  .close-btn:hover {
    background: var(--bg-tertiary);
    color: var(--text-primary);
  }

  /* Tabs */
  .tab-bar {
    display: flex;
    border-bottom: 1px solid var(--border-color);
    flex-shrink: 0;
  }

  .tab-btn {
    flex: 1;
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    cursor: pointer;
    padding: 0.75rem 1rem;
    font-size: 0.875rem;
    color: var(--text-secondary);
    transition:
      color 0.15s,
      border-color 0.15s;
  }

  .tab-btn.active {
    color: var(--primary-color);
    border-bottom-color: var(--primary-color);
    font-weight: 500;
  }

  .tab-btn:hover:not(.active) {
    color: var(--text-primary);
  }

  /* Body */
  .modal-body {
    flex: 1;
    overflow-y: auto;
    padding: 1.25rem 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  /* Drop zone */
  .drop-zone {
    border: 2px dashed var(--border-color);
    border-radius: 10px;
    padding: 2.5rem 1.5rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
    transition:
      border-color 0.15s,
      background 0.15s;
    text-align: center;
  }

  .drop-zone.dragging {
    border-color: var(--primary-color);
    background: color-mix(in srgb, var(--primary-color) 8%, transparent);
  }

  .drop-zone.busy {
    cursor: default;
    opacity: 0.7;
  }

  .drop-hint {
    margin: 0;
    color: var(--text-secondary);
    font-size: 0.9rem;
  }

  .file-link {
    color: var(--primary-color);
    cursor: pointer;
    text-decoration: underline;
  }

  .supported-types {
    margin: 0;
    font-size: 0.8rem;
    color: var(--text-tertiary, var(--text-secondary));
  }

  /* Messages */
  .message {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    border-radius: 8px;
    font-size: 0.875rem;
    line-height: 1.4;
  }

  .message.error {
    background: color-mix(in srgb, var(--error-color, #e53e3e) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--error-color, #e53e3e) 30%, transparent);
    color: var(--text-primary);
  }

  .message.info {
    background: color-mix(in srgb, var(--primary-color) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--primary-color) 30%, transparent);
    color: var(--text-primary);
  }

  .message span {
    flex: 1;
  }

  .dismiss-btn {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-secondary);
    padding: 0;
    display: flex;
    align-items: center;
    flex-shrink: 0;
    opacity: 0.7;
  }

  .dismiss-btn:hover {
    opacity: 1;
  }

  /* Upload status */
  .upload-status {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
    color: var(--text-secondary);
  }

  .upload-status p {
    margin: 0;
  }

  /* Search form */
  .search-form {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .search-row {
    display: flex;
    align-items: flex-end;
    gap: 0.5rem;
  }

  .field-col {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    flex: 1;
    min-width: 0;
  }

  .field-col.provider-col {
    flex: 0 0 9rem;
  }

  .field-col.search-btn-col {
    flex: 0 0 auto;
  }

  .field-label {
    font-size: 0.8rem;
    font-weight: 500;
    color: var(--text-secondary);
  }

  .field-input {
    box-sizing: border-box;
    height: 2.25rem;
    padding: 0 0.75rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background: var(--bg-secondary);
    color: var(--text-primary);
    font-size: 0.875rem;
  }

  .field-input:focus {
    outline: none;
    border-color: var(--primary-color);
  }

  .search-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    height: 2.25rem;
    padding: 0 1rem;
    background: var(--primary-color);
    color: #fff;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    cursor: pointer;
    transition: opacity 0.15s;
  }

  .search-btn:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .search-btn:not(:disabled):hover {
    opacity: 0.88;
  }

  /* Results */
  .results-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .result-card {
    display: flex;
    gap: 0.875rem;
    align-items: flex-start;
    padding: 0.875rem;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background: var(--bg-secondary);
  }

  .cover {
    width: 52px;
    height: 52px;
    border-radius: 4px;
    object-fit: cover;
    flex-shrink: 0;
  }

  .cover-placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-tertiary);
  }

  .result-info {
    flex: 1;
    min-width: 0;
  }

  .result-title {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .result-meta {
    margin: 0 0 0.15rem;
    font-size: 0.8rem;
  }

  .result-meta .muted {
    opacity: 0.75;
  }

  .result-description {
    margin: 0.25rem 0 0.5rem 0;
    font-size: 0.78rem;
    color: var(--text-secondary);
    line-height: 1.3;
    opacity: 0.8;
  }

  .result-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    margin-top: 0.35rem;
  }

  .tag {
    font-size: 0.72rem;
    padding: 0.15rem 0.45rem;
    border-radius: 4px;
    background: var(--bg-tertiary);
  }

  .result-actions {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    justify-content: space-between;
    gap: 0.5rem;
    flex-shrink: 0;
    align-self: stretch;
  }

  .result-actions-bottom {
    display: flex;
    align-items: flex-end;
    flex: 1;
    justify-content: flex-end;
  }

  .icon-btn {
    background: none;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    padding: 0.35rem;
    cursor: pointer;
    color: var(--text-secondary);
    display: flex;
    align-items: center;
    transition:
      background 0.15s,
      color 0.15s;
  }

  .icon-btn:hover {
    background: var(--bg-tertiary);
    color: var(--text-primary);
  }

  .add-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.35rem 0.75rem;
    background: var(--primary-color);
    color: #fff;
    border: none;
    border-radius: 6px;
    font-size: 0.8rem;
    cursor: pointer;
    white-space: nowrap;
    transition: opacity 0.15s;
  }

  .add-btn:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .add-btn:not(:disabled):hover {
    opacity: 0.88;
  }

  .add-done {
    font-size: 0.8rem;
    color: var(--primary-color);
    padding: 0.35rem 0.5rem;
  }

  /* Spinner */
  .spinner {
    width: 22px;
    height: 22px;
    border: 2px solid var(--border-color);
    border-top-color: var(--primary-color);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  .spinner.small {
    width: 13px;
    height: 13px;
    border-width: 2px;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
