<script>
    import {onMount} from "svelte";
    import {session} from "../stores/session.js";
    import {api} from "../utils/api.js";
    import ASRSettings from "./ASRSettings.svelte";

    let loading = false;
    let segmentCount = 0;

    // Load segment count
    async function loadSegmentCount() {
        try {
            const response = await api.session.getSegmentCount();
            segmentCount = response.segment_count;
        } catch (error) {
            console.error("Failed to load segment count:", error);
            segmentCount = 0;
        }
    }

    // Action handlers
    async function proceedWithTranscription() {
        if (loading) return;

        loading = true;
        try {
            await api.session.configureASR("transcribe");
        } catch (error) {
            console.error("Failed to start transcription:", error);
            session.setError("Failed to start transcription: " + error.message);
        } finally {
            loading = false;
        }
    }

    async function skipTranscription() {
        if (loading) return;

        loading = true;
        try {
            await api.session.configureASR("skip");
        } catch (error) {
            console.error("Failed to skip transcription:", error);
            session.setError("Failed to skip transcription: " + error.message);
        } finally {
            loading = false;
        }
    }

    onMount(async () => {
        await loadSegmentCount();
    });
</script>

<div class="configure-asr">
    <div class="header">
        <h2>Transcribe Titles</h2>
        <p>
            Titles will be generated for <strong>{segmentCount}</strong>
            chapter{segmentCount !== 1 ? "s" : ""} using a local ASR model.<br/>
            Configure the transcription settings below.
        </p>
    </div>

    <div class="asr-configuration">
        <ASRSettings showAdvanced={true} showOptions={true} />
    </div>

    <div class="actions">
        <button
                class="btn btn-cancel"
                on:click={skipTranscription}
                disabled={loading}
        >
            {#if loading}
                <span class="btn-spinner"></span>
                Processing…
            {:else}
                Skip Transcription
            {/if}
        </button>

        <button
                class="btn btn-verify"
                on:click={proceedWithTranscription}
                disabled={loading}
        >
            {#if loading}
                <span class="btn-spinner"></span>
                Starting…
            {:else}
                Transcribe
            {/if}
        </button>
    </div>
</div>

<style>
    .configure-asr {
        max-width: 900px;
        margin: 0 auto;
        width: 100%;
    }

    .header {
        text-align: center;
        margin-bottom: 3rem;
    }

    .header p {
        color: var(--text-secondary);
        font-size: 1rem;
        line-height: 1.5;
    }

    .header h2 {
        margin-bottom: 0.75rem;
        font-size: 2rem;
        font-weight: 600;
    }

    .asr-configuration {
        margin-bottom: 3rem;
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
