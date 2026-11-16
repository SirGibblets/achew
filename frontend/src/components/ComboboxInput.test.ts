import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import ComboboxInput from './ComboboxInput.svelte';

const models = ['Systran/faster-whisper-small.en', 'deepdml/faster-whisper-large-v3-turbo-ct2', 'parakeet-tdt-0.6b-v2'];

function setup(value = '') {
  const oninput = vi.fn();
  const onselect = vi.fn();
  render(ComboboxInput, { value, options: models, id: 'model', toggleLabel: 'Show models', oninput, onselect });
  return { user: userEvent.setup(), input: screen.getByRole('combobox') as HTMLInputElement, oninput, onselect };
}

const shownOptions = () => screen.queryAllByRole('option').map((o) => o.textContent?.trim());

describe('ComboboxInput', () => {
  it('shows every option on open even when a value is already set', async () => {
    // A native <datalist> would only offer options matching the current value
    const { user, input } = setup('parakeet-tdt-0.6b-v2');

    await user.click(input);
    expect(shownOptions()).toEqual(models);
    expect(screen.getByRole('option', { name: 'parakeet-tdt-0.6b-v2' }).getAttribute('aria-selected')).toBe('true');

    await user.keyboard('{Escape}');
    expect(shownOptions()).toEqual([]);
    await user.click(screen.getByRole('button', { name: 'Show models' }));
    expect(shownOptions()).toEqual(models);
  });

  it('filters while typing and keeps free text', async () => {
    const { user, input, oninput, onselect } = setup();

    await user.type(input, 'faster');
    expect(shownOptions()).toEqual(models.slice(0, 2));

    await user.type(input, '-medium');
    expect(shownOptions()).toEqual([]);
    expect(input.value).toBe('faster-medium');
    expect(oninput).toHaveBeenLastCalledWith('faster-medium');
    expect(onselect).not.toHaveBeenCalled();
  });

  it('picks an option by click or keyboard', async () => {
    const { user, input, onselect } = setup('Systran/faster-whisper-small.en');

    await user.click(input);
    await user.click(screen.getByRole('option', { name: 'parakeet-tdt-0.6b-v2' }));
    expect(input.value).toBe('parakeet-tdt-0.6b-v2');
    expect(onselect).toHaveBeenLastCalledWith('parakeet-tdt-0.6b-v2');
    expect(shownOptions()).toEqual([]);

    // Opening by keyboard starts on the current value; ArrowDown wraps to the first option
    await user.keyboard('{ArrowDown}{ArrowDown}{Enter}');
    expect(input.value).toBe('Systran/faster-whisper-small.en');
    expect(onselect).toHaveBeenLastCalledWith('Systran/faster-whisper-small.en');
  });

  it('is a plain text field without options', () => {
    render(ComboboxInput, { value: '', options: [], toggleLabel: 'Show models' });
    expect(screen.queryByRole('button', { name: 'Show models' })).toBeNull();
  });
});
