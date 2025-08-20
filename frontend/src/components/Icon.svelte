<script>
    export let name;
    export let size = 24;
    export let color = "currentColor";
    export let className = "";
    export let style = "";

    // List of available icons
    const availableIcons = [
        "achew-logo",
        "ai",
        "timeline",
    ];

    // Validate icon name
    $: if (name && !availableIcons.includes(name)) {
        console.warn(`Icon "${name}" not found. Available icons:`, availableIcons);
    }

    // Check if icon exists
    $: iconExists = name && availableIcons.includes(name);

    // Check if color is a gradient
    $: isGradient = color.includes("gradient");
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
    <!-- Error fallback -->
    <div
            class="icon-error {className}"
            style="width: {size}px; height: {size}px; {style}"
            title="Icon not found: {name}"
    >
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
