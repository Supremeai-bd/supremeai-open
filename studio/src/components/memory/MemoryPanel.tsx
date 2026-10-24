import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Brain,
  Plus,
  Trash2,
  Search,
  RefreshCw,
  X,
  Loader2,
  Tag,
  Lightbulb,
  ClipboardList,
  Database,
  Sparkles,
} from 'lucide-react';
import { apiClient } from '../../services/apiClient';
import { globalShowToastRef } from '../../contexts/ToastContext';

// ─── Types ───────────────────────────────────────────────────────────────

type MemoryContentType = 'fact' | 'preference' | 'instruction';

interface Memory {
  id: string;
  content: string;
  content_type: MemoryContentType;
  created_at: string;
  updated_at: string;
}

interface MemorySearchResult {
  id: string;
  content: string;
  content_type: MemoryContentType;
  score: number;
  created_at: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────

function getTypeConfig(type: MemoryContentType) {
  switch (type) {
    case 'fact':
      return {
        label: 'Fact',
        icon: <ClipboardList className="w-3.5 h-3.5" />,
        bg: 'bg-sky-100 dark:bg-sky-500/10',
        text: 'text-sky-700 dark:text-sky-400',
        border: 'border-sky-200 dark:border-sky-500/25',
      };
    case 'preference':
      return {
        label: 'Preference',
        icon: <Lightbulb className="w-3.5 h-3.5" />,
        bg: 'bg-amber-100 dark:bg-amber-500/10',
        text: 'text-amber-700 dark:text-amber-400',
        border: 'border-amber-200 dark:border-amber-500/25',
      };
    case 'instruction':
      return {
        label: 'Instruction',
        icon: <Sparkles className="w-3.5 h-3.5" />,
        bg: 'bg-violet-100 dark:bg-violet-500/10',
        text: 'text-violet-700 dark:text-violet-400',
        border: 'border-violet-200 dark:border-violet-500/25',
      };
  }
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

// ─── Component ───────────────────────────────────────────────────────────

export default function MemoryPanel() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [searchResults, setSearchResults] = useState<MemorySearchResult[] | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSearching, setIsSearching] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isAdding, setIsAdding] = useState(false);
  const [isDeleting, setIsDeleting] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newContent, setNewContent] = useState('');
  const [newType, setNewType] = useState<MemoryContentType>('fact');
  const [activeFilter, setActiveFilter] = useState<MemoryContentType | 'all'>('all');

  const fetchMemories = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await apiClient.get<Memory[]>('/api/preferences/memory');
      setMemories(Array.isArray(response) ? response : []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load memories';
      globalShowToastRef.current('error', message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMemories();
  }, [fetchMemories]);

  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) {
      setSearchResults(null);
      return;
    }
    setIsSearching(true);
    try {
      const response = await apiClient.post<MemorySearchResult[]>(
        '/api/preferences/memory/search',
        { query: searchQuery }
      );
      setSearchResults(Array.isArray(response) ? response : []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Search failed';
      globalShowToastRef.current('error', message);
    } finally {
      setIsSearching(false);
    }
  }, [searchQuery]);

  const handleSync = useCallback(async () => {
    setIsSyncing(true);
    try {
      await apiClient.post('/api/preferences/memory/sync');
      globalShowToastRef.current('success', 'Memories synced from chats successfully!');
      await fetchMemories();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to sync memories';
      globalShowToastRef.current('error', message);
    } finally {
      setIsSyncing(false);
    }
  }, [fetchMemories]);

  const handleAddMemory = useCallback(async () => {
    if (!newContent.trim()) return;
    setIsAdding(true);
    try {
      await apiClient.post('/api/preferences/memory', {
        content: newContent.trim(),
        content_type: newType,
      });
      globalShowToastRef.current('success', 'Memory added successfully!');
      setNewContent('');
      setNewType('fact');
      setShowAddForm(false);
      await fetchMemories();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to add memory';
      globalShowToastRef.current('error', message);
    } finally {
      setIsAdding(false);
    }
  }, [newContent, newType, fetchMemories]);

  const handleDelete = useCallback(async (id: string) => {
    setIsDeleting(id);
    try {
      await apiClient.delete(`/api/preferences/memory/${id}`);
      globalShowToastRef.current('success', 'Memory deleted.');
      setMemories((prev) => prev.filter((m) => m.id !== id));
      if (searchResults) {
        setSearchResults((prev) => (prev ? prev.filter((m) => m.id !== id) : null));
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to delete memory';
      globalShowToastRef.current('error', message);
    } finally {
      setIsDeleting(null);
    }
  }, [searchResults]);

  // Filter logic
  const filteredMemories = activeFilter === 'all'
    ? memories
    : memories.filter((m) => m.content_type === activeFilter);

  const displayMemories = searchResults !== null ? searchResults as unknown as Memory[] : filteredMemories;

  // Stats
  const totalCount = memories.length;
  const factCount = memories.filter((m) => m.content_type === 'fact').length;
  const prefCount = memories.filter((m) => m.content_type === 'preference').length;
  const instrCount = memories.filter((m) => m.content_type === 'instruction').length;

  return (
    <div className="flex flex-col h-full bg-white dark:bg-slate-950">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-slate-200 dark:border-slate-800 px-6 py-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
              <Brain className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-slate-900 dark:text-white">
                User Memories
              </h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Global memories that persist across all conversations
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleSync}
              disabled={isSyncing}
              className={
                'flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-xl transition-all ' +
                'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 ' +
                'disabled:opacity-50 disabled:cursor-not-allowed'
              }
              aria-label="Sync memories from chats"
            >
              <RefreshCw className={'w-4 h-4 ' + (isSyncing ? 'animate-spin' : '')} />
              <span className="hidden sm:inline">Sync from Chats</span>
            </button>
            <button
              type="button"
              onClick={() => setShowAddForm(!showAddForm)}
              className={
                'flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-xl transition-all ' +
                'text-white bg-emerald-600 hover:bg-emerald-500 shadow-lg shadow-emerald-500/20'
              }
            >
              {showAddForm ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
              <span className="hidden sm:inline">{showAddForm ? 'Cancel' : 'Add Memory'}</span>
            </button>
          </div>
        </div>

        {/* Search Bar */}
        <div className="flex items-center gap-2">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search memories semantically..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              className={
                'w-full pl-10 pr-10 py-2.5 text-sm rounded-xl border transition-colors ' +
                'bg-slate-50 dark:bg-slate-900 border-slate-200 dark:border-slate-700 ' +
                'text-slate-900 dark:text-white placeholder:text-slate-400 ' +
                'focus:outline-none focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-500'
              }
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => { setSearchQuery(''); setSearchResults(null); }}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                aria-label="Clear search"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
          <button
            type="button"
            onClick={handleSearch}
            disabled={isSearching || !searchQuery.trim()}
            className={
              'flex items-center justify-center px-4 py-2.5 text-sm font-medium rounded-xl transition-all ' +
              'bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 hover:bg-slate-800 dark:hover:bg-slate-200 ' +
              'disabled:opacity-50 disabled:cursor-not-allowed'
            }
          >
            {isSearching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Add Memory Form */}
      <AnimatePresence>
        {showAddForm && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="flex-shrink-0 overflow-hidden border-b border-slate-200 dark:border-slate-800"
          >
            <div className="px-6 py-4 space-y-3 bg-slate-50 dark:bg-slate-900/50">
              <textarea
                placeholder="Enter a memory (e.g., 'User prefers TypeScript over JavaScript', 'Always format code with Prettier')..."
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
                rows={3}
                className={
                  'w-full px-4 py-3 text-sm rounded-xl border transition-colors resize-none ' +
                  'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 ' +
                  'text-slate-900 dark:text-white placeholder:text-slate-400 ' +
                  'focus:outline-none focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-500'
                }
              />
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-slate-500 dark:text-slate-400">Type:</span>
                  {(['fact', 'preference', 'instruction'] as MemoryContentType[]).map((type) => {
                    const cfg = getTypeConfig(type);
                    return (
                      <button
                        key={type}
                        type="button"
                        onClick={() => setNewType(type)}
                        className={
                          'inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition-all ' +
                          (newType === type
                            ? cfg.bg + ' ' + cfg.text + ' ' + cfg.border + ' border'
                            : 'border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-600')
                        }
                      >
                        {cfg.icon}
                        {cfg.label}
                      </button>
                    );
                  })}
                </div>
                <button
                  type="button"
                  onClick={handleAddMemory}
                  disabled={isAdding || !newContent.trim()}
                  className={
                    'flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-xl transition-all ' +
                    'text-white bg-emerald-600 hover:bg-emerald-500 shadow-lg shadow-emerald-500/20 ' +
                    'disabled:opacity-50 disabled:cursor-not-allowed'
                  }
                >
                  {isAdding ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                  Save Memory
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Filter Tabs */}
      <div className="flex-shrink-0 px-6 py-3 border-b border-slate-100 dark:border-slate-800">
        <div className="flex items-center gap-1">
          {([
            { key: 'all' as const, label: 'All' },
            { key: 'fact' as const, label: 'Facts' },
            { key: 'preference' as const, label: 'Preferences' },
            { key: 'instruction' as const, label: 'Instructions' },
          ]).map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => { setActiveFilter(tab.key); setSearchResults(null); }}
              className={
                'px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ' +
                (activeFilter === tab.key
                  ? 'bg-slate-900 dark:bg-white text-white dark:text-slate-900'
                  : 'text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-700 dark:hover:text-slate-200')
              }
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Memory List */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
          </div>
        ) : displayMemories.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
            <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-slate-100 dark:bg-slate-800 mb-4">
              <Brain className="w-7 h-7 text-slate-400" />
            </div>
            <p className="text-sm font-medium text-slate-700 dark:text-slate-200 mb-1">
              {searchResults !== null ? 'No matching memories found' : 'No memories yet'}
            </p>
            <p className="text-xs text-slate-400 dark:text-slate-500 max-w-xs">
              {searchResults !== null
                ? 'Try a different search query'
                : 'Add memories to help the AI remember your preferences and context across conversations'}
            </p>
          </div>
        ) : (
          <div className="px-6 py-4 space-y-3 max-h-96 overflow-y-auto">
            <AnimatePresence>
              {displayMemories.map((memory) => {
                const cfg = getTypeConfig(memory.content_type);
                return (
                  <motion.div
                    key={memory.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.15 }}
                    className={
                      'group relative p-4 rounded-xl border transition-colors ' +
                      'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700/50 ' +
                      'hover:border-slate-300 dark:hover:border-slate-600'
                    }
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-2">
                          <span
                            className={
                              'inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-md border ' +
                              cfg.bg + ' ' + cfg.text + ' ' + cfg.border
                            }
                          >
                            {cfg.icon}
                            {cfg.label}
                          </span>
                          <span className="text-xs text-slate-400 dark:text-slate-500">
                            {formatDate(memory.created_at)}
                          </span>
                        </div>
                        <p className="text-sm text-slate-700 dark:text-slate-200 leading-relaxed">
                          {memory.content}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleDelete(memory.id)}
                        disabled={isDeleting === memory.id}
                        className={
                          'flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-lg transition-all ' +
                          'text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 ' +
                          'opacity-0 group-hover:opacity-100 disabled:opacity-50 disabled:cursor-not-allowed'
                        }
                        aria-label="Delete memory"
                      >
                        {isDeleting === memory.id ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <Trash2 className="w-4 h-4" />
                        )}
                      </button>
                    </div>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          </div>
        )}
      </div>

      {/* Stats Bar */}
      <div className="flex-shrink-0 border-t border-slate-200 dark:border-slate-800 px-6 py-3 bg-slate-50 dark:bg-slate-900/50">
        <div className="flex items-center gap-4 text-xs text-slate-500 dark:text-slate-400">
          <div className="flex items-center gap-1.5">
            <Database className="w-3.5 h-3.5" />
            <span className="font-medium text-slate-700 dark:text-slate-200">{totalCount}</span> total
          </div>
          <div className="flex items-center gap-1.5">
            <Tag className="w-3.5 h-3.5 text-sky-500" />
            <span>{factCount} facts</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Tag className="w-3.5 h-3.5 text-amber-500" />
            <span>{prefCount} prefs</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Tag className="w-3.5 h-3.5 text-violet-500" />
            <span>{instrCount} instr.</span>
          </div>
        </div>
      </div>
    </div>
  );
}
