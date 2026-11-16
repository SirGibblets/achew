<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { tooltip } from '../actions/tooltip';
  import type { HostedASRConfig, HostedASRTestResponse } from '../types/api';
  import { api, handleApiError } from '../utils/api';
  import ComboboxInput from './ComboboxInput.svelte';

  import CircleAlert from '@lucide/svelte/icons/circle-alert';
  import CircleCheck from '@lucide/svelte/icons/circle-check';
  import CircleQuestionMark from '@lucide/svelte/icons/circle-question-mark';
  import Info from '@lucide/svelte/icons/info';
  import X from '@lucide/svelte/icons/x';

  // Text fields save this long after the last keystroke (or on blur)
  const SAVE_DELAY_MS = 500;
  const MAX_PARALLEL_REQUESTS = 16;

  let loaded = $state(false);
  let baseUrl = $state('');
  // A new key being typed; a saved key is never sent back to the browser
  let apiKey = $state('');
  let hasSavedKey = $state(false);
  let model = $state('');
  let skipSslVerify = $state(false);
  let parallelRequests = $state(4);

  let models = $state<string[]>([]);
  let modelsError = $state<string | null>(null);
  let testing = $state(false);
  let testResult = $state<HostedASRTestResponse | null>(null);

  let pending: Partial<HostedASRConfig> = {};
  let saveTimer: ReturnType<typeof setTimeout> | null = null;
  let saving: Promise<void> = Promise.resolve();

  function applySaved(saved: HostedASRConfig) {
    hasSavedKey = saved.api_key === '***';
  }

  function queueSave(update: Partial<HostedASRConfig>, immediate = false) {
    pending = { ...pending, ...update };
    testResult = null;
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = null;
    if (immediate) {
      void flushSave();
    } else {
      saveTimer = setTimeout(() => void flushSave(), SAVE_DELAY_MS);
    }
  }

  async function flushSave(): Promise<void> {
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = null;
    const update = pending;
    pending = {};
    if (Object.keys(update).length > 0) {
      // Chained so saves land in the order they were made
      saving = saving.then(async () => {
        try {
          applySaved(await api.config.updateHostedASR(update));
        } catch (error) {
          console.error('Failed to save transcription server settings:', error);
        }
      });
      if ('base_url' in update || 'api_key' in update || 'skip_ssl_verify' in update) {
        void saving.then(loadModels);
      }
    }
    await saving;
  }

  async function loadModels() {
    if (!baseUrl.trim()) {
      models = [];
      modelsError = null;
      return;
    }
    try {
      const response = await api.config.getHostedASRModels();
      models = response.models;
      modelsError = response.error;
    } catch (error) {
      models = [];
      modelsError = handleApiError(error);
    }
  }

  async function runTest() {
    testing = true;
    testResult = null;
    try {
      await flushSave();
      testResult = await api.config.testHostedASR();
    } catch (error) {
      testResult = { success: false, message: handleApiError(error) };
    } finally {
      testing = false;
    }
  }

  function clearSavedKey() {
    apiKey = '';
    queueSave({ api_key: '' }, true);
  }

  function handleParallelChange(event: Event) {
    const value = Math.round(Number((event.target as HTMLInputElement).value));
    parallelRequests = Number.isFinite(value) ? Math.min(Math.max(value, 1), MAX_PARALLEL_REQUESTS) : 4;
    queueSave({ parallel_requests: parallelRequests }, true);
  }

  onMount(async () => {
    try {
      const saved = await api.config.getHostedASR();
      baseUrl = saved.base_url;
      model = saved.model;
      skipSslVerify = saved.skip_ssl_verify;
      parallelRequests = saved.parallel_requests;
      applySaved(saved);
      loaded = true;
      await loadModels();
    } catch (error) {
      console.error('Failed to load transcription server settings:', error);
    }
  });

  onDestroy(() => {
    // Leaving the page shouldn't drop an edit still waiting for its save delay
    if (Object.keys(pending).length > 0) void flushSave();
  });
</script>

