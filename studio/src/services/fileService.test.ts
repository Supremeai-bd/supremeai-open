import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./apiClient', () => ({
  apiClient: {
    get: vi.fn(),
    postForm: vi.fn(),
    delete: vi.fn(),
  },
}));

import { fileService, formatBytes } from './fileService';
import { apiClient } from './apiClient';

const mockedClient = apiClient as unknown as {
  get: ReturnType<typeof vi.fn>;
  postForm: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
};

describe('fileService (ERR-B02)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('listFiles GETs /api/chat/upload', async () => {
    mockedClient.get.mockResolvedValue({ items: [], total: 0 });
    const res = await fileService.listFiles();
    expect(apiClient.get).toHaveBeenCalledWith('/api/chat/upload');
    expect(res.total).toBe(0);
  });

  it('uploadFile sends multipart FormData to the upload endpoint', async () => {
    mockedClient.postForm.mockResolvedValue({
      attachment_id: 'a1',
      url: '/api/chat/upload/a1',
      name: 'pic.png',
      size: 12,
      mime_type: 'image/png',
    });
    const file = new File(['hello'], 'pic.png', { type: 'image/png' });
    const res = await fileService.uploadFile(file);
    expect(mockedClient.postForm).toHaveBeenCalledTimes(1);
    const [path, form] = mockedClient.postForm.mock.calls[0];
    expect(path).toBe('/api/chat/upload/');
    expect(form).toBeInstanceOf(FormData);
    expect(form.get('file')).toBe(file);
    expect(res.attachment_id).toBe('a1');
  });

  it('deleteFile DELETEs the attachment resource', async () => {
    mockedClient.delete.mockResolvedValue({ status: 'deleted' });
    await fileService.deleteFile('a1');
    expect(apiClient.delete).toHaveBeenCalledWith('/api/chat/upload/a1');
  });
});

describe('formatBytes', () => {
  it('formats human-readable sizes', () => {
    expect(formatBytes(500)).toBe('500 B');
    expect(formatBytes(2048)).toBe('2.0 KB');
    expect(formatBytes(5 * 1024 * 1024)).toBe('5.0 MB');
    expect(formatBytes(NaN)).toBe('—');
  });
});
