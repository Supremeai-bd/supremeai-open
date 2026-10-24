import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../../../services/apiClient";
import { adminTokenStore } from "../../../services/adminTokenStore";
import type { AdminUser } from '../../../types';

interface UserManagerProps {
  newUsername: string;
  setNewUsername: (val: string) => void;
  newUserRole: string;
  setNewUserRole: (val: string) => void;
  newUserPerms: string;
  setNewUserPerms: (val: string) => void;
}

export function UserManager({
  newUsername, setNewUsername,
  newUserRole, setNewUserRole,
  newUserPerms, setNewUserPerms,
}: UserManagerProps) {
  const qc = useQueryClient();
  const [userToDelete, setUserToDelete] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 5;

  const hasToken = () => !!adminTokenStore.getDecodedToken();

  const { data: adminUsers = [], isLoading } = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => apiClient.get<AdminUser[]>('/admin-api/users'),
    enabled: hasToken(),
    staleTime: 20_000,
  });

  const saveMutation = useMutation({
    mutationFn: (user: { username: string; role: string; permissions: string[] }) =>
      apiClient.post('/admin-api/users', user),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (username: string) => apiClient.delete(`/admin-api/users/${encodeURIComponent(username)}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }),
  });

  const totalPages = Math.ceil(adminUsers.length / itemsPerPage) || 1;
  const paginatedUsers = adminUsers.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);

  const confirmDelete = () => {
    if (userToDelete) {
      deleteMutation.mutate(userToDelete);
      setUserToDelete(null);
    }
  };

  const handleSaveUserClick = () => {
    if (!newUsername.trim()) {
      window.dispatchEvent(new CustomEvent('supremeai-toast', { detail: { message: 'Username is required', type: 'error' } }));
      return;
    }
    if (!/^[a-zA-Z0-9_.-]{3,32}$/.test(newUsername.trim())) {
      window.dispatchEvent(new CustomEvent('supremeai-toast', { detail: { message: 'Username must be 3-32 chars (letters, numbers, _ . -)', type: 'error' } }));
      return;
    }
    if (!newUserRole) {
      window.dispatchEvent(new CustomEvent('supremeai-toast', { detail: { message: 'Role is required', type: 'error' } }));
      return;
    }
    saveMutation.mutate({
      username: newUsername.trim(),
      role: newUserRole,
      permissions: newUserPerms.split(',').map(p => p.trim()).filter(Boolean),
    });
    setNewUsername('');
    setNewUserPerms('');
  };

  return (
    <div className="flex-grow bg-[#030611] p-6 overflow-y-auto font-sans relative">
      {userToDelete && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-[#0c0d12] border border-red-900/60 rounded-xl p-6 max-w-md w-full shadow-2xl">
            <h4 className="text-sm font-bold text-red-400 font-mono mb-2 uppercase tracking-wider">⚠️ Confirm Revoke Role</h4>
            <p className="text-xs text-slate-300 mb-6 font-mono">
              Are you sure you want to revoke administrative access for user <span className="text-white font-bold">{userToDelete}</span>? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-3 font-mono text-xs">
              <button onClick={() => setUserToDelete(null)} className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-slate-300 rounded-lg border border-slate-800 transition-colors">Cancel</button>
              <button onClick={confirmDelete} className="px-4 py-2 bg-red-950 hover:bg-red-900 text-red-300 font-bold rounded-lg border border-red-900 transition-colors">Confirm Revoke</button>
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between mb-6 pb-2 border-b border-slate-800">
        <h3 className="text-sm font-bold text-slate-200 tracking-wider font-mono">👤 USER & RBAC MANAGEMENT</h3>
        <span className="text-[10px] text-slate-400 font-mono bg-slate-900 border border-slate-800 px-2 py-0.5 rounded">Active Admins: {adminUsers.length}</span>
      </div>

      <div className="bg-[#0c0d12]/90 border border-slate-900 rounded-xl p-5 mb-6">
        <h4 className="text-xs font-bold text-slate-300 mb-4 uppercase tracking-wider font-mono">Add / Update Administrative Role</h4>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
          <div className="flex flex-col gap-1.5">
            <label className="text-[9px] text-slate-400 uppercase font-mono tracking-wider">Username</label>
            <input type="text" placeholder="e.g. alice" value={newUsername} onChange={e => setNewUsername(e.target.value)} className="bg-[#05060a] border border-slate-850 rounded-lg px-3.5 py-2 text-xs text-white outline-none focus:border-[#00f3ff] transition-all font-mono" />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-[9px] text-slate-400 uppercase font-mono tracking-wider">System Role</label>
            <select value={newUserRole} onChange={e => setNewUserRole(e.target.value)} className="bg-[#05060a] border border-slate-850 rounded-lg px-3.5 py-2 text-xs text-white outline-none focus:border-[#00f3ff] transition-all font-mono">
              <option value="Operator">Operator</option>
              <option value="God">God Mode</option>
              <option value="Viewer">Viewer (Read-Only)</option>
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-[9px] text-slate-400 uppercase font-mono tracking-wider">Permissions (comma separated)</label>
            <input type="text" placeholder="e.g. read:logs,write:config" value={newUserPerms} onChange={e => setNewUserPerms(e.target.value)} className="bg-[#05060a] border border-slate-850 rounded-lg px-3.5 py-2 text-xs text-white outline-none focus:border-[#00f3ff] transition-all font-mono" />
          </div>
        </div>
        <div className="flex justify-end mt-4">
          <button onClick={handleSaveUserClick} disabled={saveMutation.isPending} className="bg-[#00f3ff] hover:bg-cyan-400 text-black font-extrabold px-6 py-2 rounded-lg text-xs transition-colors uppercase font-mono tracking-wider shadow-[0_4px_12px_rgba(0,243,255,0.15)] disabled:opacity-50">
            {saveMutation.isPending ? 'Provisioning...' : 'Provision / Save User'}
          </button>
        </div>
      </div>

      <h4 className="text-xs font-bold text-slate-400 mb-4 tracking-wider uppercase font-mono">Administrative User Registry</h4>
      {isLoading ? (
        <div className="text-center py-8 text-slate-400 font-mono text-xs">Loading users...</div>
      ) : (
        <div data-testid="user-list" className="flex flex-col gap-3">
          {paginatedUsers.map(user => {
            const perms = Array.isArray(user.permissions) ? user.permissions : [];
            return (
              <div key={user.username} className="bg-[#0c0d12]/60 border border-slate-900 rounded-xl p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="flex flex-col gap-2">
                  <div className="flex items-center gap-3">
                    <span className="font-bold text-sm text-white font-mono">{user.username}</span>
                    <span className={`px-2 py-0.5 rounded text-[9px] font-bold border font-mono ${user.role === 'God' ? 'bg-red-950/80 text-red-400 border-red-900/60' : user.role === 'Operator' ? 'bg-cyan-950/80 text-[#00f3ff] border-cyan-900/60' : 'bg-slate-900 text-slate-400 border-slate-800'}`}>{user.role}</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {perms.map((perm: string, idx: number) => (<span key={idx} className="bg-slate-950 text-slate-400 border border-slate-900 px-2 py-0.5 rounded text-[9px] font-mono">{perm}</span>))}
                    {perms.length === 0 && <span className="text-[10px] text-slate-400 italic font-mono">No special permissions assigned</span>}
                  </div>
                </div>
                <button onClick={() => setUserToDelete(user.username)} disabled={deleteMutation.isPending} className="self-end md:self-auto bg-red-950/30 hover:bg-red-900/40 text-red-400 border border-red-900/30 hover:border-red-900/60 px-3 py-1.5 rounded-lg text-xs font-bold transition-all uppercase font-mono tracking-wider disabled:opacity-50">Revoke Role</button>
              </div>
            );
          })}
          {adminUsers.length === 0 && (
            <div className="text-center py-8 bg-[#0c0d12]/30 border border-slate-900 rounded-xl text-slate-400 italic font-mono">No administrative users provisioned in registry.</div>
          )}
        </div>
      )}

      {adminUsers.length > itemsPerPage && (
        <div className="flex items-center justify-between mt-6 pt-4 border-t border-slate-900 text-xs font-mono text-slate-400">
          <span>Showing {((currentPage - 1) * itemsPerPage) + 1} - {Math.min(currentPage * itemsPerPage, adminUsers.length)} of {adminUsers.length}</span>
          <div className="flex items-center gap-2">
            <button disabled={currentPage === 1} onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))} className="px-3 py-1 bg-slate-900 hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed rounded border border-slate-800 transition-colors">Prev</button>
            <span>Page {currentPage} of {totalPages}</span>
            <button disabled={currentPage >= totalPages} onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))} className="px-3 py-1 bg-slate-900 hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed rounded border border-slate-800 transition-colors">Next</button>
          </div>
        </div>
      )}
    </div>
  );
}
