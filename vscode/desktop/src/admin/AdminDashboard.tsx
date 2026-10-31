import { useEffect, useRef, useState, type FormEvent } from 'react';
import { invoke } from '@tauri-apps/api/core';
import './admin.css';

type AdminAuthMode = 'owner' | 'tenant_admin';
type AdminRole = 'admin' | 'tenant_admin';
type LoginResult = { status: string; role?: AdminRole; email?: string };
type Tenant = {
  tenant_id: string;
  org_name?: string | null;
  billing_tier?: string | null;
  created_at?: string | null;
  requests_per_minute?: number | null;
  max_tokens_per_day?: number | null;
  max_concurrent_sessions?: number | null;
};
type Usage = { tenant_id: string; requests_today: number; tokens_today: number; cost_today: number };
type TenantOverview = { total: number; tenants: Tenant[]; usages: Usage[]; truncated?: boolean };
type HealthItem = { status?: string; provider?: string; region?: string; latency_ms?: number; live_uptime_seconds?: number; configured?: boolean };
type DashboardData = {
  scope: 'platform' | 'tenant';
  role: AdminRole;
  email?: string;
  tenantOverview?: TenantOverview;
  health?: Record<string, HealthItem>;
  tenant?: Tenant;
  usage?: Usage;
};

function displayCount(value: number | null | undefined) {
  return new Intl.NumberFormat().format(Number.isFinite(value) ? value ?? 0 : 0);
}

function displayCost(value: number | undefined) {
  const amount = Number.isFinite(value) ? value ?? 0 : 0;
  return new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 4 }).format(amount);
}

function statusTone(status?: string) {
  const normalized = status?.toLowerCase();
  if (normalized === 'healthy' || normalized === 'ready' || normalized === 'ok') return 'admin-status--healthy';
  if (normalized === 'degraded' || normalized === 'warning') return 'admin-status--warning';
  return 'admin-status--offline';
}

