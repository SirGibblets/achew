<script lang="ts">
  import ChevronDown from '@lucide/svelte/icons/chevron-down';

  // A text input with a suggestion list, for values that are usually but not always one of
  // `options`. Unlike a native <datalist>, opening the list (clicking the field or the chevron,
  // or pressing ArrowDown) shows every option however much is already typed; the list only
  // filters while the user is typing.

  interface Props {
    value?: string;
    options: string[];
    id?: string;
    placeholder?: string;
    /** Label for the chevron button that opens the list */
    toggleLabel?: string;
    /** The user typed in the field */
    oninput?: (value: string) => void;
    /** The user picked an option from the list */
    onselect?: (value: string) => void;
    onblur?: () => void;
  }

  let {
    value = $bindable(''),
    options,
    id,
    placeholder = '',
    toggleLabel = 'Show suggestions',
    oninput,
    onselect,
    onblur,
  }: Props = $props();

  let listId = $derived(`${id ?? 'combobox'}-options`);

  let open = $state(false);
  // What the list is filtered by: the text typed since it opened, or null for every option
  let filter = $state<string | null>(null);
  let activeIndex = $state(-1);
  let inputEl = $state<HTMLInputElement>();
  let listEl = $state<HTMLUListElement>();

  let shown = $derived.by(() => {
    const needle = filter?.trim().toLowerCase();
    return needle ? options.filter((o) => o.toLowerCase().includes(needle)) : options;
  });
  let expanded = $derived(open && shown.length > 0);

  function openList() {
    if (options.length === 0) return;
    filter = null;
    open = true;
    activeIndex = Math.max(
      0,
      options.findIndex((o) => o === value),
    );
  }

  function close() {
    open = false;
    filter = null;
    activeIndex = -1;
  }

  function select(option: string) {
    value = option;
    close();
    onselect?.(option);
  }

  function handleInput() {
    filter = value;
    open = true;
    activeIndex = -1;
    oninput?.(value);
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!expanded) {
        openList();
        return;
      }
      const step = event.key === 'ArrowDown' ? 1 : -1;
      activeIndex = (activeIndex + step + shown.length) % shown.length;
    } else if (event.key === 'Enter' && expanded && activeIndex >= 0) {
      event.preventDefault();
      select(shown[activeIndex]);
    } else if (event.key === 'Escape' && expanded) {
      event.preventDefault();
      close();
    }
  }

  function toggle() {
    if (expanded) {
      close();
    } else {
      openList();
    }
    inputEl?.focus();
  }

  function handleBlur() {
    close();
    onblur?.();
  }

  $effect(() => {
    if (expanded && activeIndex >= 0) {
      listEl?.children[activeIndex]?.scrollIntoView({ block: 'nearest' });
    }
  });
</script>

<div class="combobox" class:with-toggle={options.length > 0}>
  <input
    bind:this={inputEl}
    {id}
    type="text"
    class="combobox-input"
    role="combobox"
    aria-autocomplete="list"
    aria-expanded={expanded}
    aria-controls={listId}
    aria-activedescendant={expanded && activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined}
    {placeholder}
    autocomplete="off"
    spellcheck="false"
    bind:value
    oninput={handleInput}
    onkeydown={handleKeydown}
    onclick={() => {
      if (!expanded) openList();
    }}
    onblur={handleBlur}
  />
  {#if options.length > 0}
    <button
      type="button"
      class="combobox-toggle"
      class:open={expanded}
      tabindex="-1"
      aria-label={toggleLabel}
      onmousedown={(e) => e.preventDefault()}
      onclick={toggle}
    >
      <ChevronDown size="14" />
    </button>
  {/if}
  {#if expanded}
    <ul bind:this={listEl} id={listId} class="combobox-options" role="listbox">
      {#each shown as option, i (option)}
        <!-- Keyboard selection goes through the input (arrows + Enter, aria-activedescendant) -->
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <li
          id="{listId}-{i}"
          class="combobox-option"
          class:active={i === activeIndex}
          class:selected={option === value}
          role="option"
          aria-selected={option === value}
          onmousedown={(e) => e.preventDefault()}
          onclick={() => select(option)}
          onmouseenter={() => (activeIndex = i)}
        >
          {option}
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .combobox {
    position: relative;
    display: flex;
  }

  .combobox-input {
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

  .with-toggle .combobox-input {
    padding-right: 2.25rem;
  }

  .combobox-input:focus {
    outline: none;
    border-color: var(--primary-color);
  }

  .combobox-toggle {
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

  .combobox-toggle :global(svg) {
    transition: transform 0.2s ease;
  }

  .combobox-toggle.open :global(svg) {
    transform: rotate(180deg);
  }

  .combobox-toggle:hover {
    background: var(--bg-tertiary);
    color: var(--text-primary);
  }

  .combobox-options {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    margin: 2px 0 0;
    padding: 0;
    list-style: none;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    z-index: 1000;
    max-height: 200px;
    overflow-y: auto;
  }

  .combobox-option {
    padding: 0.5rem 0.75rem;
    font-size: 0.9rem;
    color: var(--text-primary);
    cursor: pointer;
    overflow-wrap: anywhere;
  }

  .combobox-option.active {
    background: rgba(0, 123, 255, 0.15);
  }

  .combobox-option.selected {
    background: rgba(0, 123, 255, 0.3);
  }
</style>
