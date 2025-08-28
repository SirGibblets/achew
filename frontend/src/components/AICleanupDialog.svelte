<script>
    import {slide} from "svelte/transition";
    import {selectionStats} from "../stores/session.js";
    import {api} from "../utils/api.js";
    import ChapterModal from "./ChapterModal.svelte";
    import Icon from "./Icon.svelte";

    // Icons
    import Ban from "@lucide/svelte/icons/ban";
    import BookMarked from "@lucide/svelte/icons/book-marked";
    import ChevronDown from "@lucide/svelte/icons/chevron-down";
    import CircleQuestionMark from "@lucide/svelte/icons/circle-question-mark";
    import Delete from "@lucide/svelte/icons/delete";
    import Eye from "@lucide/svelte/icons/eye";
    import List from "@lucide/svelte/icons/list";
    import TriangleAlert from "@lucide/svelte/icons/triangle-alert";

    // Props
    let {
        isOpen = $bindable(false),
        sessionStep = "",
        cueSources = []
    } = $props();

    // Events
    import {createEventDispatcher} from "svelte";
    const dispatch = createEventDispatcher();

    // AI Cleanup options
    let aiOptions = $state({
        inferOpeningCredits: true,
        inferEndCredits: true,
        deselectNonChapters: true,
        keepDeselectedTitles: false,
        usePreferredTitles: false,
        preferredTitlesSource: "",
        additionalInstructions: "",
        provider_id: "",
        model_id: "",
    });

    // Features section collapsed state
    let featuresCollapsed = $state(true);

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

    // Load AI options when component mounts or when dialog opens
    $effect(() => {
        if (isOpen && sessionStep === "chapter_editing") {
            loadAIOptions();
        }
    });

    // Prevent background scrolling when modal is open
    $effect(() => {
        if (isOpen) {
            // Store original overflow value
            const originalOverflow = document.body.style.overflow;
            const originalPosition = document.body.style.position;
            const originalTop = document.body.style.top;
            const scrollY = window.scrollY;
            
            // Prevent background scrolling
            document.body.style.overflow = 'hidden';
            document.body.style.position = 'fixed';
            document.body.style.top = `-${scrollY}px`;
            document.body.style.width = '100%';
            
            // Cleanup function
            return () => {
                document.body.style.overflow = originalOverflow;
                document.body.style.position = originalPosition;
                document.body.style.top = originalTop;
                document.body.style.width = '';
                window.scrollTo(0, scrollY);
            };
        }
    });

    async function loadAIOptions() {
        if (sessionStep !== "chapter_editing") return;

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
        if (sessionStep !== "chapter_editing") return;

        try {
            await api.batch.updateAIOptions(aiOptions);
        } catch (err) {
            console.warn("Failed to save AI options:", err);
        }
    }

    async function loadAvailableChapterSources() {
        if (sessionStep !== "chapter_editing") return;

        availableChapterSources = [];

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

    async function confirmAICleanup() {
        try {
            // Save AI options before processing
            await saveAIOptions();
            
            // Dispatch confirm event with options
            dispatch('confirm', aiOptions);
            
            // Close dialog
            isOpen = false;
        } catch (err) {
            // Dispatch error event
            dispatch('error', err);
        }
    }

    function cancelAICleanup() {
        dispatch('cancel');
        isOpen = false;
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
</script>

<!-- AI Cleanup Confirmation Modal -->
{#if isOpen}
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
                            <input type="checkbox" bind:checked={aiOptions.deselectNonChapters}/>
                            <span>Deselect Non-Chapters</span>
                            <div
                                    class="help-icon"
                                    data-tooltip="When enabled, items that do not appear to be the start of a chapter or section will be automatically deselected during cleanup."
                            >
                                <CircleQuestionMark size="14"/>
                            </div>
                        </label>

                        {#if aiOptions.deselectNonChapters}
                            <label class="checkbox-label nested-checkbox">
                                <input type="checkbox" bind:checked={aiOptions.keepDeselectedTitles}/>
                                <span>Keep Titles</span>
                                <div
                                        class="help-icon"
                                        data-tooltip="When enabled, the titles of deselected chapters will be preserved instead of being cleared."
                                >
                                    <CircleQuestionMark size="12"/>
                                </div>
                            </label>
                        {/if}

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
        z-index: 1000;
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
        overflow-y: auto;
        max-height: 90vh;
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

    .checkbox-label.nested-checkbox {
        margin-left: 1.5rem;
        font-size: 0.8rem;
        color: var(--text-muted);
    }

    .checkbox-label.nested-checkbox:hover {
        color: var(--text-secondary);
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
        position: fixed;
        transform: translate(-50%, calc(-100% - 8px));
        padding: 8px 12px;
        background: var(--bg-primary);
        color: var(--text-primary);
        border: 1px solid var(--border-color);
        border-radius: 6px;
        font-size: 0.875rem;
        line-height: 1.4;
        white-space: pre-line;
        max-width: 360px;
        z-index: 10001;
    }

    /* Tooltip arrow */
    .help-icon[data-tooltip]:hover::before {
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

    .btn-ai-cancel {
        padding: 0.375rem 0.75rem;
        font-size: 0.875rem;
    }
</style>