import React, { useEffect, useState, useCallback } from 'react';
import { adminTokenStore } from '../../../services/adminTokenStore';
import { useToast } from '../../../contexts/useToast';
import { getApiBaseUrl } from '../../../utils/api';

interface TenantLimit {
  tenant_id: string;
  org_name: string;
  billing_tier: 'free' | 'starter' | 'pro' | 'enterprise';
  requests_per_minute: number;
  max_tokens_per_day: number;
  max_concurrent_sessions: number;
  stripe_customer_id?: string;
}

interface TenantUsage {
  tenant_id: string;
  requests_today: number;
  tokens_today: number;
  cost_today: number;
}

const TIER_COLORS: Record<string, string> = {
  free: '#6b7280',
  starter: '#3b82f6',
  pro: '#8b5cf6',
  enterprise: '#f59e0b',
};

const TIER_LIMITS: Record<string, Partial<TenantLimit>> = {
  free:       { requests_per_minute: 20,  max_tokens_per_day: 50000,   max_concurrent_sessions: 2 },
  starter:    { requests_per_minute: 60,  max_tokens_per_day: 200000,  max_concurrent_sessions: 5 },
  pro:        { requests_per_minute: 200, max_tokens_per_day: 1000000, max_concurrent_sessions: 20 },
  enterprise: { requests_per_minute: 999, max_tokens_per_day: 9999999, max_concurrent_sessions: 100 },
};

const API_BASE = getApiBaseUrl();

