<script lang="ts" module>
  export type DockPosition = 'bottom' | 'left' | 'right';
</script>

<script lang="ts">
  import { slide } from 'svelte/transition';
  import { tooltip, type TooltipParam } from '../actions/tooltip';
  import Icon from './Icon.svelte';

  import ArrowDownUp from '@lucide/svelte/icons/arrow-down-up';
  import ArrowRight from '@lucide/svelte/icons/arrow-right';
  import BookMarked from '@lucide/svelte/icons/book-marked';
  import BrushCleaning from '@lucide/svelte/icons/brush-cleaning';
  import Check from '@lucide/svelte/icons/check';
  import ChevronsLeft from '@lucide/svelte/icons/chevrons-left';
  import ChevronsRight from '@lucide/svelte/icons/chevrons-right';
  import CircleQuestionMark from '@lucide/svelte/icons/circle-question-mark';
  import Clock from '@lucide/svelte/icons/clock';
  import Mic from '@lucide/svelte/icons/mic';
  import MoreVertical from '@lucide/svelte/icons/more-vertical';
  import PanelBottom from '@lucide/svelte/icons/panel-bottom';
  import PanelLeft from '@lucide/svelte/icons/panel-left';
  import PanelRight from '@lucide/svelte/icons/panel-right';
  import PencilLine from '@lucide/svelte/icons/pencil-line';
  import Redo from '@lucide/svelte/icons/redo';
  import SettingsIcon from '@lucide/svelte/icons/settings';
  import Square from '@lucide/svelte/icons/square';
  import Trash2 from '@lucide/svelte/icons/trash-2';
  import Undo from '@lucide/svelte/icons/undo';
  import Wrench from '@lucide/svelte/icons/wrench';
  import Zap from '@lucide/svelte/icons/zap';

  import type { EditorSettings } from '../types/api';
  import type { SelectionStats } from '../types/chapter';

  interface Props {
    selectionStats: SelectionStats;
    canUndo: boolean;
    canRedo: boolean;
    hasChapters: boolean;
    hasChapterRefs: boolean;
    hasTranscriptions: boolean;
    transcribing: boolean;
    aiLoading: boolean;
    editorSettings: EditorSettings;
    dock: DockPosition;
    expanded: boolean;
    canDock: boolean;
    onDockChange: (dock: DockPosition) => void;
    onToggleExpanded: () => void;
    onUndo: () => void;
    onRedo: () => void;
    onCleanUp: () => void;
    onReview: () => void;
    onEditTitles: () => void;
    onShiftTitles: () => void;
    onApplyTitles: () => void;
    onShiftTimestamps: () => void;
    onQuickTidy: () => void;
    onQuickTidySettings: () => void;
    onTranscribe: () => void;
    onDelete: (target: 'selected' | 'unselected') => void;
    onSettingsChange: (updates: Partial<EditorSettings>) => void;
  }

  let {
    selectionStats,
    canUndo,
    canRedo,
    hasChapters,
    hasChapterRefs,
    hasTranscriptions,
    transcribing,
    aiLoading,
    editorSettings,
    dock,
    expanded,
    canDock,
    onDockChange,
    onToggleExpanded,
    onUndo,
    onRedo,
    onCleanUp,
    onReview,
    onEditTitles,
    onShiftTitles,
    onApplyTitles,
    onShiftTimestamps,
    onQuickTidy,
    onQuickTidySettings,
    onTranscribe,
    onDelete,
    onSettingsChange,
  }: Props = $props();

  let menuOpen = $state(false);
  let shellEl = $state<HTMLDivElement | null>(null);

  let sideDocked = $derived(dock !== 'bottom');
  let iconOnly = $derived(sideDocked && !expanded);
  let tooltipSide = $derived<'left' | 'right'>(dock === 'left' ? 'right' : 'left');

  // The popover only exists in the bottom dock
  $effect(() => {
    if (sideDocked) {
      menuOpen = false;
    }
  });

  function toggleMenu() {
    menuOpen = !menuOpen;
  }

  function handleOutsideClick(event: MouseEvent) {
    if (menuOpen && shellEl && !shellEl.contains(event.target as Node)) {
      menuOpen = false;
    }
  }

  $effect(() => {
    document.addEventListener('click', handleOutsideClick);
    return () => document.removeEventListener('click', handleOutsideClick);
  });

  /**
   * Tooltip for a bar control: the descriptive text in the bottom dock
   * (unchanged behavior), side-placed when docked to an edge, and an instant
   * label when collapsed to icons.
   */
  function tipFor(label: string, description: string): TooltipParam {
    if (iconOnly) return { text: label, delay: 0, placement: tooltipSide };
    if (sideDocked) return { text: description, placement: tooltipSide };
    return description;
  }

  function checkboxValue(event: Event): boolean {
    return (event.target as HTMLInputElement).checked;
  }

  function quickTidy() {
    menuOpen = false;
    onQuickTidy();
  }

  function transcribe() {
    menuOpen = false;
    onTranscribe();
  }

  function deleteBySelection(target: 'selected' | 'unselected') {
    menuOpen = false;
    onDelete(target);
  }
