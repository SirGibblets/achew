<script>
    import {createEventDispatcher} from "svelte";

    // Icons
    import Check from "@lucide/svelte/icons/check";
    import Headphones from "@lucide/svelte/icons/headphones";
    import Info from "@lucide/svelte/icons/info";
    import TriangleAlert from "@lucide/svelte/icons/triangle-alert";

    const dispatch = createEventDispatcher();

    let absUrl = "";
    let absApiKey = "";
    let loading = false;
    let validationStatus = {valid: false, message: "Not configured"};
    let configLoaded = false;
    let isInitialSetup = false; // true if this is first-time setup, false if updating existing config

    async function loadConfig() {
        try {
            loading = true;
            const response = await fetch("/api/config/abs");
            const data = await response.json();

            if (response.ok) {
                // Determine if this is initial setup (no previous valid configuration)
                isInitialSetup = !(
                    data.validated &&
                    data.url &&
                    data.api_key === "***"
                );

                absUrl = data.url || "";
                // If there's an actual API key (masked as ***), show placeholder
                if (data.api_key === "***") {
                    absApiKey = "••••••••••••••••••••••••••••••••••••••••••••••••••••"; // Show placeholder to indicate configured
                    validationStatus = {
                        valid: data.validated,
                        message: data.validated ? "Configured" : "Not Configured",
                    };
                } else {
                    // No API key configured
                    absApiKey = "";
                    validationStatus = {valid: false, message: "Not configured"};
                }

                // Force reactivity update
                validationStatus = {...validationStatus};
            }
        } catch (error) {
            console.error("Failed to load ABS config:", error);
        } finally {
            loading = false;
            configLoaded = true;
        }
    }

    async function handleVerifyAndSave() {
        try {
            loading = true;

            // If the API key field contains the placeholder (bullets), send it as is so backend knows it's unchanged
            const urlToSend = absUrl.trim();
            const apiKeyToSend = absApiKey.startsWith("••••")
                ? absApiKey
                : absApiKey.trim();

            const response = await fetch("/api/config/abs/setup", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    action: "verify_and_save",
                    url: urlToSend,
                    api_key: apiKeyToSend,
                }),
            });

            const data = await response.json();

            if (data.success) {
                // Success - user will be taken to next step automatically
                dispatch("abs-configured");
            } else {
                // Handle validation errors
                if (data.errors.abs) {
                    validationStatus = {valid: false, message: data.errors.abs};
                    validationStatus = {...validationStatus};
                } else {
                    // General error
                    validationStatus = {valid: false, message: data.message};
                    validationStatus = {...validationStatus};
                }
            }
        } catch (error) {
            console.error("Error in verify and save:", error);
            validationStatus = {valid: false, message: "Network error"};
            validationStatus = {...validationStatus};
        } finally {
            loading = false;
        }
    }

    async function handleCancel() {
        try {
            loading = true;
            const response = await fetch("/api/config/abs/setup", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    action: "cancel",
                    url: "",
                    api_key: "",
                }),
            });

            if (response.ok) {
                dispatch("abs-configured");
            }
        } catch (error) {
            console.error("Error cancelling ABS setup:", error);
        } finally {
            loading = false;
        }
    }

    // Reactive status calculations
    $: statusClass = !validationStatus
        ? "subtle"
        : validationStatus.valid
            ? "success"
            : validationStatus.message === "Not configured"
                ? "subtle"
                : "error";

    $: statusText = !validationStatus
        ? "Not configured"
        : validationStatus.message || "Not Configured";

    // Show cancel button only if not initial setup and config is loaded
    $: showCancelButton = configLoaded && !isInitialSetup;

    // Cancel button should only be disabled when loading
    $: cancelDisabled = loading;

    // Load config on mount
    import {onMount} from "svelte";

    onMount(async () => {
        await loadConfig();
    });
</script>

