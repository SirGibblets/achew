<script>
  import BookOpen from "@lucide/svelte/icons/book-open";

  const BASE_URL = "https://achew.readthedocs.io/stable";

  let {
    path,
    text = undefined,
    inlineIcon = false,
    size = undefined,
    label = "View documentation",
    featureName = undefined,
  } = $props();

  const iconProps = $derived(size != null ? { size } : {});

  const href = $derived(BASE_URL + path);
  const tooltip = $derived(featureName ? `View docs for ${featureName}` : "Click to view documentation");
</script>

<a
  {href}
  target="_blank"
  rel="noopener noreferrer"
  aria-label={text ? undefined : label}
  class="doc-link"
  class:icon-only={!text}
  class:explicit-size={size != null}
  data-tooltip={tooltip}
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

  .doc-link[data-tooltip]:hover::after {
    content: attr(data-tooltip);
    position: absolute;
    bottom: 100%;
    left: 50%;
    transform: translateX(-50%);
    margin-bottom: 12px;
    padding: 8px 12px;
    background: var(--bg-primary);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    font-size: 0.75rem;
    line-height: 1.4;
    white-space: nowrap;
    width: max-content;
    z-index: 10001;
    pointer-events: none;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    font-weight: normal;
  }

  .doc-link[data-tooltip]:hover::before {
    content: "";
    position: absolute;
    bottom: 100%;
    left: 50%;
    transform: translateX(-50%);
    border: 6px solid transparent;
    border-top-color: var(--border-color);
    z-index: 10002;
  }
</style>
