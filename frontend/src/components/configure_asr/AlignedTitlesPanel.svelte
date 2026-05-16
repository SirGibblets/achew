<script lang="ts">
  import { slide } from 'svelte/transition';
  import { SvelteSet } from 'svelte/reactivity';
  import { audio, currentSegmentId, isPlaying } from '../../stores/audio';
  import CircleQuestionMark from '@lucide/svelte/icons/circle-question-mark';
  import Pause from '@lucide/svelte/icons/pause';
  import Play from '@lucide/svelte/icons/play';
  import type { ExistingCueSource } from '../../types/sources';
  import type { PreassignedTitle } from '../../types/api';
  import { alignByTimestamp } from '../../utils/alignment';
  import { onDestroy } from 'svelte';

  interface Props {
    cues: number[];
    cueSources: ExistingCueSource[];
    preassignedTitles: PreassignedTitle[];
  }

  let { cues, cueSources, preassignedTitles = $bindable([]) }: Props = $props();

  interface CueTarget {
    id: string;
    timestamp: number;
    idx: number;
  }

  let enabled = $state(false);
  let selectedSourceId = $state<string | null>(null);
  let showUnaligned = $state(false);

  let checked = $state<Record<string, boolean>>({});
  let lastSourceId = $state<string | null>(null);
  let lastClickedIdx = $state<number | null>(null);

  let targets = $derived<CueTarget[]>(cues.map((ts, i) => ({ id: `cue-${i}`, timestamp: ts, idx: i })));

  let selectedSource = $derived(cueSources.find((s) => s.id === selectedSourceId) ?? null);

  let alignedMap = $derived(alignByTimestamp(targets, selectedSource?.cues ?? []));
  let alignedTargetIds = $derived(targets.map((t) => t.id).filter((id) => alignedMap.has(id)));

  /* Source chapters whose timestamps don't line up with any selected cue, in source order. */
  let unalignedSourceChapters = $derived.by(() => {
    const used = new SvelteSet<number>();
    for (const pair of alignedMap.values()) used.add(pair.sourceChapterIndex);
    return (selectedSource?.cues ?? [])
      .map((sourceChapter, i) => ({
        id: `src-${i}`,
        timestamp: sourceChapter.timestamp,
        title: sourceChapter.title,
        idx: i,
      }))
      .filter((c) => !used.has(c.idx));
  });

  let unalignedCount = $derived(unalignedSourceChapters.length);

  /* Unified, timeline-ordered render list:
   *   - 'aligned' rows positioned at the selected cue's timestamp
   *   - 'unaligned' rows for source chapters that weren't matched, at the source chapter's timestamp
   */
  type AlignedRow = { kind: 'aligned'; id: string; timestamp: number; target: (typeof targets)[number] };
  type UnalignedRow = { kind: 'unaligned'; id: string; timestamp: number; title: string };
  let renderRows = $derived.by<(AlignedRow | UnalignedRow)[]>(() => {
    const rows: (AlignedRow | UnalignedRow)[] = [];
    for (const target of targets) {
      if (alignedMap.has(target.id)) {
        rows.push({ kind: 'aligned', id: target.id, timestamp: target.timestamp, target });
      }
    }
    if (showUnaligned) {
      for (const sourceChapter of unalignedSourceChapters) {
        rows.push({
          kind: 'unaligned',
          id: sourceChapter.id,
          timestamp: sourceChapter.timestamp,
          title: sourceChapter.title,
        });
      }
    }
    rows.sort((a, b) => a.timestamp - b.timestamp);
    return rows;
  });

  /* Pick the first source as default; if the selected one disappears (e.g. SOURCES_UPDATE), fall back. */
  $effect(() => {
    if (cueSources.length === 0) {
      selectedSourceId = null;
      return;
    }
    if (!selectedSourceId || !cueSources.some((s) => s.id === selectedSourceId)) {
      selectedSourceId = cueSources[0].id;
    }
  });

  /* When the source changes, reset selections (all aligned rows re-check). */
  $effect(() => {
    const sourceId = selectedSource?.id ?? null;
    const pairs = alignedMap;
    if (sourceId !== lastSourceId) {
      const next: Record<string, boolean> = {};
      for (const [id] of pairs) {
        next[id] = true;
      }
      checked = next;
      lastClickedIdx = null;
      lastSourceId = sourceId;
    }
  });

  /* Sync selections up to the parent. Reports empty when feature is disabled. */
  $effect(() => {
    if (!enabled) {
      preassignedTitles = [];
      return;
    }
    const result: PreassignedTitle[] = [];
    for (const [targetId, pair] of alignedMap) {
      if (checked[targetId]) {
        result.push({ cue_index: pair.target.idx, title: pair.sourceTitle });
      }
    }
    preassignedTitles = result;
  });

  onDestroy(() => {
    audio.stop();
  });

  function handleCheck(targetId: string, event: MouseEvent): void {
    const idx = alignedTargetIds.indexOf(targetId);
    const newValue = !checked[targetId];

    const next: Record<string, boolean> = { ...checked };
    if (event.shiftKey && lastClickedIdx !== null && lastClickedIdx !== idx) {
      const lo = Math.min(lastClickedIdx, idx);
      const hi = Math.max(lastClickedIdx, idx);
      for (let i = lo; i <= hi; i++) {
        next[alignedTargetIds[i]] = newValue;
      }
    } else {
      next[targetId] = newValue;
    }
    checked = next;
    lastClickedIdx = idx;
  }

  async function playSegment(targetId: string, timestamp: number): Promise<void> {
    try {
      if ($currentSegmentId === targetId && $isPlaying) {
        audio.stop();
      } else {
        await audio.play(targetId, timestamp);
      }
    } catch {
      // silently ignore
    }
  }

  function formatTimestamp(seconds: number): string {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  }

  let selectedAlignedCount = $derived(preassignedTitles.length);

  let revealEl = $state<HTMLDivElement | null>(null);

  function scrollIntoViewAfterTransition(): void {
    revealEl?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }
