// apps/studio-client/src/components/admin/LibrarianQueue.tsx
import React, { useState, useEffect } from 'react';
import { getApiBaseUrl } from '../../utils/api';
import { getAuthHeaders } from '../../services/apiClient';

interface SkillMetadata {
  skill_id: string;
  name: string;
  description: string;
  source_url: string;
  checksum: string;
  status: string;
  permissions: {
    allow_network: boolean;
    allow_filesystem_write: boolean;
  };
}

export const LibrarianQueue: React.FC = () => {
  const [queue, setQueue] = useState<SkillMetadata[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    (async () => {
      fetch(`${getApiBaseUrl()}/api/admin/librarian/queue`, {
        headers: await getAuthHeaders(),
      })
        .then(res => res.json())
        .then(data => { setQueue(data); setLoading(false); })
        .catch(err => console.error("Error fetching quarantine queue:", err));
    })();
  }, []);

  const handleAction = async (skillId: string, action: 'APPROVE' | 'APPROVE_AS_EPHEMERAL' | 'REJECT') => {
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/admin/librarian/process`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(await getAuthHeaders()) },
        body: JSON.stringify({ skill_id: skillId, action })
      });
      const result = await response.json();
      if (result.success) {
        // সফল হলে লোকাল স্টেট থেকে রিমুভ
        setQueue(prev => prev.filter(item => item.skill_id !== skillId));
      }
    } catch {
      alert("Failed to execute librarian action.");
    }
  };

  if (loading) return <div className="p-6 text-gray-400">Loading Supreme Quarantine Registry...</div>;

  return (
    <div className="p-6 bg-slate-900 rounded-xl border border-slate-800 text-white">
      <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
        <span>🛡️</span> Librarian Security & Quarantine Queue
      </h2>

      {queue.length === 0 ? (
        <p className="text-sm text-gray-500 bg-slate-950 p-4 rounded-lg border border-slate-850">
          Everything is green. No skills currently isolated in quarantine.
        </p>
      ) : (
        <div className="flex flex-col gap-4">
          {queue.map(skill => (
            <div key={skill.skill_id} className="bg-slate-950 p-4 rounded-lg border border-slate-800 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-lg text-indigo-400">{skill.name}</h3>
                  <span className="px-2 py-0.5 text-xs rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">{skill.status}</span>
                </div>
                <p className="text-sm text-gray-400 mt-1">{skill.description}</p>
                <div className="flex gap-4 mt-2 text-xs text-gray-500">
                  <span>🌐 Network: {skill.permissions.allow_network ? "🔴 Allowed" : "🟢 Blocked"}</span>
                  <span>📁 Disk Write: {skill.permissions.allow_filesystem_write ? "🔴 Allowed" : "🟢 Blocked"}</span>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => handleAction(skill.skill_id, 'APPROVE')}
                  className="px-3 py-1.5 text-xs font-medium bg-emerald-600 hover:bg-emerald-500 text-white rounded transition"
                >
                  Approve Permanent
                </button>
                <button
                  onClick={() => handleAction(skill.skill_id, 'APPROVE_AS_EPHEMERAL')}
                  className="px-3 py-1.5 text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white rounded transition"
                >
                  Approve as Ephemeral
                </button>
                <button
                  onClick={() => handleAction(skill.skill_id, 'REJECT')}
                  className="px-3 py-1.5 text-xs font-medium bg-rose-600/20 hover:bg-rose-600 text-rose-400 hover:text-white rounded border border-rose-500/30 transition"
                >
                  Reject & Purge
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
