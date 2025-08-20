<script>
    import {onMount} from "svelte";
    import {session} from "../stores/session.js";
    import Icon from "./Icon.svelte";

    let progress = 0;
    let message = "";
    let details = {};
    let parsedCount = 0;
    let expectedCount = 0;
    let deselectedCount = 0;

    // Listen to session progress updates
    $: if ($session.progress && $session.step === "ai_cleanup") {
        progress = $session.progress.percent || 0;
        message = $session.progress.message || "";
        details = $session.progress.details || {};

        // Extract streaming progress details
        parsedCount = details.parsed_count || 0;
        expectedCount = details.expected_count || 0;
        deselectedCount = details.deselected_count || 0;
    }

    // Format progress message for display
    $: progressMessage = (() => {
        if (message) {
            return message;
        }
        if (parsedCount > 0 && expectedCount > 0) {
            return `Cleaning up chapters: ${parsedCount}/${expectedCount}`;
        }
        return "Initializing AI cleanup...";
    })();
</script>

<div class="ai-processing">
    <div class="processing-border">
        <div class="processing-container">
            <div class="processing-header">
                <div class="processing-icon">
                    <div class="ai-icon">
                        <Icon
                                name="ai"
                                size="64"
                                color="linear-gradient(135deg, var(--ai-gradient-start-hover) 0%, var(--ai-gradient-end-hover) 100%)"
                        />
                    </div>
                </div>

                <h2>AI Cleanup in Progress</h2>
                <p>Analyzing and improving the selected chapter titles...</p>

                <div class="progress-bar-container">
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: {progress}%"></div>
                    </div>
                </div>

                <div class="progress-message">
                    {progressMessage}
                </div>
            </div>
        </div>
    </div>
</div>

<style>
    .ai-processing {
        min-height: 60vh;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 2rem;
    }

    .processing-border {
        background: linear-gradient(135deg, var(--ai-gradient-start) 0%, var(--ai-gradient-end) 100%);
        border-radius: 16px;
        padding: 3px;
        max-width: 600px;
        width: 100%;
    }

    .processing-container {
        background: var(--bg-card);
        border-radius: 13px;
        padding: 1.5rem;
        text-align: center;
    }

    .processing-header {
        margin-bottom: 0;
    }

    .processing-icon {
        margin-bottom: 1.5rem;
    }

    .ai-icon {
        font-size: 4rem;
        animation: pulse 1s ease-in-out infinite;
    }

    @keyframes pulse {
        0%,
        100% {
            transform: scale(1);
        }
        50% {
            transform: scale(1.1);
        }
    }

    .processing-header h2 {
        color: var(--text-primary);
        font-size: 2rem;
        margin-bottom: 0;
        font-weight: 600;
    }

    .processing-header p {
        color: var(--text-secondary);
        font-size: 1.1rem;
    }

    .progress-message {
        color: var(--text-secondary);
        font-size: 0.8rem;
        margin-bottom: 2rem;
        margin-top: 0.75rem;
    }

    .progress-bar-container {
        display: flex;
        align-items: center;
        gap: 1rem;
        margin-top: 2.5rem;
        width: 100%;
    }

    .progress-bar {
        flex: 1;
        height: 4px;
        background: rgba(0, 0, 0, 0.1);
        border-radius: 4px;
        margin: 0 4.2rem;
        overflow: hidden;
        position: relative;
    }

    :global([data-theme="dark"]) .progress-bar {
        background: rgba(255, 255, 255, 0.1);
    }

    .progress-fill {
        height: 100%;
        background: linear-gradient(135deg, var(--ai-gradient-start) 0%, var(--ai-gradient-end) 100%);
        border-radius: 4px;
        position: relative;
    }

    @keyframes spin {
        0% {
            transform: rotate(0deg);
        }
        100% {
            transform: rotate(360deg);
        }
    }

    /* Responsive design */
    @media (max-width: 768px) {
        .ai-processing {
            padding: 1rem;
        }

        .processing-container {
            padding: 2rem;
        }

        .processing-header h2 {
            font-size: 1.5rem;
        }

        .ai-icon {
            font-size: 3rem;
        }

        .progress-bar {
            margin: 0 2rem;
        }
    }
</style>