</script>

{#snippet deleteIcon(variant: 'selected' | 'unselected')}
  <span class="delete-icon">
    <Trash2 size="16" color="var(--danger)" />
    {#if variant === 'selected'}
      <span class="delete-icon-badge check-badge">
        <span class="check-halo"><Check size="9" strokeWidth={12} /></span>
        <Check size="9" color="var(--danger)" strokeWidth={3.5} />
      </span>
    {:else}
      <span class="delete-icon-badge">
        <Square size="9" color="var(--danger)" strokeWidth={3} />
      </span>
    {/if}
  </span>
{/snippet}

{#snippet sectionHeader(label: string, icon: 'settings' | 'wrench' | 'zap')}
  {#if sideDocked}
    <div class="dock-section-divider"></div>
  {/if}
  {#if !iconOnly}
    <h5 class="popover-header">
      {#if icon === 'settings'}
        <SettingsIcon size="12" />
      {:else if icon === 'wrench'}
        <Wrench size="12" />
      {:else}
        <Zap size="12" />
      {/if}
      {label}
    </h5>
  {/if}
{/snippet}

{#snippet settingsSection()}
  <div class="popover-section settings-section">
    {@render sectionHeader('Settings', 'settings')}
    <div class="settings-grid">
      <label class="setting-item">
        <input
          type="checkbox"
          checked={editorSettings.tab_navigation}
          onchange={(event) => onSettingsChange({ tab_navigation: checkboxValue(event) })}
        />
        <span>Tab to Next</span>
        <div
          class="help-icon"
          use:tooltip={{
            text: 'Press Tab while editing a chapter title to move focus to the next selected chapter',
            delay: 0,
          }}
        >
          <CircleQuestionMark size="14" />
        </div>
      </label>

      {#if hasTranscriptions}
        <label class="setting-item">
          <input
            type="checkbox"
            checked={editorSettings.hide_transcriptions}
            onchange={(event) => onSettingsChange({ hide_transcriptions: checkboxValue(event) })}
          />
          <span>Hide Transcripts</span>
          <div
            class="help-icon"
            use:tooltip={{ text: 'Hide the original transcripts to focus on editing titles', delay: 0 }}
          >
            <CircleQuestionMark size="14" />
          </div>
        </label>
      {/if}

      <label class="setting-item">
        <input
          type="checkbox"
          checked={editorSettings.show_formatted_time}
          onchange={(event) => onSettingsChange({ show_formatted_time: checkboxValue(event) })}
        />
        <span>Format Timestamps</span>
        <div class="help-icon" use:tooltip={{ text: 'Show timestamps as hh:mm:ss instead of seconds', delay: 0 }}>
          <CircleQuestionMark size="14" />
        </div>
      </label>

      {#if editorSettings.show_formatted_time}
        <label class="setting-item setting-item-sub">
          <input
            type="checkbox"
            checked={editorSettings.show_fractional_seconds}
            onchange={(event) => onSettingsChange({ show_fractional_seconds: checkboxValue(event) })}
          />
          <span>Fractional Seconds</span>
          <div class="help-icon" use:tooltip={{ text: 'Show hundredths of a second (e.g. 1:23.45)', delay: 0 }}>
            <CircleQuestionMark size="14" />
          </div>
        </label>
      {/if}
    </div>
  </div>
{/snippet}

{#snippet toolsSection()}
  <div class="popover-section tools-section">
    {@render sectionHeader('Tools', 'wrench')}
    <div class="tools-column" class:icon-column={iconOnly}>
      <button
        class="btn btn-cancel btn-sm tool-btn"
        class:full-width={!iconOnly}
        class:icon-only={iconOnly}
        aria-label="Edit Titles"
        use:tooltip={tipFor('Edit Titles', 'Bulk-edit titles: find & replace, change case, number sequences, and more')}
        onclick={onEditTitles}
      >
        <PencilLine size="16" color="var(--primary-color)" />
        {#if !iconOnly}Edit Titles{/if}
      </button>
      <button
        class="btn btn-cancel btn-sm tool-btn"
        class:full-width={!iconOnly}
        class:icon-only={iconOnly}
        aria-label="Shift Titles"
        use:tooltip={tipFor(
          'Shift Titles',
          'Move titles forward or backward across chapters, e.g. when every title is off by one',
        )}
        onclick={onShiftTitles}
      >
        <ArrowDownUp size="16" color="var(--primary-color)" />
        {#if !iconOnly}Shift Titles{/if}
      </button>
      {#if hasChapterRefs}
        <button
          class="btn btn-cancel btn-sm tool-btn"
          class:full-width={!iconOnly}
          class:icon-only={iconOnly}
          aria-label="Apply titles from..."
          use:tooltip={tipFor('Apply titles from...', 'Apply titles from a Chapter Reference')}
          onclick={onApplyTitles}
        >
          <BookMarked size="16" color="var(--primary-color)" />
          {#if !iconOnly}Apply titles from...{/if}
        </button>
      {/if}
      <button
        class="btn btn-cancel btn-sm tool-btn"
        class:full-width={!iconOnly}
        class:icon-only={iconOnly}
        aria-label="Shift Timestamps"
        use:tooltip={tipFor('Shift Timestamps', 'Shift the timestamps of multiple chapters by a fixed amount of time')}
        onclick={onShiftTimestamps}
      >
        <Clock size="16" color="var(--primary-color)" />
        {#if !iconOnly}Shift Timestamps{/if}
      </button>
    </div>
  </div>
{/snippet}

{#snippet actionsSection()}
  <div class="popover-section tools-section">
    {@render sectionHeader('Actions', 'zap')}
    <div class="tools-column" class:icon-column={iconOnly}>
      {#if iconOnly}
        <button
          class="btn btn-cancel btn-sm tool-btn icon-only"
          aria-label="Quick Tidy"
          use:tooltip={tipFor(
            'Quick Tidy',
            'Applies your saved Tidy settings to each selected title. Use the gear icon to view or change settings.',
          )}
          onclick={quickTidy}
          disabled={selectionStats.selected === 0}
        >
          <BrushCleaning size="16" color="var(--primary-color)" />
        </button>
      {:else}
        <div class="segmented-button full-width">
          <button
            class="btn btn-cancel btn-sm tool-btn segmented-left"
            use:tooltip={tipFor(
              'Quick Tidy',
              'Applies your saved Tidy settings to each selected title. Use the gear icon to view or change settings.',
            )}
            onclick={quickTidy}
            disabled={selectionStats.selected === 0}
          >
            <BrushCleaning size="16" color="var(--primary-color)" />
            Quick Tidy
          </button>
          <button
            class="btn btn-cancel btn-sm tool-btn segmented-right"
            aria-label="Configure Quick Tidy"
            use:tooltip={tipFor('Configure Quick Tidy', 'View or change the Quick Tidy settings')}
            onclick={onQuickTidySettings}
          >
            <SettingsIcon size="14" color="var(--text-secondary)" />
          </button>
        </div>
      {/if}
      <button
        class="btn btn-cancel btn-sm tool-btn"
        class:full-width={!iconOnly}
        class:icon-only={iconOnly}
        aria-label="Transcribe"
        use:tooltip={tipFor(
          'Transcribe',
          'Transcribe the audio of each selected chapter using the current transcription settings',
        )}
        onclick={transcribe}
        disabled={selectionStats.selected === 0 || transcribing}
      >
        <Mic size="16" color="var(--primary-color)" />
        {#if !iconOnly}Transcribe{/if}
      </button>
      <button
        class="btn btn-cancel btn-sm tool-btn"
        class:full-width={!iconOnly}
        class:icon-only={iconOnly}
        aria-label="Delete Selected"
        use:tooltip={tipFor('Delete Selected', 'Delete every selected chapter')}
        onclick={() => deleteBySelection('selected')}
        disabled={selectionStats.selected === 0}
      >
        {@render deleteIcon('selected')}
        {#if !iconOnly}Delete{/if}
      </button>
      <button
        class="btn btn-cancel btn-sm tool-btn"
        class:full-width={!iconOnly}
        class:icon-only={iconOnly}
        aria-label="Delete Unselected"
        use:tooltip={tipFor('Delete Unselected', 'Delete every chapter that is not selected')}
        onclick={() => deleteBySelection('unselected')}
        disabled={selectionStats.unselected === 0}
      >
        {@render deleteIcon('unselected')}
        {#if !iconOnly}Delete Unselected{/if}
      </button>
    </div>
  </div>
{/snippet}

{#snippet selectionBadge()}
  <div class="selection-info" class:icon-only-info={iconOnly}>
    {#if iconOnly}
      <span
        class="badge badge-primary"
        use:tooltip={{
          text: `${selectionStats.selected} of ${selectionStats.total} selected`,
          delay: 0,
          placement: tooltipSide,
        }}
      >
        {selectionStats.selected}/{selectionStats.total}
      </span>
    {:else}
      <span class="badge badge-primary">
        {selectionStats.selected} of {selectionStats.total} selected
      </span>
    {/if}
  </div>
{/snippet}

{#snippet undoRedoButtons()}
  <div class="button-group" class:icon-column={iconOnly}>
    <button
      class="btn btn-outline btn-sm undo-redo-btn"
      class:icon-only={iconOnly}
      aria-label="Undo"
      onclick={onUndo}
      disabled={!canUndo}
      use:tooltip={tipFor('Undo', 'Undo last action')}
    >
      <Undo size="16" />
      {#if !iconOnly}Undo{/if}
    </button>
    <button
      class="btn btn-outline btn-sm undo-redo-btn"
      class:icon-only={iconOnly}
      aria-label="Redo"
      onclick={onRedo}
      disabled={!canRedo}
      use:tooltip={tipFor('Redo', 'Redo next action')}
    >
      {#if !iconOnly}Redo{/if}
      <Redo size="16" />
    </button>
  </div>
{/snippet}

{#snippet cleanUpButton()}
  <button
    class="btn btn-ai btn-sm"
    class:full-width={sideDocked && !iconOnly}
    class:icon-only={iconOnly}
    aria-label="Clean Up Selected"
    onclick={onCleanUp}
    disabled={selectionStats.selected === 0 || aiLoading}
    use:tooltip={tipFor('Clean Up Selected', 'Enhance selected chapter titles with AI')}
  >
    <Icon name="ai" size="16" color="white" />
    {#if !iconOnly}Clean Up Selected{/if}
  </button>
{/snippet}

{#snippet reviewButton()}
  <button
    class="btn btn-verify btn-sm action-bar-verify"
    class:full-width={sideDocked && !iconOnly}
    class:icon-only={iconOnly}
    aria-label="Review Selected"
    onclick={onReview}
    disabled={selectionStats.selected === 0}
    use:tooltip={sideDocked ? tipFor('Review Selected', 'Review the selected chapters') : null}
  >
    {#if !iconOnly}Review Selected{/if}
    <ArrowRight size="16" />
  </button>
{/snippet}

<div class="action-bar-shell" data-dock={dock} data-collapsed={iconOnly} bind:this={shellEl}>
  <div class="sticky-action-bar">
    {#if dock === 'bottom'}
      <!-- Tools & Settings Popover -->
      {#if menuOpen && hasChapters}
        <div class="tools-popover" transition:slide={{ duration: 100, axis: 'y' }}>
          {@render settingsSection()}
          <div class="popover-divider"></div>
          {@render toolsSection()}
          <div class="popover-divider"></div>
          {@render actionsSection()}
        </div>
      {/if}

      {#if canDock}
        <button
          class="dock-btn dock-btn-side dock-btn-left"
          aria-label="Dock to left side"
          use:tooltip={'Dock to left side'}
          onclick={() => onDockChange('left')}
        >
          <PanelLeft size="14" />
        </button>
        <button
          class="dock-btn dock-btn-side dock-btn-right"
          aria-label="Dock to right side"
          use:tooltip={'Dock to right side'}
          onclick={() => onDockChange('right')}
        >
          <PanelRight size="14" />
        </button>
      {/if}

      <div class="action-bar-content">
        {@render selectionBadge()}
        {@render undoRedoButtons()}

        <div class="button-group">
          <button
            class="btn btn-cancel btn-sm tools-toggle"
            class:active={menuOpen}
            onclick={toggleMenu}
            aria-label="Additional tools and settings"
            use:tooltip={'Additional tools and settings'}
          >
            <MoreVertical size="16" />
          </button>
          {@render cleanUpButton()}
          {@render reviewButton()}
        </div>
      </div>
    {:else}
      <button
        class="collapse-toggle"
        aria-expanded={expanded}
        aria-label={expanded ? 'Collapse' : 'Expand'}
        use:tooltip={{ text: expanded ? 'Collapse' : 'Expand', delay: 0, placement: tooltipSide }}
        onclick={onToggleExpanded}
      >
        {#if (dock === 'left') === expanded}
          <ChevronsLeft size="12" />
        {:else}
          <ChevronsRight size="12" />
        {/if}
      </button>

      {#if hasChapters}
        {@render toolsSection()}
        {@render actionsSection()}
        {#if !iconOnly}
          {@render settingsSection()}
        {/if}
      {/if}

      <div class="side-bar-items" class:icon-column={iconOnly}>
        <div class="dock-section-divider"></div>
        {@render selectionBadge()}
        {@render undoRedoButtons()}
        {@render cleanUpButton()}
        {@render reviewButton()}
      </div>
    {/if}
  </div>

  {#if sideDocked}
    <div class="dock-controls">
      <button
        class="dock-btn"
        aria-label="Dock to bottom"
        use:tooltip={{ text: 'Dock to bottom', delay: 0, placement: tooltipSide }}
        onclick={() => onDockChange('bottom')}
      >
        <PanelBottom size="16" />
      </button>
      <button
        class="dock-btn"
        aria-label={dock === 'left' ? 'Dock to right side' : 'Dock to left side'}
        use:tooltip={{
          text: dock === 'left' ? 'Dock to right side' : 'Dock to left side',
          delay: 0,
          placement: tooltipSide,
        }}
        onclick={() => onDockChange(dock === 'left' ? 'right' : 'left')}
      >
        {#if dock === 'left'}
          <PanelRight size="16" />
        {:else}
          <PanelLeft size="16" />
        {/if}
      </button>
    </div>
  {/if}
</div>

<style>
  .action-bar-shell {
    display: contents;
  }

  .sticky-action-bar {
    position: sticky;
    bottom: 1rem;
    background: var(--edit-bar-bg);
    border: 1px solid var(--border-color);
    border-radius: 0.5rem;
    box-shadow:
      0 0.25rem 0.5rem rgba(0, 0, 0, 0.1),
      0 0.5rem 1rem rgba(0, 0, 0, 0.15),
      0 1rem 2rem rgba(0, 0, 0, 0.1);
    padding: 1rem;
    max-width: 800px;
    margin: 2rem auto;
    z-index: 1000;
    transition: all 0.1s ease;
  }

  .action-bar-content {
    max-width: 1000px;
    margin: 0 auto;
    padding: 0 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 1rem;
  }

  .selection-info {
    display: flex;
    align-items: center;
  }

  .selection-info .badge {
    font-size: 0.875rem;
  }

  .badge {
    display: inline-block;
    font-size: 0.75rem;
    font-weight: 600;
    text-align: center;
    white-space: nowrap;
    vertical-align: baseline;
    border-radius: 0.375rem;
  }

  .button-group {
    display: flex;
    gap: 0.5rem;
  }

  .btn-ai {
    background: linear-gradient(135deg, var(--ai-gradient-start) 0%, var(--ai-gradient-end) 100%);
    color: white;
    border: none;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0 1rem 0 0.75rem;
    font-weight: 600;
    gap: 0.5rem;
  }

  .btn-ai:hover:not(:disabled) {
    background: linear-gradient(135deg, var(--ai-gradient-start-hover) 0%, var(--ai-gradient-end-hover) 100%);
  }

  .action-bar-content .btn {
    font-size: 0.875rem !important;
    min-height: 2.25rem;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .action-bar-content .undo-redo-btn {
    gap: 0.25rem;
  }

  .action-bar-content .btn-outline {
    background-color: rgba(128, 128, 128, 0.1);
    border: transparent;
  }

  .action-bar-content .btn-outline:hover:not(:disabled) {
    background-color: var(--hover-bg);
  }

  .action-bar-verify {
    padding: 0 0.6rem 0 1rem;
    gap: 0.2rem;
  }

  .tools-popover {
    position: absolute;
    bottom: 100%;
    left: 0;
    right: 0;
    margin-bottom: 0.75rem;
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 0.5rem;
    box-shadow:
      0 4px 12px rgba(0, 0, 0, 0.1),
      0 1px 3px rgba(0, 0, 0, 0.05);
    padding: 1rem;
    z-index: 1001;
    display: flex;
    gap: 1rem;
  }

  .popover-section.settings-section {
    flex: 1;
  }

  .popover-section.tools-section {
    flex: 1;
  }

  .popover-header {
    margin: 0 0 0.75rem 0.22rem;
    font-size: 0.7rem;
    font-weight: 600;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .action-bar-shell[data-dock='left'] .popover-header,
  .action-bar-shell[data-dock='right'] .popover-header {
    padding-top: 0.375rem;
  }

  .popover-divider {
    width: 1px;
    background: var(--border-color);
  }

  .settings-grid {
    display: flex;
    flex-direction: column;
    padding-top: 0.45rem;
    gap: 0.75rem;
  }

  .setting-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
    font-size: 0.875rem;
    color: var(--text-primary);
    font-weight: 500;
  }

  .setting-item input[type='checkbox'] {
    accent-color: var(--primary);
  }

  .setting-item-sub {
    margin-left: 1.5rem;
    margin-top: -0.4rem;
    font-size: 0.8rem;
    font-weight: 400;
    color: var(--text-secondary);
  }

  .tools-column {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .tool-btn {
    display: inline-flex;
    align-items: center;
    justify-content: flex-start;
    gap: 0.5rem;
    font-size: 0.875rem !important;
    height: 2.25rem;
    padding: 0 0.75rem;
    border-radius: 0.25rem;
    transition: all 0.2s;
    cursor: pointer;
  }

  .full-width {
    width: 100%;
  }

  .segmented-button {
    display: flex;
  }

  .segmented-button .segmented-left {
    flex: 1;
    min-width: 0;
    border-top-right-radius: 0;
    border-bottom-right-radius: 0;
    border-right: 0.05rem solid var(--border-color);
  }

  .segmented-button .segmented-right {
    border-top-left-radius: 0;
    border-bottom-left-radius: 0;
    padding: 0 0.5rem;
    border-left: 0;
    transition: none;
  }

  .segmented-button .segmented-right:hover {
    border-left: 0.05rem solid var(--text-primary);
    transition: none;
  }

  .help-icon {
    display: inline-flex;
    align-items: center;
    color: var(--text-secondary);
    cursor: help;
    position: relative;
    padding: 2px;
    border-radius: 50%;
    transition: all 0.2s ease;
  }

  .help-icon:hover {
    color: var(--primary-color);
    background: var(--bg-tertiary);
  }

  .tools-toggle {
    padding: 0 !important;
    width: 2.25rem;
    min-height: 2.25rem;
    display: flex !important;
    align-items: center;
    justify-content: center;
    border: none !important;
  }

  .tools-toggle:hover:not(:disabled) {
    background-color: rgba(128, 128, 128, 0.12);
  }

  .tools-toggle.active {
    background-color: rgba(128, 128, 128, 0.18);
  }

  .tools-toggle.active:hover:not(:disabled) {
    background-color: rgba(128, 128, 128, 0.26);
  }

  /* Composite delete icons: trash + selection-state badge */
  .delete-icon {
    position: relative;
    display: inline-flex;
    flex-shrink: 0;
  }

  .delete-icon-badge {
    position: absolute;
    right: -4px;
    bottom: -3px;
    display: inline-flex;
    padding: 1px;
    border-radius: 3px;
    background: var(--bg-card);
  }

  .action-bar-shell[data-dock='left'] .delete-icon-badge,
  .action-bar-shell[data-dock='right'] .delete-icon-badge {
    background: var(--edit-bar-bg);
  }

  .delete-icon-badge.check-badge,
  .action-bar-shell .delete-icon-badge.check-badge {
    background: transparent;
  }

  .check-halo {
    position: absolute;
    inset: 0.5px;
    display: inline-flex;
    color: var(--bg-card);
  }

  .check-badge > :global(svg) {
    position: relative;
  }

  .action-bar-shell[data-dock='left'] .check-halo,
  .action-bar-shell[data-dock='right'] .check-halo {
    color: var(--edit-bar-bg);
  }

  /* Dock buttons (all positions) */
  .dock-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.75rem;
    height: 1.75rem;
    padding: 0;
    border: none;
    border-radius: 0.375rem;
    background: transparent;
    color: var(--text-secondary);
    opacity: 0.6;
    cursor: pointer;
    transition:
      opacity 0.15s ease,
      background-color 0.15s ease,
      color 0.15s ease;
  }

  .dock-btn:hover {
    opacity: 1;
    color: var(--text-primary);
    background: rgba(128, 128, 128, 0.15);
  }

  .dock-btn-side {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
  }

  .dock-btn-left {
    left: -2rem;
  }

  .dock-btn-right {
    right: -2rem;
  }

  /* ---- Side dock ---- */

  .action-bar-shell[data-dock='left'],
  .action-bar-shell[data-dock='right'] {
    display: flex;
    flex-direction: column;
    position: fixed;
    top: 0;
    bottom: 0;
    width: var(--action-bar-dock-size, 16.5rem);
    z-index: 1000;
    background: var(--edit-bar-bg);
  }

  .action-bar-shell[data-dock='left'] {
    left: 0;
    border-right: 0.5px solid var(--border-color);
  }

  .action-bar-shell[data-dock='right'] {
    right: 0;
    border-left: 0.5px solid var(--border-color);
  }

  .action-bar-shell[data-dock='left'] .sticky-action-bar,
  .action-bar-shell[data-dock='right'] .sticky-action-bar {
    position: static;
    max-width: none;
    margin: 0;
    padding: 0.75rem;
    border: none;
    border-radius: 0;
    box-shadow: none;
    background: transparent;
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
    transition: none;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .action-bar-shell[data-collapsed='true'] .sticky-action-bar {
    padding: 0.5rem 0.375rem;
    gap: 0.5rem;
    align-items: center;
  }

  .side-bar-items {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    flex-shrink: 0;
  }

  .action-bar-shell[data-dock='left'] .popover-section,
  .action-bar-shell[data-dock='right'] .popover-section {
    flex: 0 0 auto;
  }

  .dock-section-divider {
    height: 0.5px;
    flex-shrink: 0;
    align-self: stretch;
    background: var(--border-color);
    margin: 0.25rem -0.75rem 0.75rem;
  }

  .action-bar-shell[data-collapsed='true'] .dock-section-divider {
    margin-left: -0.375rem;
    margin-right: -0.375rem;
  }

  .side-bar-items .selection-info {
    justify-content: center;
  }

  .side-bar-items .button-group {
    display: flex;
    gap: 0.5rem;
  }

  .side-bar-items .button-group:not(.icon-column) .undo-redo-btn {
    flex: 1;
    justify-content: center;
  }

  .side-bar-items .btn {
    font-size: 0.875rem !important;
    min-height: 2.25rem;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .side-bar-items .undo-redo-btn {
    gap: 0.25rem;
  }

  .side-bar-items .btn-outline {
    background-color: rgba(128, 128, 128, 0.1);
    border: transparent;
  }

  .side-bar-items .btn-outline:hover:not(:disabled) {
    background-color: var(--hover-bg);
  }

  .icon-column {
    flex-direction: column;
    align-items: center;
    gap: 0.375rem;
  }

  .side-bar-items > .dock-section-divider {
    margin-bottom: 0.25rem;
  }

  .side-bar-items.icon-column {
    width: 100%;
  }

  .action-bar-shell[data-collapsed='true'] .selection-info .badge {
    font-size: 0.75rem;
    font-weight: 500;
  }

  .btn.icon-only {
    width: 2.25rem;
    height: 2.25rem;
    min-height: 2.25rem;
    padding: 0 !important;
    justify-content: center !important;
    flex-shrink: 0;
  }

  .action-bar-shell[data-collapsed='true'] .popover-section {
    display: flex;
    flex-direction: column;
    align-items: center;
    width: 100%;
  }

  .collapse-toggle {
    display: flex;
    align-items: center;
    justify-content: center;
    align-self: stretch;
    height: 1.5rem;
    flex-shrink: 0;
    margin: -0.75rem;
    padding: 0;
    border: none;
    border-radius: 0;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .action-bar-shell[data-collapsed='true'] .collapse-toggle {
    margin: -0.5rem -0.375rem;
  }

  .collapse-toggle + .popover-section .dock-section-divider:first-child,
  .collapse-toggle + .side-bar-items .dock-section-divider:first-child {
    margin-top: 0;
  }

  .collapse-toggle:hover {
    color: var(--text-primary);
    background: rgba(128, 128, 128, 0.15);
  }

  .action-bar-shell[data-dock='left'][data-collapsed='false'] .collapse-toggle {
    justify-content: flex-end;
    padding-right: 0.5rem;
  }

  .action-bar-shell[data-dock='right'][data-collapsed='false'] .collapse-toggle {
    justify-content: flex-start;
    padding-left: 0.5rem;
  }

  .dock-controls {
    display: flex;
    flex-shrink: 0;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 0.25rem 0.375rem;
    border-top: 0.5px solid var(--border-color);
  }

  .action-bar-shell[data-collapsed='true'] .dock-controls {
    gap: 0;
  }

  @media (max-width: 768px) {
    .sticky-action-bar {
      padding: 0.75rem;
      margin: 1rem 0;
    }

    .action-bar-content {
      flex-direction: column;
      align-items: stretch;
      text-align: center;
    }

    .action-bar-content .button-group {
      justify-content: center;
    }
  }

  @media (max-width: 600px) {
    .tools-popover {
      flex-direction: column;
      gap: 1rem;
    }

    .popover-divider {
      width: 100%;
      height: 1px;
      margin: 0;
    }
  }
</style>
