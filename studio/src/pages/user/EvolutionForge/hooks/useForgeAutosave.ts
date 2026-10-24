import { useEffect } from 'react';
import { useReactFlow, type Node, type Edge } from '@xyflow/react';

export const useForgeAutosave = (nodes: Node[], edges: Edge[], debounceMs = 1000) => {
  const { toObject } = useReactFlow();

  useEffect(() => {
    if (nodes.length === 1 && edges.length === 0) return; // Skip initial empty state

    const handler = setTimeout(() => {
      try {
        const flow = toObject();
        localStorage.setItem('supremeai_forge_autosave', JSON.stringify(flow));
        console.warn('[SupremeAI Forge] Auto-saved layout to LocalStorage');
      } catch (e) {
        console.error('[SupremeAI Forge] Failed to auto-save layout', e);
      }
    }, debounceMs);

    return () => clearTimeout(handler);
  }, [nodes, edges, toObject, debounceMs]);
};
