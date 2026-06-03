<script lang="ts">
  interface Props {
    name: string;
    sequence?: string | null;
    themed?: boolean;
  }

  let { name, sequence, themed = true }: Props = $props();
</script>

<span class="series-pill" class:themed title={sequence ? `${name} #${sequence}` : name}>
  <span class="series-label">Series:</span>
  <span class="series-name">{name}</span>
  {#if sequence}<span class="series-seq">#{sequence}</span>{/if}
</span>

<style>
  .series-pill {
    display: inline-flex;
    align-items: baseline;
    gap: 0.25rem;
    max-width: 100%;
    min-width: 0;
    padding: 0.2rem 0.5rem;
    border-radius: 100px;
    font-size: 0.7rem;
    font-weight: 500;
    color: var(--text-primary);
    border: 1px solid var(--pill-border);
  }

  .series-pill.themed {
    background: color-mix(in srgb, var(--accent-2) 12%, transparent);
    border-color: color-mix(in srgb, var(--accent-2) 45%, transparent);
  }

  .series-label {
    flex-shrink: 0;
    white-space: nowrap;
    color: var(--text-secondary);
  }

  .series-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }

  .series-seq {
    flex-shrink: 0;
    white-space: nowrap;
  }
</style>
