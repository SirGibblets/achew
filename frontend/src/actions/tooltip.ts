import { mount, unmount, type Snippet } from 'svelte';
import type { Action } from 'svelte/action';
import TooltipContent from './TooltipContent.svelte';

export interface TooltipOptions {
  /** The tooltip text. When empty/null, the tooltip is disabled. */
  text?: string | null;
  /** Preferred side. Flips automatically when there isn't room. Default 'top'. */
  placement?: 'top' | 'bottom';
  /** Delay in ms before showing on hover/focus. Default 800 (matches native `title`). */
  delay?: number;
  /** Max bubble width in px. Default 360. */
  maxWidth?: number;
  /** Whether to render the little arrow. Default true. */
  showArrow?: boolean;
  /** Hide the tooltip when its node is clicked. Default true). */
  dismissOnClick?: boolean;
  /** Rich content rendered into the bubble instead of `text`. */
  content?: Snippet;
}

export type TooltipParam = string | null | undefined | TooltipOptions;

const GAP = 8;
const MARGIN = 8;
const ARROW = 7;

function normalize(param: TooltipParam): Required<
  Pick<TooltipOptions, 'placement' | 'delay' | 'maxWidth' | 'showArrow' | 'dismissOnClick'>
> & {
  text: string;
  content: Snippet | null;
} {
  const opts: TooltipOptions = typeof param === 'string' || param == null ? { text: param } : param;
  return {
    text: (opts.text ?? '').trim(),
    content: opts.content ?? null,
    placement: opts.placement ?? 'top',
    delay: opts.delay ?? 800,
    maxWidth: opts.maxWidth ?? 360,
    showArrow: opts.showArrow ?? true,
    dismissOnClick: opts.dismissOnClick ?? true,
  };
}

/**
 * Tooltip rendered in a body-level fixed layer to avoid being clipped in
 * dialogs or overflow containers.
 *
 * Shows after an 800ms hover/keyboard-focus delay and hides on click.
 * Override per call site via the options object.
 *
 * Usage: `<button use:tooltip={'Help text'}>` or
 *        `<span use:tooltip={{ text, placement: 'bottom', delay: 0 }}>`
 */
export const tooltip: Action<HTMLElement, TooltipParam> = (node, param) => {
  let opts = normalize(param);
  let bubble: HTMLDivElement | null = null;
  let arrow: HTMLDivElement | null = null;
  let instance: ReturnType<typeof mount> | null = null;
  let showTimer: ReturnType<typeof setTimeout> | null = null;

  function position() {
    if (!bubble) return;
    const nodeRect = node.getBoundingClientRect();
    const bubbleRect = bubble.getBoundingClientRect();
    const vw = document.documentElement.clientWidth;
    const vh = document.documentElement.clientHeight;

    let placement = opts.placement;
    let top: number;
    if (placement === 'top') {
      top = nodeRect.top - bubbleRect.height - GAP;
      if (top < MARGIN) {
        placement = 'bottom';
        top = nodeRect.bottom + GAP;
      }
    } else {
      top = nodeRect.bottom + GAP;
      if (top + bubbleRect.height > vh - MARGIN) {
        placement = 'top';
        top = nodeRect.top - bubbleRect.height - GAP;
      }
    }

    const centerX = nodeRect.left + nodeRect.width / 2;
    const left = Math.max(MARGIN, Math.min(centerX - bubbleRect.width / 2, vw - bubbleRect.width - MARGIN));

    bubble.style.top = `${Math.round(top)}px`;
    bubble.style.left = `${Math.round(left)}px`;

    if (arrow) {
      arrow.dataset.placement = placement;
      const arrowCenter = Math.max(ARROW * 2, Math.min(centerX - left, bubbleRect.width - ARROW * 2));
      arrow.style.left = `${Math.round(arrowCenter - ARROW)}px`;
    }
  }

  function show() {
    if (bubble || (!opts.text && !opts.content)) return;

    bubble = document.createElement('div');
    bubble.className = 'app-tooltip';
    bubble.style.maxWidth = `${opts.maxWidth}px`;

    if (opts.content) {
      instance = mount(TooltipContent, { target: bubble, props: { content: opts.content } });
    } else {
      bubble.textContent = opts.text;
    }

    if (opts.showArrow) {
      arrow = document.createElement('div');
      arrow.className = 'app-tooltip__arrow';
      bubble.appendChild(arrow);
    }

    document.body.appendChild(bubble);
    position();
    requestAnimationFrame(() => bubble?.classList.add('app-tooltip--visible'));

    window.addEventListener('scroll', hide, true);
    window.addEventListener('resize', hide);
  }

  function hide() {
    if (showTimer) {
      clearTimeout(showTimer);
      showTimer = null;
    }
    window.removeEventListener('scroll', hide, true);
    window.removeEventListener('resize', hide);
    if (instance) {
      unmount(instance);
      instance = null;
    }
    bubble?.remove();
    bubble = null;
    arrow = null;
  }

  function onEnter() {
    if ((!opts.text && !opts.content) || bubble) return;
    if (opts.delay > 0) {
      showTimer = setTimeout(show, opts.delay);
    } else {
      show();
    }
  }

  function onFocusIn() {
    if (node.matches(':focus-visible')) onEnter();
  }

  function onClick() {
    if (opts.dismissOnClick) hide();
  }

  node.addEventListener('mouseenter', onEnter);
  node.addEventListener('mouseleave', hide);
  node.addEventListener('focusin', onFocusIn);
  node.addEventListener('focusout', hide);
  node.addEventListener('click', onClick);

  return {
    update(next: TooltipParam) {
      opts = normalize(next);
      if (!bubble) return;
      if (!opts.text && !opts.content) {
        hide();
        return;
      }
      bubble.style.maxWidth = `${opts.maxWidth}px`;
      if (!opts.content) {
        bubble.firstChild!.textContent = opts.text;
      }
      position();
    },
    destroy() {
      hide();
      node.removeEventListener('mouseenter', onEnter);
      node.removeEventListener('mouseleave', hide);
      node.removeEventListener('focusin', onFocusIn);
      node.removeEventListener('focusout', hide);
      node.removeEventListener('click', onClick);
    },
  };
};
