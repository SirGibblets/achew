<script>
    import {createEventDispatcher, onMount} from "svelte";
    import {llm} from "../utils/api.js";
    import Icon from "./Icon.svelte";

    // Icons
    import Check from "@lucide/svelte/icons/check";
    import ExternalLink from "@lucide/svelte/icons/external-link";
    import Info from "@lucide/svelte/icons/info";
    import TriangleAlert from "@lucide/svelte/icons/triangle-alert";

    const dispatch = createEventDispatcher();

    let providers = [];
    let providerConfigs = {}; // Track config for each provider
    let originalConfigs = {}; // Track original configs to detect changes
    let loading = false;
    let validating = {};
    let configLoaded = false;

    let debounceTimers = {};

    // Auto-validate when provider configs change
    function handleProviderConfigChange(providerId, fieldName, value) {
        // Update the config
        providerConfigs[providerId][fieldName] = value;
        providerConfigs = {...providerConfigs};

        // Mark config as changed for this provider
        const provider = providers.find((p) => p.id === providerId);
        if (provider) {
            provider.config_changed = hasProviderConfigChanged(providerId);
            providers = [...providers];
        }

        // Clear existing timer
        const timerKey = `${providerId}-${fieldName}`;
        if (debounceTimers[timerKey]) {
            clearTimeout(debounceTimers[timerKey]);
        }

        // Remove auto-validation - users must click validate manually
    }

    async function loadProviders() {
        try {
            const data = await llm.getProviders();
            providers = data.providers;

            // Initialize configs for each provider
            for (const provider of providers) {
                providerConfigs[provider.id] = {};
                originalConfigs[provider.id] = {};

                // Initialize config fields based on setup_fields
                for (const field of provider.setup_fields) {
                    // Always start with empty values, don't use placeholder as default
                    providerConfigs[provider.id][field.name] = "";
                    originalConfigs[provider.id][field.name] = "";
                }
            }

            // Load any existing sensitive config values (masked)
            await loadExistingConfig();
        } catch (error) {
            console.error("Failed to load LLM providers:", error);
            providers = [];
        }
    }

    async function loadExistingConfig() {
        try {
            // Load actual saved configs from backend for each provider
            for (const provider of providers) {
                try {
                    const result = await llm.getProviderConfig(provider.id);
                    if (result && result.config) {
                        for (const field of provider.setup_fields) {
                            const savedValue = result.config[field.name];
                            if (savedValue) {
                                if (field.type === "password") {
                                    // Show placeholder for password fields if configured
                                    providerConfigs[provider.id][field.name] =
                                        "••••••••••••••••••••••••••••••••••••••••••••••••••••";
                                    originalConfigs[provider.id][field.name] = "***"; // Mark as existing
                                } else {
                                    // Show actual value for non-password fields
                                    providerConfigs[provider.id][field.name] = savedValue;
                                    originalConfigs[provider.id][field.name] = savedValue;
                                }
                            }
                        }
                    }
                } catch (error) {
                    console.log(
                        `No saved config for ${provider.id} or error loading:`,
                        error.message,
                    );
                }
            }

            // Force reactivity
            providerConfigs = {...providerConfigs};
        } catch (error) {
            console.error("Failed to load existing config:", error);
        }
    }

    function saveProviderConfigsToStorage() {
        try {
            // Save non-sensitive configs to localStorage
            const configsToSave = {};
            for (const provider of providers) {
                configsToSave[provider.id] = {};
                for (const field of provider.setup_fields) {
                    // Only save non-password fields
                    if (field.type !== "password") {
                        const value = providerConfigs[provider.id][field.name];
                        if (value && !value.startsWith("••••")) {
                            configsToSave[provider.id][field.name] = value;
                        }
                    }
                }
            }
            localStorage.setItem(
                "llm_provider_configs",
                JSON.stringify(configsToSave),
            );
        } catch (error) {
            console.error("Failed to save provider configs to storage:", error);
        }
    }

    async function validateProvider(providerId) {
        const provider = providers.find((p) => p.id === providerId);
        if (!provider || !provider.is_enabled) return;

        validating[providerId] = true;
        validating = {...validating};

        // Update provider state to validating
        provider.validation_status = "validating";
        provider.validation_message = "Validating...";
        providers = [...providers];

        try {
            const config = getProviderConfigForValidation(providerId);
            const result = await llm.validateProvider(providerId, config);

            // Update provider state with validation result
            // Note: validation now auto-saves on success
            provider.validation_status = result.valid ? "configured" : "error";
            provider.validation_message = result.message;
            provider.is_configured = result.valid;

            if (result.valid) {
                // Configuration was automatically saved, update original configs
                for (const field of provider.setup_fields) {
                    originalConfigs[provider.id][field.name] =
                        providerConfigs[provider.id][field.name];
                }
                provider.config_changed = false;

                // Save non-sensitive configs to localStorage
                saveProviderConfigsToStorage();
            }
        } catch (error) {
            console.error(`Validation error for ${providerId}:`, error);
            provider.validation_status = "error";
            provider.validation_message = error.message || "Validation failed";
            provider.is_configured = false;
        } finally {
            validating[providerId] = false;
            validating = {...validating};
            providers = [...providers];
        }
    }

    async function saveProviderConfig(providerId) {
        const provider = providers.find((p) => p.id === providerId);
        if (!provider) return;

        try {
            const config = getProviderConfigForValidation(providerId);
            const result = await llm.updateProviderConfig(providerId, config);

            if (result.provider_state) {
                // Update the provider with the new state from backend
                Object.assign(provider, result.provider_state);
            }

            // Update original configs to reflect saved state
            for (const field of provider.setup_fields) {
                originalConfigs[provider.id][field.name] =
                    providerConfigs[provider.id][field.name];
            }

            provider.config_changed = false;
            providers = [...providers];

            // Save non-sensitive configs to localStorage
            saveProviderConfigsToStorage();
        } catch (error) {
            console.error(`Save error for ${providerId}:`, error);
            provider.validation_status = "error";
            provider.validation_message = error.message || "Save failed";
            providers = [...providers];
        }
    }

    async function toggleProviderEnabled(providerId, enabled) {
        const provider = providers.find((p) => p.id === providerId);
        if (!provider) return;

        // Update validation status based on enabled state
        provider.validation_status = enabled ? "not_validated" : "disabled";
        providers = [...providers];

        try {
            const result = await llm.setProviderEnabled(providerId, enabled);

            if (result.provider_state) {
                // Update the provider with the new state from backend
                Object.assign(provider, result.provider_state);
                providers = [...providers];
            }
        } catch (error) {
            console.error(`Toggle enabled error for ${providerId}:`, error);
            // Revert the toggle on error
            provider.is_enabled = !enabled;
            provider.validation_status = !enabled ? "not_validated" : "disabled";
            providers = [...providers];
        }
    }

    async function cancelProviderChanges(providerId) {
        const provider = providers.find((p) => p.id === providerId);
        if (!provider) return;

        try {
            const result = await llm.cancelProviderChanges(providerId);

            if (result.provider_state) {
                // Update the provider with the new state from backend
                Object.assign(provider, result.provider_state);
            }

            // Revert form fields to original state
            for (const field of provider.setup_fields) {
                providerConfigs[provider.id][field.name] =
                    originalConfigs[provider.id][field.name];
            }

            provider.config_changed = false;
            providers = [...providers];
            providerConfigs = {...providerConfigs};
        } catch (error) {
            console.error(`Cancel changes error for ${providerId}:`, error);
        }
    }

    function getProviderConfigForValidation(providerId) {
        const config = {};
        const provider = providers.find((p) => p.id === providerId);
        if (!provider) return config;

        for (const field of provider.setup_fields) {
            const value = providerConfigs[providerId][field.name];
            if (value && !value.startsWith("••••")) {
                config[field.name] = value;
            } else if (originalConfigs[providerId][field.name] === "***") {
                // Keep existing config - don't send placeholder
                continue;
            } else {
                config[field.name] = value || "";
            }
        }

        return config;
    }

    function hasProviderConfigChanged(providerId) {
        const provider = providers.find((p) => p.id === providerId);
        if (!provider) return false;

        for (const field of provider.setup_fields) {
            const currentValue = providerConfigs[providerId][field.name];
            const originalValue = originalConfigs[providerId][field.name];

            // For password fields, if current value is placeholder, no change
            if (
                field.type === "password" &&
                currentValue &&
                currentValue.startsWith("••••")
            ) {
                continue;
            }

            // For password fields, if original was placeholder marker and current is different, it's a change
            if (
                field.type === "password" &&
                originalValue === "***" &&
                currentValue !== originalValue
            ) {
                return true;
            }

            // For all other cases, direct comparison
            if (currentValue !== originalValue) {
                return true;
            }
        }

        return false;
    }

    async function handleDone() {
        try {
            loading = true;

            // Save non-sensitive configs to localStorage
            saveProviderConfigsToStorage();

            const response = await fetch("/api/config/llm/setup", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    action: "verify_and_save",
                    openai_api_key: "", // Empty since validation is handled per-provider now
                }),
            });

            // Always proceed regardless of response - validation is handled per-provider now
            dispatch("llm-setup-complete");
        } catch (error) {
            console.error("Error completing LLM setup:", error);
            // Always proceed - setup is complete from user perspective
            dispatch("llm-setup-complete");
        } finally {
            loading = false;
        }
    }

    async function handleCancel() {
        try {
            loading = true;

            const response = await fetch("/api/config/llm/setup", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    action: "cancel",
                    openai_api_key: "",
                }),
            });

            if (response.ok) {
                dispatch("llm-setup-complete");
            } else {
                console.error("Failed to cancel LLM setup");
            }
        } catch (error) {
            console.error("Error cancelling LLM setup:", error);
        } finally {
            loading = false;
        }
    }

    function getProviderStatusClass(provider) {
        if (!provider.is_enabled) return "disabled";
        if (validating[provider.id]) return "validating";

        switch (provider.validation_status) {
            case "configured":
                return "success";
            case "validating":
                return "validating";
            case "error":
                return "error";
            case "not_validated":
                return "warning";
            case "disabled":
                return "disabled";
            default:
                return "subtle";
        }
    }

    function getProviderStatusText(provider) {
        if (!provider.is_enabled) return "Disabled";
        if (validating[provider.id]) return "Checking...";

        // Handle different validation states properly
        switch (provider.validation_status) {
            case "configured":
                return provider.validation_message || "Configured";
            case "error":
                return provider.validation_message || "Configuration Error";
            case "validating":
                return "Validating...";
            case "not_validated":
                return provider.validation_message || "Not Validated";
            case "disabled":
                return "Disabled";
            default:
                return provider.validation_message || "Not Configured";
        }
    }

    // Reactive statement to show helpful status message with color coding
    $: statusMessage = (() => {
        const enabledProviders = providers.filter((p) => p.is_enabled);
        const configuredProviders = enabledProviders.filter(
            (p) => p.validation_status === "configured",
        );

        if (enabledProviders.length === 0) {
            return {text: "No providers enabled", color: "grey"};
        } else if (configuredProviders.length === enabledProviders.length) {
            return {text: "All providers ready", color: "green"};
        } else {
            const remaining = enabledProviders.length - configuredProviders.length;
            const providerText =
                remaining === 1 ? "provider needs" : "providers need";
            return {
                text: `${remaining} ${providerText} configuration`,
                color: "warning",
            };
        }
    })();

    // Load providers and config on mount
    onMount(async () => {
        loading = true;
        await loadProviders();
        loading = false;
        configLoaded = true;
    });
