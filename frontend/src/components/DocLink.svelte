<script lang="ts">
  import { tooltip } from '../actions/tooltip';
  import BookOpen from '@lucide/svelte/icons/book-open';

  const BASE_URL = 'https://achew.readthedocs.io/stable';

  interface Props {
    path: string;
    text?: string;
    inlineIcon?: boolean;
    size?: number | string;
    label?: string;
    featureName?: string;
  }

  let {
    path,
    text = undefined,
    inlineIcon = false,
    size = undefined,
    label = 'View documentation',
    featureName = undefined,
  }: Props = $props();

  const iconProps = $derived(size != null ? { size } : {});

  const href = $derived(BASE_URL + path);
  const tooltipText = $derived(featureName ? `View docs for ${featureName}` : 'Click to view documentation');
</script>

<a
  {href}
  target="_blank"
  rel="noopener noreferrer"
  aria-label={text ? undefined : label}
  class="doc-link"
  class:icon-only={!text}
  class:explicit-size={size != null}
  use:tooltip={{ text: tooltipText, delay: 0 }}
>
  {#if text}
    {#if inlineIcon}<BookOpen {...iconProps} class="inline-icon" />{/if}{text}
  {:else}
    <BookOpen {...iconProps} />
  {/if}
</a>

<style>
  .doc-link {
    opacity: 0.6;
    color: inherit;
    text-decoration: none;
    transition: opacity 0.15s;
    position: relative;
  }

  .doc-link.icon-only:not(.explicit-size) :global(svg),
  .doc-link:not(.explicit-size) :global(.inline-icon) {
    width: 0.9em;
    height: 0.9em;
  }

  .doc-link.icon-only:not(.explicit-size) :global(svg),
  .doc-link:not(.explicit-size) :global(.inline-icon) {
    vertical-align: -0.1em;
  }

  .doc-link.explicit-size :global(svg) {
    vertical-align: middle;
  }

  .doc-link :global(.inline-icon) {
    margin-right: 0.25rem;
  }

  .doc-link:hover {
    opacity: 1;
  }
</style>
