import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { UpdateStatusResponse } from '../types';
import UpdateDialog from './UpdateDialog.svelte';

vi.mock('../utils/api', () => ({
  api: {
    update: {
      getStatus: vi.fn(),
      run: vi.fn(),
    },
    session: {
      getStatus: vi.fn(),
    },
  },
}));

import { api } from '../utils/api';

function mockStatus(status: Partial<UpdateStatusResponse>) {
  vi.mocked(api.update.getStatus).mockResolvedValue({
    install: 'archive',
    version: '1.0.0',
    can_update: true,
    reason: null,
    command: null,
    ...status,
  });
}

function renderDialog() {
  render(UpdateDialog, { isOpen: true, currentVersion: '1.0.0', latestVersion: '1.1.0', releaseUrl: null });
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('UpdateDialog', () => {
  it('updates from the app when the install supports it', async () => {
    mockStatus({});
    vi.mocked(api.update.run).mockResolvedValue({ updated: false, version: '1.0.0' });
    renderDialog();

    await userEvent.click(await screen.findByRole('button', { name: 'Update Now' }));

    expect(api.update.run).toHaveBeenCalledOnce();
    expect(await screen.findByText('Achew is already up to date.')).toBeInTheDocument();
  });

  it('shows why it can’t update, with the terminal command to use instead', async () => {
    mockStatus({ can_update: false, reason: 'Started some other way.', command: './run.sh --update' });
    renderDialog();

    expect(await screen.findByText('Started some other way.')).toBeInTheDocument();
    expect(screen.getByText('./run.sh --update')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Update Now' })).not.toBeInTheDocument();
  });

  it('tells Docker users to pull the new image', async () => {
    mockStatus({ install: 'docker', can_update: false });
    renderDialog();

    expect(await screen.findByText('docker compose pull && docker compose up -d')).toBeInTheDocument();
  });

  it('shows update errors and lets the user try again', async () => {
    mockStatus({});
    vi.mocked(api.update.run).mockRejectedValue(new Error('Couldn’t look up the latest Achew release'));
    renderDialog();

    await userEvent.click(await screen.findByRole('button', { name: 'Update Now' }));

    expect(await screen.findByText('Couldn’t look up the latest Achew release')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try Again' })).toBeInTheDocument();
  });
});
