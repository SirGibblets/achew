<script lang="ts">
  import type { UpdateStatusResponse } from '../types';
  import { api } from '../utils/api';
  import CopyButton from './CopyButton.svelte';
  import DocLink from './DocLink.svelte';

  import ExternalLink from '@lucide/svelte/icons/external-link';
  import X from '@lucide/svelte/icons/x';

  interface Props {
    isOpen?: boolean;
    currentVersion: string;
    latestVersion: string | null;
    releaseUrl: string | null;
  }

  let { isOpen = $bindable(false), currentVersion, latestVersion, releaseUrl }: Props = $props();

  // While Achew restarts, how often to check whether it's back, and for how long. Restarting
  // reinstalls dependencies and rebuilds the app, which takes minutes on slower machines.
  const POLL_INTERVAL_MS = 2000;
  const RESTART_TIMEOUT_MS = 15 * 60 * 1000;

  const DOCKER_COMMAND = 'docker compose pull && docker compose up -d';

  type Phase = 'idle' | 'updating' | 'restarting' | 'up-to-date' | 'failed' | 'timed-out';

  let status = $state<UpdateStatusResponse | null>(null);
  let statusError = $state<string | null>(null);
  let phase = $state<Phase>('idle');
  let error = $state<string | null>(null);

  let busy = $derived(phase === 'updating' || phase === 'restarting');
  let canStart = $derived(status?.can_update === true && (phase === 'idle' || phase === 'failed'));

  $effect(() => {
    if (isOpen && !status && !statusError) {
      loadStatus();
    }
  });

  async function loadStatus() {
    try {
      status = await api.update.getStatus();
    } catch (err) {
      statusError = err instanceof Error ? err.message : String(err);
    }
  }

  async function startUpdate() {
    phase = 'updating';
    error = null;
    try {
      const result = await api.update.run();
      if (!result.updated) {
        phase = 'up-to-date';
        return;
      }
      phase = 'restarting';
      await waitForRestart();
    } catch (err) {
      phase = 'failed';
      error = err instanceof Error ? err.message : String(err);
    }
  }

  // Reloads the page once Achew has gone down and come back up.
  async function waitForRestart() {
    const deadline = Date.now() + RESTART_TIMEOUT_MS;
    let wentDown = false;
    while (Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
      try {
        await api.session.getStatus();
        if (wentDown) {
          window.location.reload();
          return;
        }
      } catch {
        wentDown = true;
      }
    }
    phase = 'timed-out';
  }

  function close() {
    if (busy) return;
    isOpen = false;
    // Check again next time, in case something about the install changed
    status = null;
    statusError = null;
    phase = 'idle';
    error = null;
  }

  function handleBackdropClick(event: MouseEvent) {
    if (event.target === event.currentTarget) {
      close();
    }
  }

  function handleBackdropKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      close();
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
    aria-labelledby="update-dialog-title"
    tabindex="-1"
  >
    <div class="modal-dialog">
      <div class="modal-header">
        <h3 id="update-dialog-title" class="header-title">Update Achew</h3>
        {#if !busy}
          <button class="close-button" onclick={close} aria-label="Close">
            <X size="20" />
          </button>
        {/if}
      </div>

      <div class="modal-body">
        <p class="versions">
          {#if latestVersion}
            Version {latestVersion} is available. You have version {currentVersion}.
          {:else}
            You have version {currentVersion}.
          {/if}
          {#if releaseUrl}
            <a href={releaseUrl} target="_blank" rel="noopener noreferrer" class="release-link">
              What's new <ExternalLink size="14" />
            </a>
          {/if}
        </p>

        {#if statusError}
          <p class="message-error">Couldn't check how this install updates: {statusError}</p>
        {:else if !status}
          <p class="working"><span class="spinner"></span> Checking this install…</p>
        {:else if status.install === 'docker'}
          <p>Docker installs update by pulling the new image. From the folder with your docker-compose.yml, run:</p>
          <div class="command">
            <code>{DOCKER_COMMAND}</code>
            <CopyButton text={DOCKER_COMMAND} />
          </div>
        {:else if !status.can_update}
          <p>{status.reason}</p>
          {#if status.command}
            <p>To update from a terminal instead, stop Achew, then run this in its folder:</p>
            <div class="command">
              <code>{status.command}</code>
              <CopyButton text={status.command} />
            </div>
          {/if}
        {:else if phase === 'updating'}
          <p class="working"><span class="spinner"></span> Downloading the update…</p>
        {:else if phase === 'restarting'}
          <p class="working">
            <span class="spinner"></span>
            Restarting Achew to finish the update. This page reloads once it's back, which can take a few minutes.
          </p>
        {:else if phase === 'up-to-date'}
          <p>Achew is already up to date.</p>
        {:else if phase === 'timed-out'}
          <p class="message-error">
            Achew hasn't come back yet. Check the terminal or window it runs in for errors, then reload this page.
          </p>
        {:else}
          <p>
            Achew downloads the update, then restarts to install it, which can take a few minutes. Restarting ends any
            work in progress on a book.
          </p>
          {#if error}
            <p class="message-error">{error}</p>
          {/if}
        {/if}

        <p class="docs">
          <DocLink path="/installation/upgrading/" text="More about upgrading" inlineIcon size="14" />
        </p>
      </div>

      {#if canStart}
        <div class="modal-footer">
          <button class="btn btn-secondary" onclick={close}>Cancel</button>
          <button class="btn btn-primary" onclick={startUpdate}
            >{phase === 'failed' ? 'Try Again' : 'Update Now'}</button
          >
        </div>
      {/if}
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
    max-width: 520px;
    max-height: 90vh;
    background: var(--bg-card);
    border-radius: 0.5rem;
    box-shadow: 0 0.5rem 1rem rgba(0, 0, 0, 0.15);
    display: flex;
    flex-direction: column;
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 1rem 1rem 0.5rem 1.5rem;
  }

  .header-title {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-primary);
  }

  .close-button {
    flex-shrink: 0;
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
    min-height: 0;
    padding: 0.5rem 1.5rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    color: var(--text-primary);
    font-size: 0.9375rem;
    line-height: 1.5;
  }

  .modal-body p {
    margin: 0;
  }

  .release-link {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    margin-left: 0.25rem;
    color: var(--primary);
    white-space: nowrap;
  }

  .working {
    display: flex;
    align-items: center;
    gap: 0.625rem;
    color: var(--text-secondary);
  }

  .working .spinner {
    flex-shrink: 0;
  }

  .command {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--border-color);
    border-radius: 0.375rem;
    background: var(--bg-secondary);
  }

  .command code {
    flex: 1;
    min-width: 0;
    overflow-x: auto;
    white-space: nowrap;
    font-size: 0.875rem;
  }

  .message-error {
    color: var(--danger);
  }

  .docs {
    font-size: 0.875rem;
    color: var(--text-secondary);
  }

  .modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
    padding: 1rem;
    border-top: 1px solid var(--border-color);
  }
</style>
