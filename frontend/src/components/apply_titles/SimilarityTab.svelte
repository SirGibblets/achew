<script lang="ts">
  import CornerDownRight from '@lucide/svelte/icons/corner-down-right';
  import Pause from '@lucide/svelte/icons/pause';
  import Play from '@lucide/svelte/icons/play';
  import { untrack } from 'svelte';
  import { tooltip } from '../../actions/tooltip';
  import { audio, currentSegmentId, isPlaying } from '../../stores/audio';
  import { chapters } from '../../stores/session';
  import type { TitleSimilarityMatch } from '../../types/api';
  import type { ChapterData } from '../../types/chapter';
  import type { Reference } from '../../types/references';
  import { api, handleApiError } from '../../utils/api';

  interface TitleMapping {
    chapter_id: string;
    new_title: string;
  }

  interface Props {
    ref?: Reference | null;
    mappings?: TitleMapping[];
  }

  let { ref = null, mappings = $bindable([]) }: Props = $props();

  /* Chapter edits (a transcription finishing) re-run the match after this long, so a burst of them runs it once */
  const REFRESH_DELAY_MS = 300;

  let allChapters = $derived($chapters.filter((c) => !c.deleted));

  let matches = $state.raw<Map<string, TitleSimilarityMatch>>(new Map());
  let checked = $state<Record<string, boolean>>({});
  let loading = $state(false);
  let error = $state<string | null>(null);

  /* The Reference the current matches and checkboxes belong to */
  let matchedRefId: string | null = null;
  let requestSeq = 0;

  /* Everything the match depends on: the Reference's titles and each chapter's title and transcript */
  let refTitles = $derived<string[]>(ref ? ('chapters' in ref ? ref.chapters.map((c) => c.title) : ref.titles) : []);
  let signature = $derived(
    JSON.stringify([ref?.id ?? null, refTitles, allChapters.map((c) => [c.id, c.title, c.transcript])]),
  );

  $effect(() => {
    // eslint-disable-next-line @typescript-eslint/no-unused-expressions
    signature; // re-match whenever the inputs change
    const refId = untrack(() => ref?.id ?? null);
    const seq = ++requestSeq;

    if (refId !== matchedRefId) {
      matches = new Map();
      checked = {};
      error = null;
    }
    if (!refId) {
      loading = false;
      matchedRefId = null;
      return;
    }

    loading = true;
    const timer = setTimeout(() => refresh(refId, seq), refId === matchedRefId ? REFRESH_DELAY_MS : 0);
    return () => clearTimeout(timer);
  });

  async function refresh(refId: string, seq: number): Promise<void> {
    try {
      const response = await api.chapters.matchTitlesBySimilarity(refId);
      if (seq !== requestSeq) return;

      /* Keep the user's choices for pairs that didn't change; new pairs start checked when confident */
      const sameRef = refId === matchedRefId;
      const nextChecked: Record<string, boolean> = {};
      for (const m of response.matches) {
        const previous = sameRef ? matches.get(m.chapter_id) : undefined;
        nextChecked[m.chapter_id] =
          previous && previous.ref_index === m.ref_index ? (checked[m.chapter_id] ?? m.confident) : m.confident;
      }
      matches = new Map(response.matches.map((m) => [m.chapter_id, m]));
      checked = nextChecked;
      matchedRefId = refId;
      error = null;
    } catch (err) {
      if (seq === requestSeq) error = handleApiError(err);
    } finally {
      if (seq === requestSeq) loading = false;
    }
  }

  $effect(() => {
    const result: TitleMapping[] = [];
    for (const [chapterId, m] of matches) {
      if (checked[chapterId]) result.push({ chapter_id: chapterId, new_title: m.title });
    }
    mappings = result;
  });

  let matchedIds = $derived(allChapters.map((ch) => ch.id).filter((id) => matches.has(id)));
  let weakCount = $derived(matchedIds.filter((id) => !matches.get(id)?.confident).length);

  let lastClickedIdx = $state<number | null>(null);

  function handleCheck(chapterId: string, event: MouseEvent): void {
    const idx = matchedIds.indexOf(chapterId);
    const newValue = !checked[chapterId];

    const next: Record<string, boolean> = { ...checked };
    if (event.shiftKey && lastClickedIdx !== null && lastClickedIdx !== idx) {
      const lo = Math.min(lastClickedIdx, idx);
      const hi = Math.max(lastClickedIdx, idx);
      for (let i = lo; i <= hi; i++) {
        next[matchedIds[i]] = newValue;
      }
    } else {
      next[chapterId] = newValue;
    }
    checked = next;

    lastClickedIdx = idx;
  }

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

  function formatTimestamp(seconds: number): string {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  }

  function matchHint(chapter: ChapterData, m: TitleSimilarityMatch): string {
    const strength = m.confident ? 'Strong match' : 'Weaker match';
    if (m.source === 'title') return `${strength} with the chapter's current title`;
    const transcript = chapter.transcript.length > 80 ? `${chapter.transcript.slice(0, 80)}…` : chapter.transcript;
    return `${strength} with the chapter's transcript: “${transcript}”`;
  }
