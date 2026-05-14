<script lang="ts">
  /**
   * RuleEditor — recursive rule/ruleset list with drag-and-drop.
   *
   * Svelte 5 runes component.
   * Accepts callbacks: onchange(ruleset), onresetToDefaults(), ondeleteSelf()
   */
  import { onMount } from 'svelte';
  import { DragDropProvider, DragOverlay } from '@dnd-kit-svelte/svelte';
  import { CollisionPriority } from '@dnd-kit/abstract';
  import { move } from '@dnd-kit/helpers';
  import Plus from '@lucide/svelte/icons/plus';
  import FolderPlus from '@lucide/svelte/icons/folder-plus';
  import Pencil from '@lucide/svelte/icons/pencil';

  import SortableItem from './SortableItem.svelte';
  import RuleEditor from './RuleEditor.svelte';
  import EmptyDropZone from './EmptyDropZone.svelte';
  import RuleEditDialog from './RuleEditDialog.svelte';
  import RuleSetEditDialog from './RuleSetEditDialog.svelte';
  import {
    autoRuleName,
    autoRuleSetName,
    createBlankRule,
    createBlankRuleSet,
    cloneItem,
    deepCloneWithNewIds,
  } from './ruleUtils';
  import type { Rule, RuleSet, RuleOrSet } from '../../types/rules';

  interface Props {
    ruleset: RuleSet;
    isRoot?: boolean;
    inheritedItemsMap?: Record<string, RuleOrSet[]> | null;
    ancestorDisabled?: boolean;
    isOverlay?: boolean;
    onchange?: (ruleset: RuleSet) => void;
    onresetToDefaults?: () => void;
    ondeleteSelf?: () => void;
    oncloneSelf?: (clone: RuleSet) => void;
  }

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
  }: Props = $props();

  let rulesetId = $derived(ruleset.id || 'root');

  // Suppress HierarchyRequestError from dnd-kit's internal DOM reorder
  // when dragging nested sortable containers (rulesets).
  onMount(() => {
    if (!isRoot) return;
    function suppress(e: PromiseRejectionEvent) {
      const reason = e.reason as { name?: string } | undefined;
      if (reason?.name === 'HierarchyRequestError') {
        e.preventDefault();
      }
    }
    window.addEventListener('unhandledrejection', suppress);
    return () => window.removeEventListener('unhandledrejection', suppress);
  });

  // --- Global Tree State for Drag & Drop ---
  // Instead of local items per level, the root manages the entire tree mapped by container ID.
  let rootItemsMap: Record<string, RuleOrSet[]> = $state({});

  $effect(() => {
    if (isRoot && !isOverlay) {
      rootItemsMap = flattenTree(ruleset);
    }
  });

  let effectiveItemsMap = $derived(isRoot ? rootItemsMap : inheritedItemsMap);
  let currentItems = $derived(effectiveItemsMap ? effectiveItemsMap[rulesetId] || [] : ruleset.items || []);

  // Helper functions to manage the tree as an items map for dnd-kit `move`
  function flattenTree(node: RuleSet, map: Record<string, RuleOrSet[]> = {}): Record<string, RuleOrSet[]> {
    const id = node.id || 'root';
    map[id] = [...(node.items || [])];
    for (const child of node.items || []) {
      if (isRuleSet(child)) {
        flattenTree(child, map);
      }
    }
    return map;
  }

  function rebuildTree(node: RuleOrSet, map: Record<string, RuleOrSet[]>): RuleOrSet {
    if (!isRuleSet(node)) return node;
    const id = node.id || 'root';
    const newItems = (map[id] || []).map((child) => rebuildTree(child, map));
    return { ...node, items: newItems };
  }

  function findItemInMap(id: string): RuleOrSet | null {
    for (const items of Object.values(rootItemsMap)) {
      const found = items.find((it) => it.id === id);
      if (found) return found;
    }
    return null;
  }

  // Dialog state
  let editingRule: Rule | null = $state(null);
  let editingRuleSet: RuleSet | null = $state(null);
  let ruleDialogOpen = $state(false);
  let ruleSetDialogOpen = $state(false);
  let addingRule = $state(false);
  let addingRuleSet = $state(false);

  function isRuleSet(item: RuleOrSet): item is RuleSet {
    return Array.isArray((item as RuleSet).items);
  }

  // --- DnD handlers (Root Only) ---

  function findContainerOf(itemId: string): string | null {
    for (const [containerId, children] of Object.entries(rootItemsMap)) {
      if (children.some((child) => child.id === itemId)) {
        return containerId;
      }
    }
    return null;
  }

  function isOrDescendantOf(containerId: string, ancestorId: string): boolean {
    if (containerId === ancestorId) return true;
    const children = rootItemsMap[ancestorId];
    if (!children) return false;
    for (const child of children) {
      if (child.id in rootItemsMap && isOrDescendantOf(containerId, child.id)) return true;
    }
    return false;
  }

  function handleDragOver(event: {
    operation?: { source?: { id: string }; target?: { id: string } };
    canceled?: boolean;
  }) {
    if (!isRoot || isOverlay) return;

    const sourceId = event.operation?.source?.id;
    const targetId = event.operation?.target?.id;

    // Custom handling for empty drop zone
    if (targetId && String(targetId).endsWith('_empty')) {
      const destContainerId = String(targetId).replace('_empty', '');

      // Prevent a ruleset from being moved into itself or its descendants
      if (sourceId && sourceId in rootItemsMap) {
        if (isOrDescendantOf(destContainerId, sourceId)) {
          return;
        }
      }

      if (!sourceId) return;
      const sourceContainerId = findContainerOf(sourceId);
      if (!sourceContainerId || sourceContainerId === destContainerId) return;

      // Move the item manually from source container to destination container
      const itemIndex = rootItemsMap[sourceContainerId].findIndex((item) => item.id === sourceId);
      if (itemIndex > -1) {
        const item = rootItemsMap[sourceContainerId][itemIndex];
        rootItemsMap = {
          ...rootItemsMap,
          [sourceContainerId]: rootItemsMap[sourceContainerId].filter((it) => it.id !== sourceId),
          [destContainerId]: [item], // It was empty, so now it only has this item
        };
      }
      return;
    }

    // Prevent a ruleset from being moved into itself or its descendants
    if (sourceId && sourceId in rootItemsMap) {
      if (targetId) {
        const targetContainer = findContainerOf(targetId);
        if (targetContainer && isOrDescendantOf(targetContainer, sourceId)) {
          return;
        }
      }
    }
    // The dnd-kit `move` helper moves an item between arrays in an object record.
    // Cast through the move signature: dnd-kit's full event type isn't re-exported,
    // and our `event` parameter is a hand-typed subset of what it really emits.
    rootItemsMap = move(rootItemsMap, event as Parameters<typeof move>[1]) as Record<string, RuleOrSet[]>;
  }

  function handleDragEnd(event: { canceled?: boolean }) {
    if (!isRoot || isOverlay) return;
    if (!event.canceled) {
      onchange?.(rebuildTree(ruleset, rootItemsMap) as RuleSet);
    }
  }

  // --- Propagate changes ---

  function handleChildChange(index: number, updatedChild: RuleOrSet) {
    const newItems = currentItems.map((item, i) => (i === index ? updatedChild : item));
    onchange?.({ ...ruleset, items: newItems });
  }

  function handleToggle(item: Rule) {
    const newItems = currentItems.map((it) => (it.id === item.id ? { ...item, enabled: !item.enabled } : it));
    onchange?.({ ...ruleset, items: newItems });
  }

  function handleDeleteChildRuleSet(id: string) {
    const newItems = currentItems.filter((item) => item.id !== id);
    onchange?.({ ...ruleset, items: newItems });
  }

  // --- Dialog openers ---

  function openEditRule(rule: Rule) {
    editingRule = cloneItem(rule);
    addingRule = false;
    ruleDialogOpen = true;
  }

  function openEditRuleSet(rs: RuleSet) {
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

  function handleSaveRule(saved: Rule) {
    const newItems = addingRule
      ? [...currentItems, saved]
      : currentItems.map((item) => (item.id === saved.id ? saved : item));
    onchange?.({ ...ruleset, items: newItems });
    ruleDialogOpen = false;
    editingRule = null;
    addingRule = false;
  }

  function handleDeleteRule(deleted: Rule | null) {
    if (!deleted) return;
    const newItems = currentItems.filter((item) => item.id !== deleted.id);
    onchange?.({ ...ruleset, items: newItems });
    ruleDialogOpen = false;
    editingRule = null;
  }

  function handleCloneRule(original: Rule) {
    const clone = deepCloneWithNewIds(original);
    const idx = currentItems.findIndex((item) => item.id === original.id);
    const newItems =
      idx >= 0 ? [...currentItems.slice(0, idx + 1), clone, ...currentItems.slice(idx + 1)] : [...currentItems, clone];
    onchange?.({ ...ruleset, items: newItems });
    ruleDialogOpen = false;
    editingRule = null;
  }

  function handleCloneRuleSet(original: Partial<RuleSet>) {
    const clone = deepCloneWithNewIds(original as RuleSet);
    // The ruleset dialog is owned by the child RuleEditor for that ruleset,
    // so we bubble the clone up to the parent to insert as a sibling.
    oncloneSelf?.(clone);
    ruleSetDialogOpen = false;
    editingRuleSet = null;
  }

  function handleCloneChildRuleSet(itemId: string, cloned: RuleSet) {
    const idx = currentItems.findIndex((item) => item.id === itemId);
    const newItems =
      idx >= 0
        ? [...currentItems.slice(0, idx + 1), cloned, ...currentItems.slice(idx + 1)]
        : [...currentItems, cloned];
    onchange?.({ ...ruleset, items: newItems });
  }

  function handleSaveRuleSet(saved: RuleSet) {
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
  <div class="rule-editor" class:is-disabled={!ruleset.enabled && !isRoot && !ancestorDisabled}>
    <!-- Ruleset header -->
    <div class="ruleset-header" class:is-root={isRoot}>
      {#if !isRoot}
        <label class="enable-toggle" title={ruleset.enabled ? 'Disable ruleset' : 'Enable ruleset'}>
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
        <span class="match-badge">{ruleset.match_any ? 'Match Any' : 'Match All'}</span>
      </span>
      <button class="edit-btn" onclick={() => openEditRuleSet(ruleset)} aria-label="Edit ruleset">
        <Pencil size="14" />
      </button>
    </div>

    <div class="items-list">
      {#if currentItems.length === 0}
        <EmptyDropZone {rulesetId} {isOverlay} />
      {:else}
        {#each currentItems as item, i (item.id)}
          {@const isContainer = isRuleSet(item)}
          <SortableItem
            id={item.id}
            index={i}
            type={isContainer ? 'ruleset' : 'rule'}
            accept={['rule', 'ruleset']}
            group={rulesetId}
            data={{ group: rulesetId }}
            {isOverlay}
            collisionPriority={isContainer ? CollisionPriority.Low : undefined}
          >
            {#if isContainer}
              <RuleEditor
                ruleset={item as RuleSet}
                isRoot={false}
                inheritedItemsMap={effectiveItemsMap}
                ancestorDisabled={!ruleset.enabled || ancestorDisabled}
                {isOverlay}
                onchange={(updated) => handleChildChange(i, updated)}
                ondeleteSelf={() => handleDeleteChildRuleSet(item.id)}
                oncloneSelf={(cloned) => handleCloneChildRuleSet(item.id, cloned)}
                {onresetToDefaults}
              />
            {:else}
              <div class="rule-row" class:disabled={!item.enabled && !ancestorDisabled}>
                <label class="enable-toggle" title={item.enabled ? 'Disable' : 'Enable'}>
                  <input type="checkbox" checked={item.enabled} onchange={() => handleToggle(item as Rule)} />
                </label>
                <span class="rule-name" title={autoRuleName(item as Rule)}>{autoRuleName(item as Rule)}</span>
                <button class="edit-btn" onclick={() => openEditRule(item as Rule)} aria-label="Edit rule">
                  <Pencil size="14" />
                </button>
              </div>
            {/if}
          </SortableItem>
        {/each}
      {/if}
    </div>

    <!-- Add buttons -->
    <div class="add-buttons">
      <button class="add-btn" onclick={addRule} type="button">
        <Plus size="13" /> Add Rule
      </button>
      <button class="add-btn" onclick={addRuleSet} type="button">
        <FolderPlus size="13" /> Add Ruleset
      </button>
    </div>
  </div>
{/snippet}

<!-- Only the root RuleEditor renders the DragDropProvider to permit dragging across all subgroups -->
{#if isRoot}
  <DragDropProvider
    onDragOver={handleDragOver as unknown as (event: never, manager: never) => void}
    onDragEnd={handleDragEnd as unknown as (event: never, manager: never) => void}
  >
    {@render editorContent()}

    <DragOverlay>
      {#snippet children(source)}
        {@const draggingItem = findItemInMap(String(source.id))}
        {#if draggingItem}
          <div class="overlay-container">
            {#if isRuleSet(draggingItem)}
              <div class="rule-editor overlay-ruleset">
                <div class="ruleset-header is-root">
                  <span class="ruleset-label">
                    <span class="ruleset-name">{autoRuleSetName(draggingItem)}</span>
                    <span class="match-badge">{draggingItem.match_any ? 'Match Any' : 'Match All'}</span>
                  </span>
                </div>
              </div>
            {:else}
              <div class="rule-row overlay-rule">
                <span class="rule-name">{autoRuleName(draggingItem as Rule)}</span>
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
    onsave={handleSaveRule}
    ondelete={handleDeleteRule}
    onclone={handleCloneRule}
    onclose={() => {
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
    onsave={handleSaveRuleSet}
    ondelete={handleDeleteRuleSet}
    onclone={handleCloneRuleSet}
    onclose={() => {
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

  .enable-toggle input[type='checkbox'] {
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
