<script>
    import {createEventDispatcher} from "svelte";
    import {api, handleApiError} from "../utils/api.js";
    import {audio, currentSegmentId, isPlaying} from "../stores/audio.js";
    import {chapters, session} from "../stores/session.js";

    // Icons
    import CircleHelp from "@lucide/svelte/icons/circle-help";
    import Minus from "@lucide/svelte/icons/minus";
    import Pause from "@lucide/svelte/icons/pause";
    import Play from "@lucide/svelte/icons/play";
    import Plus from "@lucide/svelte/icons/plus";
    import X from "@lucide/svelte/icons/x";

    let {
        isOpen = $bindable(false),
    } = $props();

    const dispatch = createEventDispatcher();

    let applyTo = $state("selected");
    let offsetValue = $state("0");
    let driftEnabled = $state(false);
    let driftValue = $state("0");
    let loading = $state(false);
    let error = $state(null);

    let offset = $derived(parseFloat(offsetValue) || 0);
    let drift = $derived(parseFloat(driftValue) || 0);

    let selectedChapters = $derived(
        $chapters.filter(ch => !ch.deleted && ch.selected)
    );

    let showBetweenOption = $derived(selectedChapters.length >= 2);

    let affectedChapters = $derived.by(() => {
        const nonDeleted = $chapters.filter(ch => !ch.deleted);
        if (applyTo === "selected") return nonDeleted.filter(ch => ch.selected);
        if (applyTo === "all") return nonDeleted;
        // "between": all non-deleted chapters between first and last selected timestamps
        if (selectedChapters.length < 2) return selectedChapters;
        const minTs = Math.min(...selectedChapters.map(ch => ch.timestamp));
        const maxTs = Math.max(...selectedChapters.map(ch => ch.timestamp));
        return nonDeleted.filter(ch => ch.timestamp >= minTs && ch.timestamp <= maxTs);
    });

    let showDriftOption = $derived(affectedChapters.length >= 3);

    let changedCount = $derived(
        previewData.filter(item => item.oldTimestamp !== item.newTimestamp).length
    );

    let firstAffected = $derived(affectedChapters[0]);
    let lastAffected = $derived(affectedChapters[affectedChapters.length - 1]);

    let bookDuration = $derived($session.book?.duration || Infinity);

    let canApply = $derived(
        affectedChapters.length > 0 && (offset !== 0 || (driftEnabled && drift !== 0))
    );

    function computeNewTimestamps() {
        return affectedChapters.map(ch => {
            let newTs;
            if (driftEnabled && affectedChapters.length >= 2) {
                const firstTs = firstAffected.timestamp;
                const lastTs = lastAffected.timestamp;
                const range = lastTs - firstTs;
                const t = range > 0 ? (ch.timestamp - firstTs) / range : 0;
                newTs = ch.timestamp + offset + t * (drift - offset);
            } else {
                newTs = ch.timestamp + offset;
            }
            return {
                chapter_id: ch.id,
                new_timestamp: Math.max(0, Math.min(bookDuration - 1, newTs)),
            };
        });
    }

    let previewData = $derived.by(() => {
        const newTimestamps = computeNewTimestamps();
        return affectedChapters.map((ch, i) => ({
            id: ch.id,
            title: ch.current_title || ch.asr_title || null,
            oldTimestamp: ch.timestamp,
            newTimestamp: newTimestamps[i].new_timestamp,
        }));
    });

    function formatTimestamp(seconds) {
        const sign = seconds < 0 ? "-" : "";
        const abs = Math.abs(seconds);
        const hours = Math.floor(abs / 3600);
        const minutes = Math.floor((abs % 3600) / 60);
        const secs = Math.floor(abs % 60);

        if (hours > 0) {
            return `${sign}${hours}:${minutes.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
        }
        return `${sign}${minutes}:${secs.toString().padStart(2, "0")}`;
    }

    // --- Audio playback ---

    function stopPlayback() {
        if ($isPlaying && $currentSegmentId?.startsWith('shift-preview-')) {
            audio.stop();
        }
    }

    async function togglePlayOffset() {
        if (!firstAffected) return;
        try {
            if ($currentSegmentId === 'shift-preview-first' && $isPlaying) {
                audio.stop();
            } else {
                const ts = Math.max(0, firstAffected.timestamp + offset);
                await audio.play('shift-preview-first', ts);
            }
        } catch (err) {
            console.error("Failed to preview audio:", err);
        }
    }

    async function togglePlayPreviewItem(id, newTimestamp) {
        const segId = `shift-preview-item-${id}`;
        try {
            if ($currentSegmentId === segId && $isPlaying) {
                audio.stop();
            } else {
                await audio.play(segId, Math.max(0, newTimestamp));
            }
        } catch (err) {
            console.error("Failed to preview audio:", err);
        }
    }

    async function togglePlayDrift() {
        if (!lastAffected) return;
        try {
            if ($currentSegmentId === 'shift-preview-last' && $isPlaying) {
                audio.stop();
            } else {
                const ts = Math.max(0, lastAffected.timestamp + drift);
                await audio.play('shift-preview-last', ts);
            }
        } catch (err) {
            console.error("Failed to preview audio:", err);
        }
    }

    // --- Input handlers ---

    function adjustOffset(delta) {
        stopPlayback();
        offsetValue = String(offset + delta);
    }

    function adjustDrift(delta) {
        stopPlayback();
        driftValue = String(drift + delta);
    }

    function handleOffsetKeydown(e) {
        if (e.key === 'ArrowUp') {
            e.preventDefault();
            adjustOffset(1);
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            adjustOffset(-1);
        } else if (e.key === ' ') {
            e.preventDefault();
            togglePlayOffset();
        }
    }

    function handleDriftKeydown(e) {
        if (e.key === 'ArrowUp') {
            e.preventDefault();
            adjustDrift(1);
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            adjustDrift(-1);
        } else if (e.key === ' ') {
            e.preventDefault();
            togglePlayDrift();
        }
    }

    function sanitizeNumericInput(value) {
        // Strip everything except digits, minus, and decimal point
        return value.replace(/[^\d.\-]/g, '');
    }

    function handleOffsetInput() {
        stopPlayback();
        offsetValue = sanitizeNumericInput(offsetValue);
    }

    function handleDriftInput() {
        stopPlayback();
        driftValue = sanitizeNumericInput(driftValue);
    }

    // --- Dialog actions ---

    async function handleApply() {
        if (!canApply) return;
        loading = true;
        error = null;
        try {
            const shifts = computeNewTimestamps();
            await api.chapters.shiftTimestamps(shifts);
            close();
        } catch (err) {
            error = handleApiError(err);
        } finally {
            loading = false;
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

    // Reset state when dialog closes
    $effect(() => {
        if (!isOpen) {
            applyTo = "selected";
            offsetValue = "0";
            driftEnabled = false;
            driftValue = "0";
            error = null;
            loading = false;
        }
    });

    // Reset "between" selection if it becomes unavailable
    $effect(() => {
        if (applyTo === "between" && !showBetweenOption) {
            applyTo = "selected";
        }
    });

    // Disable drift if fewer than 3 affected chapters
    $effect(() => {
        if (driftEnabled && !showDriftOption) {
            driftEnabled = false;
        }
    });
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
                    <h3>Shift Timestamps</h3>
                    <button class="close-button" onclick={handleCancel} aria-label="Close">
                        <X size="20"/>
                    </button>
                </div>

                <div class="modal-body">
                    {#if error}
                        <div class="alert alert-danger">{error}</div>
                    {/if}

                    <!-- Apply to -->
                    <div class="apply-to-group">
                        <span class="apply-to-label">Apply to</span>
                        <div class="radio-options">
                            <label class="radio-label">
                                <input type="radio" bind:group={applyTo} value="selected"/>
                                Selected chapters
                            </label>
                            <label class="radio-label">
                                <input type="radio" bind:group={applyTo} value="all"/>
                                All chapters
                            </label>
                            {#if showBetweenOption}
                                <label class="radio-label">
                                    <input type="radio" bind:group={applyTo} value="between"/>
                                    Between first and last selected
                                    <div class="help-icon" data-tooltip="Shifts all chapters — including unselected ones — that fall between your first and last selected chapter">
                                        <CircleHelp size="14"/>
                                    </div>
                                </label>
                            {/if}
                        </div>
                    </div>

                    <!-- Offset input -->
                    <div class="input-group">
                        <label class="input-label">
                            {driftEnabled ? 'Start Offset' : 'Offset'}
                            <div class="help-icon" data-tooltip="How far the timestamps should be shifted, in seconds. Positive values shift chapters later, negative values shift them earlier. Use the arrow keys or +/- buttons to adjust by 1 second, or press Space to preview.">
                                <CircleHelp size="14"/>
                            </div>
                        </label>
                        <div class="offset-input-row">
                            <button class="adj-btn" onclick={() => adjustOffset(-1)} title="Decrease by 1 second">
                                <Minus size="16"/>
                            </button>
                            <input
                                type="text"
                                inputmode="decimal"
                                class="offset-input"
                                bind:value={offsetValue}
                                onkeydown={handleOffsetKeydown}

                                oninput={handleOffsetInput}
                            />
                            <button class="adj-btn" onclick={() => adjustOffset(1)} title="Increase by 1 second">
                                <Plus size="16"/>
                            </button>
                            <button class="play-btn" onclick={togglePlayOffset} title="Preview at shifted position of first affected chapter" disabled={!firstAffected}>
                                {#if $isPlaying && $currentSegmentId === 'shift-preview-first'}
                                    <Pause size="16"/>
                                {:else}
                                    <Play size="16"/>
                                {/if}
                            </button>
                        </div>
                    </div>

                    <!-- Drift option -->
                    {#if showDriftOption}
                        <div class="input-group drift-group">
                            <label class="checkbox-label">
                                <input type="checkbox" bind:checked={driftEnabled}/>
                                End Offset
                                <div class="help-icon" data-tooltip="The offset applied to the last affected chapter. The offset gradually changes from the start value to this value across all affected chapters. Useful when timing drift accumulates over the course of the book.">
                                    <CircleHelp size="14"/>
                                </div>
                            </label>
                            {#if driftEnabled}
                                <div class="offset-input-row">
                                    <button class="adj-btn" onclick={() => adjustDrift(-1)} title="Decrease by 1 second">
                                        <Minus size="16"/>
                                    </button>
                                    <input
                                        type="text"
                                        inputmode="decimal"
                                        class="offset-input"
                                        bind:value={driftValue}
                                        onkeydown={handleDriftKeydown}
        
                                        oninput={handleDriftInput}
                                    />
                                    <button class="adj-btn" onclick={() => adjustDrift(1)} title="Increase by 1 second">
                                        <Plus size="16"/>
                                    </button>
                                    <button class="play-btn" onclick={togglePlayDrift} title="Preview at shifted position of last affected chapter" disabled={!lastAffected}>
                                        {#if $isPlaying && $currentSegmentId === 'shift-preview-last'}
                                            <Pause size="16"/>
                                        {:else}
                                            <Play size="16"/>
                                        {/if}
                                    </button>
                                </div>
                            {/if}
                        </div>
                    {/if}

                    <!-- Preview list -->
                    {#if affectedChapters.length > 0}
                        <div class="preview-section">
                            <div class="preview-header">
                            <span class="input-label">Preview</span>
                            <span class="affected-count">{changedCount} chapter{changedCount !== 1 ? 's' : ''} will be shifted</span>
                        </div>
                            <div class="preview-list">
                                {#each previewData as item}
                                    <div class="preview-row">
                                        <button class="preview-play-btn" onclick={() => togglePlayPreviewItem(item.id, item.newTimestamp)} title="Preview at shifted position">
                                            {#if $isPlaying && $currentSegmentId === `shift-preview-item-${item.id}`}
                                                <Pause size="12" fill="currentColor" stroke="none"/>
                                            {:else}
                                                <Play size="12" fill="currentColor" stroke="none"/>
                                            {/if}
                                        </button>
                                        <span class="preview-title" class:no-title={!item.title} title={item.title ?? 'No Title'}>{item.title ?? 'No Title'}</span>
                                        <span class="preview-timestamps">
                                            <span class="ts-old">{formatTimestamp(item.oldTimestamp)}</span>
                                            <span class="ts-arrow">&rarr;</span>
                                            <span class="ts-new" class:ts-changed={item.oldTimestamp !== item.newTimestamp}>{formatTimestamp(item.newTimestamp)}</span>
                                        </span>
                                    </div>
                                {/each}
                            </div>
                        </div>
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
                        {loading ? 'Applying...' : 'Apply'}
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
        max-width: 500px;
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
        padding: 0.5rem 1.5rem 1rem;
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

    /* Apply to radio group */
    .apply-to-group {
        display: flex;
        align-items: flex-start;
        gap: 0.75rem;
        margin: 0 0 0.5rem;
    }

    .apply-to-label {
        font-weight: 600;
        font-size: 0.9rem;
        color: var(--text-primary);
        white-space: nowrap;
        padding-top: 0.2rem;
    }

    .radio-options {
        display: flex;
        flex-direction: column;
    }

    .radio-label {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.25rem 0;
        cursor: pointer;
        font-size: 0.875rem;
        color: var(--text-primary);
    }

    .radio-label input[type="radio"] {
        margin: 0;
    }

    /* Offset input */
    .input-group {
        margin-bottom: 1rem;
    }

    .input-label {
        display: flex;
        align-items: center;
        gap: 0.25rem;
        font-weight: 600;
        font-size: 0.9rem;
        color: var(--text-primary);
        margin-bottom: 0.4rem;
    }

    .checkbox-label {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-weight: 600;
        font-size: 0.9rem;
        color: var(--text-primary);
        cursor: pointer;
        margin-bottom: 0.4rem;
    }

    .checkbox-label input[type="checkbox"] {
        margin: 0;
    }

    .offset-input-row {
        display: flex;
        align-items: center;
        gap: 0.25rem;
    }

    .offset-input {
        width: 6rem;
        padding: 0.35rem 0.5rem;
        border: 1px solid var(--border-color);
        border-radius: 0.25rem;
        background: var(--bg-primary);
        color: var(--text-primary);
        font-size: 0.875rem;
        text-align: center;
        font-family: inherit;
    }

    .offset-input:focus {
        outline: none;
        border-color: var(--primary-color);
        box-shadow: 0 0 0 2px rgba(var(--primary-rgb, 99, 102, 241), 0.2);
    }

    .adj-btn,
    .play-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 2rem;
        height: 2rem;
        border: 1px solid var(--border-color);
        border-radius: 0.25rem;
        background: var(--bg-secondary);
        color: var(--text-primary);
        cursor: pointer;
        padding: 0;
    }

    .adj-btn:hover,
    .play-btn:hover {
        background: var(--hover-bg);
    }

    .adj-btn:disabled,
    .play-btn:disabled {
        opacity: 0.4;
        cursor: not-allowed;
    }

    .play-btn {
        color: var(--primary-color);
    }

    /* Drift group */
    .drift-group {
        padding-top: 1rem;
        border-top: 1px solid var(--border-color);
    }

    /* Preview list */
    .preview-header {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        margin-bottom: 0.4rem;
    }

    .preview-header .input-label {
        margin-bottom: 0;
    }

    .affected-count {
        font-size: 0.8rem;
        color: var(--text-secondary);
    }

    .preview-section {
        margin-top: 0.5rem;
    }

    .preview-list {
        max-height: 200px;
        overflow-y: auto;
        border: 1px solid var(--border-color);
        border-radius: 0.25rem;
        background: var(--bg-primary);
    }

    .preview-play-btn {
        flex-shrink: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        width: 1.4rem;
        height: 1.4rem;
        border: none;
        border-radius: 0.2rem;
        background: transparent;
        color: var(--primary-color);
        cursor: pointer;
        padding: 0;
        margin-right: 0.35rem;
        opacity: 0.6;
    }

    .preview-play-btn:hover {
        background: var(--hover-bg);
        opacity: 1;
    }

    .preview-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.3rem 0.6rem;
        font-size: 0.8rem;
        border-bottom: 1px solid var(--border-color);
    }

    .preview-row:last-child {
        border-bottom: none;
    }

    .preview-title {
        flex: 1;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        color: var(--text-primary);
        margin-right: 0.75rem;
    }

    .preview-title.no-title {
        color: var(--text-muted);
        font-style: italic;
    }

    .preview-timestamps {
        display: flex;
        align-items: center;
        gap: 0.35rem;
        white-space: nowrap;
        font-variant-numeric: tabular-nums;
    }

    .ts-old {
        color: var(--text-secondary);
    }

    .ts-arrow {
        color: var(--text-tertiary);
        font-size: 0.75rem;
    }

    .ts-new {
        color: var(--text-primary);
    }

    .ts-changed {
        color: var(--primary-color);
        font-weight: 600;
    }

    /* Help icon tooltip */
    .help-icon {
        display: inline-flex;
        background: transparent;
        border: none;
        color: var(--text-secondary);
        cursor: help;
        position: relative;
        padding: 2px;
        border-radius: 50%;
        transition: all 0.2s ease;
    }

    .help-icon:hover {
        color: var(--primary-color);
        background: var(--bg-tertiary);
    }

    .help-icon[data-tooltip]:hover::after {
        content: attr(data-tooltip);
        position: fixed;
        transform: translate(-50%, calc(-100% - 8px));
        padding: 8px 12px;
        background: var(--bg-primary);
        color: var(--text-primary);
        border: 1px solid var(--border-color);
        border-radius: 6px;
        font-size: 0.875rem;
        line-height: 1.4;
        white-space: pre-line;
        max-width: 360px;
        z-index: 10001;
        font-weight: normal;
    }

    .help-icon[data-tooltip]:hover::before {
        content: "";
        position: absolute;
        bottom: 100%;
        left: 50%;
        transform: translateX(-50%);
        margin-bottom: -5px;
        border: 6px solid transparent;
        border-top-color: var(--border-color);
        z-index: 10002;
    }

    /* Buttons */
    .btn {
        padding: 0.5rem 1rem;
        border: none;
        border-radius: 0.25rem;
        cursor: pointer;
        font-size: 0.875rem;
        font-weight: 500;
    }

    .btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    .btn-primary {
        background: var(--primary-color);
        color: white;
    }

    .btn-primary:hover:not(:disabled) {
        opacity: 0.9;
    }

    .btn-secondary {
        background: var(--bg-secondary);
        color: var(--text-primary);
        border: 1px solid var(--border-color);
    }

    .btn-secondary:hover:not(:disabled) {
        background: var(--hover-bg);
    }

    @media (max-width: 768px) {
        .modal-dialog {
            width: 95%;
            max-height: 95vh;
        }

        .modal-body {
            padding: 0.5rem 1rem;
        }
    }
</style>
