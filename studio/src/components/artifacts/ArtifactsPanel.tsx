import { useState, useCallback, useRef } from 'react';
import {
  X,
  FileCode,
  Atom,
  ImageIcon,
  GitBranch,
  Code,
  Copy,
  Download,
  Pin,
  Plus,
  ChevronLeft,
} from 'lucide-react';
import { globalShowToastRef } from '../../contexts/ToastContext';

// ─── Types ───────────────────────────────────────────────────────────────

export type ArtifactType = 'html' | 'react' | 'svg' | 'mermaid' | 'code';

interface Artifact {
  id: string;
  title: string;
  artifact_type: ArtifactType;
  content: string;
  version: number;
}

interface ArtifactsPanelProps {
  artifacts: Artifact[];
  activeArtifactId?: string;
  onSelect: (artifact: Artifact) => void;
  onClose: () => void;
  onNew: () => void;
}

// ─── Icon Mapper ─────────────────────────────────────────────────────────

const TYPE_ICON_MAP: Record<ArtifactType, typeof FileCode> = {
  html: FileCode,
  react: Atom,
  svg: ImageIcon,
  mermaid: GitBranch,
  code: Code,
};

const TYPE_LABEL_MAP: Record<ArtifactType, string> = {
  html: 'HTML',
  react: 'React',
  svg: 'SVG',
  mermaid: 'Mermaid',
  code: 'Code',
};

// ─── Syntax Highlighting (Simple CSS) ───────────────────────────────────

const CODE_KEYWORDS = new Set([
  'function', 'const', 'let', 'var', 'return', 'if', 'else', 'for', 'while',
  'class', 'import', 'export', 'from', 'default', 'async', 'await', 'try',
  'catch', 'throw', 'new', 'this', 'typeof', 'interface', 'type', 'enum',
  'extends', 'implements', 'switch', 'case', 'break', 'continue', 'null',
  'undefined', 'true', 'false', 'void', 'static', 'private', 'public',
  'protected', 'readonly', 'abstract', 'final', 'super', 'yield', 'of', 'in',
]);

// SECURITY FIX (audit V-3): HTML-escape the raw code FIRST so that any
// <script>, <img onerror=...> or similar tags embedded in code strings are
// rendered as literal text rather than executed HTML.
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;');
}

