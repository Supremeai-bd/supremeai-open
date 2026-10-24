import { describe, it, expect, vi } from 'vitest';
import { uploadFileToR2 } from './storageApi';

describe('storageApi — uploadFileToR2', () => {
  it('uploads a file and returns the stored path', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ upload_url: 'https://r2/put', file_path: 'custom_skills/abc.txt' }),
      })
      .mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    vi.stubGlobal('fetch', fetchMock);

    window.localStorage.setItem('supreme_admin_jwt', 'admin-token');
    const file = new File(['hello'], 'abc.txt', { type: 'text/plain' });

    const path = await uploadFileToR2(file);

    expect(path).toBe('custom_skills/abc.txt');
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      expect.stringContaining('/api/v1/media/generate-upload-url'),
      expect.objectContaining({ method: 'POST', headers: expect.objectContaining({ Authorization: 'Bearer admin-token' }) })
    );
  });

  it('throws when the upload-url request fails', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}) });
    vi.stubGlobal('fetch', fetchMock);

    const file = new File(['hello'], 'abc.txt', { type: 'text/plain' });
    await expect(uploadFileToR2(file)).rejects.toThrow();
  });
});
