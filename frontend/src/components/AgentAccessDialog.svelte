<script lang="ts">
  import type { MCPSettingsResponse } from '../types';
  import { api, handleApiError } from '../utils/api';
  import { agentClientConfigs, maskToken } from '../utils/agentAccess';
  import CopyButton from './CopyButton.svelte';
  import DocLink from './DocLink.svelte';

  import Eye from '@lucide/svelte/icons/eye';
  import EyeOff from '@lucide/svelte/icons/eye-off';
  import X from '@lucide/svelte/icons/x';

  interface Props {
    isOpen?: boolean;
  }

  let { isOpen = $bindable(false) }: Props = $props();

  let settings = $state<MCPSettingsResponse | null>(null);
  let error = $state<string | null>(null);
  let saving = $state(false);
  let showToken = $state(false);
  let activeClient = $state('claude-code');

  // The server lives on the same origin as this page (Vite proxies it in development)
  let serverUrl = $derived(settings ? `${window.location.origin}${settings.path}` : '');
  let clients = $derived(settings?.token ? agentClientConfigs(serverUrl, settings.token) : []);
  let client = $derived(clients.find((c) => c.id === activeClient) ?? clients[0]);

  $effect(() => {
    if (isOpen && !settings) {
      load();
    }
  });

  async function load() {
    error = null;
    try {
      settings = await api.mcp.getSettings();
    } catch (err) {
      error = handleApiError(err);
    }
  }

  async function update(change: { enabled?: boolean; allow_submit?: boolean }) {
    saving = true;
    error = null;
    try {
      settings = await api.mcp.updateSettings(change);
    } catch (err) {
      error = handleApiError(err);
    } finally {
      saving = false;
    }
  }

  async function regenerate() {
    if (!confirm('Agents using the current token will be disconnected until they are given the new one. Continue?')) {
      return;
    }
    saving = true;
    error = null;
    try {
      settings = await api.mcp.regenerateToken();
    } catch (err) {
      error = handleApiError(err);
    } finally {
      saving = false;
    }
  }

  function close() {
    isOpen = false;
    showToken = false;
    // Reload next time, in case the settings were changed from another tab
    settings = null;
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
    aria-labelledby="agent-access-title"
    tabindex="-1"
  >
    <div class="modal-dialog">
      <div class="modal-header">
        <h3 id="agent-access-title" class="header-title">Agent Access</h3>
        <button class="close-button" onclick={close} aria-label="Close">
          <X size="20" />
        </button>
      </div>

      <div class="modal-body">
        <p>
          Let an AI agent such as Claude Code, Claude Desktop or Cursor use Achew for you through its MCP server: find
          books, run workflows, check chapter boundaries and fix titles. Its changes show up here as it works, and you
          can undo them like your own.
        </p>

        {#if error}
          <p class="message-error">{error}</p>
        {/if}

        {#if !settings}
          {#if !error}
            <p class="working"><span class="spinner"></span> Loading…</p>
          {/if}
        {:else}
          <label class="toggle-row">
            <input
              type="checkbox"
              checked={settings.enabled}
              disabled={saving}
              onchange={(e) => update({ enabled: e.currentTarget.checked })}
            />
            <span>
              <strong>Allow agents to connect</strong>
              <span class="hint">
                {#if settings.enabled}
                  Agents connect with the server address and token below.
                {:else}
                  Off: Achew's MCP server turns every agent away.
                {/if}
              </span>
            </span>
          </label>

          <label class="toggle-row">
            <input
              type="checkbox"
              checked={settings.allow_submit}
              disabled={saving}
              onchange={(e) => update({ allow_submit: e.currentTarget.checked })}
            />
            <span>
              <strong>Let agents save chapters to Audiobookshelf</strong>
              <span class="hint">
                {#if settings.allow_submit}
                  Agents are told to ask you before saving.
                {:else}
                  Agents can edit chapters, but stop at the Review screen for you to submit.
                {/if}
              </span>
            </span>
          </label>

          {#if settings.enabled && settings.token}
            <div class="field">
              <span class="field-label">Server address</span>
              <div class="command">
                <code>{serverUrl}</code>
                <CopyButton text={serverUrl} label="Copy address" />
              </div>
            </div>

            <div class="field">
              <span class="field-label">Token</span>
              <div class="command">
                <code>{showToken ? settings.token : maskToken(settings.token)}</code>
                <button
                  class="icon-button"
                  type="button"
                  onclick={() => (showToken = !showToken)}
                  aria-label={showToken ? 'Hide token' : 'Show token'}
                >
                  {#if showToken}<EyeOff size="16" />{:else}<Eye size="16" />{/if}
                </button>
                <CopyButton text={settings.token} label="Copy token" />
              </div>
              <button class="btn btn-sm btn-outline regenerate" onclick={regenerate} disabled={saving}>
                Regenerate token
              </button>
            </div>

            {#if client}
              <div class="field">
                <span class="field-label">Connect your agent</span>
                <div class="tabs" role="tablist">
                  {#each clients as option (option.id)}
                    <button
                      class="tab"
                      class:active={option.id === client.id}
                      role="tab"
                      aria-selected={option.id === client.id}
                      onclick={() => (activeClient = option.id)}
                    >
                      {option.name}
                    </button>
                  {/each}
                </div>
                <p class="hint">{client.instructions}</p>
                <div class="command snippet">
                  <pre>{showToken
                      ? client.snippet
                      : client.snippet.replace(settings.token, maskToken(settings.token))}</pre>
                  <CopyButton text={client.snippet} />
                </div>
              </div>
            {/if}

            <p class="hint">
              Anyone with the token can control Achew, so treat it like a password. If Achew is reachable from other
              machines, prefer connecting over HTTPS (for example through your reverse proxy).
            </p>
          {/if}
        {/if}

        <p class="docs">
          <DocLink path="/getting-started/agent-access/" text="More about Agent Access" inlineIcon size="14" />
        </p>
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
    max-width: 640px;
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

  .close-button,
  .icon-button {
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

  .close-button:hover,
  .icon-button:hover {
    background: var(--hover-bg);
    color: var(--text-primary);
  }

  .modal-body {
    flex: 1;
    overflow-y: auto;
    min-height: 0;
    padding: 0.5rem 1.5rem 1.25rem;
    display: flex;
    flex-direction: column;
    gap: 0.875rem;
    color: var(--text-primary);
    font-size: 0.9375rem;
    line-height: 1.5;
  }

  .modal-body p {
    margin: 0;
  }

  .toggle-row {
    display: flex;
    align-items: flex-start;
    gap: 0.625rem;
    cursor: pointer;
  }

  .toggle-row input {
    margin-top: 0.3rem;
    flex-shrink: 0;
  }

  .toggle-row > span {
    display: flex;
    flex-direction: column;
  }

  .hint {
    color: var(--text-secondary);
    font-size: 0.875rem;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
  }

  .field-label {
    font-weight: 600;
    font-size: 0.875rem;
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

  .command code,
  .command pre {
    flex: 1;
    min-width: 0;
    overflow-x: auto;
    white-space: nowrap;
    font-size: 0.8125rem;
    margin: 0;
  }

  .snippet {
    align-items: flex-start;
  }

  .snippet pre {
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    font-family: var(--font-mono, monospace);
  }

  .regenerate {
    align-self: flex-start;
  }

  .tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    border-bottom: 1px solid var(--border-color);
  }

  .tab {
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 0.375rem 0.75rem;
    color: var(--text-secondary);
    cursor: pointer;
    font-size: 0.875rem;
  }

  .tab:hover {
    color: var(--text-primary);
  }

  .tab.active {
    color: var(--primary);
    border-bottom-color: var(--primary);
  }

  .working {
    display: flex;
    align-items: center;
    gap: 0.625rem;
    color: var(--text-secondary);
  }

  .message-error {
    color: var(--danger);
  }

  .docs {
    font-size: 0.875rem;
    color: var(--text-secondary);
  }
</style>
