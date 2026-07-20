import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { ComponentProps } from 'svelte';
import ActionBar from './ActionBar.svelte';

type Props = ComponentProps<typeof ActionBar>;

function makeProps(overrides: Partial<Props> = {}): Props {
  return {
    selectionStats: { total: 3, selected: 2, unselected: 1 },
    canUndo: true,
    canRedo: false,
    hasChapters: true,
    hasChapterRefs: false,
    hasTranscriptions: true,
    transcribing: false,
    aiLoading: false,
    editorSettings: {
      tab_navigation: false,
      hide_transcriptions: false,
      show_formatted_time: true,
      show_fractional_seconds: true,
    },
    dock: 'bottom',
    expanded: true,
    canDock: true,
    onDockChange: vi.fn(),
    onToggleExpanded: vi.fn(),
    onUndo: vi.fn(),
    onRedo: vi.fn(),
    onCleanUp: vi.fn(),
    onReview: vi.fn(),
    onEditTitles: vi.fn(),
    onShiftTitles: vi.fn(),
    onApplyTitles: vi.fn(),
    onShiftTimestamps: vi.fn(),
    onQuickTidy: vi.fn(),
    onQuickTidySettings: vi.fn(),
    onTranscribe: vi.fn(),
    onDelete: vi.fn(),
    onSettingsChange: vi.fn(),
    ...overrides,
  };
}

function renderBar(overrides: Partial<Props> = {}) {
  const props = makeProps(overrides);
  const utils = render(ActionBar, { props });
  return { props, user: userEvent.setup(), ...utils };
}

