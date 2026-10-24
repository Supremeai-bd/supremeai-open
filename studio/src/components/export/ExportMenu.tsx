import { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Download,
  FileText,
  FileDown,
  Loader2,
  ChevronDown,
  File,
} from 'lucide-react';
import { globalShowToastRef } from '../../contexts/ToastContext';
import { getAdminToken, getUserToken } from '../../services/tokenStorage';

// ─── Types ───────────────────────────────────────────────────────────────

interface ExportMenuProps {
  conversationId: string;
  conversationTitle?: string;
}

type ExportFormat = 'markdown' | 'pdf' | 'word';

interface ExportOption {
  format: ExportFormat;
  label: string;
  description: string;
  icon: React.ReactNode;
  fileExtension: string;
}

// ─── Constants ───────────────────────────────────────────────────────────

const EXPORT_OPTIONS: ExportOption[] = [
  {
    format: 'markdown',
    label: 'Markdown',
    description: 'Export as .md file',
    icon: <FileText className="w-4 h-4" />,
    fileExtension: 'md',
  },
  {
    format: 'pdf',
    label: 'PDF',
    description: 'Export as .pdf document',
    icon: <FileDown className="w-4 h-4" />,
    fileExtension: 'pdf',
  },
  {
    format: 'word',
    label: 'Word',
    description: 'Export as .docx file',
    icon: <File className="w-4 h-4" />,
    fileExtension: 'docx',
  },
];

// ─── Component ───────────────────────────────────────────────────────────

export default function ExportMenu({ conversationId, conversationTitle }: ExportMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isExporting, setIsExporting] = useState<ExportFormat | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const handleClickOutside = useCallback((event: MouseEvent) => {
    if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
      setIsOpen(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen, handleClickOutside]);

  const handleExport = useCallback(async (option: ExportOption) => {
    if (isExporting) return;

    setIsExporting(option.format);
    setIsOpen(false);

    try {
      // Fetch export blob directly
      const baseUrl = window.location.origin;
      // Issue #521: tokenStorage (sessionStorage-first, legacy localStorage swept).
      const token = getUserToken() || getAdminToken();

      const blobResponse = await fetch(`${baseUrl}/api/chat/export`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          conversation_id: conversationId,
          format: option.format,
        }),
      });

      if (!blobResponse.ok) {
        throw new Error(`Export failed with status ${blobResponse.status}`);
      }

      const blob = await blobResponse.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      const safeTitle = (conversationTitle || 'conversation').replace(/[^a-z0-9]/gi, '_').toLowerCase();
      link.href = url;
      link.download = `${safeTitle}.${option.fileExtension}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

      globalShowToastRef.current('success', `Exported as ${option.label} successfully!`);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Export failed. Please try again.';
      globalShowToastRef.current('error', message);
    } finally {
      setIsExporting(null);
    }
  }, [conversationId, conversationTitle, isExporting]);

  const isAnyExporting = isExporting !== null;

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        disabled={isAnyExporting}
        className={
          'flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-xl transition-all ' +
          'text-slate-600 dark:text-slate-300 ' +
          'hover:bg-slate-100 dark:hover:bg-slate-800 ' +
          'disabled:opacity-50 disabled:cursor-not-allowed'
        }
        aria-label="Export conversation"
        aria-haspopup="true"
        aria-expanded={isOpen}
      >
        {isAnyExporting ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Download className="w-4 h-4" />
        )}
        <span className="hidden sm:inline">
          {isAnyExporting ? 'Exporting...' : 'Export'}
        </span>
        {!isAnyExporting && (
          <ChevronDown
            className={
              'w-3 h-3 transition-transform ' + (isOpen ? 'rotate-180' : '')
            }
          />
        )}
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.95 }}
            transition={{ duration: 0.15, ease: 'easeOut' }}
            className={
              'absolute right-0 top-full mt-2 w-56 ' +
              'bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700/50 ' +
              'rounded-xl shadow-xl shadow-slate-900/10 dark:shadow-slate-950/40 ' +
              'overflow-hidden z-50'
            }
            role="menu"
          >
            <div className="px-3 py-2 border-b border-slate-100 dark:border-slate-800">
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                Export Format
              </p>
            </div>
            <div className="py-1">
              {EXPORT_OPTIONS.map((option) => (
                <button
                  key={option.format}
                  type="button"
                  onClick={() => handleExport(option)}
                  disabled={isAnyExporting}
                  className={
                    'w-full flex items-center gap-3 px-3 py-2.5 text-left text-sm ' +
                    'text-slate-700 dark:text-slate-200 ' +
                    'hover:bg-slate-50 dark:hover:bg-slate-800/80 ' +
                    'transition-colors disabled:opacity-50 disabled:cursor-not-allowed'
                  }
                  role="menuitem"
                >
                  <span className="flex items-center justify-center w-8 h-8 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                    {option.icon}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium">{option.label}</p>
                    <p className="text-xs text-slate-400 dark:text-slate-500 truncate">
                      {option.description}
                    </p>
                  </div>
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
