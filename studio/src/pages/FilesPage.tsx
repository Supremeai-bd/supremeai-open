// FilesPage — real file explorer (ERR-B02 fix)
// বাংলা মন্তব্য: /files রুট আগে `WorkspaceModulePage module="files"` রেন্ডার করত,
// যেটা modules record-এই ছিল না → blank পেজ (ERR-B02, canonical defect register
// 2026-09-15)। এখন real dropzone + explorer, ব্যাকএন্ড `/api/chat/upload`
// (upload / list / serve / delete) কনট্র্যাক্টে যুক্ত।

import { useCallback, useRef, useState } from 'react';
import { ArrowRight, FileImage, Trash2, UploadCloud } from 'lucide-react';
import { WorkspaceLayout } from '../components/layout/WorkspaceLayout';
import { useListResource } from '../hooks/useListResource';
import { fileService, formatBytes, type StoredFile } from '../services/fileService';
import { safeUrl } from '../lib/safeUrl';

const ACCEPTED_MIME =
  'image/jpeg,image/png,image/gif,image/webp,image/svg+xml,image/bmp,image/tiff,image/avif';

function formatUploadedDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return iso;
  }
}

export function FilesPage() {
  // বাংলা (Wave 3 dedup): files/isLoading/loadError + load + useEffect ক্লাস্টারটি
  // এখন useListResource হুকে; setItems দিয়ে delete-এর optimistic filter আগের মতোই।
  const {
    items: files,
    isLoading,
    loadError,
    reload: loadFiles,
    setItems: setFiles,
  } = useListResource<StoredFile>({
    fetcher: async () => (await fileService.listFiles()).items,
  });
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    async (selected: FileList | null) => {
      if (!selected || selected.length === 0) return;
      setIsUploading(true);
      setUploadError(null);
      try {
        for (const file of Array.from(selected)) {
          await fileService.uploadFile(file);
        }
        await loadFiles();
      } catch (err) {
        setUploadError(err instanceof Error ? err.message : 'Upload failed');
      } finally {
        setIsUploading(false);
        if (inputRef.current) inputRef.current.value = '';
      }
    },
    [loadFiles],
  );

  const handleDelete = async (attachmentId: string) => {
    setDeletingId(attachmentId);
    try {
      await fileService.deleteFile(attachmentId);
      setFiles((prev) => prev.filter((f) => f.attachment_id !== attachmentId));
    } catch {
      await loadFiles(); // honest failure — resync with server truth
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <WorkspaceLayout>
      <div className="mx-auto w-full max-w-7xl px-5 py-8 text-[var(--sa-ink)] sm:px-8 lg:py-10">
        <header className="flex flex-col gap-4 border-b border-[var(--sa-border)] pb-8 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="sa-eyebrow">Build / Files</p>
            <h1 className="mt-2 max-w-3xl text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
              Every asset, one explorer.
            </h1>
            <p className="mt-2 max-w-2xl text-[var(--sa-ink-muted)]">
              Upload images once and reference them from any conversation or
              project space.
            </p>
          </div>
        </header>

        {/* Dropzone */}
        <div
          data-testid="file-dropzone"
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragOver(true);
          }}
          onDragLeave={() => setIsDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragOver(false);
            void handleFiles(e.dataTransfer.files);
          }}
          className={`mt-8 flex flex-col items-center justify-center gap-3 border-2 border-dashed p-10 text-center transition ${
            isDragOver
              ? 'border-[var(--sa-primary)] bg-[var(--sa-primary-soft)]'
              : 'border-[var(--sa-border)]'
          }`}
        >
          <div className="flex size-12 items-center justify-center rounded-xl bg-[var(--sa-primary-soft)] text-[var(--sa-primary)]">
            <UploadCloud size={22} />
          </div>
          <p className="text-sm font-medium">
            {isUploading ? 'Uploading…' : 'Drag & drop images here, or'}
          </p>
          <button
            type="button"
            data-testid="file-browse-btn"
            onClick={() => inputRef.current?.click()}
            disabled={isUploading}
            className="rounded-[var(--sa-radius-sm)] bg-[var(--sa-primary)] px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
          >
            Browse files
          </button>
          <input
            ref={inputRef}
            type="file"
            data-testid="file-input"
            accept={ACCEPTED_MIME}
            multiple
            className="sr-only"
            onChange={(e) => void handleFiles(e.target.files)}
            aria-label="Upload files"
          />
          <p className="text-xs text-[var(--sa-ink-muted)]">
            JPEG, PNG, GIF, WebP, SVG, BMP, TIFF, AVIF — up to 10&nbsp;MB each
          </p>
          {uploadError && (
            <p role="alert" data-testid="file-upload-error" className="text-sm text-red-400">
              {uploadError}
            </p>
          )}
        </div>

        {/* Explorer */}
        <section className="mt-8" aria-label="Uploaded files">
          {isLoading ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[0, 1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="sa-surface-raised h-52 animate-pulse rounded-[var(--sa-radius-sm)]"
                  aria-hidden="true"
                />
              ))}
            </div>
          ) : loadError ? (
            <div
              role="alert"
              data-testid="files-error"
              className="flex flex-col gap-3 border border-red-500/40 bg-red-500/5 p-4 text-sm sm:flex-row sm:items-center"
            >
              <span className="text-red-400">{loadError}</span>
              <button
                type="button"
                onClick={() => void loadFiles()}
                className="rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] px-3 py-1.5 font-medium transition hover:border-[var(--sa-primary)] sm:ml-auto"
              >
                Try again
              </button>
            </div>
          ) : files.length === 0 ? (
            <div
              data-testid="files-empty"
              className="sa-surface-raised flex flex-col items-center gap-2 p-10 text-center"
            >
              <FileImage size={22} className="text-[var(--sa-primary)]" />
              <h2 className="text-lg font-semibold">No files yet</h2>
              <p className="max-w-md text-sm text-[var(--sa-ink-muted)]">
                Upload your first image and it will show up here, ready to attach
                anywhere.
              </p>
            </div>
          ) : (
            <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {files.map((file) => (
                <li
                  key={file.attachment_id}
                  data-testid="file-card"
                  className="sa-surface-raised group overflow-hidden"
                >
                  <div className="flex h-32 items-center justify-center overflow-hidden bg-[var(--sa-canvas)]">
                    <img
                      src={file.url}
                      alt={file.name}
                      loading="lazy"
                      className="max-h-full max-w-full object-contain"
                    />
                  </div>
                  <div className="p-4">
                    <p className="truncate text-sm font-medium" title={file.name}>
                      {file.name}
                    </p>
                    <p className="mt-1 text-xs text-[var(--sa-ink-muted)]">
                      {formatBytes(file.size)} · {formatUploadedDate(file.created_at)}
                    </p>
                    <div className="mt-3 flex items-center justify-between">
                      <a
                        // বাংলা মন্তব্য: safeUrl allowlist (#2520)
                        href={safeUrl(file.url)}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-xs font-medium text-[var(--sa-primary)]"
                      >
                        Open <ArrowRight size={12} />
                      </a>
                      <button
                        type="button"
                        data-testid={`file-delete-btn-${file.attachment_id}`}
                        aria-label={`Delete ${file.name}`}
                        onClick={() => void handleDelete(file.attachment_id)}
                        disabled={deletingId === file.attachment_id}
                        className="rounded-md p-1.5 text-[var(--sa-ink-muted)] transition hover:bg-red-500/10 hover:text-red-400 disabled:opacity-50"
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </WorkspaceLayout>
  );
}

export default FilesPage;
