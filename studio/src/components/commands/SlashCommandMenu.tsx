import { useState, useEffect, useRef } from 'react';
import {
  Search,
  BookOpen,
  PenLine,
  Code2,
  Wrench,
  Zap,
  Globe,
  FileText,
  Image,
  Table,
  ListChecks,
  Calculator,
  RefreshCw,
  Languages,
  Sparkles,
  FileCode,
  Bug,
  Lightbulb,
} from 'lucide-react';
import { apiClient } from '../../services/apiClient';

// ─── Types ───────────────────────────────────────────────────────────────

type CommandCategory = 'Research' | 'Content' | 'Code' | 'Utility';

interface SlashCommand {
  id: string;
  name: string;
  description: string;
  category: CommandCategory;
  icon: string;
  shortcut?: string;
}

interface SlashCommandMenuProps {
  isOpen: boolean;
  position: { top: number; left: number };
  onSelect: (command: string) => void;
  onClose: () => void;
  filter?: string;
}

// ─── Icon Mapper ─────────────────────────────────────────────────────────

const ICON_MAP: Record<string, typeof Search> = {
  search: Search,
  'book-open': BookOpen,
  'pen-line': PenLine,
  code: Code2,
  wrench: Wrench,
  zap: Zap,
  globe: Globe,
  'file-text': FileText,
  image: Image,
  table: Table,
  'list-checks': ListChecks,
  calculator: Calculator,
  'refresh-cw': RefreshCw,
  translate: Languages,
  sparkles: Sparkles,
  'file-code': FileCode,
  bug: Bug,
  lightbulb: Lightbulb,
};

// ─── Default commands (used if API fails) ────────────────────────────────

const DEFAULT_COMMANDS: SlashCommand[] = [
  // Research
  { id: 'search-web', name: 'search', description: 'Search the web for information', category: 'Research', icon: 'search', shortcut: '/search' },
  { id: 'deep-research', name: 'research', description: 'Deep research on a topic', category: 'Research', icon: 'book-open', shortcut: '/research' },
  { id: 'translate', name: 'translate', description: 'Translate text between languages', category: 'Research', icon: 'translate', shortcut: '/translate' },

  // Content
  { id: 'write-blog', name: 'blog', description: 'Generate a blog post', category: 'Content', icon: 'pen-line', shortcut: '/blog' },
  { id: 'write-email', name: 'email', description: 'Draft an email', category: 'Content', icon: 'file-text', shortcut: '/email' },
  { id: 'generate-image', name: 'image', description: 'Generate an image from description', category: 'Content', icon: 'image', shortcut: '/image' },
  { id: 'summarize', name: 'summarize', description: 'Summarize a long text', category: 'Content', icon: 'file-text', shortcut: '/summarize' },

  // Code
  { id: 'generate-code', name: 'code', description: 'Generate code from description', category: 'Code', icon: 'code', shortcut: '/code' },
  { id: 'debug', name: 'debug', description: 'Debug and fix code issues', category: 'Code', icon: 'bug', shortcut: '/debug' },
  { id: 'review-code', name: 'review', description: 'Review code for improvements', category: 'Code', icon: 'file-code', shortcut: '/review' },
  { id: 'explain-code', name: 'explain', description: 'Explain code step by step', category: 'Code', icon: 'lightbulb', shortcut: '/explain' },

  // Utility
  { id: 'calculate', name: 'calc', description: 'Perform calculations', category: 'Utility', icon: 'calculator', shortcut: '/calc' },
  { id: 'todo', name: 'todo', description: 'Create a to-do list', category: 'Utility', icon: 'list-checks', shortcut: '/todo' },
  { id: 'table', name: 'table', description: 'Create a data table', category: 'Utility', icon: 'table', shortcut: '/table' },
  { id: 'refine', name: 'refine', description: 'Refine and improve previous response', category: 'Utility', icon: 'refresh-cw', shortcut: '/refine' },
];

// ─── Category display config ─────────────────────────────────────────────

const CATEGORY_CONFIG: { category: CommandCategory; label: string; color: string }[] = [
  { category: 'Research', label: 'Research', color: 'text-sky-600 dark:text-sky-400' },
  { category: 'Content', label: 'Content', color: 'text-emerald-600 dark:text-emerald-400' },
  { category: 'Code', label: 'Code', color: 'text-violet-600 dark:text-violet-400' },
  { category: 'Utility', label: 'Utility', color: 'text-amber-600 dark:text-amber-400' },
];

