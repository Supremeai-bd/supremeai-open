import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../services/fileService', () => ({
  fileService: {
    listFiles: vi.fn(),
    uploadFile: vi.fn(),
    deleteFile: vi.fn(),
  },
  formatBytes: (n: number) => `${n} B`,
}));

// বাংলা: WorkspaceLayout (UnifiedAppShell) ভারী — পেজ লজিক টেস্টে হালকা stub।
vi.mock('../components/layout/WorkspaceLayout', () => ({
  WorkspaceLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { FilesPage } from './FilesPage';
import { fileService } from '../services/fileService';

const mockedService = fileService as unknown as {
  listFiles: ReturnType<typeof vi.fn>;
  uploadFile: ReturnType<typeof vi.fn>;
  deleteFile: ReturnType<typeof vi.fn>;
};

const renderPage = () =>
  render(
    <MemoryRouter>
      <FilesPage />
    </MemoryRouter>,
  );

const sampleFile = {
  attachment_id: 'a1',
  url: '/api/chat/upload/a1',
  name: 'team-photo.png',
  size: 1024,
  mime_type: 'image/png',
  created_at: '2026-09-16T12:00:00Z',
};

describe('FilesPage (ERR-B02)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedService.listFiles.mockResolvedValue({ items: [], total: 0 });
  });

  it('renders dropzone with hidden file-input and shows empty state', async () => {
    renderPage();
    expect(screen.getByTestId('file-dropzone')).toBeInTheDocument();
    expect(screen.getByTestId('file-input')).toBeInTheDocument();
    expect(await screen.findByTestId('files-empty')).toBeInTheDocument();
  });

  it('uploads a selected file and refreshes the explorer', async () => {
    mockedService.uploadFile.mockResolvedValue(sampleFile);
    mockedService.listFiles
      .mockResolvedValueOnce({ items: [], total: 0 })
      .mockResolvedValueOnce({ items: [sampleFile], total: 1 });

    renderPage();
    await screen.findByTestId('files-empty');

    const input = screen.getByTestId('file-input') as HTMLInputElement;
    const file = new File(['data'], 'team-photo.png', { type: 'image/png' });
    await userEvent.upload(input, file);

    await waitFor(() => {
      expect(mockedService.uploadFile).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(screen.getAllByTestId('file-card')).toHaveLength(1);
    });
    expect(screen.getByText('team-photo.png')).toBeInTheDocument();
  });

  it('lists uploaded files with thumbnails and delete controls', async () => {
    mockedService.listFiles.mockResolvedValue({ items: [sampleFile], total: 1 });
    renderPage();
    expect(await screen.findByTestId('file-card')).toBeInTheDocument();
    expect(screen.getByText('team-photo.png')).toBeInTheDocument();
    expect(screen.getByTestId('file-delete-btn-a1')).toBeInTheDocument();
    const img = screen.getByAltText('team-photo.png');
    expect(img).toHaveAttribute('src', '/api/chat/upload/a1');
  });

  it('deletes a file and removes it from the list', async () => {
    mockedService.deleteFile.mockResolvedValue(undefined);
    mockedService.listFiles.mockResolvedValue({ items: [sampleFile], total: 1 });

    renderPage();
    await screen.findByTestId('file-card');
    await userEvent.click(screen.getByTestId('file-delete-btn-a1'));

    await waitFor(() => {
      expect(mockedService.deleteFile).toHaveBeenCalledWith('a1');
    });
    await waitFor(() => {
      expect(screen.queryByTestId('file-card')).not.toBeInTheDocument();
    });
  });

  it('shows an honest error state when listing fails', async () => {
    mockedService.listFiles.mockRejectedValue(new Error('storage offline'));
    renderPage();
    expect(await screen.findByTestId('files-error')).toBeInTheDocument();
    expect(screen.getByText('storage offline')).toBeInTheDocument();
  });

  it('surfaces upload errors verbatim', async () => {
    mockedService.uploadFile.mockRejectedValue(new Error('playwright pool exhausted'));
    renderPage();
    await screen.findByTestId('files-empty');

    const input = screen.getByTestId('file-input') as HTMLInputElement;
    await userEvent.upload(
      input,
      new File(['data'], 'big.png', { type: 'image/png' }),
    );

    expect(await screen.findByTestId('file-upload-error')).toBeInTheDocument();
    expect(screen.getByText('playwright pool exhausted')).toBeInTheDocument();
  });
});
