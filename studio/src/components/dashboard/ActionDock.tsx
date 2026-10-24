// বাংলা মন্তব্য: Bottom Action-Dock — dnd-kit দিয়ে ড্র্যাগেবল, শুধু user-enabled ইন্টিগ্রেশনগুলো রেন্ডার করে
// (hardcoded নয়, useWorkspaceSettingsStore থেকে ডাইনামিকভাবে আসে)
import { useState } from 'react';
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  horizontalListSortingStrategy,
  useSortable,
  arrayMove,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Code2,
  Mail,
  Globe,
  MessagesSquare,
  NotebookText,
  HardDrive,
  Settings2,
  Loader2,
  Check,
  X,
} from 'lucide-react';
import { useWorkspaceSettingsStore, type DockIntegration } from '../../store/useWorkspaceSettingsStore';
import { useDashboardActions } from '../../hooks/useDashboardActions';

// বাংলা মন্তব্য: icon name (string, store-এ persist হয়) থেকে আসল lucide কম্পোনেন্টে ম্যাপ করা হয়
const ICON_MAP: Record<string, React.ComponentType<{ size?: number }>> = {
  Github: Code2,
  Mail,
  Facebook: Globe,
  MessagesSquare,
  NotebookText,
  HardDrive,
};

type RunStatus = 'idle' | 'running' | 'success' | 'error';

function DockButton({
  integration,
  status,
  onRun,
}: {
  integration: DockIntegration;
  status: RunStatus;
  onRun: (id: string) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: integration.id,
  });
  const Icon = ICON_MAP[integration.icon] ?? Settings2;

  return (
    <motion.button
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      onClick={() => onRun(integration.id)}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
      }}
      whileHover={{ y: -4 }}
      whileTap={{ scale: 0.94 }}
      className={`relative flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border transition-colors ${
        isDragging
          ? 'opacity-50 border-[var(--supremeai-color-brand-500)]'
          : 'border-[var(--supremeai-color-border-accent-dark)] bg-[var(--supremeai-color-bg-elevated-dark)] hover:border-[var(--supremeai-color-brand-500)]/60'
      }`}
      title={integration.label}
      data-testid={`dock-item-${integration.id}`}
    >
      <Icon size={18} />

      {/* বাংলা মন্তব্য: এক্সিকিউশন চলাকালীন নিয়ন-পালস রিং */}
      {status === 'running' && (
        <motion.span
          className="absolute inset-0 rounded-2xl border-2 border-[var(--supremeai-color-brand-500)]"
          animate={{ opacity: [0.9, 0.15, 0.9], scale: [1, 1.12, 1] }}
          transition={{ duration: 1.1, repeat: Infinity, ease: 'easeInOut' }}
        />
      )}
      {status === 'running' && (
        <span className="absolute -top-1 -right-1">
          <Loader2 size={12} className="animate-spin text-[var(--supremeai-color-brand-500)]" />
        </span>
      )}
      {status === 'success' && (
        <span className="absolute -top-1 -right-1 rounded-full bg-emerald-500 p-0.5">
          <Check size={10} className="text-white" />
        </span>
      )}
      {status === 'error' && (
        <span className="absolute -top-1 -right-1 rounded-full bg-red-500 p-0.5">
          <X size={10} className="text-white" />
        </span>
      )}
    </motion.button>
  );
}

export function ActionDock() {
  const integrations = useWorkspaceSettingsStore((s) => s.integrations);
  const reorderIntegrations = useWorkspaceSettingsStore((s) => s.reorderIntegrations);
  const { runIntegrationAction } = useDashboardActions();
  const [statuses, setStatuses] = useState<Record<string, RunStatus>>({});
  const [configOpen, setConfigOpen] = useState(false);

  const enabled = integrations.filter((i) => i.enabled);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const ids = enabled.map((i) => i.id);
    const oldIndex = ids.indexOf(String(active.id));
    const newIndex = ids.indexOf(String(over.id));
    reorderIntegrations(arrayMove(ids, oldIndex, newIndex));
  };

  const handleRun = async (id: string) => {
    setStatuses((s) => ({ ...s, [id]: 'running' }));
    const result = await runIntegrationAction(id);
    setStatuses((s) => ({ ...s, [id]: result.ok ? 'success' : 'error' }));
    window.setTimeout(() => {
      setStatuses((s) => ({ ...s, [id]: 'idle' }));
    }, 1800);
  };

  return (
    <div
      data-testid="action-dock"
      className="relative z-10 flex items-center gap-3 border-t border-[var(--supremeai-color-border-accent-dark)] bg-[var(--supremeai-color-bg-elevated-dark)]/80 px-4 py-3 backdrop-blur-md"
    >
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={enabled.map((i) => i.id)} strategy={horizontalListSortingStrategy}>
          <div className="flex items-center gap-2 overflow-x-auto">
            <AnimatePresence initial={false}>
              {enabled.map((integration) => (
                <motion.div
                  key={integration.id}
                  layout
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.8 }}
                >
                  <DockButton
                    integration={integration}
                    status={statuses[integration.id] ?? 'idle'}
                    onRun={handleRun}
                  />
                </motion.div>
              ))}
            </AnimatePresence>
            {enabled.length === 0 && (
              <span className="text-xs text-[var(--supremeai-color-neutral-500)]">
                No integrations enabled — configure below.
              </span>
            )}
          </div>
        </SortableContext>
      </DndContext>

      <button
        onClick={() => setConfigOpen((v) => !v)}
        className="ml-auto flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-[var(--supremeai-color-neutral-500)] hover:text-foreground hover:bg-[var(--supremeai-color-neutral-900)] transition-colors"
        data-testid="dock-configure-toggle"
        title="Configure dock"
      >
        <Settings2 size={16} />
      </button>

      <AnimatePresence>
        {configOpen && <DockConfigPanel onClose={() => setConfigOpen(false)} />}
      </AnimatePresence>
    </div>
  );
}

function DockConfigPanel({ onClose }: { onClose: () => void }) {
  const integrations = useWorkspaceSettingsStore((s) => s.integrations);
  const toggleIntegration = useWorkspaceSettingsStore((s) => s.toggleIntegration);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 8 }}
      className="absolute bottom-16 right-4 w-64 rounded-xl border border-[var(--supremeai-color-border-accent-dark)] bg-[var(--supremeai-color-bg-elevated-dark)] p-3 shadow-xl"
      data-testid="dock-config-panel"
    >
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-[var(--supremeai-color-neutral-500)]">
          Dock integrations
        </span>
        <button onClick={onClose} className="text-[var(--supremeai-color-neutral-500)] hover:text-foreground">
          <X size={14} />
        </button>
      </div>
      <div className="space-y-1">
        {integrations.map((integration) => {
          const Icon = ICON_MAP[integration.icon] ?? Settings2;
          return (
            <label
              key={integration.id}
              className="flex items-center justify-between rounded-lg px-2 py-1.5 hover:bg-[var(--supremeai-color-neutral-900)] cursor-pointer"
            >
              <span className="flex items-center gap-2 text-sm">
                <Icon size={14} />
                {integration.label}
              </span>
              <input
                type="checkbox"
                checked={integration.enabled}
                onChange={() => toggleIntegration(integration.id)}
                className="accent-[var(--supremeai-color-brand-500)]"
              />
            </label>
          );
        })}
      </div>
    </motion.div>
  );
}