</script>

<div class="aligned-titles-panel" class:disabled={!enabled}>
  <div class="header-row">
    <label class="enable-label">
      <input type="checkbox" bind:checked={enabled} />
      <span>
        {#if enabled}
          Use <strong>{selectedAlignedCount}</strong> aligned title{selectedAlignedCount === 1 ? '' : 's'} from
        {:else}
          Use aligned titles from
        {/if}
      </span>
    </label>
    <select class="source-select" bind:value={selectedSourceId} disabled={!enabled}>
      {#each cueSources as src (src.id)}
        <option value={src.id}>{src.name} ({src.cues.length} chapters)</option>
      {/each}
    </select>
    <div
      class="help-icon"
      data-tooltip="Use titles from a chapter source whose timestamps line up with pending chapters. Selected titles are applied directly, while the remaining titles will be transcribed."
    >
      <CircleQuestionMark size="14" />
    </div>
  </div>

  {#if enabled}
    <div
      class="reveal"
      bind:this={revealEl}
      transition:slide={{ duration: 200 }}
      onintroend={scrollIntoViewAfterTransition}
    >
      {#if renderRows.length === 0}
        <p class="empty-state">
          No chapters from <strong>{selectedSource?.name ?? 'the selected source'}</strong> align with your selected cues.
        </p>
      {:else}
        <div class="chapter-list">
          {#each renderRows as row (row.id)}
            {#if row.kind === 'aligned'}
              {@const pair = alignedMap.get(row.id)!}
              <!-- svelte-ignore a11y_click_events_have_key_events -->
              <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
              <label
                class="row aligned"
                class:checked={checked[row.id]}
                onclick={(e) => {
                  e.preventDefault();
                  handleCheck(row.id, e);
                }}
              >
                <input type="checkbox" checked={checked[row.id]} />
                <span class="chapter-ts">{formatTimestamp(row.timestamp)}</span>
                <button
                  type="button"
                  class="play-btn"
                  onclick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    playSegment(row.id, row.timestamp);
                  }}
                  title="Play"
                >
                  {#if $currentSegmentId === row.id && $isPlaying}
                    <Pause size="14" />
                  {:else}
                    <Play size="14" />
                  {/if}
                </button>
                <span class="chapter-title">
                  <span class="title-aligned" class:fallback={!pair.sourceTitle}>
                    {pair.sourceTitle || 'No Title'}
                  </span>
                </span>
              </label>
            {:else}
              <div class="row unaligned">
                <input type="checkbox" class="checkbox-hidden" />
                <span class="chapter-ts unaligned">{formatTimestamp(row.timestamp)}</span>
                <button
                  type="button"
                  class="play-btn"
                  onclick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    playSegment(row.id, row.timestamp);
                  }}
                  title="Play"
                >
                  {#if $currentSegmentId === row.id && $isPlaying}
                    <Pause size="14" />
                  {:else}
                    <Play size="14" />
                  {/if}
                </button>
                <span class="chapter-title">
                  <span class="title-unaligned" class:fallback={!row.title}>
                    {row.title || 'No Title'}
                  </span>
                </span>
              </div>
            {/if}
          {/each}
        </div>
      {/if}
      <label class="show-unaligned" style:visibility={unalignedCount > 0 ? 'visible' : 'hidden'}>
        <input type="checkbox" bind:checked={showUnaligned} />
        <span>Show {unalignedCount} unaligned chapter{unalignedCount === 1 ? '' : 's'}</span>
      </label>
    </div>
  {/if}
</div>

<style>
  .aligned-titles-panel {
    width: 100%;
    max-width: 720px;
    margin: 2.5rem auto 1.5rem;
  }

  .aligned-titles-panel.disabled .source-select {
    opacity: 0.4;
  }

  .header-row {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .enable-label {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
    user-select: none;
    color: var(--text-secondary);
    font-size: 0.95rem;
  }

  .enable-label input[type='checkbox'] {
    cursor: pointer;
  }

  .source-select {
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--border-color);
    border-radius: 0.375rem;
    background: var(--bg-primary);
    color: var(--text-primary);
    font-size: 0.875rem;
    transition:
      border-color 0.2s ease,
      opacity 0.2s ease;
    max-width: 360px;
  }

  .source-select:focus {
    outline: none;
    border-color: var(--primary-color);
  }

  .source-select:disabled {
    cursor: not-allowed;
  }

  .reveal {
    margin-top: 1rem;
    padding-bottom: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .empty-state {
    color: var(--text-muted);
    font-size: 0.85rem;
    margin: 0.5rem 0;
    text-align: center;
    padding: 1rem;
    border: 1px dashed var(--border-color);
    border-radius: 8px;
  }

  .chapter-list {
    overflow-y: auto;
    max-height: 320px;
    width: 100%;
    max-width: 580px;
    margin: 0 auto;
    border: 1px solid var(--border-color);
    border-radius: 8px;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.35rem 0.75rem;
    min-height: 3.5rem;
    font-size: 0.875rem;
    user-select: none;
  }

  .row:nth-child(even) {
    background: rgba(128, 128, 128, 0.06);
  }

  .row.unaligned {
    opacity: 0.4;
  }

  .row.aligned {
    opacity: 0.5;
    cursor: pointer;
    transition: opacity 0.15s;
  }

  .row.aligned:hover {
    opacity: 0.7;
  }

  .row.aligned.checked {
    opacity: 1;
  }

  .row input[type='checkbox'] {
    flex-shrink: 0;
    cursor: pointer;
    pointer-events: none;
  }

  .checkbox-hidden {
    visibility: hidden;
  }

  .play-btn {
    flex-shrink: 0;
    width: 1.4rem;
    height: 1.4rem;
    border-radius: 50%;
    border: none;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    transition:
      color 0.15s,
      background 0.15s;
  }

  .play-btn:hover {
    color: var(--primary-color);
    background: var(--hover-bg);
  }

  .chapter-ts {
    flex-shrink: 0;
    font-family: monospace;
    font-size: 0.72rem;
    color: var(--text-muted);
    min-width: 3.5rem;
  }

  .chapter-ts.unaligned {
    text-decoration: line-through;
  }

  .chapter-title {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }

  .title-aligned {
    color: var(--text-primary);
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .row.aligned:not(.checked) .title-aligned {
    color: var(--text-secondary);
  }

  .title-unaligned {
    color: var(--text-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .fallback {
    font-style: italic;
  }

  .show-unaligned {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    align-self: center;
    margin-top: 0.25rem;
    cursor: pointer;
    user-select: none;
    color: var(--text-muted);
    font-size: 0.8rem;
  }

  .show-unaligned input[type='checkbox'] {
    cursor: pointer;
  }

  .help-icon {
    border: none;
    background: transparent;
    color: var(--text-secondary);
    padding: 2px;
    border-radius: 50%;
    transition: all 0.2s ease;
    position: relative;
    cursor: help;
    display: flex;
  }

  .help-icon:hover {
    color: var(--primary-color);
    background: var(--bg-tertiary);
  }

  .help-icon[data-tooltip]:hover::after {
    content: attr(data-tooltip);
    position: absolute;
    bottom: 100%;
    left: 50%;
    transform: translateX(-50%);
    margin-bottom: 8px;
    padding: 8px 12px;
    background: var(--bg-primary);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    font-size: 0.875rem;
    line-height: 1.4;
    white-space: normal;
    min-width: 280px;
    max-width: 480px;
    z-index: 1000;
    animation: tooltipFadeIn 0.2s ease-out;
  }

  .help-icon[data-tooltip]:hover::before {
    content: '';
    position: absolute;
    bottom: 100%;
    left: 50%;
    transform: translateX(-50%);
    margin-bottom: -3px;
    border: 6px solid transparent;
    border-top-color: var(--border-color);
    z-index: 1001;
  }

  @keyframes tooltipFadeIn {
    from {
      opacity: 0;
      transform: translateX(-50%) translateY(4px);
    }
    to {
      opacity: 1;
      transform: translateX(-50%) translateY(0);
    }
  }
</style>
