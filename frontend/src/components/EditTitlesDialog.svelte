<script lang="ts">
  import { api, handleApiError } from '../utils/api';
  import { tooltip } from '../actions/tooltip';
  import { audio, currentSegmentId, isPlaying } from '../stores/audio';
  import { chapters } from '../stores/session';
  import type { ApplyTitleMapping } from '../types/api';
  import {
    addRemoveText,
    applySequence,
    changeCase,
    convertNumbers,
    findReplace,
    resolveTidyOptions,
    tidyTitle,
    DEFAULT_TIDY_OPTIONS,
    type AddRemoveOptions,
    type CaseMode,
    type FindReplaceOptions,
    type NumberFormat,
    type NumberTarget,
    type SequenceOptions,
    type SequencePlacement,
    type TidyOptions,
  } from '../utils/titleTools';
  import DocLink from './DocLink.svelte';

  import CircleHelp from '@lucide/svelte/icons/circle-help';
  import CornerDownRight from '@lucide/svelte/icons/corner-down-right';
  import Pause from '@lucide/svelte/icons/pause';
  import Play from '@lucide/svelte/icons/play';
  import X from '@lucide/svelte/icons/x';

  interface EditorSettings {
    show_formatted_time?: boolean;
    tidy_options?: Partial<TidyOptions>;
  }

  type Mode = 'find-replace' | 'change-case' | 'add-remove' | 'sequence' | 'convert-numbers' | 'tidy';

  interface Props {
    isOpen?: boolean;
    editorSettings?: EditorSettings;
    /** Tool pre-selected when the dialog opens. */
    initialMode?: Mode;
    /** Persists the given Tidy options as the Quick Tidy defaults; should throw on failure. */
    onsavetidy?: (options: TidyOptions) => Promise<void>;
    oncancel?: () => void;
  }

  let {
    isOpen = $bindable(false),
    editorSettings = { show_formatted_time: true },
    initialMode = 'find-replace',
    onsavetidy,
    oncancel,
  }: Props = $props();

  const MODE_LABELS: { id: Mode; label: string }[] = [
    { id: 'find-replace', label: 'Find & Replace' },
    { id: 'change-case', label: 'Change Case' },
    { id: 'add-remove', label: 'Add or Remove Text' },
    { id: 'sequence', label: 'Sequence Numbering' },
    { id: 'convert-numbers', label: 'Convert Numbers' },
    { id: 'tidy', label: 'Tidy' },
  ];

  let mode = $state<Mode>('find-replace');

  // Find & Replace
  let frFind = $state('');
  let frReplace = $state('');
  let frRegex = $state(false);
  let frMatchCase = $state(false);
  let frPreserveCase = $state(false);

  // Change Case
  let ccMode = $state<CaseMode>('title');
  let ccKeepRoman = $state(true);

  // Add or Remove Text
  let arOp = $state<'add' | 'remove'>('add');
  let arWhere = $state<'start' | 'end'>('start');
  let arBy = $state<'text' | 'chars'>('text');
  let arText = $state('');
  let arCountValue = $state('1');

  // Sequence Numbering
  let seqTemplate = $state('Chapter {n}');
  let seqStartValue = $state('1');
  let seqFormat = $state<NumberFormat>('digits');
  let seqPlacement = $state<SequencePlacement>('replace');

  // Convert Numbers
  let cnTarget = $state<NumberTarget>('digits');
  let cnKeywordOnly = $state(true);

  // Tidy. The separator is kept as a preset choice plus a custom-text input
  // (rather than in tidyOpts directly) so switching away from Custom doesn't
  // lose the typed value.
  const SEPARATOR_PRESETS = [': ', ' - ', '. '];
  let tidyOpts = $state<TidyOptions>({ ...DEFAULT_TIDY_OPTIONS });
  let tidySepChoice = $state<string>(DEFAULT_TIDY_OPTIONS.separator);
  let tidySepCustom = $state('');
  let savingTidy = $state(false);
  let savedTidyFlash = $state(false);
  let tidyFlashTimer: number | undefined;

  let tidyOptions = $derived<TidyOptions>({
    ...tidyOpts,
    separator: tidySepChoice === 'custom' ? tidySepCustom : tidySepChoice,
  });

  // Loads the saved Tidy configuration (what the Quick Tidy button uses)
  // into the dialog's Tidy mode.
  function seedTidyFromSettings(): void {
    const saved = resolveTidyOptions(editorSettings.tidy_options);
    tidyOpts = saved;
    if (SEPARATOR_PRESETS.includes(saved.separator)) {
      tidySepChoice = saved.separator;
      tidySepCustom = '';
    } else {
      tidySepChoice = 'custom';
      tidySepCustom = saved.separator;
    }
  }

  let loading = $state(false);
  let error = $state<string | null>(null);
  let appliedFlash = $state(false);
  let flashTimer: number | undefined;

  let checked = $state<Record<string, boolean>>({});
  let lastClickedIdx = $state<number | null>(null);

  // Tracks whether the checkbox state has been seeded for the current open session,
  // so editing chapters while the dialog is open doesn't wipe the user's selection.
  let hasSeeded = false;

  let allChapters = $derived($chapters.filter((c) => !c.deleted));
  let allIds = $derived(allChapters.map((ch) => ch.id));

  // Checked chapters in list order; sequence numbering follows this order.
  let checkedChapters = $derived(allChapters.filter((ch) => checked[ch.id]));

  let regexError = $derived.by(() => {
    if (mode !== 'find-replace' || !frRegex || !frFind) return null;
    try {
      new RegExp(frFind);
      return null;
    } catch (err) {
      return err instanceof Error ? err.message : 'Invalid regular expression';
    }
  });

  // The active tool as a pure function of (title, position among checked
  // chapters), or null while the tool's inputs are incomplete or invalid.
  let transform = $derived.by<((title: string, seqIndex: number) => string) | null>(() => {
    switch (mode) {
      case 'find-replace': {
        if (!frFind || regexError !== null) return null;
        const opts: FindReplaceOptions = {
          find: frFind,
          replace: frReplace,
          useRegex: frRegex,
          matchCase: frMatchCase,
          preserveCase: frPreserveCase,
        };
        return (title) => findReplace(title, opts);
      }
      case 'change-case': {
        const caseMode = ccMode;
        const keepRoman = ccKeepRoman;
        return (title) => changeCase(title, caseMode, keepRoman);
      }
      case 'add-remove': {
        const count = parseInt(arCountValue, 10);
        if (arOp === 'remove' && arBy === 'chars') {
          if (!Number.isFinite(count) || count <= 0) return null;
        } else if (!arText) {
          return null;
        }
        const opts: AddRemoveOptions = {
          op: arOp,
          where: arWhere,
          removeBy: arBy,
          text: arText,
          count: Number.isFinite(count) ? count : 0,
        };
        return (title) => addRemoveText(title, opts);
      }
      case 'sequence': {
        const start = parseInt(seqStartValue, 10);
        if (!seqTemplate || !Number.isFinite(start)) return null;
        const opts: SequenceOptions = { template: seqTemplate, start, format: seqFormat, placement: seqPlacement };
        return (title, seqIndex) => applySequence(title, seqIndex, opts);
      }
      case 'convert-numbers': {
        const opts = { target: cnTarget, keywordOnly: cnKeywordOnly };
        return (title) => convertNumbers(title, opts);
      }
      case 'tidy': {
        const opts = { ...tidyOptions };
        return (title) => tidyTitle(title, opts);
      }
    }
  });

  let newTitleById = $derived.by(() => {
    const map: Record<string, string> = {};
    const fn = transform;
    if (!fn) return map;
    checkedChapters.forEach((ch, j) => {
      // Trim actual changes so no tool can leave invisible leading/trailing
      // whitespace behind (e.g. a regex group that captured a space).
      const out = fn(ch.title, j);
      map[ch.id] = out === ch.title ? out : out.trim();
    });
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

  function sanitizeIntInput(value: string, allowNegative: boolean): string {
    const negative = allowNegative && value.trim().startsWith('-');
    const digits = value.replace(/[^\d]/g, '');
    return (negative ? '-' : '') + digits;
  }

  // Arrow-up/down increments/decrements a numeric text input.
  function handleIntArrows(event: KeyboardEvent, value: string, set: (v: string) => void, min?: number): void {
    if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
    event.preventDefault();
    let next = (parseInt(value, 10) || 0) + (event.key === 'ArrowUp' ? 1 : -1);
    if (min !== undefined && next < min) next = min;
    set(String(next));
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

  // Applies the current changes but keeps the dialog open, so tools can be
  // chained (e.g. Tidy, then Add Text). Each apply is one undo step.
  async function handleApply(): Promise<void> {
    if (!canApply || loading) return;
    loading = true;
    error = null;
    try {
      await api.chapters.applyTitles(changedMappings);
      appliedFlash = true;
      window.clearTimeout(flashTimer);
      flashTimer = window.setTimeout(() => (appliedFlash = false), 1600);
    } catch (err) {
      error = handleApiError(err);
    } finally {
      loading = false;
    }
  }

  async function handleSaveTidyDefaults(): Promise<void> {
    if (!onsavetidy || savingTidy) return;
    savingTidy = true;
    error = null;
    try {
      await onsavetidy({ ...tidyOptions });
      savedTidyFlash = true;
      window.clearTimeout(tidyFlashTimer);
      tidyFlashTimer = window.setTimeout(() => (savedTidyFlash = false), 1600);
    } catch (err) {
      error = handleApiError(err);
    } finally {
      savingTidy = false;
    }
  }

  function handleClose(): void {
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
      handleClose();
    }
  }

  function handleBackdropKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      handleClose();
    }
  }

  // On open: seed checkboxes from the current editor selection, select the
  // requested tool, and load the saved Tidy configuration. On close: reset
  // all tool inputs.
  $effect(() => {
    if (isOpen) {
      if (!hasSeeded) {
        const next: Record<string, boolean> = {};
        for (const ch of $chapters) {
          if (!ch.deleted) next[ch.id] = ch.selected;
        }
        checked = next;
        mode = initialMode;
        seedTidyFromSettings();
        lastClickedIdx = null;
        hasSeeded = true;
      }
    } else if (hasSeeded) {
      hasSeeded = false;
      frFind = '';
      frReplace = '';
      frRegex = false;
      frMatchCase = false;
      frPreserveCase = false;
      ccMode = 'title';
      ccKeepRoman = true;
      arOp = 'add';
      arWhere = 'start';
      arBy = 'text';
      arText = '';
      arCountValue = '1';
      seqTemplate = 'Chapter {n}';
      seqStartValue = '1';
      seqFormat = 'digits';
      seqPlacement = 'replace';
      cnTarget = 'digits';
      cnKeywordOnly = true;
      lastClickedIdx = null;
      error = null;
      loading = false;
      appliedFlash = false;
      savingTidy = false;
      savedTidyFlash = false;
      window.clearTimeout(flashTimer);
      window.clearTimeout(tidyFlashTimer);
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
            Edit Titles &nbsp;<DocLink path="/editor/edit-titles/" featureName="Editing Titles" size="14" />
          </h3>
          <button class="close-button" onclick={handleClose} aria-label="Close">
            <X size="20" />
          </button>
        </div>

        <div class="modal-body">
          {#if error}
            <div class="alert alert-danger">{error}</div>
          {/if}

          <!-- Tool selector -->
          <div class="mode-row">
            <label class="input-label" for="edit-titles-mode">Tool</label>
            <select id="edit-titles-mode" class="select-input" bind:value={mode}>
              {#each MODE_LABELS as { id, label } (id)}
                <option value={id}>{label}</option>
              {/each}
            </select>
          </div>

          <!-- Tool controls -->
          <div class="mode-controls">
            {#if mode === 'find-replace'}
              <div class="field-row">
                <input type="text" class="text-input" placeholder="Find" bind:value={frFind} />
                <input type="text" class="text-input" placeholder="Replace with" bind:value={frReplace} />
              </div>
              {#if regexError}
                <div class="inline-error">{regexError}</div>
              {/if}
              <div class="option-row">
                <label class="opt">
                  <input type="checkbox" bind:checked={frRegex} />
                  <span>Regex</span>
                  <div
                    class="help-icon"
                    use:tooltip={{
                      text: 'Interpret the search text as a regular expression. Use $1, $2, … in the replacement to insert capture groups.',
                      delay: 0,
                    }}
                  >
                    <CircleHelp size="14" />
                  </div>
                </label>
                <label class="opt">
                  <input type="checkbox" bind:checked={frMatchCase} />
                  <span>Match case</span>
                </label>
                <label class="opt">
                  <input type="checkbox" bind:checked={frPreserveCase} />
                  <span>Preserve case</span>
                  <div
                    class="help-icon"
                    use:tooltip={{
                      text: 'Attempts to match the case of the text being replaced, e.g. CHAPTER→PART, Chapter→Part, chapter→part.',
                      delay: 0,
                    }}
                  >
                    <CircleHelp size="14" />
                  </div>
                </label>
              </div>
            {:else if mode === 'change-case'}
              <div class="field-row">
                <select class="select-input" bind:value={ccMode} aria-label="Target case">
                  <option value="title">Title Case</option>
                  <option value="sentence">Sentence case</option>
                  <option value="upper">UPPERCASE</option>
                  <option value="lower">lowercase</option>
                </select>
                {#if ccMode === 'title' || ccMode === 'sentence'}
                  <label class="opt">
                    <input type="checkbox" bind:checked={ccKeepRoman} />
                    <span>Keep Roman numerals uppercase</span>
                    <div
                      class="help-icon"
                      use:tooltip={{
                        text: 'Keeps numerals like XIV uppercase ("Chapter XIV", "Henry VIII") instead of casing them like words ("Xiv").',
                        delay: 0,
                      }}
                    >
                      <CircleHelp size="14" />
                    </div>
                  </label>
                {/if}
              </div>
            {:else if mode === 'add-remove'}
              <div class="field-row">
                <select class="select-input" bind:value={arOp} aria-label="Operation">
                  <option value="add">Add</option>
                  <option value="remove">Remove</option>
                </select>
                {#if arOp === 'remove'}
                  <select class="select-input" bind:value={arBy} aria-label="Remove by">
                    <option value="text">matching text</option>
                    <option value="chars">number of characters</option>
                  </select>
                {/if}
                <select class="select-input" bind:value={arWhere} aria-label="Position">
                  <option value="start">at the start</option>
                  <option value="end">at the end</option>
                </select>
              </div>
              <div class="field-row">
                {#if arOp === 'remove' && arBy === 'chars'}
                  <input
                    type="text"
                    inputmode="numeric"
                    class="text-input count-input"
                    aria-label="Number of characters"
                    bind:value={arCountValue}
                    oninput={() => (arCountValue = sanitizeIntInput(arCountValue, false))}
                    onkeydown={(e) => handleIntArrows(e, arCountValue, (v) => (arCountValue = v), 1)}
                  />
                  <span class="field-note">character{parseInt(arCountValue, 10) === 1 ? '' : 's'}</span>
                {:else}
                  <input
                    type="text"
                    class="text-input"
                    placeholder={arOp === 'add' ? 'Text to add' : 'Text to remove'}
                    bind:value={arText}
                  />
                {/if}
              </div>
            {:else if mode === 'sequence'}
              <div class="field-row">
                <select class="select-input" bind:value={seqPlacement} aria-label="Placement">
                  <option value="replace">Replace title</option>
                  <option value="start">Add to start</option>
                  <option value="end">Add to end</option>
                </select>
                <input type="text" class="text-input" placeholder="Template" bind:value={seqTemplate} />
                <div
                  class="help-icon"
                  use:tooltip={{
                    text: 'In the template, {n} becomes the sequence number and {title} the chapter’s current title, e.g. "Chapter {n}: {title}". The result replaces each title, or is added to its start or end. Numbering follows the checked chapters in order.',
                    delay: 0,
                  }}
                >
                  <CircleHelp size="14" />
                </div>
              </div>
              <div class="field-row">
                <label class="field-note" for="seq-start">Start at</label>
                <input
                  id="seq-start"
                  type="text"
                  inputmode="numeric"
                  class="text-input count-input"
                  bind:value={seqStartValue}
                  oninput={() => (seqStartValue = sanitizeIntInput(seqStartValue, true))}
                  onkeydown={(e) => handleIntArrows(e, seqStartValue, (v) => (seqStartValue = v))}
                />
                <select class="select-input" bind:value={seqFormat} aria-label="Number format">
                  <option value="digits">1, 2, 3</option>
                  <option value="digits-2">01, 02, 03</option>
                  <option value="digits-3">001, 002, 003</option>
                  <option value="roman-upper">I, II, III</option>
                  <option value="roman-lower">i, ii, iii</option>
                  <option value="words-title">One, Two, Three</option>
                  <option value="words-lower">one, two, three</option>
                </select>
              </div>
            {:else if mode === 'convert-numbers'}
              <div class="field-row">
                <label class="field-note" for="cn-target">Convert numbers to</label>
                <select id="cn-target" class="select-input" bind:value={cnTarget}>
                  <option value="digits">Digits (1, 2, 3)</option>
                  <option value="roman-upper">Roman numerals (I, II, III)</option>
                  <option value="roman-lower">Roman numerals (i, ii, iii)</option>
                  <option value="words-title">Words (One, Two, Three)</option>
                  <option value="words-lower">Words (one, two, three)</option>
                </select>
              </div>
              <div class="option-row">
                <label class="opt">
                  <input type="checkbox" bind:checked={cnKeywordOnly} />
                  <span>Only chapter numbers</span>
                  <div
                    class="help-icon"
                    use:tooltip={{
                      text: 'Convert only numbers acting as chapter markers: after a structural word (Chapter, Part, Book, …), starting the title ("1. Intro", "One the Beginning"), or alone in the title. Uncheck to convert every number — check the preview carefully, since titles like "Catch Twenty-Two" will change too.',
                      delay: 0,
                    }}
                  >
                    <CircleHelp size="14" />
                  </div>
                </label>
              </div>
            {:else if mode === 'tidy'}
              <div class="tidy-rows">
                <label class="opt tall">
                  <input type="checkbox" bind:checked={tidyOpts.whitespace} />
                  <span>Fix whitespace</span>
                </label>
                <label class="opt tall">
                  <input type="checkbox" bind:checked={tidyOpts.trailingPunctuation} />
                  <span>Remove trailing punctuation</span>
                </label>
                <div class="tidy-row">
                  <label class="opt">
                    <input type="checkbox" bind:checked={tidyOpts.normalizeNumbers} />
                    <span>Convert chapter numbers to</span>
                  </label>
                  <select
                    class="select-input"
                    bind:value={tidyOpts.numberFormat}
                    disabled={!tidyOpts.normalizeNumbers}
                    aria-label="Number format"
                  >
                    <option value="digits">Digits (1, 2, 3)</option>
                    <option value="roman-upper">Roman numerals (I, II, III)</option>
                    <option value="roman-lower">Roman numerals (i, ii, iii)</option>
                    <option value="words-title">Words (One, Two, Three)</option>
                    <option value="words-lower">Words (one, two, three)</option>
                  </select>
                </div>
                <div class="tidy-row">
                  <label class="opt">
                    <input type="checkbox" bind:checked={tidyOpts.chapterSeparator} />
                    <span>Separator after chapter number</span>
                  </label>
                  <select
                    class="select-input"
                    bind:value={tidySepChoice}
                    disabled={!tidyOpts.chapterSeparator}
                    aria-label="Separator"
                  >
                    <option value=": ">Colon (:)</option>
                    <option value=" - ">Dash (-)</option>
                    <option value=". ">Period (.)</option>
                    <option value="custom">Custom…</option>
                  </select>
                  {#if tidySepChoice === 'custom'}
                    <input
                      type="text"
                      class="text-input sep-input"
                      placeholder="Separator"
                      aria-label="Custom separator"
                      bind:value={tidySepCustom}
                      disabled={!tidyOpts.chapterSeparator}
                    />
                  {/if}
                </div>
                <div class="tidy-row">
                  <label class="opt">
                    <input type="checkbox" bind:checked={tidyOpts.applyCase} />
                    <span>Change case to</span>
                  </label>
                  <select
                    class="select-input"
                    bind:value={tidyOpts.caseMode}
                    disabled={!tidyOpts.applyCase}
                    aria-label="Case style"
                  >
                    <option value="title">Title Case</option>
                    <option value="sentence">Sentence case</option>
                    <option value="upper">UPPERCASE</option>
                    <option value="lower">lowercase</option>
                  </select>
                </div>
                <div class="tidy-save-row">
                  <button
                    class="btn btn-secondary tidy-save-btn"
                    onclick={handleSaveTidyDefaults}
                    disabled={savingTidy}
                  >
                    {savingTidy ? 'Saving…' : savedTidyFlash ? 'Saved ✓' : 'Save as Quick Tidy settings'}
                    {#if !savingTidy}
                      <div
                        class="help-icon"
                        use:tooltip={{
                          text: 'The Quick Tidy button in the editor menu applies your saved settings in a single click',
                          delay: 0,
                        }}
                      >
                        <CircleHelp size="14" />
                      </div>
                    {/if}
                  </button>
                </div>
              </div>
            {/if}
          </div>

          <!-- Chapter list -->
          <div class="preview-header">
            <span class="input-label">Chapters</span>
            <span class="affected-count">{changedCount} title{changedCount !== 1 ? 's' : ''} will change</span>
          </div>
          <p class="list-explanation">Uncheck any chapters you want to leave untouched.</p>

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
          <button class="btn btn-secondary" onclick={handleClose}> Close </button>
          <button class="btn btn-primary" onclick={handleApply} disabled={!canApply || loading}>
            {loading ? 'Applying…' : appliedFlash ? 'Applied ✓' : 'Apply'}
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
    max-width: 640px;
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

  /* Tool selector & controls */
  .mode-row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.75rem;
  }

  .mode-row .input-label {
    margin-bottom: 0;
  }

  .mode-controls {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 0.75rem;
    margin-bottom: 1rem;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background: var(--bg-secondary);
  }

  .field-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .option-row {
    display: flex;
    align-items: center;
    gap: 1rem;
    flex-wrap: wrap;
  }

  .tidy-rows {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .tidy-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .sep-input {
    flex: 0 1 6rem;
    min-width: 5rem;
  }

  .tidy-save-row {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    margin: 0.25rem -0.8rem -0.8rem -0.8rem;
  }

  .btn.tidy-save-btn {
    flex: 1;
    border-top-left-radius: 0;
    border-top-right-radius: 0;
  }

  .select-input:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .opt {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.85rem;
    color: var(--text-primary);
    cursor: pointer;
    user-select: none;
  }

  .opt.tall {
    min-height: 2rem;
  }

  .opt input[type='checkbox'] {
    cursor: pointer;
  }

  .text-input {
    flex: 1;
    min-width: 8rem;
    height: 2rem;
    padding: 0.35rem 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: 0.25rem;
    background: var(--bg-primary);
    color: var(--text-primary);
    font-size: 0.875rem;
    font-family: inherit;
  }

  .count-input {
    flex: 0 0 4rem;
    min-width: 4rem;
    text-align: center;
  }

  .text-input:focus,
  .select-input:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 2px rgba(var(--primary-rgb, 99, 102, 241), 0.2);
  }

  .select-input {
    height: 2rem;
    padding: 0.25rem 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: 0.25rem;
    background: var(--bg-primary);
    color: var(--text-primary);
    font-size: 0.875rem;
    font-family: inherit;
    cursor: pointer;
  }

  .field-note {
    font-size: 0.85rem;
    color: var(--text-secondary);
  }

  .inline-error {
    font-size: 0.8rem;
    color: var(--danger, #c00);
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
    max-height: 320px;
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
