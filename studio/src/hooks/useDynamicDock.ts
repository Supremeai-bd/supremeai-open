// বাংলা মন্তব্য: Action-Dock-এর ড্র্যাগ-ড্রপ থেকে real /api/v1/agent/action কলে যাওয়ার বিজনেস লজিক — payload, loading, error সব এখানে
import { useCallback, useRef, useState } from 'react';
import type { DragEndEvent } from '@dnd-kit/core';
import { apiClient, ApiError } from '../services/apiClient';
import { useToast } from '../contexts/useToast';

export type DockNodeStatus = 'idle' | 'pending' | 'success' | 'error';

export interface DockActionResult {
  status: DockNodeStatus;
  message: string;
}

interface UseDynamicDockOptions {
  // বাংলা মন্তব্য: ড্র্যাগ করা আইটেমের id থেকে প্রকৃত content/context রিজলভ করে (ফাইল, চ্যাট মেসেজ ইত্যাদি)
  resolveContent: (draggedId: string) => { content: string; context?: Record<string, unknown> };
  // বাংলা মন্তব্য: backend DAG-তে এখনো wire না হওয়া প্ল্যাটফর্মগুলো ব্লক করার জন্য (যেমন 'github')
  unsupportedPlatforms?: string[];
}

const AUTO_RESET_MS = 4000;

export function useDynamicDock({ resolveContent, unsupportedPlatforms = [] }: UseDynamicDockOptions) {
  const { showToast } = useToast();
  const [nodeStatus, setNodeStatus] = useState<Record<string, DockActionResult>>({});
  const [pendingAction, setPendingAction] = useState<{ platform: string; content: string; context: Record<string, unknown> } | null>(null);
  const resetTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const setStatus = useCallback((platform: string, status: DockNodeStatus, message: string) => {
    setNodeStatus((prev) => ({ ...prev, [platform]: { status, message } }));
    if (resetTimers.current[platform]) clearTimeout(resetTimers.current[platform]);
    if (status === 'success' || status === 'error') {
      resetTimers.current[platform] = setTimeout(() => {
        setNodeStatus((prev) => ({ ...prev, [platform]: { status: 'idle', message: '' } }));
      }, AUTO_RESET_MS);
    }
  }, []);

  // বাংলা মন্তব্য: এটাই আসল E2E API কল — /api/v1/agent/action, apiClient দিয়ে (auth header, retry, failover — সব বিল্ট-ইন)
  const executeAction = useCallback(
    async (platform: string, content: string, context: Record<string, unknown> = {}) => {
      if (unsupportedPlatforms.includes(platform)) {
        setStatus(platform, 'error', `${platform} এখনো orchestrator DAG-এ wire করা হয়নি`);
        showToast('error', `${platform} integration চালু নেই — backend DAG সাপোর্ট নেই।`);
        return;
      }

      setStatus(platform, 'pending', `Syncing to ${platform}...`);
      try {
        const result = await apiClient.post<{ status: string; result?: Record<string, unknown> }>(
          '/api/v1/agent/action',
          {
            target_platform: platform,
            content,
            context,
          }
        );
        setStatus(platform, 'success', 'Synced successfully');
        showToast('success', `${platform}-এ সফলভাবে sync হয়েছে।`);
        return result;
      } catch (err) {
        // বাংলা মন্তব্য: 400 মানে সাধারণত Integration token পাওয়া যায়নি — ইউজারকে Settings/Vault-এ পাঠানো দরকার
        const message = err instanceof ApiError ? err.message : 'Unknown error occurred';
        setStatus(platform, 'error', message);
        showToast('error', `${platform} sync failed: ${message}`);
        throw err;
      }
    },
    [setStatus, showToast, unsupportedPlatforms]
  );

  // বাংলা মন্তব্য: dnd-kit DndContext-এর onDragEnd-এ সরাসরি বসানোর জন্য
  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { over, active } = event;
      if (!over) return;
      const platform = String(over.id);
      const draggedId = String(active.id);
      const { content, context } = resolveContent(draggedId);

      // HITL: Hold the action and set node to pending
      setPendingAction({ platform, content, context: context ?? {} });
      setStatus(platform, 'pending', 'Awaiting your confirmation...');
    },
    [resolveContent, setStatus]
  );

  const confirmAction = useCallback(async () => {
    if (!pendingAction) return;
    const { platform, content, context } = pendingAction;
    setPendingAction(null);
    await executeAction(platform, content, context);
  }, [pendingAction, executeAction]);

  const cancelAction = useCallback(() => {
    if (!pendingAction) return;
    setStatus(pendingAction.platform, 'idle', '');
    setPendingAction(null);
    showToast('info', 'Action cancelled by user.');
  }, [pendingAction, setStatus, showToast]);

  return { nodeStatus, executeAction, handleDragEnd, pendingAction, confirmAction, cancelAction };
}