// ─── Helpers ─────────────────────────────────────────────────────────────

function filterCommands(commands: SlashCommand[], filter: string): SlashCommand[] {
  if (!filter) return commands;
  const lowerFilter = filter.toLowerCase();
  return commands.filter(
    (cmd) =>
      cmd.name.toLowerCase().includes(lowerFilter) ||
      cmd.description.toLowerCase().includes(lowerFilter)
  );
}

function groupByCategory(commands: SlashCommand[]): Map<CommandCategory, SlashCommand[]> {
  const grouped = new Map<CommandCategory, SlashCommand[]>();
  for (const cmd of commands) {
    const existing = grouped.get(cmd.category) || [];
    existing.push(cmd);
    grouped.set(cmd.category, existing);
  }
  return grouped;
}

// ─── Component ───────────────────────────────────────────────────────────

export function SlashCommandMenu({
  isOpen,
  position,
  onSelect,
  onClose,
  filter = '',
}: SlashCommandMenuProps) {
  const [commands, setCommands] = useState<SlashCommand[]>(DEFAULT_COMMANDS);
  const [isLoading, setIsLoading] = useState(true);
  const [activeIndex, setActiveIndex] = useState(0);
  const menuRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<Map<number, HTMLButtonElement>>(new Map());

  // Fetch commands on mount
  useEffect(() => {
    let cancelled = false;

    async function fetchCommands() {
      try {
        const response = await apiClient.get<SlashCommand[]>('/api/commands/');
        if (!cancelled && Array.isArray(response) && response.length > 0) {
          setCommands(response);
        }
      } catch {
        // Silently fall back to defaults
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    fetchCommands();
    return () => {
      cancelled = true;
    };
  }, []);

  // Filter and group commands
  const filtered = filterCommands(commands, filter);
  const grouped = groupByCategory(filtered);

  // Build flat list for keyboard navigation
  const flatCommands = CATEGORY_CONFIG.filter((c) => grouped.has(c.category)).flatMap(
    (cat) => grouped.get(cat.category) || []
  );

  // Reset active index when filter changes
  useEffect(() => {
    setActiveIndex(0);
  }, [filter]);

  // Scroll active item into view
  useEffect(() => {
    const el = itemRefs.current.get(activeIndex);
    if (el) {
      el.scrollIntoView({ block: 'nearest' });
    }
  }, [activeIndex]);

  // Attach keyboard listener to parent
  useEffect(() => {
    if (!isOpen) return;

    const handler = (e: KeyboardEvent) => {
      if (!['ArrowDown', 'ArrowUp', 'Enter', 'Escape'].includes(e.key)) return;

      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setActiveIndex((prev) =>
            prev < flatCommands.length - 1 ? prev + 1 : 0
          );
          break;
        case 'ArrowUp':
          e.preventDefault();
          setActiveIndex((prev) =>
            prev > 0 ? prev - 1 : flatCommands.length - 1
          );
          break;
        case 'Enter': {
          e.preventDefault();
          const cmd = flatCommands[activeIndex];
          if (cmd) {
            onSelect(cmd.name);
          }
          break;
        }
        case 'Escape':
          e.preventDefault();
          onClose();
          break;
      }
    };

    document.addEventListener('keydown', handler, true);
    return () => document.removeEventListener('keydown', handler, true);
  }, [isOpen, flatCommands, activeIndex, onSelect, onClose]);

  // Close on click outside
  useEffect(() => {
    if (!isOpen) return;

    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };

    // Use capture phase to close before other handlers
    document.addEventListener('mousedown', handler, true);
    return () => document.removeEventListener('mousedown', handler, true);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  let globalIndex = -1;

  return (
    <div
      ref={menuRef}
      role="listbox"
      aria-label="Slash commands"
      className="fixed z-[90] w-80 max-h-80 overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700/50 bg-white dark:bg-slate-900 shadow-xl shadow-black/10 dark:shadow-black/30 flex flex-col"
      style={{ top: position.top, left: position.left }}
    >
 {/* Search header */}
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-slate-200 dark:border-slate-700/50 bg-slate-50 dark:bg-slate-800/50">
        <Search className="w-4 h-4 text-slate-400 dark:text-slate-500 flex-shrink-0" />
        <span className="text-sm text-slate-500 dark:text-slate-400 truncate">
          {filter ? `Matching "${filter}"` : 'Type to filter commands...'}
        </span>
        {flatCommands.length > 0 && (
          <span className="ml-auto text-xs text-slate-400 dark:text-slate-500">
            {flatCommands.length} {flatCommands.length === 1 ? 'result' : 'results'}
          </span>
        )}
      </div>

      {/* Command list */}
      <div className="overflow-y-auto flex-1 py-1 custom-scrollbar">
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <div className="w-5 h-5 border-2 border-violet-500/30 border-t-violet-500 rounded-full animate-spin" />
          </div>
        ) : flatCommands.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-8 px-4">
            <Sparkles className="w-8 h-8 text-slate-300 dark:text-slate-600" />
            <p className="text-sm text-slate-400 dark:text-slate-500 text-center">
              No commands match &ldquo;{filter}&rdquo;
            </p>
          </div>
        ) : (
          CATEGORY_CONFIG.map((catConfig) => {
            const catCommands = grouped.get(catConfig.category);
            if (!catCommands || catCommands.length === 0) return null;

            return (
              <div key={catConfig.category}>
                {/* Category header */}
                <div className="px-3 pt-2 pb-1">
                  <span className={`text-[10px] font-semibold uppercase tracking-wider ${catConfig.color}`}>
                    {catConfig.label}
                  </span>
                </div>

                {/* Category items */}
                {catCommands.map((cmd) => {
                  globalIndex++;
                  const currentIndex = globalIndex;
                  const isActive = currentIndex === activeIndex;
                  const IconComponent = ICON_MAP[cmd.icon] || Zap;

                  return (
                    <button
                      key={cmd.id}
                      ref={(el) => {
                        if (el) {
                          itemRefs.current.set(currentIndex, el);
                        }
                      }}
                      type="button"
                      role="option"
                      aria-selected={isActive}
                      onClick={() => onSelect(cmd.name)}
                      className={`w-full flex items-center gap-3 px-3 py-2 text-left transition-colors ${
                          isActive
                            ? 'bg-violet-50 dark:bg-violet-500/10'
                            : 'hover:bg-slate-50 dark:hover:bg-slate-800/50'
                        }`}
                    >
                      <div
                        className={`flex items-center justify-center w-7 h-7 rounded-lg flex-shrink-0 ${
                            isActive
                              ? 'bg-violet-200 dark:bg-violet-500/20 text-violet-600 dark:text-violet-400'
                              : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400'
                          }`}
                      >
                        <IconComponent className="w-3.5 h-3.5" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p
                          className={`text-sm font-medium truncate ${
                              isActive
                                ? 'text-violet-700 dark:text-violet-300'
                                : 'text-slate-700 dark:text-slate-300'
                            }`}
                        >
                          /{cmd.name}
                        </p>
                        <p className="text-xs text-slate-400 dark:text-slate-500 truncate">
                          {cmd.description}
                        </p>
                      </div>
                      {cmd.shortcut && (
                        <kbd className="hidden sm:inline-flex items-center px-1.5 py-0.5 text-[10px] font-mono text-slate-400 dark:text-slate-500 bg-slate-100 dark:bg-slate-800 rounded">
                          {cmd.shortcut}
                        </kbd>
                      )}
                    </button>
                  );
                })}
              </div>
            );
          })
        )}
      </div>

      {/* Footer hint */}
      <div className="flex items-center justify-between px-3 py-2 border-t border-slate-200 dark:border-slate-700/50 bg-slate-50 dark:bg-slate-800/30">
        <div className="flex items-center gap-3 text-[10px] text-slate-400 dark:text-slate-500">
          <span className="flex items-center gap-1">
            <kbd className="px-1 py-0.5 bg-slate-200 dark:bg-slate-700 rounded text-[9px] font-mono">↑↓</kbd>
            navigate
          </span>
          <span className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 bg-slate-200 dark:bg-slate-700 rounded text-[9px] font-mono">↵</kbd>
            select
          </span>
          <span className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 bg-slate-200 dark:bg-slate-700 rounded text-[9px] font-mono">esc</kbd>
            close
          </span>
        </div>
      </div>
    </div>
  );
}