function prettify(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export default function AdminDashboard({ onClose }: { onClose: () => void }) {
  const dialogRef = useRef<HTMLElement | null>(null);
  const closeRef = useRef<() => void>(() => undefined);
  const [mode, setMode] = useState<AdminAuthMode>('owner');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [needsOtp, setNeedsOtp] = useState(false);
  const [rememberDevice, setRememberDevice] = useState(true);
  const [needsSetup, setNeedsSetup] = useState(false);
  const [role, setRole] = useState<AdminRole | null>(null);
  const [sessionEmail, setSessionEmail] = useState('');
  const [data, setData] = useState<DashboardData | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadingData, setLoadingData] = useState(false);
  const [notice, setNotice] = useState('');

  async function refreshDashboard() {
    setLoadingData(true);
    setNotice('');
    try {
      const result = await invoke<DashboardData>('admin_dashboard');
      setData(result);
      if (result.email) setSessionEmail(result.email);
    } catch (error) {
      setNotice(typeof error === 'string' ? error : 'The admin dashboard could not be refreshed.');
    } finally {
      setLoadingData(false);
    }
  }

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setNotice('');
    try {
      const result = await invoke<LoginResult>('admin_login', { mode, email, password });
      if (result.status === 'otp_required') {
        setNeedsOtp(true);
        setNeedsSetup(false);
        return;
      }
      if (result.status === 'totp_setup_required') {
        setNeedsSetup(true);
        setNeedsOtp(false);
        return;
      }
      if (result.status !== 'authenticated' || (result.role !== 'admin' && result.role !== 'tenant_admin')) {
        throw new Error('The authentication service returned an invalid session.');
      }
      setRole(result.role);
      setSessionEmail(result.email || email);
      await refreshDashboard();
    } catch (error) {
      setNotice(typeof error === 'string' ? error : error instanceof Error ? error.message : 'Sign-in failed.');
    } finally {
      setPassword('');
      setBusy(false);
    }
  }

  async function verifyTotp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setNotice('');
    try {
      const result = await invoke<LoginResult>('admin_verify_totp', { otp, rememberDevice });
      setOtp('');
      if (result.status !== 'authenticated' || result.role !== 'admin') {
        throw new Error('The verification service returned an invalid session.');
      }
      setRole('admin');
      setSessionEmail(result.email || email);
      setNeedsOtp(false);
      await refreshDashboard();
    } catch (error) {
      setNotice(typeof error === 'string' ? error : error instanceof Error ? error.message : 'Verification failed.');
    } finally {
      setOtp('');
      setBusy(false);
    }
  }

  async function signOut() {
    setBusy(true);
    try {
      await invoke('admin_logout');
    } catch {
      // Native session is cleared by the command even if the best-effort server logout is unavailable.
    }
    setData(null);
    setRole(null);
    setSessionEmail('');
    setEmail('');
    setPassword('');
    setOtp('');
    setNeedsOtp(false);
    setNeedsSetup(false);
    setNotice('');
    setBusy(false);
  }

  function closeConsole() {
    void invoke('admin_logout').catch(() => undefined);
    onClose();
  }
  closeRef.current = closeConsole;

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = dialogRef.current;
    const focusable = () => Array.from(dialog?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ) ?? []);
    focusable()[0]?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeRef.current();
        return;
      }
      if (event.key !== 'Tab') return;
      const items = focusable();
      if (items.length === 0) {
        event.preventDefault();
        dialog?.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      } else if (!dialog?.contains(document.activeElement)) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      previousFocus?.focus();
    };
  }, []);

  const overview = data?.tenantOverview;
  const usageByTenant = new Map<string, Usage>((overview?.usages ?? []).map((usage): [string, Usage] => [usage.tenant_id, usage]));
  const totalRequests = (overview?.usages ?? []).reduce((sum, usage) => sum + (usage.requests_today || 0), 0);
  const totalTokens = (overview?.usages ?? []).reduce((sum, usage) => sum + (usage.tokens_today || 0), 0);
  const registeredTenants = (overview?.tenants ?? []).length;

  return (
    <div className="admin-overlay" role="presentation">
      <section ref={dialogRef} className="admin-window" role="dialog" aria-modal="true" aria-label="SupremeAI admin console" tabIndex={-1}>
        <header className="admin-header">
          <div className="admin-brand"><span className="admin-brand-mark">S</span><span><strong>SUPREMEAI CONTROL PLANE</strong><small>Read-only administration</small></span></div>
          <div className="admin-header-actions">
            {role && <span className="admin-session-label">{role === 'admin' ? 'PLATFORM OWNER' : 'TENANT ADMIN'}</span>}
            {role && <button className="admin-button admin-button--quiet" onClick={() => void refreshDashboard()} disabled={loadingData || busy}>{loadingData ? 'Refreshing…' : 'Refresh'}</button>}
            {role && <button className="admin-button admin-button--quiet" onClick={() => void signOut()} disabled={busy}>Sign out</button>}
            <button className="admin-close" type="button" aria-label="Return to chat" onClick={closeConsole}>×</button>
          </div>
        </header>

        {!role ? (
          <main className="admin-auth-layout">
            <div className="admin-auth-copy">
              <span className="admin-eyebrow">SUPREMEAI · ADMINISTRATION</span>
              <h1>Operations,<br /><em>in one place.</em></h1>
              <p>Sign in to review system health and tenant usage. This first release is read-only; it cannot change accounts, limits, or service settings.</p>
              <div className="admin-security-note"><span aria-hidden="true">●</span><span>Tenant scope is assigned server-side. Tenant IDs are never accepted from this screen.</span></div>
            </div>
            <form className="admin-login-card" onSubmit={needsOtp ? verifyTotp : signIn}>
              <div className="admin-card-kicker">SECURE ACCESS</div>
              {needsSetup ? (
                <>
                  <h2>Two-factor setup required</h2>
                  <p className="admin-form-copy">Complete owner TOTP enrollment through the existing admin setup flow, then return here to sign in.</p>
                  <button type="button" className="admin-button admin-button--primary" onClick={() => { setNeedsSetup(false); setMode('owner'); }}>Back to sign in</button>
                </>
              ) : needsOtp ? (
                <>
                  <h2>Verify it’s you</h2>
                  <p className="admin-form-copy">Enter the six-digit code from your authenticator app.</p>
                  <label className="admin-field"><span>AUTHENTICATION CODE</span><input autoFocus inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={otp} onChange={(event) => setOtp(event.target.value.replace(/\D/g, '').slice(0, 6))} placeholder="000000" /></label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', color: 'var(--muted)', cursor: 'pointer', margin: '4px 0 12px' }}>
                    <input type="checkbox" checked={rememberDevice} onChange={(e) => setRememberDevice(e.target.checked)} style={{ accentColor: 'var(--acid)', width: '15px', height: '15px', cursor: 'pointer' }} />
                    <span>Trust this desktop device (Save device — skip OTP for 30 days)</span>
                  </label>
                  <button type="submit" className="admin-button admin-button--primary" disabled={busy || otp.length !== 6}>{busy ? 'Verifying…' : 'Verify and continue'}</button>
                  <button type="button" className="admin-text-button" onClick={() => { setNeedsOtp(false); setOtp(''); }}>Use a different sign-in</button>
                </>
              ) : (
                <>
                  <h2>Sign in</h2>
                  <p className="admin-form-copy">Choose the account type for your existing SupremeAI credentials.</p>
                  <label className="admin-field"><span>SIGN-IN METHOD</span><select value={mode} onChange={(event) => setMode(event.target.value as AdminAuthMode)}><option value="owner">Platform owner</option><option value="tenant_admin">Tenant administrator</option></select></label>
                  <label className="admin-field"><span>EMAIL</span><input type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" required /></label>
                  <label className="admin-field"><span>PASSWORD</span><input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
                  <button type="submit" className="admin-button admin-button--primary" disabled={busy}>{busy ? 'Signing in…' : 'Continue securely'}</button>
                  <p className="admin-form-footnote">Tenant administrator assignment is managed by the platform owner in Supabase Auth.</p>
                </>
              )}
              {notice && <p className="admin-notice" role="alert">{notice}</p>}
            </form>
          </main>
        ) : (
          <main className="admin-content">
            <div className="admin-page-heading"><div><span className="admin-eyebrow">{data?.scope === 'platform' ? 'PLATFORM OVERVIEW' : 'TENANT WORKSPACE'}</span><h1>{data?.scope === 'platform' ? 'System overview' : data?.tenant?.org_name || 'Tenant overview'}</h1><p>{sessionEmail} · Read-only session</p></div><span className="admin-readonly-pill">READ ONLY</span></div>
            {notice && <p className="admin-notice admin-notice--wide" role="status">{notice}</p>}
            {loadingData && !data ? <div className="admin-loading">Loading authorized dashboard data…</div> : data?.scope === 'platform' ? (
              <>
                <section className="admin-metric-grid" aria-label="Platform totals">
                  <article className="admin-metric-card"><span>CONFIGURED TENANTS</span><strong>{displayCount(registeredTenants)}</strong><small>tenant limit records</small></article>
                  <article className="admin-metric-card"><span>REQUESTS TODAY</span><strong>{displayCount(totalRequests)}</strong><small>UTC daily totals</small></article>
                  <article className="admin-metric-card"><span>TOKENS TODAY</span><strong>{displayCount(totalTokens)}</strong><small>UTC daily totals</small></article>
                  <article className="admin-metric-card"><span>DATA ACCESS</span><strong>Read only</strong><small>No settings or limits can be changed</small></article>
                </section>
                <section className="admin-section">
                  <div className="admin-section-heading"><div><span className="admin-eyebrow">INFRASTRUCTURE</span><h2>Service health</h2></div><span>Live backend status</span></div>
                  <div className="admin-health-grid">{Object.entries(data.health ?? {}).map(([name, item]) => <article className="admin-health-card" key={name}><div><span className="admin-health-name">{prettify(name)}</span><span className={`admin-status ${statusTone(item.status)}`}><i />{item.status || 'unknown'}</span></div><small>{[item.provider, item.region, item.latency_ms != null ? `${item.latency_ms} ms` : null].filter(Boolean).join(' · ') || 'Status reported by backend'}</small></article>)}</div>
                </section>
                <section className="admin-section">
                  <div className="admin-section-heading"><div><span className="admin-eyebrow">TENANT MANAGEMENT</span><h2>Tenants</h2></div><span>{displayCount(overview?.total)} records · no actions enabled</span></div>
                  <div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Organization</th><th>Plan</th><th>Status</th><th>Requests today</th><th>Tokens today</th><th>Cost today</th></tr></thead><tbody>{(overview?.tenants ?? []).map((tenant) => { const usage = usageByTenant.get(tenant.tenant_id); return <tr key={tenant.tenant_id}><td><strong>{tenant.org_name || 'Unnamed tenant'}</strong></td><td>{tenant.billing_tier || 'free'}</td><td><span className="admin-status admin-status--healthy"><i />configured</span></td><td>{displayCount(usage?.requests_today)}</td><td>{displayCount(usage?.tokens_today)}</td><td>{displayCost(usage?.cost_today)}</td></tr>; })}{(overview?.tenants ?? []).length === 0 && <tr><td colSpan={6} className="admin-empty-cell">No tenant records were returned.</td></tr>}</tbody></table></div>
                  {overview?.truncated && <p className="admin-form-footnote">The service returned the first 1,000 tenant records.</p>}
                </section>
              </>
            ) : data?.scope === 'tenant' ? (
              <>
                <section className="admin-metric-grid admin-metric-grid--tenant"><article className="admin-metric-card"><span>PLAN</span><strong>{data.tenant?.billing_tier || 'free'}</strong><small>Assigned tenant plan</small></article><article className="admin-metric-card"><span>REQUESTS TODAY</span><strong>{displayCount(data.usage?.requests_today)}</strong><small>UTC daily total</small></article><article className="admin-metric-card"><span>TOKENS TODAY</span><strong>{displayCount(data.usage?.tokens_today)}</strong><small>UTC daily total</small></article><article className="admin-metric-card"><span>COST TODAY</span><strong>{displayCost(data.usage?.cost_today)}</strong><small>Recorded usage</small></article></section>
                <section className="admin-section"><div className="admin-section-heading"><div><span className="admin-eyebrow">WORKSPACE DETAILS</span><h2>{data.tenant?.org_name || 'Tenant workspace'}</h2></div><span className="admin-status admin-status--healthy"><i />configured</span></div><div className="admin-detail-grid"><div><span>Request limit</span><strong>{displayCount(data.tenant?.requests_per_minute)} / minute</strong></div><div><span>Daily token limit</span><strong>{displayCount(data.tenant?.max_tokens_per_day)}</strong></div><div><span>Concurrent sessions</span><strong>{displayCount(data.tenant?.max_concurrent_sessions)}</strong></div></div><p className="admin-form-footnote">This view is scoped to the tenant assignment in your server-managed account. The desktop client cannot change or select that assignment.</p></section>
              </>
            ) : (
              <div className="admin-empty-state"><strong>Dashboard data is not loaded.</strong><p>Use Refresh to try again or sign in again.</p><button className="admin-button admin-button--primary" onClick={() => void refreshDashboard()} disabled={loadingData}>{loadingData ? 'Refreshing…' : 'Load dashboard'}</button></div>
            )}
          </main>
        )}
      </section>
    </div>
  );
}