<div class="hosted-settings">
  {#if !loaded}
    <div class="hosted-loading">
      <div class="mini-spinner"></div>
      Loading server settings…
    </div>
  {:else}
    <div class="field">
      <label for="hosted-asr-url">
        Server URL
        <span
          class="help-icon"
          use:tooltip={{
            text: 'The API root that serves /audio/transcriptions, usually ending in /v1. For example http://192.168.1.10:8000/v1 for a self-hosted server, or https://api.openai.com/v1.',
            delay: 0,
          }}
        >
          <CircleQuestionMark size="14" />
        </span>
      </label>
      <input
        id="hosted-asr-url"
        type="text"
        class="setting-input"
        placeholder="http://192.168.1.10:8000/v1"
        autocomplete="off"
        spellcheck="false"
        bind:value={baseUrl}
        oninput={() => queueSave({ base_url: baseUrl })}
        onblur={() => void flushSave()}
      />
      {#if modelsError}
        <div class="field-message error">
          <CircleAlert size="14" />
          <span>{modelsError}</span>
        </div>
      {/if}
    </div>

    <div class="field-row">
      <div class="field">
        <label for="hosted-asr-key">API Key</label>
        <div class="input-with-action">
          <input
            id="hosted-asr-key"
            type="password"
            class="setting-input"
            placeholder={hasSavedKey ? 'Saved (type to replace)' : 'Leave blank if not required'}
            autocomplete="off"
            data-1p-ignore
            data-lpignore="true"
            data-bwignore
            data-form-type="other"
            bind:value={apiKey}
            oninput={() => queueSave({ api_key: apiKey })}
            onblur={() => void flushSave()}
          />
          {#if hasSavedKey || apiKey}
            <button
              type="button"
              class="input-action"
              aria-label="Remove API key"
              use:tooltip={'Remove API key'}
              onclick={clearSavedKey}
            >
              <X size="14" />
            </button>
          {/if}
        </div>
      </div>

      <div class="field">
        <label for="hosted-asr-model">
          Model
          <span
            class="help-icon"
            use:tooltip={{
              text: 'The model the server should use, e.g. whisper-1 for OpenAI or a model ID your server lists. Leave blank for servers that only run one model, like whisper.cpp.',
              delay: 0,
            }}
          >
            <CircleQuestionMark size="14" />
          </span>
        </label>
        <ComboboxInput
          id="hosted-asr-model"
          bind:value={model}
          options={models}
          placeholder={models.length > 0 ? 'Select or type a model' : 'Server default'}
          toggleLabel="Show the server's models"
          oninput={() => queueSave({ model })}
          onselect={() => queueSave({ model }, true)}
          onblur={() => void flushSave()}
        />
      </div>
    </div>

    <div class="field-row options-row">
      <label class="checkbox-label">
        <input
          type="checkbox"
          bind:checked={skipSslVerify}
          onchange={() => queueSave({ skip_ssl_verify: skipSslVerify }, true)}
        />
        <span class="checkbox-text">
          Skip SSL certificate verification
          <span
            class="help-icon"
            use:tooltip={{
              text: 'Allows HTTPS servers with self-signed certificates. Only enable this for servers you trust.',
              delay: 0,
            }}
          >
            <CircleQuestionMark size="14" />
          </span>
        </span>
      </label>

      <div class="parallel-field">
        <label for="hosted-asr-parallel">Parallel requests</label>
        <input
          id="hosted-asr-parallel"
          type="number"
          class="setting-input number-input"
          min="1"
          max={MAX_PARALLEL_REQUESTS}
          value={parallelRequests}
          onchange={handleParallelChange}
        />
        <span
          class="help-icon"
          use:tooltip={{
            text: 'How many chapters are sent to the server at once. More is faster on servers and services that handle requests in parallel; lower it if the server is overloaded or rate-limits you.',
            delay: 0,
          }}
        >
          <CircleQuestionMark size="14" />
        </span>
      </div>
    </div>

    <div class="test-row">
      <button type="button" class="btn btn-outline test-button" onclick={runTest} disabled={testing || !baseUrl.trim()}>
        {#if testing}
          <span class="btn-spinner"></span>
          Testing…
        {:else}
          Test Connection
        {/if}
      </button>
      {#if testResult}
        <div class="field-message" class:error={!testResult.success} class:success={testResult.success}>
          {#if testResult.success}
            <CircleCheck size="14" />
          {:else}
            <CircleAlert size="14" />
          {/if}
          <span>{testResult.message}</span>
        </div>
      {/if}
    </div>

    <div class="privacy-note">
      <Info size="14" />
      <span>The first few seconds of each chapter's audio are sent to this server for transcription.</span>
    </div>
  {/if}
</div>

<style>
  .hosted-settings {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .hosted-loading {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--text-secondary);
    font-size: 0.9rem;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    flex: 1;
    min-width: 0;
  }

  .field label,
  .parallel-field label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 500;
    color: var(--text-primary);
    font-size: 0.9rem;
  }

  .field-row {
    display: flex;
    gap: 1rem;
  }

  .setting-input {
    width: 100%;
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background: var(--bg-primary);
    color: var(--text-primary);
    font-size: 0.9rem;
    font-family: inherit;
    transition: border-color 0.2s ease;
  }

  .setting-input:focus {
    outline: none;
    border-color: var(--primary-color);
  }

  .input-with-action {
    position: relative;
    display: flex;
  }

  .input-with-action .setting-input {
    padding-right: 2.25rem;
  }

  .input-action {
    position: absolute;
    right: 0.4rem;
    top: 50%;
    transform: translateY(-50%);
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
  }

  .input-action:hover {
    background: var(--bg-tertiary);
    color: var(--text-primary);
  }

  .options-row {
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
  }

  .checkbox-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
    font-size: 0.9rem;
    color: var(--text-primary);
    margin: 0;
  }

  .checkbox-label input {
    cursor: pointer;
    margin: 0;
  }

  .checkbox-text {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 500;
  }

  .parallel-field {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .number-input {
    width: 4.5rem;
  }

  .test-row {
    display: flex;
    align-items: center;
    gap: 1rem;
    flex-wrap: wrap;
  }

  .test-button {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.45rem 1rem;
    font-size: 0.9rem;
    border-radius: 6px;
  }

  .test-button .btn-spinner {
    width: 12px;
    height: 12px;
    margin-right: 0.25rem;
  }

  .field-message {
    display: flex;
    align-items: flex-start;
    gap: 0.4rem;
    font-size: 0.85rem;
    line-height: 1.4;
    color: var(--text-secondary);
    flex: 1;
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .field-message :global(svg) {
    flex-shrink: 0;
    margin-top: 0.1rem;
  }

  .field-message.error {
    color: var(--danger);
  }

  .field-message.success {
    color: var(--success);
  }

  .privacy-note {
    display: flex;
    align-items: flex-start;
    gap: 0.4rem;
    font-size: 0.8rem;
    color: var(--text-muted);
  }

  .privacy-note :global(svg) {
    flex-shrink: 0;
    margin-top: 0.1rem;
  }

  .help-icon {
    color: var(--text-secondary);
    padding: 2px;
    border-radius: 50%;
    cursor: help;
    display: flex;
  }

  .help-icon:hover {
    color: var(--primary-color);
    background: var(--bg-tertiary);
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

  @media (max-width: 768px) {
    .field-row {
      flex-direction: column;
      gap: 1rem;
    }

    .options-row {
      align-items: flex-start;
    }
  }
</style>
