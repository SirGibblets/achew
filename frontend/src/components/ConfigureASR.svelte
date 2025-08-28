<script>
    import {onMount} from "svelte";
    import {session} from "../stores/session.js";
    import {api} from "../utils/api.js";

    import ChevronDown from "@lucide/svelte/icons/chevron-down";
    import CircleQuestionMark from '@lucide/svelte/icons/circle-question-mark';
    import RotateCcw from '@lucide/svelte/icons/rotate-ccw';
    import TriangleAlert from "@lucide/svelte/icons/triangle-alert";

    let loading = false;
    let segmentCount = 0;

    // ASR Services state
    let asrServices = [];
    let currentASRService = "";
    let currentASRVariant = "";
    let currentASRLanguage = "";
    let bookLanguage = null;
    let asrLoading = false;
    let serviceDropdownOpen = false;

    // ASR Options state
    let asrOptions = {trim: true, use_bias_words: false, bias_words: ""};
    let asrOptionsLoading = false;
    
    // Default bias words
    const DEFAULT_BIAS_WORDS = `Chapter Section Part Letter Book Volume Section Subsection Paragraph Page Segment Scene Act Episode
Introduction Preface Epilogue Prologue Foreword Dedication Acknowledgments Afterword Notes Endnotes
Audible Librivox Recording Summary Previously Preview Epigraph Recap Appendix
1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25`;

    let biasWordsDebounceTimer = null;

    function findMatchingLanguage(availableLanguages, bookLang) {
        if (!bookLang || !availableLanguages || availableLanguages.length === 0) {
            return null;
        }
        
        const normalizedBookLang = bookLang.trim().toLowerCase();
        
        // Try exact matches first (language codes)
        for (const [code, englishName, nativeName] of availableLanguages) {
            if (code.toLowerCase() === normalizedBookLang) {
                return code;
            }
        }
        
        // Try matching English names
        for (const [code, englishName, nativeName] of availableLanguages) {
            if (englishName.toLowerCase() === normalizedBookLang) {
                return code;
            }
        }
        
        // Try matching native names
        for (const [code, englishName, nativeName] of availableLanguages) {
            if (nativeName && nativeName.toLowerCase() === normalizedBookLang) {
                return code;
            }
        }
        
        // Try partial matches on English names
        for (const [code, englishName, nativeName] of availableLanguages) {
            if (englishName.toLowerCase().includes(normalizedBookLang) ||
                normalizedBookLang.includes(englishName.toLowerCase())) {
                return code;
            }
        }
        
        return null;
    }

    function selectLanguageForVariant(variant, bookLang) {
        if (!variant || !variant.languages) {
            return variant?.languages?.[0]?.[0] || "";
        }
        
        const matchedLanguage = findMatchingLanguage(variant.languages, bookLang);
        return matchedLanguage || variant.languages[0][0] || "";
    }

    // Load ASR preferences
    async function loadASRPreferences() {
        try {
            asrLoading = true;
            const response = await api.config.getASRPreferences();
            asrServices = response.available_services;
            currentASRService = response.current_service;
            currentASRVariant = response.current_variant;
            currentASRLanguage = response.current_language;
            bookLanguage = response.book_language;

            // If no variant is set, default to the first variant of the current service
            if (!currentASRVariant && currentASRService) {
                const service = asrServices.find(
                    (s) => s.service_id === currentASRService,
                );
                const firstVariant = service?.variants?.[0]?.model_id;
                if (firstVariant) {
                    currentASRVariant = firstVariant;
                    // Update the backend with the default variant
                    await updateASRPreference(
                        currentASRService,
                        firstVariant,
                        currentASRLanguage,
                    );
                }
            }

            // If no language is set or if there's a book language, try to select matching language
            if (currentASRService && currentASRVariant) {
                const service = asrServices.find(
                    (s) => s.service_id === currentASRService,
                );
                const variant = service?.variants?.find(
                    (v) => v.model_id === currentASRVariant,
                );
                
                if (variant) {
                    let selectedLanguage = currentASRLanguage;
                    
                    // If no current language is set, or if book language exists, try to match book language
                    if (!currentASRLanguage || bookLanguage) {
                        const matchedLanguage = selectLanguageForVariant(variant, bookLanguage);
                        if (matchedLanguage) {
                            selectedLanguage = matchedLanguage;
                        }
                    }
                    
                    // If still no language, use first available
                    if (!selectedLanguage) {
                        selectedLanguage = variant.languages?.[0]?.[0] || "";
                    }
                    
                    // Update if language changed
                    if (selectedLanguage !== currentASRLanguage) {
                        currentASRLanguage = selectedLanguage;
                        await updateASRPreference(
                            currentASRService,
                            currentASRVariant,
                            selectedLanguage,
                        );
                    }
                }
            }
        } catch (error) {
            console.error("Failed to load ASR preferences:", error);
        } finally {
            asrLoading = false;
        }
    }

    async function updateASRPreference(serviceId, variantId = "", language = "") {
        try {
            await api.config.setASRPreferences(serviceId, variantId, language);
            currentASRService = serviceId;
            currentASRVariant = variantId;
            currentASRLanguage = language;
        } catch (error) {
            console.error("Failed to update ASR preferences:", error);
        }
    }

    function handleASRServiceChange(event) {
        const serviceId = event.target.value;
        // Find the new service and auto-select its first variant and appropriate language
        const newService = asrServices.find((s) => s.service_id === serviceId);
        const firstVariant = newService?.variants?.[0];
        const firstVariantId = firstVariant?.model_id || "";
        const selectedLanguage = selectLanguageForVariant(firstVariant, bookLanguage);
        updateASRPreference(serviceId, firstVariantId, selectedLanguage);
    }

    function selectASRService(serviceId) {
        // Find the new service and auto-select its first variant and appropriate language
        const newService = asrServices.find((s) => s.service_id === serviceId);
        const firstVariant = newService?.variants?.[0];
        const firstVariantId = firstVariant?.model_id || "";
        const selectedLanguage = selectLanguageForVariant(firstVariant, bookLanguage);
        updateASRPreference(serviceId, firstVariantId, selectedLanguage);
        serviceDropdownOpen = false;
    }

    // Close dropdown when clicking outside
    function handleClickOutside(event) {
        if (serviceDropdownOpen && !event.target.closest(".custom-select")) {
            serviceDropdownOpen = false;
        }
    }

    function handleASRVariantChange(event) {
        const variantId = event.target.value;
        // Find the new variant and auto-select appropriate language
        const service = asrServices.find((s) => s.service_id === currentASRService);
        const variant = service?.variants?.find((v) => v.model_id === variantId);
        const selectedLanguage = selectLanguageForVariant(variant, bookLanguage);
        updateASRPreference(currentASRService, variantId, selectedLanguage);
    }

    function handleASRLanguageChange(event) {
        const language = event.target.value;
        updateASRPreference(currentASRService, currentASRVariant, language);
    }

    // ASR Options functions
    async function loadASROptions() {
        if ($session.step !== "configure_asr") return;

        try {
            asrOptionsLoading = true;
            const response = await api.session.getASROptions();
            asrOptions = response.options;
            if (!asrOptions.bias_words) {
                asrOptions.bias_words = DEFAULT_BIAS_WORDS;
            }
        } catch (error) {
            console.error("Failed to load ASR options:", error);
            // Use defaults if loading fails
            asrOptions = {trim: true, use_bias_words: false, bias_words: DEFAULT_BIAS_WORDS};
        } finally {
            asrOptionsLoading = false;
        }
    }

    async function updateASROptions(options) {
        if ($session.step !== "configure_asr") return;

        try {
            await api.session.updateASROptions(options);
            asrOptions = {...options};
        } catch (error) {
            console.error("Failed to update ASR options:", error);
        }
    }

    function handleTrimChange(event) {
        const trimValue = event.target.checked;
        updateASROptions({...asrOptions, trim: trimValue});
    }

    function handleUseBiasWordsChange(event) {
        const useBiasWords = event.target.checked;
        updateASROptions({...asrOptions, use_bias_words: useBiasWords});
    }

    function handleBiasWordsChange(event) {
        const biasWords = event.target.value;
        
        asrOptions = {...asrOptions, bias_words: biasWords};
        
        if (biasWordsDebounceTimer) {
            clearTimeout(biasWordsDebounceTimer);
        }
        
        biasWordsDebounceTimer = setTimeout(() => {
            updateASROptions({...asrOptions, bias_words: biasWords});
        }, 500);
    }

    function resetBiasWords() {
        updateASROptions({...asrOptions, bias_words: DEFAULT_BIAS_WORDS});
    }

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

    // Get current service info
    $: currentService = asrServices.find(
        (s) => s.service_id === currentASRService,
    );
    $: currentVariantInfo = currentService?.variants?.find(
        (v) => v.model_id === currentASRVariant,
    );
    $: availableLanguages = currentVariantInfo?.languages || [];
    $: currentServiceSupportsBiasWords = currentService?.supports_bias_words || false;

    onMount(async () => {
        await loadASRPreferences();
        await loadASROptions();
        await loadSegmentCount();
    });
