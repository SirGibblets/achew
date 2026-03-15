<script>
    import { useDroppable } from "@dnd-kit-svelte/svelte";

    let { rulesetId, isOverlay = false } = $props();

    const { ref, isDropTarget } = useDroppable({
        id: () => rulesetId + "_empty",
        data: () => ({ isEmptyDropZone: true, rulesetId }),
        disabled: () => isOverlay,
    });
</script>

<div
    class="empty-drop-zone"
    class:is-active={isDropTarget.current}
    {@attach ref}
>
    <div class="empty-drop-zone-content">No rules added</div>
</div>

<style>
    .empty-drop-zone {
        padding: 0.5rem 0.75rem;
        border: 2px dashed var(--border-color);
        border-radius: 6px;
        text-align: center;
        color: var(--text-muted, var(--text-secondary));
        transition: all 0.2s ease;
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 2.25rem; 
    }
    .empty-drop-zone-content {
        font-size: 0.8125rem;
        opacity: 0.7;
    }
    .empty-drop-zone.is-active {
        border-color: var(--primary);
        background: var(--bg-primary-hover, rgba(0, 0, 0, 0.05));
        color: var(--primary);
    }
    .empty-drop-zone.is-active .empty-drop-zone-content {
        opacity: 1;
    }
</style>