function highlightSyntax(code: string): string {
  // Escape first — the regex replacements below insert trusted HTML span tags,
  // but all user-controlled content must already be neutralised.
  const lines = escapeHtml(code).split('\n');
  return lines
    .map((line) => {
      const highlighted = line
        // String literals (double and single quotes) — content is already escaped.
        .replace(
          /(&quot;[^&]*&quot;|&#x27;[^&]*&#x27;|`[^`]*`)/g,
          '<span class="text-emerald-600 dark:text-emerald-400">$1</span>'
        )
        // Comments
        .replace(
          /(\/\/.*$)/gm,
          '<span class="text-slate-400 italic">$1</span>'
        )
        // Numbers
        .replace(
          /\b(\d+(?:\.\d+)?)\b/g,
          '<span class="text-amber-600 dark:text-amber-400">$1</span>'
        )
        // Keywords
        .replace(
          /\b([a-zA-Z_][a-zA-Z0-9_]*)\b/g,
          (match) => {
            if (CODE_KEYWORDS.has(match)) {
              return `<span class="text-violet-600 dark:text-violet-400 font-semibold">${match}</span>`;
            }
            return match;
          }
        );
      return highlighted;
    })
    .join('\n');
}

// SECURITY FIX (audit S-3): Robust SVG sanitizer — strips script, foreignObject elements
// and dangerous event-handler attributes (on*) and javascript: / vbscript: URI values.
function sanitizeSvg(svgContent: string): string {
  // Remove <script> and <foreignObject> blocks entirely.
  let safe = svgContent.replace(/<script[\s\S]*?<\/script>/gi, '');
  safe = safe.replace(/<foreignObject[\s\S]*?<\/foreignObject>/gi, '');
  // Strip event-handler attributes (onclick, onerror, onload, …).
  safe = safe.replace(/\s+on\w+\s*=\s*("[^"]*"|'[^']*'|\S+)/gi, '');
  // Strip javascript: and vbscript: href/xlink:href values.
  safe = safe.replace(/(href|xlink:href)\s*=\s*["']\s*(?:javascript|vbscript|data):[^"']*["']/gi, '');
  return safe;
}

// ─── Sub-components ──────────────────────────────────────────────────────

function ArtifactListItem({
  artifact,
  isActive,
  onClick,
}: {
  artifact: Artifact;
  isActive: boolean;
  onClick: () => void;
}) {
  const Icon = TYPE_ICON_MAP[artifact.artifact_type];

  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all group ${
        isActive
          ? 'bg-violet-100 dark:bg-violet-500/10 border border-violet-200 dark:border-violet-500/25'
          : 'hover:bg-slate-100 dark:hover:bg-slate-800 border border-transparent'
      }`}
    >
      <div
        className={`flex items-center justify-center w-8 h-8 rounded-lg flex-shrink-0 ${
          isActive
            ? 'bg-violet-200 dark:bg-violet-500/20 text-violet-600 dark:text-violet-400'
            : 'bg-slate-200 dark:bg-slate-700 text-slate-500 dark:text-slate-400 group-hover:text-slate-700 dark:group-hover:text-slate-300'
        }`}
      >
        <Icon className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <p
          className={`text-sm font-medium truncate ${
            isActive
              ? 'text-violet-700 dark:text-violet-300'
              : 'text-slate-700 dark:text-slate-300'
          }`}
        >
          {artifact.title}
        </p>
        <p className="text-xs text-slate-400 dark:text-slate-500">
          {TYPE_LABEL_MAP[artifact.artifact_type]}
        </p>
      </div>
      <span
        className={`text-[10px] font-mono font-medium px-1.5 py-0.5 rounded ${
          isActive
            ? 'bg-violet-200 dark:bg-violet-500/20 text-violet-600 dark:text-violet-400'
            : 'bg-slate-100 dark:bg-slate-800 text-slate-400 dark:text-slate-500'
        }`}
      >
        v{artifact.version}
      </span>
    </button>
  );
}

function ArtifactPreview({ artifact }: { artifact: Artifact }) {
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(artifact.content);
      globalShowToastRef.current('success', 'Content copied to clipboard!');
    } catch {
      globalShowToastRef.current('error', 'Failed to copy content');
    }
  }, [artifact.content]);

  const handleDownload = useCallback(() => {
    let ext = 'txt';
    if (artifact.artifact_type === 'html' || artifact.artifact_type === 'react') ext = 'html';
    else if (artifact.artifact_type === 'svg') ext = 'svg';
    else if (artifact.artifact_type === 'mermaid') ext = 'mmd';
    else if (artifact.artifact_type === 'code') ext = 'js';

    const blob = new Blob([artifact.content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${artifact.title}.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
    globalShowToastRef.current('success', 'File downloaded!');
  }, [artifact]);

  const renderContent = () => {
    switch (artifact.artifact_type) {
      case 'html':
      case 'react':
        return (
          <iframe
            ref={iframeRef}
            srcDoc={artifact.content}
            title={artifact.title}
            sandbox="allow-scripts"
            className="w-full h-full border-0 bg-white rounded-lg"
          />
        );

      case 'svg':
        return (
          <div
            className="w-full h-full flex items-center justify-center p-4 bg-white dark:bg-slate-800 rounded-lg overflow-auto"
            // SECURITY FIX (audit S-3): SVG content is sanitized before render.
            dangerouslySetInnerHTML={{ __html: sanitizeSvg(artifact.content) }}
          />
        );

      case 'mermaid':
        return (
          <div className="w-full h-full flex flex-col items-center justify-center gap-3 p-6 bg-slate-50 dark:bg-slate-800/50 rounded-lg border border-dashed border-slate-300 dark:border-slate-600">
            <GitBranch className="w-10 h-10 text-slate-300 dark:text-slate-600" />
            <p className="text-sm font-medium text-slate-500 dark:text-slate-400">
              Mermaid Diagram
            </p>
            <p className="text-xs text-slate-400 dark:text-slate-500 text-center max-w-xs">
              Diagram rendering requires the Mermaid library. The code is shown below.
            </p>
          </div>
        );

      case 'code':
      default:
        return (
          <pre className="w-full h-full overflow-auto p-4 bg-slate-50 dark:bg-slate-800/50 rounded-lg text-sm font-mono leading-relaxed custom-scrollbar">
            <code
              dangerouslySetInnerHTML={{
                __html: highlightSyntax(artifact.content),
              }}
            />
          </pre>
        );
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Title bar with actions */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-200 dark:border-slate-700/50 bg-slate-50 dark:bg-slate-800/30">
        <div className="flex items-center gap-2 min-w-0">
          {(() => {
            const Icon = TYPE_ICON_MAP[artifact.artifact_type];
            return <Icon className="w-4 h-4 text-slate-400 dark:text-slate-500 flex-shrink-0" />;
          })()}
          <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200 truncate">
            {artifact.title}
          </h3>
          <span className="text-[10px] font-mono text-slate-400 dark:text-slate-500 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700">
            v{artifact.version}
          </span>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            type="button"
            onClick={handleCopy}
            className="p-1.5 rounded-md text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
            aria-label="Copy content"
            title="Copy content"
          >
            <Copy className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={handleDownload}
            className="p-1.5 rounded-md text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
            aria-label="Download"
            title="Download"
          >
            <Download className="w-4 h-4" />
          </button>
          <button
            type="button"
            className="p-1.5 rounded-md text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
            aria-label="Pin artifact"
            title="Pin artifact"
          >
            <Pin className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Content area */}
      <div className="flex-1 min-h-0 overflow-hidden p-3">
        {renderContent()}
      </div>

      {/* Show mermaid source code below the placeholder */}
      {artifact.artifact_type === 'mermaid' && (
        <pre className="mx-3 mb-3 px-4 py-3 bg-slate-50 dark:bg-slate-800/50 rounded-lg text-xs font-mono text-slate-600 dark:text-slate-400 overflow-auto max-h-48 custom-scrollbar border border-slate-200 dark:border-slate-700/50">
          <code>{artifact.content}</code>
        </pre>
      )}
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────

export function ArtifactsPanel({
  artifacts,
  activeArtifactId,
  onSelect,
  onClose,
  onNew,
}: ArtifactsPanelProps) {
  const activeArtifact = artifacts.find((a) => a.id === activeArtifactId);

  // Mobile: show list or detail, Desktop: side-by-side
  const [mobileView, setMobileView] = useState<'list' | 'detail'>(
    activeArtifact ? 'detail' : 'list'
  );

  const handleSelect = useCallback(
    (artifact: Artifact) => {
      onSelect(artifact);
      setMobileView('detail');
    },
    [onSelect]
  );

  const handleBack = useCallback(() => {
    setMobileView('list');
  }, []);

  return (
    <div className="flex h-full bg-white dark:bg-slate-900 border-l border-slate-200 dark:border-slate-700/50">
      {/* Sidebar List */}
      <div
        className={`w-full sm:w-64 flex-shrink-0 flex flex-col border-r border-slate-200 dark:border-slate-700/50 ${
          mobileView === 'detail' ? 'hidden sm:flex' : 'flex'
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-slate-700/50">
          <h2 className="text-sm font-semibold text-slate-800 dark:text-white">
            Artifacts
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="hidden sm:flex items-center justify-center w-7 h-7 rounded-md text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            aria-label="Close artifacts panel"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Artifact List */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1 custom-scrollbar">
          {artifacts.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-2 px-4">
              <FileCode className="w-8 h-8 text-slate-300 dark:text-slate-600" />
              <p className="text-sm text-slate-400 dark:text-slate-500 text-center">
                No artifacts yet
              </p>
            </div>
          ) : (
            artifacts.map((artifact) => (
              <ArtifactListItem
                key={artifact.id}
                artifact={artifact}
                isActive={artifact.id === activeArtifactId}
                onClick={() => handleSelect(artifact)}
              />
            ))
          )}
        </div>

        {/* New Artifact Button */}
        <div className="p-2 border-t border-slate-200 dark:border-slate-700/50">
          <button
            type="button"
            onClick={onNew}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium text-violet-600 dark:text-violet-400 hover:bg-violet-50 dark:hover:bg-violet-500/10 rounded-lg transition-colors"
          >
            <Plus className="w-4 h-4" />
            New Artifact
          </button>
        </div>
      </div>

      {/* Detail / Preview Panel */}
      <div
        className={`flex-1 min-w-0 flex flex-col ${
          mobileView === 'list' ? 'hidden sm:flex' : 'flex'
        }`}
      >
        {activeArtifact ? (
          <>
            {/* Mobile back button */}
            <div className="sm:hidden flex items-center gap-2 px-3 py-2 border-b border-slate-200 dark:border-slate-700/50">
              <button
                type="button"
                onClick={handleBack}
                className="p-1 rounded-md text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                aria-label="Back to list"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              <button
                type="button"
                onClick={onClose}
                className="ml-auto p-1 rounded-md text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                aria-label="Close artifacts panel"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <ArtifactPreview artifact={activeArtifact} />
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center p-6">
            <div className="text-center">
              <FileCode className="w-12 h-12 text-slate-200 dark:text-slate-700 mx-auto mb-3" />
              <p className="text-sm text-slate-400 dark:text-slate-500">
                Select an artifact to preview
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
