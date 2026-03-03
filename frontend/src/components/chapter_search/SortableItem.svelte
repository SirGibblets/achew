<script>
    import { useSortable } from "@dnd-kit-svelte/svelte/sortable";
    import GripVertical from "@lucide/svelte/icons/grip-vertical";

    let {
        id,
        index,
        children,
        type = "item",
        accept = ["item"],
        group = undefined,
        data = undefined,
        collisionPriority = undefined,
        isOverlay = false,
    } = $props();

    const { ref, handleRef, isDragging, isDropTarget } = useSortable({
        id,
        index: () => index,
        type,
        accept,
        group,
        data,
        collisionPriority,
        disabled: isOverlay,
    });
</script>

<div
    class="sortable-item"
    class:is-dragging={isDragging.current && !isOverlay}
    class:is-drop-target={isDropTarget.current && !isDragging.current}
    {@attach ref}
>
    <span class="drag-handle" {@attach handleRef}>
        <GripVertical size="14" />
    </span>
    <div class="item-content">
        {@render children()}
    </div>
</div>

<style>
    .sortable-item {
        display: flex;
        align-items: flex-start;
        gap: 0.375rem;
        border-radius: 6px;
    }

    .sortable-item.is-dragging {
        opacity: 0.3;
        /* When dragging a container with children, we don't want it to collapse completely, but we might want it hidden.
           Let's just keep opacity 0.3 for now to see where it went, but maybe it vanishes because of `display: flex` disappearing? */
    }

    .sortable-item.is-drop-target {
        outline: 2px solid var(--primary);
        outline-offset: 1px;
    }

    .drag-handle {
        display: flex;
        align-items: center;
        padding-top: 0.5rem;
        color: var(--text-muted, var(--text-secondary));
        cursor: grab;
        flex-shrink: 0;
        touch-action: none; /* required for pointer sensor */
    }

    .drag-handle:active {
        cursor: grabbing;
    }

    .item-content {
        flex: 1;
        min-width: 0;
    }
</style>
