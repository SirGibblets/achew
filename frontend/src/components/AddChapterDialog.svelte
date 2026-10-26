<script lang="ts">
  import { SvelteSet } from 'svelte/reactivity';
  import { tooltip } from '../actions/tooltip';
  import { api, handleApiError } from '../utils/api';
  import { audio, currentSegmentId, isPlaying } from '../stores/audio';
  import { snippetStatus, snippetTranscripts } from '../stores/snippetTranscripts';
  import DocLink from './DocLink.svelte';

  import ArrowDown from '@lucide/svelte/icons/arrow-down';
  import ArrowUp from '@lucide/svelte/icons/arrow-up';
  import AudioLines from '@lucide/svelte/icons/audio-lines';
  import ChevronDown from '@lucide/svelte/icons/chevron-down';
  import ChevronUp from '@lucide/svelte/icons/chevron-up';
  import CircleAlert from '@lucide/svelte/icons/circle-alert';
  import Clock from '@lucide/svelte/icons/clock';
  import LoaderCircle from '@lucide/svelte/icons/loader-circle';
  import MoveHorizontal from '@lucide/svelte/icons/move-horizontal';
  import Pause from '@lucide/svelte/icons/pause';
  import Play from '@lucide/svelte/icons/play';
  import Mic from '@lucide/svelte/icons/mic';
  import ScanSearch from '@lucide/svelte/icons/scan-search';
  import X from '@lucide/svelte/icons/x';

  interface EditorSettings {
    show_formatted_time?: boolean;
    show_fractional_seconds?: boolean;
    add_chapter_auto_asr?: boolean | null;
  }

  interface AddChapterConfirmDetail {
    timestamp: number;
    title: string;
  }

  interface Props {
    isOpen?: boolean;
    chapterId?: string | null;
    defaultTab?: string | null;
    editorSettings?: EditorSettings;
    onsettingschange?: (updates: Partial<EditorSettings>) => void;
    onconfirm?: (detail: AddChapterConfirmDetail) => void;
    oncancel?: () => void;
  }

  let {
    isOpen = $bindable(false),
    chapterId = null,
    defaultTab = null,
    editorSettings = { show_formatted_time: true, show_fractional_seconds: true },
    onsettingschange,
    onconfirm,
    oncancel,
  }: Props = $props();

  import type { AddOptionsResponse } from '../types/api';

  let loading = $state(false);
  let scanning = $state(false);
  let error = $state<string | null>(null);

  let addOptions = $state<AddOptionsResponse | null>(null);
  let activeTab = $state('timestamp');
  let selectedTimestamp = $state<number | null>(null);
  let selectedTitle = $state('');
  let manualTimestamp = $state('');
  let originalTimestamp = $state<number | null>(null);
  let sortBy = $state('gap');
  let sortOrder = $state('desc');

  // Set when the user toggles Auto ASR so the checkbox responds before the saved setting round-trips
  let autoAsrOverride = $state<boolean | null>(null);
  // Without a saved preference, auto-transcribe only if an ASR model is already loaded, so opening
  // the dialog never triggers a surprise model load/download
  let autoAsrEnabled = $derived(
    autoAsrOverride ?? editorSettings.add_chapter_auto_asr ?? addOptions?.asr_warm ?? false,
  );

  function formatTimestamp(seconds: number) {
    if (!editorSettings.show_formatted_time) {
      return seconds.toFixed(2);
    }

    const showFractions = editorSettings.show_fractional_seconds !== false;
    const rounded = showFractions ? Math.round(seconds * 100) / 100 : Math.floor(seconds);
    const hours = Math.floor(rounded / 3600);
    const minutes = Math.floor((rounded % 3600) / 60);
    const secsValue = rounded % 60;
    const secs = showFractions ? secsValue.toFixed(2).padStart(5, '0') : secsValue.toString().padStart(2, '0');

    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, '0')}:${secs}`;
    } else {
      return `${minutes}:${secs}`;
    }
  }

  function parseTimestamp(input: string) {
    if (!editorSettings.show_formatted_time) {
      return parseFloat(input) || 0;
    }

    const parts = input.split(':').map((p: string) => parseFloat(p) || 0);
    if (parts.length === 2) {
      return parts[0] * 60 + parts[1];
    } else if (parts.length === 3) {
      return parts[0] * 3600 + parts[1] * 60 + parts[2];
    }
    return 0;
  }

  function isValidTimestamp(timestamp: number) {
    if (!addOptions) return false;
    const tolerance = 0.1;
    return timestamp >= addOptions.min_timestamp - tolerance && timestamp <= addOptions.max_timestamp + tolerance;
  }

  function getAvailableTabs() {
    if (!addOptions) return ['timestamp'];

    const tabs = ['timestamp', 'detected_cue'];

    const chapterRefs = addOptions.chapter_refs;
    if (chapterRefs) {
      Object.keys(chapterRefs).forEach((refName) => {
        if (chapterRefs[refName].length > 0) {
          tabs.push(refName);
        }
      });
    }

    if (addOptions.deleted && addOptions.deleted.length > 0) {
      tabs.push('deleted');
    }

    return tabs;
  }

  function getSortedDetectedCues() {
    if (!addOptions?.detected_cues) return [];

    const cues = [...addOptions.detected_cues];
    cues.sort((a, b) => {
      if (sortBy === 'gap') {
        return sortOrder === 'desc' ? b.gap - a.gap : a.gap - b.gap;
      } else {
        return sortOrder === 'desc' ? b.timestamp - a.timestamp : a.timestamp - b.timestamp;
      }
    });
    return cues;
  }

  // Timestamps of the active tab's rows, top to bottom as displayed
  function getListedTimestamps(): number[] {
    if (!addOptions) return [];
    if (activeTab === 'detected_cue') return getSortedDetectedCues().map((c) => c.timestamp);
    if (activeTab === 'deleted') return addOptions.deleted.map((c) => c.timestamp);
    return addOptions.chapter_refs?.[activeTab]?.map((c) => c.timestamp) ?? [];
  }

  function toggleAutoAsr(enabled: boolean) {
    autoAsrOverride = enabled;
    onsettingschange?.({ add_chapter_auto_asr: enabled });
  }

  // A row counts as in view once at least this much of it is visible inside the scrolling list
  const IN_VIEW_RATIO = 0.5;
  // Wait for scrolling to settle before re-queueing, so rows that only flick past aren't transcribed
  const AUTO_QUEUE_SETTLE_MS = 150;

  // Timestamps of rows currently in view. The observer is rooted at the viewport, which still
  // accounts for clipping by the dialog's scroll containers.
  const rowsInView = new SvelteSet<number>();
  let rowObserver: IntersectionObserver | null = null;
  const observedRows = new Map<Element, number>();

  function getRowObserver() {
    rowObserver ??= new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const timestamp = observedRows.get(entry.target);
          if (timestamp === undefined) continue;
          if (entry.isIntersecting && entry.intersectionRatio >= IN_VIEW_RATIO) {
            rowsInView.add(timestamp);
          } else {
            rowsInView.delete(timestamp);
          }
        }
      },
      { threshold: [0, IN_VIEW_RATIO, 1] },
    );
    return rowObserver;
  }

  function trackInView(node: HTMLElement, timestamp: number) {
    // No observer (e.g. jsdom): treat every row as in view
    if (typeof IntersectionObserver === 'undefined') {
      rowsInView.add(timestamp);
      return {
        update(next: number) {
          rowsInView.delete(timestamp);
          timestamp = next;
          rowsInView.add(timestamp);
        },
        destroy() {
          rowsInView.delete(timestamp);
        },
      };
    }

    const observer = getRowObserver();
    observedRows.set(node, timestamp);
    observer.observe(node);
    return {
      // Unkeyed {#each} rows are reused when the sort changes; re-observe for a fresh reading
      update(next: number) {
        rowsInView.delete(timestamp);
        timestamp = next;
        observedRows.set(node, timestamp);
        observer.unobserve(node);
        observer.observe(node);
      },
      destroy() {
        observer.unobserve(node);
        observedRows.delete(node);
        rowsInView.delete(timestamp);
      },
    };
  }

  // Keep the auto-queue in step with the rows in view; disabling (or closing) stops queueing
  $effect(() => {
    const timestamps = isOpen && autoAsrEnabled ? getListedTimestamps().filter((t) => rowsInView.has(t)) : [];
    if (timestamps.length === 0) {
      snippetTranscripts.setAutoQueue([]);
      return;
    }
    const timer = setTimeout(() => snippetTranscripts.setAutoQueue(timestamps), AUTO_QUEUE_SETTLE_MS);
    return () => clearTimeout(timer);
  });

  function selectTab(tab: string) {
    activeTab = tab;
    selectedTimestamp = null;
    selectedTitle = '';

    if (tab === 'timestamp' && manualTimestamp && addOptions) {
      const parsed = parseTimestamp(manualTimestamp);
      if (isValidTimestamp(parsed)) {
        selectedTimestamp = parsed;
      }
    }
  }

  function selectOption(timestamp: number, title = '') {
    selectedTimestamp = timestamp;
    selectedTitle = title;
  }

  function handleTimestampInput(event: Event) {
    const target = event.target as HTMLInputElement;
    manualTimestamp = target.value;
    const parsed = parseTimestamp(manualTimestamp);
    if (isValidTimestamp(parsed)) {
      selectedTimestamp = parsed;
    } else {
      selectedTimestamp = null;
    }
    originalTimestamp = null;
  }

  function adjustTimestamp(delta: number) {
    if (!addOptions) return;
    const current = originalTimestamp !== null ? originalTimestamp : parseTimestamp(manualTimestamp);
    const newValue = Math.max(addOptions.min_timestamp, Math.min(addOptions.max_timestamp, current + delta));
    manualTimestamp = formatTimestamp(newValue);
    selectedTimestamp = newValue;
    originalTimestamp = newValue;
  }

  function handleTimestampKeydown(event: KeyboardEvent) {
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      adjustTimestamp(1);
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      adjustTimestamp(-1);
    } else if (event.key === ' ') {
      event.preventDefault();
      if (selectedTimestamp !== null) {
        previewAudio(selectedTimestamp);
      }
    }
  }

  function toggleSort(column: string) {
    if (sortBy === column) {
      sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
    } else {
      sortBy = column;
      sortOrder = column === 'gap' ? 'desc' : 'asc';
    }
  }

  function handleRowClick(event: MouseEvent, timestamp: number, title = '') {
    const target = event.target as HTMLElement;
    if (target.tagName === 'BUTTON' || target.tagName === 'INPUT') {
      return;
    }
    selectOption(timestamp, title);
  }

  function handleRowKeydown(event: KeyboardEvent, timestamp: number, title = '') {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      selectOption(timestamp, title);
    }
  }

  async function previewAudio(timestamp: number) {
    try {
      if ($currentSegmentId === `preview-${timestamp}` && $isPlaying) {
        audio.stop();
      } else {
        await audio.play(`preview-${timestamp}`, timestamp);
      }
    } catch (err) {
      console.error('Failed to preview audio:', err);
    }
  }

  async function loadAddOptions() {
    if (chapterId === null) return;

    loading = true;
    error = null;

    try {
      const options = await api.chapters.getAddOptions(chapterId);
      // Before assigning addOptions, so the auto-queue effect never sees a stale cache
      snippetTranscripts.setCacheKey(options.transcript_cache_key);
      addOptions = options;

      if (addOptions) {
        if (editorSettings.show_formatted_time && editorSettings.show_fractional_seconds === false) {
          addOptions.min_timestamp = Math.ceil(addOptions.min_timestamp);
          addOptions.max_timestamp = Math.floor(addOptions.max_timestamp);
        }

        if (defaultTab && getAvailableTabs().includes(defaultTab)) {
          activeTab = defaultTab;
        } else if (addOptions.detected_cues && addOptions.detected_cues.length > 0) {
          activeTab = 'detected_cue';
        } else {
          activeTab = 'timestamp';
        }

        originalTimestamp = addOptions.min_timestamp;
        manualTimestamp = formatTimestamp(addOptions.min_timestamp);
        if (activeTab === 'timestamp') {
          selectedTimestamp = addOptions.min_timestamp;
        }
      }
    } catch (err) {
      error = handleApiError(err);
    } finally {
      loading = false;
    }
  }

  // Prevent background scrolling when modal is open
  $effect(() => {
    if (isOpen) {
      const originalOverflow = document.body.style.overflow;
      const originalPosition = document.body.style.position;
      const originalTop = document.body.style.top;
      const originalWidth = document.body.style.width;
      const scrollY = window.scrollY;

      document.body.style.overflow = 'hidden';
      document.body.style.position = 'fixed';
      document.body.style.top = `-${scrollY}px`;
      document.body.style.width = '100%';

      return () => {
        document.body.style.overflow = originalOverflow;
        document.body.style.position = originalPosition;
        document.body.style.top = originalTop;
        document.body.style.width = originalWidth;
        window.scrollTo(0, scrollY);
      };
    }
  });

  // Handle dialog open/close
  $effect(() => {
    if (isOpen && chapterId != null) {
      loadAddOptions();
    } else if (isOpen === false) {
      if ($isPlaying && $currentSegmentId && $currentSegmentId.startsWith('preview-')) {
        audio.stop();
      }

      addOptions = null;
      selectedTimestamp = null;
      selectedTitle = '';
      manualTimestamp = '';
      originalTimestamp = null;
      activeTab = 'timestamp';
      error = null;
      scanning = false;
      autoAsrOverride = null;
      snippetTranscripts.clearQueue();
    }
  });

  async function startPartialScan(scanType: string) {
    if (!chapterId) return;
    scanning = true;
    error = null;
    try {
      await api.chapters.startPartialScan(chapterId, scanType);
      close(); // Pipeline takes over; dialog will re-open when scan completes
    } catch (err) {
      error = handleApiError(err);
      scanning = false;
    }
  }

  async function handleConfirm(transcribe = false) {
    if (!selectedTimestamp) return;

    const timestamp = selectedTimestamp;
    const title = selectedTitle;
    // Reuse a transcript already shown in the table rather than transcribing the same audio again
    const status = transcribe ? snippetStatus($snippetTranscripts, timestamp) : null;
    const transcript = status?.state === 'done' ? status.transcript : undefined;

    onconfirm?.({ timestamp, title });
    close();

    try {
      await api.chapters.add({
        timestamp,
        title,
        transcribe,
        ...(transcript !== undefined && { transcript }),
      });
    } catch (err) {
      console.error('Failed to add chapter:', err);
    }
  }

  function handleCancel() {
    oncancel?.();
    close();
  }

  function close() {
    if ($isPlaying) {
      audio.stop();
    }
    addOptions = null;
    selectedTimestamp = null;
    selectedTitle = '';
    manualTimestamp = '';
    originalTimestamp = null;
    activeTab = 'timestamp';
    error = null;
    scanning = false;
    autoAsrOverride = null;
    snippetTranscripts.clearQueue();
    isOpen = false;
  }

  function handleBackdropClick(event: MouseEvent) {
    if (event.target === event.currentTarget) {
      handleCancel();
    }
  }

  function handleBackdropKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      handleCancel();
    }
  }
</script>

{#snippet transcriptHeader()}
  <th class="transcript-header">
    <div class="transcript-header-content">
      Transcript
      <label
        class="auto-asr-toggle"
        use:tooltip={'Automatically transcribe the items in view, top to bottom, using your ASR "Transcription Length"'}
      >
        <input type="checkbox" checked={autoAsrEnabled} onchange={(e) => toggleAutoAsr(e.currentTarget.checked)} />
        <span>Auto<span class="auto-asr-label-long">&nbsp;Transcribe</span></span>
      </label>
    </div>
  </th>
{/snippet}

{#snippet transcriptCell(timestamp: number)}
  {@const status = snippetStatus($snippetTranscripts, timestamp)}
  <td class="transcript-cell">
    {#if status.state === 'done'}
      {#if status.transcript}
        <span class="transcript-text" title={status.transcript}>{status.transcript}</span>
      {:else}
        <span class="no-speech">&lt;no speech&gt;</span>
      {/if}
    {:else if status.state === 'active'}
      <span class="transcript-status" aria-label="Transcribing">
        <LoaderCircle size="16" class="transcribing-icon" />
      </span>
    {:else}
      <button
        class="transcribe-button"
        class:queued={status.state === 'queued'}
        class:failed={status.state === 'error'}
        onclick={(e) => {
          e.stopPropagation();
          snippetTranscripts.enqueue(timestamp);
        }}
        aria-label={status.state === 'queued' ? 'Transcribe next' : 'Transcribe'}
        use:tooltip={status.state === 'queued'
          ? 'Queued (click to transcribe next)'
          : status.state === 'error'
            ? `${status.error} (click to retry)`
            : 'Transcribe'}
      >
        {#if status.state === 'queued'}
          <Clock size="16" />
        {:else if status.state === 'error'}
          <CircleAlert size="16" />
        {:else}
          <Mic size="16" />
        {/if}
      </button>
    {/if}
  </td>
{/snippet}

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
          <h3>
            Add Chapter from… &nbsp;&nbsp;<DocLink
              path="/editor/add-chapter-dialog/"
              featureName="Adding Chapters"
              size="14"
            />
          </h3>
          <button class="close-button" onclick={handleCancel} aria-label="Close">
            <X size="20" />
          </button>
        </div>

        <div class="modal-body">
          {#if error}
            <div class="alert alert-danger">
              {error}
            </div>
          {/if}

          {#if loading}
            <div class="loading-state">
              <div class="spinner"></div>
              <p>Loading add options…</p>
            </div>
          {:else if addOptions}
            <!-- Tab Navigation -->
            <div class="tabs">
              {#each getAvailableTabs() as tab}
                <button class="tab-button" class:active={activeTab === tab} onclick={() => selectTab(tab)}>
                  {#if tab === 'timestamp'}
                    Timestamp
                  {:else if tab === 'detected_cue'}
                    Detected Cues
                  {:else if tab === 'deleted'}
                    Deleted
                  {:else}
                    {tab}
                  {/if}
                </button>
              {/each}
            </div>

            <!-- Tab Content -->
            <div class="tab-content">
              {#if activeTab === 'timestamp'}
                <div class="timestamp-tab-wrapper">
                  <div class="timestamp-input-section">
                    <div class="timestamp-input-group">
                      <input
                        id="manual-timestamp"
                        type="text"
                        bind:value={manualTimestamp}
                        oninput={handleTimestampInput}
                        onkeydown={handleTimestampKeydown}
                        class="timestamp-input"
                        placeholder={editorSettings.show_formatted_time
                          ? editorSettings.show_fractional_seconds === false
                            ? 'mm:ss'
                            : 'mm:ss.ss'
                          : 'seconds'}
                      />
                      <div class="timestamp-controls">
                        <button
                          class="timestamp-adjust"
                          onclick={() => adjustTimestamp(1)}
                          aria-label="Increase by 1 second"
                          use:tooltip={'Increase by 1 second'}
                        >
                          <ChevronUp size="16" />
                        </button>
                        <button
                          class="timestamp-adjust"
                          onclick={() => adjustTimestamp(-1)}
                          aria-label="Decrease by 1 second"
                          use:tooltip={'Decrease by 1 second'}
                        >
                          <ChevronDown size="16" />
                        </button>
                      </div>
                      {#if selectedTimestamp != null}
                        {@const ts = selectedTimestamp}
                        <button
                          class="preview-button"
                          class:playing={$currentSegmentId === `preview-${ts}` && $isPlaying}
                          onclick={() => {
                            selectOption(ts);
                            previewAudio(ts);
                          }}
                          aria-label="Preview audio"
                          use:tooltip={'Preview audio'}
                        >
                          {#if $currentSegmentId === `preview-${ts}` && $isPlaying}
                            <Pause size="16" />
                          {:else}
                            <Play size="16" />
                          {/if}
                        </button>
                      {/if}
                    </div>
                    {#if manualTimestamp && !isValidTimestamp(parseTimestamp(manualTimestamp))}
                      <div class="validation-error">
                        Timestamp must be between {formatTimestamp(addOptions.min_timestamp)} and
                        {formatTimestamp(addOptions.max_timestamp)}
                      </div>
                    {/if}
                  </div>
                </div>
              {:else if activeTab === 'detected_cue'}
                <div class="cue-tab-wrapper">
                  <div class="cue-list-scroll">
                    {#if getSortedDetectedCues().length > 0}
                      <div class="cue-table-section">
                        <table class="cue-table">
                          <thead>
                            <tr>
                              <th style="width: 1px"></th>
                              <th style="width: 1px"></th>
                              <th style="width: 1px" class="sortable" onclick={() => toggleSort('gap')}>
                                Gap
                                {#if sortBy === 'gap'}
                                  {#if sortOrder === 'asc'}
                                    <ArrowUp size="14" class="sort-icon" />
                                  {:else}
                                    <ArrowDown size="14" class="sort-icon" />
                                  {/if}
                                {/if}
                              </th>
                              <th style="width: 1px" class="sortable" onclick={() => toggleSort('timestamp')}>
                                Timestamp
                                {#if sortBy === 'timestamp'}
                                  {#if sortOrder === 'asc'}
                                    <ArrowUp size="14" class="sort-icon" />
                                  {:else}
                                    <ArrowDown size="14" class="sort-icon" />
                                  {/if}
                                {/if}
                              </th>
                              {@render transcriptHeader()}
                            </tr>
                          </thead>
                          <tbody>
                            {#each getSortedDetectedCues() as cue}
                              <tr
                                class="cue-row clickable-row"
                                use:trackInView={cue.timestamp}
                                class:selected={selectedTimestamp === cue.timestamp}
                                onclick={(e) => handleRowClick(e, cue.timestamp)}
                                onkeydown={(e) => handleRowKeydown(e, cue.timestamp)}
                                tabindex="0"
                                role="button"
                                aria-label="Select detected cue at {formatTimestamp(
                                  cue.timestamp,
                                )} with {cue.gap.toFixed(1)}s gap"
                              >
                                <td class="radio-cell">
                                  <input
                                    type="radio"
                                    name="detected-cue"
                                    checked={selectedTimestamp === cue.timestamp}
                                    onchange={() => selectOption(cue.timestamp)}
                                  />
                                </td>
                                <td class="preview-cell">
                                  <button
                                    class="preview-button"
                                    class:playing={$currentSegmentId === `preview-${cue.timestamp}` && $isPlaying}
                                    onclick={() => {
                                      selectOption(cue.timestamp);
                                      previewAudio(cue.timestamp);
                                    }}
                                    aria-label="Preview audio"
                                    use:tooltip={'Preview audio'}
                                  >
                                    {#if $currentSegmentId === `preview-${cue.timestamp}` && $isPlaying}
                                      <Pause size="16" />
                                    {:else}
                                      <Play size="16" />
                                    {/if}
                                  </button>
                                </td>
                                <td class="gap-cell">{cue.gap.toFixed(1)}s</td>
                                <td class="timestamp-cell">{formatTimestamp(cue.timestamp)}</td>
                                {@render transcriptCell(cue.timestamp)}
                              </tr>
                            {/each}
                          </tbody>
                        </table>
                      </div>
                    {:else}
                      <div class="empty-cues-state">
                        {#if addOptions.allow_normal_scan && addOptions.allow_vad_scan}
                          This region has not been scanned for cues yet.
                        {:else if addOptions.allow_vad_scan}
                          No cues found in this region. Try clicking "Detect Cues [Dramatized]".
                        {:else}
                          No cues found in this region.
                        {/if}
                      </div>
                    {/if}
                  </div>

                  {#if addOptions.allow_normal_scan || addOptions.allow_vad_scan}
                    <div class="scan-actions">
                      {#if addOptions.allow_normal_scan}
                        <button
                          class="btn btn-secondary btn-scan"
                          onclick={() => startPartialScan('normal')}
                          disabled={scanning}
                          use:tooltip={'Scan this region for chapter cues using silence detection'}
                        >
                          <ScanSearch size="16" />
                          Detect {getSortedDetectedCues().length > 0 ? 'Additional ' : ''}Cues
                        </button>
                      {/if}
                      {#if addOptions.allow_vad_scan}
                        <button
                          class="btn btn-secondary btn-scan"
                          onclick={() => startPartialScan('vad')}
                          disabled={scanning}
                          use:tooltip={'Scan this region for chapter cues using voice activity detection (for dramatized audiobooks)'}
                        >
                          <AudioLines size="16" />
                          Detect {getSortedDetectedCues().length > 0 ? 'Additional ' : ''}Cues [Dramatized]
                        </button>
                      {/if}
                    </div>
                  {/if}
                </div>
              {:else if activeTab === 'deleted'}
                <div class="cue-table-section">
                  <table class="cue-table">
                    <thead>
                      <tr>
                        <th style="width: 1px"></th>
                        <th style="width: 1px"></th>
                        <th style="width: 1px">Timestamp</th>
                        <th>Title</th>
                        {@render transcriptHeader()}
                      </tr>
                    </thead>
                    <tbody>
                      {#each addOptions.deleted as deletedChapter}
                        <tr
                          class="cue-row clickable-row"
                          use:trackInView={deletedChapter.timestamp}
                          class:selected={selectedTimestamp === deletedChapter.timestamp}
                          onclick={(e) => handleRowClick(e, deletedChapter.timestamp, deletedChapter.title)}
                          onkeydown={(e) => handleRowKeydown(e, deletedChapter.timestamp, deletedChapter.title)}
                          tabindex="0"
                          role="button"
                          aria-label="Select deleted chapter '{deletedChapter.title}' at {formatTimestamp(
                            deletedChapter.timestamp,
                          )}"
                        >
                          <td class="radio-cell">
                            <input
                              type="radio"
                              name="deleted-chapter"
                              checked={selectedTimestamp === deletedChapter.timestamp}
                              onchange={() => selectOption(deletedChapter.timestamp, deletedChapter.title)}
                            />
                          </td>
                          <td class="preview-cell">
                            <button
                              class="preview-button"
                              class:playing={$currentSegmentId === `preview-${deletedChapter.timestamp}` && $isPlaying}
                              onclick={() => {
                                selectOption(deletedChapter.timestamp, deletedChapter.title);
                                previewAudio(deletedChapter.timestamp);
                              }}
                              aria-label="Preview audio"
                              use:tooltip={'Preview audio'}
                            >
                              {#if $currentSegmentId === `preview-${deletedChapter.timestamp}` && $isPlaying}
                                <Pause size="16" />
                              {:else}
                                <Play size="16" />
                              {/if}
                            </button>
                          </td>
                          <td class="timestamp-cell">{formatTimestamp(deletedChapter.timestamp)}</td>
                          <td class="title-cell">{deletedChapter.title}</td>
                          {@render transcriptCell(deletedChapter.timestamp)}
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                </div>
              {:else if addOptions.chapter_refs && addOptions.chapter_refs[activeTab]}
                <div class="cue-table-section">
                  <table class="cue-table">
                    <thead>
                      <tr>
                        <th style="width: 1px"></th>
                        <th style="width: 1px"></th>
                        <th style="width: 1px">Timestamp</th>
                        <th>Title</th>
                        {@render transcriptHeader()}
                      </tr>
                    </thead>
                    <tbody>
                      {#each addOptions.chapter_refs[activeTab] as chapter}
                        <tr
                          class="cue-row clickable-row"
                          use:trackInView={chapter.timestamp}
                          class:selected={selectedTimestamp === chapter.timestamp}
                          onclick={(e) => handleRowClick(e, chapter.timestamp, chapter.title)}
                          onkeydown={(e) => handleRowKeydown(e, chapter.timestamp, chapter.title)}
                          tabindex="0"
                          role="button"
                          aria-label="Select chapter '{chapter.title}' at {formatTimestamp(chapter.timestamp)}"
                        >
                          <td class="radio-cell">
                            <input
                              type="radio"
                              name="chapter"
                              checked={selectedTimestamp === chapter.timestamp}
                              onchange={() => selectOption(chapter.timestamp, chapter.title)}
                            />
                          </td>
                          <td class="preview-cell">
                            <button
                              class="preview-button"
                              class:playing={$currentSegmentId === `preview-${chapter.timestamp}` && $isPlaying}
                              onclick={() => {
                                selectOption(chapter.timestamp, chapter.title);
                                previewAudio(chapter.timestamp);
                              }}
                              aria-label="Preview audio"
                              use:tooltip={'Preview audio'}
                            >
                              {#if $currentSegmentId === `preview-${chapter.timestamp}` && $isPlaying}
                                <Pause size="16" />
                              {:else}
                                <Play size="16" />
                              {/if}
                            </button>
                          </td>
                          <td class="timestamp-cell">{formatTimestamp(chapter.timestamp)}</td>
                          <td class="title-cell">{chapter.title}</td>
                          {@render transcriptCell(chapter.timestamp)}
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                </div>
              {/if}
            </div>
          {/if}
        </div>

        <div class="modal-footer">
          {#if addOptions}
            <div class="time-boundaries">
              <span>{formatTimestamp(addOptions.min_timestamp)}</span>
              <MoveHorizontal size="16" />
              <span>{formatTimestamp(addOptions.max_timestamp)}</span>
            </div>
          {/if}
          <button class="btn btn-secondary" onclick={handleCancel}> Cancel </button>
          <div class="segmented-button">
            <button
              class="btn btn-primary segmented-left"
              onclick={() => handleConfirm(false)}
              disabled={!selectedTimestamp}
            >
              Add chapter at {selectedTimestamp ? formatTimestamp(selectedTimestamp) : ''}
            </button>
            <button
              class="btn btn-primary segmented-right"
              onclick={() => handleConfirm(true)}
              disabled={!selectedTimestamp}
              aria-label="Add and transcribe"
              use:tooltip={{ text: 'Add and transcribe', delay: 0 }}
            >
              <Mic size="16" />
            </button>
          </div>
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
    max-width: 720px;
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
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1rem 0.5rem 1.5rem;
  }

  .modal-header h3 {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-primary);
  }

  .close-button {
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
  }

  .modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
    padding: 1rem;
    border-top: 1px solid var(--border-color);
  }

  .loading-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    text-align: center;
  }

  .spinner {
    width: 2rem;
    height: 2rem;
    border: 2px solid var(--border-color);
    border-top: 2px solid var(--primary);
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-bottom: 1rem;
  }

  @keyframes spin {
    0% {
      transform: rotate(0deg);
    }
    100% {
      transform: rotate(360deg);
    }
  }

  .tabs {
    display: flex;
    padding: 0 1rem;
    overflow: auto;
  }

  .tab-button {
    background: none;
    border: none;
    padding: 0.75rem 1rem;
    color: var(--text-secondary);
    cursor: pointer;
    border-bottom: 2px solid transparent;
    white-space: nowrap;
    font-size: 0.875rem;
    font-weight: 500;
  }

  .tab-button:hover {
    color: var(--text-primary);
    background: var(--hover-bg);
  }

  .tab-button.active {
    color: var(--primary);
    border-bottom-color: var(--primary);
  }

  .tab-content {
    min-height: 200px;
    max-height: 400px;
    overflow-y: auto;
  }

  .time-boundaries {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: start;
    gap: 0.5rem;
    margin-left: 0.5rem;
    color: var(--text-secondary);
    font-size: 0.9rem;
  }

  .timestamp-tab-wrapper {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    min-height: 200px;
  }

  .timestamp-input-section {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
  }

  .timestamp-input-group {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .timestamp-input {
    padding: 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: 0.25rem;
    background: var(--bg-secondary);
    color: var(--text-primary);
    font-family: monospace;
  }

  .timestamp-input:focus {
    border-color: var(--primary);
    outline: none;
  }

  .timestamp-controls {
    display: flex;
    flex-direction: column;
  }

  .timestamp-adjust {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    color: var(--text-secondary);
    cursor: pointer;
    padding: 0.25rem;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 2rem;
    height: 1rem;
  }

  .timestamp-adjust:hover {
    background: var(--hover-bg);
    color: var(--text-primary);
  }

  .timestamp-adjust:first-child {
    border-top-left-radius: 0.25rem;
    border-top-right-radius: 0.25rem;
    border-bottom: none;
  }

  .timestamp-adjust:last-child {
    border-bottom-left-radius: 0.25rem;
    border-bottom-right-radius: 0.25rem;
  }

  .preview-button {
    width: 2rem;
    height: 2rem;
    border-radius: 50%;
    border: none;
    background-color: transparent;
    color: var(--primary-contrast);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.75rem;
    transition: all 0.2s ease;
  }

  .preview-button:hover {
    color: white;
    background-color: var(--primary-hover);
    transform: scale(1.1);
  }

  .preview-button.playing {
    color: white;
    background-color: var(--primary-color);
  }

  .validation-error {
    color: var(--danger);
    font-size: 0.875rem;
  }

  .cue-tab-wrapper {
    display: flex;
    flex-direction: column;
    min-height: 200px;
    max-height: 400px;
    overflow: hidden;
  }

  .cue-list-scroll {
    flex: 1;
    overflow-y: auto;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }

  .empty-cues-state {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1rem;
    color: var(--text-secondary);
    font-size: 0.875rem;
  }

  .scan-actions {
    display: flex;
    justify-content: center;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    flex-wrap: wrap;
  }

  .btn-secondary.btn-scan {
    border-color: var(--primary);
  }

  .btn-scan :global(svg) {
    color: var(--primary);
  }

  .cue-table-section {
    overflow-x: auto;
  }

  .cue-table {
    width: 100%;
    border-collapse: collapse;
    margin: 0 auto;
  }

  .cue-table th,
  .cue-table td {
    padding: 0.75rem;
    text-align: left;
    border-bottom: 1px solid var(--border-color);
  }

  .cue-table th {
    background: var(--bg-secondary);
    font-weight: 600;
    color: var(--text-primary);
  }

  .cue-table th.sortable {
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
  }

  .cue-table th.sortable:hover {
    background: var(--hover-bg);
  }

  .radio-cell {
    padding: 0.75rem 0.75rem 0.75rem 1.5rem !important;
    accent-color: var(--primary);
  }

  .preview-cell {
    padding: 0.75rem 0rem !important;
  }

  .cue-row {
    transition: background-color 0.1s ease;
  }

  .cue-row:hover {
    background: var(--hover-bg);
  }

  .cue-row.selected {
    background: var(--primary-light);
  }

  .clickable-row {
    cursor: pointer;
  }

  .clickable-row:focus {
    outline: 2px solid var(--primary);
    outline-offset: -2px;
  }

  .clickable-row:hover {
    background: var(--hover-bg);
  }

  .clickable-row.selected:hover {
    background: var(--primary-light);
  }

  .gap-cell,
  .timestamp-cell {
    font-family: monospace;
    font-size: 0.875rem;
  }

  .title-cell {
    color: var(--text-primary);
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* Mirrors .radio-cell's 1.5rem left inset so the table sits symmetrically in the dialog */
  .transcript-header,
  .transcript-cell {
    padding-right: 1.5rem !important;
  }

  .transcript-header-content {
    display: flex;
    align-items: center;
    gap: 1rem;
    white-space: nowrap;
  }

  .auto-asr-toggle {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    font-weight: 400;
    font-size: 0.8125rem;
    color: var(--text-secondary);
    cursor: pointer;
    user-select: none;
    accent-color: var(--primary);
  }

  /* max-width: 0 lets the cell take the leftover width and ellipsize instead of widening the table */
  .transcript-cell {
    width: 50%;
    max-width: 0;
    padding-top: 0 !important;
    padding-bottom: 0 !important;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.875rem;
  }

  .transcript-text {
    color: var(--text-primary);
  }

  .no-speech {
    color: var(--text-secondary);
    font-style: italic;
  }

  .transcript-status {
    display: inline-flex;
    width: 2rem;
    height: 2rem;
    align-items: center;
    justify-content: center;
    color: var(--primary);
    vertical-align: middle;
  }

  .transcript-status :global(.transcribing-icon) {
    animation: spin 1s linear infinite;
  }

  .transcribe-button {
    width: 2rem;
    height: 2rem;
    border-radius: 50%;
    border: none;
    background-color: transparent;
    color: var(--text-secondary);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    vertical-align: middle;
    transition: all 0.2s ease;
  }

  .transcribe-button:hover {
    color: white;
    background-color: var(--primary-hover);
  }

  .transcribe-button.queued {
    opacity: 0.6;
  }

  .transcribe-button.failed {
    color: var(--danger);
  }

  .alert {
    padding: 0.75rem;
    border-radius: 0.25rem;
    margin-bottom: 1rem;
  }

  .alert-danger {
    background: var(--danger-light);
    color: var(--danger-dark);
    border: 1px solid var(--danger);
  }

  .btn {
    padding: 0.5rem 1rem;
    border: 1px solid transparent;
    border-radius: 0.25rem;
    cursor: pointer;
    font-size: 0.875rem;
    font-weight: 500;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    transition: all 0.2s ease;
  }

  .btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .btn-primary {
    background: var(--primary);
    color: white;
  }

  .btn-primary:hover:not(:disabled) {
    background: var(--primary-hover);
  }

  .segmented-button {
    display: flex;
  }

  .segmented-left {
    border-top-right-radius: 0;
    border-bottom-right-radius: 0;
    border-right: 1px solid rgba(255, 255, 255, 0.2);
  }

  .segmented-right {
    border-top-left-radius: 0;
    border-bottom-left-radius: 0;
    padding-left: 0.5rem;
    padding-right: 0.5rem;
  }

  .btn-secondary {
    background: var(--bg-secondary);
    color: var(--text-primary);
    border-color: var(--border-color);
  }

  .btn-secondary:hover:not(:disabled) {
    background: var(--hover-bg);
  }

  @media (max-width: 768px) {
    /* Narrow dialogs leave the Transcript column little room; fall back to just "Auto" */
    .auto-asr-label-long {
      display: none;
    }

    .modal-dialog {
      width: 95%;
      max-height: 95vh;
    }

    .modal-header,
    .modal-body,
    .modal-footer {
      padding: 1rem;
    }

    .timestamp-input-group {
      flex-direction: column;
      align-items: stretch;
    }

    .timestamp-controls {
      flex-direction: row;
      width: 100%;
    }

    .timestamp-adjust {
      flex: 1;
      height: 2rem;
    }

    .timestamp-adjust:first-child {
      border-radius: 0.25rem 0 0 0.25rem;
      border-right: none;
      border-bottom: 1px solid var(--border-color);
    }

    .timestamp-adjust:last-child {
      border-radius: 0 0.25rem 0.25rem 0;
    }

    .tabs {
      overflow-x: scroll;
    }

    .cue-table {
      font-size: 0.75rem;
    }

    .cue-table th,
    .cue-table td {
      padding: 0.5rem;
    }
  }
</style>
