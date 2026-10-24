import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search,
  Plus,
  X,
  Loader2,
  Eye,
  Code2,
  FileText,
  FlaskConical,
  LayoutGrid,
  BookmarkPlus,
  Trash2,
  Send,
  Variable,
  ChevronRight,
  Star,
  Sparkles,
} from 'lucide-react';
import { apiClient } from '../../services/apiClient';
import { globalShowToastRef } from '../../contexts/ToastContext';

// ─── Types ───────────────────────────────────────────────────────────────

type TemplateCategory = 'code' | 'content' | 'research' | 'general';

interface PromptTemplate {
  id: string;
  name: string;
  description: string;
  category: TemplateCategory;
  prompt: string;
  variables: string[];
  usage_count: number;
  is_builtin: boolean;
  created_at: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────

function getCategoryConfig(category: TemplateCategory) {
  switch (category) {
    case 'code':
      return {
        label: 'Code',
        icon: <Code2 className="w-3.5 h-3.5" />,
        bg: 'bg-emerald-100 dark:bg-emerald-500/10',
        text: 'text-emerald-700 dark:text-emerald-400',
        border: 'border-emerald-200 dark:border-emerald-500/25',
      };
    case 'content':
      return {
        label: 'Content',
        icon: <FileText className="w-3.5 h-3.5" />,
        bg: 'bg-amber-100 dark:bg-amber-500/10',
        text: 'text-amber-700 dark:text-amber-400',
        border: 'border-amber-200 dark:border-amber-500/25',
      };
    case 'research':
      return {
        label: 'Research',
        icon: <FlaskConical className="w-3.5 h-3.5" />,
        bg: 'bg-violet-100 dark:bg-violet-500/10',
        text: 'text-violet-700 dark:text-violet-400',
        border: 'border-violet-200 dark:border-violet-500/25',
      };
    case 'general':
      return {
        label: 'General',
        icon: <LayoutGrid className="w-3.5 h-3.5" />,
        bg: 'bg-slate-100 dark:bg-slate-500/10',
        text: 'text-slate-700 dark:text-slate-400',
        border: 'border-slate-200 dark:border-slate-500/25',
      };
  }
}

function extractVariablesFromPrompt(prompt: string): string[] {
  const matches = prompt.match(/\{\{([^}]+)\}\}/g);
  if (!matches) return [];
  return [...new Set(matches.map((m) => m.replace(/[{}]/g, '').trim()))];
}

// ─── Component ───────────────────────────────────────────────────────────

