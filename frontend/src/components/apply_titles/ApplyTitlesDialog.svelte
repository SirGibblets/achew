<script>
    import {session, chapters} from "../../stores/session.js";
    import {api, handleApiError} from "../../utils/api.js";
    import {audio} from "../../stores/audio.js";
    import AlignmentTab from "./AlignmentTab.svelte";
    import SelectionTab from "./SelectionTab.svelte";

    import X from "@lucide/svelte/icons/x";
    import Eye from "@lucide/svelte/icons/eye";
    import Pencil from "@lucide/svelte/icons/pencil";
    import Plus from "@lucide/svelte/icons/plus";
    import ChapterModal from "../ChapterModal.svelte";
    import AddSourceDialog from "../AddSourceDialog.svelte";
    import CustomTitlesDialog from "../CustomTitlesDialog.svelte";

    let {
        isOpen = $bindable(false),
    } = $props();

    let activeTab = $state('alignment');
    let selectedSourceId = $state(null);
    let loading = $state(false);
    let error = $state(null);

    let alignmentMappings = $state([]);
    let selectionMappings = $state([]);

    let showChapterTitlesModal = $state(false);
    let chapterTitlesModalTitle = $state("");
    let chapterTitlesModalData = $state([]);
    let chapterTitlesModalLoading = false;

    let cueSources = $derived($session.cueSources || []);
    let titleSources = $derived($session.titleSources || []);

    /** All sources available for title mapping, cue first then title. */
    let allSources = $derived([
        ...cueSources.map(s => ({...s, _isCue: true})),
        ...titleSources.map(s => ({
            ...s,
            _isCue: false,
            // Normalise to cues shape so tabs work positionally
            cues: (s.titles || []).map(t => ({timestamp: null, title: t})),
        })),
    ]);

    let selectedSource = $derived(allSources.find(s => s.id === selectedSourceId) ?? null);
    let selectedSourceIsCustom = $derived(selectedSource?.type === 'custom');
    let selectedSourceIsCue = $derived(selectedSource?._isCue ?? true);

    // Custom title source id for the edit dialog
    let customTitlesSourceId = $derived(titleSources.find(s => s.type === 'custom')?.id ?? '');

    // Add / edit dialog state
    let showAddSource = $state(false);
    let showCustomTitles = $state(false);

    let currentMappings = $derived(
        selectedSourceIsCue && activeTab === 'alignment' ? alignmentMappings : selectionMappings
    );

    let canApply = $derived.by(() => {
        if (currentMappings.length === 0) return false;
        return currentMappings.some(m => {
            const ch = $chapters.find(c => c.id === m.chapter_id);
            return ch && ch.current_title !== m.new_title;
        });
    });

    $effect(() => {
        if (isOpen && allSources.length > 0 && !selectedSourceId) {
            selectedSourceId = allSources[0].id;
        }
        if (!isOpen) {
            audio.stop();
            selectedSourceId = null;
            activeTab = 'alignment';
            alignmentMappings = [];
            selectionMappings = [];
            error = null;
        }
    });

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

    async function handleApply() {
        if (!canApply) return;

        /* Filter to only mappings that actually change a title */
        const effectiveMappings = currentMappings.filter(m => {
            const ch = $chapters.find(c => c.id === m.chapter_id);
            return ch && ch.current_title !== m.new_title;
        });

        if (effectiveMappings.length === 0) return;

        loading = true;
        error = null;
        try {
            await api.chapters.applyTitles(effectiveMappings);
            isOpen = false;
        } catch (err) {
            error = handleApiError(err);
        } finally {
            loading = false;
        }
    }

    function switchTab(tab) {
        audio.stop();
        activeTab = tab;
    }

    function handleCancel() {
        isOpen = false;
    }

    function handleBackdropClick(event) {
        if (event.target === event.currentTarget) {
            handleCancel();
        }
    }

    function viewChapterTitles() {
        if (!selectedSource) return;

        chapterTitlesModalTitle = selectedSource.name;
        chapterTitlesModalData = selectedSource.cues.map((cue, index) => ({
            timestamp: cue.timestamp,
            title: cue.title || `Chapter ${index + 1}`,
        }));
        showChapterTitlesModal = true;
    }

    function closeChapterTitlesModal() {
        showChapterTitlesModal = false;
        chapterTitlesModalData = [];
        chapterTitlesModalTitle = "";
    }

    function handleBackdropKeydown(event) {
        if (event.key === 'Escape') {
            handleCancel();
        }
    }
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
                    <h3>Apply Titles</h3>
                    <button class="close-button" onclick={handleCancel} aria-label="Close">
                        <X size="20"/>
                    </button>
                </div>

                <div class="modal-body">
                    {#if error}
                        <div class="alert alert-danger">{error}</div>
                    {/if}

                    <div class="source-row">
                        <span class="source-label">Apply titles from:</span>
                        <div class="source-select-group">
                            <select class="source-select" bind:value={selectedSourceId}>
                                {#each allSources as src (src.id)}
                                    <option value={src.id}>
                                        {src.name} ({src._isCue ? src.cues.length + ' chapters' : (src.titles?.length ?? 0) + ' titles'})
                                    </option>
                                {/each}
                            </select>
                        </div>
                        <button
                                type="button"
                                class="view-titles-btn"
                                onclick={() => selectedSourceIsCustom ? (showCustomTitles = true) : viewChapterTitles()}
                                disabled={!selectedSourceId}
                                title={selectedSourceIsCustom ? "Edit custom titles" : "View chapter titles from selected source"}
                        >
                            {#if selectedSourceIsCustom}
                                <Pencil size="20"/>
                            {:else}
                                <Eye size="20"/>
                            {/if}
                        </button>
                        <button
                                type="button"
                                class="view-titles-btn"
                                onclick={() => showAddSource = true}
                                title="Add Chapter Source"
                        >
                            <Plus size="20"/>
                        </button>
                    </div>

                    {#if selectedSourceIsCue}
                        <div class="mode-selector">
                            <button
                                class="mode-btn"
                                class:active={activeTab === 'alignment'}
                                onclick={() => switchTab('alignment')}
                            >
                                By Alignment
                            </button>
                            <button
                                class="mode-btn"
                                class:active={activeTab === 'selection'}
                                onclick={() => switchTab('selection')}
                            >
                                By Selection
                            </button>
                        </div>
                    {/if}

                    {#if selectedSourceIsCue && activeTab === 'alignment'}
                        <AlignmentTab
                            source={selectedSource}
                            bind:mappings={alignmentMappings}
                        />
                    {:else}
                        <SelectionTab
                            source={selectedSource}
                            bind:mappings={selectionMappings}
                        />
                    {/if}
                </div>

                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick={handleCancel}>
                        Cancel
                    </button>
                    <button
                        class="btn btn-primary"
                        onclick={handleApply}
                        disabled={!canApply || loading}
                    >
                        {loading ? 'Applying…' : 'Apply Titles'}
                    </button>
                </div>
            </div>
        </div>
    </div>
{/if}

<ChapterModal
        bind:isOpen={showChapterTitlesModal}
        title={chapterTitlesModalTitle}
        chapters={chapterTitlesModalData}
        loading={chapterTitlesModalLoading}
        on:close={closeChapterTitlesModal}
/>

<AddSourceDialog
    bind:isOpen={showAddSource}
    expectCues={false}
    onSourceAdded={(src) => { selectedSourceId = src.id; }}
/>

<CustomTitlesDialog
    bind:isOpen={showCustomTitles}
    sourceId={customTitlesSourceId}
/>

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
        max-width: 720px;
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
        flex: 1;
        text-align: center;
    }

    .source-row {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.5rem;
        margin-bottom: 0.75rem;
    }

    .source-label {
        white-space: nowrap;
        font-size: 0.875rem;
        color: var(--text-secondary);
    }

    .source-select-group {
        flex: 1;
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
        max-width: 360px;
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
        border-color: var(--primary-color);
    }

    .source-select:disabled {
        opacity: 0.4;
        cursor: not-allowed;
    }

    .view-titles-btn {
        flex-shrink: 0;
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
        background: var(--primary-color);
        color: white;
        border-color: var(--primary-color);
        transform: translateY(-1px);
    }

    .view-titles-btn:disabled {
        opacity: 0.4;
        cursor: not-allowed;
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

    .mode-selector {
        display: inline-flex;
        border: 1px solid var(--border-color);
        border-radius: 8px;
        margin-bottom: 0.75rem;
        overflow: hidden;
        align-self: center;
    }

    .mode-btn {
        padding: 0.5rem 1rem;
        border: none;
        background: transparent;
        color: var(--text-muted);
        font-weight: 500;
        font-size: 0.875rem;
        border-radius: 0;
        cursor: pointer;
        border-right: 1px solid var(--border-color);
    }

    .mode-btn:last-child {
        border-right: none;
    }

    .mode-btn:first-child {
        border-top-left-radius: 7px;
        border-bottom-left-radius: 7px;
    }

    .mode-btn:last-child {
        border-top-right-radius: 7px;
        border-bottom-right-radius: 7px;
    }

    .mode-btn:hover:not(.active) {
        color: var(--text-primary);
        background: var(--hover-bg);
    }

    .mode-btn.active {
        background: linear-gradient(
            135deg,
            var(--verify-gradient-start) 0%,
            var(--verify-gradient-end) 100%
        );
        color: white;
        font-weight: 600;
        border-right-color: transparent;
    }

    .mode-btn.active + .mode-btn {
        border-left: 1px solid transparent;
    }
</style>
