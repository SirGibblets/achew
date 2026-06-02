<script lang="ts">
  import Check from '@lucide/svelte/icons/check';
  import Copy from '@lucide/svelte/icons/copy';
  import { tooltip } from '../actions/tooltip';

  interface Props {
    text: string;
    size?: number;
    label?: string;
  }

  let { text, size = 16, label = 'Copy' }: Props = $props();

  let copied = $state(false);
  let timeout: ReturnType<typeof setTimeout> | null = null;

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      copied = true;
      if (timeout) clearTimeout(timeout);
      timeout = setTimeout(() => (copied = false), 1500);
    } catch (error) {
      console.error('Failed to copy to clipboard:', error);
    }
  }
</script>

<button
  class="copy-button"
  class:copied
  type="button"
  onclick={copy}
  use:tooltip={copied ? 'Copied!' : label}
  aria-label={copied ? 'Copied' : label}
>
  {#if copied}
    <Check {size} />
  {:else}
    <Copy {size} />
  {/if}
</button>

<style>
  .copy-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.35rem;
    border: 1px solid var(--border-color);
    border-radius: 0.375rem;
    background: var(--bg-card);
    color: var(--text-secondary);
    cursor: pointer;
    transition:
      color 0.15s ease,
      border-color 0.15s ease,
      background-color 0.15s ease;
  }

  .copy-button:hover {
    color: var(--text-primary);
    background: var(--hover-bg);
  }

  .copy-button.copied {
    color: var(--primary-contrast);
    border-color: var(--primary-contrast);
  }
</style>
