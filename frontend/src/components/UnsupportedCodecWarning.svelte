<script lang="ts">
  import DocLink from './DocLink.svelte';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
</script>

<div class="codec-warning-card">
  <TriangleAlert size="20" color="var(--warning)" />
  <div class="codec-warning-content">
    <p class="codec-warning-title">
      Unsupported Audio Codec (xHE-AAC) <DocLink
        path="/reference/supported-formats/#audio"
        featureName="Supported Formats"
      />
    </p>
    <p class="codec-warning-text">
      This audiobook uses a codec that is not currently supported by Achew. Features like Smart Detect, chapter
      realignment, transcription, audio playback, etc. may not work as expected.
    </p>
  </div>
</div>

<style>
  .codec-warning-card {
    display: flex;
    flex-direction: row;
    align-items: flex-start;
    gap: 0.75rem;
    padding: 1rem 1.25rem;
    background: rgba(245, 158, 11, 0.1);
    border: 0.5px solid var(--warning);
    border-radius: 8px;
  }

  .codec-warning-card :global(svg) {
    flex-shrink: 0;
    margin-top: 2px;
  }

  .codec-warning-content {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .codec-warning-title {
    margin: 0;
    font-weight: 600;
    font-size: 0.95rem;
    color: var(--warning);
  }

  .codec-warning-text {
    margin: 0;
    font-size: 0.9rem;
    line-height: 1.4;
  }
</style>
