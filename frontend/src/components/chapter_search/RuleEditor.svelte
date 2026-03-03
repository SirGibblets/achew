<script>
    /**
     * RuleEditor — recursive rule/ruleset list with drag-and-drop.
     *
     * Svelte 5 runes component.
     * Accepts callbacks: onchange(ruleset), onresetToDefaults(), ondeleteSelf()
     */
    import { onMount } from "svelte";
    import { DragDropProvider, DragOverlay } from "@dnd-kit-svelte/svelte";
    import { CollisionPriority } from "@dnd-kit/abstract";
    import { move } from "@dnd-kit/helpers";
    import Plus from "@lucide/svelte/icons/plus";
    import FolderPlus from "@lucide/svelte/icons/folder-plus";
    import Pencil from "@lucide/svelte/icons/pencil";

    import SortableItem from "./SortableItem.svelte";
    import RuleEditor from "./RuleEditor.svelte";
    import RuleEditDialog from "./RuleEditDialog.svelte";
    import RuleSetEditDialog from "./RuleSetEditDialog.svelte";
    import {
        autoRuleName,
        autoRuleSetName,
        createBlankRule,
        createBlankRuleSet,
        cloneItem,
        deepCloneWithNewIds,
    } from "./ruleUtils.js";

    let {
        ruleset,
        isRoot = false,
        inheritedItemsMap = null,
        ancestorDisabled = false,
        isOverlay = false,
        onchange,
        onresetToDefaults,
        ondeleteSelf,
        oncloneSelf,
    } = $props();

    let rulesetId = $derived(ruleset.id || "root");

    // Suppress HierarchyRequestError from dnd-kit's internal DOM reorder
    // when dragging nested sortable containers (rulesets).
    onMount(() => {
        if (!isRoot) return;
        function suppress(e) {
            if (e.reason?.name === "HierarchyRequestError") {
                e.preventDefault();
            }
        }
        window.addEventListener("unhandledrejection", suppress);
        return () => window.removeEventListener("unhandledrejection", suppress);
    });

    // --- Global Tree State for Drag & Drop ---
    // Instead of local items per level, the root manages the entire tree mapped by container ID.
    let rootItemsMap = $state({});

    $effect(() => {
        if (isRoot && !isOverlay) {
            rootItemsMap = flattenTree(ruleset);
        }
    });

    let effectiveItemsMap = $derived(isRoot ? rootItemsMap : inheritedItemsMap);
    let currentItems = $derived(
        effectiveItemsMap
            ? effectiveItemsMap[rulesetId] || []
            : ruleset.items || [],
    );

    // Helper functions to manage the tree as an items map for dnd-kit `move`
    function flattenTree(node, map = {}) {
        const id = node.id || "root";
        map[id] = [...(node.items || [])];
        for (const child of node.items || []) {
            if (isRuleSet(child)) {
                flattenTree(child, map);
            }
        }
        return map;
    }

    function rebuildTree(node, map) {
        if (!isRuleSet(node)) return node;
        const id = node.id || "root";
        const newItems = (map[id] || []).map((child) =>
            rebuildTree(child, map),
        );
        return { ...node, items: newItems };
    }

    function findItemInMap(id) {
        for (const items of Object.values(rootItemsMap)) {
            const found = items.find((it) => it.id === id);
            if (found) return found;
        }
        return null;
    }

    // Dialog state
    let editingRule = $state(null);
    let editingRuleSet = $state(null);
    let ruleDialogOpen = $state(false);
    let ruleSetDialogOpen = $state(false);
    let addingRule = $state(false);
    let addingRuleSet = $state(false);

    function isRuleSet(item) {
        return Array.isArray(item.items);
    }

    // --- DnD handlers (Root Only) ---

    function findContainerOf(itemId) {
        for (const [containerId, children] of Object.entries(rootItemsMap)) {
            if (children.some((child) => child.id === itemId)) {
                return containerId;
            }
        }
        return null;
    }

    function isOrDescendantOf(containerId, ancestorId) {
        if (containerId === ancestorId) return true;
        const children = rootItemsMap[ancestorId];
        if (!children) return false;
        for (const child of children) {
            if (
                child.id in rootItemsMap &&
                isOrDescendantOf(containerId, child.id)
            )
                return true;
        }
        return false;
    }

    function handleDragOver(event) {
        if (!isRoot || isOverlay) return;
        // Prevent a ruleset from being moved into itself or its descendants
        const sourceId = event.operation?.source?.id;
        if (sourceId && sourceId in rootItemsMap) {
            const targetId = event.operation?.target?.id;
            if (targetId) {
                const targetContainer = findContainerOf(targetId);
                if (
                    targetContainer &&
                    isOrDescendantOf(targetContainer, sourceId)
                ) {
                    return;
                }
            }
        }
        // The dnd-kit `move` helper moves an item between arrays in an object record.
        rootItemsMap = move(rootItemsMap, event);
    }

    function handleDragEnd(event) {
        if (!isRoot || isOverlay) return;
        if (!event.canceled) {
            onchange?.(rebuildTree(ruleset, rootItemsMap));
        }
    }

    // --- Propagate changes ---

    function handleChildChange(index, updatedChild) {
        const newItems = currentItems.map((item, i) =>
            i === index ? updatedChild : item,
        );
        onchange?.({ ...ruleset, items: newItems });
    }

    function handleToggle(item) {
        const newItems = currentItems.map((it) =>
            it.id === item.id ? { ...item, enabled: !item.enabled } : it,
        );
        onchange?.({ ...ruleset, items: newItems });
    }

    function handleDeleteChildRuleSet(id) {
        const newItems = currentItems.filter((item) => item.id !== id);
        onchange?.({ ...ruleset, items: newItems });
    }

    // --- Dialog openers ---

    function openEditRule(rule) {
        editingRule = cloneItem(rule);
        addingRule = false;
        ruleDialogOpen = true;
    }

    function openEditRuleSet(rs) {
        editingRuleSet = cloneItem(rs);
        addingRuleSet = false;
        ruleSetDialogOpen = true;
    }

    function addRule() {
        editingRule = createBlankRule();
        addingRule = true;
        ruleDialogOpen = true;
    }

    function addRuleSet() {
        editingRuleSet = createBlankRuleSet();
        addingRuleSet = true;
        ruleSetDialogOpen = true;
    }

    function handleSaveRule(e) {
        const saved = e.detail;
        const newItems = addingRule
            ? [...currentItems, saved]
            : currentItems.map((item) => (item.id === saved.id ? saved : item));
        onchange?.({ ...ruleset, items: newItems });
        ruleDialogOpen = false;
        editingRule = null;
        addingRule = false;
    }

    function handleDeleteRule(e) {
        const deleted = e.detail;
        const newItems = currentItems.filter((item) => item.id !== deleted.id);
        onchange?.({ ...ruleset, items: newItems });
        ruleDialogOpen = false;
        editingRule = null;
    }

    function handleCloneRule(e) {
        const original = e.detail;
        const clone = deepCloneWithNewIds(original);
        const idx = currentItems.findIndex((item) => item.id === original.id);
        const newItems = idx >= 0
            ? [...currentItems.slice(0, idx + 1), clone, ...currentItems.slice(idx + 1)]
            : [...currentItems, clone];
        onchange?.({ ...ruleset, items: newItems });
        ruleDialogOpen = false;
        editingRule = null;
    }

    function handleCloneRuleSet(e) {
        const original = e.detail;
        const clone = deepCloneWithNewIds(original);
        // The ruleset dialog is owned by the child RuleEditor for that ruleset,
        // so we bubble the clone up to the parent to insert as a sibling.
        oncloneSelf?.(clone);
        ruleSetDialogOpen = false;
        editingRuleSet = null;
    }

    function handleCloneChildRuleSet(itemId, cloned) {
        const idx = currentItems.findIndex((item) => item.id === itemId);
        const newItems = idx >= 0
            ? [...currentItems.slice(0, idx + 1), cloned, ...currentItems.slice(idx + 1)]
            : [...currentItems, cloned];
        onchange?.({ ...ruleset, items: newItems });
    }

    function handleSaveRuleSet(e) {
        const saved = e.detail;
        if (addingRuleSet) {
            onchange?.({ ...ruleset, items: [...currentItems, saved] });
        } else {
            onchange?.({
                ...ruleset,
                name: saved.name,
                match_any: saved.match_any,
            });
        }
        ruleSetDialogOpen = false;
        editingRuleSet = null;
        addingRuleSet = false;
    }

    function handleDeleteRuleSet() {
        if (isRoot) {
            onresetToDefaults?.();
        } else {
            ondeleteSelf?.();
        }
        ruleSetDialogOpen = false;
        editingRuleSet = null;
    }
