import { render, screen, waitFor } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import HostedASRSettings from './HostedASRSettings.svelte';

vi.mock('../utils/api', () => ({
  api: {
    config: {
      getHostedASR: vi.fn(),
      updateHostedASR: vi.fn(),
      getHostedASRModels: vi.fn(),
      testHostedASR: vi.fn(),
    },
  },
  handleApiError: (err: unknown) => (err instanceof Error ? err.message : String(err)),
}));

import { api } from '../utils/api';

const saved = {
  base_url: 'http://gpu-box:8000/v1',
  api_key: '***',
  model: '',
  skip_ssl_verify: false,
  parallel_requests: 4,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.config.getHostedASR).mockResolvedValue({ ...saved });
  vi.mocked(api.config.updateHostedASR).mockImplementation(async (update) => ({ ...saved, ...update }));
  vi.mocked(api.config.getHostedASRModels).mockResolvedValue({
    models: ['Systran/faster-whisper-small.en', 'istupakov/parakeet-tdt-0.6b-v2-onnx'],
    error: null,
  });
});

describe('HostedASRSettings', () => {
  it('shows the saved settings and offers the models the server lists', async () => {
    const user = userEvent.setup();
    render(HostedASRSettings);

    expect(await screen.findByDisplayValue('http://gpu-box:8000/v1')).toBeTruthy();
    // The saved key itself never reaches the browser
    expect(screen.getByPlaceholderText('Saved (type to replace)')).toBeTruthy();
    await user.click(await screen.findByRole('button', { name: "Show the server's models" }));
    expect(screen.getAllByRole('option').map((o) => o.textContent?.trim())).toEqual([
      'Systran/faster-whisper-small.en',
      'istupakov/parakeet-tdt-0.6b-v2-onnx',
    ]);
  });

  it('saves a model picked from the list right away', async () => {
    const user = userEvent.setup();
    render(HostedASRSettings);

    await user.click(await screen.findByRole('button', { name: "Show the server's models" }));
    await user.click(screen.getByRole('option', { name: 'istupakov/parakeet-tdt-0.6b-v2-onnx' }));

    expect(api.config.updateHostedASR).toHaveBeenCalledWith({ model: 'istupakov/parakeet-tdt-0.6b-v2-onnx' });
    expect(screen.getByRole('combobox')).toHaveProperty('value', 'istupakov/parakeet-tdt-0.6b-v2-onnx');
  });

  it('saves only the edited field and refreshes the model list when the server changes', async () => {
    const user = userEvent.setup();
    render(HostedASRSettings);
    const url = await screen.findByDisplayValue('http://gpu-box:8000/v1');

    await user.clear(url);
    await user.type(url, 'http://other:9000/v1');
    await user.tab();

    await waitFor(() => expect(api.config.updateHostedASR).toHaveBeenCalled());
    const updates = vi.mocked(api.config.updateHostedASR).mock.calls.map(([update]) => update);
    expect(updates.every((u) => Object.keys(u).join() === 'base_url')).toBe(true);
    expect(updates.at(-1)).toEqual({ base_url: 'http://other:9000/v1' });
    await waitFor(() => expect(api.config.getHostedASRModels).toHaveBeenCalledTimes(2));
  });

  it('removes a saved key', async () => {
    const user = userEvent.setup();
    render(HostedASRSettings);

    await user.click(await screen.findByRole('button', { name: 'Remove API key' }));

    expect(api.config.updateHostedASR).toHaveBeenCalledWith({ api_key: '' });
    await waitFor(() => expect(screen.getByPlaceholderText('Leave blank if not required')).toBeTruthy());
  });

  it('saves pending edits before testing and shows the result', async () => {
    const user = userEvent.setup();
    vi.mocked(api.config.testHostedASR).mockResolvedValue({
      success: false,
      message: "Not found (HTTP 404): Model 'whisper-1' is not installed locally",
    });
    render(HostedASRSettings);
    const model = await screen.findByPlaceholderText('Select or type a model');

    await user.type(model, 'whisper-1');
    await user.click(screen.getByRole('button', { name: 'Test Connection' }));

    expect(await screen.findByText(/is not installed locally/)).toBeTruthy();
    const order = (fn: unknown) => vi.mocked(fn as () => void).mock.invocationCallOrder.at(-1) ?? 0;
    expect(vi.mocked(api.config.updateHostedASR).mock.calls.at(-1)?.[0]).toEqual({ model: 'whisper-1' });
    expect(order(api.config.updateHostedASR)).toBeLessThan(order(api.config.testHostedASR));
  });

  it('clamps parallel requests', async () => {
    const user = userEvent.setup();
    render(HostedASRSettings);
    const parallel = await screen.findByLabelText('Parallel requests');

    await user.clear(parallel);
    await user.type(parallel, '40');
    await user.tab();

    await waitFor(() => expect(api.config.updateHostedASR).toHaveBeenCalledWith({ parallel_requests: 16 }));
    expect((parallel as HTMLInputElement).value).toBe('16');
  });
});