export const RateLimitManager: React.FC = () => {
  const [tenants, setTenants] = useState<TenantLimit[]>([]);
  const [usages, setUsages] = useState<Record<string, TenantUsage>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValues, setEditValues] = useState<Partial<TenantLimit>>({});
  const { showToast } = useToast();
  const [newTenant, setNewTenant] = useState<Pick<TenantLimit, 'tenant_id' | 'org_name' | 'billing_tier'>>({
    tenant_id: '',
    org_name: '',
    billing_tier: 'free',
  });
  const [showNewForm, setShowNewForm] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${API_BASE}/admin-api/tenant-limits`, {
        headers: { 'Authorization': `Bearer ${adminTokenStore.getRawToken()}` }
      });

      // 🛡️ এপিআই স্ট্যাটাস হ্যান্ডশেক এবং সাইলেন্ট ফেইলর প্রোটেকশন
      if (!resp.ok) {
        throw new Error(`HTTP Error! Status: ${resp.status}`);
      }

      const data = await resp.json();
      setTenants(data.tenants || []);
      const usageMap: Record<string, TenantUsage> = {};
      (data.usages || []).forEach((u: TenantUsage) => { usageMap[u.tenant_id] = u; });
      setUsages(usageMap);
    } catch (e: unknown) {
      // 🚫 Fake Fallback Data (demo-org, free-user) চিরতরে রিমুভ করা হলো
      const errMsg = e instanceof Error ? e.message : 'Failed to fetch rate limit configuration.';
      setError(errMsg);
      setTenants([]);

      // 🚨 অ্যাডমিনকে লাইভ ইনফর্ম করার জন্য টোস্ট নোটিফিকেশন ফায়ার
      showToast('error', `⚠️ System Synchronization Failed: ${errMsg}`);
    }
    setLoading(false);
  }, [showToast]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleEdit = (t: TenantLimit) => {
    setEditingId(t.tenant_id);
    setEditValues({ ...t });
  };

  const handleTierChange = (tier: string) => {
    const defaults = TIER_LIMITS[tier] || {};
    setEditValues(prev => ({ ...prev, billing_tier: tier as TenantLimit['billing_tier'], ...defaults }));
  };

  const handleSave = async (tenant_id: string) => {
    setSaving(tenant_id);
    try {
      const resp = await fetch(`${API_BASE}/admin-api/tenant-limits/${tenant_id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${adminTokenStore.getRawToken()}`,
        },
        body: JSON.stringify(editValues),
      });
      if (resp.ok) {
        showToast('success', `✅ ${tenant_id} limits saved`);
        setTenants(prev => prev.map(t => t.tenant_id === tenant_id ? { ...t, ...editValues } : t));
        setEditingId(null);
      } else {
        showToast('error', `❌ Save failed: ${resp.status}`);
      }
    } catch {
      showToast('error', `❌ Save failed - server unreachable`);
    }
    setSaving(null);
  };

  const handleCreateTenant = async () => {
    if (!newTenant.tenant_id.trim()) return;
    const record: TenantLimit = {
      ...newTenant,
      ...TIER_LIMITS[newTenant.billing_tier],
    } as TenantLimit;
    try {
      const resp = await fetch(`${API_BASE}/admin-api/tenant-limits`, {
        method: 'POST',
        // বাংলা মন্তব্য: getAdminToken এর পরিবর্তে প্রপার adminTokenStore.getRawToken() মেথড কল যোগ করা হলো
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${adminTokenStore.getRawToken()}` },
        body: JSON.stringify(record),
      });
      if (!resp.ok) {
        throw new Error(`Server returned ${resp.status}: ${resp.statusText}`);
      }
      setTenants(prev => [...prev, record]);
      setNewTenant({ tenant_id: '', org_name: '', billing_tier: 'free' });
      setShowNewForm(false);
      showToast('success', `✅ Tenant ${record.tenant_id} created`);
    } catch (e: unknown) {
      showToast('error', `❌ Failed to create tenant: ${e instanceof Error ? e.message : 'Unknown error'}`);
    }
  };

  const usagePercent = (used: number, max: number) => Math.min(100, Math.round((used / max) * 100));

  if (loading) return <div>Loading limits...</div>;
  if (error) return <div className="text-red-500">Error: {error}</div>;

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <div>
          <h2 style={styles.title}>🛡️ Rate Limit Manager</h2>
          <p style={styles.subtitle}>Manage per-tenant API quotas and billing tiers</p>
        </div>
        <div style={styles.headerActions}>
          <button style={styles.btnSecondary} onClick={fetchData}>↻ Refresh</button>
          <button style={styles.btnPrimary} onClick={() => setShowNewForm(v => !v)}>
            {showNewForm ? '✕ Cancel' : '+ New Tenant'}
          </button>
        </div>
      </div>

      {/* New Tenant Form */}
      {showNewForm && (
        <div style={styles.newForm}>
          <h3 style={styles.formTitle}>Create New Tenant</h3>
          <div style={styles.formRow}>
            <input
              style={styles.input}
              placeholder="Tenant ID (e.g. acme-corp)"
              value={newTenant.tenant_id}
              onChange={e => setNewTenant(p => ({ ...p, tenant_id: e.target.value }))}
            />
            <input
              style={styles.input}
              placeholder="Organization Name"
              value={newTenant.org_name}
              onChange={e => setNewTenant(p => ({ ...p, org_name: e.target.value }))}
            />
            <select
              style={styles.select}
              value={newTenant.billing_tier}
              onChange={e => setNewTenant(p => ({ ...p, billing_tier: e.target.value as TenantLimit['billing_tier'] }))}
            >
              {Object.keys(TIER_LIMITS).map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            <button style={styles.btnPrimary} onClick={handleCreateTenant}>Create</button>
          </div>
        </div>
      )}

      {/* Stats Bar */}
      <div style={styles.statsBar}>
        {(['free', 'starter', 'pro', 'enterprise'] as const).map(tier => (
          <div key={tier} style={styles.statCard}>
            <span style={{ ...styles.tierBadge, background: TIER_COLORS[tier] }}>{tier}</span>
            <span style={styles.statCount}>{tenants.filter(t => t.billing_tier === tier).length}</span>
            <span style={styles.statLabel}>tenants</span>
          </div>
        ))}
      </div>

      {/* Tenant List */}
      <div style={styles.list}>
        {tenants.map(tenant => {
          const isEditing = editingId === tenant.tenant_id;
          const usage = usages[tenant.tenant_id];
          return (
            <div key={tenant.tenant_id} style={styles.card}>
              <div style={styles.cardHeader}>
                <div>
                  <span style={{ ...styles.tierBadge, background: TIER_COLORS[tenant.billing_tier] }}>
                    {isEditing ? editValues.billing_tier || tenant.billing_tier : tenant.billing_tier}
                  </span>
                  <span style={styles.tenantId}>{tenant.tenant_id}</span>
                  <span style={styles.orgName}>{tenant.org_name}</span>
                </div>
                <div style={styles.cardActions}>
                  {isEditing ? (
                    <>
                      <button
                        style={styles.btnSave}
                        onClick={() => handleSave(tenant.tenant_id)}
                        disabled={saving === tenant.tenant_id}
                      >
                        {saving === tenant.tenant_id ? 'Saving...' : '💾 Save'}
                      </button>
                      <button style={styles.btnCancel} onClick={() => setEditingId(null)}>Cancel</button>
                    </>
                  ) : (
                    <button style={styles.btnEdit} onClick={() => handleEdit(tenant)}>✎ Edit</button>
                  )}
                </div>
              </div>

              {/* Limits Row */}
              <div style={styles.limitsRow}>
                {isEditing ? (
                  <>
                    <div style={styles.limitGroup}>
                      <label style={styles.limitLabel}>Tier</label>
                      <select style={styles.selectSmall} value={editValues.billing_tier || tenant.billing_tier} onChange={e => handleTierChange(e.target.value)}>
                        {Object.keys(TIER_LIMITS).map(t => <option key={t} value={t}>{t}</option>)}
                      </select>
                    </div>
                    <div style={styles.limitGroup}>
                      <label style={styles.limitLabel}>Req/min</label>
                      <input style={styles.inputSmall} type="number" value={editValues.requests_per_minute ?? tenant.requests_per_minute} onChange={e => setEditValues(p => ({ ...p, requests_per_minute: +e.target.value }))} />
                    </div>
                    <div style={styles.limitGroup}>
                      <label style={styles.limitLabel}>Tokens/day</label>
                      <input style={styles.inputSmall} type="number" value={editValues.max_tokens_per_day ?? tenant.max_tokens_per_day} onChange={e => setEditValues(p => ({ ...p, max_tokens_per_day: +e.target.value }))} />
                    </div>
                    <div style={styles.limitGroup}>
                      <label style={styles.limitLabel}>Sessions</label>
                      <input style={styles.inputSmall} type="number" value={editValues.max_concurrent_sessions ?? tenant.max_concurrent_sessions} onChange={e => setEditValues(p => ({ ...p, max_concurrent_sessions: +e.target.value }))} />
                    </div>
                  </>
                ) : (
                  <>
                    <div style={styles.limitChip}>🔁 {tenant.requests_per_minute} req/min</div>
                    <div style={styles.limitChip}>📊 {tenant.max_tokens_per_day.toLocaleString()} tok/day</div>
                    <div style={styles.limitChip}>🔗 {tenant.max_concurrent_sessions} sessions</div>
                  </>
                )}
              </div>

              {/* Usage Bar */}
              {usage && (
                <div style={styles.usageSection}>
                  <div style={styles.usageRow}>
                    <span style={styles.usageLabel}>Today's Usage</span>
                    <span style={styles.usageCost}>${usage.cost_today.toFixed(4)}</span>
                  </div>
                  <div style={styles.progressOuter}>
                    <div style={styles.progressLabel}>
                      <span>Requests: {usage.requests_today.toLocaleString()}</span>
                      <span>{usagePercent(usage.requests_today, tenant.requests_per_minute * 1440)}%</span>
                    </div>
                    <div style={styles.progressBar}>
                      <div style={{
                        ...styles.progressFill,
                        width: `${usagePercent(usage.requests_today, tenant.requests_per_minute * 1440)}%`,
                        background: usagePercent(usage.requests_today, tenant.requests_per_minute * 1440) > 80 ? '#ef4444' : '#22c55e',
                      }} />
                    </div>
                    <div style={styles.progressLabel}>
                      <span>Tokens: {usage.tokens_today.toLocaleString()}</span>
                      <span>{usagePercent(usage.tokens_today, tenant.max_tokens_per_day)}%</span>
                    </div>
                    <div style={styles.progressBar}>
                      <div style={{
                        ...styles.progressFill,
                        width: `${usagePercent(usage.tokens_today, tenant.max_tokens_per_day)}%`,
                        background: usagePercent(usage.tokens_today, tenant.max_tokens_per_day) > 80 ? '#f59e0b' : '#3b82f6',
                      }} />
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
        {tenants.length === 0 && (
          <div style={styles.emptyState}>No tenants configured. Create one above.</div>
        )}
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: { background: '#030611', minHeight: '100%', padding: '24px', color: '#e2e8f0', fontFamily: "'Inter', sans-serif" },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' },
  title: { margin: 0, fontSize: '1.5rem', fontWeight: 700, color: '#f1f5f9' },
  subtitle: { margin: '4px 0 0', color: '#94a3b8', fontSize: '0.875rem' },
  headerActions: { display: 'flex', gap: '8px' },
  btnPrimary: { background: '#3b82f6', color: '#fff', border: 'none', borderRadius: '8px', padding: '8px 16px', cursor: 'pointer', fontSize: '0.875rem', fontWeight: 600 },
  btnSecondary: { background: '#1e293b', color: '#94a3b8', border: '1px solid #334155', borderRadius: '8px', padding: '8px 16px', cursor: 'pointer', fontSize: '0.875rem' },
  btnEdit: { background: '#1e293b', color: '#60a5fa', border: '1px solid #3b82f6', borderRadius: '6px', padding: '4px 12px', cursor: 'pointer', fontSize: '0.8rem' },
  btnSave: { background: '#065f46', color: '#6ee7b7', border: 'none', borderRadius: '6px', padding: '4px 12px', cursor: 'pointer', fontSize: '0.8rem' },
  btnCancel: { background: '#1e293b', color: '#94a3b8', border: '1px solid #334155', borderRadius: '6px', padding: '4px 12px', cursor: 'pointer', fontSize: '0.8rem' },
  newForm: { background: '#1e293b', borderRadius: '12px', padding: '20px', marginBottom: '20px', border: '1px solid #334155' },
  formTitle: { margin: '0 0 16px', color: '#f1f5f9', fontSize: '1rem' },
  formRow: { display: 'flex', gap: '12px', flexWrap: 'wrap' },
  input: { flex: 1, minWidth: '160px', background: '#0f172a', border: '1px solid #334155', borderRadius: '8px', padding: '8px 12px', color: '#e2e8f0', fontSize: '0.875rem' },
  select: { background: '#0f172a', border: '1px solid #334155', borderRadius: '8px', padding: '8px 12px', color: '#e2e8f0', fontSize: '0.875rem', cursor: 'pointer' },
  statsBar: { display: 'flex', gap: '12px', marginBottom: '20px' },
  statCard: { flex: 1, background: '#1e293b', borderRadius: '10px', padding: '16px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px', border: '1px solid #334155' },
  statCount: { fontSize: '2rem', fontWeight: 700, color: '#f1f5f9' },
  statLabel: { fontSize: '0.75rem', color: '#64748b' },
  loading: { textAlign: 'center', color: '#64748b', padding: '48px', fontSize: '1rem' },
  emptyState: { textAlign: 'center', color: '#475569', padding: '48px', fontSize: '0.9rem' },
  list: { display: 'flex', flexDirection: 'column', gap: '12px' },
  card: { background: '#1e293b', borderRadius: '12px', padding: '20px', border: '1px solid #334155', transition: 'border-color 0.2s' },
  cardHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' },
  cardActions: { display: 'flex', gap: '8px' },
  tierBadge: { display: 'inline-block', padding: '2px 10px', borderRadius: '999px', fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', color: '#fff', letterSpacing: '0.05em', marginRight: '8px' },
  tenantId: { fontWeight: 600, color: '#f1f5f9', marginRight: '8px' },
  orgName: { color: '#64748b', fontSize: '0.85rem' },
  limitsRow: { display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '12px' },
  limitChip: { background: '#0f172a', border: '1px solid #334155', borderRadius: '6px', padding: '4px 12px', fontSize: '0.8rem', color: '#94a3b8' },
  limitGroup: { display: 'flex', flexDirection: 'column', gap: '4px' },
  limitLabel: { fontSize: '0.7rem', color: '#64748b', fontWeight: 600, textTransform: 'uppercase' },
  inputSmall: { width: '100px', background: '#0f172a', border: '1px solid #334155', borderRadius: '6px', padding: '4px 8px', color: '#e2e8f0', fontSize: '0.8rem' },
  selectSmall: { background: '#0f172a', border: '1px solid #334155', borderRadius: '6px', padding: '4px 8px', color: '#e2e8f0', fontSize: '0.8rem', cursor: 'pointer' },
  usageSection: { borderTop: '1px solid #334155', paddingTop: '12px', marginTop: '4px' },
  usageRow: { display: 'flex', justifyContent: 'space-between', marginBottom: '8px' },
  usageLabel: { fontSize: '0.75rem', color: '#64748b', fontWeight: 600, textTransform: 'uppercase' },
  usageCost: { fontSize: '0.8rem', color: '#f59e0b', fontWeight: 600 },
  progressOuter: { display: 'flex', flexDirection: 'column', gap: '4px' },
  progressLabel: { display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: '#64748b' },
  progressBar: { height: '6px', background: '#0f172a', borderRadius: '3px', overflow: 'hidden' },
  progressFill: { height: '100%', borderRadius: '3px', transition: 'width 0.4s ease' },
};

export default RateLimitManager;