</script>

{#snippet editorContent()}
    <div
        class="rule-editor"
        class:is-disabled={!ruleset.enabled && !isRoot && !ancestorDisabled}
    >
        <!-- Ruleset header -->
        <div class="ruleset-header" class:is-root={isRoot}>
            {#if !isRoot}
                <label
                    class="enable-toggle"
                    title={ruleset.enabled
                        ? "Disable rule set"
                        : "Enable rule set"}
                >
                    <input
                        type="checkbox"
                        checked={ruleset.enabled}
                        onchange={() =>
                            onchange?.({
                                ...ruleset,
                                enabled: !ruleset.enabled,
                            })}
                    />
                </label>
            {/if}
            <span class="ruleset-label">
                <span class="ruleset-name">{autoRuleSetName(ruleset)}</span>
                <span class="match-badge"
                    >{ruleset.match_any ? "Match Any" : "Match All"}</span
                >
            </span>
            <button
                class="edit-btn"
                onclick={() => openEditRuleSet(ruleset)}
                aria-label="Edit rule set"
            >
                <Pencil size="14" />
            </button>
        </div>

        <div class="items-list">
            {#each currentItems as item, i (item.id)}
                {@const isContainer = isRuleSet(item)}
                <SortableItem
                    id={item.id}
                    index={i}
                    type={isContainer ? "ruleset" : "rule"}
                    accept={["rule", "ruleset"]}
                    group={rulesetId}
                    data={{ group: rulesetId }}
                    {isOverlay}
                    collisionPriority={isContainer
                        ? CollisionPriority.Low
                        : undefined}
                >
                    {#snippet children()}
                        {#if isContainer}
                            <RuleEditor
                                ruleset={item}
                                isRoot={false}
                                inheritedItemsMap={effectiveItemsMap}
                                ancestorDisabled={!ruleset.enabled ||
                                    ancestorDisabled}
                                {isOverlay}
                                onchange={(updated) =>
                                    handleChildChange(i, updated)}
                                ondeleteSelf={() =>
                                    handleDeleteChildRuleSet(item.id)}
                                oncloneSelf={(cloned) =>
                                    handleCloneChildRuleSet(item.id, cloned)}
                                {onresetToDefaults}
                            />
                        {:else}
                            <div
                                class="rule-row"
                                class:disabled={!item.enabled &&
                                    !ancestorDisabled}
                            >
                                <label
                                    class="enable-toggle"
                                    title={item.enabled ? "Disable" : "Enable"}
                                >
                                    <input
                                        type="checkbox"
                                        checked={item.enabled}
                                        onchange={() => handleToggle(item)}
                                    />
                                </label>
                                <span
                                    class="rule-name"
                                    title={autoRuleName(item)}
                                    >{autoRuleName(item)}</span
                                >
                                <button
                                    class="edit-btn"
                                    onclick={() => openEditRule(item)}
                                    aria-label="Edit rule"
                                >
                                    <Pencil size="14" />
                                </button>
                            </div>
                        {/if}
                    {/snippet}
                </SortableItem>
            {/each}
        </div>

        <!-- Add buttons -->
        <div class="add-buttons">
            <button class="add-btn" onclick={addRule} type="button">
                <Plus size="13" /> Add Rule
            </button>
            <button class="add-btn" onclick={addRuleSet} type="button">
                <FolderPlus size="13" /> Add Rule Set
            </button>
        </div>
    </div>
{/snippet}

<!-- Only the root RuleEditor renders the DragDropProvider to permit dragging across all subgroups -->
{#if isRoot}
    <DragDropProvider onDragOver={handleDragOver} onDragEnd={handleDragEnd}>
        {@render editorContent()}

        <DragOverlay>
            {#snippet children(source)}
                {@const draggingItem = findItemInMap(source.id)}
                {#if draggingItem}
                    <div class="overlay-container">
                        {#if isRuleSet(draggingItem)}
                            <div class="rule-editor overlay-ruleset">
                                <div class="ruleset-header is-root">
                                    <span class="ruleset-label">
                                        <span class="ruleset-name"
                                            >{autoRuleSetName(
                                                draggingItem,
                                            )}</span
                                        >
                                        <span class="match-badge"
                                            >{draggingItem.match_any
                                                ? "Match Any"
                                                : "Match All"}</span
                                        >
                                    </span>
                                </div>
                            </div>
                        {:else}
                            <div class="rule-row overlay-rule">
                                <span class="rule-name"
                                    >{autoRuleName(draggingItem)}</span
                                >
                            </div>
                        {/if}
                    </div>
                {/if}
            {/snippet}
        </DragOverlay>
    </DragDropProvider>
{:else}
    {@render editorContent()}
{/if}

<!-- Dialogs -->
{#if editingRule}
    <RuleEditDialog
        bind:open={ruleDialogOpen}
        rule={editingRule}
        on:save={handleSaveRule}
        on:delete={handleDeleteRule}
        on:clone={handleCloneRule}
        on:close={() => {
            ruleDialogOpen = false;
            editingRule = null;
            addingRule = false;
        }}
    />
{/if}

{#if editingRuleSet}
    <RuleSetEditDialog
        bind:open={ruleSetDialogOpen}
        ruleset={editingRuleSet}
        isRoot={isRoot && !addingRuleSet}
        on:save={handleSaveRuleSet}
        on:delete={handleDeleteRuleSet}
        on:clone={handleCloneRuleSet}
        on:close={() => {
            ruleSetDialogOpen = false;
            editingRuleSet = null;
            addingRuleSet = false;
        }}
    />
{/if}

<style>
    .rule-editor {
        display: flex;
        flex-direction: column;
        gap: 0;
        border: 1px solid var(--border-color);
        border-radius: 8px;
        overflow: visible;
        background: var(--bg-secondary);
    }

    .rule-editor.is-disabled {
        opacity: 0.45;
    }

    .ruleset-header {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.625rem 0.75rem;
        border-bottom: 1px solid var(--border-color);
        background: var(--bg-tertiary);
        border-radius: 8px 8px 0 0;
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

    .ruleset-label {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        flex: 1;
        min-width: 0;
    }

    .ruleset-name {
        font-size: 0.875rem;
        font-weight: 600;
        color: var(--text-primary);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .match-badge {
        font-size: 0.75rem;
        color: var(--text-secondary);
        background: var(--bg-primary);
        border: 1px solid var(--border-color);
        border-radius: 4px;
        padding: 0.1rem 0.4rem;
        flex-shrink: 0;
    }

    .edit-btn {
        background: none;
        border: none;
        cursor: pointer;
        color: var(--text-secondary);
        padding: 0.25rem;
        display: flex;
        align-items: center;
        border-radius: 4px;
        flex-shrink: 0;
    }
    .edit-btn:hover {
        color: var(--text-primary);
        background: var(--bg-primary);
    }

    .items-list {
        display: flex;
        flex-direction: column;
        gap: 0.375rem;
        padding: 0.5rem;
        min-height: 2rem;
    }

    .rule-row {
        flex: 1;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.5rem 0.75rem;
        background: var(--bg-primary);
        border: 1px solid var(--border-color);
        border-radius: 6px;
        min-width: 0;
    }

    .rule-row.disabled {
        opacity: 0.45;
    }

    .rule-name {
        flex: 1;
        font-size: 0.875rem;
        color: var(--text-primary);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .add-buttons {
        display: flex;
        gap: 0.5rem;
        padding: 0.5rem;
        border-top: 1px solid var(--border-color);
    }

    .add-btn {
        display: flex;
        align-items: center;
        gap: 0.375rem;
        padding: 0.375rem 0.75rem;
        background: none;
        border: 1px dashed var(--border-color);
        border-radius: 6px;
        color: var(--text-secondary);
        font-size: 0.8125rem;
        cursor: pointer;
        transition:
            color 0.15s,
            border-color 0.15s;
    }
    .add-btn:hover {
        color: var(--text-primary);
        border-color: var(--text-secondary);
    }

    /* Overlay specific styles */
    .overlay-container {
        pointer-events: none;
        box-shadow: 0 8px 16px rgba(0, 0, 0, 0.15);
        border-radius: 6px;
    }
    .overlay-ruleset {
        border-radius: 8px;
        background: var(--bg-secondary);
    }
    .overlay-rule {
        background: var(--bg-primary);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    }
</style>