</script>

<p class="tab-explanation">
  {#if error}
    <span class="tab-error">{error}</span>
  {:else if matchedIds.length === 0}
    {#if loading}
      Matching titles…
    {:else}
      No chapters match a title in the selected Reference.<br />Each chapter's transcript and current title are compared
      with the Reference's titles.
    {/if}
  {:else}
    {matchedIds.length} of {allChapters.length} chapters match a title in the selected Reference by their transcript or current
    title.<br />
    {#if weakCount > 0}
      {weakCount} weaker {weakCount === 1 ? 'match starts' : 'matches start'} unchecked.
    {/if}
    Uncheck any titles you don't want to apply.
  {/if}
</p>

<div class="chapter-list">
  {#each allChapters as chapter (chapter.id)}
    {@const m = matches.get(chapter.id)}
    {#if m}
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
      <label
        class="row matched"
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
          aria-label="Play"
          use:tooltip={'Play'}
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
            <span class="title-new" class:unchanged={m.title === chapter.title}>
              &nbsp;<CornerDownRight
                size="14"
                style="margin-right: 0.15rem;"
                color={m.title === chapter.title ? 'var(--text-muted)' : 'var(--primary-color)'}
              />{m.title}
            </span>
          {:else}
            <span class="title-original" class:fallback={!chapter.title}>{chapter.title || 'No Title'}</span>
            <span class="title-suggested">Match: {m.title}</span>
          {/if}
        </span>
        <span
          class="match-score"
          class:weak={!m.confident}
          aria-label={matchHint(chapter, m)}
          use:tooltip={{ text: matchHint(chapter, m), maxWidth: 360 }}
        >
          {Math.round(m.score * 100)}%
        </span>
      </label>
    {:else}
      <div class="row unmatched">
        <span class="chapter-ts">{formatTimestamp(chapter.timestamp)}</span>
        <button
          type="button"
          class="play-btn"
          onclick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            playChapter(chapter.id);
          }}
          aria-label="Play"
          use:tooltip={'Play'}
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

  .tab-error {
    color: var(--danger, #c00);
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
    user-select: none;
  }

  .row:nth-child(even) {
    background: rgba(128, 128, 128, 0.06);
  }

  .row.unmatched {
    opacity: 0.4;
  }

  .row.matched {
    opacity: 0.5;
    cursor: pointer;
    transition: opacity 0.15s;
  }

  .row.matched:hover {
    opacity: 0.7;
  }

  .row.matched.checked {
    opacity: 1;
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

  .title-original-superscript,
  .title-suggested {
    color: var(--text-muted);
    font-size: 0.65rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    line-height: 1.2;
  }

  .match-score {
    flex-shrink: 0;
    min-width: 2.6rem;
    padding: 0.1rem 0.4rem;
    border-radius: 999px;
    border: 1px solid var(--primary-color);
    color: var(--primary-color);
    font-size: 0.7rem;
    font-variant-numeric: tabular-nums;
    text-align: center;
  }

  .match-score.weak {
    border-color: var(--border-color);
    color: var(--text-muted);
  }

  .fallback {
    font-style: italic;
  }
</style>
