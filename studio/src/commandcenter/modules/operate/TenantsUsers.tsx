import { useState } from 'react';
import { useTenants, useUsers } from '../../data/hooks';
import { useImpersonateUser, useResetTenantUsage } from '../../data/hooks';
import { DataTable, StatusPill, ConfirmModal, EmptyState } from '../../kit';
import type { Tenant, User } from '../../data/types';

export function TenantsUsers() {
  const { data: tenants, isLoading: tenantsLoading } = useTenants();
  const { data: users, isLoading: usersLoading } = useUsers();
  const impersonate = useImpersonateUser();
  const resetUsage = useResetTenantUsage();

  const [tab, setTab] = useState<'tenants' | 'users'>('tenants');
  const [impersonateTarget, setImpersonateTarget] = useState<string | null>(null);
  const [resetTarget, setResetTarget] = useState<string | null>(null);
  const [otp, setOtp] = useState('');

  const tenantColumns = [
    { key: 'org', label: 'ORG', width: '25%' },
    { key: 'tier', label: 'TIER', width: '15%' },
    { key: 'rpm_limit', label: 'RPM', width: '10%' },
    { key: 'tokens_per_day', label: 'TOKENS/DAY', width: '15%' },
    { key: 'concurrent_sessions', label: 'SESSIONS', width: '15%' },
    { key: 'status', label: 'STATUS', width: '10%', render: (t: Tenant) => <StatusPill status={t.status} size="sm" /> },
  ];

  const userColumns = [
    { key: 'name', label: 'NAME', width: '25%' },
    { key: 'email', label: 'EMAIL', width: '30%' },
    { key: 'role', label: 'ROLE', width: '15%' },
    { key: 'status', label: 'STATUS', width: '15%', render: (u: User) => <StatusPill status={u.status} size="sm" /> },
  ];

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Tenants & Users</h2>
      <div className="flex gap-2">
        <button
          onClick={() => setTab('tenants')}
          className={`px-3 py-1.5 rounded-lg text-[10px] font-mono border ${tab === 'tenants' ? 'border-[#00f3ff] text-[#00f3ff]' : 'border-[var(--sa-line)] text-[var(--sa-text-2)]'}`}
        >
          TENANTS
        </button>
        <button
          onClick={() => setTab('users')}
          className={`px-3 py-1.5 rounded-lg text-[10px] font-mono border ${tab === 'users' ? 'border-[#00f3ff] text-[#00f3ff]' : 'border-[var(--sa-line)] text-[var(--sa-text-2)]'}`}
        >
          USERS
        </button>
      </div>

      {tab === 'tenants' ? (
        tenantsLoading ? (
          <EmptyState title="টেন্যান্ট লোড হচ্ছে..." loading />
        ) : (
          <DataTable columns={tenantColumns} data={tenants ?? []} rowKey={(t) => t.tenant_id} />
        )
      ) : (
        usersLoading ? (
          <EmptyState title="ইউজার লোড হচ্ছে..." loading />
        ) : (
          <DataTable columns={userColumns} data={users ?? []} rowKey={(u) => u.id} />
        )
      )}

      <ConfirmModal
        open={!!impersonateTarget}
        title="ইমপারসনেট"
        message="আপনি কি এই ব্যবহারিকৃতর নামে লগিন করতে চান?"
        onCancel={() => { setImpersonateTarget(null); setOtp(''); }}
        onConfirm={() => {
          if (impersonateTarget) impersonate.mutate({ user_id: impersonateTarget, otp });
          setImpersonateTarget(null);
          setOtp('');
        }}
      />

      <ConfirmModal
        open={!!resetTarget}
        title="রিসেট ব্যবহার"
        message="আপনি কি এই টেন্যান্টের ব্যবহার রিসেট করতে চান?"
        onCancel={() => { setResetTarget(null); setOtp(''); }}
        onConfirm={() => {
          if (resetTarget) resetUsage.mutate({ tenant_id: resetTarget, otp });
          setResetTarget(null);
          setOtp('');
        }}
      />
    </div>
  );
}
