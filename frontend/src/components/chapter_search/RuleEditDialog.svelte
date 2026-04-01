<script>
    import {createEventDispatcher} from 'svelte';
    import X from '@lucide/svelte/icons/x';
    import Plus from '@lucide/svelte/icons/plus';
    import Trash2 from '@lucide/svelte/icons/trash-2';
    import {
        SUBJECT_LABELS, MULTI_PREDICATE_SUBJECTS,
        autoRuleName, createBlankPredicate,
    } from './ruleUtils.js';

    export let open = false;
    export let rule = null;     // null = new rule

    const dispatch = createEventDispatcher();

    let dialog;
    let name = '';
    let subject = 'any_chapter';
    let predicates = [];
    let showDeleteConfirm = false;

    // Contextual help text
    const SUBJECT_HELP = {
        every_middle_chapter: 'Every chapter except the first and last.',
        any_middle_chapter: 'Any chapter (excluding the first and last).',
        most_every_chapter: 'At least two-thirds of chapters.',
    };

    const PART2_HELP = {
        text_similar: 'Matches text that is similar to the provided value (does not require an exact match). Always case-insensitive.',
        book_title_similar: 'Matches text that is similar to the book title (does not require an exact match). Always case-insensitive.',
        regex: 'Uses Python regular expression syntax. You can test your regex patterns <a href="https://regex101.com" target="_blank" rel="noopener noreferrer">here</a> (set flavor to Python).',
    };

    $: subjectHelp = SUBJECT_HELP[subject] || null;

    $: if (open) {
        if (rule) {
            name = rule.name || '';
            subject = rule.subject || 'any_chapter';
            predicates = JSON.parse(JSON.stringify(rule.predicates || []));
        } else {
            name = '';
            subject = 'any_chapter';
            predicates = [createBlankPredicate('any_chapter')];
        }
        showDeleteConfirm = false;
    }

    $: if (dialog) {
        if (open) dialog.showModal();
        else dialog.close();
    }

    $: isCountSubject = subject === 'chapter_count';
    $: canMultiPredicate = MULTI_PREDICATE_SUBJECTS.has(subject);

    function handleSubjectChange() {
        // Reset predicates only when switching between count and text subjects
        const wasCount = predicates.length > 0 && predicates[0].kind === 'count';
        const nowCount = subject === 'chapter_count';
        if (wasCount !== nowCount) {
            predicates = [createBlankPredicate(subject)];
        }
    }

    function addPredicate() {
        predicates = [...predicates, createBlankPredicate(subject)];
    }

    function removePredicate(i) {
        predicates = predicates.filter((_, idx) => idx !== i);
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
            ...(rule || {}),
            id: rule?.id || crypto.randomUUID(),
            name: name.trim(),
            subject,
            predicates: predicates.map(p => ({...p})),
            enabled: rule?.enabled !== false,
        });
        close();
    }

    function handleDelete() {
        if (!showDeleteConfirm) { showDeleteConfirm = true; return; }
        dispatch('delete', rule);
        close();
    }

    function handleClone() {
        dispatch('clone', {
            ...(rule || {}),
            id: rule?.id || crypto.randomUUID(),
            name: name.trim(),
            subject,
            predicates: predicates.map(p => ({...p})),
            enabled: rule?.enabled !== false,
        });
        close();
    }

    // Preview name
    $: previewRule = {name: name.trim(), subject, predicates};
    $: previewName = autoRuleName(previewRule);

    // Part2 options that need a value input
    function needsTextValue(part2) { return part2 === 'text' || part2 === 'text_similar' || part2 === 'regex'; }
    function needsNumberValue(part2) { return false; /* number value is in count predicates */ }
    function showIgnoreCase(pred) { return pred.kind === 'text' && (pred.part2 === 'text' || pred.part2 === 'regex'); }

    function isMatchesOp(op) { return op === 'is' || op === 'is_not'; }

    function handleOpChange(pred) {
        if (!isMatchesOp(pred.op) && pred.part2 === 'regex') {
            pred.part2 = 'text';
            predicates = predicates;
        }
    }
</script>

