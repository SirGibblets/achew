<script lang="ts">
  interface Props {
    name: string;
    size?: number | string;
    color?: string;
    className?: string;
    style?: string;
  }

  let { name, size = 24, color = 'currentColor', className = '', style = '' }: Props = $props();

  const availableIcons = ['achew-logo', 'ai', 'timeline'];

  let iconExists = $derived(name && availableIcons.includes(name));
  let isGradient = $derived(color.includes('gradient'));

  $effect(() => {
    if (name && !availableIcons.includes(name)) {
      console.warn(`Icon "${name}" not found. Available icons:`, availableIcons);
    }
  });
</script>

{#if iconExists}
  <div
    class="icon {className}"
    class:gradient={isGradient}
    style="
      --icon-size: {size}px;
      --icon-color: {color};
      --icon-url: url('/icons/{name}.svg');
      {style}
    "
    role="img"
    aria-label={name}
    title={name}
  ></div>
{:else}
  <div class="icon-error {className}" style="width: {size}px; height: {size}px; {style}" title="Icon not found: {name}">
    ?
  </div>
{/if}

<style>
  .icon {
    display: inline-block;
    flex-shrink: 0;
    width: var(--icon-size);
    height: var(--icon-size);
    background-color: var(--icon-color);
    mask: var(--icon-url) no-repeat center;
    mask-size: contain;
    -webkit-mask: var(--icon-url) no-repeat center;
    -webkit-mask-size: contain;
  }

  .icon.gradient {
    background: var(--icon-color);
    background-color: unset;
  }

  .icon-error {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    background-color: transparent;
    border: 1px solid currentColor;
    color: currentColor;
    font-size: 0.7em;
    font-weight: bold;
    opacity: 0.5;
  }
</style>
