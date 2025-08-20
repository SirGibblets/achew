<script>
    import {createEventDispatcher} from "svelte";
    import Icon from "./Icon.svelte";

    // Icons
    import CircleQuestionMark from "@lucide/svelte/icons/circle-question-mark";
    import X from "@lucide/svelte/icons/x";

    const dispatch = createEventDispatcher();

    export let isOpen = false;
    export let title = "";
    export let chapters = [];
    export let loading = false;

    let dialog;

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

    function closeModal() {
        dialog?.close();
        dispatch("close");
    }

    // React to isOpen prop changes
    $: if (dialog) {
        if (isOpen) {
            dialog.showModal();
        } else {
            dialog.close();
        }
    }

    function handleDialogClick(event) {
        // Close dialog when clicking on backdrop (outside the dialog content)
        if (event.target === dialog) {
            closeModal();
        }
    }
</script>

<dialog bind:this={dialog} on:click={handleDialogClick} on:close={closeModal}>
    <div class="modal-container">
        <div class="modal-header">
            <h3>{title}</h3>
            <button
                    class="close-button"
                    on:click={closeModal}
                    aria-label="Close modal"
            >
                <X size="24"/>
            </button>
        </div>

        <div class="modal-body">
            {#if loading}
                <div class="loading-state">
                    <div class="spinner"></div>
                    <p>Loading chapter data...</p>
                </div>
            {:else if chapters.length === 0}
                <div class="empty-state">
                    <CircleQuestionMark size="48" color="var(--text-secondary)"/>
                    <p>No chapter data available</p>
                </div>
            {:else}
                <div class="chapters-list">
                    <div class="chapter-header">
                        <span class="header-time">Timestamp</span>
                        <span class="header-title">Chapter Title</span>
                    </div>
                    {#each chapters as chapter, index}
                        <div class="chapter-row">
                            <span class="chapter-time">{formatTime(chapter.timestamp)}</span>
                            <span class="chapter-title"
                            >{chapter.title || `Chapter ${index + 1}`}</span
                            >
                        </div>
                    {/each}
                </div>
            {/if}
        </div>
    </div>
</dialog>

<style>
    dialog {
        padding: 0;
        border: none;
        border-radius: 12px;
        background: transparent;
        max-width: 90vw;
        max-height: 90vh;
        width: 600px;
    }

    dialog::backdrop {
        background: rgba(0, 0, 0, 0.6);
        backdrop-filter: blur(2px);
    }

    .modal-container {
        background: var(--bg-primary);
        border-radius: 12px;
        width: 100%;
        max-height: 80vh;
        display: flex;
        flex-direction: column;
        border: 1px solid var(--border-color);
    }

    .modal-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 1.5rem;
        border-bottom: 1px solid var(--border-color);
    }

    .modal-header h3 {
        margin: 0;
        color: var(--text-primary);
        font-size: 1.25rem;
        font-weight: 600;
    }

    .close-button {
        background: none;
        border: none;
        cursor: pointer;
        padding: 0.5rem;
        border-radius: 6px;
        color: var(--text-secondary);
        transition: all 0.2s ease;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.5rem;
        width: 32px;
        height: 32px;
    }

    .close-button:hover {
        background: var(--bg-tertiary);
        color: var(--text-primary);
    }

    .modal-body {
        flex: 1;
        overflow: hidden;
        display: flex;
        flex-direction: column;
    }

    .loading-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 3rem;
        color: var(--text-secondary);
    }

    .spinner {
        width: 24px;
        height: 24px;
        border: 2px solid var(--border-color);
        border-top: 2px solid var(--primary-color);
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin-bottom: 1rem;
    }

    @keyframes spin {
        0% {
            transform: rotate(0deg);
        }
        100% {
            transform: rotate(360deg);
        }
    }

    .empty-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 3rem;
        color: var(--text-secondary);
    }

    .empty-state p {
        margin-top: 1rem;
        margin-bottom: 0;
    }

    .chapters-list {
        flex: 1;
        overflow: auto;
        padding: 0;
    }

    .chapter-header {
        display: grid;
        grid-template-columns: 120px 1fr;
        gap: 1rem;
        padding: 1rem 1.5rem;
        background: var(--bg-secondary);
        border-bottom: 1px solid var(--border-color);
        font-weight: 600;
        color: var(--text-secondary);
        font-size: 0.875rem;
        text-transform: uppercase;
        position: sticky;
        top: 0;
        z-index: 1;
    }

    .chapter-row {
        display: grid;
        grid-template-columns: 120px 1fr;
        gap: 1rem;
        padding: 0.875rem 1.5rem;
        border-bottom: 1px solid var(--border-color);
        transition: background-color 0.15s ease;
    }

    .chapter-row:hover {
        background: var(--bg-secondary);
    }

    .chapter-row:last-child {
        border-bottom: none;
    }

    .chapter-time {
        font-family: "Courier New", monospace;
        font-size: 0.875rem;
        color: var(--text-secondary);
        font-weight: 500;
    }

    .chapter-title {
        color: var(--text-primary);
        font-size: 0.875rem;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .header-time,
    .header-title {
        font-size: 0.75rem;
    }

    /* Responsive design */
    @media (max-width: 768px) {
        dialog {
            width: 95vw;
            max-width: 95vw;
        }

        .modal-container {
            max-height: 85vh;
        }

        .modal-header {
            padding: 1rem;
        }

        .modal-header h3 {
            font-size: 1.125rem;
        }

        .chapter-header,
        .chapter-row {
            grid-template-columns: 100px 1fr;
            gap: 0.75rem;
            padding: 0.75rem 1rem;
        }

        .chapter-time {
            font-size: 0.8rem;
        }

        .chapter-title {
            font-size: 0.8rem;
        }
    }
</style>