function expectBefore(first: HTMLElement, second: HTMLElement) {
  expect(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
}

describe('bottom dock', () => {
  it('renders the bar controls and dock buttons', async () => {
    const { props, user } = renderBar();

    expect(screen.getByText('2 of 3 selected')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Undo' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Redo' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Additional tools and settings' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Clean Up Selected' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Review Selected' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Dock to left side' }));
    expect(props.onDockChange).toHaveBeenCalledWith('left');

    await user.click(screen.getByRole('button', { name: 'Dock to right side' }));
    expect(props.onDockChange).toHaveBeenCalledWith('right');
  });

  it('hides the dock buttons when docking is unavailable', () => {
    renderBar({ canDock: false });
    expect(screen.queryByRole('button', { name: 'Dock to left side' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Dock to right side' })).not.toBeInTheDocument();
  });

  it('has no collapse toggle or dock-to-bottom button', () => {
    renderBar();
    expect(screen.queryByRole('button', { name: 'Collapse' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Dock to bottom' })).not.toBeInTheDocument();
  });

  it('fires menu callbacks and closes the menu for quick actions', async () => {
    const { props, user } = renderBar();

    await user.click(screen.getByRole('button', { name: 'Additional tools and settings' }));
    await user.click(screen.getByRole('button', { name: 'Edit Titles' }));
    expect(props.onEditTitles).toHaveBeenCalledOnce();
    expect(screen.getByRole('heading', { name: 'Tools' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Quick Tidy' }));
    expect(props.onQuickTidy).toHaveBeenCalledOnce();
    expect(screen.queryByRole('heading', { name: 'Tools' })).not.toBeInTheDocument();
  });
});

describe('side dock (expanded)', () => {
  it('shows all sections inline in Tools, Actions, Settings order with the bar items below', () => {
    renderBar({ dock: 'left' });

    expect(screen.queryByRole('button', { name: 'Additional tools and settings' })).not.toBeInTheDocument();

    const tools = screen.getByRole('heading', { name: 'Tools' });
    const actions = screen.getByRole('heading', { name: 'Actions' });
    const settings = screen.getByRole('heading', { name: 'Settings' });
    expectBefore(tools, actions);
    expectBefore(actions, settings);
    expectBefore(settings, screen.getByText('2 of 3 selected'));
    expectBefore(screen.getByText('2 of 3 selected'), screen.getByRole('button', { name: 'Undo' }));
    expectBefore(
      screen.getByRole('button', { name: 'Undo' }),
      screen.getByRole('button', { name: 'Clean Up Selected' }),
    );
    expectBefore(
      screen.getByRole('button', { name: 'Clean Up Selected' }),
      screen.getByRole('button', { name: 'Review Selected' }),
    );
  });

  it('offers the other two dock positions below the bar', async () => {
    const { props, user } = renderBar({ dock: 'left' });

    await user.click(screen.getByRole('button', { name: 'Dock to bottom' }));
    expect(props.onDockChange).toHaveBeenCalledWith('bottom');

    await user.click(screen.getByRole('button', { name: 'Dock to right side' }));
    expect(props.onDockChange).toHaveBeenCalledWith('right');
  });

  it('mirrors the side-switch button when docked right', () => {
    renderBar({ dock: 'right' });
    expect(screen.getByRole('button', { name: 'Dock to left side' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Dock to right side' })).not.toBeInTheDocument();
  });

  it('toggles expansion from the collapse button', async () => {
    const { props, user } = renderBar({ dock: 'left' });
    const toggle = screen.getByRole('button', { name: 'Collapse' });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');

    await user.click(toggle);
    expect(props.onToggleExpanded).toHaveBeenCalledOnce();
  });

  it('propagates settings changes', async () => {
    const { props, user } = renderBar({ dock: 'left' });
    await user.click(screen.getByLabelText(/Tab to Next/));
    expect(props.onSettingsChange).toHaveBeenCalledWith({ tab_navigation: true });
  });

  it('hides the sections when there are no chapters', () => {
    renderBar({ dock: 'left', hasChapters: false });
    expect(screen.queryByRole('heading', { name: 'Tools' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Undo' })).toBeInTheDocument();
  });
});

describe('side dock (collapsed)', () => {
  function renderCollapsed(overrides: Partial<Props> = {}) {
    return renderBar({ dock: 'left', expanded: false, ...overrides });
  }

  it('renders icon-only buttons without text or section headers', () => {
    const { container } = renderCollapsed();

    expect(screen.queryByRole('heading', { name: 'Tools' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Actions' })).not.toBeInTheDocument();
    expect(container.querySelectorAll('.dock-section-divider').length).toBeGreaterThanOrEqual(2);

    for (const name of [
      'Edit Titles',
      'Shift Titles',
      'Shift Timestamps',
      'Quick Tidy',
      'Transcribe',
      'Delete Selected',
    ]) {
      const button = screen.getByRole('button', { name });
      expect(button.textContent!.trim()).toBe('');
    }
  });

  it('hides the editor settings and the Quick Tidy gear', () => {
    renderCollapsed();
    expect(screen.queryByRole('heading', { name: 'Settings' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Tab to Next/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Configure Quick Tidy' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Quick Tidy' })).toBeInTheDocument();
  });

  it('shortens the selection badge', () => {
    renderCollapsed();
    expect(screen.getByText('2/3')).toBeInTheDocument();
    expect(screen.queryByText('2 of 3 selected')).not.toBeInTheDocument();
  });

  it('labels the toggle as Expand', () => {
    const toggle = renderCollapsed() && screen.getByRole('button', { name: 'Expand' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });

  it('still fires the action callbacks', async () => {
    const { props, user } = renderCollapsed();
    await user.click(screen.getByRole('button', { name: 'Delete Unselected' }));
    expect(props.onDelete).toHaveBeenCalledWith('unselected');

    await user.click(screen.getByRole('button', { name: 'Review Selected' }));
    expect(props.onReview).toHaveBeenCalledOnce();
  });

  it('propagates disabled states', () => {
    renderCollapsed({ selectionStats: { total: 3, selected: 0, unselected: 3 } });
    expect(screen.getByRole('button', { name: 'Quick Tidy' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Transcribe' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Delete Selected' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Clean Up Selected' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Review Selected' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Delete Unselected' })).toBeEnabled();
  });
});
