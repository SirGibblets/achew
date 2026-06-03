<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { tooltip } from './actions/tooltip';
  import { session } from './stores/session';
  import { isConnected, websocket } from './stores/websocket';

  import ABSSetup from './components/ABSSetup.svelte';
  import ASRSetup from './components/ASRSetup.svelte';
  import BookInfoDialog from './components/BookInfoDialog.svelte';
  import MigrationFailed from './components/MigrationFailed.svelte';
  import AICleanup from './components/AICleanup.svelte';
  import ChapterEditor from './components/ChapterEditor.svelte';
  import ChapterReview from './components/ChapterReview.svelte';
  import ConfigureASR from './components/ConfigureASR.svelte';
  import Connecting from './components/Connecting.svelte';
  import InitialChapterSelection from './components/InitialChapterSelection.svelte';
  import FindBook from './components/FindBook.svelte';
  import Icon from './components/Icon.svelte';
  import LLMSetup from './components/LLMSetup.svelte';
  import ProgressDisplay from './components/ProgressDisplay.svelte';
  import SelectWorkflow from './components/SelectWorkflow.svelte';
  import SubmitSuccess from './components/SubmitSuccess.svelte';
  import Welcome from './components/Welcome.svelte';

  import BookOpen from '@lucide/svelte/icons/book-open';
  import Bug from '@lucide/svelte/icons/bug';
  import ChevronLeft from '@lucide/svelte/icons/chevron-left';
  import CircleQuestionMark from '@lucide/svelte/icons/circle-question-mark';
  import Download from '@lucide/svelte/icons/download';
  import Headphones from '@lucide/svelte/icons/headphones';
  import Info from '@lucide/svelte/icons/info';
  import Lightbulb from '@lucide/svelte/icons/lightbulb';
  import Mic from '@lucide/svelte/icons/mic';
  import Moon from '@lucide/svelte/icons/moon';
  import Pencil from '@lucide/svelte/icons/pencil';
  import Settings from '@lucide/svelte/icons/settings';
  import Sun from '@lucide/svelte/icons/sun';
  import Workflow from '@lucide/svelte/icons/workflow';

  interface BuildMeta {
    branch?: string;
    commit?: string;
    commit_short?: string;
  }

  let mounted = $state(false);
  let darkMode = $state(false);
  let showRestartOptions = $state(false);
  let showBookInfo = $state(false);
  let showSettingsMenu = $state(false);
  let checkingConfig = $state(true);
  let previousStep = $state<string | null>(null);

  let latestVersion = $state<string | null>(null);
  let updateUrl = $state<string | null>(null);

  // Theme management
  function toggleTheme() {
    darkMode = !darkMode;
    updateTheme();
    localStorage.setItem('theme', darkMode ? 'dark' : 'light');
  }

  function updateTheme() {
    if (darkMode) {
      document.documentElement.setAttribute('data-theme', 'dark');
    } else {
      document.documentElement.removeAttribute('data-theme');
    }
  }

  // Initialize theme from localStorage
  function initializeTheme() {
    const savedTheme = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

    darkMode = savedTheme === 'dark' || (savedTheme === null && prefersDark);
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

  type ViewKey =
    | 'connecting'
    | 'migration_failed'
    | 'welcome'
    | 'abs_setup'
    | 'llm_setup'
    | 'asr_setup'
    | 'progress'
    | 'select_workflow'
    | 'initial_chapter_selection'
    | 'configure_asr'
    | 'chapter_editing'
    | 'ai_cleanup'
    | 'reviewing'
    | 'submit_success'
    | 'find_book';

  let currentView = $derived.by<ViewKey>(() => {
    if (!mounted) return 'connecting';
    if (checkingConfig || !$isConnected) return 'connecting';
    switch ($session.step) {
      case 'migration_failed':
        return 'migration_failed';
      case 'welcome':
        return 'welcome';
      case 'abs_setup':
        return 'abs_setup';
      case 'llm_setup':
        return 'llm_setup';
      case 'asr_setup':
        return 'asr_setup';
      case 'validating':
      case 'downloading':
      case 'file_prep':
      case 'audio_analysis':
      case 'vad_prep':
      case 'vad_analysis':
      case 'partial_scan_prep':
      case 'partial_audio_analysis':
      case 'partial_vad_analysis':
      case 'audio_extraction':
      case 'trimming':
      case 'asr_processing':
        return 'progress';
      case 'select_workflow':
        return 'select_workflow';
      case 'initial_chapter_selection':
        return 'initial_chapter_selection';
      case 'configure_asr':
        return 'configure_asr';
      case 'chapter_editing':
        return 'chapter_editing';
      case 'ai_cleanup':
        return 'ai_cleanup';
      case 'reviewing':
        return 'reviewing';
      case 'completed':
        return 'submit_success';
      default:
        return $session.step ? 'find_book' : 'connecting';
    }
  });

  $effect(() => {
    if ($session.error) {
      console.error('Session error:', $session.error);
    }
  });

  $effect(() => {
    if (mounted && $session.step && previousStep !== null && $session.step !== previousStep) {
      setTimeout(() => {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }, 0);
      previousStep = $session.step;
    } else if (mounted && $session.step && previousStep === null) {
      previousStep = $session.step;
    }
  });

  async function checkForUpdates() {
    try {
      const response = await fetch('https://api.github.com/repos/sirgibblets/achew/releases/latest');
      if (!response.ok) return;
      const data = (await response.json()) as { tag_name: string; html_url: string };
      latestVersion = data.tag_name.replace('v', '');
      updateUrl = data.html_url;
    } catch (error) {
      console.error('Failed to check for updates:', error);
    }
  }

  function isNewerVersion(current: string | null | undefined, latest: string | null): boolean {
    if (!current || !latest) return false;
    const currentParts = current.split('.').map(Number);
    const latestParts = latest.split('.').map(Number);
    for (let i = 0; i < Math.max(currentParts.length, latestParts.length); i++) {
      const currentPart = currentParts[i] || 0;
      const latestPart = latestParts[i] || 0;
      if (latestPart > currentPart) return true;
      if (latestPart < currentPart) return false;
    }
    return false;
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
      console.error('Failed to load session data:', error);
    } finally {
      checkingConfig = false;
    }

    checkForUpdates();
  });

  onDestroy(() => {
    // Cleanup stores
    session.destroy();
    websocket.destroy();
  });

  function getConnectionStatusText(connected: boolean, step: string): string {
    if (step === 'idle') return 'Ready';
    if (connected) return 'Connected';
    return 'Disconnected';
  }

  function getConnectionStatusClass(connected: boolean, step: string): string {
    if (step === 'idle') return 'ready';
    if (connected) return 'connected';
    return 'disconnected';
  }

  function handleRestartClick(event: MouseEvent) {
    event.stopPropagation();
    showRestartOptions = !showRestartOptions;
  }

  async function handleRestartFromStep(step: string) {
    showRestartOptions = false;

    if (step === 'idle') {
      await session.deleteSession();
      return;
    }

    try {
      await session.restartSession(step);
    } catch (error) {
      console.error(`Failed to restart from ${step}:`, error);
    }
  }

  function getRestartOptionLabel(step: string): string {
    switch (step) {
      case 'idle':
        return 'New Audiobook';
      case 'select_workflow':
        return 'Select Workflow';
      case 'initial_chapter_selection':
        return 'Initial Chapter Selection';
      case 'configure_asr':
        return 'Transcribe Titles';
      case 'chapter_editing':
        return 'Edit Chapters';
      default:
        return 'Unknown Step (' + step + ')';
    }
  }

  function getRestartOptionIcon(step: string) {
    switch (step) {
      case 'idle':
        return Headphones;
      case 'select_workflow':
        return Workflow;
      case 'configure_asr':
        return Mic;
      case 'chapter_editing':
        return Pencil;
      default:
        return CircleQuestionMark;
    }
  }

  function closeRestartOptions() {
    showRestartOptions = false;
  }

  function handleOutsideClick(event: MouseEvent) {
    const target = event.target as HTMLElement | null;
    if (showRestartOptions && !target?.closest('.restart-container')) {
      closeRestartOptions();
    }
    if (showSettingsMenu && !target?.closest('.settings-container')) {
      closeSettingsMenu();
    }
  }

  function shouldShowRestartButton(_restartOptions: string[]): boolean {
    return !['migration_failed', 'welcome', 'abs_setup', 'llm_setup', 'asr_setup', 'idle'].includes($session.step);
  }

  function shouldDisableRestartButton(restartOptions: string[]): boolean {
    if (restartOptions.length === 0) {
      return true;
    }
    return ![
      'select_workflow',
      'initial_chapter_selection',
      'configure_asr',
      'chapter_editing',
      'reviewing',
      'completed',
    ].includes($session.step);
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
      const response = await fetch('/api/goto-abs-setup', {
        method: 'POST',
      });

      if (response.ok) {
        // Refresh session status to trigger UI update
        await session.loadActiveSession();
      } else {
        console.error('Failed to navigate to ABS setup');
      }
    } catch (error) {
      console.error('Error navigating to ABS setup:', error);
    }
  }

  async function gotoLLMSetup() {
    closeSettingsMenu();
    try {
      const response = await fetch('/api/goto-llm-setup', {
        method: 'POST',
      });

      if (response.ok) {
        // Refresh session status to trigger UI update
        await session.loadActiveSession();
      } else {
        console.error('Failed to navigate to LLM setup');
      }
    } catch (error) {
      console.error('Error navigating to LLM setup:', error);
    }
  }

  async function gotoASRSetup() {
    closeSettingsMenu();
    try {
      const response = await fetch('/api/goto-asr-setup', {
        method: 'POST',
      });

      if (response.ok) {
        await session.loadActiveSession();
      } else {
        console.error('Failed to navigate to ASR setup');
      }
    } catch (error) {
      console.error('Error navigating to ASR setup:', error);
    }
  }

  let isConnectingView = $derived(currentView === 'connecting');
  let shouldShowSettings = $derived(
    !['migration_failed', 'welcome', 'abs_setup', 'llm_setup', 'asr_setup'].includes($session.step) &&
      !isConnectingView,
  );

  let updateAvailable = $derived(isNewerVersion($session.version, latestVersion));

  let buildMeta = $derived($session.buildMeta as BuildMeta | null);
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<main class="app" onclick={handleOutsideClick}>
  <header class="app-header">
    <div class="header-content">
      <div class="header-left">
        {#if !isConnectingView && shouldShowRestartButton($session.restartOptions)}
          <div class="restart-container">
            <button
              class="restart-toggle"
              onclick={handleRestartClick}
              disabled={$session.loading || shouldDisableRestartButton($session.restartOptions)}
              aria-label="Go back to…"
              use:tooltip={'Go back to…'}
            >
              <ChevronLeft size="20" />
            </button>

            {#if showRestartOptions}
              <div class="restart-dropdown">
                <div class="restart-options">
                  {#each $session.restartOptions as option}
                    <button
                      class="btn btn-sm btn-outline restart-option"
                      onclick={() => handleRestartFromStep(option)}
                      disabled={$session.loading}
                    >
                      {#if option === 'initial_chapter_selection'}
                        <Icon name="timeline" size="16" />
                      {:else}
                        {@const RestartIcon = getRestartOptionIcon(option)}
                        <RestartIcon size="16" />
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
          <button
            class="audiobook-info-pill"
            type="button"
            onclick={() => (showBookInfo = true)}
            use:tooltip={'View book info'}
          >
            <span class="audiobook-title">{$session.book.media.metadata.title}</span>
            <span class="audiobook-info-icon"><Info size="16" /></span>
          </button>
          <BookInfoDialog bind:isOpen={showBookInfo} />
        {/if}
      </div>
      <div class="header-info">
        <div
          class="connection-status {getConnectionStatusClass($isConnected, $session.step)}"
          use:tooltip={'WebSocket connection status'}
        >
          {getConnectionStatusText($isConnected, $session.step)}
        </div>

        <button
          class="theme-toggle"
          onclick={toggleTheme}
          aria-label="Toggle {darkMode ? 'light' : 'dark'} mode"
          use:tooltip={`Toggle ${darkMode ? 'light' : 'dark'} mode`}
        >
          {#if darkMode}
            <Sun size="18" class="theme-toggle-icon" />
          {:else}
            <Moon size="18" class="theme-toggle-icon" />
          {/if}
        </button>

        <div class="settings-container">
          <button class="settings-toggle" onclick={toggleSettingsMenu} aria-label="Settings" use:tooltip={'Settings'}>
            <Settings size="18" />
          </button>

          {#if showSettingsMenu}
            <div class="settings-dropdown">
              <div class="settings-options">
                {#if shouldShowSettings}
                  <button class="settings-option" onclick={gotoABSSetup} disabled={$session.loading}>
                    <Headphones size="16" color="var(--primary)" />
                    Audiobookshelf Setup
                  </button>
                  <button class="settings-option" onclick={gotoASRSetup} disabled={$session.loading}>
                    <Mic size="16" color="var(--primary)" />
                    Transcription Settings
                  </button>
                  <button class="settings-option" onclick={gotoLLMSetup} disabled={$session.loading}>
                    <Icon name="ai" size="16" color="var(--primary)" />
                    LLM Setup
                  </button>
                  <div class="settings-divider"></div>
                {/if}
                <a
                  class="settings-option"
                  href="https://achew.readthedocs.io/stable/"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <BookOpen size="16" color="var(--text-secondary)" />
                  View Documentation
                </a>
                <a
                  class="settings-option"
                  href="https://achew.readthedocs.io/stable/troubleshooting/logs-and-support/#filing-a-bug-report"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Bug size="16" color="var(--text-secondary)" />
                  Report a Bug
                </a>
                <a
                  class="settings-option"
                  href="https://github.com/SirGibblets/achew/discussions/categories/ideas"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Lightbulb size="16" color="var(--text-secondary)" />
                  Request a Feature
                </a>
              </div>
            </div>
          {/if}
        </div>
      </div>
    </div>
  </header>

  <div class="app-content">
    {#if $session.error}
      <div class="alert alert-danger mb-3 error-message">
        <strong>Error:</strong>
        {$session.error}
        <button type="button" class="btn btn-sm btn-outline float-right" onclick={() => session.clearError()}>
          Dismiss
        </button>
      </div>
    {/if}

    {#if mounted}
      {#if currentView === 'connecting'}
        <Connecting message={checkingConfig ? 'Checking configuration…' : null} />
      {:else if currentView === 'migration_failed'}
        <MigrationFailed onmigrationreset={() => session.loadActiveSession()} />
      {:else if currentView === 'welcome'}
        <Welcome onwelcomedismissed={() => session.loadActiveSession()} />
      {:else if currentView === 'abs_setup'}
        <ABSSetup onabsconfigured={handleABSConfigured} />
      {:else if currentView === 'llm_setup'}
        <LLMSetup onllmsetupcomplete={handleLLMSetupComplete} />
      {:else if currentView === 'asr_setup'}
        <ASRSetup onasrsetupcomplete={() => session.loadActiveSession()} />
      {:else if currentView === 'progress'}
        <ProgressDisplay />
      {:else if currentView === 'select_workflow'}
        <SelectWorkflow />
      {:else if currentView === 'initial_chapter_selection'}
        <InitialChapterSelection />
      {:else if currentView === 'configure_asr'}
        <ConfigureASR />
      {:else if currentView === 'chapter_editing'}
        <ChapterEditor />
      {:else if currentView === 'ai_cleanup'}
        <AICleanup />
      {:else if currentView === 'reviewing'}
        <ChapterReview />
      {:else if currentView === 'submit_success'}
        <SubmitSuccess />
      {:else if currentView === 'find_book'}
        <FindBook />
      {/if}
    {:else}
      <div class="text-center p-4">
        <div class="spinner"></div>
        <p class="mt-2">Loading…</p>
      </div>
    {/if}
  </div>

  <!-- Version display in bottom right corner -->
  {#if $session.version}
    <div class="version-container">
      {#if buildMeta && buildMeta.branch !== 'release'}
        <a
          href="https://github.com/SirGibblets/achew/commit/{buildMeta.commit}"
          target="_blank"
          rel="noopener noreferrer"
          class="version-display"
          use:tooltip={'View commit on GitHub'}
        >
          v{$session.version} · {buildMeta.branch} ({buildMeta.commit_short})
        </a>
      {:else}
        <a
          href="https://github.com/SirGibblets/achew/releases/tag/v{$session.version}"
          target="_blank"
          rel="noopener noreferrer"
          class="version-display"
          use:tooltip={'View release notes on GitHub'}
        >
          v{$session.version}
        </a>
        {#if updateAvailable}
          <a
            href={updateUrl}
            target="_blank"
            rel="noopener noreferrer"
            class="update-button"
            aria-label="New version available: v{latestVersion}"
            use:tooltip={`New version available: v${latestVersion}`}
          >
            <Download size={14} />
          </a>
        {/if}
      {/if}
    </div>
  {/if}
</main>

<style>
  .app {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    background:
      radial-gradient(
        ellipse 100% 60% at center bottom,
        color-mix(in srgb, var(--accent-1) 0%, transparent) 0%,
        color-mix(in srgb, var(--accent-2) 0%, transparent) 40%,
        transparent 100%
      ),
      var(--bg-primary);
  }

  /* Dark mode gradient originating from the top */
  :global([data-theme='dark']) .app {
    background:
      radial-gradient(
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
    text-decoration: none;
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

  .settings-divider {
    height: 1px;
    background: var(--border-color);
    margin-top: 0.15rem;
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
    padding: 0.45rem 0.7rem 0.45rem 1rem;
    display: inline-flex;
    align-items: center;
    gap: 0.6rem;
    max-width: 50vw;
    cursor: pointer;
    font: inherit;
    transition:
      background 0.15s ease,
      border-color 0.15s ease;
  }

  .audiobook-info-pill:hover {
    background: linear-gradient(
      135deg,
      color-mix(in srgb, var(--accent-1) 18%, transparent) 0%,
      color-mix(in srgb, var(--accent-2) 14%, transparent) 100%
    );
    border-color: color-mix(in srgb, var(--accent-1) 30%, transparent);
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

  .audiobook-info-icon {
    display: inline-flex;
    align-items: center;
    color: var(--text-secondary);
    flex-shrink: 0;
  }

  .audiobook-info-pill:hover .audiobook-info-icon {
    color: var(--text-primary);
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
      max-width: calc(100vw - 1rem);
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
      max-width: calc(100vw - 1rem);
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
    font-size: 0.75rem;
    color: var(--text-secondary);
    opacity: 0.6;
    font-family: monospace;
    text-decoration: none;
    transition: all 0.2s ease;
    cursor: pointer;
  }

  .version-display:hover {
    opacity: 0.9;
    color: var(--primary);
    text-decoration: underline;
  }

  .version-container {
    position: fixed;
    bottom: 0.25rem;
    right: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    z-index: 10;
  }

  .update-button {
    color: var(--primary);
    display: flex;
    align-items: center;
    justify-content: center;
    text-decoration: none;
    cursor: pointer;
  }

  /* Hide on small screens to avoid clutter */
  @media (max-width: 480px) {
    .version-display {
      display: none;
    }
    .version-container {
      display: none;
    }
  }
</style>