</script>

<svelte:window on:click={handleClickOutside}/>

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
        <!-- ASR Settings Section -->
        <div class="settings-section">
            {#if asrLoading}
                <div class="asr-loading">
                    <div class="mini-spinner"></div>
                    Loading services...
                </div>
            {:else if asrServices.length > 0}
                <div class="asr-settings">
                    <!-- Controls Row -->
                    <div class="asr-controls-row">
                        <!-- Service Selection -->
                        <div class="asr-control-group">
                            <label for="asr-service">ASR Service</label>
                            <div class="custom-select" class:open={serviceDropdownOpen}>
                                <button
                                        type="button"
                                        class="custom-select-trigger"
                                        on:click={() => (serviceDropdownOpen = !serviceDropdownOpen)}
                                >
                                    {#if currentService}
                    <span class="service-option">
                      {currentService.name}
                        {#if currentService.uses_gpu}
                        <span class="performance-pill gpu"> GPU </span>
                      {/if}
                    </span>
                                    {:else}
                                        Select service...
                                    {/if}
                                    <span class="chevron" class:open={serviceDropdownOpen}>
                    <ChevronDown size="12"/>
                  </span>
                                </button>
                                {#if serviceDropdownOpen}
                                    <div class="custom-select-options">
                                        {#each asrServices as service}
                                            <button
                                                    type="button"
                                                    class="custom-select-option"
                                                    class:selected={service.service_id ===
                          currentASRService}
                                                    on:click={() => selectASRService(service.service_id)}
                                            >
                        <span class="service-option">
                          {service.name}
                            {#if service.uses_gpu}
                            <span class="performance-pill gpu"> GPU </span>
                          {/if}
                        </span>
                                            </button>
                                        {/each}
                                    </div>
                                {/if}
                            </div>
                        </div>

                        <!-- Variant Selection -->
                        {#if currentService?.variants?.length > 0}
                            <div class="asr-control-group">
                                <label for="asr-variant">Model Variant</label>
                                <select
                                        id="asr-variant"
                                        value={currentASRVariant}
                                        on:change={handleASRVariantChange}
                                        class="setting-select"
                                >
                                    {#each currentService.variants as variant}
                                        <option value={variant.model_id}>{variant.name}</option>
                                    {/each}
                                </select>
                            </div>
                        {/if}

                        <!-- Language Selection -->
                        {#if availableLanguages.length > 0}
                            <div class="asr-control-group">
                                <label for="asr-language" class="language-label">
                                    Language
                                    {#if currentASRLanguage === 'auto' && availableLanguages.length > 1}
                                        <div
                                            class="warning-icon"
                                            data-tooltip="Transcriptions tend to be faster and more accurate when the audio language is specified."
                                        >
                                            <TriangleAlert size="14"/>
                                        </div>
                                    {/if}
                                </label>
                                <select
                                        id="asr-language"
                                        value={currentASRLanguage}
                                        on:change={handleASRLanguageChange}
                                        class="setting-select"
                                >
                                    {#each availableLanguages as [code, name, nativeName]}
                                        <option value={code}>{name}</option>
                                    {/each}
                                </select>
                            </div>
                        {/if}
                    </div>

                    <div class="asr-descriptions">
                        {#if currentService}
                            <div class="description-item">
                                <strong>{currentService.name}:</strong>
                                {currentService.desc}
                            </div>
                        {/if}

                        {#if currentVariantInfo}
                            <div class="description-item">
                                <strong>{currentVariantInfo.name}:</strong>
                                {currentVariantInfo.desc}
                            </div>
                        {/if}
                    </div>
                </div>
            {:else}
                <div class="asr-error">
                    Failed to load ASR services. Please refresh the page.
                </div>
            {/if}
        </div>

        <div class="asr-options-container">
            <div class="asr-options-row">
                <label class="checkbox-label">
                    <input
                            type="checkbox"
                            bind:checked={asrOptions.trim}
                            on:change={handleTrimChange}
                            disabled={asrOptionsLoading}
                            class="asr-checkbox"
                    />
                    <span class="checkbox-text">
                        Trim segments
                        <div
                                class="help-icon"
                                data-tooltip="Trimming can help increase transcription speed and accuracy by removing excess speech from chapter audio segments. Disable this if transcriptions are frequently blank, nonsensical, or missing wanted portions of the chapter title."
                        >
                            <CircleQuestionMark size="14"/>
                        </div>
                    </span>
                </label>

                <label class="checkbox-label"
                       class:disabled={!currentServiceSupportsBiasWords}
                       data-tooltip={!currentServiceSupportsBiasWords ? "Not available for this ASR Service" : null}>
                    <input
                            type="checkbox"
                            bind:checked={asrOptions.use_bias_words}
                            on:change={handleUseBiasWordsChange}
                            disabled={asrOptionsLoading || !currentServiceSupportsBiasWords}
                            class="asr-checkbox"
                    />
                    <span class="checkbox-text">
                        Use Bias Words
                        {#if currentServiceSupportsBiasWords}
                            <div
                                    class="help-icon"
                                    data-tooltip="Bias words can help guide the ASR model toward more consistent results. For example, providing numerical digits helps the model produce chapter numbers as digits instead of words. Providing a list of uncommon words or names can help the model spell those correctly. You'll want to ensure that the bias words are in the same language as the audiobook."
                            >
                                <CircleQuestionMark size="14"/>
                            </div>
                        {/if}
                    </span>
                </label>
            </div>

            {#if asrOptions.use_bias_words && currentServiceSupportsBiasWords}
                <div class="bias-words-input-container">
                    <div class="input-with-reset">
                        <textarea
                                bind:value={asrOptions.bias_words}
                                on:input={handleBiasWordsChange}
                                disabled={asrOptionsLoading}
                                class="bias-words-input"
                                placeholder="Enter bias words..."
                                rows="4"
                        ></textarea>
                        <button
                                type="button"
                                class="reset-button"
                                on:click={resetBiasWords}
                                title="Reset to default"
                                disabled={asrOptionsLoading}
                        >
                            <RotateCcw size="12"/>
                        </button>
                    </div>
                </div>
            {/if}
        </div>
    </div>

    <div class="actions">
        <button
                class="btn btn-cancel"
                on:click={skipTranscription}
                disabled={loading}
        >
            {#if loading}
                <span class="btn-spinner"></span>
                Processing...
            {:else}
                Skip Transcription
            {/if}
        </button>

        <button
                class="btn btn-verify"
                on:click={proceedWithTranscription}
                disabled={loading || asrLoading}
        >
            {#if loading}
                <span class="btn-spinner"></span>
                Starting...
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

    .settings-section {
        background: var(--bg-secondary);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 1.5rem;
    }

    .asr-settings {
        display: flex;
        flex-direction: column;
        gap: 1.25rem;
    }

    .setting-select {
        padding: 0.5rem 0.75rem;
        border: 1px solid var(--border-color);
        border-radius: 6px;
        background: var(--bg-primary);
        color: var(--text-primary);
        font-size: 0.9rem;
        transition: border-color 0.2s ease;
    }

    .setting-select:focus {
        outline: none;
        border-color: var(--primary-color);
    }

    .performance-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.25rem;
        padding: 0.2rem 0.4rem;
        border-radius: 12px;
        font-size: 0.7rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.025em;
        margin-left: 0.5rem;
    }

    .performance-pill.gpu {
        background: rgba(34, 197, 94, 0.1);
        color: rgb(34, 197, 94);
        border: 1px solid rgba(34, 197, 94, 0.2);
    }

    .custom-select {
        position: relative;
        width: 100%;
    }

    .custom-select-trigger {
        width: 100%;
        min-height: 2.25rem;
        padding: 0.4rem 0 0.4rem 1rem;
        border: 1px solid var(--border-color);
        border-radius: 6px;
        background: var(--bg-primary);
        color: var(--text-primary);
        font-size: 0.9rem;
        text-align: left;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: space-between;
        transition: border-color 0.2s ease;
    }

    .custom-select-trigger:hover {
        border-color: var(--primary-color);
    }

    .custom-select.open .custom-select-trigger {
        border-color: var(--primary-color);
    }

    .custom-select-options {
        position: absolute;
        top: 100%;
        left: 0;
        right: 0;
        background: var(--bg-primary);
        border: 1px solid var(--border-color);
        border-radius: 6px;
        z-index: 1000;
        max-height: 200px;
        overflow-y: auto;
        margin-top: 2px;
    }

    .custom-select-option {
        width: 100%;
        padding: 0.5rem 0.75rem;
        border: none;
        background: none;
        text-align: left;
        cursor: pointer;
        font-size: 0.9rem;
        color: var(--text-primary);
        transition: background-color 0.2s ease;
        display: flex;
        align-items: center;
    }

    .custom-select-option:hover {
        background: rgba(0, 123, 255, 0.15);
    }

    .custom-select-option.selected {
        background: rgba(0, 123, 255, 0.3);
        color: white;
    }

    .custom-select-option.selected .performance-pill.gpu {
        background: rgba(255, 255, 255, 0.2);
        color: white;
        border-color: rgba(255, 255, 255, 0.3);
    }

    .service-option {
        display: flex;
        align-items: center;
        flex: 1;
    }

    .custom-select-trigger .chevron {
        transition: transform 0.2s ease;
        display: flex;
        align-items: center;
        margin-left: 0.5rem;
    }

    .custom-select-trigger .chevron.open {
        transform: rotate(180deg);
    }

    .asr-loading,
    .asr-error {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 1rem;
        border-radius: 6px;
        font-size: 0.9rem;
    }

    .asr-loading {
        background: var(--bg-tertiary);
        color: var(--text-secondary);
    }

    .asr-error {
        background: rgba(239, 68, 68, 0.1);
        color: rgb(239, 68, 68);
        border: 1px solid rgba(239, 68, 68, 0.2);
    }

    /* ASR Controls Layout */
    .asr-controls-row {
        display: flex;
        gap: 1rem;
        align-items: end;
    }

    .asr-control-group {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
        flex: 1;
    }

    .asr-control-group label {
        font-weight: 500;
        color: var(--text-primary);
        font-size: 0.9rem;
        min-height: 1.2rem;
    }

    .language-label {
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    .warning-icon {
        border: none;
        background: transparent;
        color: var(--warning);
        padding: 2px;
        border-radius: 50%;
        transition: all 0.2s ease;
        position: relative;
        cursor: help;
        display: flex;
    }

    .warning-icon:hover {
        background: var(--bg-tertiary);
    }

    /* Warning tooltip on hover */
    .warning-icon[data-tooltip]:hover::after {
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

    /* Warning tooltip arrow */
    .warning-icon[data-tooltip]:hover::before {
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

    .asr-descriptions {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
    }

    .description-item {
        font-size: 0.85rem;
        line-height: 1.4;
        color: var(--text-secondary);
        white-space: pre-line;
    }

    .description-item strong {
        color: var(--text-primary);
    }

    .asr-options-container {
        margin-top: 1rem;
    }

    .asr-options-row {
        display: flex;
        gap: 2rem;
        align-items: center;
        justify-content: center;
        margin-bottom: 1rem;
    }

    /* Checkbox styles for ASR options */
    .checkbox-label {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        cursor: pointer;
        font-size: 0.9rem;
        color: var(--text-primary);
        margin: 0;
    }

    .asr-checkbox {
        cursor: pointer;
        margin: 0;
    }

    .checkbox-text {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-weight: 500;
    }

    .checkbox-label:hover .checkbox-text {
        color: var(--primary-color);
    }

    .asr-checkbox:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    .checkbox-label:has(.asr-checkbox:disabled) {
        opacity: 0.5;
        cursor: not-allowed;
    }

    .checkbox-label:has(.asr-checkbox:disabled) .checkbox-text {
        color: var(--text-secondary);
    }

    .checkbox-label.disabled {
        position: relative;
    }

    .checkbox-label.disabled:hover::after {
        content: attr(data-tooltip);
        position: absolute;
        top: -40px;
        left: 50%;
        transform: translateX(-50%);
        padding: 8px 12px;
        background: var(--bg-primary);
        color: var(--text-primary);
        border: 1px solid var(--border-color);
        border-radius: 6px;
        font-size: 0.875rem;
        line-height: 1.4;
        white-space: nowrap;
        z-index: 1000;
        animation: tooltipFadeIn 0.2s ease-out;
        pointer-events: none;
    }

    .checkbox-label.disabled:hover::before {
        content: "";
        position: absolute;
        top: -3px;
        left: 50%;
        transform: translateX(-50%);
        border: 6px solid transparent;
        border-top-color: var(--border-color);
        z-index: 1001;
        pointer-events: none;
    }

    .checkbox-label:not(.disabled):hover::after,
    .checkbox-label:not(.disabled):hover::before {
        display: none;
    }

    .bias-words-input-container {
        margin-top: 1rem;
    }

    .input-with-reset {
        position: relative;
        display: flex;
        align-items: flex-start;
    }

    .bias-words-input {
        flex: 1;
        padding: 0.5rem 2.5rem 0.5rem 0.75rem;
        border: 1px solid var(--border-color);
        border-radius: 6px;
        background: var(--bg-primary);
        color: var(--text-primary);
        font-size: 0.9rem;
        font-family: inherit;
        resize: vertical;
        min-height: 6rem;
        line-height: 1.4;
        transition: border-color 0.2s ease;
    }

    .bias-words-input:focus {
        outline: none;
        border-color: var(--primary-color);
    }

    .bias-words-input:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    .reset-button {
        position: absolute;
        right: 0.5rem;
        top: 0.5rem;
        width: 1.5rem;
        height: 1.5rem;
        border: none;
        background: transparent;
        color: var(--text-secondary);
        cursor: pointer;
        border-radius: 3px;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.2s ease;
    }

    .reset-button:hover {
        background: var(--bg-tertiary);
        color: var(--primary-color);
    }

    .reset-button:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    .help-icon {
        border: none;
        background: transparent;
        color: var(--text-secondary);
        padding: 2px;
        border-radius: 50%;
        transition: all 0.2s ease;
        position: relative;
        cursor: help;
        display: flex;
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

    .mini-spinner {
        width: 14px;
        height: 14px;
        border: 2px solid transparent;
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }

    @keyframes spin {
        0% {
            transform: rotate(0deg);
        }
        100% {
            transform: rotate(360deg);
        }
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

    /* Responsive design updates */
    @media (max-width: 768px) {
        .asr-controls-row {
            flex-direction: column;
            gap: 0.75rem;
            align-items: stretch;
        }

        .asr-descriptions {
            font-size: 0.8rem;
            padding: 0.6rem;
        }

        .actions {
            flex-direction: column;
            align-items: stretch;
        }
    }
</style>
