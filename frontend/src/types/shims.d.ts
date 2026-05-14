declare namespace svelteHTML {
  /* eslint-disable @typescript-eslint/no-unused-vars, @typescript-eslint/no-explicit-any */
  interface HTMLAttributes<T> {
    onconsider?: (event: CustomEvent<any>) => unknown;
    onfinalize?: (event: CustomEvent<any>) => unknown;
  }
  /* eslint-enable @typescript-eslint/no-unused-vars, @typescript-eslint/no-explicit-any */
}

declare module 'svelte-dnd-action' {
  import type { Action } from 'svelte/action';

  export interface DndzoneOptions<T = unknown> {
    items: T[];
    type?: string;
    flipDurationMs?: number;
    dragDisabled?: boolean;
    morphDisabled?: boolean;
    dropFromOthersDisabled?: boolean;
    zoneTabIndex?: number;
    dropTargetStyle?: Record<string, string>;
    dropTargetClasses?: string[];
    transformDraggedElement?: (el?: HTMLElement, items?: T[], index?: number) => void;
    autoAriaDisabled?: boolean;
    centreDraggedOnCursor?: boolean;
  }

  export interface DndEventInfo {
    trigger: string;
    id: string;
    source: string;
  }

  export interface DndEvent<T = unknown> {
    items: T[];
    info: DndEventInfo;
  }

  export const dndzone: Action<HTMLElement, DndzoneOptions>;

  export const TRIGGERS: {
    DRAG_STARTED: string;
    DRAGGED_ENTERED: string;
    DRAGGED_OVER_INDEX: string;
    DRAGGED_LEFT: string;
    DROPPED_INTO_ZONE: string;
    DROPPED_INTO_ANOTHER: string;
    DROPPED_OUTSIDE_OF_ANY: string;
    DRAG_STOPPED: string;
  };

  export const SOURCES: {
    POINTER: string;
    KEYBOARD: string;
  };

  export const SHADOW_PLACEHOLDER_ITEM_ID: string;
  export const SHADOW_ITEM_MARKER_PROPERTY_NAME: string;
  export const DRAGGED_ELEMENT_ID: string;
}
