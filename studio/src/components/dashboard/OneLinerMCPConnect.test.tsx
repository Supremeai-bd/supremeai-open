import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { OneLinerMCPConnect } from './OneLinerMCPConnect';
import { apiClient } from '../../services/apiClient';

vi.mock('../../services/apiClient', () => ({
  apiClient: {
    post: vi.fn(),
  },
}));

describe('OneLinerMCPConnect', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the 1-line connect input and button', () => {
    render(<OneLinerMCPConnect />);
    expect(screen.getByTestId('one-liner-mcp-connect')).toBeDefined();
    expect(screen.getByLabelText('Integration URL')).toBeDefined();
    expect(screen.getByTestId('mcp-connect-btn')).toBeDefined();
  });

  it('button is disabled when input is empty', () => {
    render(<OneLinerMCPConnect />);
    const btn = screen.getByTestId('mcp-connect-btn') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it('shows success card on successful MCP discovery', async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      id: 'mcp:x',
      name: 'My MCP Server',
      type: 'mcp',
      status: 'connected',
      capabilities: ['tools', 'resources'],
    });

    render(<OneLinerMCPConnect />);
    const input = screen.getByLabelText('Integration URL');
    fireEvent.change(input, { target: { value: 'https://my-mcp-server.com' } });
    fireEvent.click(screen.getByTestId('mcp-connect-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('mcp-connect-success')).toBeDefined();
    });
    expect(screen.getByText(/My MCP Server/)).toBeDefined();
    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/integrations/discover', {
      url: 'https://my-mcp-server.com',
      register: true,
    });
  });

  it('shows inline error when discovery fails', async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      id: '',
      name: '',
      type: 'unknown',
      status: 'failed',
      capabilities: [],
      error: 'Endpoint unreachable or not recognizable as MCP/AI provider/webhook',
    });

    render(<OneLinerMCPConnect />);
    fireEvent.change(screen.getByLabelText('Integration URL'), {
      target: { value: 'https://dead-endpoint.invalid' },
    });
    fireEvent.click(screen.getByTestId('mcp-connect-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('mcp-connect-error')).toBeDefined();
    });
  });

  it('shows error when apiClient throws', async () => {
    vi.mocked(apiClient.post).mockRejectedValueOnce(new Error('Network down'));

    render(<OneLinerMCPConnect />);
    fireEvent.change(screen.getByLabelText('Integration URL'), {
      target: { value: 'https://api.openai.com/v1' },
    });
    fireEvent.click(screen.getByTestId('mcp-connect-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('mcp-connect-error')).toBeDefined();
    });
    expect(screen.getByText(/Network down/)).toBeDefined();
  });
});
