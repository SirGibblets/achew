<script>
    import {onMount} from "svelte";
    import {session} from "../stores/session.js";
    import {api} from "../utils/api.js";
    import AudiobookCard from "./AudiobookCard.svelte";
    import ChapterModal from "./ChapterModal.svelte";
    import AddSourceDialog from "./AddSourceDialog.svelte";
    import SourceFooter from "./SourceFooter.svelte";

    // Icons
    import CircleQuestionMark from "@lucide/svelte/icons/circle-question-mark";
    import ExternalLink from "@lucide/svelte/icons/external-link";
    import TriangleAlert from "@lucide/svelte/icons/triangle-alert";

    let loading = false;
    let selectedExistingSource = "";
    let selectedRealignSource = "";
    let selectedQuickEditSource = "";
    let activeTab = "smart_detect";
    let isDramatized = false;
    let cueSources = {};
    let existingCueSources = [];
    let error = null;

    let showAddSource = false;

    $: titleSources = $session.titleSources || [];

    function handleSourceAdded(newSource) {
        // Auto-select the new source in the active tab if it's a cue source
        if ('cues' in newSource) {
            if (activeTab === 'realign') selectedRealignSource = newSource.id;
            else if (activeTab === 'regenerate_titles') selectedExistingSource = newSource.id;
            else if (activeTab === 'quick_edit') selectedQuickEditSource = newSource.id;
        }
    }

    // Chapter details modal state
    let chapterModalOpen = false;
    let chapterModalTitle = "";
    let chapterModalData = [];
    let chapterModalLoading = false;

    // Get cue sources from session data
    $: if ($session.cueSources) {
        cueSources = $session.cueSources;
        error = null;
    }

    // Get existing cue sources from session store
    $: if ($session.cueSources) {
        existingCueSources = $session.cueSources;
        if (!selectedQuickEditSource) {
            const absSource = existingCueSources.find(s => s.type === 'abs');
            if (absSource) selectedQuickEditSource = absSource.id;
        }
    }

    // Format time for display
    function formatTime(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);

        if (hours > 0) {
            return `${hours}:${minutes.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
        }
        return `${minutes}:${secs.toString().padStart(2, "0")}`;
    }

    // Format duration for display
    function formatDuration(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);

        if (hours > 0) {
            return `${hours}h ${minutes}m ${secs}s`;
        }
        return `${minutes}m ${secs}s`;
    }

    // Get warning data for a specific option
    function getWarnings(optionType) {
        if (!cueSources.warnings || !cueSources.warnings[optionType]) {
            return [];
        }
        return cueSources.warnings[optionType];
    }

    async function proceedWithSelection() {
        loading = true;
        try {
            if (activeTab === "smart_detect") {
                const option = isDramatized ? "smart_detect_vad" : "smart_detect";
                await api.session.selectWorkflow(option);
            } else if (activeTab === "realign") {
                if (!selectedRealignSource) {
                    alert("Please select a chapter source.");
                    loading = false;
                    return;
                }
                await api.session.realignChapter(selectedRealignSource, isDramatized);
            } else if (activeTab === "regenerate_titles") {
                if (!selectedExistingSource) {
                    alert("Please select a chapter source.");
                    loading = false;
                    return;
                }
                await api.session.selectWorkflow(selectedExistingSource);
            } else if (activeTab === "quick_edit") {
                if (!selectedQuickEditSource) {
                    alert("Please select a chapter source.");
                    loading = false;
                    return;
                }
                await api.session.selectWorkflow("quick_edit:" + selectedQuickEditSource);
            }
        } catch (error) {
            console.error("Error selecting workflow:", error);
            session.setError("Failed to select workflow: " + error.message);
        } finally {
            loading = false;
        }
    }

    // Fetch detailed chapter data for modal display
    async function fetchChapterData(sourceId) {
        if ($session.step !== "select_workflow") return [];

        chapterModalLoading = true;
        try {
            // Find the source in existingCueSources
            const source = existingCueSources.find((s) => s.id === sourceId);
            if (source && source.cues) {
                return source.cues.map((cue, index) => ({
                    timestamp: cue.timestamp,
                    title: cue.title || `Chapter ${index + 1}`,
                }));
            }

            return [];
        } catch (error) {
            console.error("Failed to fetch chapter data:", error);
            return [];
        } finally {
            chapterModalLoading = false;
        }
    }

    // Handle chapter count bubble click
    async function handleChapterCountClick(sourceId) {
        const source = existingCueSources.find((s) => s.id === sourceId);

        chapterModalTitle = source ? source.name : "Chapter Data";
        chapterModalData = [];
        chapterModalOpen = true;

        chapterModalData = await fetchChapterData(sourceId);
    }

    // Close chapter modal
    function closeChapterModal() {
        chapterModalOpen = false;
        chapterModalData = [];
        chapterModalTitle = "";
    }



    // Get the option display info
    function getOptionInfo(option) {
        // Handle dynamic existing cue sources
        const existingSource = existingCueSources.find(
            (source) => source.id === option,
        );
        if (existingSource) {
            return {
                title: existingSource.name,
                description: existingSource.description,
            };
        }

        return {
            title: option,
            description: "Unknown option",
        };
    }

    onMount(async () => {
    });
</script>

<div class="chapter-options">
    {#if error}
        <div class="alert alert-danger">
            {error}
            <button
                    type="button"
                    class="btn btn-sm btn-outline float-right"
                    on:click={() => (error = null)}
            >
                Dismiss
            </button>
        </div>
    {/if}

    {#if cueSources.book_duration}
        <div class="audiobook-card-container">
            <AudiobookCard
                    title={cueSources.book_title || "Audiobook"}
                    duration={cueSources.book_duration}
                    coverImageUrl={cueSources.cover_url}
                    fileCount={cueSources.file_count || 1}
            />
        </div>
    {/if}

    <div class="header">
        <h2>Select a Workflow</h2>
    </div>

    {#if loading}
        <div class="text-center p-4">
            <div class="spinner"></div>
            <p class="mt-2">Loading cue sources…</p>
        </div>
    {:else}
        <div class="mode-selector">
            <button
                    class="mode-btn {activeTab === 'smart_detect' ? 'active' : ''}"
                    on:click={() => activeTab = 'smart_detect'}
                    type="button"
            >
                Smart Detect
            </button>
            <button
                    class="mode-btn {activeTab === 'realign' ? 'active' : ''}"
                    on:click={() => activeTab = 'realign'}
                    type="button"
            >
                Realign Chapters
            </button>
            <button
                    class="mode-btn {activeTab === 'regenerate_titles' ? 'active' : ''}"
                    on:click={() => activeTab = 'regenerate_titles'}
                    type="button"
            >
                Regenerate Titles
            </button>
            <button
                    class="mode-btn {activeTab === 'quick_edit' ? 'active' : ''}"
                    on:click={() => activeTab = 'quick_edit'}
                    type="button"
            >
                Quick Edit
            </button>
        </div>

        <div class="options-grid">
            {#if activeTab === 'smart_detect'}
                <p class="tab-description">
                    The <b>Smart Detect</b> workflow uses audio analysis to locate potential chapter cues within the audiobook. In the following step you will choose which cues will become your initial chapters.
                    {#if existingCueSources.length > 0}
                        {@const availableSourceNames = existingCueSources.map(source => source.name)}
                        {@const sourcesList = availableSourceNames.length === 1 ? availableSourceNames[0] : availableSourceNames.length === 2 ? availableSourceNames.join(" and ") : availableSourceNames.slice(0, -1).join(", ") + ", and " + availableSourceNames[availableSourceNames.length - 1]}
                         You will also be able to compare to the {sourcesList}.
                    {/if}
                </p>


                <div class="dramatized-toggle">
                    <label>
                        <input
                                type="checkbox"
                                bind:checked={isDramatized}
                                disabled={loading}
                        />
                        <span>Dramatized</span>
                    </label>
                    <div
                            class="help-icon"
                            data-tooltip="Select this if your audiobook contains non-speech elements like music and sound effects. Detection will be slower but more accurate."
                    >
                        <CircleQuestionMark size="14"/>
                    </div>
                </div>

                <div class="actions">
                    <button
                            class="btn btn-verify"
                            on:click={proceedWithSelection}
                            disabled={loading}
                    >
                        {#if loading}
                            <span class="btn-spinner"></span>
                            Processing…
                        {:else}
                            Start Smart Detect
                        {/if}
                    </button>
                </div>

            {:else if activeTab === 'realign'}
                <p class="tab-description">
                    The <b>Realign Chapters</b> workflow attempts to realign the timestamps of an existing chapter source to better match the book's audio, preserving the chapter titles. This is useful for cases where a source has correct titles, but the timestamps are off by a few seconds.
                </p>

                {#if existingCueSources.length > 0}
                    {#each existingCueSources as source}
                        <div class="option-card" class:selected={selectedRealignSource === source.id}>
                            <label>
                                <div class="option-layout">
                                    <input
                                            type="radio"
                                            bind:group={selectedRealignSource}
                                            value={source.id}
                                            disabled={loading}
                                    />
                                    <div class="option-content">
                                        <div class="option-header">
                                            <b>{getOptionInfo(source.id).title}</b>
                                            <div class="chapter-count-container">
                                                <button
                                                        class="chapter-count clickable"
                                                        on:click={() => handleChapterCountClick(source.id)}
                                                        title="Click to view chapter details"
                                                >
                                                    {source.cues.length} chapters
                                                    <ExternalLink size="12"/>
                                                </button>
                                            </div>
                                        </div>
                                        <p class="description">
                                            {getOptionInfo(source.id).description}
                                        </p>
                                    </div>
                                </div>
                            </label>
                        </div>
                    {/each}

                    <SourceFooter {titleSources} onAddSource={() => showAddSource = true}/>

                    <div class="dramatized-toggle">
                        <label>
                            <input
                                    type="checkbox"
                                    bind:checked={isDramatized}
                                    disabled={loading}
                            />
                            <span>Dramatized</span>
                        </label>
                        <div
                                class="help-icon"
                                data-tooltip="Select this if your audiobook contains non-speech elements like music and sound effects. Detection will be slower but more accurate."
                        >
                            <CircleQuestionMark size="14"/>
                        </div>
                    </div>

                    <div class="actions">
                        <button
                                class="btn btn-verify"
                                on:click={proceedWithSelection}
                                disabled={loading || !selectedRealignSource}
                        >
                            {#if loading}
                                <span class="btn-spinner"></span>
                                Processing…
                            {:else}
                                {#if selectedRealignSource}
                                    Realign {getOptionInfo(selectedRealignSource).title}
                                {:else}
                                    Select a Chapter Source
                                {/if}
                            {/if}
                        </button>
                    </div>
                {:else}
                    <div class="no-sources-card">
                        <TriangleAlert size="16" />
                        <p>No existing chapters to realign</p>
                    </div>
                {/if}

            {:else if activeTab === 'regenerate_titles'}
                <p class="tab-description">
                    The <b>Regenerate Titles</b> workflow transcribes new titles at the timestamps of an existing chapter source. This is useful for cases where a source has correct timestamps, but the titles are missing or incorrect.
                </p>

                {#if existingCueSources.length > 0}
                    {#each existingCueSources as source}
                        <div class="option-card" class:selected={selectedExistingSource === source.id}>
                            <label>
                                <div class="option-layout">
                                    <input
                                            type="radio"
                                            bind:group={selectedExistingSource}
                                            value={source.id}
                                            disabled={loading}
                                    />
                                    <div class="option-content">
                                        <div class="option-header">
                                            <b>{getOptionInfo(source.id).title}</b>
                                            <div class="chapter-count-container">
                                                <button
                                                        class="chapter-count clickable"
                                                        on:click={() => handleChapterCountClick(source.id)}
                                                        title="Click to view chapter details"
                                                >
                                                    {source.cues.length} chapters
                                                    <ExternalLink size="12"/>
                                                </button>
                                                {#each getWarnings(source.id) as warning}
                                                    <div class="warning-icon-container" title="">
                                                        <TriangleAlert size="16" color="var(--warning)"/>
                                                        <div class="warning-tooltip">
                                                            <TriangleAlert
                                                                    name="warning"
                                                                    color="var(--warning)"
                                                                    size="14"
                                                            />
                                                            <div class="warning-content">
                                                                <span class="warning-title">{warning.title}:</span>
                                                                <span class="warning-text"
                                                                >{warning.description}</span
                                                                >
                                                            </div>
                                                        </div>
                                                    </div>
                                                {/each}
                                            </div>
                                        </div>
                                        <p class="description">
                                            {getOptionInfo(source.id).description}
                                        </p>
                                    </div>
                                </div>
                            </label>
                        </div>
                    {/each}

                    <SourceFooter {titleSources} onAddSource={() => showAddSource = true}/>

                    <div class="actions" style="margin-top: 1.5rem;">
                        <button
                                class="btn btn-verify"
                                on:click={proceedWithSelection}
                                disabled={loading || !selectedExistingSource}
                        >
                            {#if loading}
                                <span class="btn-spinner"></span>
                                Processing…
                            {:else if selectedExistingSource}
                                Continue with {getOptionInfo(selectedExistingSource).title}
                            {:else}
                                Select a Chapter Source
                            {/if}
                        </button>
                    </div>
                {:else}
                    <div class="no-sources-card">
                        <TriangleAlert size="16" />
                        <p>No existing chapters to regenerate</p>
                    </div>
                {/if}

            {:else if activeTab === 'quick_edit'}
                <p class="tab-description">
                    The <b>Quick Edit</b> workflow skips audio analysis and loads chapters from an existing source directly into the editor. Use this when you only need to make quick changes, like using AI Cleanup or adding a missing chapter.
                </p>

                {#if existingCueSources.length > 0}
                    {#each existingCueSources as source}
                        <div class="option-card" class:selected={selectedQuickEditSource === source.id}>
                            <label>
                                <div class="option-layout">
                                    <input
                                            type="radio"
                                            bind:group={selectedQuickEditSource}
                                            value={source.id}
                                            disabled={loading}
                                    />
                                    <div class="option-content">
                                        <div class="option-header">
                                            <b>{getOptionInfo(source.id).title}</b>
                                            <div class="chapter-count-container">
                                                <button
                                                        class="chapter-count clickable"
                                                        on:click={() => handleChapterCountClick(source.id)}
                                                        title="Click to view chapter details"
                                                >
                                                    {source.cues.length} chapters
                                                    <ExternalLink size="12"/>
                                                </button>
                                            </div>
                                        </div>
                                        <p class="description">
                                            {getOptionInfo(source.id).description}
                                        </p>
                                    </div>
                                </div>
                            </label>
                        </div>
                    {/each}

                    <SourceFooter {titleSources} onAddSource={() => showAddSource = true}/>

                    <div class="actions" style="margin-top: 1.5rem;">
                        <button
                                class="btn btn-verify"
                                on:click={proceedWithSelection}
                                disabled={loading || !selectedQuickEditSource}
                        >
                            {#if loading}
                                <span class="btn-spinner"></span>
                                Loading…
                            {:else if selectedQuickEditSource}
                                Open in Editor
                            {:else}
                                Select a Chapter Source
                            {/if}
                        </button>
                    </div>
                {:else}
                    <div class="no-sources-card">
                        <TriangleAlert size="16" />
                        <p>No existing chapters to edit</p>
                    </div>
                {/if}
            {/if}
        </div>
    {/if}
</div>

<!-- Chapter Data Modal -->
<ChapterModal
        bind:isOpen={chapterModalOpen}
        title={chapterModalTitle}
        chapters={chapterModalData}
        loading={chapterModalLoading}
        on:close={closeChapterModal}
/>

<AddSourceDialog
    bind:isOpen={showAddSource}
    expectCues={true}
    onSourceAdded={handleSourceAdded}
/>

<style>
    .chapter-options {
        max-width: 900px;
        width: 100%;
        margin: 0 auto;
    }

    .header {
        text-align: center;
        margin-bottom: 2rem;
    }

    .header h2 {
        margin-bottom: 0.75rem;
        font-size: 2rem;
        font-weight: 600;
    }

    .options-grid {
        display: grid;
        gap: 1rem;
    }

    .option-card {
        border: 2px solid var(--border-color);
        border-radius: 12px;
        padding: 0;
        background: var(--bg-secondary);
        transition: all 0.1s ease;
        cursor: pointer;
    }

    .option-card:hover {
        border-color: var(--primary-hover);
    }

    .option-card.selected {
        border-color: var(--primary-color);
    }

    .option-card label {
        display: block;
        padding: 0.75rem;
        cursor: pointer;
        margin: 0;
    }

    .option-card input[type="radio"] {
        width: 20px;
        height: 20px;
        flex-shrink: 0;
        accent-color: var(--primary-contrast);
        margin: 0 0.5rem;
        cursor: pointer;
    }

    .option-layout {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        width: 100%;
    }

    .option-content {
        flex: 1;
        min-width: 0;
    }

    .option-header {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        margin-bottom: 0.25rem;
        position: relative;
        flex-wrap: wrap;
    }

    .description {
        color: var(--text-secondary);
        margin-bottom: 0;
        line-height: 1.5;
    }

    .audiobook-card-container {
        display: none;
        margin: 0 auto 3rem auto;
        max-width: 600px;
    }

    .chapter-count {
        background: var(--bg-tertiary);
        padding: 0.25rem 0.75rem;
        border-radius: 60px;
        font-size: 0.75rem;
        color: var(--text-primary);
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        border: none;
        cursor: default;
    }

    .chapter-count.clickable {
        cursor: pointer;
        transition: all 0.2s ease;
        border: 1px solid transparent;
    }

    .chapter-count.clickable:hover {
        background: var(--primary-color);
        color: white;
        transform: translateY(-1px);
    }

    .chapter-count.clickable:active {
        transform: translateY(0);
    }

    .chapter-count-container {
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    .warning-icon-container {
        position: relative;
        display: flex;
        align-items: center;
        cursor: help;
    }

    .warning-tooltip {
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
        white-space: normal;
        min-width: 420px;
        max-width: 640px;
        z-index: 1000;
        opacity: 0;
        visibility: hidden;
        transition: all 0.2s ease;
        pointer-events: none;
        display: flex;
        align-items: flex-start;
        gap: 0.35rem;
    }

    .warning-tooltip::before {
        content: "";
        position: absolute;
        top: 100%;
        left: 50%;
        transform: translateX(-50%);
        border: 6px solid transparent;
        border-top-color: var(--border-color);
        z-index: 1001;
    }

    .warning-tooltip::after {
        content: "";
        position: absolute;
        top: 100%;
        left: 50%;
        transform: translateX(-50%);
        margin-top: -1px;
        border: 5px solid transparent;
        border-top-color: var(--bg-primary);
        z-index: 1002;
    }

    .warning-icon-container:hover .warning-tooltip {
        opacity: 1;
        visibility: visible;
        transform: translateX(-50%) translateY(-4px);
    }

    .warning-tooltip :global(.icon) {
        margin-top: 2px;
        flex-shrink: 0;
    }

    .warning-content {
        line-height: 1;
    }

    .warning-title {
        font-size: 0.8rem;
    }

    .warning-text {
        font-size: 0.8rem;
        color: var(--text-secondary);
        line-height: 1.4;
    }

    .actions {
        display: flex;
        justify-content: center;
        margin-top: 0rem;
    }

    .spinner {
        width: 16px;
        height: 16px;
        border: 2px solid transparent;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        display: inline-block;
        margin-right: 0.5rem;
    }

    @keyframes spin {
        0% {
            transform: rotate(0deg);
        }
        100% {
            transform: rotate(360deg);
        }
    }

    .text-center {
        text-align: center;
    }

    .p-4 {
        padding: 2rem;
    }

    .mt-2 {
        margin-top: 0.5rem;
    }

    .float-right {
        float: right;
        margin-left: 1rem;
    }

    .help-icon {
        border: none;
        display: inline-flex;
        background: transparent;
        color: var(--text-secondary);
        cursor: pointer;
        padding: 2px;
        border-radius: 50%;
        transition: all 0.2s ease;
    }

    .help-icon {
        position: relative;
        cursor: help;
    }

    .help-icon:hover {
        color: var(--primary-color);
        background: var(--bg-tertiary);
    }

    /* Tooltip on hover */
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
        white-space: normal;
        min-width: 280px;
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

    @media (max-width: 768px) {
        .chapter-options {
            padding: 1rem;
        }

        .audiobook-card-container {
            margin: 1.5rem auto;
        }

        .option-card label {
            padding: 1rem;
        }

        .option-header {
            flex-wrap: wrap;
        }

        .chapter-count-container {
            flex-wrap: wrap;
            gap: 0.25rem;
        }

        .warning-tooltip {
            min-width: 250px;
            max-width: 90vw;
            left: 0;
            transform: translateX(0);
        }

        .warning-tooltip::before,
        .warning-tooltip::after {
            left: 20px;
            transform: translateX(0);
        }

        .warning-icon-container:hover .warning-tooltip {
            transform: translateX(0) translateY(-4px);
        }

        .warning-title {
            font-size: 0.8rem;
        }

        .warning-text {
            font-size: 0.75rem;
        }
    }

    .mode-selector {
        display: flex;
        border: 1px solid var(--border-color);
        border-radius: 8px;
        width: fit-content;
        min-width: 620px;
        margin-left: auto;
        margin-right: auto;
        overflow: hidden;
        margin-bottom: 2rem;
    }

    .mode-btn {
        flex: 1;
        padding: 0.5rem 1rem;
        border: none;
        background: transparent;
        color: var(--text-muted);
        font-weight: 500;
        font-size: 0.875rem;
        border-radius: 0;
        cursor: pointer;
        position: relative;
        border-right: 1px solid var(--border-color);
        white-space: nowrap;
    }

    .mode-btn:first-child {
        border-top-left-radius: 7px;
        border-bottom-left-radius: 7px;
    }

    .mode-btn:last-child {
        border-top-right-radius: 7px;
        border-bottom-right-radius: 7px;
        border-right: none;
    }

    .mode-btn:hover:not(.active) {
        color: var(--text-primary);
        background: var(--hover-bg);
    }

    .mode-btn.active {
        background: linear-gradient(
                135deg,
                var(--accent-gradient-start) 0%,
                var(--accent-gradient-end) 100%
        );
        color: white;
        font-weight: 600;
    }

    .tab-description {
        color: var(--text-secondary);
        font-size: 1rem;
        line-height: 1.5;
        margin-bottom: 1rem;
        text-align: center;
        max-width: 700px;
        margin-left: auto;
        margin-right: auto;
    }

    .tab-description b {
        color: var(--text-primary);
    }

    .dramatized-toggle {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.5rem;
        margin-top: 1.5rem;
    }

    .dramatized-toggle label {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        cursor: pointer;
        font-weight: 500;
        color: var(--text-primary);
        margin: 0;
    }

    .dramatized-toggle input[type="checkbox"] {
        width: 16px;
        height: 16px;
        accent-color: var(--primary-color);
        cursor: pointer;
    }

    .no-sources-card {
        display: flex;
        flex-direction: row;
        align-items: center;
        justify-content: center;
        gap: 0.75rem;
        padding: 1rem 1.5rem;
        background: rgba(245, 158, 11, 0.1);
        border: 0.5px solid var(--warning);
        border-radius: 8px;
        color: var(--warning);
        text-align: left;
        margin: 1rem auto;
        width: fit-content;
        max-width: 100%;
    }

    .no-sources-card p {
        margin: 0;
        font-weight: 400;
        font-size: 0.95rem;
        color: var(--warning);
    }
</style>
