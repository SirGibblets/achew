<script>
    import {onDestroy, onMount} from "svelte";
    import {session} from "./stores/session.js";
    import {isConnected, websocket} from "./stores/websocket.js";

    // Pages
    import ABSSetup from "./components/ABSSetup.svelte";
    import AICleanup from "./components/AICleanup.svelte";
    import ChapterEditor from "./components/ChapterEditor.svelte";
    import ChapterReview from "./components/ChapterReview.svelte";
    import ConfigureASR from "./components/ConfigureASR.svelte";
    import Connecting from "./components/Connecting.svelte";
    import CueSetSelection from "./components/CueSetSelection.svelte";
    import FindBook from "./components/FindBook.svelte";
    import Icon from "./components/Icon.svelte";
    import LLMSetup from "./components/LLMSetup.svelte";
    import ProgressDisplay from "./components/ProgressDisplay.svelte";
    import SelectCueSource from "./components/SelectCueSource.svelte";

    // Icons
    import ChevronLeft from "@lucide/svelte/icons/chevron-left";
    import CircleDot from "@lucide/svelte/icons/circle-dot";
    import CircleQuestionMark from "@lucide/svelte/icons/circle-question-mark";
    import Headphones from "@lucide/svelte/icons/headphones";
    import Mic from "@lucide/svelte/icons/mic";
    import Moon from "@lucide/svelte/icons/moon";
    import Pencil from "@lucide/svelte/icons/pencil";
    import Settings from "@lucide/svelte/icons/settings";
    import Sun from "@lucide/svelte/icons/sun";

    let currentComponent = Connecting;
    let mounted = false;
    let darkMode = false;
    let showRestartOptions = false;
    let showSettingsMenu = false;
    let checkingConfig = true;

    // Theme management
    function toggleTheme() {
        darkMode = !darkMode;
        updateTheme();
        localStorage.setItem("theme", darkMode ? "dark" : "light");
    }

    function updateTheme() {
        if (darkMode) {
            document.documentElement.setAttribute("data-theme", "dark");
        } else {
            document.documentElement.removeAttribute("data-theme");
        }
    }

    // Initialize theme from localStorage
    function initializeTheme() {
        const savedTheme = localStorage.getItem("theme");
        const prefersDark = window.matchMedia(
            "(prefers-color-scheme: dark)",
        ).matches;

        darkMode = savedTheme === "dark" || (savedTheme === null && prefersDark);
        updateTheme();
    }

    // Handle ABS configuration complete
    function handleABSConfigured() {
        // The backend will automatically transition to LLM setup
        // Just refresh the session status
        session.loadActiveSession();
    }

    // Handle LLM setup complete
    function handleLLMSetupComplete() {
        // The backend will automatically transition to idle
        // Just refresh the session status
        session.loadActiveSession();
    }

    // Reactive component selection based on connection and session step
    $: currentComponent = (() => {
        if (!mounted) return Connecting;
        if (checkingConfig || !$isConnected) return Connecting;
        switch ($session.step) {
            case "abs_setup":
                return ABSSetup;
            case "llm_setup":
                return LLMSetup;
            case "validating":
            case "downloading":
            case "file_prep":
            case "audio_analysis":
            case "vad_prep":
            case "vad_analysis":
            case "audio_extraction":
            case "trimming":
            case "asr_processing":
                return ProgressDisplay;
            case "select_cue_source":
                return SelectCueSource;
            case "cue_set_selection":
                return CueSetSelection;
            case "configure_asr":
                return ConfigureASR;
            case "chapter_editing":
                return ChapterEditor;
            case "ai_cleanup":
                return AICleanup;
            case "reviewing":
                return ChapterReview;
            case "completed":
                return FindBook;
            default:
                return $session.step ? FindBook : Connecting;
        }
    })();

    // Handle global errors
    $: if ($session.error) {
        console.error("Session error:", $session.error);
    }

    onMount(async () => {
        mounted = true;

        // Initialize theme
        initializeTheme();

        // Connect WebSocket immediately for real-time updates
        session.connectWebSocket();

        // Load active session - backend will set appropriate step
        try {
            await session.loadActiveSession();
        } catch (error) {
            console.error("Failed to load session data:", error);
        } finally {
            checkingConfig = false;
        }
    });

    onDestroy(() => {
        // Cleanup stores
        session.destroy();
        websocket.destroy();
    });

    // Helper function to get connection status display
    function getConnectionStatusText(connected, step) {
        if (step === "idle") return "Ready";
        if (connected) return "Connected";
        return "Disconnected";
    }

    // Helper function to get connection status class
    function getConnectionStatusClass(connected, step) {
        if (step === "idle") return "ready";
        if (connected) return "connected";
        return "disconnected";
    }

    // Restart functionality
    function handleRestartClick(event) {
        event.stopPropagation();
        showRestartOptions = !showRestartOptions;
    }

    async function handleRestartFromStep(step) {
        showRestartOptions = false;

        // Restarting at 'idle' means ending the session
        if (step == "idle") {
            session.deleteSession();
            return;
        }

        // For other steps, restart the session from that step
        try {
            await session.restartSession(step);
        } catch (error) {
            console.error(`Failed to restart from ${step}:`, error);
        }
    }

    function getRestartOptionLabel(step) {
        switch (step) {
            case "idle":
                return "New Audiobook";
            case "select_cue_source":
                return "Select Cue Source";
            case "cue_set_selection":
                return "Select Cue Set";
            case "configure_asr":
                return "Transcribe Titles";
            case "chapter_editing":
                return "Edit Chapters";
            default:
                return "Unknown Step (" + step + ")";
        }
    }

    function getRestartOptionIcon(step) {
        switch (step) {
            case "idle":
                return Headphones;
            case "select_cue_source":
                return CircleDot;
            case "configure_asr":
                return Mic;
            case "chapter_editing":
                return Pencil;
            default:
                return CircleQuestionMark;
        }
    }

    function closeRestartOptions() {
        showRestartOptions = false;
    }

    // Close dropdowns when clicking outside
    function handleOutsideClick(event) {
        if (showRestartOptions && !event.target.closest(".restart-container")) {
            closeRestartOptions();
        }
        if (showSettingsMenu && !event.target.closest(".settings-container")) {
            closeSettingsMenu();
        }
    }

    // Check if restart button should be shown
    function shouldShowRestartButton(restartOptions) {
        return !["abs_setup", "llm_setup", "idle"].includes($session.step);
    }

    // Check if restart button should be disabled
    function shouldDisableRestartButton(restartOptions) {
        if (restartOptions.length === 0) {
            return true;
        }
        return ![
            "select_cue_source",
            "cue_set_selection",
            "configure_asr",
            "chapter_editing",
            "reviewing",
            "completed",
        ].includes($session.step);
    }

    // Format duration for display
    function formatDuration(seconds) {
        if (!seconds) return "";
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);

        if (hours > 0) {
            return `${hours}h ${minutes}m`;
        }
        return `${minutes}m`;
    }

    // Settings menu functions
    function toggleSettingsMenu() {
        showSettingsMenu = !showSettingsMenu;
    }

    function closeSettingsMenu() {
        showSettingsMenu = false;
    }

    async function gotoABSSetup() {
        closeSettingsMenu();
        try {
            const response = await fetch("/api/goto-abs-setup", {
                method: "POST",
            });

            if (response.ok) {
                // Refresh session status to trigger UI update
                await session.loadActiveSession();
            } else {
                console.error("Failed to navigate to ABS setup");
            }
        } catch (error) {
            console.error("Error navigating to ABS setup:", error);
        }
    }

    async function gotoLLMSetup() {
        closeSettingsMenu();
        try {
            const response = await fetch("/api/goto-llm-setup", {
                method: "POST",
            });

            if (response.ok) {
                // Refresh session status to trigger UI update
                await session.loadActiveSession();
            } else {
                console.error("Failed to navigate to LLM setup");
            }
        } catch (error) {
            console.error("Error navigating to LLM setup:", error);
        }
    }

    // Check if settings button should be shown (hide during setup steps and while connecting)
    $: isConnectingView = currentComponent === Connecting;
    $: shouldShowSettings =
        !["abs_setup", "llm_setup"].includes($session.step) && !isConnectingView;
