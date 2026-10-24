import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Clock,
  Plus,
  X,
  Loader2,
  Play,
  Trash2,
  Pencil,
  ToggleLeft,
  ToggleRight,
  ChevronDown,
  ChevronRight,
  Calendar,
  Repeat,
  Zap,
  AlertCircle,
  CheckCircle2,
  Timer,
} from 'lucide-react';
import { apiClient } from '../../services/apiClient';
import { globalShowToastRef } from '../../contexts/ToastContext';

// ─── Types ───────────────────────────────────────────────────────────────

type ScheduleType = 'once' | 'daily' | 'weekly' | 'custom';
type ExecutionStatus = 'success' | 'failed' | 'running';

interface ScheduledTask {
  id: string;
  title: string;
  prompt: string;
  schedule_type: ScheduleType;
  cron_expression?: string;
  next_run_at: string | null;
  is_active: boolean;
  created_at: string;
}

interface ExecutionHistory {
  id: string;
  task_id: string;
  status: ExecutionStatus;
  executed_at: string;
  result?: string;
  error?: string;
}

interface TaskFormData {
  title: string;
  prompt: string;
  schedule_type: ScheduleType;
  datetime?: string;
  cron_expression?: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────

function getScheduleConfig(type: ScheduleType) {
  switch (type) {
    case 'once':
      return {
        label: 'Once',
        icon: <Zap className="w-3.5 h-3.5" />,
        bg: 'bg-amber-100 dark:bg-amber-500/10',
        text: 'text-amber-700 dark:text-amber-400',
        border: 'border-amber-200 dark:border-amber-500/25',
      };
    case 'daily':
      return {
        label: 'Daily',
        icon: <Repeat className="w-3.5 h-3.5" />,
        bg: 'bg-emerald-100 dark:bg-emerald-500/10',
        text: 'text-emerald-700 dark:text-emerald-400',
        border: 'border-emerald-200 dark:border-emerald-500/25',
      };
    case 'weekly':
      return {
        label: 'Weekly',
        icon: <Calendar className="w-3.5 h-3.5" />,
        bg: 'bg-violet-100 dark:bg-violet-500/10',
        text: 'text-violet-700 dark:text-violet-400',
        border: 'border-violet-200 dark:border-violet-500/25',
      };
    case 'custom':
      return {
        label: 'Custom',
        icon: <Timer className="w-3.5 h-3.5" />,
        bg: 'bg-sky-100 dark:bg-sky-500/10',
        text: 'text-sky-700 dark:text-sky-400',
        border: 'border-sky-200 dark:border-sky-500/25',
      };
  }
}

function getStatusConfig(status: ExecutionStatus) {
  switch (status) {
    case 'success':
      return {
        label: 'Success',
        icon: <CheckCircle2 className="w-3.5 h-3.5" />,
        bg: 'bg-emerald-100 dark:bg-emerald-500/10',
        text: 'text-emerald-700 dark:text-emerald-400',
      };
    case 'failed':
      return {
        label: 'Failed',
        icon: <AlertCircle className="w-3.5 h-3.5" />,
        bg: 'bg-red-100 dark:bg-red-500/10',
        text: 'text-red-700 dark:text-red-400',
      };
    case 'running':
      return {
        label: 'Running',
        icon: <Loader2 className="w-3.5 h-3.5 animate-spin" />,
        bg: 'bg-amber-100 dark:bg-amber-500/10',
        text: 'text-amber-700 dark:text-amber-400',
      };
  }
}

function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return 'Not scheduled';
  const date = new Date(dateStr);
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

const emptyForm: TaskFormData = {
  title: '',
  prompt: '',
  schedule_type: 'once',
  datetime: '',
  cron_expression: '',
};

// ─── Component ───────────────────────────────────────────────────────────

export default function ScheduledTasksPanel() {
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [formData, setFormData] = useState<TaskFormData>(emptyForm);
  const [isSaving, setIsSaving] = useState(false);
  const [isRunning, setIsRunning] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState<string | null>(null);
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null);
  const [historyMap, setHistoryMap] = useState<Record<string, ExecutionHistory[]>>({});
  const [isLoadingHistory, setIsLoadingHistory] = useState<string | null>(null);

