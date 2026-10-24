/**
 * MeshAgentsPanel — MESH-2 (issue #940): connected mesh agents list with
 * Planner/Coder/Tester/Gate/Observer role-assignment dropdowns.
 *
 * Data contract (backend/api/routes/mesh.py):
 *   GET   /api/v1/nodes               → { nodes: NodeRecord[] }
 *   PATCH /api/v1/nodes/{node_id}     → { node: NodeRecord } (role update;
 *                                       invalid role → 422, unknown id → 404)
 *   NodeRecord: { node_id, node_type, role, load?, last_seen, last_seen_epoch }
 *
 * UX contract: optimistic role update with rollback + inline error on PATCH
 * failure; 10s polling; online = heartbeat within PRESENCE_TTL (registry
 * default 10 min — the backend already filters, the badge mirrors it).
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { getApiBaseUrl } from '../../utils/api';

const VALID_ROLES = ['planner', 'coder', 'tester', 'gate', 'observer'] as const;
type MeshRole = (typeof VALID_ROLES)[number];

const ROLE_STYLES: Record<string, string> = {
  planner: 'bg-sky-950/60 text-sky-300 border-sky-900/60',
  coder: 'bg-emerald-950/60 text-emerald-300 border-emerald-900/60',
  tester: 'bg-amber-950/60 text-amber-300 border-amber-900/60',
  gate: 'bg-rose-950/60 text-rose-300 border-rose-900/60',
  observer: 'bg-zinc-900 text-zinc-300 border-zinc-800',
};

const NODE_TYPE_ICONS: Record<string, string> = {
  planner: '🧭',
  coder: '⌨️',
  tester: '🧪',
  gate: '🚦',
  observer: '👁️',
  browser: '🌐',
  scraper: '🕷️',
  worker: '⚙️',
};

interface NodeLoad {
  cpu_percent?: number | null;
  memory_percent?: number | null;
  active_tasks?: number | null;
}

interface MeshNode {
  node_id: string;
  node_type: string;
  role: string;
  load?: NodeLoad | null;
  last_seen: string;
  last_seen_epoch: number;
}

function presenceLabel(lastSeenEpoch: number, nowEpoch: number): { text: string; online: boolean } {
  const ageSec = Math.max(0, Math.round(nowEpoch - lastSeenEpoch));
  const online = ageSec < 10 * 60; // presence registry TTL (default 10 min)
  const text =
    ageSec < 60
      ? `${ageSec}s ago`
      : ageSec < 3600
        ? `${Math.floor(ageSec / 60)}m ago`
        : `${Math.floor(ageSec / 3600)}h ago`;
  return { text, online };
}

export function MeshAgentsPanel() {
  const [nodes, setNodes] = useState<MeshNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [roleError, setRoleError] = useState<{ nodeId: string; message: string } | null>(null);
  const [nowEpoch, setNowEpoch] = useState(() => Date.now() / 1000);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const fetchNodes = useCallback(async () => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/v1/nodes`, {
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) throw new Error(`GET /nodes -> HTTP ${res.status}`);
      const data = (await res.json()) as { nodes?: MeshNode[] } | MeshNode[];
      const list = Array.isArray(data) ? data : (data.nodes ?? []);
      if (mountedRef.current) {
        setNodes(list);
        setError(null);
      }
    } catch (e) {
      if (mountedRef.current) {
        setError(e instanceof Error ? e.message : 'Failed to load mesh nodes');
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchNodes();
    const poll = setInterval(() => void fetchNodes(), 10_000);
    const tick = setInterval(() => setNowEpoch(Date.now() / 1000), 1_000);
    return () => {
      clearInterval(poll);
      clearInterval(tick);
    };
  }, [fetchNodes]);

  const changeRole = useCallback(
    async (nodeId: string, role: MeshRole, previousRole: string) => {
      setPending(prev => new Set(prev).add(nodeId));
      setRoleError(null);
      // Optimistic update
      setNodes(prev => prev.map(n => (n.node_id === nodeId ? { ...n, role } : n)));
      try {
        const res = await fetch(`${getApiBaseUrl()}/api/v1/nodes/${encodeURIComponent(nodeId)}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ role }),
        });
        if (!res.ok) {
          const detail = await res.json().catch(() => null);
          throw new Error(detail?.detail ?? `HTTP ${res.status}`);
        }
        const data = (await res.json()) as { node?: MeshNode };
        if (data.node) {
          setNodes(prev => prev.map(n => (n.node_id === nodeId ? data.node! : n)));
        }
      } catch (e) {
        // Rollback on any failure
        setNodes(prev => prev.map(n => (n.node_id === nodeId ? { ...n, role: previousRole } : n)));
        setRoleError({
          nodeId,
          message: e instanceof Error ? e.message : 'Role update failed',
        });
      } finally {
        setPending(prev => {
          const next = new Set(prev);
          next.delete(nodeId);
          return next;
        });
      }
    },
    [],
  );

  if (loading) {
    return (
      <section aria-label="Connected mesh agents" className="p-4 rounded-lg border border-zinc-800 bg-zinc-950/60">
        <h3 className="text-sm font-semibold text-zinc-200 mb-3">MESH AGENTS</h3>
        <div className="text-xs text-zinc-500 animate-pulse" role="status">Scanning mesh…</div>
      </section>
    );
  }

  return (
    <section aria-label="Connected mesh agents" className="p-4 rounded-lg border border-zinc-800 bg-zinc-950/60">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-zinc-200">MESH AGENTS</h3>
        <span className="text-[10px] uppercase tracking-wider text-zinc-500">
          {nodes.length} node{nodes.length === 1 ? '' : 's'}
        </span>
      </div>

      {error && (
        <p className="mb-3 text-xs text-rose-400" role="alert">
          {error}
        </p>
      )}

      {nodes.length === 0 ? (
        <p className="text-xs text-zinc-500">No mesh agents have checked in yet.</p>
      ) : (
        <ul className="divide-y divide-zinc-900 max-h-96 overflow-y-auto">
          {nodes.map(node => {
            const presence = presenceLabel(node.last_seen_epoch, nowEpoch);
            const isPending = pending.has(node.node_id);
            return (
              <li key={node.node_id} className="py-2 flex items-center gap-3">
                <span aria-hidden="true" className="text-base">
                  {NODE_TYPE_ICONS[node.node_type] ?? '🤖'}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs font-mono text-zinc-300" title={node.node_id}>
                    {node.node_id}
                  </div>
                  <div className="flex items-center gap-2 text-[10px] text-zinc-500">
                    <span
                      className={`inline-block h-1.5 w-1.5 rounded-full ${presence.online ? 'bg-emerald-400' : 'bg-zinc-600'}`}
                      aria-label={presence.online ? 'online' : 'stale'}
                    />
                    <span>{node.node_type}</span>
                    <span>·</span>
                    <span>seen {presence.text}</span>
                    {node.load?.cpu_percent != null && (
                      <>
                        <span>·</span>
                        <span>load {Math.round(node.load.cpu_percent)}%</span>
                      </>
                    )}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-0.5">
                  <select
                    aria-label={`Role for ${node.node_id}`}
                    className={`text-[11px] rounded border px-1.5 py-1 bg-zinc-900 text-zinc-200 outline-none focus:ring-1 focus:ring-zinc-600 disabled:opacity-50 ${ROLE_STYLES[node.role] ?? ROLE_STYLES.observer}`}
                    value={node.role}
                    disabled={isPending || !VALID_ROLES.includes(node.role as MeshRole)}
                    onChange={e => void changeRole(node.node_id, e.target.value as MeshRole, node.role)}
                  >
                    {VALID_ROLES.map(r => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                  {roleError?.nodeId === node.node_id && (
                    <span className="text-[10px] text-rose-400" role="alert">
                      {roleError.message} — reverted
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
