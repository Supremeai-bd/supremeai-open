import { useState, useRef, useCallback } from 'react';
import { ImagePlus, X, Loader2 } from 'lucide-react';
import { getApiBaseUrl } from '../../utils/api';
import { getAdminToken, getUserToken } from '../../services/tokenStorage';
import { globalShowToastRef } from '../../contexts/ToastContext';

// ─── Types ───────────────────────────────────────────────────────────────

interface ChatAttachment {
  id: string;
  url: string;
  name: string;
  size: number;
  mime_type: string;
}

interface ImageUploadButtonProps {
  onUpload: (attachment: ChatAttachment) => void;
  disabled?: boolean;
}

interface UploadResponse {
  id: string;
  url: string;
  name: string;
  size: number;
  mime_type: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const k = 1024;
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const size = parseFloat((bytes / Math.pow(k, i)).toFixed(1));
  return `${size} ${units[i]}`;
}

const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20 MB

// ─── Component ───────────────────────────────────────────────────────────

export function ImageUploadButton({ onUpload, disabled }: ImageUploadButtonProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [preview, setPreview] = useState<{ url: string; name: string } | null>(null);

  const handleFileSelect = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;

      // Validate file type
      if (!file.type.startsWith('image/')) {
        globalShowToastRef.current('error', 'Please select an image file');
        return;
      }

      // Validate file size
      if (file.size > MAX_FILE_SIZE) {
        globalShowToastRef.current('error', `File too large. Maximum size is ${formatFileSize(MAX_FILE_SIZE)}`);
        return;
      }

      // Show preview immediately
      const objectUrl = URL.createObjectURL(file);
      setPreview({ url: objectUrl, name: file.name });

      setIsUploading(true);
      setUploadProgress(0);

      try {
        const formData = new FormData();
        formData.append('file', file);

        // Use XMLHttpRequest for progress tracking
        const result = await new Promise<UploadResponse>((resolve, reject) => {
          const xhr = new XMLHttpRequest();

          xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
              const percent = Math.round((e.loaded / e.total) * 100);
              setUploadProgress(percent);
            }
          });

          xhr.addEventListener('load', () => {
            if (xhr.status >= 200 && xhr.status < 300) {
              try {
                const data: UploadResponse = JSON.parse(xhr.responseText);
                resolve(data);
              } catch {
                reject(new Error('Failed to parse upload response'));
              }
            } else {
              try {
                const errData = JSON.parse(xhr.responseText);
                reject(new Error(errData.detail || errData.message || `Upload failed (${xhr.status})`));
              } catch {
                reject(new Error(`Upload failed (${xhr.status})`));
              }
            }
          });

          xhr.addEventListener('error', () => {
            reject(new Error('Network error during upload'));
          });

          xhr.addEventListener('abort', () => {
            reject(new Error('Upload cancelled'));
          });

          // Get auth token — Issue #521: tokenStorage (sessionStorage-first,
          // legacy localStorage swept).
          const token = getUserToken() || getAdminToken();
          const headers: Record<string, string> = {};
          if (token) {
            headers['Authorization'] = `Bearer ${token}`;
          }

          xhr.open('POST', `${getApiBaseUrl()}/api/chat/upload/`);

          // Set auth headers
          Object.entries(headers).forEach(([key, value]) => {
            xhr.setRequestHeader(key, value);
          });

          xhr.send(formData);
        });

        onUpload({
          id: result.id,
          url: result.url,
          name: result.name,
          size: result.size,
          mime_type: result.mime_type,
        });

        globalShowToastRef.current('success', 'Image uploaded successfully!');
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Upload failed';
        globalShowToastRef.current('error', message);
        setPreview(null);
      } finally {
        setIsUploading(false);
        setUploadProgress(0);
        // Reset input so the same file can be re-selected
        if (fileInputRef.current) {
          fileInputRef.current.value = '';
        }
      }
    },
    [onUpload]
  );

  const handleClearPreview = useCallback(() => {
    if (preview) {
      URL.revokeObjectURL(preview.url);
    }
    setPreview(null);
  }, [preview]);

  const handleClick = useCallback(() => {
    if (disabled || isUploading) return;
    fileInputRef.current?.click();
  }, [disabled, isUploading]);

  return (
    <div className="flex items-center gap-2">
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        onChange={handleFileSelect}
        className="hidden"
        aria-label="Upload image"
      />

      {/* Upload Button */}
      <button
        type="button"
        onClick={handleClick}
        disabled={disabled || isUploading}
        className={`flex items-center justify-center w-9 h-9 rounded-lg transition-all ${
            disabled || isUploading
              ? 'text-slate-300 dark:text-slate-600 cursor-not-allowed'
              : 'text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
          }`}
        aria-label="Upload image"
        title="Upload image"
      >
        {isUploading ? (
          <Loader2 className="w-5 h-5 animate-spin text-violet-500" />
        ) : (
          <ImagePlus className="w-5 h-5" />
        )}
      </button>

      {/* Preview Thumbnail */}
      {preview && (
        <div className="relative group">
          <div className="w-10 h-10 rounded-lg overflow-hidden border-2 border-violet-400 dark:border-violet-500 shadow-sm">
            <img
              src={preview.url}
              alt={preview.name}
              className="w-full h-full object-cover"
            />
          </div>

          {/* Clear button overlay */}
          <button
            type="button"
            onClick={handleClearPreview}
            className="absolute -top-1.5 -right-1.5 flex items-center justify-center w-5 h-5 rounded-full bg-red-500 text-white shadow-sm opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-600"
            aria-label="Remove image"
          >
            <X className="w-3 h-3" />
          </button>

          {/* Upload progress bar under thumbnail */}
          {isUploading && (
            <div className="absolute -bottom-1 left-0 right-0 h-1 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
              <div
                className="h-full bg-violet-500 transition-all duration-200 rounded-full"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
