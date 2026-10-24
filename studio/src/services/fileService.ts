// Files Service — ERR-B02 fix (canonical defect register 2026-09-15)
// বাংলা মন্তব্য: /files পেজ আগে blank ছিল (WorkspaceModulePage module="files"
// modules record-এই ছিল না)। এই সার্ভিস ব্যাকএন্ডের `/api/chat/upload` কনট্র্যাক্টের
// সাথে পেজটিকে যুক্ত করে: upload / list / delete (+ serve URL helper)।

import { apiClient } from './apiClient';

export interface StoredFile {
  attachment_id: string;
  url: string;
  name: string;
  size: number;
  mime_type: string;
  created_at: string;
}

export interface FileListResponse {
  items: StoredFile[];
  total: number;
}

export const fileService = {
  listFiles: async (): Promise<FileListResponse> => {
    return apiClient.get<FileListResponse>('/api/chat/upload');
  },

  uploadFile: async (file: File): Promise<StoredFile> => {
    const form = new FormData();
    form.append('file', file);
    return apiClient.postForm<StoredFile>('/api/chat/upload/', form);
  },

  deleteFile: async (attachmentId: string): Promise<void> => {
    await apiClient.delete<{ status: string }>(`/api/chat/upload/${attachmentId}`);
  },
};

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '—';
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unit]}`;
}