  const fetchTasks = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await apiClient.get<ScheduledTask[]>('/api/schedule');
      setTasks(Array.isArray(response) ? response : []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load scheduled tasks';
      globalShowToastRef.current('error', message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  const fetchHistory = useCallback(async (taskId: string) => {
    if (historyMap[taskId]) {
      setExpandedTaskId(expandedTaskId === taskId ? null : taskId);
      return;
    }
    setIsLoadingHistory(taskId);
    try {
      const response = await apiClient.get<ExecutionHistory[]>(`/api/schedule/history?task_id=${taskId}`);
      setHistoryMap((prev) => ({ ...prev, [taskId]: Array.isArray(response) ? response : [] }));
      setExpandedTaskId(taskId);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load history';
      globalShowToastRef.current('error', message);
    } finally {
      setIsLoadingHistory(null);
    }
  }, [historyMap, expandedTaskId]);

  const handleSave = useCallback(async () => {
    if (!formData.title.trim() || !formData.prompt.trim()) {
      globalShowToastRef.current('error', 'Title and prompt are required.');
      return;
    }
    if (formData.schedule_type === 'custom' && !formData.cron_expression?.trim()) {
      globalShowToastRef.current('error', 'Cron expression is required for custom schedule.');
      return;
    }
    if (formData.schedule_type === 'once' && !formData.datetime) {
      globalShowToastRef.current('error', 'Please select a date and time.');
      return;
    }

    setIsSaving(true);
    try {
      if (editingTaskId) {
        await apiClient.put(`/api/schedule/${editingTaskId}`, formData);
        globalShowToastRef.current('success', 'Task updated successfully!');
      } else {
        await apiClient.post('/api/schedule', formData);
        globalShowToastRef.current('success', 'Task created successfully!');
      }
      setFormData(emptyForm);
      setShowCreateForm(false);
      setEditingTaskId(null);
      await fetchTasks();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to save task';
      globalShowToastRef.current('error', message);
    } finally {
      setIsSaving(false);
    }
  }, [formData, editingTaskId, fetchTasks]);

  const handleDelete = useCallback(async (taskId: string) => {
    setIsDeleting(taskId);
    try {
      await apiClient.delete(`/api/schedule/${taskId}`);
      globalShowToastRef.current('success', 'Task deleted.');
      setTasks((prev) => prev.filter((t) => t.id !== taskId));
      setHistoryMap((prev) => {
        const next = { ...prev };
        delete next[taskId];
        return next;
      });
      if (expandedTaskId === taskId) setExpandedTaskId(null);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to delete task';
      globalShowToastRef.current('error', message);
    } finally {
      setIsDeleting(null);
    }
  }, [expandedTaskId]);

  const handleToggle = useCallback(async (taskId: string, currentState: boolean) => {
    try {
      await apiClient.put(`/api/schedule/${taskId}`, { is_active: !currentState });
      setTasks((prev) =>
        prev.map((t) => (t.id === taskId ? { ...t, is_active: !currentState } : t))
      );
      globalShowToastRef.current('success', `Task ${!currentState ? 'activated' : 'deactivated'}.`);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to toggle task';
      globalShowToastRef.current('error', message);
    }
  }, []);

  const handleRunNow = useCallback(async (taskId: string) => {
    setIsRunning(taskId);
    try {
      await apiClient.post(`/api/schedule/${taskId}/run`);
      globalShowToastRef.current('success', 'Task execution started!');
      // Refresh history if expanded
      if (expandedTaskId === taskId) {
        setHistoryMap((prev) => {
          const next = { ...prev };
          delete next[taskId];
          return next;
        });
        fetchHistory(taskId);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to run task';
      globalShowToastRef.current('error', message);
    } finally {
      setIsRunning(null);
    }
  }, [expandedTaskId, fetchHistory]);

  const handleEdit = useCallback((task: ScheduledTask) => {
    setFormData({
      title: task.title,
      prompt: task.prompt,
      schedule_type: task.schedule_type,
      cron_expression: task.cron_expression || '',
      datetime: '',
    });
    setEditingTaskId(task.id);
    setShowCreateForm(true);
  }, []);

  const handleCancelForm = useCallback(() => {
    setFormData(emptyForm);
    setEditingTaskId(null);
    setShowCreateForm(false);
  }, []);

  return (
    <div className="flex flex-col h-full bg-white dark:bg-slate-950">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-slate-200 dark:border-slate-800 px-6 py-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-amber-100 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400">
              <Clock className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-slate-900 dark:text-white">
                Scheduled Tasks
              </h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Automate recurring chat tasks with schedules
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => { setShowCreateForm(!showCreateForm); setEditingTaskId(null); setFormData(emptyForm); }}
            className={
              'flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-xl transition-all ' +
              'text-white bg-amber-600 hover:bg-amber-500 shadow-lg shadow-amber-500/20'
            }
          >
            {showCreateForm ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
            <span className="hidden sm:inline">{showCreateForm ? 'Cancel' : 'New Task'}</span>
          </button>
        </div>

        {/* Create/Edit Form */}
        <AnimatePresence>
          {showCreateForm && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden"
            >
              <div className="space-y-4 p-4 rounded-xl bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700">
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Title</label>
                  <input
                    type="text"
                    value={formData.title}
                    onChange={(e) => setFormData((p) => ({ ...p, title: e.target.value }))}
                    placeholder="Task title"
                    className={
                      'w-full px-3 py-2.5 text-sm rounded-xl border transition-colors ' +
                      'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 ' +
                      'text-slate-900 dark:text-white placeholder:text-slate-400 ' +
                      'focus:outline-none focus:ring-2 focus:ring-amber-500/40 focus:border-amber-500'
                    }
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Prompt</label>
                  <textarea
                    value={formData.prompt}
                    onChange={(e) => setFormData((p) => ({ ...p, prompt: e.target.value }))}
                    placeholder="The prompt to send when this task runs..."
                    rows={3}
                    className={
                      'w-full px-3 py-2.5 text-sm rounded-xl border transition-colors resize-none ' +
                      'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 ' +
                      'text-slate-900 dark:text-white placeholder:text-slate-400 ' +
                      'focus:outline-none focus:ring-2 focus:ring-amber-500/40 focus:border-amber-500'
                    }
                  />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Schedule Type</label>
                    <div className="flex flex-wrap gap-2">
                      {(['once', 'daily', 'weekly', 'custom'] as ScheduleType[]).map((type) => {
                        const cfg = getScheduleConfig(type);
                        return (
                          <button
                            key={type}
                            type="button"
                            onClick={() => setFormData((p) => ({ ...p, schedule_type: type }))}
                            className={
                              'inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition-all ' +
                              (formData.schedule_type === type
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
                  </div>
                  <div>
                    {formData.schedule_type === 'once' && (
                      <div>
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Date & Time</label>
                        <input
                          type="datetime-local"
                          value={formData.datetime || ''}
                          onChange={(e) => setFormData((p) => ({ ...p, datetime: e.target.value }))}
                          className={
                            'w-full px-3 py-2.5 text-sm rounded-xl border transition-colors ' +
                            'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 ' +
                            'text-slate-900 dark:text-white ' +
                            'focus:outline-none focus:ring-2 focus:ring-amber-500/40 focus:border-amber-500'
                          }
                        />
                      </div>
                    )}
                    {formData.schedule_type === 'custom' && (
                      <div>
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Cron Expression</label>
                        <input
                          type="text"
                          value={formData.cron_expression || ''}
                          onChange={(e) => setFormData((p) => ({ ...p, cron_expression: e.target.value }))}
                          placeholder="e.g., 0 9 * * 1-5 (weekdays 9am)"
                          className={
                            'w-full px-3 py-2.5 text-sm rounded-xl border transition-colors font-mono ' +
                            'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 ' +
                            'text-slate-900 dark:text-white placeholder:text-slate-400 ' +
                            'focus:outline-none focus:ring-2 focus:ring-amber-500/40 focus:border-amber-500'
                          }
                        />
                      </div>
                    )}
                  </div>
                </div>
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={handleCancelForm}
                    className="px-4 py-2 text-sm font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleSave}
                    disabled={isSaving}
                    className={
                      'flex items-center gap-2 px-5 py-2 text-sm font-medium rounded-xl transition-all ' +
                      'text-white bg-amber-600 hover:bg-amber-500 shadow-lg shadow-amber-500/20 ' +
                      'disabled:opacity-50 disabled:cursor-not-allowed'
                    }
                  >
                    {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                    {editingTaskId ? 'Update Task' : 'Create Task'}
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Task List */}
      <div className="flex-1 overflow-y-auto p-6">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
          </div>
        ) : tasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-slate-100 dark:bg-slate-800 mb-4">
              <Clock className="w-7 h-7 text-slate-400" />
            </div>
            <p className="text-sm font-medium text-slate-700 dark:text-slate-200 mb-1">No scheduled tasks</p>
            <p className="text-xs text-slate-400 dark:text-slate-500 max-w-xs">
              Create your first scheduled task to automate recurring prompts
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            <AnimatePresence>
              {tasks.map((task) => {
                const scheduleCfg = getScheduleConfig(task.schedule_type);
                const isExpanded = expandedTaskId === task.id;
                const history = historyMap[task.id] || [];

                return (
                  <motion.div
                    key={task.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.15 }}
                    className={
                      'rounded-xl border transition-colors ' +
                      'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700/50 '
                      + (!task.is_active ? 'opacity-60' : '')
                    }
                  >
                    {/* Task Row */}
                    <div className="px-4 py-3 flex items-center gap-3">
                      {/* Expand toggle */}
                      <button
                        type="button"
                        onClick={() => fetchHistory(task.id)}
                        className="flex-shrink-0 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
                        aria-label="Toggle history"
                      >
                        {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                      </button>

                      {/* Active toggle */}
                      <button
                        type="button"
                        onClick={() => handleToggle(task.id, task.is_active)}
                        className="flex-shrink-0 transition-colors"
                        aria-label={`Toggle ${task.is_active ? 'off' : 'on'}`}
                      >
                        {task.is_active ? (
                          <ToggleRight className="w-6 h-6 text-emerald-500" />
                        ) : (
                          <ToggleLeft className="w-6 h-6 text-slate-400" />
                        )}
                      </button>

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <p className={
                            'text-sm font-semibold truncate ' +
                            (task.is_active ? 'text-slate-900 dark:text-white' : 'text-slate-500 dark:text-slate-400')
                          }>
                            {task.title}
                          </p>
                          <span className={
                            'inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-md border flex-shrink-0 ' +
                            scheduleCfg.bg + ' ' + scheduleCfg.text + ' ' + scheduleCfg.border
                          }>
                            {scheduleCfg.icon}
                            {scheduleCfg.label}
                          </span>
                        </div>
                        <p className="text-xs text-slate-400 dark:text-slate-500 truncate">
                          {task.prompt.substring(0, 80)}{task.prompt.length > 80 ? '...' : ''}
                        </p>
                      </div>

                      {/* Next run */}
                      <div className="hidden sm:block flex-shrink-0 text-right">
                        <p className="text-xs text-slate-400 dark:text-slate-500">Next run</p>
                        <p className="text-xs font-medium text-slate-600 dark:text-slate-300">
                          {formatDateTime(task.next_run_at)}
                        </p>
                      </div>

                      {/* Actions */}
                      <div className="flex items-center gap-1 flex-shrink-0">
                        <button
                          type="button"
                          onClick={() => handleRunNow(task.id)}
                          disabled={isRunning === task.id}
                          className="p-1.5 text-slate-400 hover:text-emerald-500 rounded-lg hover:bg-emerald-50 dark:hover:bg-emerald-500/10 transition-colors disabled:opacity-50"
                          aria-label="Run now"
                          title="Run now"
                        >
                          {isRunning === task.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleEdit(task)}
                          className="p-1.5 text-slate-400 hover:text-amber-500 rounded-lg hover:bg-amber-50 dark:hover:bg-amber-500/10 transition-colors"
                          aria-label="Edit task"
                          title="Edit"
                        >
                          <Pencil className="w-4 h-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(task.id)}
                          disabled={isDeleting === task.id}
                          className="p-1.5 text-slate-400 hover:text-red-500 rounded-lg hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors disabled:opacity-50"
                          aria-label="Delete task"
                          title="Delete"
                        >
                          {isDeleting === task.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                        </button>
                      </div>
                    </div>

                    {/* Expandable History */}
                    <AnimatePresence>
                      {isExpanded && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.15 }}
                          className="overflow-hidden border-t border-slate-100 dark:border-slate-800"
                        >
                          <div className="px-4 py-3 bg-slate-50 dark:bg-slate-900/50">
                            {isLoadingHistory === task.id ? (
                              <div className="flex items-center justify-center py-4">
                                <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
                              </div>
                            ) : history.length === 0 ? (
                              <p className="text-xs text-slate-400 dark:text-slate-500 text-center py-4">
                                No execution history yet
                              </p>
                            ) : (
                              <div className="space-y-2 max-h-48 overflow-y-auto">
                                {history.map((entry) => {
                                  const statusCfg = getStatusConfig(entry.status);
                                  return (
                                    <div
                                      key={entry.id}
                                      className="flex items-center gap-3 px-3 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                                    >
                                      <span className={
                                        'inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-md ' +
                                        statusCfg.bg + ' ' + statusCfg.text
                                      }>
                                        {statusCfg.icon}
                                        {statusCfg.label}
                                      </span>
                                      <span className="flex-1 text-xs text-slate-500 dark:text-slate-400 truncate">
                                        {entry.result || entry.error || 'No output'}
                                      </span>
                                      <span className="text-xs text-slate-400 dark:text-slate-500 flex-shrink-0">
                                        {formatDateTime(entry.executed_at)}
                                      </span>
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          </div>
        )}
      </div>
    </div>
  );
}
