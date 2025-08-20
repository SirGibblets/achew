<script>
    import {onDestroy, onMount} from "svelte";
    import {slide} from "svelte/transition";
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
    import ChapterModal from "./ChapterModal.svelte";
    import Icon from "./Icon.svelte";

    // Icons
    import ArrowRight from "@lucide/svelte/icons/arrow-right";
    import Ban from "@lucide/svelte/icons/ban";
    import BookMarked from "@lucide/svelte/icons/book-marked";
    import ChevronDown from "@lucide/svelte/icons/chevron-down";
    import CircleQuestionMark from "@lucide/svelte/icons/circle-question-mark";
    import Delete from "@lucide/svelte/icons/delete";
    import Eye from "@lucide/svelte/icons/eye";
    import List from "@lucide/svelte/icons/list";
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

    // AI Cleanup options
    let aiOptions = $state({
        inferOpeningCredits: true,
        inferEndCredits: true,
        assumeAllValid: false,
        usePreferredTitles: false,
        preferredTitlesSource: "",
        additionalInstructions: "",
        provider_id: "",
        model_id: "",
    });

    // Features section collapsed state
    let featuresCollapsed = $state(true);

    // Time format toggle state - true for hh:mm:ss, false for raw seconds
    let showFormattedTime = $state(true);

    // Store textarea references for auto-resizing
    let textareaRefs = new Map();

    // Available chapter sources for preferred titles
    let availableChapterSources = $state([]);

    // Chapter titles modal state
    let showChapterTitlesModal = $state(false);
    let chapterTitlesModalTitle = $state("");
    let chapterTitlesModalData = $state([]);
    let chapterTitlesModalLoading = false;

    // LLM Provider and Model state
    let availableProviders = $state([]);
    let availableModels = $state([]);
    let loadingModels = $state(false);

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
        await loadAIOptions();
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

    async function loadAIOptions() {
        if ($session.step !== "chapter_editing") return;

        try {
            const options = await api.batch.getAIOptions();
            aiOptions = options;
        } catch (err) {
            // Use defaults if loading fails
            console.warn("Failed to load AI options, using defaults:", err);
        }

        // Load available chapter sources and LLM providers
        await loadAvailableChapterSources();
        await loadAvailableProviders();
    }

    async function saveAIOptions() {
        if ($session.step !== "chapter_editing") return;

        try {
            await api.batch.updateAIOptions(aiOptions);
        } catch (err) {
            console.warn("Failed to save AI options:", err);
        }
    }

    async function loadAvailableChapterSources() {
        if ($session.step !== "chapter_editing") return;

        availableChapterSources = [];

        // Get existing cue sources from session state (available during chapter_editing step)
        const cueSources = $session.cueSources || [];

        console.log("Existing Cue Sources:", cueSources);

        if (cueSources.length > 0) {
            availableChapterSources = cueSources.map((source) => ({
                id: source.id,
                name: source.name,
                count: source.cues.length,
                chapters: source.cues.map((cue) => ({
                    timestamp: cue.timestamp,
                    title: cue.title || `Chapter ${source.cues.indexOf(cue) + 1}`,
                })),
            }));
        }

        // Set default source if available
        if (
            availableChapterSources.length > 0 &&
            !aiOptions.preferredTitlesSource
        ) {
            aiOptions.preferredTitlesSource = availableChapterSources[0].id;
        }
    }

    async function loadAvailableProviders() {
        try {
            const data = await api.llm.getProviders();
            availableProviders = data.providers;

            // Ensure we have a valid provider selected
            const configuredProviders = availableProviders.filter(
                (p) => p.is_enabled && p.is_configured,
            );

            if (configuredProviders.length === 0) {
                console.warn("No configured AI providers available");
                availableModels = [];
                return;
            }

            // If current provider is not available/configured, switch to first available one
            if (!configuredProviders.find((p) => p.id === aiOptions.provider_id)) {
                aiOptions.provider_id = configuredProviders[0].id;
            }

            // Load models for the current provider
            if (aiOptions.provider_id) {
                await loadAvailableModels(aiOptions.provider_id);
            }
        } catch (err) {
            console.warn("Failed to load LLM providers:", err);
            availableProviders = [];
            availableModels = [];
        }
    }

    async function loadAvailableModels(providerId) {
        if (!providerId) return;

        try {
            loadingModels = true;
            const data = await api.llm.getModels(providerId);
            availableModels = data.models;

            // Set default model if current one is not available
            if (!availableModels.find((m) => m.id === aiOptions.model_id)) {
                if (availableModels.length > 0) {
                    aiOptions.model_id = availableModels[0].id;
                }
            }

            // Set provider-specific default models
            if (aiOptions.model_id === "gpt-4o" && providerId === "ollama") {
                // If switching from OpenAI default to Ollama, pick a common Ollama model
                const commonModels = [
                    "llama3.2:latest",
                    "llama3.1:latest",
                    "gemma2:latest",
                ];
                const foundModel = availableModels.find((m) =>
                    commonModels.some((cm) => m.id.includes(cm.split(":")[0])),
                );
                if (foundModel) {
                    aiOptions.model_id = foundModel.id;
                }
            }
        } catch (err) {
            console.warn("Failed to load models for provider", providerId, ":", err);
            availableModels = [];
        } finally {
            loadingModels = false;
        }
    }

    async function handleProviderChange(newProviderId) {
        aiOptions.provider_id = newProviderId;
        await loadAvailableModels(newProviderId);
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

    async function confirmAICleanup() {
        showAIConfirmation = false;

        try {
            // Save AI options before processing
            await saveAIOptions();

            await api.batch.processSelected(aiOptions);
        } catch (err) {
            error = handleApiError(err);
        }
    }

    function cancelAICleanup() {
        showAIConfirmation = false;
    }

    // View chapter titles modal
    async function viewChapterTitles() {
        if (!aiOptions.preferredTitlesSource) return;

        const selectedSource = availableChapterSources.find(
            (s) => s.id === aiOptions.preferredTitlesSource,
        );
        if (!selectedSource) return;

        chapterTitlesModalTitle = selectedSource.name;
        chapterTitlesModalData = selectedSource.chapters.map((chapter, index) => ({
            timestamp: chapter.timestamp,
            title: chapter.title || `Chapter ${index + 1}`,
        }));
        showChapterTitlesModal = true;
    }

    function closeChapterTitlesModal() {
        showChapterTitlesModal = false;
        chapterTitlesModalData = [];
        chapterTitlesModalTitle = "";
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
                            disabled={$selectionStats.selected === 0 ||
              loading ||
              availableProviders.filter((p) => p.is_enabled && p.is_configured)
                .length === 0}
                            title={availableProviders.filter(
              (p) => p.is_enabled && p.is_configured,
            ).length > 0
              ? "Enhance selected chapter titles with AI"
              : "No LLM services configured - AI features disabled"}
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

<!-- AI Cleanup Confirmation Modal -->
{#if showAIConfirmation}
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="modal-overlay" onclick={cancelAICleanup}>
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div
                class="ai-modal"
                onclick={(e) => {
        e.stopPropagation();
      }}
        >
            <div class="ai-modal-header">
                <div class="ai-modal-header-content">
                    <div class="ai-modal-icon">
                        <Icon name="ai" size="32" color="var(--ai-accent)"/>
                    </div>
                    <h3>AI Chapter Cleanup</h3>
                </div>

                <div
                        class="features-toggle"
                        onclick={() => (featuresCollapsed = !featuresCollapsed)}
                >
                    <div class="what-is-this">
                        <span class="features-toggle-text">What is this?</span>
                        <span class="chevron" class:expanded={!featuresCollapsed}>
              <ChevronDown size="12"/>
            </span>
                    </div>

                    {#if !featuresCollapsed}
                        <div
                                class="ai-features-content"
                                transition:slide={{ duration: 300 }}
                        >
                            <p class="ai-features-header">
                                This process uses AI to intelligently clean up the selected
                                chapter titles. It will attempt to:
                            </p>

                            <div class="ai-features">
                                <div class="feature-item">
                                    <List size="16" color="var(--ai-accent)"/>
                                    <span>Standardize format/numbering</span>
                                </div>
                                <div class="feature-item">
                                    <Delete size="16" color="var(--ai-accent)"/>
                                    <span>Remove unrelated text</span>
                                </div>
                                <div class="feature-item">
                                    <BookMarked size="16" color="var(--ai-accent)"/>
                                    <span>Identify special sections</span>
                                </div>
                                <div class="feature-item">
                                    <Ban size="16" color="var(--ai-accent)"/>
                                    <span>Deselect non-chapters</span>
                                </div>
                            </div>
                        </div>
                    {/if}
                </div>
            </div>

            <div class="ai-modal-body">
                <div class="ai-options">
                    <h4>Select Provider and Model</h4>

                    {#if availableProviders.filter((p) => p.is_enabled && p.is_configured).length === 0}
                        <div class="no-providers-message">
                            <TriangleAlert size="20" color="#f59e0b"/>
                            <p>
                                No LLM providers are configured. Please set up an AI provider in
                                the settings to use this feature.
                            </p>
                        </div>
                    {:else}
                        <div class="llm-selection-group llm-selection-row">
                            <div class="provider-selection">
                                <select
                                        id="provider-select"
                                        class="provider-select"
                                        bind:value={aiOptions.provider_id}
                                        onchange={(e) => handleProviderChange(e.target.value)}
                                >
                                    {#each availableProviders.filter((p) => p.is_enabled && p.is_configured) as provider}
                                        <option value={provider.id}>{provider.name}</option>
                                    {/each}
                                </select>
                            </div>

                            <div class="model-selection">
                                <select
                                        id="model-select"
                                        class="model-select"
                                        bind:value={aiOptions.model_id}
                                        disabled={loadingModels || availableModels.length === 0}
                                >
                                    {#if loadingModels}
                                        <option>Loading models...</option>
                                    {:else if availableModels.length === 0}
                                        <option>No models available</option>
                                    {:else}
                                        {#each availableModels as model}
                                            <option value={model.id}>{model.name}</option>
                                        {/each}
                                    {/if}
                                </select>
                            </div>
                        </div>
                    {/if}

                    <h4>Cleanup Options</h4>

                    <div class="checkbox-group">
                        <label class="checkbox-label">
                            <input
                                    type="checkbox"
                                    bind:checked={aiOptions.inferOpeningCredits}
                            />
                            <span>Infer opening credits/intro</span>
                            <div
                                    class="help-icon"
                                    data-tooltip="When enabled, the first selected chapter is more likely to be titled as an intro section, e.g. 'Opening Credits', 'Intro', etc."
                            >
                                <CircleQuestionMark size="14"/>
                            </div>
                        </label>

                        <label class="checkbox-label">
                            <input type="checkbox" bind:checked={aiOptions.inferEndCredits}/>
                            <span>Infer end credits/outro</span>
                            <div
                                    class="help-icon"
                                    data-tooltip="When enabled, the last selected chapter is more likely to be titled as an outro section, e.g. 'End Credits', 'Outro', etc."
                            >
                                <CircleQuestionMark size="14"/>
                            </div>
                        </label>

                        <label class="checkbox-label">
                            <input type="checkbox" bind:checked={aiOptions.assumeAllValid}/>
                            <span>Keep All Chapters</span>
                            <div
                                    class="help-icon"
                                    data-tooltip="When enabled, all selected chapters will be kept. This will prevent chapters that appear to be non-chapters from being discarded."
                            >
                                <CircleQuestionMark size="14"/>
                            </div>
                        </label>

                        {#if availableChapterSources.length > 0}
                            <label
                                    class="checkbox-label"
                                    class:disabled={availableChapterSources.length === 0}
                            >
                                <input
                                        type="checkbox"
                                        bind:checked={aiOptions.usePreferredTitles}
                                        disabled={availableChapterSources.length === 0}
                                />
                                <span>Prefer existing titles from:</span>
                                <div
                                        class="help-icon"
                                        data-tooltip="When enabled, chapter titles from the selected source will be used as a reference during cleanup."
                                >
                                    <CircleQuestionMark size="14"/>
                                </div>
                            </label>
                        {/if}
                    </div>

                    {#if availableChapterSources.length > 0}
                        <div class="preferred-titles-options">
                            <div class="preferred-titles-row">
                                <div class="source-select-group">
                                    <select
                                            id="preferred-titles-source"
                                            bind:value={aiOptions.preferredTitlesSource}
                                            class="source-select"
                                            disabled={!aiOptions.usePreferredTitles}
                                    >
                                        {#each availableChapterSources as source}
                                            <option value={source.id}
                                            >{source.name} ({source.count} chapters)
                                            </option
                                            >
                                        {/each}
                                    </select>
                                </div>

                                <button
                                        type="button"
                                        class="view-titles-btn"
                                        onclick={viewChapterTitles}
                                        disabled={!aiOptions.preferredTitlesSource || !aiOptions.usePreferredTitles}
                                        title="View chapter titles from selected source"
                                >
                                    <Eye size="20"/>
                                </button>
                            </div>
                        </div>
                    {/if}

                    <div class="instructions-group">
                        <label for="additional-instructions">
                            Additional instructions:
                            <div
                                    class="help-icon"
                                    data-tooltip="Examples:
                  &quot;Use words for numbers instead of digits&quot;
                  &quot;Return the results in Spanish&quot;
                  &quot;Do not include title text&quot;
                  &quot;Use this format: Chapter [number] - [title]&quot;
                  &quot;Fix any misspellings of 'A-A-Ron'&quot;"
                            >
                                <CircleQuestionMark size="14"/>
                            </div>
                        </label>
                        <textarea
                                id="additional-instructions"
                                bind:value={aiOptions.additionalInstructions}
                                placeholder="Enter any special instructions or clarifications for this audiobook..."
                                rows="3"
                        ></textarea>
                    </div>
                </div>
            </div>

            <div class="ai-modal-actions">
                <button class="btn btn-cancel btn-ai-cancel" onclick={cancelAICleanup}>
                    Cancel
                </button>
                <button
                        class="btn ai-confirm-btn"
                        onclick={confirmAICleanup}
                        disabled={availableProviders.filter(
            (p) => p.is_enabled && p.is_configured,
          ).length === 0}
                >
                    <Icon name="ai" size="16" style="margin-right: 0.5rem;"/>
                    Clean Up {$selectionStats.selected} Chapters
                </button>
            </div>
        </div>
    </div>
{/if}

<!-- Chapter Titles Modal -->
<ChapterModal
        bind:isOpen={showChapterTitlesModal}
        title={chapterTitlesModalTitle}
        chapters={chapterTitlesModalData}
        loading={chapterTitlesModalLoading}
        on:close={closeChapterTitlesModal}
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

    /* AI Confirmation Modal */
    .modal-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.6);
        backdrop-filter: blur(4px);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 10000;
        animation: fadeIn 0.2s ease-out;
    }

    .ai-modal {
        background: var(--bg-card);
        border-radius: 1rem;
        max-width: 500px;
        width: 90%;
        margin: 2rem;
        border: 1px solid var(--border-color);
        animation: slideIn 0.1s ease-out;
        overflow: hidden;
    }

    .ai-modal-header {
        padding: 2rem 1.5rem 1rem 1.5rem;
        background: linear-gradient(
                135deg,
                color-mix(in srgb, var(--ai-gradient-start) 10%, transparent),
                color-mix(in srgb, var(--ai-gradient-end) 10%, transparent)
        );
        border-bottom: 1px solid var(--border-color);
    }

    .ai-modal-header-content {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 1rem;
    }

    .ai-modal-icon {
        flex-shrink: 0;
    }

    .ai-modal-header h3 {
        margin: 0;
        color: var(--text-primary);
        font-size: 1.25rem;
        font-weight: 600;
        padding-right: 48px;
    }

    .ai-modal-body {
        padding: 1.5rem;
    }

    .ai-modal input {
        accent-color: var(--ai-accent);
    }

    .ai-features-header {
        color: var(--text-primary);
        font-weight: 500;
        margin-bottom: 1rem;
        margin-top: 0;
    }

    .ai-features {
        display: flex;
        flex-direction: column;
        gap: 0.75rem;
    }

    .features-toggle {
        cursor: pointer;
        transition: all 0.2s ease;
        width: 100%;
    }

    .what-is-this {
        display: flex;
        justify-content: center;
        align-items: center;
        color: var(--text-muted);
        font-size: 0.75rem;
        font-weight: 500;
    }

    .features-toggle:hover {
        color: var(--text-primary);
    }

    .features-toggle-text {
        color: inherit;
        font-weight: inherit;
        font-size: inherit;
    }

    .features-toggle .chevron {
        transition: transform 0.2s ease;
        display: flex;
        align-items: center;
        margin-left: 0.25rem;
    }

    .features-toggle .chevron.expanded {
        transform: rotate(180deg);
    }

    .ai-features-content {
        margin: 1rem 1rem 0.25rem 1rem;
        text-align: center;
    }

    .feature-item {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        margin: 0 4rem;
        color: var(--text-secondary);
        font-size: 0.875rem;
    }

    .ai-modal-actions {
        padding: 0 1.5rem 1.5rem 1.5rem;
        display: flex;
        gap: 1rem;
        justify-content: flex-end;
    }

    .ai-confirm-btn {
        background: linear-gradient(135deg, var(--ai-gradient-start) 0%, var(--ai-gradient-end) 100%) !important;
        border: none !important;
        color: white !important;
        font-weight: 600;
        display: flex;
        align-items: center;
    }

    .ai-confirm-btn:hover {
        background: linear-gradient(135deg, var(--ai-gradient-start-hover) 0%, var(--ai-gradient-end-hover) 100%) !important;
    }

    @keyframes fadeIn {
        from {
            opacity: 0;
        }
        to {
            opacity: 1;
        }
    }

    @keyframes slideIn {
        from {
            opacity: 0;
            transform: translateY(-20px) scale(0.95);
        }
        to {
            opacity: 1;
            transform: translateY(0) scale(1);
        }
    }

    /* Responsive modal */
    @media (max-width: 768px) {
        .ai-modal {
            width: 95%;
            margin: 1rem;
        }

        .ai-modal-header,
        .ai-modal-body,
        .ai-modal-actions {
            padding: 1.5rem;
        }

        .ai-modal-actions {
            flex-direction: column;
            gap: 0.75rem;
        }

        .ai-modal-actions .btn {
            width: 100%;
        }

        .ai-confirm-btn {
            justify-content: center;
        }
    }

    .ai-options {
        margin-top: 0;
    }

    .ai-options h4 {
        margin: 0 0 0.75rem 0;
        color: var(--text-primary);
        font-size: 0.9rem;
        font-weight: 600;
    }

    .checkbox-group {
        display: flex;
        flex-direction: column;
        gap: 0.75rem;
        margin-bottom: 1rem;
    }

    .checkbox-label {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.875rem;
        color: var(--text-secondary);
        cursor: pointer;
        user-select: none;
    }

    .checkbox-label:hover {
        color: var(--text-primary);
    }

    .instructions-group {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
    }

    .instructions-group label {
        font-size: 0.875rem;
        color: var(--text-secondary);
        font-weight: 500;
    }

    .instructions-group textarea {
        width: 100%;
        min-height: 4rem;
        padding: 0.75rem;
        border: 1px solid var(--border-color);
        border-radius: 0.375rem;
        background: var(--bg-secondary);
        color: var(--text-primary);
        font-family: inherit;
        font-size: 0.875rem;
        resize: vertical;
        transition: border-color 0.2s ease;
    }

    .instructions-group textarea:focus {
        outline: none;
        border-color: var(--ai-accent);
    }

    .instructions-group textarea::placeholder {
        color: var(--text-muted);
    }

    /* Preferred Titles Options Styling */
    .checkbox-label.disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    .checkbox-label.disabled input[type="checkbox"] {
        cursor: not-allowed;
    }

    .preferred-titles-options {
        margin-top: -0.75rem;
        padding: 0 0 0.75rem 1.5rem;
    }

    .preferred-titles-row {
        display: flex;
        align-items: end;
        gap: 0.5rem;
    }

    .source-select-group {
        flex: 1;
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
    }

    .source-select {
        width: 100%;
        padding: 0.5rem 0.75rem;
        border: 1px solid var(--border-color);
        border-radius: 0.375rem;
        background: var(--bg-primary);
        color: var(--text-primary);
        font-size: 0.875rem;
        transition: border-color 0.2s ease;
    }

    .source-select:focus {
        outline: none;
        border-color: var(--ai-accent);
    }

    .source-select:disabled {
        opacity: 0.4;
        cursor: not-allowed;
    }

    .view-titles-btn {
        width: 36px;
        height: 36px;
        border: 1px solid var(--border-color);
        border-radius: 0.375rem;
        background: var(--bg-primary);
        color: var(--text-secondary);
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .view-titles-btn:hover:not(:disabled) {
        background: var(--ai-accent);
        color: white;
        border-color: var(--ai-accent);
        transform: translateY(-1px);
    }

    .view-titles-btn:disabled {
        opacity: 0.4;
        cursor: not-allowed;
    }

    /* Responsive design for preferred titles */
    @media (max-width: 768px) {
        .preferred-titles-row {
            flex-direction: column;
            align-items: stretch;
            gap: 1rem;
        }

        .view-titles-btn {
            align-self: center;
            width: auto;
            padding: 0.5rem 1rem;
        }
    }

    /* LLM Selection Styling */
    .llm-selection-group {
        display: flex;
        flex-direction: column;
        gap: 1rem;
        margin-bottom: 1.5rem;
    }

    .llm-selection-row {
        flex-direction: row;
        gap: 0.5rem;
    }

    .provider-selection,
    .model-selection {
        display: flex;
        flex-direction: column;
    }

    .llm-selection-row .provider-selection {
        flex-basis: 25%;
    }

    .llm-selection-row .model-selection {
        flex-basis: 75%;
    }

    .provider-select,
    .model-select {
        width: 100%;
        padding: 0.5rem 0.75rem;
        border: 1px solid var(--border-color);
        border-radius: 0.375rem;
        background: var(--bg-primary);
        color: var(--text-primary);
        font-size: 0.875rem;
        transition: border-color 0.2s ease;
    }

    .provider-select:focus,
    .model-select:focus {
        outline: none;
        border-color: var(--ai-accent);
    }

    .model-select:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }

    .help-icon {
        border: none;
        display: inline-flex;
        background: transparent;
        color: var(--text-secondary);
        position: relative;
        cursor: help;
        padding: 2px;
        border-radius: 50%;
        transition: all 0.2s ease;
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
        white-space: pre-line;
        min-width: 320px;
        max-width: 480px;
        z-index: 1000;
        animation: tooltipFadeIn 0.2s ease-out;
    }

    /* Tooltip arrow */
    .help-icon[data-tooltip]:hover::before {
        content: "";
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

    .no-providers-message {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 1rem;
        background: rgba(245, 158, 11, 0.1);
        border: 1px solid rgba(245, 158, 11, 0.3);
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }

    .no-providers-message p {
        margin: 0;
        color: var(--text-secondary);
        font-size: 0.875rem;
        line-height: 1.4;
    }

    @media (max-width: 768px) {
        .ai-modal-header-content {
            flex-direction: column;
            gap: 0.5rem;
        }

        .llm-selection-group {
            padding: 0.75rem;
        }

        .llm-selection-row {
            flex-direction: column;
        }

        .llm-selection-row .provider-selection,
        .llm-selection-row .model-selection {
            flex: 1;
        }

        .no-providers-message {
            flex-direction: column;
            text-align: center;
            gap: 0.5rem;
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

    .btn-ai-cancel {
        padding: 0.375rem 0.75rem;
        font-size: 0.875rem;
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