</script>

<!-- svelte-ignore a11y-click-events-have-key-events -->
<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
<main class="app" on:click={handleOutsideClick}>
    <header class="app-header">
        <div class="header-content">
            <div class="header-left">
                {#if !isConnectingView && shouldShowRestartButton($session.restartOptions)}
                    <div class="restart-container">
                        <button
                                class="restart-toggle"
                                on:click={handleRestartClick}
                                disabled={$session.loading ||
                shouldDisableRestartButton($session.restartOptions)}
                                title="Go back to..."
                                aria-label="Go back to..."
                        >
                            <ChevronLeft size="20"/>
                        </button>

                        {#if showRestartOptions}
                            <div class="restart-dropdown">
                                <div class="restart-options">
                                    {#each $session.restartOptions as option}
                                        <button
                                                class="btn btn-sm btn-outline restart-option"
                                                on:click={() => handleRestartFromStep(option)}
                                                disabled={$session.loading}
                                        >
                                            {#if option === "cue_set_selection"}
                                                <Icon name="timeline" size="16"/>
                                            {:else}
                                                <svelte:component this={getRestartOptionIcon(option)} size="16"/>
                                            {/if}
                                            {getRestartOptionLabel(option)}
                                        </button>
                                    {/each}
                                </div>
                            </div>
                        {/if}
                    </div>
                {/if}

                {#if !isConnectingView && $session.book && $session.book.media && $session.book.media.metadata && $session.book.media.metadata.title}
                    <div class="audiobook-info-pill">
            <span class="audiobook-title"
            >{$session.book.media.metadata.title}</span
            >
                        {#if $session.book.duration > 0}
              <span class="audiobook-duration"
              >{formatDuration($session.book.duration)}</span
              >
                        {/if}
                    </div>
                {/if}
            </div>
            <div class="header-info">
                <div
                        class="connection-status {getConnectionStatusClass(
            $isConnected,
            $session.step,
          )}"
                        title="WebSocket connection status"
                >
                    {getConnectionStatusText($isConnected, $session.step)}
                </div>

                <button
                        class="theme-toggle"
                        on:click={toggleTheme}
                        title="Toggle {darkMode ? 'light' : 'dark'} mode"
                >
                    {#if darkMode}
                        <Sun size="18" class="theme-toggle-icon"/>
                    {:else}
                        <Moon size="18" class="theme-toggle-icon"/>
                    {/if}
                </button>

                {#if shouldShowSettings}
                    <div class="settings-container">
                        <button
                                class="settings-toggle"
                                on:click={toggleSettingsMenu}
                                title="Settings"
                        >
                            <Settings size="18"/>
                        </button>

                        {#if showSettingsMenu}
                            <div class="settings-dropdown">
                                <div class="settings-options">
                                    <button
                                            class="settings-option"
                                            on:click={gotoABSSetup}
                                            disabled={$session.loading}
                                    >
                                        <Headphones size="16"/>
                                        Audiobookshelf Setup
                                    </button>
                                    <button
                                            class="settings-option"
                                            on:click={gotoLLMSetup}
                                            disabled={$session.loading}
                                    >
                                        <Icon name="ai" size="16"/>
                                        LLM Setup
                                    </button>
                                </div>
                            </div>
                        {/if}
                    </div>
                {/if}
            </div>
        </div>
    </header>

    <div class="app-content">
        {#if $session.error}
            <div class="alert alert-danger mb-3 error-message">
                <strong>Error:</strong>
                {$session.error}
                <button
                        type="button"
                        class="btn btn-sm btn-outline float-right"
                        on:click={() => session.clearError()}
                >
                    Dismiss
                </button>
            </div>
        {/if}

        {#if mounted}
            {#if currentComponent === Connecting}
                <Connecting
                        message={checkingConfig ? "Checking configuration…" : null}
                />
            {:else}
                <svelte:component
                        this={currentComponent}
                        on:abs-configured={handleABSConfigured}
                        on:llm-setup-complete={handleLLMSetupComplete}
                />
            {/if}
        {:else}
            <div class="text-center p-4">
                <div class="spinner"></div>
                <p class="mt-2">Loading...</p>
            </div>
        {/if}
    </div>

    <!-- Version display in bottom right corner -->
    {#if $session.version}
        <a
                href="https://github.com/SirGibblets/achew/releases/tag/v{$session.version}"
                target="_blank"
                rel="noopener noreferrer"
                class="version-display"
                title="View release notes on GitHub"
        >
            v{$session.version}
        </a>
    {/if}
</main>

<style>
    .app {
        min-height: 100vh;
        display: flex;
        flex-direction: column;
        background: radial-gradient(
                ellipse 100% 60% at center bottom,
                color-mix(in srgb, var(--accent-1) 0%, transparent) 0%,
                color-mix(in srgb, var(--accent-2) 0%, transparent) 40%,
                transparent 100%
        ),
        var(--bg-primary);
    }

    /* Dark mode gradient originating from the top */
    :global([data-theme="dark"]) .app {
        background: radial-gradient(
                ellipse 100% 60% at center top,
                color-mix(in srgb, var(--accent-1) 14%, transparent) 0%,
                color-mix(in srgb, var(--accent-2) 8%, transparent) 40%,
                transparent 100%
        ),
        var(--bg-primary);
    }

    .app-header {
        background: transparent;
        color: var(--text-primary);
    }

    .header-content {
        margin: 0 auto;
        padding: 0.75rem 1rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    .header-left {
        display: flex;
        align-items: center;
        gap: 1rem;
    }

    .header-info {
        display: flex;
        align-items: center;
        gap: 1rem;
    }

    .connection-status {
        padding: 0.25rem 0.75rem;
        border-radius: 1rem;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        transition: all 0.1s ease;
        min-width: 80px;
        text-align: center;
    }

    .connection-status.ready {
        display: none;
        background: color-mix(in srgb, var(--text-primary) 6%, transparent);
        color: var(--text-primary);
        border: 1px solid rgba(108, 117, 125, 0.5);
    }

    .connection-status.connected {
        display: none;
        background: rgba(40, 167, 69, 0.3);
        color: color-mix(in srgb, var(--text-primary) 35%, var(--success));
        border: 1px solid rgba(40, 167, 69, 0.5);
    }

    .connection-status.disconnected {
        background: rgba(220, 53, 69, 0.3);
        color: color-mix(in srgb, var(--text-primary) 35%, var(--danger));
        border: 1px solid rgba(220, 53, 69, 0.5);
        animation: pulse 2s infinite;
    }

    @keyframes pulse {
        0% {
            opacity: 1;
        }
        50% {
            opacity: 0.7;
        }
        100% {
            opacity: 1;
        }
    }

    .theme-toggle {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 50%;
        width: 2.5rem;
        height: 2.5rem;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: all 0.1s ease;
        padding: 0;
    }

    .theme-toggle:hover {
        transform: scale(1.1);
    }

    .theme-toggle-icon {
        font-size: 1rem;
        transition: transform 0.1s ease;
    }

    .settings-container {
        position: relative;
    }

    .settings-toggle {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 50%;
        width: 2.5rem;
        height: 2.5rem;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: all 0.1s ease;
        padding: 0;
        color: var(--text-primary);
    }

    .settings-toggle:hover {
        transform: scale(1.1);
        border-color: var(--primary);
    }

    .settings-dropdown {
        position: absolute;
        top: 100%;
        right: 0;
        margin-top: 0.5rem;
        min-width: 220px;
        z-index: 1000;
    }

    .settings-options {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        overflow: hidden;
    }

    .settings-option {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        width: 100%;
        padding: 0.75rem 1rem;
        background: transparent;
        border: none;
        color: var(--text-primary);
        font-size: 0.9rem;
        cursor: pointer;
        transition: all 0.2s ease;
        text-align: left;
    }

    .settings-option:hover:not(:disabled) {
        background: var(--bg-tertiary);
        color: var(--primary);
    }

    .settings-option:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }

    .settings-option:not(:last-child) {
        border-bottom: 1px solid var(--border-color);
    }

    .app-content {
        flex: 1;
        max-width: 1200px;
        margin: 0 auto;
        width: 100%;
        padding: 2rem;
        display: flex;
        flex-direction: column;
    }

    .audiobook-info-pill {
        background: linear-gradient(
                135deg,
                color-mix(in srgb, var(--accent-1) 10%, transparent) 0%,
                color-mix(in srgb, var(--accent-2) 8%, transparent) 100%
        );
        border: 1px solid color-mix(in srgb, var(--accent-1) 15%, transparent);
        border-radius: 60px;
        padding: 0.45rem 0.6rem 0.45rem 1rem;
        display: inline-flex;
        align-items: center;
        gap: 0.75rem;
        max-width: 50vw;
    }

    .audiobook-title {
        font-size: 0.9rem;
        font-weight: 600;
        color: var(--text-primary);
        margin: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        max-width: 30vw;
    }

    .audiobook-duration {
        background: color-mix(in srgb, var(--bg-primary) 50%, transparent);
        padding: 0.125rem 0.5rem;
        border-radius: 100px;
        font-size: 0.75rem;
        color: var(--text-primary);
        white-space: nowrap;
    }

    .restart-container {
        position: relative;
    }

    .restart-toggle {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 50%;
        width: 2.5rem;
        height: 2.5rem;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: all 0.1s ease;
        padding: 0;
        color: var(--text-primary);
    }

    .restart-toggle:hover:not(:disabled) {
        transform: scale(1.1);
        border-color: var(--primary);
    }

    .restart-toggle:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }

    .restart-toggle:disabled:hover {
        transform: none;
    }

    .restart-dropdown {
        position: absolute;
        top: 100%;
        left: 0;
        margin-top: 0.5rem;
        min-width: 250px;
        z-index: 1000;
    }

    .restart-options {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        overflow: hidden;
    }

    .restart-option {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        width: 100%;
        padding: 0.75rem 1rem;
        background: transparent;
        border: none;
        color: var(--text-primary);
        font-size: 0.9rem;
        cursor: pointer;
        transition: all 0.2s ease;
        text-align: left;
    }

    .restart-option:hover:not(:disabled) {
        background: var(--bg-tertiary);
        color: var(--primary);
    }

    .restart-option:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }

    .restart-option:not(:last-child) {
        border-bottom: 1px solid var(--border-color);
    }

    .float-right {
        float: right;
        margin-left: 1rem;
    }

    .error-message {
        width: 100%;
        max-width: 900px;
        margin: 0 auto 2.5rem auto;
    }

    /* Responsive design */
    @media (max-width: 768px) {
        .header-content {
            padding: 1rem;
            gap: 0.75rem;
            text-align: center;
        }

        .header-left {
            order: -1;
            width: 100%;
        }

        .header-info {
            gap: 0.5rem;
        }

        .settings-dropdown {
            right: 50%;
            transform: translateX(50%);
            min-width: 180px;
        }

        .audiobook-info-pill {
            max-width: 90vw;
            padding: 0.4rem 0.75rem;
            gap: 0.5rem;
        }

        .audiobook-title {
            font-size: 0.85rem;
            max-width: 60vw;
        }

        .audiobook-duration {
            font-size: 0.7rem;
            padding: 0.1rem 0.4rem;
        }

        .app-content {
            padding: 1rem;
        }

        .restart-dropdown {
            left: 50%;
            transform: translateX(-50%);
            min-width: 200px;
        }
    }

    @media (max-width: 480px) {
        .header-content {
            padding: 0.75rem;
        }

        .app-content {
            padding: 0.75rem 0.75rem 2rem 0.75rem;
        }

        .connection-status {
            font-size: 0.625rem;
            padding: 0.125rem 0.5rem;
            min-width: 70px;
        }
    }

    .version-display {
        position: fixed;
        bottom: 0.25rem;
        right: 0.5rem;
        font-size: 0.75rem;
        color: var(--text-secondary);
        opacity: 0.6;
        font-family: monospace;
        text-decoration: none;
        z-index: 10;
        transition: all 0.2s ease;
        cursor: pointer;
    }

    .version-display:hover {
        opacity: 0.9;
        color: var(--primary);
        text-decoration: underline;
    }

    /* Hide on small screens to avoid clutter */
    @media (max-width: 480px) {
        .version-display {
            display: none;
        }
    }
</style>