<div class="abs-setup-container">
    <div class="setup-header">
        <!-- SVG gradient definition -->
        <svg width="0" height="0" style="position: absolute;">
            <defs>
                <radialGradient id="headphone-gradient" cx="0%" cy="0%" fr="35%" r="136%">
                    <stop offset="0%" style="stop-color: var(--accent-gradient-start);"/>
                    <stop offset="100%" style="stop-color: var(--accent-gradient-end);"/>
                </radialGradient>
            </defs>
        </svg>

        <div class="header-icon">
            <div class="gradient-icon">
                <Headphones size="48"/>
            </div>
        </div>
        <h1>Audiobookshelf Setup</h1>
        <p class="required-label">REQUIRED</p>
    </div>

    <div class="setup-form">
        <!-- ABS Server Section -->
        <div class="provider-section">
            <div class="provider-header">
                <div class="provider-info">
                    <div class="provider-title-row">
                        <h2>Audiobookshelf Server</h2>
                        <div class="provider-status {statusClass}">
                            <div class="status-icon">
                                {#if statusClass === "success"}
                                    <Check size="16"/>
                                {:else if statusClass === "error"}
                                    <TriangleAlert size="16"/>
                                {:else}
                                    <Info size="16"/>
                                {/if}
                            </div>
                            <span class="status-text">{statusText}</span>
                        </div>
                    </div>
                    <p class="provider-desc">
                        Enter your Audiobookshelf URL and API key. The key must act on
                        behalf of a user with the following permissions: Can Download, Can
                        Update.
                    </p>
                </div>
            </div>

            <div class="provider-form">
                <div class="form-group">
                    <input
                            id="abs-url"
                            type="url"
                            bind:value={absUrl}
                            placeholder="https://abs.your-server.com"
                            disabled={loading}
                    />
                    <p class="field-hint">
                        Server URL. Must include the protocol, e.g. https://
                    </p>
                </div>

                <div class="form-group">
                    <input
                            id="abs-api-key"
                            type="text"
                            bind:value={absApiKey}
                            placeholder="API Key"
                            disabled={loading}
                    />
                    <p class="field-hint">
                        API Key. Create new keys in your Audiobookshelf settings.
                    </p>
                </div>
            </div>
        </div>

        <div class="form-actions">
            {#if showCancelButton}
                <button
                        class="btn btn-cancel"
                        disabled={cancelDisabled}
                        on:click={handleCancel}
                >
                    Cancel
                </button>
            {/if}
            <button
                    class="btn btn-verify"
                    disabled={loading}
                    on:click={handleVerifyAndSave}
            >
                {#if loading}
                    <span class="btn-spinner"></span>
                    Verifying...
                {:else}
                    {isInitialSetup ? "Continue" : "Done"}
                {/if}
            </button>
        </div>
    </div>
</div>

<style>
    .abs-setup-container {
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

    .gradient-icon :global(svg) {
        stroke: url(#headphone-gradient);
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
        transition: all 0.2s ease;
    }

    .provider-header {
        margin-bottom: 1rem;
    }

    .provider-title-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.25rem;
        gap: 1rem;
    }

    .provider-info h2 {
        margin: 0;
        color: var(--text-primary);
        font-size: 1.25rem;
        font-weight: 600;
    }

    .provider-desc {
        margin: 0;
        color: var(--text-secondary);
        font-size: 0.9rem;
    }

    .provider-status {
        display: flex;
        align-items: center;
        gap: 0.35rem;
        font-size: 0.85rem;
        font-weight: 500;
        transition: all 0.2s ease;
        white-space: nowrap;
    }

    .provider-status.success {
        color: var(--success);
    }

    .provider-status.error {
        color: var(--danger);
    }

    .provider-status.subtle {
        color: var(--text-secondary);
    }

    .status-icon {
        display: flex;
        align-items: center;
        flex-shrink: 0;
    }

    .status-text {
        white-space: nowrap;
    }

    .provider-form {
        display: flex;
        flex-direction: column;
        gap: 1.5rem;
    }

    .form-group {
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
        margin-bottom: 0;
    }

    .field-hint {
        font-size: 0.8rem;
        margin: 0;
    }

    .spinner {
        width: 16px;
        height: 16px;
        border: 2px solid transparent;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        flex-shrink: 0;
    }

    .required-label {
        color: var(--primary-color);
        font-weight: 600;
        font-size: 0.75rem;
        margin-top: -0.25rem;
    }

    @keyframes spin {
        0% {
            transform: rotate(0deg);
        }
        100% {
            transform: rotate(360deg);
        }
    }

    .form-actions {
        margin-top: 1rem;
        display: flex;
        justify-content: center;
        gap: 1rem;
    }

    @media (max-width: 768px) {
        .abs-setup-container {
            margin: 1rem;
        }

        .setup-header h1 {
            font-size: 1.5rem;
        }

        .provider-title-row {
            flex-direction: column;
            align-items: flex-start;
            gap: 0.5rem;
        }

        .provider-status {
            align-self: flex-end;
            font-size: 0.8rem;
        }

        .form-actions {
            flex-direction: column;
            gap: 0.75rem;
        }
    }
</style>