</script>

<div class="llm-setup-container">
    <div class="setup-header">
        <div class="header-icon">
            <Icon
                    name="ai"
                    size="48"
                    color="linear-gradient(135deg, var(--accent-gradient-start) 0%, var(--accent-gradient-end) 100%)"
            />
        </div>
        <h1>LLM Configuration</h1>
        <p class="optional-label">OPTIONAL</p>
        <p>
            Configure access to LLM services for enhanced cleanup and processing of
            chapter titles.<br/>These are <strong>optional</strong>, but at least one
            is required to use <strong>AI Cleanup</strong>.
        </p>
    </div>

    <div class="setup-form">
        <!-- Dynamic Providers -->
        {#each providers as provider (provider.id)}
            <div class="provider-section" class:disabled={!provider.is_enabled}>
                <div class="provider-header">
                    <div class="provider-info">
                        <div class="provider-title-row">
                            <div class="provider-title-with-toggle">
                                <label class="toggle-switch">
                                    <input
                                            type="checkbox"
                                            bind:checked={provider.is_enabled}
                                            on:change={() =>
                      toggleProviderEnabled(provider.id, provider.is_enabled)}
                                            disabled={loading}
                                    />
                                    <span class="toggle-slider"></span>
                                </label>
                                <h2>{provider.name}</h2>
                                {#if provider.is_recommended}
                                    <span class="recommended-badge">Recommended</span>
                                {/if}
                            </div>
                            <div class="provider-status {getProviderStatusClass(provider)}">
                                <div class="status-icon">
                                    {#if validating[provider.id]}
                                        <div class="spinner"></div>
                                    {:else if getProviderStatusClass(provider) === "success"}
                                        <Check size="16"/>
                                    {:else if getProviderStatusClass(provider) === "error"}
                                        <TriangleAlert size="16"/>
                                    {:else}
                                        <Info size="16"/>
                                    {/if}
                                </div>
                                <span class="status-text"
                                >{getProviderStatusText(provider)}</span
                                >
                            </div>
                        </div>
                        <p class="provider-desc">{provider.description}</p>
                    </div>
                </div>

                <!-- Dynamic form fields based on setup_fields -->
                <div class="provider-form" class:form-disabled={!provider.is_enabled}>
                    {#each provider.setup_fields as field}
                        {#if field.help_url}
                            <p class="field-hint">
                                <a
                                        class="field-hint"
                                        href={field.help_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                >
                                    Get my {field.label}
                                    <ExternalLink size="12"/>
                                </a>
                            </p>
                        {/if}

                        <div class="form-group">
                            <input
                                    id="{provider.id}-{field.name}"
                                    type={field.type === "password" ? "password" : "text"}
                                    bind:value={providerConfigs[provider.id][field.name]}
                                    placeholder={field.placeholder || field.label}
                                    disabled={loading || !provider.is_enabled}
                                    required={field.required}
                                    on:input={() =>
                  handleProviderConfigChange(
                    provider.id,
                    field.name,
                    providerConfigs[provider.id][field.name],
                  )}
                            />
                        </div>
                    {/each}

                    <!-- Provider Actions -->
                    {#if provider.is_enabled && provider.config_changed}
                        <div class="provider-actions">
                            <button
                                    class="btn btn-cancel"
                                    disabled={loading || validating[provider.id]}
                                    on:click={() => cancelProviderChanges(provider.id)}
                            >
                                Cancel
                            </button>

                            <button
                                    class="btn btn-validate"
                                    disabled={loading || validating[provider.id]}
                                    on:click={() => validateProvider(provider.id)}
                            >
                                {#if validating[provider.id]}
                                    <span class="btn-spinner"></span>
                                    Validating...
                                {:else}
                                    Validate
                                {/if}
                            </button>
                        </div>
                    {/if}
                </div>
            </div>
        {/each}

        <div class="form-actions">
            <div class="status-message status-{statusMessage.color}">
                <div class="status-icon">
                    {#if statusMessage.color === "green"}
                        <Check size="16"/>
                    {:else if statusMessage.color === "warning"}
                        <TriangleAlert size="16"/>
                    {:else}
                        <Info size="16"/>
                    {/if}
                </div>
                <span class="status-text">{statusMessage.text}</span>
            </div>
            <button class="btn btn-verify" disabled={loading} on:click={handleDone}>
                {#if loading}
                    <span class="btn-spinner"></span>
                    Completing...
                {:else}
                    Done
                {/if}
            </button>
        </div>
    </div>
</div>

<style>
    .llm-setup-container {
        max-width: 700px;
        margin: 0 auto;
    }

    .setup-header {
        text-align: center;
        margin-bottom: 3rem;
    }

    .header-icon {
        margin-bottom: 1rem;
        color: var(--primary-color);
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

    .provider-section.disabled {
        opacity: 0.65;
        background: linear-gradient(
                135deg,
                rgba(100, 100, 100, 0.1) 0%,
                rgba(120, 120, 120, 0.08) 100%
        );
        border-color: rgba(100, 100, 100, 0.2);
    }

    .provider-title-with-toggle {
        display: flex;
        align-items: center;
        gap: 1rem;
    }

    .toggle-switch {
        position: relative;
        display: inline-block;
        width: 50px;
        height: 24px;
    }

    .toggle-switch input {
        opacity: 0;
        width: 0;
        height: 0;
    }

    .toggle-slider {
        position: absolute;
        cursor: pointer;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background-color: #ccc;
        transition: 0.3s;
        border-radius: 24px;
    }

    .toggle-slider:before {
        position: absolute;
        content: "";
        height: 18px;
        width: 18px;
        left: 3px;
        bottom: 3px;
        background-color: white;
        transition: 0.3s;
        border-radius: 50%;
    }

    .recommended-badge {
        background-color: color-mix(in srgb, var(--primary-color) 80%, transparent);
        color: white;
        padding: 0.25rem 0.5rem;
        border-radius: 12px;
        font-size: 0.6rem;
        font-weight: 700;
        margin-left: 0.25rem;
        text-transform: uppercase;
    }

    input:checked + .toggle-slider {
        background-color: var(--primary-color);
    }

    input:checked + .toggle-slider:before {
        transform: translateX(26px);
    }

    input:disabled + .toggle-slider {
        opacity: 0.6;
        cursor: not-allowed;
    }

    .form-disabled {
        pointer-events: none;
        opacity: 0.35;
    }

    .provider-header {
        margin-bottom: 0.25rem;
    }

    .provider-title-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.5rem;
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
        color: var(--text-primary);
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

    .provider-status.validating {
        color: var(--text-secondary);
    }

    .provider-status.disabled {
        color: var(--text-secondary);
        opacity: 0.6;
    }

    .provider-status.warning {
        color: var(--warning);
    }

    .provider-form {
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
    }

    .form-group {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
        margin-bottom: 0;
    }

    .field-hint {
        font-size: 0.75rem;
        color: var(--text-secondary);
        margin-top: 0.5rem;
        margin-bottom: 0;
        display: flex;
        align-items: center;
        gap: 0.25rem;
    }

    .field-hint a {
        color: var(--primary-color);
        text-decoration: none;
    }

    .field-hint a:hover {
        text-decoration: underline;
    }

    .provider-actions {
        display: flex;
        justify-content: flex-end;
        gap: 0.75rem;
        margin-top: 1rem;
    }

    .btn-validate,
    .btn-cancel {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.5rem 1rem;
        border-radius: 6px;
        font-size: 0.9rem;
        font-weight: 500;
        cursor: pointer;
        border: 2px solid var(--color-border);
        background: var(--color-background);
        color: var(--text-primary);
    }

    .btn-validate {
        background: var(--primary-color);
        color: white;
        border-color: var(--primary-color);
    }

    .btn-validate:hover:not(:disabled) {
        background: var(--primary-hover);
    }

    .btn-cancel:hover:not(:disabled) {
        border-color: var(--primary-color);
        background: var(--color-surface);
    }

    .btn-validate:disabled,
    .btn-cancel:disabled {
        opacity: 0.6;
        cursor: not-allowed;
        transform: none;
    }

    .btn-spinner {
        width: 14px;
        height: 14px;
        border: 2px solid transparent;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        flex-shrink: 0;
    }

    .spinner {
        width: 16px;
        height: 16px;
        border: 2px solid transparent;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        flex-shrink: 0;
    }

    .optional-label {
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
        flex-direction: column;
        align-items: center;
        gap: 0.75rem;
    }

    .status-message {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.9rem;
        font-weight: 500;
        text-align: center;
    }

    .status-icon {
        display: flex;
        align-items: center;
        flex-shrink: 0;
    }

    .status-text {
        white-space: pre-line;
    }

    @media (max-width: 768px) {
        .llm-setup-container {
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
