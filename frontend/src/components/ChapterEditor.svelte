<script>
    import {onDestroy, onMount} from "svelte";
    import {audio, currentSegmentId, isPlaying} from "../stores/audio.js";
    import {
        canRedo,
        canUndo,
        chapters,
        progress,
        selectionStats,
        session,
        pendingAddChapterDialog,
    } from "../stores/session.js";
    import {api, handleApiError} from "../utils/api.js";
    import AddChapterDialog from "./AddChapterDialog.svelte";
    import AICleanupDialog from "./AICleanupDialog.svelte";
    import Icon from "./Icon.svelte";

    // Icons
    import ArrowRight from "@lucide/svelte/icons/arrow-right";
    import BookMarked from "@lucide/svelte/icons/book-marked";
    import Check from "@lucide/svelte/icons/check";
    import ChevronUp from "@lucide/svelte/icons/chevron-up";
    import Pause from "@lucide/svelte/icons/pause";
    import Play from "@lucide/svelte/icons/play";
    import Plus from "@lucide/svelte/icons/plus";
    import Redo from "@lucide/svelte/icons/redo";
    import Settings from "@lucide/svelte/icons/settings";
    import Trash2 from "@lucide/svelte/icons/trash-2";
    import TriangleAlert from "@lucide/svelte/icons/triangle-alert";
    import Undo from "@lucide/svelte/icons/undo";
    import X from "@lucide/svelte/icons/x";
    import CircleHelp from "@lucide/svelte/icons/circle-help";

    let mounted = false;
    let loading = $state(false);
    let error = $state(null);
    let aiCleanupError = $state(null);
    let showAIConfirmation = $state(false);
    let showAddChapterDialog = $state(false);
    let addChapterDialogChapterId = $state(null);
    let addChapterDialogDefaultTab = $state(null);

    let showSettings = $state(false);
    let editorSettings = $state({
        tab_navigation: false,
        hide_transcriptions: false,
        show_formatted_time: true
    });

    // Timestamp editing state
    let editingTimestampId = $state(null);
    let timestampInputValue = $state("");
    let timestampValidationError = $state(null);
    let showEditButton = $state(null);

    // Store textarea references for auto-resizing
    let textareaRefs = new Map();

    // Check if any chapters have transcriptions
    let hasTranscriptions = $derived(
        $chapters.some(
            (chapter) => chapter.asr_title && chapter.asr_title.trim() !== "",
        ),
    );

    let hasAlignmentData = $derived(
        $chapters.some(
            (chapter) => chapter.realignment != null
        )
    );

    let showTranscriptions = $derived(
        hasTranscriptions && !editorSettings.hide_transcriptions && !hasAlignmentData
    );

    // Load chapters and AI options when component mounts
    onMount(async () => {
        mounted = true;
        await loadEditorSettings();
        await loadChapters();
        window.addEventListener("keydown", handleKeydown);
    });

    onDestroy(() => {
        audio.stop();
        window.removeEventListener("keydown", handleKeydown);
    });

    // Resize all text areas after updates (for programmatic value changes)
    $effect(() => {
        if (mounted) {
            textareaRefs.forEach((textarea) => {
                resizeTextareaByElement(textarea);
            });
        }
    });

    // Monitor AI cleanup progress for errors
    $effect(() => {
        if ($progress && $progress.step === "ai_cleanup") {
            if (
                $progress.percent === 0 &&
                $progress.message &&
                ($progress.message.includes("failed") ||
                    $progress.message.includes("error") ||
                    $progress.message.includes("authentication") ||
                    $progress.message.includes("rate limit") ||
                    $progress.message.includes("connection"))
            ) {
                // Set AI cleanup error with additional context
                const errorDetails = $progress.details || {};
                aiCleanupError = {
                    message: $progress.message,
                    provider: errorDetails.provider || "Unknown",
                    errorType: errorDetails.error_type || "unknown",
                    timestamp: new Date(),
                };
            } else if ($progress.percent > 0) {
                // Clear error if processing progresses successfully
                aiCleanupError = null;
            }
        } else if (
            $progress &&
            $progress.step === "chapter_editing" &&
            $progress.percent === 100
        ) {
            // Clear error when successfully completing and returning to chapter editing
            aiCleanupError = null;
        }
    });

    async function loadEditorSettings() {
        try {
            const response = await api.config.getEditorSettings();
            editorSettings = response;
        } catch (err) {
            console.warn('Failed to load editor settings:', err);
        }
    }

    async function saveEditorSettings(updates) {
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

    async function handleTabNavigationChange(event) {
        const enabled = event.target.checked;
        await saveEditorSettings({ tab_navigation: enabled });
    }

    async function handleHideTranscriptionsChange(event) {
        const enabled = event.target.checked;
        await saveEditorSettings({ hide_transcriptions: enabled });
    }

    async function handleTimeFormatChange(event) {
        const enabled = event.target.checked;
        await saveEditorSettings({ show_formatted_time: enabled });
    }

    // Keyboard shortcuts
    function handleKeydown(event) {
        // Check if user is typing in an input field
        if (
            event.target.tagName === "TEXTAREA" ||
            event.target.tagName === "INPUT"
        ) {
            if (event.key === "Tab" && editorSettings.tab_navigation) {
                event.preventDefault();
                handleTabNavigation(event.target, event.shiftKey);
            }
            return;
        }

        const isMac = navigator.platform.toUpperCase().indexOf("MAC") >= 0;
        const ctrlKey = isMac ? event.metaKey : event.ctrlKey;

        if (ctrlKey && event.key === "z" && !event.shiftKey) {
            event.preventDefault();
            undo();
        } else if (
            ctrlKey &&
            (event.key === "y" || (event.key === "z" && event.shiftKey))
        ) {
            event.preventDefault();
            redo();
        }
    }

    function handleTabNavigation(currentTextarea, isReverse = false) {
        const selectedChapters = $chapters.filter(ch => ch.selected);
        const currentChapterId = getCurrentChapterIdFromTextarea(currentTextarea);
        const currentChapterIndex = selectedChapters.findIndex(ch => ch.id === currentChapterId);
        
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
            const targetTextarea = textareaRefs.get(targetChapter.id);
            if (targetTextarea) {
                targetTextarea.focus();
                targetTextarea.select();
                
                scrollToFocusedInput(targetTextarea);
            }
        }
    }

    function scrollToFocusedInput(textarea) {
        requestAnimationFrame(() => {
            const textareaRect = textarea.getBoundingClientRect();
            const stickyBar = document.querySelector('.sticky-action-bar');
            const stickyBarRect = stickyBar ? stickyBar.getBoundingClientRect() : null;
            
            const bottomBarHeight = stickyBarRect ? stickyBarRect.height : 0;
            const padding = 32;
            const scrollTarget = textareaRect.bottom + bottomBarHeight + padding;
            const viewportHeight = window.innerHeight;
            
            if (scrollTarget > viewportHeight) {
                const scrollOffset = scrollTarget - viewportHeight;
                window.scrollBy({
                    top: scrollOffset,
                    behavior: 'smooth'
                });
            }
        });
    }

    function getCurrentChapterIdFromTextarea(textarea) {
        for (const [chapterId, ref] of textareaRefs.entries()) {
            if (ref === textarea) {
                return chapterId;
            }
        }
        return null;
    }

    async function loadChapters() {
        if ($session.step !== "chapter_editing") return;

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
    async function updateChapterTitle(chapterId, newTitle) {
        try {
            await api.chapters.updateTitle(chapterId, newTitle);
        } catch (err) {
            error = handleApiError(err);
        }
    }

    async function toggleChapterSelection(chapterId, selected) {
        try {
            await api.chapters.toggleSelection(chapterId, selected);
        } catch (err) {
            error = handleApiError(err);
        }
    }

    async function deleteChapter(chapterId) {
        try {
            await api.chapters.delete(chapterId);
            // Clear audio cache when chapters are deleted to prevent wrong segments from playing
            audio.clearSegmentCache();
        } catch (err) {
            error = handleApiError(err);
        }
    }

    // Audio playback
    async function playChapter(chapterId) {
        if ($session.step !== "chapter_editing") return;

        try {
            if ($currentSegmentId === chapterId && $isPlaying) {
                // Stop the current playback instead of pausing
                audio.stop();
            } else {
                const chapter = $chapters.find(ch => ch.id === chapterId);
                const chapterTimestamp = chapter ? chapter.timestamp : null;
                
                await audio.play(chapterId, chapterTimestamp);
            }
        } catch (err) {
            error = `Failed to play audio: ${err.message}`;
        }
    }

    // Format timestamp
    function formatTimestamp(seconds) {
        if (!editorSettings.show_formatted_time) {
            // Show raw seconds with 2 decimal places
            return seconds.toFixed(2);
        }

        // Show formatted time hh:mm:ss
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);

        if (hours > 0) {
            return `${hours}:${minutes.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
        } else {
            return `${minutes}:${secs.toString().padStart(2, "0")}`;
        }
    }

    // Title editing with debounce
    let titleTimeouts = new Map();

    function handleTitleEdit(chapterId, newTitle, originalTitle) {
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

    // Auto-resize textarea up to max 3 lines
    function autoResizeTextarea(event) {
        const textarea = event.target;
        textarea.style.height = "auto";
        const newHeight = Math.min(textarea.scrollHeight, 72); // Max 72px (3 lines * 24px including padding)
        textarea.style.height = newHeight + "px";
    }

    // Auto-resize textarea when value changes (for programmatic updates)
    function resizeTextareaByElement(textarea) {
        if (textarea) {
            textarea.style.height = "auto";
            const newHeight = Math.min(textarea.scrollHeight, 72);
            textarea.style.height = newHeight + "px";
        }
    }

    // Action to track textarea elements
    function trackTextarea(node, chapterId) {
        textareaRefs.set(chapterId, node);
        // Initial resize
        resizeTextareaByElement(node);

        return {
            destroy() {
                textareaRefs.delete(chapterId);
            },
        };
    }

    // Action to focus input elements
    function focusInput(node) {
        node.focus();
        node.select();
    }

    // AI cleanup
    async function processSelectedWithAI() {
        if ($selectionStats.selected === 0) return;
        showAIConfirmation = true;
    }

    async function handleAICleanupConfirm(event) {
        try {
            await api.batch.processSelected(event.detail);
        } catch (err) {
            error = handleApiError(err);
        }
    }

    function handleAICleanupCancel() {
        showAIConfirmation = false;
    }

    function handleAICleanupError(event) {
        error = handleApiError(event.detail);
    }

    // Quick restore ASR title
    async function restoreAsrTitle(chapterId, asrTitle) {
        if ($session.step !== "chapter_editing") return;

        try {
            await updateChapterTitle(chapterId, asrTitle);
        } catch (err) {
            error = handleApiError(err);
        }
    }

    function openAddChapterDialog(chapterId, defaultTab = null) {
        addChapterDialogChapterId = chapterId;
        addChapterDialogDefaultTab = defaultTab;
        showAddChapterDialog = true;
    }

    function handleAddChapterConfirm(event) {
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
            openAddChapterDialog(chapter_id, open_tab);
        }
    });

    // Go to review page
    function goToReview() {
        window.scrollTo({top: 0, behavior: "instant"});
        api.session
            .gotoReview()
            .then(() => session.loadActiveSession())
            .catch((err) => {
                error = handleApiError(err);
            });
    }

    // Timestamp editing functions
    function startTimestampEdit(chapterId, currentTimestamp) {
        editingTimestampId = chapterId;
        timestampInputValue = formatTimestamp(currentTimestamp);
        timestampValidationError = null;
    }

    function cancelTimestampEdit() {
        editingTimestampId = null;
        timestampInputValue = "";
        timestampValidationError = null;
    }

    function parseTimestampInput(input) {
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

    function validateTimestamp(chapterId, timestamp) {
        const currentChapterIndex = $chapters.findIndex(ch => ch.id === chapterId);

        if (currentChapterIndex === -1) return null;

        const prevChapter = currentChapterIndex > 0 ? $chapters[currentChapterIndex - 1] : null;
        const nextChapter = currentChapterIndex < $chapters.length - 1 ? $chapters[currentChapterIndex + 1] : null;

        const minTimestamp = prevChapter ? prevChapter.timestamp + 1 : 0;
        const maxTimestamp = nextChapter ? nextChapter.timestamp - 1 : $session.book?.duration - 1 || Infinity;

        if (timestamp < minTimestamp) {
            return `Timestamp must be at least ${formatTimestamp(minTimestamp)}`;
        }

        if (timestamp > maxTimestamp) {
            return `Timestamp must be at most ${formatTimestamp(maxTimestamp)}`;
        }

        return null;
    }

    async function saveTimestampEdit(chapterId) {
        if (timestampValidationError) {
            return;
        }

        const parsedTimestamp = parseTimestampInput(timestampInputValue);
        if (parsedTimestamp === null) {
            timestampValidationError = "Invalid timestamp format. Use hh:mm:ss, mm:ss, or seconds.";
            return;
        }

        try {
            await api.chapters.updateTimestamp(chapterId, parsedTimestamp);
            cancelTimestampEdit();
        } catch (err) {
            timestampValidationError = handleApiError(err);
        }
    }

    function handleTimestampInputKeydown(event, chapterId) {
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
            if ($currentSegmentId && $currentSegmentId.startsWith('timestamp-edit-')) {
                audio.stop();
            }
            const current = parseTimestampInput(timestampInputValue) || 0;
            timestampInputValue = formatTimestamp(current + 1);
        } else if (event.key === 'ArrowDown') {
            event.preventDefault();
            if ($currentSegmentId && $currentSegmentId.startsWith('timestamp-edit-')) {
                audio.stop();
            }
            const current = parseTimestampInput(timestampInputValue) || 0;
            timestampInputValue = formatTimestamp(Math.max(0, current - 1));
        }
    }

    function handleTimestampInputChange() {
        if ($currentSegmentId && $currentSegmentId.startsWith('timestamp-edit-')) {
            audio.stop();
        }

        const parsedTimestamp = parseTimestampInput(timestampInputValue);
        if (parsedTimestamp !== null) {
            timestampValidationError = validateTimestamp(editingTimestampId, parsedTimestamp);
        } else {
            timestampValidationError = "Invalid timestamp format. Use hh:mm:ss, mm:ss, or seconds.";
        }
    }

    function playFromEditedTimestamp(chapterId) {
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
                error = `Failed to play audio: ${err.message}`;
            }
        }
    }
</script>

<div class="chapter-editor">
    {#if error}
        <div class="alert alert-danger">
            {error}
            <button
                    class="btn btn-sm btn-outline float-right"
                    onclick={() => (error = null)}
            >
                Dismiss
            </button>
        </div>
    {/if}

    {#if aiCleanupError}
        <div class="alert alert-danger">
            <div class="alert-header">
                <TriangleAlert size="20"/>
                <strong>AI Cleanup Failed</strong>
                <button
                        class="btn btn-sm btn-outline float-right"
                        onclick={() => (aiCleanupError = null)}
                >
                    Dismiss
                </button>
            </div>
            <div class="alert-content">
                <p>{aiCleanupError.message}</p>
                {#if aiCleanupError.provider && aiCleanupError.provider !== "Unknown"}
                    <small class="text-muted">Provider: {aiCleanupError.provider}</small>
                {/if}
            </div>
        </div>
    {/if}

    <!-- Page Header -->
    <div class="page-header">
        <h2>Edit Chapters</h2>
        <p>Review and edit your audiobook chapters</p>
    </div>

    <!-- Chapter Table -->
    {#if loading}
        <div class="text-center p-4">
            <div class="spinner"></div>
            <p>Loading chapters...</p>
        </div>
    {:else if $chapters.length === 0}
        <div class="empty-state">
            <div class="empty-icon">
                <BookMarked size="48"/>
            </div>
            <h3>No chapters found</h3>
            <p>Chapters will appear here once processing is complete.</p>
        </div>
    {:else}
        <div class="table-container" class:hide-transcriptions={editorSettings.hide_transcriptions}>
            <table class="table">
                <thead>
                <tr>
                    <th width="1">
                        <input
                                type="checkbox"
                                checked={$selectionStats.selected === $selectionStats.total &&
                  $selectionStats.total > 0}
                                indeterminate={$selectionStats.selected > 0 &&
                  $selectionStats.selected < $selectionStats.total}
                                onchange={(e) =>
                  e.target.checked
                    ? api.batch.selectAll()
                    : api.batch.deselectAll()}
                        />
                    </th>
                    <th width="1" class="time-header">
                        Time
                    </th>
                    {#if hasAlignmentData}
                        <th width="1" class="offset-header">
                            <div class="header-with-icon">
                                Offset
                                <div class="help-icon" data-tooltip="The time difference between the source chapter timestamp and the realigned timestamp.">
                                    <CircleHelp size="14" />
                                </div>
                            </div>
                        </th>
                    {/if}
                    {#if showTranscriptions}
                        <th width="1">Transcription</th>
                        <th width="1"></th>
                    {/if}
                    <th>Title</th>
                    <th width="1">Actions</th>
                    <th width="1" style="min-width: 1; padding: 0;"></th>
                </tr>
                </thead>
                <tbody>
                {#each $chapters.filter((ch) => ch.id !== undefined && ch.id !== null) as chapter (chapter.id)}
                    <tr class="chapter-row" class:dimmed={!chapter.selected}>
                        <td>
                            <input
                                    type="checkbox"
                                    checked={chapter.selected}
                                    onchange={(e) =>
                    toggleChapterSelection(chapter.id, e.target.checked)}
                            />
                        </td>
                        <td class="timestamp" class:editing={editingTimestampId === chapter.id}>
                            {#if editingTimestampId === chapter.id}
                                <div class="timestamp-edit-overlay">
                                    <button
                                        class="timestamp-play-btn"
                                        class:disabled={timestampValidationError}
                                        class:playing={$currentSegmentId === `timestamp-edit-${chapter.id}` && $isPlaying}
                                        onclick={() => playFromEditedTimestamp(chapter.id)}
                                        title={timestampValidationError ? "Cannot play: invalid timestamp" : "Play from edited timestamp"}
                                        disabled={timestampValidationError}
                                    >
                                        {#if $currentSegmentId === `timestamp-edit-${chapter.id}` && $isPlaying}
                                            <Pause size="14"/>
                                        {:else}
                                            <Play size="14"/>
                                        {/if}
                                    </button>
                                    <input
                                        class="timestamp-input"
                                        class:error={timestampValidationError}
                                        bind:value={timestampInputValue}
                                        onkeydown={(e) => handleTimestampInputKeydown(e, chapter.id)}
                                        oninput={handleTimestampInputChange}
                                        placeholder="hh:mm:ss or seconds"
                                        use:focusInput
                                    />
                                    {#if timestampValidationError}
                                        <button
                                            class="timestamp-warning-btn"
                                            data-tooltip={timestampValidationError}
                                        >
                                            <TriangleAlert size="14"/>
                                        </button>
                                    {:else}
                                        <button
                                            class="timestamp-save-btn"
                                            onclick={() => saveTimestampEdit(chapter.id)}
                                            title="Save timestamp"
                                        >
                                            <Check size="14"/>
                                        </button>
                                    {/if}
                                    <button
                                        class="timestamp-cancel-btn"
                                        onclick={cancelTimestampEdit}
                                        title="Cancel editing"
                                    >
                                        <X size="14"/>
                                    </button>
                                </div>
                            {:else}
                                <button
                                    class="timestamp-display"
                                    onclick={() => startTimestampEdit(chapter.id, chapter.timestamp)}
                                    title="Edit timestamp"
                                >
                                    {formatTimestamp(chapter.timestamp)}
                                </button>
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
                                            <div class="warning-icon" 
                                                 data-tooltip={isGuess ? "This timestamp is an estimate. Please verify." : "Low confidence alignment. Please verify."}>
                                                <TriangleAlert size="14" />
                                            </div>
                                        {/if}
                                    </div>
                                {/if}
                            </td>
                        {/if}
                        {#if showTranscriptions}
                            <td class="original-title-cell">
                   <span class="asr-title" title={chapter.asr_title}>
                     {chapter.asr_title?.length > 120
                         ? chapter.asr_title.substring(0, 120) + "…"
                         : chapter.asr_title}
                   </span>
                            </td>
                            <td class="restore-cell">
                                <button
                                        class="btn btn-sm btn-outline restore-btn"
                                        onclick={() =>
                       restoreAsrTitle(chapter.id, chapter.asr_title)}
                                        disabled={chapter.current_title === chapter.asr_title}
                                        title="Replace with transcribed title"
                                >
                                    <ArrowRight size="14"/>
                                </button>
                            </td>
                        {/if}
                        <td class="title-cell">
                <textarea
                        class="chapter-title-input"
                        value={chapter.current_title}
                        oninput={(e) => {
                    handleTitleEdit(
                      chapter.id,
                      e.target.value,
                      chapter.current_title,
                    );
                    autoResizeTextarea(e);
                  }}
                        use:trackTextarea={chapter.id}
                        placeholder=""
                        rows="1"
                ></textarea>
                        </td>
                        <td>
                            <div class="action-buttons">
                                <button
                                        class="play-button"
                                        class:playing={$currentSegmentId === chapter.id &&
                      $isPlaying}
                                        onclick={() => playChapter(chapter.id)}
                                        title={$currentSegmentId === chapter.id && $isPlaying
                      ? "Stop"
                      : "Play"}
                                >
                                    {#if $currentSegmentId === chapter.id && $isPlaying}
                                        <Pause size="16"/>
                                    {:else}
                                        <Play size="16"/>
                                    {/if}
                                </button>
                                {#if chapter.timestamp > 0.01}
                                    <button
                                            class="btn btn-sm btn-danger delete-btn"
                                            onclick={() => deleteChapter(chapter.id)}
                                            title="Delete chapter"
                                    >
                                        <Trash2 size="16"/>
                                    </button>
                                {/if}
                            </div>
                        </td>
                        <td class="add-chapter-cell-container">
                            <div class="add-chapter-cell">
                                <button
                                    class="add-chapter-button"
                                    onclick={() => openAddChapterDialog(chapter.id)}
                                    title="Add chapter after this one"
                                    >
                                    <Plus size="16"/>
                                </button>
                            </div>
                        </td>
                    </tr>
                {/each}
                </tbody>
            </table>
        </div>

        <!-- Sticky Action Bar -->
        <div class="sticky-action-bar">
            <!-- Settings Panel -->
            {#if showSettings}
                <div class="settings-section">
                    <div class="settings-content">
                        <h4>Editor Settings</h4>
                        <div class="setting-item">
                            <label class="setting-label">
                                <input
                                    type="checkbox"
                                    checked={editorSettings.tab_navigation}
                                    onchange={handleTabNavigationChange}
                                />
                                <span class="setting-text">
                                    Tab to Next Title
                                </span>
                            </label>
                            <div class="setting-description">
                                Press Tab while editing a chapter title to move focus to the next selected chapter
                            </div>
                        </div>

                        {#if hasTranscriptions}
                            <div class="setting-item">
                                <label class="setting-label">
                                    <input
                                        type="checkbox"
                                        checked={editorSettings.hide_transcriptions}
                                        onchange={handleHideTranscriptionsChange}
                                    />
                                    <span class="setting-text">
                                        Hide Transcriptions
                                    </span>
                                </label>
                                <div class="setting-description">
                                    Hide the original transcriptions to focus on editing titles
                                </div>
                            </div>
                        {/if}

                        <div class="setting-item">
                            <label class="setting-label">
                                <input
                                    type="checkbox"
                                    checked={editorSettings.show_formatted_time}
                                    onchange={handleTimeFormatChange}
                                />
                                <span class="setting-text">
                                    Format Timestamps
                                </span>
                            </label>
                            <div class="setting-description">
                                Show timestamps as hh:mm:ss instead of seconds
                            </div>
                        </div>
                    </div>
                </div>
            {/if}

            <div class="action-bar-content">
                <div class="selection-info">
                    <div class="settings-control">
                        <div class="chevron-indicator" class:expanded={showSettings}>
                            <ChevronUp size="12"/>
                        </div>
                        <button
                            class="settings-toggle"
                            onclick={toggleSettingsPanel}
                            title="Settings"
                        >
                            <Settings size="20"/>
                        </button>
                    </div>
          <span class="badge badge-primary">
            {$selectionStats.selected} of {$selectionStats.total} selected
          </span>
                </div>

                <div class="button-group">
                    <button
                            class="btn btn-secondary btn-sm"
                            onclick={undo}
                            disabled={!$canUndo}
                            title="Undo last action"
                    >
                        <Undo size="16"/>
                        Undo
                    </button>
                    <button
                            class="btn btn-secondary btn-sm"
                            onclick={redo}
                            disabled={!$canRedo}
                            title="Redo next action"
                    >
                        Redo
                        <Redo size="16"/>
                    </button>
                </div>

                <div class="button-group">
                    <button
                            class="btn btn-ai btn-sm"
                            onclick={processSelectedWithAI}
                            disabled={$selectionStats.selected === 0 || loading}
                            title="Enhance selected chapter titles with AI"
                    >
                        <Icon name="ai" size="16" color="white"/>
                        Clean Up Selected
                    </button>
                    <button
                            class="btn btn-verify btn-sm action-bar-verify"
                            onclick={goToReview}
                            disabled={$selectionStats.selected === 0}
                    >
                        Review Selected
                        <ArrowRight size="16"/>
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
        cueSources={$session.cueSources || []}
        on:confirm={handleAICleanupConfirm}
        on:cancel={handleAICleanupCancel}
        on:error={handleAICleanupError}
/>

<!-- Add Chapter Dialog -->
<AddChapterDialog
        bind:isOpen={showAddChapterDialog}
        chapterId={addChapterDialogChapterId}
        defaultTab={addChapterDialogDefaultTab}
        editorSettings={editorSettings}
        on:confirm={handleAddChapterConfirm}
        on:cancel={handleAddChapterCancel}
/>

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

    .sticky-action-bar {
        position: sticky;
        bottom: 1rem;
        background: var(--edit-bar-bg);
        border: 1px solid var(--border-color);
        border-radius: 0.5rem;
        box-shadow: 0 0.25rem 0.5rem rgba(0, 0, 0, 0.1),
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

    .timestamp-display:hover {
        color: var(--text-primary);
        background-color: var(--hover-bg);
        border-radius: 0.25rem;
        padding: 0.25rem;
        margin: -0.25rem;
    }



    .timestamp-edit-overlay {
        position: absolute;
        top: 0.5rem;
        left: -4rem;
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
        min-width: 230px;
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

    .timestamp-input {
        flex: 1;
        border: none;
        border-radius: 0.25rem;
        padding: 0.25rem 0.5rem;
        font-size: 0.875rem;
        font-family: monospace;
        color: var(--text-primary);
        background: var(--bg-secondary);
        transition: all 0.2s ease;
        min-width: 0;
        width: 100%;
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

    .timestamp-warning-btn[data-tooltip]:hover::after {
        content: attr(data-tooltip);
        position: absolute;
        transform: translateY(calc(-50% - 18px));
        padding: 8px 12px;
        background: var(--bg-primary);
        color: var(--text-primary);
        border: 1px solid var(--border-color);
        border-radius: 6px;
        font-size: 0.875rem;
        line-height: 1.4;
        white-space: pre-line;
        max-width: 320px;
        width: max-content;
        z-index: 10001;
        pointer-events: none;
    }

    .timestamp-warning-btn[data-tooltip]:hover::before {
        content: "";
        position: absolute;
        bottom: 100%;
        left: 50%;
        transform: translateX(-50%);
        margin-bottom: -5px;
        border: 6px solid transparent;
        border-top-color: var(--border-color);
        z-index: 10002;
    }

    .original-title-cell {
        min-width: 320px;
        max-width: 480px;
        padding: 0.75rem;
        line-height: 1.4;
        vertical-align: top;
    }

    .restore-cell {
        padding: 0;
        text-align: center;
    }

    .asr-title {
        color: var(--text-secondary);
        font-size: 0.875rem;
        font-style: italic;
        word-wrap: break-word;
        overflow-wrap: break-word;
        word-break: break-word;
        hyphens: auto;
        line-height: 1.4;
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
        resize: none;
        overflow-y: hidden;
        min-height: 1.5rem;
        max-height: 4.5rem;
        line-height: 1.5rem;
        font-family: inherit;
        width: 100%;
        box-sizing: border-box;
        scrollbar-width: none;
        -ms-overflow-style: none;
        margin-top: 0.2rem;
        margin-bottom: -0.25rem;
    }

    :global(.hide-transcriptions) .chapter-title-input {
        max-height: 2.5rem;
        overflow: hidden;
    }

    .chapter-title-input::-webkit-scrollbar {
        display: none;
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

    .chapter-row td {
        vertical-align: middle !important;
    }

    .chapter-row td:last-child {
        height: 100%;
    }

    .action-buttons {
        display: flex;
        gap: 0.5rem;
        align-items: center;
        height: 100%;
        justify-content: flex-start;
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

        .original-title-cell {
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

    .action-bar-verify {
        padding: 0 0.6rem 0 1rem;
        gap: 0.20rem;
    }

    .settings-section {
        border-bottom: 1px solid var(--border-color);
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
    }

    .settings-content h4 {
        margin: 0 0 1rem 0;
        color: var(--text-primary);
        font-size: 1rem;
        font-weight: 600;
    }

    .setting-item {
        margin-bottom: 0.75rem;
    }

    .setting-label {
        display: flex;
        align-items: flex-start;
        gap: 0.5rem;
        cursor: pointer;
        font-size: 0.875rem;
    }

    .setting-label input[type="checkbox"] {
        margin-top: 0.25rem;
        flex-shrink: 0;
    }

    .setting-text {
        color: var(--text-primary);
        font-weight: 500;
    }

    .setting-description {
        margin-top: 0.25rem;
        margin-left: 1.75rem;
        font-size: 0.75rem;
        color: var(--text-secondary);
        line-height: 1.4;
    }

    .settings-toggle {
        background: none;
        border: none;
        color: var(--text-secondary);
        cursor: pointer;
        padding: 0.25rem;
        border-radius: 0.25rem;
        margin-right: 0.5rem;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.2s ease;
    }

    .settings-toggle:hover {
        color: var(--text-primary);
        background-color: var(--hover-bg);
    }

    .selection-info {
        display: flex;
        align-items: center;
    }

    .settings-control {
        position: relative;
        display: flex;
        align-items: center;
        margin-right: 0.5rem;
    }

    .chevron-indicator {
        position: absolute;
        top: -14px;
        left: 50%;
        transform: translateX(-10px);
        color: var(--text-muted);
        transition: all 0.15s ease;
        z-index: 1;
        pointer-events: none;
    }

    .chevron-indicator.expanded {
        top: 16px;
        transform: translateX(-10px) rotate(180deg);
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

    .warning-icon[data-tooltip]:hover::after {
        content: attr(data-tooltip);
        position: absolute;
        bottom: 100%;
        left: 50%;
        transform: translateX(-50%);
        margin-bottom: 11px;
        padding: 8px 12px;
        background: var(--bg-primary);
        color: var(--text-primary);
        border: 1px solid var(--border-color);
        border-radius: 6px;
        font-size: 0.75rem;
        line-height: 1.4;
        white-space: pre-line;
        width: max-content;
        max-width: 200px;
        z-index: 10001;
        pointer-events: none;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }

    .warning-icon[data-tooltip]:hover::before {
        content: "";
        position: absolute;
        bottom: 100%;
        left: 50%;
        transform: translateX(-50%);
        border: 6px solid transparent;
        border-top-color: var(--border-color);
        z-index: 10002;
    }

    .header-with-icon {
        display: flex;
        align-items: center;
        gap: 0.25rem;
    }

    .help-icon {
        display: flex;
        align-items: center;
        color: var(--text-secondary);
        cursor: help;
        position: relative;
    }

    .help-icon:hover {
        color: var(--text-primary);
    }

    .help-icon[data-tooltip]:hover::after {
        content: attr(data-tooltip);
        position: absolute;
        bottom: 100%;
        left: 50%;
        transform: translateX(-50%);
        margin-bottom: 11px;
        padding: 8px 12px;
        background: var(--bg-primary);
        color: var(--text-primary);
        border: 1px solid var(--border-color);
        border-radius: 6px;
        font-size: 0.75rem;
        line-height: 1.4;
        white-space: pre-line;
        width: max-content;
        max-width: 200px;
        z-index: 10001;
        pointer-events: none;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        font-weight: normal;
    }

    .help-icon[data-tooltip]:hover::before {
        content: "";
        position: absolute;
        bottom: 100%;
        left: 50%;
        transform: translateX(-50%);
        border: 6px solid transparent;
        border-top-color: var(--border-color);
        z-index: 10002;
    }
</style>
