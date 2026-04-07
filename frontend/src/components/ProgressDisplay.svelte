<script>
    import {session, progress} from "../stores/session.js";
    import {isConnected} from "../stores/websocket.js";
    import {api} from "../utils/api.js";
    import {onMount, onDestroy} from "svelte";
    import {slide} from "svelte/transition";

    // Icons
    import AudioLines from "@lucide/svelte/icons/audio-lines";
    import BellOff from "@lucide/svelte/icons/bell-off";
    import BellRing from "@lucide/svelte/icons/bell-ring";
    import CircleCheckBig from "@lucide/svelte/icons/circle-check-big";
    import ClipboardList from "@lucide/svelte/icons/clipboard-list";
    import Download from "@lucide/svelte/icons/download";
    import Mic from "@lucide/svelte/icons/mic";
    import ScanSearch from "@lucide/svelte/icons/scan-search";
    import Scissors from "@lucide/svelte/icons/scissors";
    import ScissorsLineDashed from "@lucide/svelte/icons/scissors-line-dashed";
    import Settings from "@lucide/svelte/icons/settings";

    // Progress step configurations
    const stepConfig = {
        validating: {
            title: "Validating Item",
            description: "Checking if the item exists and is accessible…",
            icon: CircleCheckBig,
        },
        downloading: {
            title: "Downloading Audio",
            description: "Downloading the audiobook file(s)…",
            icon: Download,
        },
        file_prep: {
            title: "Preparing files",
            description: "Getting files ready for processing…",
            icon: ClipboardList,
        },
        audio_analysis: {
            title: "Scanning for Chapter Cues",
            description: "Analyzing audio to detect chapter cues…",
            icon: ScanSearch,
        },
        vad_prep: {
            title: "Preparing files",
            description: "Getting files ready for Smart Detection…",
            icon: ClipboardList,
        },
        vad_analysis: {
            title: "Scanning for Chapter Cues",
            description: "Analyzing voice activity to detect chapter cues…",
            icon: AudioLines,
        },
        partial_scan_prep: {
            title: "Preparing Partial Scan",
            description: "Extracting audio for analysis…",
            icon: ScissorsLineDashed,
        },
        partial_audio_analysis: {
            title: "Scanning for Chapter Cues",
            description: "Analyzing audio in selected region…",
            icon: ScanSearch,
        },
        partial_vad_analysis: {
            title: "Scanning for Chapter Cues",
            description: "Analyzing voice activity in selected region…",
            icon: AudioLines,
        },
        audio_extraction: {
            title: "Extracting",
            description: "Extracting short segments of chapter audio…",
            icon: ScissorsLineDashed,
        },
        trimming: {
            title: "Trimming",
            description: "Removing excess audio from chapter segments…",
            icon: Scissors,
        },
        asr_processing: {
            title: "Transcribing",
            description: "Generating chapter titles using speech recognition…",
            icon: Mic,
        },
    };

    // Get current step configuration
    $: currentStepConfig = stepConfig[$session.step] || {
        title: "Processing",
        description: "Working…",
        icon: Settings,
    };

    // Format bytes for download progress
    function formatBytes(bytes) {
        if (bytes === 0) return "0 B";
        const k = 1024;
        const sizes = ["B", "KB", "MB", "GB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
    }

    // Format time remaining
    function formatTimeRemaining(seconds) {
        if (!seconds || seconds <= 0) return "";

        if (seconds < 60) {
            return `${Math.round(seconds)}s`;
        } else if (seconds < 3600) {
            const mins = Math.floor(seconds / 60);
            const secs = Math.round(seconds % 60);
            return `${mins}m ${secs}s`;
        } else {
            const hours = Math.floor(seconds / 3600);
            const mins = Math.floor((seconds % 3600) / 60);
            return `${hours}h ${mins}m`;
        }
    }

    // Calculate download speed and ETA for download progress
    $: downloadInfo = (() => {
        if ($session.step !== "downloading" || !$progress.details) {
            return null;
        }

        const {bytes_downloaded, total_bytes, speed_bps, eta_seconds} =
            $progress.details;

        return {
            downloaded: formatBytes(bytes_downloaded || 0),
            total: formatBytes(total_bytes || 0),
            speed: speed_bps ? `${formatBytes(speed_bps)}/s` : null,
            eta: eta_seconds ? formatTimeRemaining(eta_seconds) : null,
        };
    })();

    // Format processing details for other steps
    $: processingInfo = (() => {
        if (!$progress.details) return null;

        switch ($session.step) {
            case "audio_analysis":
                const {current_time, total_duration} = $progress.details;
                return {
                    current: current_time ? `${Math.round(current_time)}s` : null,
                    total: total_duration ? `${Math.round(total_duration)}s` : null,
                };

            case "asr_processing":
                const {completed_segments, total_segments} = $progress.details;
                return {
                    completed: completed_segments || 0,
                    total: total_segments || 0,
                };

            default:
                return null;
        }
    })();

    // Indeterminate mode when progress percent is negative
    $: indeterminate = $progress.percent < 0;

    // Connection warning
    $: showConnectionWarning = !$isConnected && $session.step !== "idle";

    let feedText = null;
    let lastStep = $session.step;
    $: {
        if ($session.step !== lastStep) {
            lastStep = $session.step;
            feedText = null;
        }
        const latest = $progress.details?.feed_text;
        if (latest) feedText = latest;
    }

    async function handleCancel() {
        try {
            const response = await api.session.cancel();
            if (response.action === "deleted") {
                session.resetToIdle();
            }
        } catch (error) {
            console.error("Failed to cancel current step:", error);
            session.setError("Failed to cancel processing. Please try again.");
        }
    }

    // Chime functionality
    let chimeEnabled = false;
    let selectedChime = "chime1";
    let wiggle = false;
    let wiggleTimeout;
    let mountTime;

    onMount(() => {
        mountTime = Date.now();
        const storedEnabled = localStorage.getItem("achew_chime_enabled");
        if (storedEnabled !== null) {
            chimeEnabled = storedEnabled === "true";
        }
        
        const storedChime = localStorage.getItem("achew_selected_chime");
        if (storedChime) {
            selectedChime = storedChime;
        }
    });

    onDestroy(() => {
        if (wiggleTimeout) clearTimeout(wiggleTimeout);
        if (chimeEnabled && mountTime && (Date.now() - mountTime) >= 15000) {
            const audio = new Audio(`/sounds/${selectedChime}.mp3`);
            audio.play().catch(e => console.error("Could not play chime:", e));
        }
    });

    function playChime(chime) {
        selectedChime = chime;
        localStorage.setItem("achew_selected_chime", chime);
        const audio = new Audio(`/sounds/${chime}.mp3`);
        audio.play().catch(e => console.error("Could not play chime:", e));
        
        if (wiggleTimeout) clearTimeout(wiggleTimeout);
        wiggle = false;
        setTimeout(() => {
            wiggle = true;
            wiggleTimeout = setTimeout(() => wiggle = false, 400);
        }, 10);
    }

    function toggleChime() {
        chimeEnabled = !chimeEnabled;
        localStorage.setItem("achew_chime_enabled", chimeEnabled.toString());
        if (chimeEnabled) {
            playChime(selectedChime);
        }
    }
</script>

<div class="progress-display">
    <div>
        <div class="step-icon">
            <svelte:component this={currentStepConfig.icon || Settings} size="48"/>
        </div>
        <h2>{currentStepConfig.title}</h2>
        <div>
            <p class="step-description">{currentStepConfig.description}</p>
        </div>

        <div class="progress-section">
            <div class="progress-header">
        <span class="progress-label"
        >{$progress.message || "Processing…"}</span
        >
                {#if !indeterminate}
                    <span class="progress-percent">{Math.round($progress.percent)}%</span>
                {/if}
            </div>

            <div class="progress">
                <div
                        class="progress-bar"
                        class:indeterminate
                        style={indeterminate ? undefined : `width: ${$progress.percent}%`}
                        role="progressbar"
                        aria-valuenow={indeterminate ? undefined : $progress.percent}
                        aria-valuemin="0"
                        aria-valuemax="100"
                ></div>
            </div>
        </div>

        <p class="feed-text">{feedText ?? "\u00A0"}</p>

        <div class="action-section">
            <button
                    class="btn btn-cancel"
                    on:click={handleCancel}
                    disabled={$session.loading}
            >
                Cancel
            </button>
        </div>

        {#if showConnectionWarning}
            <div class="alert alert-warning mb-3">
                <strong>Connection Lost:</strong> Reconnecting to server…
                <br/><small
            >Progress updates may be delayed but processing continues.</small
            >
            </div>
        {/if}
    </div>

    <div class="chime-container">
        <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
        <div 
            class="chime-content" 
            class:disabled-clickable={!chimeEnabled}
            role={!chimeEnabled ? "button" : "region"}
            tabindex={!chimeEnabled ? "0" : undefined}
            on:click={!chimeEnabled ? toggleChime : undefined}
            on:keydown={!chimeEnabled ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleChime(); } } : undefined}
            aria-label={!chimeEnabled ? "Enable Chime" : "Chime settings"}
            title={!chimeEnabled ? "Click to enable chime" : undefined}
        >
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <svelte:element 
                this={chimeEnabled ? "button" : "div"}
                class="chime-icon-btn {wiggle ? 'wiggle' : ''}" 
                class:disabled={!chimeEnabled}
                on:click={chimeEnabled ? ((e) => { e.stopPropagation(); toggleChime(); }) : undefined} 
                aria-label={chimeEnabled ? "Disable Chime" : undefined}
            >
                {#if chimeEnabled}
                    <BellRing size={48} color="var(--primary)" />
                {:else}
                    <BellOff size={48} color="var(--text-muted)" />
                {/if}
            </svelte:element>

            {#if chimeEnabled}
                <div transition:slide={{ duration: 300 }}>
                    <div class="chime-details">
                        <p class="chime-title">Chime will play when processing has finished</p>
                        <div class="chime-dots">
                            {#each Array(12) as _, i}
                                <button 
                                    class="chime-dot {selectedChime === `chime${i + 1}` ? 'active' : ''}"
                                    on:click={() => playChime(`chime${i + 1}`)}
                                    aria-label={`Select Chime ${i + 1}`}
                                ></button>
                            {/each}
                        </div>
                    </div>
                </div>
            {/if}
        </div>
    </div>
</div>

<style>
    .progress-display {
        max-width: 600px;
        width: 100%;
        margin: 0 auto;
        display: flex;
        flex-direction: column;
        flex: 1;
        text-align: center;
        height: 100vh;
    }

    .step-icon {
        text-align: center;
        display: flex;
        justify-content: center;
        align-items: center;
        color: var(--primary-color);
    }

    h2 {
        margin-top: 1.5rem;
        margin-bottom: 0.75rem;
        font-size: 2rem;
        font-weight: 600;
    }

    .step-description {
        color: var(--text-secondary);
    }

    .progress-section {
        margin-top: 3rem;
    }

    .progress-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.5rem;
    }

    .progress-label {
        font-weight: 500;
        color: var(--text-primary);
    }

    .progress-percent {
        font-weight: 600;
        color: var(--primary);
        font-size: 1.125rem;
    }

    .progress {
        height: 0.5rem;
        background-color: var(--bg-tertiary);
        border-radius: 0.75rem;
        overflow: hidden;
    }

    .progress-bar {
        background-color: var(--primary);
        transition: width 0.1s ease;
        border-radius: 0.75rem;
    }

    .progress-bar.indeterminate {
        width: 40%;
        animation: indeterminate 1.5s ease-in-out infinite;
    }

    @keyframes indeterminate {
        0% {
            transform: translateX(-100%);
        }
        100% {
            transform: translateX(250%);
        }
    }

    .action-section {
        display: flex;
        justify-content: center;
        margin-top: 2rem;
        margin-bottom: 2rem;
    }

    .feed-text {
        margin: 0.5rem 0rem;
        font-size: 0.85rem;
        color: var(--text-secondary);
        font-style: italic;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    /* Chime styles */
    .chime-container {
        flex: 1;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        padding-bottom: 2rem;
    }

    .chime-content {
        display: flex;
        flex-direction: column;
        align-items: center;
        padding: 0.75rem 1.25rem;
        border-radius: 0.75rem;
        transition: all 0.3s ease;
        max-width: 100%;
    }

    .chime-content.disabled-clickable {
        cursor: pointer;
    }

    .chime-content.disabled-clickable:hover .chime-icon-btn {
        background-color: var(--bg-tertiary);
    }

    .chime-icon-btn {
        background: none;
        border: none;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 0.5rem;
        border-radius: 50%;
        color: var(--text-primary);
        transition: background-color 0.2s, opacity 0.2s;
    }

    .chime-icon-btn.disabled {
        opacity: 0.5;
    }

    .chime-icon-btn:hover {
        background-color: var(--bg-tertiary);
    }

    .chime-details {
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        width: max-content;
        margin-top: 0.75rem;
    }

    .chime-title {
        margin: 0;
        font-size: 0.65rem;
        font-weight: 500;
        color: var(--text-muted);
    }

    .chime-dots {
        display: grid;
        grid-template-columns: repeat(12, auto);
        gap: 0.75rem;
        margin: 0.5rem 0;
    }

    .chime-dot {
        width: 0.75rem;
        height: 0.75rem;
        border-radius: 50%;
        background-color: var(--text-primary);
        border: none;
        cursor: pointer;
        padding: 0;
        opacity: 0.2;
        transition: all 0.2s, transform 0.1s;
    }

    .chime-dot:hover {
        background-color: var(--text-secondary);
        opacity: 0.8;
        transform: scale(1.1);
    }

    .chime-dot.active {
        opacity: 0.7;
        transform: scale(1.2);
    }

    @keyframes wiggle {
        0% { transform: rotate(-10deg); }
        33% { transform: rotate(10deg); }
        66% { transform: rotate(-10deg); }
        100% { transform: rotate(0deg); }
    }

    .wiggle {
        animation: wiggle 0.3s ease-in-out;
    }

    /* Responsive design */
    @media (max-width: 768px) {
        .step-icon {
            font-size: 1.5rem;
            min-width: auto;
        }

        .progress-header {
            flex-direction: column-reverse;
            gap: 0.25rem;
            text-align: center;
        }
    }

    /* Responsive design */
    @media (max-width: 480px) {
        .progress-display {
            padding: 1rem;
        }

        h2 {
            margin-top: 1rem;
            margin-bottom: 0.25rem;
            font-size: 1.2rem;
            font-weight: 600;
        }

        .step-description {
            font-size: 0.875rem;
        }

        .progress-label {
            font-size: 0.875rem;
        }
    }
</style>
