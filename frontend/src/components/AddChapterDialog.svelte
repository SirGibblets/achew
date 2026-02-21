<script>
    import {createEventDispatcher} from "svelte";
    import {api, handleApiError} from "../utils/api.js";
    import {audio, currentSegmentId, isPlaying} from "../stores/audio.js";
    
    // Icons
    import ArrowDown from "@lucide/svelte/icons/arrow-down";
    import ArrowUp from "@lucide/svelte/icons/arrow-up";
    import AudioLines from "@lucide/svelte/icons/audio-lines";
    import ChevronDown from "@lucide/svelte/icons/chevron-down";
    import ChevronUp from "@lucide/svelte/icons/chevron-up";
    import MoveHorizontal from "@lucide/svelte/icons/move-horizontal";
    import Pause from "@lucide/svelte/icons/pause";
    import Play from "@lucide/svelte/icons/play";
    import ScanSearch from "@lucide/svelte/icons/scan-search";
    import X from "@lucide/svelte/icons/x";

    let {
        isOpen = $bindable(false),
        chapterId = null,
        defaultTab = null,
        editorSettings = { show_formatted_time: true }
    } = $props();

    const dispatch = createEventDispatcher();

    let loading = $state(false);
    let scanning = $state(false);
    let error = $state(null);
    let addOptions = $state(null);
    let activeTab = $state("timestamp");
    let selectedTimestamp = $state(null);
    let selectedTitle = $state("");
    let manualTimestamp = $state("");
    let originalTimestamp = $state(null);
    let sortBy = $state("gap");
    let sortOrder = $state("desc");

    function formatTimestamp(seconds) {
        if (!editorSettings.show_formatted_time) {
            return seconds.toFixed(2);
        }

        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);

        if (hours > 0) {
            return `${hours}:${minutes.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
        } else {
            return `${minutes}:${secs.toString().padStart(2, "0")}`;
        }
    }

    function parseTimestamp(input) {
        if (!editorSettings.show_formatted_time) {
            return parseFloat(input) || 0;
        }

        const parts = input.split(':').map(p => parseInt(p, 10));
        if (parts.length === 2) {
            return parts[0] * 60 + parts[1];
        } else if (parts.length === 3) {
            return parts[0] * 3600 + parts[1] * 60 + parts[2];
        }
        return 0;
    }

    function isValidTimestamp(timestamp) {
        if (!addOptions) return false;
        const tolerance = 0.1;
        return timestamp >= (addOptions.min_timestamp - tolerance) &&
               timestamp <= (addOptions.max_timestamp + tolerance);
    }

    function getAvailableTabs() {
        if (!addOptions) return ["timestamp"];

        const tabs = ["timestamp", "detected_cue"];

        if (addOptions.existing_cues) {
            Object.keys(addOptions.existing_cues).forEach(sourceName => {
                if (addOptions.existing_cues[sourceName].length > 0) {
                    tabs.push(sourceName);
                }
            });
        }
        
        if (addOptions.deleted && addOptions.deleted.length > 0) {
            tabs.push("deleted");
        }
        
        return tabs;
    }

    function getSortedDetectedCues() {
        if (!addOptions?.detected_cues) return [];
        
        const cues = [...addOptions.detected_cues];
        cues.sort((a, b) => {
            if (sortBy === "gap") {
                return sortOrder === "desc" ? b.gap - a.gap : a.gap - b.gap;
            } else {
                return sortOrder === "desc" ? b.timestamp - a.timestamp : a.timestamp - b.timestamp;
            }
        });
        return cues;
    }

    function selectTab(tab) {
        activeTab = tab;
        selectedTimestamp = null;
        selectedTitle = "";
        
        if (tab === "timestamp" && manualTimestamp && addOptions) {
            const parsed = parseTimestamp(manualTimestamp);
            if (isValidTimestamp(parsed)) {
                selectedTimestamp = parsed;
            }
        }
    }

    function selectOption(timestamp, title = "") {
        selectedTimestamp = timestamp;
        selectedTitle = title;
    }

    function handleTimestampInput(event) {
        manualTimestamp = event.target.value;
        const parsed = parseTimestamp(manualTimestamp);
        if (isValidTimestamp(parsed)) {
            selectedTimestamp = parsed;
        } else {
            selectedTimestamp = null;
        }
        originalTimestamp = null;
    }

    function adjustTimestamp(delta) {
        const current = originalTimestamp !== null ? originalTimestamp : parseTimestamp(manualTimestamp);
        const newValue = Math.max(addOptions.min_timestamp, Math.min(addOptions.max_timestamp, current + delta));
        manualTimestamp = formatTimestamp(newValue);
        selectedTimestamp = newValue;
        originalTimestamp = newValue;
    }

    function handleTimestampKeydown(event) {
        if (event.key === "ArrowUp") {
            event.preventDefault();
            adjustTimestamp(1);
        } else if (event.key === "ArrowDown") {
            event.preventDefault();
            adjustTimestamp(-1);
        }
    }

    function toggleSort(column) {
        if (sortBy === column) {
            sortOrder = sortOrder === "asc" ? "desc" : "asc";
        } else {
            sortBy = column;
            sortOrder = column === "gap" ? "desc" : "asc";
        }
    }

    function handleRowClick(event, timestamp, title = "") {
        if (event.target.tagName === 'BUTTON' || event.target.tagName === 'INPUT') {
            return;
        }
        selectOption(timestamp, title);
    }

    function handleRowKeydown(event, timestamp, title = "") {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            selectOption(timestamp, title);
        }
    }

    async function previewAudio(timestamp) {
        try {
            if ($currentSegmentId === `preview-${timestamp}` && $isPlaying) {
                audio.stop();
            } else {
                await audio.play(`preview-${timestamp}`, timestamp);
            }
        } catch (err) {
            console.error("Failed to preview audio:", err);
        }
    }

    async function loadAddOptions() {
        if (chapterId === null) return;
        
        loading = true;
        error = null;
        
        try {
            addOptions = await api.chapters.getAddOptions(chapterId);
            
            if (addOptions) {
                originalTimestamp = addOptions.min_timestamp;
                manualTimestamp = formatTimestamp(addOptions.min_timestamp);
                selectedTimestamp = addOptions.min_timestamp;

                if (defaultTab && getAvailableTabs().includes(defaultTab)) {
                    activeTab = defaultTab;
                } else if (addOptions.detected_cues && addOptions.detected_cues.length > 0) {
                    activeTab = "detected_cue";
                } else {
                    activeTab = "timestamp";
                }
            }
        } catch (err) {
            error = handleApiError(err);
        } finally {
            loading = false;
        }
    }

    // Prevent background scrolling when modal is open
    $effect(() => {
        if (isOpen) {
            const originalOverflow = document.body.style.overflow;
            const originalPosition = document.body.style.position;
            const originalTop = document.body.style.top;
            const scrollY = window.scrollY;
            
            document.body.style.overflow = 'hidden';
            document.body.style.position = 'fixed';
            document.body.style.top = `-${scrollY}px`;
            document.body.style.width = '100%';
            
            return () => {
                document.body.style.overflow = originalOverflow;
                document.body.style.position = originalPosition;
                document.body.style.top = originalTop;
                document.body.style.width = '';
                window.scrollTo(0, scrollY);
            };
        }
    });

    // Handle dialog open/close
    $effect(() => {
        if (isOpen && chapterId != null) {
            loadAddOptions();
        } else if (isOpen === false) {
            if ($isPlaying && $currentSegmentId && $currentSegmentId.startsWith('preview-')) {
                audio.stop();
            }

            addOptions = null;
            selectedTimestamp = null;
            selectedTitle = "";
            manualTimestamp = "";
            originalTimestamp = null;
            activeTab = "timestamp";
            error = null;
            scanning = false;
        }
    });

    async function startPartialScan(scanType) {
        scanning = true;
        error = null;
        try {
            await api.chapters.startPartialScan(chapterId, scanType);
            close(); // Pipeline takes over; dialog will re-open when scan completes
        } catch (err) {
            error = handleApiError(err);
            scanning = false;
        }
    }

    async function handleConfirm() {
        if (!selectedTimestamp) return;
        
        try {
            await api.chapters.add({
                timestamp: selectedTimestamp,
                title: selectedTitle
            });
            
            dispatch('confirm', {
                timestamp: selectedTimestamp,
                title: selectedTitle
            });
            
            close();
        } catch (err) {
            error = handleApiError(err);
        }
    }

    function handleCancel() {
        dispatch('cancel');
        close();
    }

    function close() {
        if ($isPlaying) {
            audio.stop();
        }
        isOpen = false;
    }

    function handleBackdropClick(event) {
        if (event.target === event.currentTarget) {
            handleCancel();
        }
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
                    <h3>Add Chapter from...</h3>
                    <button class="close-button" onclick={handleCancel} aria-label="Close">
                        <X size="20"/>
                    </button>
                </div>

                <div class="modal-body">
                    {#if error}
                        <div class="alert alert-danger">
                            {error}
                        </div>
                    {/if}

                    {#if loading}
                        <div class="loading-state">
                            <div class="spinner"></div>
                            <p>Loading add options...</p>
                        </div>
                    {:else if addOptions}
                        <!-- Tab Navigation -->
                        <div class="tabs">
                            {#each getAvailableTabs() as tab}
                                <button 
                                    class="tab-button" 
                                    class:active={activeTab === tab}
                                    onclick={() => selectTab(tab)}
                                >
                                    {#if tab === "timestamp"}
                                        Timestamp
                                    {:else if tab === "detected_cue"}
                                        Detected Cues
                                    {:else if tab === "deleted"}
                                        Deleted
                                    {:else}
                                        {tab}
                                    {/if}
                                </button>
                            {/each}
                        </div>

                        <!-- Tab Content -->
                        <div class="tab-content">
                            {#if activeTab === "timestamp"}
                                <div class="timestamp-tab-wrapper">
                                    <div class="timestamp-input-section">
                                        <div class="timestamp-input-group">
                                        <input
                                            id="manual-timestamp"
                                            type="text"
                                            bind:value={manualTimestamp}
                                            oninput={handleTimestampInput}
                                            onkeydown={handleTimestampKeydown}
                                            class="timestamp-input"
                                            placeholder={editorSettings.show_formatted_time ? "mm:ss" : "seconds"}
                                        />
                                        <div class="timestamp-controls">
                                            <button 
                                                class="timestamp-adjust"
                                                onclick={() => adjustTimestamp(1)}
                                                title="Increase by 1 second"
                                            >
                                                <ChevronUp size="16"/>
                                            </button>
                                            <button 
                                                class="timestamp-adjust"
                                                onclick={() => adjustTimestamp(-1)}
                                                title="Decrease by 1 second"
                                            >
                                                <ChevronDown size="16"/>
                                            </button>
                                        </div>
                                        {#if selectedTimestamp}
                                            <button
                                                class="preview-button"
                                                class:playing={$currentSegmentId === `preview-${selectedTimestamp}` && $isPlaying}
                                                onclick={() => { selectOption(selectedTimestamp); previewAudio(selectedTimestamp); }}
                                                title="Preview audio"
                                            >
                                                {#if $currentSegmentId === `preview-${selectedTimestamp}` && $isPlaying}
                                                    <Pause size="16"/>
                                                {:else}
                                                    <Play size="16"/>
                                                {/if}
                                            </button>
                                        {/if}
                                    </div>
                                    {#if manualTimestamp && !isValidTimestamp(parseTimestamp(manualTimestamp))}
                                        <div class="validation-error">
                                            Timestamp must be between {formatTimestamp(addOptions.min_timestamp)} and {formatTimestamp(addOptions.max_timestamp)}
                                        </div>
                                    {/if}
                                    </div>
                                </div>
                            {:else if activeTab === "detected_cue"}
                                <div class="cue-tab-wrapper">
                                    <div class="cue-list-scroll">
                                    {#if getSortedDetectedCues().length > 0}
                                        <div class="cue-table-section">
                                            <table class="cue-table">
                                                <thead>
                                                    <tr>
                                                        <th width="1"></th>
                                                        <th width="1"></th>
                                                        <th width="1" class="sortable" onclick={() => toggleSort("gap")}>
                                                            Gap
                                                            {#if sortBy === "gap"}
                                                                {#if sortOrder === "asc"}
                                                                    <ArrowUp size="14" class="sort-icon"/>
                                                                {:else}
                                                                    <ArrowDown size="14" class="sort-icon"/>
                                                                {/if}
                                                            {/if}
                                                        </th>
                                                        <th class="sortable" onclick={() => toggleSort("timestamp")}>
                                                            Timestamp
                                                            {#if sortBy === "timestamp"}
                                                                {#if sortOrder === "asc"}
                                                                    <ArrowUp size="14" class="sort-icon"/>
                                                                {:else}
                                                                    <ArrowDown size="14" class="sort-icon"/>
                                                                {/if}
                                                            {/if}
                                                        </th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {#each getSortedDetectedCues() as cue}
                                                        <tr
                                                            class="cue-row clickable-row"
                                                            class:selected={selectedTimestamp === cue.timestamp}
                                                            onclick={(e) => handleRowClick(e, cue.timestamp)}
                                                            onkeydown={(e) => handleRowKeydown(e, cue.timestamp)}
                                                            tabindex="0"
                                                            role="button"
                                                            aria-label="Select detected cue at {formatTimestamp(cue.timestamp)} with {cue.gap.toFixed(1)}s gap"
                                                        >
                                                            <td class="radio-cell">
                                                                <input
                                                                    type="radio"
                                                                    name="detected-cue"
                                                                    checked={selectedTimestamp === cue.timestamp}
                                                                    onchange={() => selectOption(cue.timestamp)}
                                                                />
                                                            </td>
                                                            <td class="preview-cell">
                                                                <button
                                                                    class="preview-button"
                                                                    class:playing={$currentSegmentId === `preview-${cue.timestamp}` && $isPlaying}
                                                                    onclick={() => { selectOption(cue.timestamp); previewAudio(cue.timestamp); }}
                                                                    title="Preview audio"
                                                                >
                                                                    {#if $currentSegmentId === `preview-${cue.timestamp}` && $isPlaying}
                                                                        <Pause size="16"/>
                                                                    {:else}
                                                                        <Play size="16"/>
                                                                    {/if}
                                                                </button>
                                                            </td>
                                                            <td class="gap-cell">{cue.gap.toFixed(1)}s</td>
                                                            <td class="timestamp-cell">{formatTimestamp(cue.timestamp)}</td>
                                                        </tr>
                                                    {/each}
                                                </tbody>
                                            </table>
                                        </div>
                                    {:else}
                                        <div class="empty-cues-state">
                                            {#if addOptions.allow_normal_scan && addOptions.allow_vad_scan}
                                                This region has not been scanned for cues yet.
                                            {:else if addOptions.allow_vad_scan}
                                                No cues found in this region. Try clicking "Detect Cues [Dramatized]".
                                            {:else}
                                                No cues found in this region.
                                            {/if}
                                        </div>
                                    {/if}
                                    </div>

                                    {#if addOptions.allow_normal_scan || addOptions.allow_vad_scan}
                                        <div class="scan-actions">
                                            {#if addOptions.allow_normal_scan}
                                                <button
                                                    class="btn btn-secondary btn-scan"
                                                    onclick={() => startPartialScan('normal')}
                                                    disabled={scanning}
                                                    title="Scan this region for chapter cues using silence detection"
                                                >
                                                    <ScanSearch size="16"/>
                                                    Detect {getSortedDetectedCues().length > 0 ? 'Additional ' : ''}Cues
                                                </button>
                                            {/if}
                                            {#if addOptions.allow_vad_scan}
                                                <button
                                                    class="btn btn-secondary btn-scan"
                                                    onclick={() => startPartialScan('vad')}
                                                    disabled={scanning}
                                                    title="Scan this region for chapter cues using voice activity detection (for dramatized audiobooks)"
                                                >
                                                    <AudioLines size="16"/>
                                                    Detect {getSortedDetectedCues().length > 0 ? 'Additional ' : ''}Cues [Dramatized]
                                                </button>
                                            {/if}
                                        </div>
                                    {/if}
                                </div>
                            {:else if activeTab === "deleted"}
                                <div class="cue-table-section">
                                    <table class="cue-table">
                                        <thead>
                                            <tr>
                                                <th width="1"></th>
                                                <th width="1"></th>
                                                <th width="1">Timestamp</th>
                                                <th>Title</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {#each addOptions.deleted as deletedChapter}
                                                <tr
                                                    class="cue-row clickable-row"
                                                    class:selected={selectedTimestamp === deletedChapter.timestamp}
                                                    onclick={(e) => handleRowClick(e, deletedChapter.timestamp, deletedChapter.title)}
                                                    onkeydown={(e) => handleRowKeydown(e, deletedChapter.timestamp, deletedChapter.title)}
                                                    tabindex="0"
                                                    role="button"
                                                    aria-label="Select deleted chapter '{deletedChapter.title}' at {formatTimestamp(deletedChapter.timestamp)}"
                                                >
                                                    <td class="radio-cell">
                                                        <input
                                                            type="radio"
                                                            name="deleted-chapter"
                                                            checked={selectedTimestamp === deletedChapter.timestamp}
                                                            onchange={() => selectOption(deletedChapter.timestamp, deletedChapter.title)}
                                                        />
                                                    </td>
                                                    <td class="preview-cell">
                                                        <button
                                                            class="preview-button"
                                                            class:playing={$currentSegmentId === `preview-${deletedChapter.timestamp}` && $isPlaying}
                                                            onclick={() => { selectOption(deletedChapter.timestamp, deletedChapter.title); previewAudio(deletedChapter.timestamp); }}
                                                            title="Preview audio"
                                                        >
                                                            {#if $currentSegmentId === `preview-${deletedChapter.timestamp}` && $isPlaying}
                                                                <Pause size="16"/>
                                                            {:else}
                                                                <Play size="16"/>
                                                            {/if}
                                                        </button>
                                                    </td>
                                                    <td class="timestamp-cell">{formatTimestamp(deletedChapter.timestamp)}</td>
                                                    <td class="title-cell">{deletedChapter.title}</td>
                                                </tr>
                                            {/each}
                                        </tbody>
                                    </table>
                                </div>
                            {:else if addOptions.existing_cues && addOptions.existing_cues[activeTab]}
                                <div class="cue-table-section">
                                    <table class="cue-table">
                                        <thead>
                                            <tr>
                                                <th width="1"></th>
                                                <th width="1"></th>
                                                <th width="1">Timestamp</th>
                                                <th>Title</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {#each addOptions.existing_cues[activeTab] as existingCue}
                                                <tr
                                                    class="cue-row clickable-row"
                                                    class:selected={selectedTimestamp === existingCue.timestamp}
                                                    onclick={(e) => handleRowClick(e, existingCue.timestamp, existingCue.title)}
                                                    onkeydown={(e) => handleRowKeydown(e, existingCue.timestamp, existingCue.title)}
                                                    tabindex="0"
                                                    role="button"
                                                    aria-label="Select existing cue '{existingCue.title}' at {formatTimestamp(existingCue.timestamp)}"
                                                >
                                                    <td class="radio-cell">
                                                        <input
                                                            type="radio"
                                                            name="existing-cue"
                                                            checked={selectedTimestamp === existingCue.timestamp}
                                                            onchange={() => selectOption(existingCue.timestamp, existingCue.title)}
                                                        />
                                                    </td>
                                                    <td class="preview-cell">
                                                        <button
                                                            class="preview-button"
                                                            class:playing={$currentSegmentId === `preview-${existingCue.timestamp}` && $isPlaying}
                                                            onclick={() => { selectOption(existingCue.timestamp, existingCue.title); previewAudio(existingCue.timestamp); }}
                                                            title="Preview audio"
                                                        >
                                                            {#if $currentSegmentId === `preview-${existingCue.timestamp}` && $isPlaying}
                                                                <Pause size="16"/>
                                                            {:else}
                                                                <Play size="16"/>
                                                            {/if}
                                                        </button>
                                                    </td>
                                                    <td class="timestamp-cell">{formatTimestamp(existingCue.timestamp)}</td>
                                                    <td class="title-cell">{existingCue.title}</td>
                                                </tr>
                                            {/each}
                                        </tbody>
                                    </table>
                                </div>
                            {/if}
                        </div>
                    {/if}
                </div>

                <div class="modal-footer">
                    {#if addOptions}
                        <div class="time-boundaries">
                            <span>{formatTimestamp(addOptions.min_timestamp)}</span>
                            <MoveHorizontal size="16"/>
                            <span>{formatTimestamp(addOptions.max_timestamp)}</span>
                        </div>
                    {/if}
                    <button class="btn btn-secondary" onclick={handleCancel}>
                        Cancel
                    </button>
                    <button 
                        class="btn btn-primary" 
                        onclick={handleConfirm}
                        disabled={!selectedTimestamp}
                    >
                        Add chapter at {selectedTimestamp ? formatTimestamp(selectedTimestamp) : ""}
                    </button>
                </div>
            </div>
        </div>
    </div>
{/if}

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
        max-width: 600px;
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
    }

    .modal-footer {
        display: flex;
        justify-content: flex-end;
        gap: 0.75rem;
        padding: 1rem;
        border-top: 1px solid var(--border-color);
    }

    .loading-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 2rem;
        text-align: center;
    }

    .spinner {
        width: 2rem;
        height: 2rem;
        border: 2px solid var(--border-color);
        border-top: 2px solid var(--primary);
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin-bottom: 1rem;
    }

    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }

    .tabs {
        display: flex;
        padding: 0 1rem;
        overflow: auto;
    }

    .tab-button {
        background: none;
        border: none;
        padding: 0.75rem 1rem;
        color: var(--text-secondary);
        cursor: pointer;
        border-bottom: 2px solid transparent;
        white-space: nowrap;
        font-size: 0.875rem;
        font-weight: 500;
    }

    .tab-button:hover {
        color: var(--text-primary);
        background: var(--hover-bg);
    }

    .tab-button.active {
        color: var(--primary);
        border-bottom-color: var(--primary);
    }

    .tab-content {
        min-height: 200px;
        max-height: 400px;
        overflow-y: auto;
    }

    .time-boundaries {
        flex: 1;
        display: flex;
        align-items: center;
        justify-content: start;
        gap: 0.5rem;
        margin-left: 0.5rem;
        color: var(--text-secondary);
        font-size: 0.9rem;
    }

    .timestamp-tab-wrapper {
        display: flex;
        align-items: center;
        justify-content: center;
        height: 100%;
        min-height: 200px;
    }

    .timestamp-input-section {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 0.75rem;
    }

    .timestamp-input-group {
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    .timestamp-input {
        padding: 0.5rem;
        border: 1px solid var(--border-color);
        border-radius: 0.25rem;
        background: var(--bg-secondary);
        color: var(--text-primary);
        font-family: monospace;
    }

    .timestamp-input:focus {
        border-color: var(--primary);
        outline: none;
    }

    .timestamp-controls {
        display: flex;
        flex-direction: column;
    }

    .timestamp-adjust {
        background: var(--bg-secondary);
        border: 1px solid var(--border-color);
        color: var(--text-secondary);
        cursor: pointer;
        padding: 0.25rem;
        display: flex;
        align-items: center;
        justify-content: center;
        width: 2rem;
        height: 1rem;
    }

    .timestamp-adjust:hover {
        background: var(--hover-bg);
        color: var(--text-primary);
    }

    .timestamp-adjust:first-child {
        border-top-left-radius: 0.25rem;
        border-top-right-radius: 0.25rem;
        border-bottom: none;
    }

    .timestamp-adjust:last-child {
        border-bottom-left-radius: 0.25rem;
        border-bottom-right-radius: 0.25rem;
    }

    .preview-button {
        width: 2rem;
        height: 2rem;
        border-radius: 50%;
        border: none;
        background-color: transparent;
        color: var(--primary-contrast);
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.75rem;
        transition: all 0.2s ease;
    }

    .preview-button:hover {
        color: white;
        background-color: var(--primary-hover);
        transform: scale(1.1);
    }

    .preview-button.playing {
        color: white;
        background-color: var(--primary-color);
    }

    .validation-error {
        color: var(--danger);
        font-size: 0.875rem;
    }

    .cue-tab-wrapper {
        display: flex;
        flex-direction: column;
        min-height: 200px;
        max-height: 400px;
        overflow: hidden;
    }

    .cue-list-scroll {
        flex: 1;
        overflow-y: auto;
        min-height: 0;
        display: flex;
        flex-direction: column;
    }

    .empty-cues-state {
        flex: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 1rem;
        color: var(--text-secondary);
        font-size: 0.875rem;
    }

    .scan-actions {
        display: flex;
        justify-content: center;
        gap: 0.75rem;
        padding: 0.75rem 1rem;
        flex-wrap: wrap;
    }

    .btn-secondary.btn-scan {
        border-color: var(--primary);
    }

    .btn-scan :global(svg) {
        color: var(--primary);
    }

    .cue-table-section {
        overflow-x: auto;
    }

    .cue-table {
        width: 100%;
        border-collapse: collapse;
        margin: 0 auto;
    }

    .cue-table th,
    .cue-table td {
        padding: 0.75rem;
        text-align: left;
        border-bottom: 1px solid var(--border-color);
    }

    .cue-table th {
        background: var(--bg-secondary);
        font-weight: 600;
        color: var(--text-primary);
    }

    .cue-table th.sortable {
        cursor: pointer;
        user-select: none;
        white-space: nowrap;
    }

    .cue-table th.sortable:hover {
        background: var(--hover-bg);
    }

    .radio-cell {
        padding: 0.75rem 0.75rem 0.75rem 1.5rem !important;
        accent-color: var(--primary);
    }

    .preview-cell {
        padding: 0.75rem 0rem !important;
    }

    .cue-row {
        transition: background-color 0.1s ease;
    }

    .cue-row:hover {
        background: var(--hover-bg);
    }

    .cue-row.selected {
        background: var(--primary-light);
    }

    .clickable-row {
        cursor: pointer;
    }

    .clickable-row:focus {
        outline: 2px solid var(--primary);
        outline-offset: -2px;
    }

    .clickable-row:hover {
        background: var(--hover-bg);
    }

    .clickable-row.selected:hover {
        background: var(--primary-light);
    }

    .gap-cell,
    .timestamp-cell {
        font-family: monospace;
        font-size: 0.875rem;
    }

    .title-cell {
        color: var(--text-primary);
        max-width: 200px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .alert {
        padding: 0.75rem;
        border-radius: 0.25rem;
        margin-bottom: 1rem;
    }

    .alert-danger {
        background: var(--danger-light);
        color: var(--danger-dark);
        border: 1px solid var(--danger);
    }

    .btn {
        padding: 0.5rem 1rem;
        border: 1px solid transparent;
        border-radius: 0.25rem;
        cursor: pointer;
        font-size: 0.875rem;
        font-weight: 500;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 0.5rem;
        transition: all 0.2s ease;
    }

    .btn:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }

    .btn-primary {
        background: var(--primary);
        color: white;
    }

    .btn-primary:hover:not(:disabled) {
        background: var(--primary-hover);
    }

    .btn-secondary {
        background: var(--bg-secondary);
        color: var(--text-primary);
        border-color: var(--border-color);
    }

    .btn-secondary:hover:not(:disabled) {
        background: var(--hover-bg);
    }

    @media (max-width: 768px) {
        .modal-dialog {
            width: 95%;
            max-height: 95vh;
        }

        .modal-header,
        .modal-body,
        .modal-footer {
            padding: 1rem;
        }

        .timestamp-input-group {
            flex-direction: column;
            align-items: stretch;
        }

        .timestamp-controls {
            flex-direction: row;
            width: 100%;
        }

        .timestamp-adjust {
            flex: 1;
            height: 2rem;
        }

        .timestamp-adjust:first-child {
            border-radius: 0.25rem 0 0 0.25rem;
            border-right: none;
            border-bottom: 1px solid var(--border-color);
        }

        .timestamp-adjust:last-child {
            border-radius: 0 0.25rem 0.25rem 0;
        }

        .tabs {
            overflow-x: scroll;
        }

        .cue-table {
            font-size: 0.75rem;
        }

        .cue-table th,
        .cue-table td {
            padding: 0.5rem;
        }
    }
</style>