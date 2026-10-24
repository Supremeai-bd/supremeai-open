import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { SettingsPage } from './SettingsPage';
import { connectionsApi } from '../../services/connectionsApi';

vi.mock('../../services/apiClient', () => ({
  apiClient: {
    get: vi.fn().mockImplementation((path: string) => {
      if (path.includes('/preferences/')) {
        return Promise.resolve({
          theme: 'dark',
          default_model: 'gpt-4o',
          max_tokens: 4096,
          auto_save: true,
          verbosity: 'normal',
        });
      }
      if (path.includes('/admin/trusted-browsers')) {
        return Promise.resolve({ browsers: [] });
      }
      return Promise.resolve({});
    }),
    post: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock('../../services/connectionsApi', () => ({
  connectionsApi: {
    getMyWorkspace: vi.fn().mockResolvedValue({
      userId: 'test-user',
      executionMode: 'ask_before_acting',
      capabilities: [],
      connections: [],
      authorizedContexts: [],
      recentActivity: [],
    }),
    setExecutionMode: vi.fn().mockResolvedValue({
      user_id: 'test-user',
      mode: 'autonomous',
      persisted: true,
      message: 'Execution mode updated to autonomous',
    }),
  },
}));

describe('SettingsPage - Execution Mode integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders all three execution modes with labels', async () => {
    render(<SettingsPage theme="dark" toggleTheme={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('Execution Mode')).toBeInTheDocument();
    });

    expect(screen.getByTestId('execution-mode-read_only')).toBeInTheDocument();
    expect(screen.getByTestId('execution-mode-ask_before_acting')).toBeInTheDocument();
    expect(screen.getByTestId('execution-mode-autonomous')).toBeInTheDocument();
  });

  it('loads the active execution mode from workspace', async () => {
    vi.mocked(connectionsApi.getMyWorkspace).mockResolvedValueOnce({
      userId: 'test-user',
      executionMode: 'read_only',
      capabilities: [],
      connections: [],
      authorizedContexts: [],
      recentActivity: [],
    });

    render(<SettingsPage theme="dark" toggleTheme={vi.fn()} />);

    await waitFor(() => {
      const readOnlyRadio = screen.getByRole('radio', { name: /read only/i });
      expect(readOnlyRadio).toBeChecked();
    });
  });

  it('calls setExecutionMode when a new mode is selected', async () => {
    render(<SettingsPage theme="dark" toggleTheme={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('Execution Mode')).toBeInTheDocument();
    });

    const autonomousRadio = screen.getByRole('radio', { name: /autonomous/i });
    fireEvent.click(autonomousRadio);

    await waitFor(() => {
      expect(connectionsApi.setExecutionMode).toHaveBeenCalledWith('autonomous');
    });

    await waitFor(() => {
      expect(screen.getByTestId('execution-mode-status')).toHaveTextContent(
        'Execution mode updated to autonomous',
      );
    });
  });
});
