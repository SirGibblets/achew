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
    } from "../stores/session.js";
    import {api, handleApiError} from "../utils/api.js";
    import AICleanupDialog from "./AICleanupDialog.svelte";
    import Icon from "./Icon.svelte";

    // Icons
    import ArrowRight from "@lucide/svelte/icons/arrow-right";
    import BookMarked from "@lucide/svelte/icons/book-marked";
    import Pause from "@lucide/svelte/icons/pause";
    import Play from "@lucide/svelte/icons/play";
    import Redo from "@lucide/svelte/icons/redo";
    import Trash2 from "@lucide/svelte/icons/trash-2";
    import TriangleAlert from "@lucide/svelte/icons/triangle-alert";
    import Undo from "@lucide/svelte/icons/undo";

    let mounted = false;
    let loading = $state(false);
    let error = $state(null);
    let aiCleanupError = $state(null);
    let showAIConfirmation = $state(false);

    // Time format toggle state - true for hh:mm:ss, false for raw seconds
    let showFormattedTime = $state(true);

    // Store textarea references for auto-resizing
    let textareaRefs = new Map();

    // Check if any chapters have transcriptions
    let hasTranscriptions = $derived(
        $chapters.some(
            (chapter) => chapter.asr_title && chapter.asr_title.trim() !== "",
        ),
    );

    // Load chapters and AI options when component mounts
    onMount(async () => {
        mounted = true;
        await loadChapters();
        window.addEventListener("keydown", handleKeydown);
    });

    onDestroy(() => {
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

    // Keyboard shortcuts for undo/redo
    function handleKeydown(event) {
        // Check if user is typing in an input field
        if (
            event.target.tagName === "TEXTAREA" ||
            event.target.tagName === "INPUT"
        ) {
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
                // Always start fresh playback (no resume functionality)
                await audio.play(chapterId);
            }
        } catch (err) {
            error = `Failed to play audio: ${err.message}`;
        }
    }

    // Format timestamp
    function formatTimestamp(seconds) {
        if (!showFormattedTime) {
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

    // Toggle time format display
    function toggleTimeFormat() {
        showFormattedTime = !showFormattedTime;
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
        <div class="table-container">
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
                    <th
                            width="1"
                            class="time-header"
                            onclick={toggleTimeFormat}
                            title="Click to toggle between hh:mm:ss and seconds"
                    >
                        Time
                    </th>
                    {#if hasTranscriptions}
                        <th width="1">Transcription</th>
                        <th width="1"></th>
                    {/if}
                    <th>Title</th>
                    <th width="1">Actions</th>
                    <!-- <th width="10">Ac</th> -->
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
                        <td class="timestamp">
                            {(showFormattedTime, formatTimestamp(chapter.timestamp))}
                        </td>
                        {#if hasTranscriptions}
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
                                <button
                                        class="btn btn-sm btn-danger delete-btn"
                                        onclick={() => deleteChapter(chapter.id)}
                                        title="Delete chapter"
                                >
                                    <Trash2 size="16"/>
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
            <div class="action-bar-content">
                <div class="selection-info">
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
        overflow: hidden;
        border: 1px solid var(--border-color);
    }

    .table thead th {
        text-align: left;
    }

    .time-header {
        cursor: pointer;
        user-select: none;
        position: relative;
    }

    .time-header:hover {
        background-color: var(--hover-bg);
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
</style>
