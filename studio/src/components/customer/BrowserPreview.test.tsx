import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../../services/browserService', () => ({
  browserService: {
    createSession: vi.fn(),
    execute: vi.fn(),
    closeSession: vi.fn(),
  },
}));

import { BrowserPreview } from './BrowserPreview';
import { browserService } from '../../services/browserService';

const mockedService = vi.mocked(browserService);

describe('BrowserPreview ERR-A03 screenshot proxy', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedService.closeSession.mockResolvedValue({ success: true });
  });

  it('renders external URLs via the screenshot proxy instead of a raw iframe', async () => {
    mockedService.createSession.mockResolvedValue({ session_id: 's1', status: 'ready', url: '' });
    mockedService.execute.mockImplementation(async (_id: string, action: { action: string }) => {
      if (action.action === 'navigate') return { success: true, action: 'navigate', url: 'https://example.gov' };
      return { success: true, action: 'screenshot', url: 'https://example.gov', screenshot: 'PNGBASE64' };
    });

    render(<BrowserPreview url="https://example.gov" />);
    const img = await waitFor(() => screen.getByTestId('screenshot-proxy-view'));
    expect(img).toHaveAttribute('src', 'data:image/png;base64,PNGBASE64');
    // no raw external iframe is mounted in proxy mode
    expect(document.querySelector('iframe[src="https://example.gov"]')).toBeNull();
    expect(mockedService.execute).toHaveBeenCalledWith('s1', { action: 'navigate', url: 'https://example.gov' });
    expect(mockedService.execute).toHaveBeenCalledWith('s1', { action: 'screenshot', full_page: false });
  });

  it('displays the image returned by the capture button (previously discarded)', async () => {
    mockedService.createSession.mockResolvedValue({ session_id: 's2', status: 'ready', url: '' });
    mockedService.execute.mockImplementation(async (_id: string, action: { action: string }) => {
      if (action.action === 'navigate') return { success: true, action: 'navigate', url: 'https://example.gov' };
      if (action.action === 'screenshot' && (action as { full_page?: boolean }).full_page)
        return { success: true, action: 'screenshot', url: '', screenshot: 'FULLPAGEPNG' };
      return { success: true, action: 'screenshot', url: '', screenshot: 'VIEWPORTPNG' };
    });

    render(<BrowserPreview url="https://example.gov" />);
    await waitFor(() => screen.getByTestId('screenshot-proxy-view'));

    fireEvent.click(screen.getByRole('button', { name: /capture full-page screenshot/i }));
    const img = await waitFor(() => screen.getByTestId('screenshot-proxy-view'));
    expect(img).toHaveAttribute('src', 'data:image/png;base64,FULLPAGEPNG');
  });

  it('shows the verbatim backend error honestly instead of a blank frame', async () => {
    mockedService.createSession.mockRejectedValue(new Error('playwright pool exhausted'));

    render(<BrowserPreview url="https://example.gov" />);
    await waitFor(() => expect(screen.getByText(/playwright pool exhausted/)).toBeInTheDocument());
    expect(document.querySelector('iframe')).toBeNull();
    expect(screen.getByRole('link', { name: /open directly/i })).toHaveAttribute(
      'href',
      'https://example.gov',
    );
  });

  it('keeps the iframe for same-origin generated html content', () => {
    render(<BrowserPreview html="<h1>generated</h1>" />);
    const frame = document.querySelector('iframe');
    expect(frame).not.toBeNull();
    expect(frame).toHaveAttribute('srcdoc', '<h1>generated</h1>');
  });
});
