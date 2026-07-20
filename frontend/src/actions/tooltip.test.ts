import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { tooltip, type TooltipParam } from './tooltip';

function stubRect(node: HTMLElement, rect: Partial<DOMRect>) {
  node.getBoundingClientRect = () =>
    ({
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      width: 0,
      height: 0,
      toJSON: () => ({}),
      ...rect,
    }) as DOMRect;
}

function mount(param: TooltipParam, rect: Partial<DOMRect>) {
  const node = document.createElement('button');
  document.body.appendChild(node);
  stubRect(node, rect);
  const action = tooltip(node, param);
  return { node, action };
}

function hover(node: HTMLElement) {
  node.dispatchEvent(new MouseEvent('mouseenter'));
}

function bubble(): HTMLElement | null {
  return document.querySelector('.app-tooltip');
}

function arrow(): HTMLElement | null {
  return document.querySelector('.app-tooltip__arrow');
}

beforeEach(() => {
  Object.defineProperty(document.documentElement, 'clientWidth', { value: 1024, configurable: true });
  Object.defineProperty(document.documentElement, 'clientHeight', { value: 768, configurable: true });
});

afterEach(() => {
  document.body.innerHTML = '';
});

describe('tooltip horizontal placement', () => {
  it('shows to the right of the node with placement "right"', () => {
    const { node } = mount(
      { text: 'Help', placement: 'right', delay: 0 },
      { top: 100, bottom: 130, left: 10, right: 40, width: 30, height: 30 },
    );
    hover(node);

    expect(bubble()).not.toBeNull();
    expect(arrow()?.dataset.placement).toBe('right');
    // node.right (40) + 8px gap
    expect(bubble()!.style.left).toBe('48px');
  });

  it('flips to the left when there is no room on the right', () => {
    const { node } = mount(
      { text: 'Help', placement: 'right', delay: 0 },
      { top: 100, bottom: 130, left: 990, right: 1020, width: 30, height: 30 },
    );
    hover(node);

    expect(arrow()?.dataset.placement).toBe('left');
  });

  it('flips to the right when there is no room on the left', () => {
    const { node } = mount(
      { text: 'Help', placement: 'left', delay: 0 },
      { top: 100, bottom: 130, left: 4, right: 34, width: 30, height: 30 },
    );
    hover(node);

    expect(arrow()?.dataset.placement).toBe('right');
    expect(bubble()!.style.left).toBe('42px');
  });

  it('hides on mouseleave', () => {
    const { node } = mount(
      { text: 'Help', placement: 'right', delay: 0 },
      { top: 100, bottom: 130, left: 10, right: 40, width: 30, height: 30 },
    );
    hover(node);
    expect(bubble()).not.toBeNull();

    node.dispatchEvent(new MouseEvent('mouseleave'));
    expect(bubble()).toBeNull();
  });

  it('keeps vertical placement working with an arrow offset', () => {
    const { node } = mount('Help', { top: 500, bottom: 530, left: 100, right: 130, width: 30, height: 30 });
    node.dispatchEvent(new MouseEvent('mouseenter'));
    expect(bubble()).toBeNull();

    const { node: instant } = mount(
      { text: 'Help', delay: 0 },
      { top: 500, bottom: 530, left: 100, right: 130, width: 30, height: 30 },
    );
    hover(instant);
    expect(arrow()?.dataset.placement).toBe('top');
  });
});
