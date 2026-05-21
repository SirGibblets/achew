<script lang="ts">
  import { onMount } from 'svelte';
  import { session } from '../stores/session';
  import type { PreassignedTitle } from '../types/api';
  import { api } from '../utils/api';
  import ASRSettings from './ASRSettings.svelte';
  import DocLink from './DocLink.svelte';
  import AlignedTitlesPanel from './configure_asr/AlignedTitlesPanel.svelte';

  let loading = $state(false);
  let cues = $state<number[]>([]);
  let preassignedTitles = $state<PreassignedTitle[]>([]);

  let chapterRefs = $derived($session.chapterRefs ?? []);
  let toTranscribeCount = $derived(cues.length - preassignedTitles.length);

  async function loadCues() {
    try {
      const response = await api.session.getSelectedCues();
      cues = response.cues;
    } catch (error) {
      console.error('Failed to load selected cues:', error);
      cues = [];
    }
  }

  async function proceedWithTranscription() {
    if (loading) return;

    loading = true;
    try {
      await api.session.configureASR('transcribe', preassignedTitles);
    } catch (error) {
      console.error('Failed to start transcription:', error);
      session.setError('Failed to start transcription: ' + (error as Error).message);
    } finally {
      loading = false;
    }
  }

  async function skipTranscription() {
    if (loading) return;

    loading = true;
    try {
      await api.session.configureASR('skip', preassignedTitles);
    } catch (error) {
      console.error('Failed to skip transcription:', error);
      session.setError('Failed to skip transcription: ' + (error as Error).message);
    } finally {
      loading = false;
    }
  }

  onMount(async () => {
    await loadCues();
  });
</script>

<div class="configure-asr">
  <div class="header">
    <h2>
      Transcribe Titles <DocLink path="/reference/transcription/" featureName="Transcription Settings" size="16" />
    </h2>
    <p>
      Titles will be generated for <strong>{toTranscribeCount}</strong>
      chapter{toTranscribeCount !== 1 ? 's' : ''} using a local transcription model.<br />
      Configure the transcription settings below.
    </p>
  </div>

  <div class="asr-configuration">
    <ASRSettings showAdvanced={true} showOptions={true} />
  </div>

  <div class="actions">
    <button class="btn btn-cancel" onclick={skipTranscription} disabled={loading}>
      {#if loading}
        <span class="btn-spinner"></span>
        Processing…
      {:else}
        Skip Transcription
      {/if}
    </button>

    <button
      class="btn btn-verify"
      onclick={proceedWithTranscription}
      disabled={loading || (toTranscribeCount === 0 && preassignedTitles.length === 0)}
    >
      {#if loading}
        <span class="btn-spinner"></span>
        Starting…
      {:else if toTranscribeCount === 0 && preassignedTitles.length > 0}
        Apply {preassignedTitles.length} Title{preassignedTitles.length === 1 ? '' : 's'}
      {:else}
        Transcribe {toTranscribeCount} Title{toTranscribeCount === 1 ? '' : 's'}
      {/if}
    </button>
  </div>

  {#if chapterRefs.length > 0 && cues.length > 0}
    <AlignedTitlesPanel {cues} {chapterRefs} bind:preassignedTitles />
  {/if}
</div>

<style>
  .configure-asr {
    max-width: 900px;
    margin: 0 auto;
    width: 100%;
  }

  .header {
    text-align: center;
    margin-bottom: 3rem;
  }

  .header p {
    color: var(--text-secondary);
    font-size: 1rem;
    line-height: 1.5;
  }

  .header h2 {
    margin-bottom: 0.75rem;
    font-size: 2rem;
    font-weight: 600;
  }

  .asr-configuration {
    margin-bottom: 3rem;
  }

  .actions {
    display: flex;
    gap: 1rem;
    justify-content: center;
    margin-top: 2rem;
  }

  .btn-spinner {
    width: 14px;
    height: 14px;
    border: 2px solid transparent;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-right: 0.5rem;
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
    .actions {
      flex-direction: column;
      align-items: stretch;
    }
  }
</style>
