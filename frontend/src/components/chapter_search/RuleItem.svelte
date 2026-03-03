<script>
    import {createEventDispatcher} from 'svelte';
    import Pencil from '@lucide/svelte/icons/pencil';
    import {autoRuleName} from './ruleUtils.js';

    export let rule;
    export let dragHandleListeners = null;  // passed in from dndzone

    const dispatch = createEventDispatcher();

    $: displayName = autoRuleName(rule);

    function toggleEnabled() {
        dispatch('toggle', {...rule, enabled: !rule.enabled});
    }

    function openEdit() {
        dispatch('edit', rule);
    }
</script>

<div class="rule-item" class:disabled={!rule.enabled}>
    <!-- Drag handle / enabled toggle area -->
    <label class="enable-toggle" title={rule.enabled ? 'Disable rule' : 'Enable rule'}>
        <input type="checkbox" checked={rule.enabled} on:change={toggleEnabled} />
    </label>

    <span class="rule-name" title={displayName}>{displayName}</span>

    <button class="edit-btn" on:click={openEdit} aria-label="Edit rule" title="Edit rule">
        <Pencil size="14"/>
    </button>
</div>

<style>
    .rule-item {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.5rem 0.75rem;
        background: var(--bg-primary);
        border: 1px solid var(--border-color);
        border-radius: 6px;
        cursor: default;
        user-select: none;
    }

    .rule-item.disabled {
        opacity: 0.5;
    }

    .enable-toggle {
        display: flex;
        align-items: center;
        cursor: pointer;
        flex-shrink: 0;
    }

    .enable-toggle input[type="checkbox"] {
        width: 1rem;
        height: 1rem;
        cursor: pointer;
    }

    .rule-name {
        flex: 1;
        font-size: 0.875rem;
        color: var(--text-primary);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .edit-btn {
        background: none;
        border: none;
        cursor: pointer;
        color: var(--text-secondary);
        padding: 0.25rem;
        display: flex;
        align-items: center;
        flex-shrink: 0;
        border-radius: 4px;
    }
    .edit-btn:hover {
        color: var(--text-primary);
        background: var(--bg-secondary);
    }
</style>
