import type { Action } from 'svelte/action';

export interface TooltipOptions {
  /** The tooltip text. When empty/null, the tooltip is disabled. */
  text?: string | null;
  /** Preferred side. Flips automatically when there isn't room. Default 'top'. */
  placement?: 'top' | 'bottom';
  /** Delay in ms before showing on hover/focus. Default 0 (instant). */
  delay?: number;
  /** Max bubble width in px. Default 360. */
  maxWidth?: number;
  /** Whether to render the little arrow. Default true. */
  showArrow?: boolean;
}

export type TooltipParam = string | null | undefined | TooltipOptions;

const GAP = 8;
const MARGIN = 8;
const ARROW = 7;

function normalize(param: TooltipParam): Required<
  Pick<TooltipOptions, 'placement' | 'delay' | 'maxWidth' | 'showArrow'>
> & {
  text: string;
} {
  const opts = typeof param === 'string' || param == null ? { text: param } : param;
  return {
    text: (opts.text ?? '').trim(),
    placement: opts.placement ?? 'top',
    delay: opts.delay ?? 0,
    maxWidth: opts.maxWidth ?? 360,
    showArrow: opts.showArrow ?? true,
  };
}

/**
 * Tooltip rendered in a body-level fixed layer to avoid being clipped in
 * dialogs or overflow containers.
 *
 * Usage: `<button use:tooltip={'Help text'}>` or
 *        `<span use:tooltip={{ text, placement: 'bottom', delay: 300 }}>`
 */
export const tooltip: Action<HTMLElement, TooltipParam> = (node, param) => {
  let opts = normalize(param);
  let bubble: HTMLDivElement | null = null;
  let arrow: HTMLDivElement | null = null;
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
    if (bubble || !opts.text) return;

    bubble = document.createElement('div');
    bubble.className = 'app-tooltip';
    bubble.textContent = opts.text;
    bubble.style.maxWidth = `${opts.maxWidth}px`;

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
    bubble?.remove();
    bubble = null;
    arrow = null;
  }

  function onEnter() {
    if (!opts.text || bubble) return;
    if (opts.delay > 0) {
      showTimer = setTimeout(show, opts.delay);
    } else {
      show();
    }
  }

  node.addEventListener('mouseenter', onEnter);
  node.addEventListener('mouseleave', hide);
  node.addEventListener('focusin', onEnter);
  node.addEventListener('focusout', hide);

  return {
    update(next: TooltipParam) {
      opts = normalize(next);
      if (bubble) {
        if (!opts.text) {
          hide();
        } else {
          bubble.firstChild!.textContent = opts.text;
          bubble.style.maxWidth = `${opts.maxWidth}px`;
          position();
        }
      }
    },
    destroy() {
      hide();
      node.removeEventListener('mouseenter', onEnter);
      node.removeEventListener('mouseleave', hide);
      node.removeEventListener('focusin', onEnter);
      node.removeEventListener('focusout', hide);
    },
  };
};
