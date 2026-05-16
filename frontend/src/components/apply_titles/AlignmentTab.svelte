<script lang="ts">
  import CornerDownRight from '@lucide/svelte/icons/corner-down-right';
  import Pause from '@lucide/svelte/icons/pause';
  import Play from '@lucide/svelte/icons/play';
  import { audio, currentSegmentId, isPlaying } from '../../stores/audio';
  import { chapters } from '../../stores/session';
  import type { ExistingCueSource } from '../../types/sources';
  import { alignByTimestamp } from '../../utils/alignment';

  interface TitleMapping {
    chapter_id: string;
    new_title: string;
  }

  interface Props {
    source?: ExistingCueSource | null;
    mappings?: TitleMapping[];
  }

  let { source = null, mappings = $bindable([]) }: Props = $props();

  async function playChapter(chapterId: string): Promise<void> {
    try {
      if ($currentSegmentId === chapterId && $isPlaying) {
        audio.stop();
      } else {
        const chapter = allChapters.find((ch) => ch.id === chapterId);
        if (chapter) await audio.play(chapterId, chapter.timestamp);
      }
    } catch {
      // silently ignore
    }
  }

  let allChapters = $derived($chapters.filter((c) => !c.deleted));

  let alignedMap = $derived(alignByTimestamp(allChapters, source?.cues ?? []));

  let alignedCount = $derived(alignedMap.size);

  let checked = $state<Record<string, boolean>>({});
  let lastSourceId = $state<string | null>(null);

  let lastClickedIdx = $state<number | null>(null);

  let alignedIds = $derived(allChapters.map((ch) => ch.id).filter((id) => alignedMap.has(id)));

  function handleCheck(chapterId: string, event: MouseEvent): void {
    const idx = alignedIds.indexOf(chapterId);
    const newValue = !checked[chapterId];

    const next: Record<string, boolean> = { ...checked };
    if (event.shiftKey && lastClickedIdx !== null && lastClickedIdx !== idx) {
      const lo = Math.min(lastClickedIdx, idx);
      const hi = Math.max(lastClickedIdx, idx);
      for (let i = lo; i <= hi; i++) {
        next[alignedIds[i]] = newValue;
      }
    } else {
      next[chapterId] = newValue;
    }
    checked = next;

    lastClickedIdx = idx;
  }

  $effect(() => {
    const sourceId = source?.id ?? null;
    const pairs = alignedMap;
    if (sourceId !== lastSourceId) {
      const next: Record<string, boolean> = {};
      for (const [id] of pairs) {
        next[id] = true;
      }
      checked = next;
      lastSourceId = sourceId;
    }
  });

  $effect(() => {
    const result: TitleMapping[] = [];
    for (const [chapterId, pair] of alignedMap) {
      if (checked[chapterId]) {
        result.push({
          chapter_id: chapterId,
          new_title: pair.sourceTitle,
        });
      }
    }
    mappings = result;
  });

  function formatTimestamp(seconds: number): string {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  }
</script>

<p class="tab-explanation">
  {#if alignedCount === 0}
    No chapters with matching timestamps were found in the selected source.
  {:else}
    {alignedCount} of {allChapters.length} chapters have a matching (timestamp-aligned) chapter in the selected source.<br
    />Uncheck any titles you don't want to apply.
  {/if}
</p>

<div class="chapter-list">
  {#each allChapters as chapter (chapter.id)}
    {@const pair = alignedMap.get(chapter.id)}
    {#if pair}
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
      <label
        class="row aligned"
        class:checked={checked[chapter.id]}
        onclick={(e) => {
          e.preventDefault();
          handleCheck(chapter.id, e);
        }}
      >
        <input type="checkbox" checked={checked[chapter.id]} />
        <span class="chapter-ts">{formatTimestamp(chapter.timestamp)}</span>
        <button
          type="button"
          class="play-btn"
          onclick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            playChapter(chapter.id);
          }}
          title="Play"
        >
          {#if $currentSegmentId === chapter.id && $isPlaying}
            <Pause size="14" />
          {:else}
            <Play size="14" />
          {/if}
        </button>
        <span class="chapter-title">
          {#if checked[chapter.id]}
            <span class="title-original-superscript" class:fallback={!chapter.title}>
              {chapter.title || 'No Title'}
            </span>
            <span class="title-new" class:unchanged={pair.sourceTitle === chapter.title}>
              &nbsp;<CornerDownRight
                size="14"
                style="margin-right: 0.15rem;"
                color={pair.sourceTitle === chapter.title ? 'var(--text-muted)' : 'var(--primary-color)'}
              />{pair.sourceTitle}
            </span>
          {:else}
            <span class="title-original" class:fallback={!chapter.title}>{chapter.title || 'No Title'}</span>
          {/if}
        </span>
      </label>
    {:else}
      <div class="row unaligned">
        <span class="chapter-ts">{formatTimestamp(chapter.timestamp)}</span>
        <button
          type="button"
          class="play-btn"
          onclick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            playChapter(chapter.id);
          }}
          title="Play"
        >
          {#if $currentSegmentId === chapter.id && $isPlaying}
            <Pause size="14" />
          {:else}
            <Play size="14" />
          {/if}
        </button>
        <span class="chapter-title">
          <span class="title-original" class:fallback={!chapter.title}>{chapter.title || 'No Title'}</span>
        </span>
      </div>
    {/if}
  {/each}
</div>

<style>
  .tab-explanation {
    color: var(--text-muted);
    font-size: 0.85rem;
    margin: 0 0 0.75rem 0;
    line-height: 1.4;
    text-align: center;
  }

  .chapter-list {
    overflow-y: auto;
    max-height: 360px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.35rem 0.6rem;
    min-height: 3.5rem;
    font-size: 0.875rem;
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

  .row {
    user-select: none;
  }

  .row input[type='checkbox'] {
    flex-shrink: 0;
    cursor: pointer;
    pointer-events: none;
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

  .chapter-title {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }

  .title-new {
    color: var(--text-primary);
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .title-new.unchanged {
    color: var(--text-muted);
  }

  .title-original {
    color: var(--text-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .title-original-superscript {
    color: var(--text-muted);
    font-size: 0.65rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    line-height: 1.2;
  }

  .fallback {
    font-style: italic;
  }
</style>