export default function PromptTemplateLibrary() {
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [filteredTemplates, setFilteredTemplates] = useState<PromptTemplate[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState<TemplateCategory | 'all'>('all');
  const [selectedTemplate, setSelectedTemplate] = useState<PromptTemplate | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [variableValues, setVariableValues] = useState<Record<string, string>>({});
  const [isCreating, setIsCreating] = useState(false);
  const [isDeleting, setIsDeleting] = useState<string | null>(null);

  // Create form state
  const [createForm, setCreateForm] = useState({
    name: '',
    description: '',
    category: 'general' as TemplateCategory,
    prompt: '',
    variables: [''],
  });

  const fetchTemplates = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await apiClient.get<PromptTemplate[]>('/api/prompt-templates');
      const list = Array.isArray(response) ? response : [];
      setTemplates(list);
      setFilteredTemplates(list);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load templates';
      globalShowToastRef.current('error', message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  // Filter logic
  useEffect(() => {
    let result = templates;
    if (activeCategory !== 'all') {
      result = result.filter((t) => t.category === activeCategory);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (t) => t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q)
      );
    }
    setFilteredTemplates(result);
  }, [templates, activeCategory, searchQuery]);

  const handleOpenDetail = useCallback((template: PromptTemplate) => {
    setSelectedTemplate(template);
    const vars = template.variables || extractVariablesFromPrompt(template.prompt);
 const initial: Record<string, string> = {};
 vars.forEach((v) => { initial[v] = ''; });
 setVariableValues(initial);
 }, []);

  const handleUseTemplate = useCallback(() => {
    if (!selectedTemplate) return;
    let filledPrompt = selectedTemplate.prompt;
    Object.entries(variableValues).forEach(([key, value]) => {
      if (value.trim()) {
        filledPrompt = filledPrompt.replace(new RegExp(`\\{\\{${key}\\}\\}`, 'g'), value);
      }
    });
    window.dispatchEvent(
      new CustomEvent('supremeai:insert-prompt', { detail: { prompt: filledPrompt } })
    );
    globalShowToastRef.current('success', 'Template inserted into chat input!');
    setSelectedTemplate(null);
  }, [selectedTemplate, variableValues]);

  const handleAddVariable = useCallback(() => {
    setCreateForm((prev) => ({ ...prev, variables: [...prev.variables, ''] }));
  }, []);

  const handleRemoveVariable = useCallback((index: number) => {
    setCreateForm((prev) => ({
      ...prev,
      variables: prev.variables.filter((_, i) => i !== index),
    }));
  }, []);

  const handleVariableChange = useCallback((index: number, value: string) => {
    setCreateForm((prev) => {
      const updated = [...prev.variables];
      updated[index] = value;
      return { ...prev, variables: updated };
    });
  }, []);

  const handleCreate = useCallback(async () => {
    if (!createForm.name.trim() || !createForm.prompt.trim()) {
      globalShowToastRef.current('error', 'Name and prompt are required.');
      return;
    }
    setIsCreating(true);
    try {
      const detectedVars = extractVariablesFromPrompt(createForm.prompt);
      const manualVars = createForm.variables.filter((v) => v.trim());
      const allVars = [...new Set([...detectedVars, ...manualVars])];
      await apiClient.post('/api/prompt-templates', {
        ...createForm,
        variables: allVars,
      });
      globalShowToastRef.current('success', 'Template created successfully!');
      setCreateForm({ name: '', description: '', category: 'general', prompt: '', variables: [''] });
      setShowCreateForm(false);
      await fetchTemplates();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to create template';
      globalShowToastRef.current('error', message);
    } finally {
      setIsCreating(false);
    }
  }, [createForm, fetchTemplates]);

  const handleDelete = useCallback(async (id: string) => {
    setIsDeleting(id);
    try {
      await apiClient.delete(`/api/prompt-templates/${id}`);
      globalShowToastRef.current('success', 'Template deleted.');
      if (selectedTemplate?.id === id) setSelectedTemplate(null);
      await fetchTemplates();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to delete template';
      globalShowToastRef.current('error', message);
    } finally {
      setIsDeleting(null);
    }
  }, [selectedTemplate, fetchTemplates]);

  const categoryTabs = [
    { key: 'all' as const, label: 'All' },
    { key: 'code' as const, label: 'Code' },
    { key: 'content' as const, label: 'Content' },
    { key: 'research' as const, label: 'Research' },
    { key: 'general' as const, label: 'General' },
  ];

  const templateVariables = selectedTemplate
    ? (selectedTemplate.variables.length > 0
        ? selectedTemplate.variables
        : extractVariablesFromPrompt(selectedTemplate.prompt))
    : [];

  return (
    <div className="flex flex-col h-full bg-white dark:bg-slate-950">
      {/* Header + Search + Filter */}
      <div className="flex-shrink-0 border-b border-slate-200 dark:border-slate-800 px-6 py-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-violet-100 dark:bg-violet-500/10 text-violet-600 dark:text-violet-400">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-slate-900 dark:text-white">
                Prompt Templates
              </h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Reusable prompt templates to boost your productivity
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setShowCreateForm(!showCreateForm)}
            className={
              'flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-xl transition-all ' +
              'text-white bg-violet-600 hover:bg-violet-500 shadow-lg shadow-violet-500/20'
            }
          >
            {showCreateForm ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
            <span className="hidden sm:inline">{showCreateForm ? 'Cancel' : 'Create Template'}</span>
          </button>
        </div>

        {/* Search */}
        <div className="relative mb-4">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search templates by name or description..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className={
              'w-full pl-10 pr-4 py-2.5 text-sm rounded-xl border transition-colors ' +
              'bg-slate-50 dark:bg-slate-900 border-slate-200 dark:border-slate-700 ' +
              'text-slate-900 dark:text-white placeholder:text-slate-400 ' +
              'focus:outline-none focus:ring-2 focus:ring-violet-500/40 focus:border-violet-500'
            }
          />
        </div>

        {/* Category Tabs */}
        <div className="flex items-center gap-1">
          {categoryTabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveCategory(tab.key)}
              className={
                'px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ' +
                (activeCategory === tab.key
                  ? 'bg-slate-900 dark:bg-white text-white dark:text-slate-900'
                  : 'text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-700 dark:hover:text-slate-200')
              }
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Create Form */}
      <AnimatePresence>
        {showCreateForm && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="flex-shrink-0 overflow-hidden border-b border-slate-200 dark:border-slate-800"
          >
            <div className="px-6 py-5 space-y-4 bg-slate-50 dark:bg-slate-900/50">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Name</label>
                  <input
                    type="text"
                    value={createForm.name}
                    onChange={(e) => setCreateForm((p) => ({ ...p, name: e.target.value }))}
                    placeholder="Template name"
                    className={
                      'w-full px-3 py-2.5 text-sm rounded-xl border transition-colors ' +
                      'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 ' +
                      'text-slate-900 dark:text-white placeholder:text-slate-400 ' +
                      'focus:outline-none focus:ring-2 focus:ring-violet-500/40 focus:border-violet-500'
                    }
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Category</label>
                  <select
                    value={createForm.category}
                    onChange={(e) => setCreateForm((p) => ({ ...p, category: e.target.value as TemplateCategory }))}
                    className={
                      'w-full px-3 py-2.5 text-sm rounded-xl border transition-colors ' +
                      'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 ' +
                      'text-slate-900 dark:text-white ' +
                      'focus:outline-none focus:ring-2 focus:ring-violet-500/40 focus:border-violet-500'
                    }
                  >
                    <option value="general">General</option>
                    <option value="code">Code</option>
                    <option value="content">Content</option>
                    <option value="research">Research</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Description</label>
                <input
                  type="text"
                  value={createForm.description}
                  onChange={(e) => setCreateForm((p) => ({ ...p, description: e.target.value }))}
                  placeholder="Brief description of what this template does"
                  className={
                    'w-full px-3 py-2.5 text-sm rounded-xl border transition-colors ' +
                    'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 ' +
                    'text-slate-900 dark:text-white placeholder:text-slate-400 ' +
                    'focus:outline-none focus:ring-2 focus:ring-violet-500/40 focus:border-violet-500'
                  }
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Prompt</label>
                <textarea
                  value={createForm.prompt}
                  onChange={(e) => setCreateForm((p) => ({ ...p, prompt: e.target.value }))}
                  placeholder="Write your prompt template. Use {{variable_name}} for dynamic variables."
                  rows={5}
                  className={
                    'w-full px-3 py-2.5 text-sm rounded-xl border transition-colors resize-none ' +
                    'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 ' +
                    'text-slate-900 dark:text-white placeholder:text-slate-400 font-mono ' +
                    'focus:outline-none focus:ring-2 focus:ring-violet-500/40 focus:border-violet-500'
                  }
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Variables</label>
                <div className="space-y-2">
                  {createForm.variables.map((v, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <Variable className="w-4 h-4 text-slate-400 flex-shrink-0" />
                      <input
                        type="text"
                        value={v}
                        onChange={(e) => handleVariableChange(i, e.target.value)}
                        placeholder="Variable name"
                        className={
                          'flex-1 px-3 py-2 text-sm rounded-lg border transition-colors ' +
                          'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 ' +
                          'text-slate-900 dark:text-white placeholder:text-slate-400 ' +
                          'focus:outline-none focus:ring-2 focus:ring-violet-500/40 focus:border-violet-500'
                        }
                      />
                      {createForm.variables.length > 1 && (
                        <button
                          type="button"
                          onClick={() => handleRemoveVariable(i)}
                          className="p-1.5 text-slate-400 hover:text-red-500 rounded-lg hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                          aria-label="Remove variable"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={handleAddVariable}
                    className={
                      'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ' +
                      'text-violet-600 dark:text-violet-400 hover:bg-violet-50 dark:hover:bg-violet-500/10'
                    }
                  >
                    <Plus className="w-3.5 h-3.5" />
                    Add Variable
                  </button>
                </div>
              </div>
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={handleCreate}
                  disabled={isCreating || !createForm.name.trim() || !createForm.prompt.trim()}
                  className={
                    'flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-xl transition-all ' +
                    'text-white bg-violet-600 hover:bg-violet-500 shadow-lg shadow-violet-500/20 ' +
                    'disabled:opacity-50 disabled:cursor-not-allowed'
                  }
                >
                  {isCreating ? <Loader2 className="w-4 h-4 animate-spin" /> : <BookmarkPlus className="w-4 h-4" />}
                  Create Template
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Template Grid */}
      <div className="flex-1 overflow-y-auto p-6">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
          </div>
        ) : filteredTemplates.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-slate-100 dark:bg-slate-800 mb-4">
              <Sparkles className="w-7 h-7 text-slate-400" />
            </div>
            <p className="text-sm font-medium text-slate-700 dark:text-slate-200 mb-1">No templates found</p>
            <p className="text-xs text-slate-400 dark:text-slate-500 max-w-xs">
              {searchQuery ? 'Try a different search query or category' : 'Create your first prompt template to get started'}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <AnimatePresence>
              {filteredTemplates.map((template) => {
                const catCfg = getCategoryConfig(template.category);
                return (
                  <motion.div
                    key={template.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.15 }}
                    onClick={() => handleOpenDetail(template)}
                    className={
                      'group relative p-4 rounded-xl border cursor-pointer transition-all ' +
                      'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700/50 ' +
                      'hover:border-violet-300 dark:hover:border-violet-500/50 hover:shadow-md hover:shadow-violet-500/5'
                    }
                  >
                    <div className="flex items-start justify-between gap-2 mb-3">
                      <span
                        className={
                          'inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-md border ' +
                          catCfg.bg + ' ' + catCfg.text + ' ' + catCfg.border
                        }
                      >
                        {catCfg.icon}
                        {catCfg.label}
                      </span>
                      <span
                        className={
                          'inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-md ' +
                          (template.is_builtin
                            ? 'bg-sky-50 dark:bg-sky-500/10 text-sky-600 dark:text-sky-400'
                            : 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400')
                        }
                      >
                        {template.is_builtin ? (
                          <Star className="w-3 h-3" />
                        ) : (
                          <BookmarkPlus className="w-3 h-3" />
                        )}
                        {template.is_builtin ? 'Built-in' : 'Custom'}
                      </span>
                    </div>
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-1 group-hover:text-violet-600 dark:group-hover:text-violet-400 transition-colors">
                      {template.name}
                    </h3>
                    <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-2 mb-3 leading-relaxed">
                      {template.description || 'No description provided'}
                    </p>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-slate-400 dark:text-slate-500">
                        Used {template.usage_count} times
                      </span>
                      <ChevronRight className="w-4 h-4 text-slate-400 group-hover:text-violet-500 transition-colors" />
                    </div>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          </div>
        )}
      </div>

      {/* Detail Modal */}
      <AnimatePresence>
        {selectedTemplate && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
            onClick={() => setSelectedTemplate(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 16 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 16 }}
              transition={{ type: 'spring', damping: 25, stiffness: 300 }}
              className="w-full max-w-2xl max-h-[80vh] overflow-hidden bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700/50 rounded-2xl shadow-2xl flex flex-col"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Modal Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-700/50">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-violet-100 dark:bg-violet-500/10 text-violet-600 dark:text-violet-400 flex-shrink-0">
                    <Eye className="w-5 h-5" />
                  </div>
                  <div className="min-w-0">
                    <h2 className="text-lg font-semibold text-slate-900 dark:text-white truncate">
                      {selectedTemplate.name}
                    </h2>
                    <p className="text-sm text-slate-500 dark:text-slate-400 truncate">
                      {selectedTemplate.description}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {!selectedTemplate.is_builtin && (
                    <button
                      type="button"
                      onClick={() => handleDelete(selectedTemplate.id)}
                      disabled={isDeleting === selectedTemplate.id}
                      className="p-2 text-slate-400 hover:text-red-500 rounded-lg hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors disabled:opacity-50"
                      aria-label="Delete template"
                    >
                      {isDeleting === selectedTemplate.id ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Trash2 className="w-4 h-4" />
                      )}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => setSelectedTemplate(null)}
                    className="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                    aria-label="Close"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>
              </div>

              {/* Modal Body */}
              <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
                {/* Prompt Text */}
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">Prompt</label>
                  <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                    <pre className="text-sm text-slate-700 dark:text-slate-200 whitespace-pre-wrap font-mono leading-relaxed">
                      {selectedTemplate.prompt}
                    </pre>
                  </div>
                </div>

                {/* Variables */}
                {templateVariables.length > 0 && (
                  <div>
                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                      Fill Variables
                    </label>
                    <div className="space-y-3">
                      {templateVariables.map((variable) => (
                        <div key={variable}>
                          <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">
                            {`{{${variable}}}`}
                          </label>
                          <input
                            type="text"
                            value={variableValues[variable] || ''}
                            onChange={(e) =>
                              setVariableValues((prev) => ({ ...prev, [variable]: e.target.value }))
                            }
                            placeholder={`Enter value for ${variable}`}
                            className={
                              'w-full px-3 py-2 text-sm rounded-lg border transition-colors ' +
                              'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 ' +
                              'text-slate-900 dark:text-white placeholder:text-slate-400 ' +
                              'focus:outline-none focus:ring-2 focus:ring-violet-500/40 focus:border-violet-500'
                            }
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Modal Footer */}
              <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-200 dark:border-slate-700/50 bg-slate-50 dark:bg-slate-800/50">
                <button
                  type="button"
                  onClick={() => setSelectedTemplate(null)}
                  className="px-4 py-2.5 text-sm font-medium text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl transition-colors"
                >
                  Close
                </button>
                <button
                  type="button"
                  onClick={handleUseTemplate}
                  className={
                    'flex items-center gap-2 px-5 py-2.5 text-sm font-medium text-white rounded-xl transition-all ' +
                    'bg-violet-600 hover:bg-violet-500 shadow-lg shadow-violet-500/20'
                  }
                >
                  <Send className="w-4 h-4" />
                  Use Template
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
