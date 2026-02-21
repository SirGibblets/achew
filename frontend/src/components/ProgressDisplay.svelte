<script>
    import {session, progress} from "../stores/session.js";
    import {isConnected} from "../stores/websocket.js";
    import {api} from "../utils/api.js";
    import Icon from "./Icon.svelte";

    // Icons
    import AudioLines from "@lucide/svelte/icons/audio-lines";
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
            description: "Checking if the item exists and is accessible...",
            icon: CircleCheckBig,
        },
        downloading: {
            title: "Downloading Audio",
            description: "Downloading the audiobook file(s)...",
            icon: Download,
        },
        file_prep: {
            title: "Preparing files",
            description: "Getting files ready for processing...",
            icon: ClipboardList,
        },
        audio_analysis: {
            title: "Scanning for Chapter Cues",
            description: "Analyzing audio to detect chapter cues...",
            icon: ScanSearch,
        },
        vad_prep: {
            title: "Preparing files",
            description: "Getting files ready for Smart Detection...",
            icon: ClipboardList,
        },
        vad_analysis: {
            title: "Scanning for Chapter Cues",
            description: "Analyzing voice activity to detect chapter cues...",
            icon: AudioLines,
        },
        partial_scan_prep: {
            title: "Preparing Partial Scan",
            description: "Extracting audio for analysis...",
            icon: ScissorsLineDashed,
        },
        partial_audio_analysis: {
            title: "Scanning for Chapter Cues",
            description: "Analyzing audio in selected region...",
            icon: ScanSearch,
        },
        partial_vad_analysis: {
            title: "Scanning for Chapter Cues",
            description: "Analyzing voice activity in selected region...",
            icon: AudioLines,
        },
        audio_extraction: {
            title: "Extracting",
            description: "Extracting short segments of chapter audio...",
            icon: ScissorsLineDashed,
        },
        trimming: {
            title: "Trimming",
            description: "Removing excess audio from chapter segments...",
            icon: Scissors,
        },
        asr_processing: {
            title: "Transcribing",
            description: "Generating chapter titles using speech recognition...",
            icon: Mic,
        },
    };

    // Get current step configuration
    $: currentStepConfig = stepConfig[$session.step] || {
        title: "Processing",
        description: "Working...",
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

    // Connection warning
    $: showConnectionWarning = !$isConnected && $session.step !== "idle";

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
        >{$progress.message || "Processing..."}</span
        >
                <span class="progress-percent">{Math.round($progress.percent)}%</span>
            </div>

            <div class="progress">
                <div
                        class="progress-bar"
                        style="width: {$progress.percent}%"
                        role="progressbar"
                        aria-valuenow={$progress.percent}
                        aria-valuemin="0"
                        aria-valuemax="100"
                ></div>
            </div>
        </div>

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
                <strong>Connection Lost:</strong> Reconnecting to server...
                <br/><small
            >Progress updates may be delayed but processing continues.</small
            >
            </div>
        {/if}
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

    .action-section {
        display: flex;
        justify-content: center;
        margin-top: 2rem;
        margin-bottom: 2rem;
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
