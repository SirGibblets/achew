<script lang="ts">
  import { api, handleApiError } from '../utils/api';
  import { tooltip } from '../actions/tooltip';
  import { audio, currentSegmentId, isPlaying } from '../stores/audio';
  import { chapters } from '../stores/session';
  import type { ApplyTitleMapping } from '../types/api';
  import DocLink from './DocLink.svelte';

  import CircleHelp from '@lucide/svelte/icons/circle-help';
  import CornerDownRight from '@lucide/svelte/icons/corner-down-right';
  import Minus from '@lucide/svelte/icons/minus';
  import Pause from '@lucide/svelte/icons/pause';
  import Play from '@lucide/svelte/icons/play';
  import Plus from '@lucide/svelte/icons/plus';
  import X from '@lucide/svelte/icons/x';

  interface EditorSettings {
    show_formatted_time?: boolean;
  }

  interface Props {
    isOpen?: boolean;
    editorSettings?: EditorSettings;
    oncancel?: () => void;
  }

  let { isOpen = $bindable(false), editorSettings = { show_formatted_time: true }, oncancel }: Props = $props();

  let shiftValue = $state('0');
  let loading = $state(false);
  let error = $state<string | null>(null);

  let checked = $state<Record<string, boolean>>({});
  let lastClickedIdx = $state<number | null>(null);

  // Tracks whether the checkbox state has been seeded for the current open session,
  // so editing chapters while the dialog is open doesn't wipe the user's selection.
  let hasSeeded = false;

  let allChapters = $derived($chapters.filter((c) => !c.deleted));
  let allIds = $derived(allChapters.map((ch) => ch.id));

  let shift = $derived(parseInt(shiftValue, 10) || 0);

  // Checked chapters in list order; their titles are the values being shifted around.
  let checkedChapters = $derived(allChapters.filter((ch) => checked[ch.id]));

  // The title each checked chapter ends up with: the title from `shift` positions
  // earlier in the checked sequence. Positive shift moves titles to later chapters.
  // Titles pushed past either end are dropped (the vacated slot becomes blank).
  let newTitleById = $derived.by(() => {
    const map: Record<string, string> = {};
    const k = checkedChapters.length;
    for (let j = 0; j < k; j++) {
      const srcIdx = j - shift;
      map[checkedChapters[j].id] = srcIdx >= 0 && srcIdx < k ? checkedChapters[srcIdx].title : '';
    }
    return map;
  });

  let changedMappings = $derived<ApplyTitleMapping[]>(
    checkedChapters
      .filter((ch) => (newTitleById[ch.id] ?? ch.title) !== ch.title)
      .map((ch) => ({ chapter_id: ch.id, new_title: newTitleById[ch.id] ?? '' })),
  );

  let changedCount = $derived(changedMappings.length);
  let canApply = $derived(changedCount > 0);

  function handleCheck(chapterId: string, event: MouseEvent): void {
    const idx = allIds.indexOf(chapterId);
    const newValue = !checked[chapterId];

    const next: Record<string, boolean> = { ...checked };
    if (event.shiftKey && lastClickedIdx !== null && lastClickedIdx !== idx) {
      const lo = Math.min(lastClickedIdx, idx);
      const hi = Math.max(lastClickedIdx, idx);
      for (let i = lo; i <= hi; i++) {
        next[allIds[i]] = newValue;
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

  function sanitizeIntInput(value: string): string {
    const negative = value.trim().startsWith('-');
    const digits = value.replace(/[^\d]/g, '');
    return (negative ? '-' : '') + digits;
  }

  function adjustShift(delta: number): void {
    shiftValue = String(shift + delta);
  }

  function handleShiftInput(): void {
    shiftValue = sanitizeIntInput(shiftValue);
  }

  function handleShiftKeydown(e: KeyboardEvent): void {
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      adjustShift(1);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      adjustShift(-1);
    }
  }

  function formatTimestamp(seconds: number): string {
    const whole = Math.floor(seconds);
    if (!editorSettings.show_formatted_time) {
      return whole.toString();
    }
    const hours = Math.floor(whole / 3600);
    const minutes = Math.floor((whole % 3600) / 60);
    const secs = (whole % 60).toString().padStart(2, '0');

    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, '0')}:${secs}`;
    }
    return `${minutes}:${secs}`;
  }

  async function handleApply(): Promise<void> {
    if (!canApply) return;
    loading = true;
    error = null;
    try {
      await api.chapters.applyTitles(changedMappings);
      close();
    } catch (err) {
      error = handleApiError(err);
    } finally {
      loading = false;
    }
  }

  function handleCancel(): void {
    oncancel?.();
    close();
  }

  function close(): void {
    if ($isPlaying) {
      audio.stop();
    }
    isOpen = false;
  }

  function handleBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) {
      handleCancel();
    }
  }

  function handleBackdropKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      handleCancel();
    }
  }

  // Seed checkboxes from the current editor selection on open, reset on close.
  $effect(() => {
    if (isOpen) {
      if (!hasSeeded) {
        const next: Record<string, boolean> = {};
        for (const ch of $chapters) {
          if (!ch.deleted) next[ch.id] = ch.selected;
        }
        checked = next;
        lastClickedIdx = null;
        hasSeeded = true;
      }
    } else if (hasSeeded) {
      hasSeeded = false;
      shiftValue = '0';
      lastClickedIdx = null;
      error = null;
      loading = false;
    }
  });

  // Prevent background scrolling when modal is open.
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
          <h3>
            Shift Titles &nbsp;<DocLink path="/editor/shift-titles/" featureName="Shifting Titles" size="14" />
          </h3>
          <button class="close-button" onclick={handleCancel} aria-label="Close">
            <X size="20" />
          </button>
        </div>

        <div class="modal-body">
          {#if error}
            <div class="alert alert-danger">{error}</div>
          {/if}

          <!-- Shift amount input -->
          <div class="input-group">
            <span class="shift-unit shift-prefix">Shift by</span>
            <div class="shift-input-row">
              <button
                class="adj-btn"
                onclick={() => adjustShift(-1)}
                aria-label="Decrease by 1"
                use:tooltip={'Decrease by 1'}
              >
                <Minus size="12" />
              </button>
              <input
                type="text"
                inputmode="numeric"
                class="shift-input"
                bind:value={shiftValue}
                onkeydown={handleShiftKeydown}
                oninput={handleShiftInput}
              />
              <button
                class="adj-btn"
                onclick={() => adjustShift(1)}
                aria-label="Increase by 1"
                use:tooltip={'Increase by 1'}
              >
                <Plus size="12" />
              </button>
            </div>

            <div class="shift-suffix">
              <span class="shift-unit">chapter{Math.abs(shift) === 1 ? '' : 's'}</span>

              <div
                class="help-icon"
                use:tooltip={{
                  text: 'How many chapters to move each checked title. Positive values move titles to later chapters, negative values to earlier ones. Titles pushed past the beginning or end are dropped, and chapters left with no incoming title become blank. Unchecked chapters remain unaffected.',
                  delay: 0,
                }}
              >
                <CircleHelp size="14" />
              </div>
            </div>
          </div>

          <!-- Chapter list -->
          <div class="preview-header">
            <span class="input-label">Chapters</span>
            <span class="affected-count">{changedCount} title{changedCount !== 1 ? 's' : ''} will change</span>
          </div>
          <p class="list-explanation">Uncheck any chapters you want to exclude from the shift.</p>

          <div class="chapter-list">
            {#each allChapters as chapter (chapter.id)}
              {@const isChecked = checked[chapter.id]}
              {@const newTitle = newTitleById[chapter.id] ?? chapter.title}
              {@const changed = isChecked && newTitle !== chapter.title}
              <!-- svelte-ignore a11y_click_events_have_key_events -->
              <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
              <label
                class="row"
                class:checked={isChecked}
                onclick={(e) => {
                  e.preventDefault();
                  handleCheck(chapter.id, e);
                }}
              >
                <input type="checkbox" checked={isChecked} />
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
                  {#if changed}
                    <span class="title-original-superscript" class:fallback={!chapter.title}>
                      {chapter.title || 'No Title'}
                    </span>
                    <span class="title-new" class:fallback={!newTitle}>
                      &nbsp;<CornerDownRight
                        size="14"
                        style="margin-right: 0.15rem;"
                        color="var(--primary-color)"
                      />{newTitle || 'No Title'}
                    </span>
                  {:else}
                    <span class="title-original" class:fallback={!chapter.title}>{chapter.title || 'No Title'}</span>
                  {/if}
                </span>
              </label>
            {/each}
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary" onclick={handleCancel}> Cancel </button>
          <button class="btn btn-primary" onclick={handleApply} disabled={!canApply || loading}>
            {loading ? 'Applying…' : 'Apply'}
          </button>
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
    padding: 0.5rem 1.5rem 1rem;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
    padding: 1rem;
    border-top: 1px solid var(--border-color);
  }

  .alert-danger {
    padding: 0.75rem;
    border-radius: 0.25rem;
    background: var(--danger-bg, #fee);
    color: var(--danger, #c00);
    margin-bottom: 1rem;
  }

  /* Shift amount input */
  .input-group {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    margin-bottom: 1rem;
  }

  .shift-prefix {
    justify-self: end;
  }

  .shift-suffix {
    display: flex;
    align-items: center;
    justify-self: start;
  }

  .input-label {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-weight: 600;
    font-size: 0.9rem;
    color: var(--text-primary);
    margin-bottom: 0.4rem;
  }

  .shift-input-row {
    display: flex;
    align-items: center;
    margin: 0 0.25rem;
  }

  .shift-input {
    width: 2.5rem;
    height: 2rem;
    padding: 0.35rem 0.5rem;
    border: 1px solid var(--border-color);
    background: var(--bg-primary);
    color: var(--text-primary);
    font-size: 0.875rem;
    text-align: center;
    font-family: inherit;
  }

  .shift-input:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 2px rgba(var(--primary-rgb, 99, 102, 241), 0.2);
  }

  .shift-unit {
    margin: 0 0.35rem;
  }

  .adj-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 1.5rem;
    height: 2rem;
    border: 1px solid var(--border-color);
    border-right: none;
    border-radius: 0.25rem 0 0 0.25rem;
    background: var(--bg-secondary);
    color: var(--text-primary);
    cursor: pointer;
    padding: 0;
  }
  .adj-btn:last-child {
    border: 1px solid var(--border-color);
    border-radius: 0 0.25rem 0.25rem 0;
    border-left: none;
  }

  .adj-btn:hover {
    background: var(--hover-bg);
  }

  /* Chapter list */
  .preview-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 0.25rem;
  }

  .preview-header .input-label {
    margin-bottom: 0;
  }

  .affected-count {
    font-size: 0.8rem;
    color: var(--text-secondary);
  }

  .list-explanation {
    color: var(--text-muted);
    font-size: 0.8rem;
    margin: 0 0 0.5rem 0;
    line-height: 1.4;
  }

  .chapter-list {
    overflow-y: auto;
    flex: 1;
    min-height: 120px;
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
    opacity: 0.5;
    cursor: pointer;
    transition: opacity 0.15s;
  }

  .row:nth-child(even) {
    background: rgba(128, 128, 128, 0.06);
  }

  .row:hover {
    opacity: 0.7;
  }

  .row.checked {
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
    color: var(--text-secondary);
    font-style: italic;
  }

  /* Help icon */
  .help-icon {
    display: inline-flex;
    background: transparent;
    border: none;
    color: var(--text-secondary);
    cursor: help;
    border-radius: 50%;
    transition: all 0.2s ease;
  }

  .help-icon:hover {
    color: var(--primary-color);
    background: var(--bg-tertiary);
  }

  /* Buttons */
  .btn {
    padding: 0.5rem 1rem;
    border: none;
    border-radius: 0.25rem;
    cursor: pointer;
    font-size: 0.875rem;
    font-weight: 500;
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-primary {
    background: var(--primary-color);
    color: white;
  }

  .btn-primary:hover:not(:disabled) {
    opacity: 0.9;
  }

  .btn-secondary {
    background: var(--bg-secondary);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
  }

  .btn-secondary:hover:not(:disabled) {
    background: var(--hover-bg);
  }

  @media (max-width: 768px) {
    .modal-dialog {
      width: 95%;
      max-height: 95vh;
    }

    .modal-body {
      padding: 0.5rem 1rem;
    }
  }
</style>