<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
<dialog bind:this={dialog} on:click={handleBackdropClick} on:close={close}>
    <div class="dialog-container">
        <div class="dialog-header">
            <h3>{rule ? 'Edit Rule' : 'Add Rule'}</h3>
            <button class="close-btn" on:click={close} aria-label="Close"><X size="18"/></button>
        </div>

        <div class="dialog-body">
            <!-- Custom name -->
            <div class="field">
                <label for="rule-name">
                    Name <span class="hint">(leave blank to use auto-generated name)</span>
                </label>
                <input
                    id="rule-name"
                    type="text"
                    bind:value={name}
                    placeholder={previewName}
                />
            </div>

            <!-- Subject -->
            <div class="field">
                <label for="rule-subject">Target</label>
                <select id="rule-subject" bind:value={subject} on:change={handleSubjectChange}>
                    {#each Object.entries(SUBJECT_LABELS) as [val, label]}
                        <option value={val}>{label}</option>
                    {/each}
                </select>
                {#if subjectHelp}
                    <div class="context-help">{subjectHelp}</div>
                {/if}
            </div>

            <!-- Conditions -->
            <div class="field">
                <span class="field-label">
                    {#if canMultiPredicate}
                        Conditions
                    {:else}
                        Condition
                    {/if}
                </span>

                {#each predicates as pred, i (i)}
                    {#if i > 0}
                        <div class="pred-and">AND</div>
                    {/if}
                    <div class="predicate-row">
                        {#if isCountSubject}
                            <!-- Count predicate -->
                            <select bind:value={pred.op} class="pred-op">
                                <option value="is">is</option>
                                <option value="is_not">is not</option>
                                <option value="less_than">is less than</option>
                                <option value="not_less_than">is not less than</option>
                                <option value="greater_than">is greater than</option>
                                <option value="not_greater_than">is not greater than</option>
                            </select>
                            <input
                                type="number"
                                class="pred-value"
                                bind:value={pred.value}
                                min="0"
                                max="9999"
                                placeholder="0"
                            />
                        {:else}
                            <!-- Text predicate -->
                            <select bind:value={pred.op} class="pred-op" on:change={() => handleOpChange(pred)}>
                                <option value="is">matches</option>
                                <option value="is_not">does not match</option>
                                <option value="contains">contains</option>
                                <option value="does_not_contain">does not contain</option>
                                <option value="starts_with">starts with</option>
                                <option value="does_not_start_with">does not start with</option>
                                <option value="ends_with">ends with</option>
                                <option value="does_not_end_with">does not end with</option>
                            </select>
                            <select bind:value={pred.part2} class="pred-part2">
                                <option value="text">the text</option>
                                <option value="text_similar">text similar to</option>
                                <option value="number">a number</option>
                                <option value="book_title_exact">the book title (exact)</option>
                                <option value="book_title_similar">the book title (similar)</option>
                                {#if isMatchesOp(pred.op)}
                                    <option value="regex">the regex</option>
                                {/if}
                            </select>
                            {#if needsTextValue(pred.part2)}
                                <input
                                    type="text"
                                    class="pred-value"
                                    bind:value={pred.value}
                                    placeholder={pred.part2 === 'regex' ? 'regex pattern' : 'text value'}
                                />
                            {/if}
                            {#if showIgnoreCase(pred)}
                                <label class="ignore-case">
                                    <input type="checkbox" bind:checked={pred.ignore_case} />
                                    Ignore case
                                </label>
                            {/if}
                        {/if}

                        {#if canMultiPredicate && predicates.length > 1}
                            <button
                                class="remove-pred-btn"
                                on:click={() => removePredicate(i)}
                                aria-label="Remove condition"
                                type="button"
                            >
                                <Trash2 size="14"/>
                            </button>
                        {/if}
                    </div>
                    {#if PART2_HELP[pred.part2]}
                        <div class="context-help">{@html PART2_HELP[pred.part2]}</div>
                    {/if}
                {/each}

                {#if canMultiPredicate}
                    <button class="add-pred-btn" on:click={addPredicate} type="button">
                        <Plus size="14"/> Add condition
                    </button>
                {/if}
            </div>

            {#if showDeleteConfirm}
                <div class="warning-box">
                    <strong>Are you sure?</strong> This rule will be permanently deleted.
                </div>
            {/if}
        </div>

        <div class="dialog-footer">
            {#if rule}
                <button class="btn btn-danger" on:click={handleDelete}>
                    {showDeleteConfirm ? 'Confirm Delete' : 'Delete'}
                </button>
            {/if}
            {#if rule}
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
        width: 560px;
        max-height: 90vh;
    }

    dialog::backdrop {
        background: rgba(0, 0, 0, 0.6);
        backdrop-filter: blur(2px);
    }

    .dialog-container {
        background: var(--bg-primary);
        border-radius: 12px;
        border: 1px solid var(--border-color);
        display: flex;
        flex-direction: column;
        max-height: 85vh;
    }

    .dialog-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1rem 1.25rem;
        border-bottom: 1px solid var(--border-color);
        flex-shrink: 0;
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
        overflow-y: auto;
    }

    .field { display: flex; flex-direction: column; gap: 0.5rem; }

    .field > label, .field > .field-label {
        font-size: 0.875rem;
        font-weight: 500;
        color: var(--text-primary);
    }

    .hint { font-weight: 400; color: var(--text-secondary); }

    .field input[type="text"],
    .field input[type="number"],
    .field select {
        padding: 0.5rem 0.75rem;
        border: 1px solid var(--border-color);
        border-radius: 6px;
        background: var(--bg-secondary);
        color: var(--text-primary);
        font-size: 0.9375rem;
        width: 100%;
    }

    .pred-and {
        font-size: 0.6875rem;
        font-weight: 700;
        letter-spacing: 0.06em;
        color: var(--text-secondary);
        text-align: center;
        padding: 0.125rem 0;
    }

    .predicate-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
        align-items: center;
        padding: 0.75rem;
        background: var(--bg-secondary);
        border: 1px solid var(--border-color);
        border-radius: 6px;
    }

    .pred-op {
        min-width: 160px;
        flex-shrink: 0;
        padding: 0.375rem 0.5rem;
        border: 1px solid var(--border-color);
        border-radius: 6px;
        background: var(--bg-tertiary);
        color: var(--text-primary);
        font-size: 0.875rem;
        width: auto;
    }

    .pred-part2 {
        min-width: 180px;
        flex-shrink: 0;
        padding: 0.375rem 0.5rem;
        border: 1px solid var(--border-color);
        border-radius: 6px;
        background: var(--bg-tertiary);
        color: var(--text-primary);
        font-size: 0.875rem;
        width: auto;
    }

    .pred-value {
        flex: 1;
        min-width: 120px;
        padding: 0.375rem 0.5rem;
        border: 1px solid var(--border-color);
        border-radius: 6px;
        background: var(--bg-tertiary);
        color: var(--text-primary);
        font-size: 0.875rem;
        width: auto !important;
    }

    .ignore-case {
        display: flex;
        align-items: center;
        gap: 0.375rem;
        font-size: 0.8125rem;
        color: var(--text-secondary);
        white-space: nowrap;
        cursor: pointer;
    }

    .remove-pred-btn {
        background: none;
        border: none;
        cursor: pointer;
        color: var(--text-secondary);
        padding: 0.25rem;
        display: flex;
        align-items: center;
        margin-left: auto;
    }
    .remove-pred-btn:hover { color: var(--danger); }

    .add-pred-btn {
        display: flex;
        align-items: center;
        gap: 0.375rem;
        padding: 0.375rem 0.75rem;
        background: none;
        border: 1px dashed var(--border-color);
        border-radius: 6px;
        color: var(--text-secondary);
        font-size: 0.875rem;
        cursor: pointer;
        align-self: flex-start;
    }
    .add-pred-btn:hover { color: var(--text-primary); border-color: var(--text-secondary); }

    .context-help {
        font-size: 0.8125rem;
        color: var(--text-secondary);
        margin-top: 0.125rem;
    }
    .context-help :global(a) {
        color: var(--primary);
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
        flex-shrink: 0;
    }

    .footer-right { display: flex; gap: 0.5rem; margin-left: auto; }
    .btn-danger { background: var(--danger); color: white; }
    .btn-danger:hover { opacity: 0.9; }
</style>
