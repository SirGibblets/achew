<script>
    import {createEventDispatcher} from "svelte";
    import {session, transcriptionStatuses} from "../stores/session.js";
    import ASRSettings from "./ASRSettings.svelte";

    import Mic from "@lucide/svelte/icons/mic";

    const dispatch = createEventDispatcher();

    let loading = false;

    async function handleSave() {
        loading = true;
        try {
            const response = await fetch("/api/complete-asr-setup", {
                method: "POST",
            });

            if (response.ok) {
                await session.loadActiveSession();
                dispatch("asr-setup-complete");
            } else {
                const data = await response.json();
                console.error("Failed to complete ASR setup:", data.detail);
            }
        } catch (error) {
            console.error("Error completing ASR setup:", error);
        } finally {
            loading = false;
        }
    }

    async function handleCancel() {
        // Just go back without releasing the warm cache
        loading = true;
        try {
            const response = await fetch("/api/complete-asr-setup", {
                method: "POST",
            });

            if (response.ok) {
                await session.loadActiveSession();
            }
        } catch (error) {
            console.error("Error canceling ASR setup:", error);
        } finally {
            loading = false;
        }
    }

    $: hasActiveTranscriptions = Object.keys($transcriptionStatuses).length > 0;
</script>

<div class="asr-setup">
    <div class="header">
        <div class="header-icon">
            <Mic size="32"/>
        </div>
        <h2>Transcription Settings</h2>
        <p>Configure the Automatic Speech Recognition service used for transcribing chapter titles.</p>
    </div>

    <div class="settings-content">
        <ASRSettings showAdvanced={true} showOptions={true} />
    </div>

    {#if hasActiveTranscriptions}
        <div class="warning-banner">
            Transcriptions are currently in progress. Settings changes will take effect for future transcriptions.
        </div>
    {/if}

    <div class="actions">
        <button
                class="btn btn-cancel"
                on:click={handleCancel}
                disabled={loading}
        >
            Cancel
        </button>
        <button
                class="btn btn-verify"
                on:click={handleSave}
                disabled={loading}
        >
            {#if loading}
                <span class="btn-spinner"></span>
                Saving…
            {:else}
                Save
            {/if}
        </button>
    </div>
</div>

<style>
    .asr-setup {
        max-width: 900px;
        margin: 0 auto;
        width: 100%;
    }

    .header {
        text-align: center;
        margin-bottom: 3rem;
    }

    .header-icon {
        display: flex;
        justify-content: center;
        margin-bottom: 1rem;
        color: var(--primary-color);
    }

    .header h2 {
        margin-bottom: 0.75rem;
        font-size: 2rem;
        font-weight: 600;
    }

    .header p {
        color: var(--text-secondary);
        font-size: 1rem;
        line-height: 1.5;
    }

    .settings-content {
        margin-bottom: 2rem;
    }

    .warning-banner {
        background: rgba(245, 158, 11, 0.1);
        border: 1px solid rgba(245, 158, 11, 0.3);
        color: var(--warning);
        padding: 0.75rem 1rem;
        border-radius: 8px;
        font-size: 0.9rem;
        text-align: center;
        margin-bottom: 1rem;
    }

    .actions {
        display: flex;
        gap: 1rem;
        justify-content: center;
        margin-top: 2rem;
    }

    .btn-spinner {
        width: 14px;
        height: 14px;
        border: 2px solid transparent;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin-right: 0.5rem;
    }

    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }

    @media (max-width: 768px) {
        .actions {
            flex-direction: column;
            align-items: stretch;
        }
    }
</style>
