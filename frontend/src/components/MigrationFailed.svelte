<script>
    import {createEventDispatcher} from "svelte";

    import TriangleAlert from "@lucide/svelte/icons/triangle-alert";

    const dispatch = createEventDispatcher();

    let loading = false;
    let error = null;

    async function handleReset() {
        try {
            loading = true;
            error = null;

            const response = await fetch("/api/config/migration/reset", {
                method: "POST",
            });

            const data = await response.json();

            if (data.success) {
                dispatch("migration-reset");
            } else {
                error = data.detail || "Reset failed";
            }
        } catch (e) {
            console.error("Migration reset failed:", e);
            error = "Network error — could not reach the server.";
        } finally {
            loading = false;
        }
    }
</script>

<div class="migration-container">
    <div class="setup-header">
        <div class="header-icon">
            <TriangleAlert size="48" color="var(--primary-color)"/>
        </div>
        <h1>Settings Migration Failed</h1>
    </div>

    <div class="setup-form">
        <div class="provider-section">
            <div class="provider-header">
                <div class="provider-info">
                    <h2>Unable to Read Existing Settings</h2>
                    <p class="provider-desc">
                        Your settings were saved in a format that is incompatible with this
                        version. This can happen when the underlying Python version changes
                        during an update. Unfortunately, the old settings cannot be recovered
                        automatically.
                    </p>
                    <h2 style="margin-top: 1.25rem;">
                        To continue, you must either reset your settings or downgrade Achew
                        to a previous version.
                    </h2>
                    <p class="provider-desc">
                        After resetting, you will need to re-enter any of the following that
                        were previously configured:
                    </p>
                    <ul class="reset-details">
                        <li>Audiobookshelf server URL and API key</li>
                        <li>LLM provider API keys</li>
                        <li>Transcription and editor preferences</li>
                        <li>Custom AI Cleanup instructions</li>
                        <li>Chapter search rules</li>
                    </ul>
                </div>
            </div>
        </div>

        {#if error}
            <div class="alert alert-danger">
                {error}
            </div>
        {/if}

        <div class="form-actions">
            <button
                    class="btn btn-verify"
                    disabled={loading}
                    on:click={handleReset}
            >
                {#if loading}
                    <span class="btn-spinner"></span>
                    Resetting…
                {:else}
                    Reset Settings and Continue
                {/if}
            </button>
        </div>
    </div>
</div>

<style>
    .migration-container {
        max-width: 700px;
        margin: 0 auto;
    }

    .setup-header {
        text-align: center;
        margin-bottom: 3rem;
    }

    .header-icon {
        margin-bottom: 1rem;
        display: flex;
        justify-content: center;
    }

    .setup-header h1 {
        margin: 0 0 0.5rem 0;
        color: var(--text-primary);
        font-size: 1.75rem;
        font-weight: 600;
    }

    .setup-form {
        display: flex;
        flex-direction: column;
        gap: 2rem;
    }

    .provider-section {
        background: linear-gradient(
                135deg,
                color-mix(in srgb, var(--accent-1) 14%, transparent) 0%,
                color-mix(in srgb, var(--accent-2) 10%, transparent) 100%
        );
        border: 1px solid color-mix(in srgb, var(--accent-1) 20%, transparent);
        border-radius: 16px;
        padding: 1.5rem;
    }

    .provider-header {
        margin-bottom: 0;
    }

    .provider-info h2 {
        margin: 0 0 0.5rem 0;
        color: var(--text-primary);
        font-size: 1.25rem;
        font-weight: 600;
    }

    .provider-desc {
        margin: 0;
        color: var(--text-secondary);
        font-size: 0.9rem;
    }

    .reset-details {
        margin: 0.25rem 0 0 1.25rem;
        padding: 0;
        color: var(--text-secondary);
        font-size: 0.9rem;
        line-height: 1.6;
    }

    .alert-danger {
        color: var(--danger);
        background: color-mix(in srgb, var(--danger) 10%, transparent);
        border: 1px solid color-mix(in srgb, var(--danger) 25%, transparent);
        border-radius: 8px;
        padding: 0.75rem 1rem;
        font-size: 0.9rem;
    }

    .form-actions {
        margin-top: 1rem;
        display: flex;
        justify-content: center;
    }

    @media (max-width: 768px) {
        .migration-container {
            margin: 1rem;
        }

        .setup-header h1 {
            font-size: 1.5rem;
        }
    }
</style>
