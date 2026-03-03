<script>
    import {createEventDispatcher} from 'svelte';
    import X from '@lucide/svelte/icons/x';

    export let open = false;
    export let ruleset = null;      // null = adding new; object = editing existing
    export let isRoot = false;

    const dispatch = createEventDispatcher();

    let dialog;
    let name = '';
    let matchAny = true;
    let showDeleteConfirm = false;

    $: if (open && ruleset) {
        name = ruleset.name || '';
        matchAny = ruleset.match_any !== false;
        showDeleteConfirm = false;
    } else if (open && !ruleset) {
        name = '';
        matchAny = true;
        showDeleteConfirm = false;
    }

    $: if (dialog) {
        if (open) dialog.showModal();
        else dialog.close();
    }

    function close() {
        open = false;
        dispatch('close');
    }

    function handleBackdropClick(e) {
        if (e.target === dialog) close();
    }

    function save() {
        dispatch('save', {
            ...ruleset,
            name: name.trim(),
            match_any: matchAny,
            id: ruleset?.id || crypto.randomUUID(),
            enabled: ruleset?.enabled !== false,
            items: ruleset?.items || [],
        });
        close();
    }

    function handleDelete() {
        if (!showDeleteConfirm) {
            showDeleteConfirm = true;
            return;
        }
        dispatch('delete', ruleset);
        close();
    }

    function handleClone() {
        dispatch('clone', {
            ...ruleset,
            name: name.trim(),
            match_any: matchAny,
        });
        close();
    }
</script>

<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
<dialog bind:this={dialog} on:click={handleBackdropClick} on:close={close}>
    <div class="dialog-container">
        <div class="dialog-header">
            <h3>{ruleset ? 'Edit Rule Set' : 'Add Rule Set'}</h3>
            <button class="close-btn" on:click={close} aria-label="Close"><X size="18"/></button>
        </div>

        <div class="dialog-body">
            <div class="field">
                <label for="rs-name">Name <span class="hint">(leave blank for "Rule Set")</span></label>
                <input id="rs-name" type="text" bind:value={name} placeholder="Rule Set" />
            </div>

            <div class="field">
                <span class="field-label">Logic</span>
                <div class="toggle-group">
                    <button
                        class="toggle-btn {matchAny ? 'active' : ''}"
                        on:click={() => matchAny = true}
                        type="button"
                    >
                        Match Any
                    </button>
                    <button
                        class="toggle-btn {!matchAny ? 'active' : ''}"
                        on:click={() => matchAny = false}
                        type="button"
                    >
                        Match All
                    </button>
                </div>
            </div>

            {#if isRoot && showDeleteConfirm}
                <div class="warning-box">
                    <strong>Warning:</strong> Deleting the main rule set will permanently delete all rules
                    and replace them with the default starting rules.
                </div>
            {:else if showDeleteConfirm}
                <div class="warning-box">
                    <strong>Warning:</strong> This will permanently delete this rule set and all rules
                    and nested sets inside it.
                </div>
            {/if}
        </div>

        <div class="dialog-footer">
            {#if ruleset}
                <button
                    class="btn btn-danger"
                    on:click={handleDelete}
                >
                    {showDeleteConfirm ? 'Confirm Delete' : 'Delete'}
                </button>
            {/if}
            {#if ruleset && !isRoot}
                <button class="btn btn-secondary" on:click={handleClone}>Clone</button>
            {/if}
            <div class="footer-right">
                <button class="btn btn-secondary" on:click={close}>Cancel</button>
                <button class="btn btn-primary" on:click={save}>Save</button>
            </div>
        </div>
    </div>
</dialog>

<style>
    dialog {
        padding: 0;
        border: none;
        border-radius: 12px;
        background: transparent;
        max-width: 90vw;
        width: 480px;
    }

    dialog::backdrop {
        background: rgba(0, 0, 0, 0.6);
        backdrop-filter: blur(2px);
    }

    .dialog-container {
        background: var(--bg-primary);
        border-radius: 12px;
        border: 1px solid var(--border-color);
    }

    .dialog-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1rem 1.25rem;
        border-bottom: 1px solid var(--border-color);
    }

    .dialog-header h3 { margin: 0; font-size: 1rem; font-weight: 600; color: var(--text-primary); }

    .close-btn {
        background: none; border: none; cursor: pointer;
        color: var(--text-secondary); padding: 0.25rem;
        display: flex; align-items: center;
    }
    .close-btn:hover { color: var(--text-primary); }

    .dialog-body {
        padding: 1.25rem;
        display: flex;
        flex-direction: column;
        gap: 1rem;
    }

    .field { display: flex; flex-direction: column; gap: 0.375rem; }

    .field label, .field .field-label {
        font-size: 0.875rem;
        font-weight: 500;
        color: var(--text-primary);
    }

    .hint { font-weight: 400; color: var(--text-secondary); }

    .field input {
        padding: 0.5rem 0.75rem;
        border: 1px solid var(--border-color);
        border-radius: 6px;
        background: var(--bg-secondary);
        color: var(--text-primary);
        font-size: 0.9375rem;
    }

    .toggle-group {
        display: flex;
        border: 1px solid var(--border-color);
        border-radius: 6px;
        overflow: hidden;
    }

    .toggle-btn {
        flex: 1;
        padding: 0.5rem 1rem;
        background: var(--bg-secondary);
        border: none;
        cursor: pointer;
        font-size: 0.875rem;
        color: var(--text-secondary);
        transition: background 0.15s, color 0.15s;
    }

    .toggle-btn + .toggle-btn {
        border-left: 1px solid var(--border-color);
    }

    .toggle-btn.active {
        background: var(--primary);
        color: white;
    }

    .warning-box {
        padding: 0.75rem 1rem;
        background: color-mix(in srgb, var(--danger) 10%, transparent);
        border: 1px solid var(--danger);
        border-radius: 6px;
        font-size: 0.875rem;
        color: var(--text-primary);
    }

    .dialog-footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.5rem;
        padding: 1rem 1.25rem;
        border-top: 1px solid var(--border-color);
    }

    .footer-right { display: flex; gap: 0.5rem; margin-left: auto; }

    .btn-danger { background: var(--danger); color: white; }
    .btn-danger:hover { opacity: 0.9; }
</style>
