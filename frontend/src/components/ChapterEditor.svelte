<script lang="ts">
  import { onDestroy, onMount, tick } from 'svelte';
  import { SvelteMap } from 'svelte/reactivity';
  import { get } from 'svelte/store';
  import { fade, slide } from 'svelte/transition';
  import { tooltip } from '../actions/tooltip';
  import { audio, currentSegmentId, isPlaying } from '../stores/audio';
  import DocLink from './DocLink.svelte';
  import {
    canRedo,
    canUndo,
    chapters,
    progress,
    savedChapterEditorScroll,
    selectionStats,
    session,
    pendingAddChapterDialog,
    transcriptionStatuses,
  } from '../stores/session';
  import { api, handleApiError } from '../utils/api';
  import AddChapterDialog from './AddChapterDialog.svelte';
  import AICleanupDialog from './AICleanupDialog.svelte';
  import ApplyTitlesDialog from './apply_titles/ApplyTitlesDialog.svelte';
  import ShiftTimestampsDialog from './ShiftTimestampsDialog.svelte';
  import Icon from './Icon.svelte';

  // Icons
  import ArrowRight from '@lucide/svelte/icons/arrow-right';
  import BookMarked from '@lucide/svelte/icons/book-marked';
  import Check from '@lucide/svelte/icons/check';
  import ChevronLeft from '@lucide/svelte/icons/chevron-left';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import Pause from '@lucide/svelte/icons/pause';
  import Play from '@lucide/svelte/icons/play';
  import Plus from '@lucide/svelte/icons/plus';
  import Redo from '@lucide/svelte/icons/redo';
  import SettingsIcon from '@lucide/svelte/icons/settings';
  import MoreVertical from '@lucide/svelte/icons/more-vertical';
  import Wrench from '@lucide/svelte/icons/wrench';
  import Clock from '@lucide/svelte/icons/clock';
  import CircleQuestionMark from '@lucide/svelte/icons/circle-question-mark';
  import Trash2 from '@lucide/svelte/icons/trash-2';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import Undo from '@lucide/svelte/icons/undo';
  import X from '@lucide/svelte/icons/x';
  import CircleHelp from '@lucide/svelte/icons/circle-help';
  import Mic from '@lucide/svelte/icons/mic';

  import type { DetectedCueEntry, EditorSettings } from '../types/api';

  interface AICleanupErrorInfo {
    message: string;
    provider: string;
    errorType: string;
    timestamp: Date;
  }

  let lastScrollY = 0;
  let loading = $state(false);
  let error = $state<string | null>(null);
  let aiCleanupError = $state<AICleanupErrorInfo | null>(null);
  let showAIConfirmation = $state(false);
  let showAddChapterDialog = $state(false);
  let showShiftTimestampsDialog = $state(false);
  let showApplyTitlesDialog = $state(false);
  let addChapterDialogChapterId = $state<string | null>(null);
  let addChapterDialogDefaultTab = $state<string | null>(null);

  let showSettings = $state(false);
  let editorSettings = $state<EditorSettings>({
    tab_navigation: false,
    hide_transcriptions: false,
    show_formatted_time: true,
    show_fractional_seconds: true,
  });

  // Timestamp editing state
  let editingTimestampId = $state<string | null>(null);
  let timestampInputValue = $state('');
  let timestampValidationError = $state<string | null>(null);

  // Jump-to-cue state (populated while a timestamp is being edited)
  type JumpTarget = { timestamp: number; isOriginal: boolean };
  let nearbyCues = $state<DetectedCueEntry[] | null>(null);
  let editingOriginalTimestamp = $state<number | null>(null);
  let nearbyCuesError = $state<string | null>(null);
  let currentJumpPosition = $state<number | null>(null);

  // Shift-click range selection
  let lastClickedChapterId = $state<string | null>(null);

  let inputRefs = new SvelteMap<string, HTMLInputElement>();

  // Check if any chapters have transcriptions
  let hasTranscriptions = $derived($chapters.some((chapter) => chapter.transcript && chapter.transcript.trim() !== ''));

  let hasAlignmentData = $derived($chapters.some((chapter) => chapter.realignment != null));

  let showTranscriptions = $derived(hasTranscriptions && !editorSettings.hide_transcriptions);

  // Load chapters and AI options when component mounts
  onMount(async () => {
    await loadEditorSettings();
    await loadChapters();
    await tick();

    // Restore scroll if it hasn't been consumed by the pendingAddChapterDialog effect
    const scrollToRestore = get(savedChapterEditorScroll);
    if (scrollToRestore !== null && scrollToRestore > 0) {
      savedChapterEditorScroll.set(null);
      window.scrollTo({ top: scrollToRestore, behavior: 'instant' });
    }

    window.addEventListener('scroll', handleScroll, { passive: true });
    window.addEventListener('keydown', handleKeydown);
    document.addEventListener('click', handleOutsideClick);
  });

  // Transcription progress/cancel bar; show after 1000ms
  let showTranscriptionBar = $state(false);
  let transcriptionBarTimer: ReturnType<typeof setTimeout> | null = null;
  let cancellingTranscription = $state(false);

  $effect(() => {
    const hasStatuses = Object.keys($transcriptionStatuses).length > 0;
    if (hasStatuses && !showTranscriptionBar) {
      if (!transcriptionBarTimer) {
        transcriptionBarTimer = setTimeout(() => {
          showTranscriptionBar = true;
          transcriptionBarTimer = null;
        }, 1000);
      }
    } else if (!hasStatuses) {
      if (transcriptionBarTimer) {
        clearTimeout(transcriptionBarTimer);
        transcriptionBarTimer = null;
      }
      showTranscriptionBar = false;
    }
  });

  let transcriptionProgress = $derived(
    (() => {
      const entries = Object.values($transcriptionStatuses);
      const total = entries.length;
      if (total === 0) return { finished: 0, total: 0, percent: 0 };
      const finished = entries.filter((s) => s === 'finished').length;
      const transcribing = entries.filter((s) => s === 'transcribing').length;
      const percent = Math.round(((finished + transcribing * 0.5) / total) * 100);
      return { finished, total, percent };
    })(),
  );

  async function cancelTranscriptions() {
    cancellingTranscription = true;
    try {
      await api.chapters.cancelTranscriptions();
    } catch (err) {
      error = handleApiError(err);
    } finally {
      cancellingTranscription = false;
    }
  }

  onDestroy(() => {
    if (get(savedChapterEditorScroll) === null) {
      savedChapterEditorScroll.set(lastScrollY);
    }
    audio.stop();
    window.removeEventListener('scroll', handleScroll);
    window.removeEventListener('keydown', handleKeydown);
    document.removeEventListener('click', handleOutsideClick);
    if (transcriptionBarTimer) {
      clearTimeout(transcriptionBarTimer);
    }
  });

  // Monitor AI cleanup progress for errors
  $effect(() => {
    if ($progress && $progress.step === 'ai_cleanup') {
      if (
        $progress.percent === 0 &&
        $progress.message &&
        ($progress.message.includes('failed') ||
          $progress.message.includes('error') ||
          $progress.message.includes('authentication') ||
          $progress.message.includes('rate limit') ||
          $progress.message.includes('connection'))
      ) {
        // Set AI cleanup error with additional context
        const errorDetails = ($progress.details || {}) as { provider?: string; error_type?: string };
        aiCleanupError = {
          message: $progress.message,
          provider: errorDetails.provider || 'Unknown',
          errorType: errorDetails.error_type || 'unknown',
          timestamp: new Date(),
        };
      } else if ($progress.percent > 0) {
        // Clear error if processing progresses successfully
        aiCleanupError = null;
      }
    } else if ($progress && $progress.step === 'chapter_editing' && $progress.percent === 100) {
      // Clear error when successfully completing and returning to chapter editing
      aiCleanupError = null;
    }
  });

  async function loadEditorSettings() {
    try {
      editorSettings = await api.config.getEditorSettings();
    } catch (err) {
      console.warn('Failed to load editor settings:', err);
    }
  }

  async function saveEditorSettings(updates: Partial<EditorSettings>) {
    try {
      const response = await api.config.updateEditorSettings(updates);
      editorSettings = response.editor_settings;
    } catch (err) {
      error = handleApiError(err);
    }
  }

  function toggleSettingsPanel() {
    showSettings = !showSettings;
  }

  function handleOutsideClick(event: MouseEvent) {
    if (showSettings) {
      const stickyBar = document.querySelector('.sticky-action-bar');
      if (stickyBar && !stickyBar.contains(event.target as Node)) {
        showSettings = false;
      }
    }
  }

  async function handleTabNavigationChange(event: Event) {
    const enabled = (event.target as HTMLInputElement).checked;
    await saveEditorSettings({ tab_navigation: enabled });
  }

  async function handleHideTranscriptionsChange(event: Event) {
    const enabled = (event.target as HTMLInputElement).checked;
    await saveEditorSettings({ hide_transcriptions: enabled });
  }

  async function handleTimeFormatChange(event: Event) {
    const enabled = (event.target as HTMLInputElement).checked;
    await saveEditorSettings({ show_formatted_time: enabled });
  }

  async function handleFractionalSecondsChange(event: Event) {
    const enabled = (event.target as HTMLInputElement).checked;
    await saveEditorSettings({ show_fractional_seconds: enabled });
  }

  function handleScroll() {
    lastScrollY = window.scrollY;
  }

  // Keyboard shortcuts
  function handleKeydown(event: KeyboardEvent) {
    // Check if user is typing in an input field
    const target = event.target as HTMLElement;
    if (target.tagName === 'INPUT') {
      if (event.key === 'Tab' && editorSettings.tab_navigation) {
        event.preventDefault();
        handleTabNavigation(target as HTMLInputElement, event.shiftKey);
      }
      return;
    }

    const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
    const ctrlKey = isMac ? event.metaKey : event.ctrlKey;

    if (ctrlKey && event.key === 'z' && !event.shiftKey) {
      event.preventDefault();
      undo();
    } else if (ctrlKey && (event.key === 'y' || (event.key === 'z' && event.shiftKey))) {
      event.preventDefault();
      redo();
    }
  }

  function handleTabNavigation(currentInput: HTMLInputElement, isReverse = false) {
    const selectedChapters = $chapters.filter((ch) => ch.selected);
    const currentChapterId = getCurrentChapterIdFromInput(currentInput);
    const currentChapterIndex = selectedChapters.findIndex((ch) => ch.id === currentChapterId);

    if (currentChapterIndex === -1) return;

    let targetChapter = null;

    if (isReverse) {
      if (currentChapterIndex > 0) {
        targetChapter = selectedChapters[currentChapterIndex - 1];
      }
    } else {
      if (currentChapterIndex < selectedChapters.length - 1) {
        targetChapter = selectedChapters[currentChapterIndex + 1];
      }
    }

    if (targetChapter) {
      const targetInput = inputRefs.get(targetChapter.id);
      if (targetInput) {
        targetInput.focus();
        targetInput.select();

        scrollToFocusedInput(targetInput);
      }
    }
  }

  function scrollToFocusedInput(input: HTMLElement) {
    requestAnimationFrame(() => {
      const inputRect = input.getBoundingClientRect();
      const stickyBar = document.querySelector('.sticky-action-bar');
      const stickyBarRect = stickyBar ? stickyBar.getBoundingClientRect() : null;

      const bottomBarHeight = stickyBarRect ? stickyBarRect.height : 0;
      const padding = 32;
      const scrollTarget = inputRect.bottom + bottomBarHeight + padding;
      const viewportHeight = window.innerHeight;

      if (scrollTarget > viewportHeight) {
        const scrollOffset = scrollTarget - viewportHeight;
        window.scrollBy({
          top: scrollOffset,
          behavior: 'smooth',
        });
      }
    });
  }

  function getCurrentChapterIdFromInput(input: HTMLInputElement) {
    for (const [chapterId, ref] of inputRefs.entries()) {
      if (ref === input) {
        return chapterId;
      }
    }
    return null;
  }

  async function loadChapters() {
    if ($session.step !== 'chapter_editing') return;

    loading = true;
    error = null;

    try {
      await session.loadChapters();
    } catch (err) {
      error = handleApiError(err);
    } finally {
      loading = false;
    }
  }

  // History operations
  async function undo() {
    if (!$canUndo) return;

    try {
      await api.chapters.undo();
      // Clear audio cache when chapter structure changes via undo
      audio.clearSegmentCache();
    } catch (err) {
      error = handleApiError(err);
    }
  }

  async function redo() {
    if (!$canRedo) return;

    try {
      await api.chapters.redo();
      // Clear audio cache when chapter structure changes via redo
      audio.clearSegmentCache();
    } catch (err) {
      error = handleApiError(err);
    }
  }

  // Individual chapter operations
  async function updateChapterTitle(chapterId: string, newTitle: string) {
    try {
      await api.chapters.updateTitle(chapterId, newTitle);
    } catch (err) {
      error = handleApiError(err);
    }
  }

  async function setChapterSelection(chapterIds: string[] | null, selected: boolean) {
    try {
      await api.chapters.setSelection({ chapterIds, selected });
    } catch (err) {
      error = handleApiError(err);
    }
  }

  async function handleSelectionCheckboxClick(chapterId: string, event: MouseEvent) {
    event.preventDefault();

    const visible = $chapters.filter((ch) => ch.id !== undefined && ch.id !== null);
    const idx = visible.findIndex((ch) => ch.id === chapterId);
    if (idx === -1) return;

    const newValue = !visible[idx].selected;

    if (event.shiftKey && lastClickedChapterId !== null) {
      const lastIdx = visible.findIndex((ch) => ch.id === lastClickedChapterId);
      if (lastIdx !== -1 && lastIdx !== idx) {
        const lo = Math.min(lastIdx, idx);
        const hi = Math.max(lastIdx, idx);
        const ids = visible.slice(lo, hi + 1).map((ch) => ch.id);
        lastClickedChapterId = chapterId;
        await setChapterSelection(ids, newValue);
        return;
      }
    }

    lastClickedChapterId = chapterId;
    await setChapterSelection([chapterId], newValue);
  }

  async function deleteChapter(chapterId: string) {
    try {
      await api.chapters.delete(chapterId);
      // Clear audio cache when chapters are deleted to prevent wrong segments from playing
      audio.clearSegmentCache();
    } catch (err) {
      error = handleApiError(err);
    }
  }

  async function deleteBySelection(target: 'selected' | 'unselected') {
    const count = target === 'selected' ? $selectionStats.selected : $selectionStats.unselected;
    if (count === 0) return;
    try {
      await api.chapters.deleteBySelection(target);
      audio.clearSegmentCache();
      showSettings = false;
    } catch (err) {
      error = handleApiError(err);
    }
  }

  // Transcription
  async function transcribeChapter(chapterId: string) {
    try {
      await api.chapters.transcribe(chapterId);
    } catch (err) {
      error = handleApiError(err);
    }
  }

  async function transcribeSelected() {
    showSettings = false;
    try {
      await api.chapters.transcribeSelected();
    } catch (err) {
      error = handleApiError(err);
    }
  }

  // Audio playback
  async function playChapter(chapterId: string) {
    if ($session.step !== 'chapter_editing') return;

    try {
      if ($currentSegmentId === chapterId && $isPlaying) {
        // Stop the current playback instead of pausing
        audio.stop();
      } else {
        const chapter = $chapters.find((ch) => ch.id === chapterId);
        const chapterTimestamp = chapter ? chapter.timestamp : null;

        await audio.play(chapterId, chapterTimestamp);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      error = `Failed to play audio: ${message}`;
    }
  }

  // Format timestamp
  function formatTimestamp(seconds: number) {
    if (!editorSettings.show_formatted_time) {
      // Show raw seconds with 2 decimal places
      return seconds.toFixed(2);
    }

    // Show formatted time hh:mm:ss, optionally with hundredths on the seconds
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

  // Title editing with debounce
  let titleTimeouts = new SvelteMap<string, ReturnType<typeof setTimeout>>();

  function handleTitleEdit(chapterId: string, newTitle: string, originalTitle: string) {
    if (newTitle === originalTitle) return;

    // Clear existing timeout
    if (titleTimeouts.has(chapterId)) {
      clearTimeout(titleTimeouts.get(chapterId));
    }

    // Set new timeout
    const timeoutId = setTimeout(() => {
      updateChapterTitle(chapterId, newTitle);
      titleTimeouts.delete(chapterId);
    }, 600);

    titleTimeouts.set(chapterId, timeoutId);
  }

  function trackInput(node: HTMLInputElement, chapterId: string) {
    inputRefs.set(chapterId, node);

    return {
      destroy() {
        inputRefs.delete(chapterId);
      },
    };
  }

  // Action to focus input elements
  function focusInput(node: HTMLInputElement | HTMLTextAreaElement) {
    node.focus();
    node.select();
  }

  // AI cleanup
  async function processSelectedWithAI() {
    if ($selectionStats.selected === 0) return;
    showAIConfirmation = true;
  }

  async function handleAICleanupConfirm(aiOptions: import('../types/api').AIOptions) {
    try {
      await api.batch.processSelected(aiOptions);
    } catch (err) {
      error = handleApiError(err);
    }
  }

  function handleAICleanupCancel() {
    showAIConfirmation = false;
  }

  function handleAICleanupError(err: unknown) {
    error = handleApiError(err);
  }

  // Quick restore transcript as the title
  async function restoreTranscript(chapterId: string, transcript: string) {
    if ($session.step !== 'chapter_editing') return;

    try {
      await updateChapterTitle(chapterId, transcript);
    } catch (err) {
      error = handleApiError(err);
    }
  }

  function openAddChapterDialog(chapterId: string, defaultTab: string | null = null) {
    addChapterDialogChapterId = chapterId;
    addChapterDialogDefaultTab = defaultTab;
    showAddChapterDialog = true;
  }

  function handleAddChapterConfirm() {
    showAddChapterDialog = false;
    addChapterDialogChapterId = null;
    addChapterDialogDefaultTab = null;
  }

  function handleAddChapterCancel() {
    showAddChapterDialog = false;
    addChapterDialogChapterId = null;
    addChapterDialogDefaultTab = null;
  }

  // Re-open add-chapter dialog after a partial scan completes
  $effect(() => {
    if ($pendingAddChapterDialog) {
      const { chapter_id, open_tab } = $pendingAddChapterDialog;
      pendingAddChapterDialog.set(null);

      // Restore scroll before the dialog opens (so its freeze captures the right position)
      const scrollToRestore = get(savedChapterEditorScroll);
      if (scrollToRestore !== null && scrollToRestore > 0) {
        savedChapterEditorScroll.set(null);
        window.scrollTo({ top: scrollToRestore, behavior: 'instant' });
      }

      openAddChapterDialog(chapter_id, open_tab);
    }
  });

  // Go to review page
  function goToReview() {
    savedChapterEditorScroll.set(window.scrollY);
    window.scrollTo({ top: 0, behavior: 'instant' });
    api.session
      .gotoReview()
      .then(() => session.loadActiveSession())
      .catch((err) => {
        error = handleApiError(err);
      });
  }

  // Timestamp editing functions
  function startTimestampEdit(chapterId: string, currentTimestamp: number) {
    editingTimestampId = chapterId;
    timestampInputValue = formatTimestamp(currentTimestamp);
    timestampValidationError = null;
    editingOriginalTimestamp = currentTimestamp;
    currentJumpPosition = currentTimestamp;
    nearbyCues = null;
    nearbyCuesError = null;
    api.chapters
      .getNearbyCues(chapterId)
      .then((response) => {
        if (editingTimestampId === chapterId) nearbyCues = response.cues;
      })
      .catch((err) => {
        if (editingTimestampId === chapterId) nearbyCuesError = handleApiError(err);
      });
  }

  function clearJumpState() {
    nearbyCues = null;
    editingOriginalTimestamp = null;
    nearbyCuesError = null;
    currentJumpPosition = null;
  }

  function cancelTimestampEdit() {
    if ($currentSegmentId && $currentSegmentId.startsWith('timestamp-edit-')) {
      audio.stop();
    }
    editingTimestampId = null;
    timestampInputValue = '';
    timestampValidationError = null;
    clearJumpState();
  }

  function buildJumpList(): JumpTarget[] {
    if (editingOriginalTimestamp === null || nearbyCues === null) return [];
    const COLLISION = 0.1;
    const original = editingOriginalTimestamp;
    const result: JumpTarget[] = [{ timestamp: original, isOriginal: true }];
    for (const cue of nearbyCues) {
      if (Math.abs(cue.timestamp - original) > COLLISION) {
        result.push({ timestamp: cue.timestamp, isOriginal: false });
      }
    }
    result.sort((a, b) => a.timestamp - b.timestamp);
    return result;
  }

  function findJumpTarget(direction: 'prev' | 'next', current: number): JumpTarget | undefined {
    const list = buildJumpList();
    if (direction === 'next') {
      return list.find((t) => t.timestamp > current);
    }
    for (let i = list.length - 1; i >= 0; i--) {
      if (list[i].timestamp < current) return list[i];
    }
    return undefined;
  }

  function jumpToCue(direction: 'prev' | 'next', chapterId: string) {
    if (currentJumpPosition === null) return;
    const target = findJumpTarget(direction, currentJumpPosition);
    if (!target) return;
    timestampInputValue = formatTimestamp(target.timestamp);
    currentJumpPosition = target.timestamp;
    timestampValidationError = null;
    audio.play(`timestamp-edit-${chapterId}`, target.timestamp);
  }

  function jumpTooltip(target: JumpTarget | undefined, current: number, dir: 'prev' | 'next'): string {
    if (!target) {
      return dir === 'next'
        ? 'No cues before next chapter. Use the Add Chapter button to scan for cues.'
        : 'No cues after previous chapter. Use the Add Chapter button to scan for cues.';
    }
    if (target.isOriginal) {
      return `Jump to original timestamp: ${formatTimestamp(target.timestamp)}`;
    }
    const delta = target.timestamp - current;
    const sign = delta >= 0 ? '+' : '-';
    return `Jump to ${dir} cue: ${formatTimestamp(target.timestamp)} (${sign}${formatTimestamp(Math.abs(delta))})`;
  }

  function parseTimestampInput(input: string) {
    // Remove any non-numeric characters except : and .
    const cleaned = input.replace(/[^0-9:.\s]/g, '').trim();

    // Split by colon and parse as numbers
    const parts = cleaned.split(':').map(Number);

    if (parts.length === 2) {
      // mm:ss format
      const [minutes, seconds] = parts;
      return minutes * 60 + seconds;
    }

    if (parts.length === 3) {
      // hh:mm:ss format
      const [hours, minutes, seconds] = parts;
      return hours * 3600 + minutes * 60 + seconds;
    }

    // Try to parse as seconds
    const seconds = parseFloat(cleaned);
    if (!isNaN(seconds) && seconds >= 0) {
      return seconds;
    }

    return null;
  }

  function validateTimestamp(chapterId: string, timestamp: number) {
    const currentChapterIndex = $chapters.findIndex((ch) => ch.id === chapterId);

    if (currentChapterIndex === -1) return null;

    const prevChapter = currentChapterIndex > 0 ? $chapters[currentChapterIndex - 1] : null;
    const nextChapter = currentChapterIndex < $chapters.length - 1 ? $chapters[currentChapterIndex + 1] : null;

    const minTimestamp = prevChapter ? prevChapter.timestamp + 1 : 1;
    const maxTimestamp = nextChapter ? nextChapter.timestamp - 1 : ($session.book?.duration ?? Infinity) - 1;

    if (timestamp < minTimestamp) {
      return `Timestamp must be at least ${formatTimestamp(minTimestamp)}`;
    }

    if (timestamp > maxTimestamp) {
      return `Timestamp must be at most ${formatTimestamp(maxTimestamp)}`;
    }

    return null;
  }

  async function saveTimestampEdit(chapterId: string) {
    if (timestampValidationError) {
      return;
    }

    const parsedTimestamp = parseTimestampInput(timestampInputValue);
    if (parsedTimestamp === null) {
      timestampValidationError = 'Invalid timestamp format. Use hh:mm:ss, mm:ss, or seconds.';
      return;
    }

    // formatTimestamp() is lossy (floors to whole seconds when fractional seconds are off,
    // rounds to hundredths otherwise), so re-parsing the displayed string drops the finer
    // precision of a jumped/nudged cue. When the input still reflects currentJumpPosition,
    // save that exact value; only fall back to the parsed input when the user has typed
    // something different.
    const timestampToSave =
      currentJumpPosition !== null && formatTimestamp(currentJumpPosition) === timestampInputValue
        ? currentJumpPosition
        : parsedTimestamp;

    try {
      await api.chapters.updateTimestamp(chapterId, timestampToSave);
      cancelTimestampEdit();
    } catch (err) {
      timestampValidationError = handleApiError(err);
    }
  }

  function handleTimestampInputKeydown(event: KeyboardEvent, chapterId: string) {
    if (event.key === 'Enter') {
      event.preventDefault();
      saveTimestampEdit(chapterId);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      cancelTimestampEdit();
    } else if (event.key === ' ') {
      event.preventDefault();
      if (!timestampValidationError) {
        playFromEditedTimestamp(chapterId);
      }
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      if (event.shiftKey) {
        jumpToCue('next', chapterId);
        return;
      }
      if ($currentSegmentId && $currentSegmentId.startsWith('timestamp-edit-')) {
        audio.stop();
      }
      const current = parseTimestampInput(timestampInputValue) || 0;
      const nudged = current + 1;
      timestampInputValue = formatTimestamp(nudged);
      currentJumpPosition = nudged;
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      if (event.shiftKey) {
        jumpToCue('prev', chapterId);
        return;
      }
      if ($currentSegmentId && $currentSegmentId.startsWith('timestamp-edit-')) {
        audio.stop();
      }
      const current = parseTimestampInput(timestampInputValue) || 0;
      const nudged = Math.max(0, current - 1);
      timestampInputValue = formatTimestamp(nudged);
      currentJumpPosition = nudged;
    }
  }

  function handleTimestampInputChange() {
    if ($currentSegmentId && $currentSegmentId.startsWith('timestamp-edit-')) {
      audio.stop();
    }

    const parsedTimestamp = parseTimestampInput(timestampInputValue);
    if (parsedTimestamp !== null && editingTimestampId !== null) {
      timestampValidationError = validateTimestamp(editingTimestampId, parsedTimestamp);
      currentJumpPosition = parsedTimestamp;
    } else if (parsedTimestamp === null) {
      timestampValidationError = 'Invalid timestamp format. Use hh:mm:ss, mm:ss, or seconds.';
      currentJumpPosition = null;
    }
  }

  function playFromEditedTimestamp(chapterId: string) {
    const parsedTimestamp = parseTimestampInput(timestampInputValue);
    if (parsedTimestamp !== null && !timestampValidationError) {
      try {
        const previewId = `timestamp-edit-${chapterId}`;
        if ($currentSegmentId === previewId && $isPlaying) {
          audio.stop();
        } else {
          audio.play(previewId, parsedTimestamp);
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        error = `Failed to play audio: ${message}`;
      }
    }
  }
</script>

<div class="chapter-editor">
  {#if error}
    <div class="alert alert-danger">
      {error}
      <button class="btn btn-sm btn-outline float-right" onclick={() => (error = null)}> Dismiss </button>
    </div>
  {/if}

  {#if aiCleanupError}
    <div class="alert alert-danger">
      <div class="alert-header">
        <TriangleAlert size="20" />
        <strong>AI Cleanup Failed</strong>
        <button class="btn btn-sm btn-outline float-right" onclick={() => (aiCleanupError = null)}> Dismiss </button>
      </div>
      <div class="alert-content">
        <p>{aiCleanupError.message}</p>
        {#if aiCleanupError.provider && aiCleanupError.provider !== 'Unknown'}
          <small class="text-muted">Provider: {aiCleanupError.provider}</small>
        {/if}
      </div>
    </div>
  {/if}

  <!-- Page Header -->
  <div class="page-header">
    <h2>Edit Chapters <DocLink path="/editor/overview/" featureName="the Chapter Editor" size="16" /></h2>
    <p>Review and edit your audiobook chapters</p>
  </div>

  <!-- Chapter Table -->
  {#if loading}
    <div class="text-center p-4">
      <div class="spinner"></div>
      <p>Loading chapters…</p>
    </div>
  {:else if $chapters.length === 0}
    <div class="empty-state">
      <div class="empty-icon">
        <BookMarked size="48" />
      </div>
      <h3>No chapters found</h3>
      <p>Chapters will appear here once processing is complete.</p>
    </div>
  {:else}
    <div class="table-container">
      <table class="table">
        <thead>
          <tr>
            <th style="width: 1px">
              <input
                type="checkbox"
                checked={$selectionStats.selected === $selectionStats.total && $selectionStats.total > 0}
                indeterminate={$selectionStats.selected > 0 && $selectionStats.selected < $selectionStats.total}
                onchange={(e) =>
                  api.chapters.setSelection({
                    selected: (e.target as HTMLInputElement).checked,
                  })}
              />
            </th>
            <th style="width: 1px" class="time-header"> Time </th>
            {#if hasAlignmentData}
              <th style="width: 1px" class="offset-header">
                <div class="header-with-icon">
                  Offset
                  <div
                    class="help-icon"
                    use:tooltip={{
                      text: 'The time difference between the reference chapter timestamp and the realigned timestamp.',
                      delay: 0,
                    }}
                  >
                    <CircleHelp size="14" />
                  </div>
                </div>
              </th>
            {/if}
            {#if showTranscriptions}
              <th style="width: 1px">Transcript</th>
              <th style="width: 1px"></th>
            {/if}
            <th>Title</th>
            <th style="width: 1px">Actions</th>
            <th style="width: 1px; min-width: 1px; padding: 0;"></th>
          </tr>
        </thead>
        <tbody>
          {#each $chapters.filter((ch) => ch.id !== undefined && ch.id !== null) as chapter (chapter.id)}
            <tr
              class="chapter-row"
              class:dimmed={!chapter.selected}
              class:transcribing={$transcriptionStatuses[chapter.id]}
            >
              <td>
                <input
                  type="checkbox"
                  checked={chapter.selected}
                  onclick={(e) => handleSelectionCheckboxClick(chapter.id, e)}
                />
                {#if $transcriptionStatuses[chapter.id]}
                  <div class="transcribing-overlay">
                    {#if $transcriptionStatuses[chapter.id] === 'finished'}
                      Finished
                    {:else}
                      <div class="transcribing-spinner"></div>
                      {#if $transcriptionStatuses[chapter.id] === 'transcribing'}
                        Transcribing…
                      {:else}
                        Pending…
                      {/if}
                    {/if}
                  </div>
                {/if}
              </td>
              <td class="timestamp" class:editing={editingTimestampId === chapter.id}>
                {#if editingTimestampId === chapter.id}
                  <!-- Reserve the cell's normal width: the edit overlay is position:absolute,
                       so without this the auto-layout column collapses to the next-widest row. -->
                  <span class="timestamp-width-keeper" aria-hidden="true">{formatTimestamp(chapter.timestamp)}</span>
                  <div
                    class="timestamp-edit-overlay"
                    class:with-fractions={editorSettings.show_fractional_seconds !== false}
                  >
                    <button
                      class="timestamp-play-btn"
                      class:disabled={timestampValidationError}
                      class:playing={$currentSegmentId === `timestamp-edit-${chapter.id}` && $isPlaying}
                      onclick={() => playFromEditedTimestamp(chapter.id)}
                      aria-label={timestampValidationError
                        ? 'Cannot play: invalid timestamp'
                        : 'Play from edited timestamp'}
                      use:tooltip={timestampValidationError
                        ? 'Cannot play: invalid timestamp'
                        : 'Play from edited timestamp'}
                      disabled={!!timestampValidationError}
                    >
                      {#if $currentSegmentId === `timestamp-edit-${chapter.id}` && $isPlaying}
                        <Pause size="14" />
                      {:else}
                        <Play size="14" />
                      {/if}
                    </button>
                    <div class="timestamp-input-wrap">
                      <input
                        class="timestamp-input"
                        class:error={timestampValidationError}
                        bind:value={timestampInputValue}
                        onkeydown={(e) => handleTimestampInputKeydown(e, chapter.id)}
                        oninput={handleTimestampInputChange}
                        placeholder="hh:mm:ss or seconds"
                        use:focusInput
                      />
                      {#if nearbyCuesError !== null}
                        <span
                          class="jump-fetch-error"
                          use:tooltip={`Could not load cues: ${nearbyCuesError}`}
                          transition:fade={{ duration: 250 }}
                        >
                          <TriangleAlert size="10" />
                        </span>
                      {:else}
                        {@const cuesLoaded = nearbyCues !== null}
                        {@const current = currentJumpPosition ?? parseTimestampInput(timestampInputValue) ?? 0}
                        {@const prevTarget = cuesLoaded ? findJumpTarget('prev', current) : undefined}
                        {@const nextTarget = cuesLoaded ? findJumpTarget('next', current) : undefined}
                        <button
                          type="button"
                          class="jump-btn jump-btn-prev"
                          class:loaded={cuesLoaded}
                          disabled={!cuesLoaded || !prevTarget}
                          aria-label="Jump to previous cue"
                          use:tooltip={{ text: jumpTooltip(prevTarget, current, 'prev'), dismissOnClick: false }}
                          onmousedown={(e) => e.preventDefault()}
                          onclick={() => jumpToCue('prev', chapter.id)}
                        >
                          <ChevronLeft size="12" />
                        </button>
                        <button
                          type="button"
                          class="jump-btn jump-btn-next"
                          class:loaded={cuesLoaded}
                          disabled={!cuesLoaded || !nextTarget}
                          aria-label="Jump to next cue"
                          use:tooltip={{ text: jumpTooltip(nextTarget, current, 'next'), dismissOnClick: false }}
                          onmousedown={(e) => e.preventDefault()}
                          onclick={() => jumpToCue('next', chapter.id)}
                        >
                          <ChevronRight size="12" />
                        </button>
                      {/if}
                    </div>
                    {#if timestampValidationError}
                      <button
                        class="timestamp-warning-btn"
                        aria-label={timestampValidationError}
                        use:tooltip={timestampValidationError}
                      >
                        <TriangleAlert size="14" />
                      </button>
                    {:else}
                      <button
                        class="timestamp-save-btn"
                        onclick={() => saveTimestampEdit(chapter.id)}
                        aria-label="Save timestamp"
                        use:tooltip={'Save timestamp'}
                      >
                        <Check size="14" />
                      </button>
                    {/if}
                    <button
                      class="timestamp-cancel-btn"
                      onclick={cancelTimestampEdit}
                      aria-label="Cancel editing"
                      use:tooltip={'Cancel editing'}
                    >
                      <X size="14" />
                    </button>
                  </div>
                {:else if chapter.timestamp > 0.01}
                  <button
                    class="timestamp-display"
                    onclick={() => startTimestampEdit(chapter.id, chapter.timestamp)}
                    use:tooltip={'Edit timestamp'}
                  >
                    {formatTimestamp(chapter.timestamp)}
                  </button>
                {:else}
                  <span class="timestamp-display readonly" use:tooltip={'The first chapter must start at 0'}>
                    {formatTimestamp(chapter.timestamp)}
                  </span>
                {/if}
              </td>
              {#if hasAlignmentData}
                <td class="offset-cell">
                  {#if chapter.realignment != null}
                    {@const offset = chapter.timestamp - chapter.realignment.original_timestamp}
                    {@const isGuess = chapter.realignment.is_guess}
                    {@const lowConfidence = chapter.realignment.confidence < 0.75}
                    <div class="offset-display" class:warning={isGuess || lowConfidence}>
                      <span class="offset-value">
                        {offset > 0 ? '+' : ''}{offset.toFixed(1)}s
                      </span>
                      {#if isGuess || lowConfidence}
                        <div
                          class="warning-icon"
                          use:tooltip={{
                            text: isGuess
                              ? 'This timestamp is an estimate. Please verify.'
                              : 'Low confidence alignment. Please verify.',
                            delay: 0,
                          }}
                        >
                          <TriangleAlert size="14" />
                        </div>
                      {/if}
                    </div>
                  {/if}
                </td>
              {/if}
              {#if showTranscriptions}
                <td class="transcript-cell">
                  <span class="transcript-tooltip-wrapper" use:tooltip={{ text: chapter.transcript, delay: 500 }}>
                    <span class="transcript-text">{chapter.transcript}</span>
                  </span>
                </td>
                <td class="restore-cell">
                  <button
                    class="btn btn-sm btn-outline restore-btn"
                    onclick={() => restoreTranscript(chapter.id, chapter.transcript)}
                    disabled={chapter.title === chapter.transcript}
                    aria-label="Replace title with transcript"
                    use:tooltip={'Replace title with transcript'}
                  >
                    <ArrowRight size="14" />
                  </button>
                </td>
              {/if}
              <td class="title-cell">
                <input
                  type="text"
                  class="chapter-title-input"
                  value={chapter.title}
                  oninput={(e) => {
                    const target = e.target as HTMLInputElement;
                    handleTitleEdit(chapter.id, target.value, chapter.title);
                  }}
                  use:trackInput={chapter.id}
                />
              </td>
              <td>
                <div class="action-buttons">
                  <button
                    class="transcribe-button"
                    onclick={() => transcribeChapter(chapter.id)}
                    aria-label="Transcribe chapter title"
                    use:tooltip={'Transcribe chapter title'}
                    disabled={!!$transcriptionStatuses[chapter.id]}
                  >
                    <Mic size="16" />
                  </button>
                  <button
                    class="play-button"
                    class:playing={$currentSegmentId === chapter.id && $isPlaying}
                    onclick={() => playChapter(chapter.id)}
                    aria-label={$currentSegmentId === chapter.id && $isPlaying ? 'Stop' : 'Play'}
                    use:tooltip={$currentSegmentId === chapter.id && $isPlaying ? 'Stop' : 'Play'}
                  >
                    {#if $currentSegmentId === chapter.id && $isPlaying}
                      <Pause size="16" />
                    {:else}
                      <Play size="16" />
                    {/if}
                  </button>
                  {#if chapter.timestamp > 0.01}
                    <button
                      class="btn btn-sm btn-danger delete-btn"
                      onclick={() => deleteChapter(chapter.id)}
                      aria-label="Delete chapter"
                      use:tooltip={'Delete chapter'}
                    >
                      <Trash2 size="16" />
                    </button>
                  {/if}
                </div>
              </td>
              <td class="add-chapter-cell-container">
                <div class="add-chapter-cell">
                  <button
                    class="add-chapter-button"
                    onclick={() => openAddChapterDialog(chapter.id)}
                    aria-label="Add chapter after this one"
                    use:tooltip={'Add chapter after this one'}
                  >
                    <Plus size="16" />
                  </button>
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}

  {#if showTranscriptionBar}
    <div class="transcription-cancel-bar" transition:slide={{ duration: 150, axis: 'y' }}>
      <div class="transcription-cancel-content">
        <div class="transcription-cancel-info">
          <div class="transcribing-spinner"></div>
          <span>Transcribing {transcriptionProgress.total} chapter{transcriptionProgress.total === 1 ? '' : 's'}…</span>
          <div class="transcription-progress-bar">
            <div class="transcription-progress-fill" style="width: {transcriptionProgress.percent}%"></div>
          </div>
        </div>
        <button class="btn transcription-cancel-btn" onclick={cancelTranscriptions} disabled={cancellingTranscription}>
          <X size={14} />
          Cancel
        </button>
      </div>
    </div>
  {/if}

  <!-- Sticky Action Bar -->
  {#if $chapters.length > 0 || $canUndo}
    <div class="sticky-action-bar">
      <!-- Tools & Settings Popover -->
      {#if showSettings && $chapters.length > 0}
        <div class="tools-popover" transition:slide={{ duration: 100, axis: 'y' }}>
          <div class="popover-section settings-section">
            <h5 class="popover-header">
              <SettingsIcon size="12" />
              Settings
            </h5>
            <div class="settings-grid">
              <label class="setting-item">
                <input type="checkbox" checked={editorSettings.tab_navigation} onchange={handleTabNavigationChange} />
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
                    onchange={handleHideTranscriptionsChange}
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
                <input type="checkbox" checked={editorSettings.show_formatted_time} onchange={handleTimeFormatChange} />
                <span>Format Timestamps</span>
                <div
                  class="help-icon"
                  use:tooltip={{ text: 'Show timestamps as hh:mm:ss instead of seconds', delay: 0 }}
                >
                  <CircleQuestionMark size="14" />
                </div>
              </label>

              {#if editorSettings.show_formatted_time}
                <label class="setting-item setting-item-sub">
                  <input
                    type="checkbox"
                    checked={editorSettings.show_fractional_seconds}
                    onchange={handleFractionalSecondsChange}
                  />
                  <span>Fractional Seconds</span>
                  <div class="help-icon" use:tooltip={{ text: 'Show hundredths of a second (e.g. 1:23.45)', delay: 0 }}>
                    <CircleQuestionMark size="14" />
                  </div>
                </label>
              {/if}
            </div>
          </div>

          <div class="popover-divider"></div>

          <div class="popover-section tools-section">
            <h5 class="popover-header">
              <Wrench size="12" />
              Tools
            </h5>
            <div class="tools-split-layout">
              <div class="tools-column">
                {#if ($session.chapterRefs || []).length > 0}
                  <button
                    class="btn btn-cancel btn-sm tool-btn full-width"
                    use:tooltip={'Apply titles from a chapter reference'}
                    onclick={() => (showApplyTitlesDialog = true)}
                  >
                    <BookMarked size="16" color="var(--primary-color)" />
                    Apply titles from...
                  </button>
                {/if}
                <button
                  class="btn btn-cancel btn-sm tool-btn full-width"
                  use:tooltip={'Shift Timestamps'}
                  onclick={() => (showShiftTimestampsDialog = true)}
                >
                  <Clock size="16" color="var(--primary-color)" />
                  Shift Timestamps
                </button>
                <button
                  class="btn btn-cancel btn-sm tool-btn full-width"
                  use:tooltip={'Transcribe Selected'}
                  onclick={transcribeSelected}
                  disabled={$selectionStats.selected === 0 || Object.keys($transcriptionStatuses).length > 0}
                >
                  <Mic size="16" color="var(--primary-color)" />
                  Transcribe Selected
                </button>
              </div>
              <div class="tools-column">
                <button
                  class="btn btn-cancel btn-sm tool-btn full-width"
                  use:tooltip={'Delete Selected'}
                  onclick={() => deleteBySelection('selected')}
                  disabled={$selectionStats.selected === 0}
                >
                  <Trash2 size="16" color="var(--danger)" />
                  Delete Selected
                </button>
                <button
                  class="btn btn-cancel btn-sm tool-btn full-width"
                  use:tooltip={'Delete Unselected'}
                  onclick={() => deleteBySelection('unselected')}
                  disabled={$selectionStats.unselected === 0}
                >
                  <Trash2 size="16" color="var(--danger)" />
                  Delete Unselected
                </button>
              </div>
            </div>
          </div>
        </div>
      {/if}

      <div class="action-bar-content">
        <div class="selection-info">
          <span class="badge badge-primary">
            {$selectionStats.selected} of {$selectionStats.total} selected
          </span>
        </div>

        <div class="button-group">
          <button
            class="btn btn-outline btn-sm undo-redo-btn"
            onclick={undo}
            disabled={!$canUndo}
            use:tooltip={'Undo last action'}
          >
            <Undo size="16" />
            Undo
          </button>
          <button
            class="btn btn-outline btn-sm undo-redo-btn"
            onclick={redo}
            disabled={!$canRedo}
            use:tooltip={'Redo next action'}
          >
            Redo
            <Redo size="16" />
          </button>
        </div>

        <div class="button-group">
          <button
            class="btn btn-cancel btn-sm tools-toggle"
            class:active={showSettings}
            onclick={toggleSettingsPanel}
            aria-label="Additional tools and settings"
            use:tooltip={'Additional tools and settings'}
          >
            <MoreVertical size="16" />
          </button>
          <button
            class="btn btn-ai btn-sm"
            onclick={processSelectedWithAI}
            disabled={$selectionStats.selected === 0 || loading}
            use:tooltip={'Enhance selected chapter titles with AI'}
          >
            <Icon name="ai" size="16" color="white" />
            Clean Up Selected
          </button>
          <button
            class="btn btn-verify btn-sm action-bar-verify"
            onclick={goToReview}
            disabled={$selectionStats.selected === 0}
          >
            Review Selected
            <ArrowRight size="16" />
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>

<!-- AI Cleanup Dialog -->
<AICleanupDialog
  bind:isOpen={showAIConfirmation}
  sessionStep={$session.step}
  chapterRefs={$session.chapterRefs || []}
  onconfirm={handleAICleanupConfirm}
  oncancel={handleAICleanupCancel}
  onerror={handleAICleanupError}
/>

<!-- Add Chapter Dialog -->
<AddChapterDialog
  bind:isOpen={showAddChapterDialog}
  chapterId={addChapterDialogChapterId}
  defaultTab={addChapterDialogDefaultTab}
  {editorSettings}
  onconfirm={handleAddChapterConfirm}
  oncancel={handleAddChapterCancel}
/>

<!-- Shift Timestamps Dialog -->
<ShiftTimestampsDialog bind:isOpen={showShiftTimestampsDialog} {editorSettings} />

<!-- Apply Titles Dialog -->
<ApplyTitlesDialog bind:isOpen={showApplyTitlesDialog} />

<style>
  .page-header {
    margin-bottom: 2rem;
    text-align: center;
  }

  .page-header h2 {
    margin-bottom: 0.75rem;
    font-size: 2rem;
    font-weight: 600;
  }

  .page-header p {
    margin: 0;
    color: var(--text-secondary);
  }

  .transcription-cancel-bar {
    position: sticky;
    bottom: 6rem;
    background: var(--edit-bar-bg);
    border: 1px solid var(--border-color);
    border-radius: 0.5rem;
    box-shadow:
      0 0.25rem 0.5rem rgba(0, 0, 0, 0.1),
      0 0.5rem 1rem rgba(0, 0, 0, 0.15);
    padding: 0.625rem 1rem;
    max-width: 500px;
    margin: 0 auto 0.5rem auto;
    z-index: 1000;
  }

  .transcription-cancel-content {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }

  .transcription-cancel-info {
    display: flex;
    align-items: center;
    gap: 0.625rem;
    color: var(--primary-color);
    font-size: 0.875rem;
    font-weight: 500;
    min-width: 0;
  }

  .transcription-progress-bar {
    flex: 1;
    min-width: 60px;
    max-width: 120px;
    height: 4px;
    background: var(--border-color);
    border-radius: 2px;
    overflow: hidden;
  }

  .transcription-progress-fill {
    height: 100%;
    background: var(--primary-color);
    border-radius: 2px;
    transition: width 0.4s ease;
    min-width: 8px;
  }

  .transcription-cancel-btn {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.25rem 0.625rem;
    font-size: 0.8rem;
    line-height: 1.5;
    background: transparent;
    border: 1px solid var(--danger, #dc3545);
    color: var(--danger, #dc3545);
    border-radius: 0.25rem;
    cursor: pointer;
    transition:
      background 0.15s ease,
      color 0.15s ease;
  }

  .transcription-cancel-btn:hover:not(:disabled) {
    background: var(--danger, #dc3545);
    color: white;
  }

  .transcription-cancel-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
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

  .selection-info .badge {
    font-size: 0.875rem;
  }

  .button-group {
    display: flex;
    gap: 0.5rem;
  }

  .table-container {
    background: var(--bg-card);
    border-radius: 0.5rem;
    overflow: visible;
    border: 1px solid var(--border-color);
  }

  .add-chapter-cell-container {
    padding: 0;
    height: 100%;
    vertical-align: bottom;
    position: relative;
    overflow: visible;
  }

  .add-chapter-cell {
    position: absolute;
    bottom: 0;
    left: 50%;
    transform: translateX(-50%);
    width: auto;
    padding: 0;
    z-index: 10;
  }

  .add-chapter-button {
    position: absolute;
    width: 1.75rem;
    height: 1.75rem;
    top: -0.825rem;
    left: -0.825rem;
    border-radius: 50%;
    border: 1px solid var(--border-color);
    background: var(--bg-card);
    color: var(--text-secondary);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.75rem;
    transition: all 0.2s ease;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }

  .add-chapter-button:hover {
    background: var(--primary);
    color: white;
    border-color: var(--primary);
    transform: scale(1.1);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
  }

  .table thead th {
    text-align: left;
  }

  .chapter-row {
    transition: opacity 0.1s ease;
  }

  .chapter-row.dimmed {
    background-color: var(--bg-chapter-disabled);
  }

  .chapter-row:hover {
    background-color: var(--bg-chapter-hover);
  }

  .chapter-row.dimmed:hover {
    background-color: var(--bg-chapter-disabled);
  }

  .chapter-row.transcribing {
    position: relative;
    pointer-events: none;
  }

  .chapter-row.transcribing > td:not(:first-child) {
    opacity: 0.1;
  }

  .chapter-row.transcribing > td:first-child {
    position: static;
  }

  .chapter-row.transcribing > td:first-child > :not(.transcribing-overlay) {
    opacity: 0.1;
  }

  .transcribing-overlay {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    color: var(--primary-color);
    font-size: 0.875rem;
    font-weight: 500;
    opacity: 1;
    z-index: 1;
    pointer-events: none;
  }

  .transcribing-spinner {
    width: 16px;
    height: 16px;
    border: 2px solid transparent;
    border-top-color: var(--primary-color);
    border-radius: 50%;
    animation: transcribe-spin 0.8s linear infinite;
  }

  @keyframes transcribe-spin {
    to {
      transform: rotate(360deg);
    }
  }

  .timestamp {
    font-family: monospace;
    color: var(--text-secondary);
    font-size: 0.875rem;
    position: relative;
    min-height: 1.5rem;
  }

  .timestamp-display {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: space-between;
    min-height: 1.5rem;
    background: none;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    padding: 0;
    font-family: monospace;
    font-size: 0.875rem;
    width: 100%;
    text-align: left;
    transition: all 0.2s ease;
  }

  .timestamp-display:hover:not(.readonly) {
    color: var(--text-primary);
    background-color: var(--hover-bg);
    border-radius: 0.25rem;
    padding: 0.25rem;
    margin: -0.25rem;
  }

  .timestamp-display.readonly {
    cursor: default;
  }

  .timestamp-width-keeper {
    visibility: hidden;
    white-space: nowrap;
  }

  .timestamp-edit-overlay {
    position: absolute;
    top: 0.5rem;
    left: -4.91rem;
    bottom: 0.5rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: var(--bg-primary);
    border: 1px solid var(--primary);
    border-radius: 0.25rem;
    padding: 0.25rem 0.5rem;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    z-index: 1000;
    min-width: 262px;
  }

  .timestamp-edit-overlay.with-fractions {
    min-width: 286px;
  }

  .timestamp-play-btn {
    width: 1.5rem;
    height: 1.5rem;
    border-radius: 50%;
    border: none;
    background: transparent;
    color: var(--primary);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.75rem;
    transition: all 0.2s ease;
    flex-shrink: 0;
    margin-left: 1.3rem;
    margin-right: 0.4rem;
  }

  .timestamp-play-btn:hover:not(:disabled) {
    background-color: var(--primary);
    color: white;
    transform: scale(1.1);
  }

  .timestamp-play-btn:disabled {
    color: var(--text-muted);
    cursor: not-allowed;
    opacity: 0.5;
  }

  .timestamp-play-btn.playing {
    background-color: var(--primary);
    color: white;
  }

  .timestamp-input-wrap {
    position: relative;
    flex: 1;
    display: flex;
    min-width: 0;
  }

  .timestamp-input {
    flex: 1;
    border: none;
    border-radius: 0.25rem;
    padding: 0.25rem 1.4rem;
    font-size: 0.875rem;
    font-family: monospace;
    color: var(--text-primary);
    background: var(--bg-secondary);
    transition: all 0.2s ease;
    min-width: 0;
    width: 100%;
  }

  .jump-btn {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    display: flex;
    align-items: center;
    justify-content: center;
    width: 1.1rem;
    height: 1.1rem;
    padding: 0;
    border: none;
    background: transparent;
    color: var(--text-primary);
    cursor: pointer;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.25s ease;
  }

  .jump-btn.loaded {
    opacity: 1;
    pointer-events: auto;
  }

  .jump-btn :global(svg) {
    opacity: 0.45;
    transition: opacity 0.15s ease;
  }

  .jump-btn:hover:not(:disabled) :global(svg) {
    opacity: 0.9;
  }

  .jump-btn:disabled {
    cursor: default;
  }

  .jump-btn:disabled :global(svg) {
    opacity: 0.2;
  }

  .jump-btn-prev {
    left: 0.15rem;
  }

  .jump-btn-next {
    right: 0.15rem;
  }

  .jump-fetch-error {
    position: absolute;
    right: 0.3rem;
    top: 50%;
    transform: translateY(-50%);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--warning);
    opacity: 0.6;
    cursor: help;
  }

  .timestamp-input:focus {
    outline: none;
    background: var(--bg-primary);
  }

  .timestamp-input.error {
    background: rgba(255, 193, 7, 0.1);
  }

  .timestamp-save-btn,
  .timestamp-cancel-btn,
  .timestamp-warning-btn {
    width: 1.5rem;
    height: 1.5rem;
    border-radius: 0.25rem;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.75rem;
    transition: all 0.2s ease;
    flex-shrink: 0;
    background: transparent;
  }

  .timestamp-save-btn {
    color: var(--success);
  }

  .timestamp-save-btn:hover {
    background-color: var(--success);
    color: white;
    transform: scale(1.1);
  }

  .timestamp-cancel-btn {
    color: var(--danger);
  }

  .timestamp-cancel-btn:hover {
    background-color: var(--danger);
    color: white;
    transform: scale(1.1);
  }

  .timestamp-warning-btn {
    color: var(--warning);
    cursor: help;
    position: relative;
  }

  .transcript-cell {
    min-width: 120px;
    max-width: 280px;
    padding: 0.75rem;
    line-height: 1.4;
    vertical-align: middle;
  }

  .restore-cell {
    padding: 0;
    text-align: center;
  }

  .transcript-tooltip-wrapper {
    display: block;
    position: relative;
  }

  .transcript-text {
    display: block;
    color: var(--text-secondary);
    font-size: 0.875rem;
    font-style: italic;
    line-height: 1.4;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .title-cell {
    min-width: 300px;
    padding-left: 0.5rem;
    padding-right: 0.25rem;
    vertical-align: middle;
    display: table-cell;
  }

  .chapter-title-input {
    flex: 1;
    border: 1px solid transparent;
    background: rgba(255, 255, 255, 0.05);
    border-radius: 0.25rem;
    padding: 0.5rem;
    font-size: 0.875rem;
    color: var(--text-primary);
    transition: all 0.2s ease;
    line-height: 1.5rem;
    font-family: inherit;
    width: 100%;
    box-sizing: border-box;
  }

  .chapter-title-input:hover {
    background: rgba(255, 255, 255, 0.05);
    border-color: var(--border-color);
  }

  .chapter-title-input:focus {
    background: var(--bg-secondary);
    border: 1px solid var(--primary);
    border-radius: 0.25rem;
    outline: none;
  }

  .play-button {
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

  .play-button:hover {
    color: white;
    background-color: var(--primary-hover);
    transform: scale(1.1);
  }

  .play-button.playing {
    color: white;
    background-color: var(--primary-color);
  }

  .transcribe-button {
    width: 2rem;
    height: 2rem;
    border-radius: 50%;
    border: none;
    background-color: transparent;
    color: var(--text-secondary);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.75rem;
    transition: all 0.2s ease;
  }

  .transcribe-button:hover:not(:disabled) {
    color: var(--text-primary);
    background-color: #8883;
    transform: scale(1.1);
  }

  .transcribe-button:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .chapter-row td {
    vertical-align: middle !important;
  }

  .chapter-row td:last-child {
    height: 100%;
  }

  .action-buttons {
    display: flex;
    gap: 0.25rem;
    align-items: center;
    height: 100%;
    justify-content: flex-start;
    margin-left: -0.35rem;
  }

  .delete-btn {
    width: 2rem;
    height: 2rem;
    border-radius: 0.25rem;
    color: var(--danger);
    background-color: transparent;
    border: none;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    transition: all 0.2s ease;
  }

  .delete-btn:hover {
    transform: scale(1.1);
    color: white;
  }

  .restore-btn {
    color: var(--primary-contrast);
    border-color: transparent;
    display: flex;
    align-items: center;
  }

  .restore-btn:hover:not(:disabled) {
    border-color: transparent;
    color: white;
    background-color: var(--primary-color);
  }

  .restore-btn:disabled {
    opacity: 1;
    color: var(--border-color);
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

  .badge {
    display: inline-block;
    font-size: 0.75rem;
    font-weight: 600;
    text-align: center;
    white-space: nowrap;
    vertical-align: baseline;
    border-radius: 0.375rem;
  }

  .float-right {
    float: right;
  }

  /* Responsive design */
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

    .button-group {
      justify-content: center;
    }

    .table-container {
      overflow-x: auto;
    }

    .transcript-cell {
      min-width: 120px;
      max-width: 200px;
    }

    .title-cell {
      min-width: 200px;
    }

    .chapter-title-input {
      font-size: 0.75rem;
    }
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
    flex: 2;
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

  .popover-divider {
    width: 1px;
    background: var(--border-color);
  }

  .settings-grid {
    display: flex;
    flex-direction: column;
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

  .tools-split-layout {
    display: flex;
    gap: 0.75rem;
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

  @media (max-width: 600px) {
    .tools-popover {
      flex-direction: column;
      gap: 1rem;
    }

    .tools-split-layout {
      flex-direction: column;
      gap: 0.5rem;
    }

    .popover-divider {
      width: 100%;
      height: 1px;
      margin: 0;
    }
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

  .selection-info {
    display: flex;
    align-items: center;
  }

  .offset-cell {
    white-space: nowrap;
    font-family: monospace;
    font-size: 0.85rem;
    color: var(--text-secondary);
    padding: 0.5rem;
  }

  .offset-display {
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }

  .offset-display.warning {
    color: var(--warning-color, #f59e0b);
  }

  .warning-icon {
    display: flex;
    align-items: center;
    cursor: help;
    position: relative;
  }

  .header-with-icon {
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }
</style>
