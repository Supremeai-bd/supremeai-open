import { useEffect, useRef, useState, type FormEvent } from 'react';
import { invoke } from '@tauri-apps/api/core';
import './admin.css';

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
type AdminView = 'overview' | 'services' | 'tenants';

function displayCount(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—';
  return new Intl.NumberFormat().format(value);
}

function displayCost(value: number | undefined) {
  if (value == null || !Number.isFinite(value)) return '—';
  return new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 4 }).format(value);
}

function statusTone(status?: string) {
  const normalized = status?.trim().toLowerCase();
  if (['healthy', 'ready', 'ok', 'up', 'operational'].includes(normalized ?? '')) return 'admin-status--healthy';
  if (['degraded', 'warning', 'limited'].includes(normalized ?? '')) return 'admin-status--warning';
  if (['down', 'offline', 'unhealthy', 'failed', 'error', 'critical'].includes(normalized ?? '')) return 'admin-status--offline';
  return 'admin-status--unknown';
}

function statusLabel(status?: string) {
  const normalized = status?.trim().toLowerCase();
  if (['healthy', 'ready', 'ok', 'up', 'operational'].includes(normalized ?? '')) return 'healthy';
  if (['degraded', 'warning', 'limited'].includes(normalized ?? '')) return 'degraded';
  if (['down', 'offline', 'unhealthy', 'failed', 'error', 'critical'].includes(normalized ?? '')) return 'down';
  return 'unknown';
}

function isHealthyStatus(status?: string) {
  return statusTone(status) === 'admin-status--healthy';
}

function prettify(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function TenantTable({ tenants, usageByTenant, emptyMessage }: { tenants: Tenant[]; usageByTenant: Map<string, Usage>; emptyMessage: string }) {
  return (
    <div className="admin-table-wrap">
      <table className="admin-table">
        <thead><tr><th>Organization</th><th>Plan</th><th>Requests today</th><th>Tokens today</th><th>Cost today</th></tr></thead>
        <tbody>
          {tenants.map((tenant) => {
            const usage = usageByTenant.get(tenant.tenant_id);
            return <tr key={tenant.tenant_id}><td><strong>{tenant.org_name || 'Unnamed tenant'}</strong><small className="admin-tenant-id">{tenant.tenant_id}</small></td><td>{tenant.billing_tier || '—'}</td><td>{displayCount(usage?.requests_today)}</td><td>{displayCount(usage?.tokens_today)}</td><td>{displayCost(usage?.cost_today)}</td></tr>;
          })}
          {tenants.length === 0 && <tr><td colSpan={5} className="admin-empty-cell">{emptyMessage}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

export default function AdminDashboard({ onClose }: { onClose: () => void }) {
  const dialogRef = useRef<HTMLElement | null>(null);
  const closeRef = useRef<() => void>(() => undefined);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [needsOtp, setNeedsOtp] = useState(false);
  const [needsSetup, setNeedsSetup] = useState(false);
  const [role, setRole] = useState<AdminRole | null>(null);
  const [sessionEmail, setSessionEmail] = useState('');
  const [data, setData] = useState<DashboardData | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadingData, setLoadingData] = useState(false);
  const [notice, setNotice] = useState('');
  const [activeView, setActiveView] = useState<AdminView>('overview');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [tenantSearch, setTenantSearch] = useState('');

  async function refreshDashboard() {
    setLoadingData(true);
    setNotice('');
    try {
      const result = await invoke<DashboardData>('admin_dashboard');
      setData(result);
      setLastUpdated(new Date());
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
      const result = await invoke<LoginResult>('admin_login', { mode: 'owner', email, password });
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
      if (result.status !== 'authenticated' || result.role !== 'admin') {
        throw new Error('The authentication service returned an invalid session.');
      }
      setRole('admin');
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
      const result = await invoke<LoginResult>('admin_verify_totp', { otp });
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
    setLastUpdated(null);
    setActiveView('overview');
    setTenantSearch('');
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
  const healthEntries = Object.entries(data?.health ?? {}).sort(([, left], [, right]) => {
    const priority = (status?: string) => statusTone(status) === 'admin-status--offline' ? 0 : statusTone(status) === 'admin-status--warning' ? 1 : statusTone(status) === 'admin-status--unknown' ? 2 : 3;
    return priority(left.status) - priority(right.status);
  });
  const attentionEntries = healthEntries.filter(([, item]) => !isHealthyStatus(item.status));
  const healthSummary = healthEntries.length === 0
    ? 'Unavailable'
    : attentionEntries.length === 0
      ? 'All reported healthy'
      : `${attentionEntries.length} need attention`;
  const healthSummaryTone = healthEntries.length === 0
    ? 'admin-status--unknown'
    : attentionEntries.some(([, item]) => statusTone(item.status) === 'admin-status--offline')
      ? 'admin-status--offline'
      : attentionEntries.length > 0
        ? 'admin-status--warning'
        : 'admin-status--healthy';
  const filteredTenants = (overview?.tenants ?? []).filter((tenant) => {
    const query = tenantSearch.trim().toLowerCase();
    return !query || [tenant.org_name, tenant.tenant_id, tenant.billing_tier].some((value) => value?.toLowerCase().includes(query));
  });
  const fetchedAtLabel = lastUpdated
    ? new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(lastUpdated)
    : 'Not fetched';

  return (
    <div className="admin-overlay" role="presentation">
      <section ref={dialogRef} className="admin-window" role="dialog" aria-modal="true" aria-label="SupremeAI admin console" tabIndex={-1}>
        <header className="admin-header">
          <div className="admin-brand"><span className="admin-brand-mark">S</span><span><strong>SUPREMEAI CONTROL CENTER</strong><small>Evidence-first · read-only workspace</small></span></div>
          <div className="admin-header-actions">
            {role && <span className="admin-refresh-meta" aria-live="polite">Fetched {fetchedAtLabel}</span>}
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
              <div className="admin-security-note"><span aria-hidden="true">●</span><span>Tenant-admin sign-in is disabled until owner-controlled provisioning, scoped permissions, and audit controls are ready.</span></div>
            </div>
            <form className="admin-login-card" onSubmit={needsOtp ? verifyTotp : signIn}>
              <div className="admin-card-kicker">SECURE ACCESS</div>
              {needsSetup ? (
                <>
                  <h2>Two-factor setup required</h2>
                  <p className="admin-form-copy">Complete owner TOTP enrollment through the existing admin setup flow, then return here to sign in.</p>
                  <button type="button" className="admin-button admin-button--primary" onClick={() => setNeedsSetup(false)}>Back to sign in</button>
                </>
              ) : needsOtp ? (
                <>
                  <h2>Verify it’s you</h2>
                  <p className="admin-form-copy">Enter the six-digit code from your authenticator app.</p>
                  <label className="admin-field"><span>AUTHENTICATION CODE</span><input autoFocus inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={otp} onChange={(event) => setOtp(event.target.value.replace(/\D/g, '').slice(0, 6))} placeholder="000000" /></label>
                  <button type="submit" className="admin-button admin-button--primary" disabled={busy || otp.length !== 6}>{busy ? 'Verifying…' : 'Verify and continue'}</button>
                  <button type="button" className="admin-text-button" onClick={() => { setNeedsOtp(false); setOtp(''); }}>Use a different sign-in</button>
                </>
              ) : (
                <>
                  <h2>Sign in</h2>
                  <p className="admin-form-copy">Platform owner access. Verify with your existing SupremeAI credentials.</p>
                  <label className="admin-field"><span>EMAIL</span><input type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" required /></label>
                  <label className="admin-field"><span>PASSWORD</span><input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
                  <button type="submit" className="admin-button admin-button--primary" disabled={busy}>{busy ? 'Signing in…' : 'Continue securely'}</button>
                  <p className="admin-form-footnote">Each desktop sign-in requires fresh verification; this client does not save a trusted-device token.</p>
                </>
              )}
              {notice && <p className="admin-notice" role="alert">{notice}</p>}
            </form>
          </main>
        ) : (
          <div className="admin-workspace">
            <nav className="admin-nav" aria-label="Admin sections">
              <span className="admin-nav-label">WORKSPACE</span>
              <button type="button" className={`admin-nav-item ${activeView === 'overview' ? 'admin-nav-item--active' : ''}`} aria-current={activeView === 'overview' ? 'page' : undefined} onClick={() => setActiveView('overview')}><span aria-hidden="true">⌂</span>Overview</button>
              {role === 'admin' && <>
                <button type="button" className={`admin-nav-item ${activeView === 'services' ? 'admin-nav-item--active' : ''}`} aria-current={activeView === 'services' ? 'page' : undefined} onClick={() => setActiveView('services')}><span aria-hidden="true">◈</span>Services <span className="admin-nav-count">{healthEntries.length || '—'}</span></button>
                <button type="button" className={`admin-nav-item ${activeView === 'tenants' ? 'admin-nav-item--active' : ''}`} aria-current={activeView === 'tenants' ? 'page' : undefined} onClick={() => setActiveView('tenants')}><span aria-hidden="true">▦</span>Tenants <span className="admin-nav-count">{displayCount(overview?.total ?? overview?.tenants?.length)}</span></button>
              </>}
              <div className="admin-nav-note"><strong>Read-only access</strong><span>Changes and service controls are not available in this workspace.</span></div>
            </nav>
            <main className="admin-content">
              <div className="admin-page-heading"><div><span className="admin-eyebrow">{data?.scope === 'platform' ? 'PLATFORM WORKSPACE' : 'TENANT WORKSPACE'}</span><h1>{activeView === 'services' ? 'Services & health' : activeView === 'tenants' ? 'Tenants & usage' : data?.scope === 'platform' ? 'Control center' : data?.tenant?.org_name || 'Tenant overview'}</h1><p>{sessionEmail} · {data?.scope === 'platform' ? 'Platform scope' : 'Server-assigned tenant scope'}</p></div><span className="admin-readonly-pill">READ ONLY</span></div>
              {notice && <p className="admin-notice admin-notice--wide" role="status">{notice}{data && lastUpdated ? ` Showing the last fetched snapshot from ${fetchedAtLabel}.` : ''}</p>}
              {loadingData && !data ? <div className="admin-loading" role="status">Loading authorized dashboard data…</div> : data?.scope === 'platform' ? (
                <>
                  {activeView === 'overview' && <>
                    <section className="admin-metric-grid" aria-label="Platform overview">
                      <article className="admin-metric-card"><span>SERVICE HEALTH</span><strong className={`admin-metric-status ${healthSummaryTone}`}>{healthSummary}</strong><small>{healthEntries.length ? `${healthEntries.length} reported service${healthEntries.length === 1 ? '' : 's'}` : 'No health data returned'}</small></article>
                      <article className="admin-metric-card"><span>NEEDS ATTENTION</span><strong>{displayCount(healthEntries.length ? attentionEntries.length : undefined)}</strong><small>degraded, down, or unknown</small></article>
                      <article className="admin-metric-card"><span>CONFIGURED TENANTS</span><strong>{displayCount(overview?.total ?? (overview ? registeredTenants : undefined))}</strong><small>tenant limit records</small></article>
                      <article className="admin-metric-card"><span>REQUESTS TODAY</span><strong>{displayCount(overview?.usages?.length ? totalRequests : undefined)}</strong><small>recorded UTC daily totals</small></article>
                    </section>
                    <section className="admin-section">
                      <div className="admin-section-heading"><div><span className="admin-eyebrow">PRIORITY QUEUE</span><h2>Needs attention</h2></div><button type="button" className="admin-link-button" onClick={() => setActiveView('services')}>View all services <span aria-hidden="true">→</span></button></div>
                      {healthEntries.length === 0 ? <div className="admin-inline-state"><strong>Health data unavailable</strong><span>The service health endpoint did not return any service records. Refresh to try again.</span></div> : attentionEntries.length === 0 ? <div className="admin-inline-state admin-inline-state--healthy"><strong>All reported services are healthy</strong><span>Based on the latest fetched health response at {fetchedAtLabel}; this is not a guarantee of end-to-end availability.</span></div> : <div className="admin-attention-list">{attentionEntries.slice(0, 5).map(([name, item]) => <button type="button" className="admin-attention-row" key={name} onClick={() => setActiveView('services')}><span className={`admin-status ${statusTone(item.status)}`}><i />{statusLabel(item.status)}</span><strong>{prettify(name)}</strong><span>{[item.provider, item.region, item.latency_ms != null ? `${item.latency_ms} ms` : null].filter(Boolean).join(' · ') || 'No further health detail reported'}</span><span aria-hidden="true">→</span></button>)}</div>}
                    </section>
                    <section className="admin-section">
                      <div className="admin-section-heading"><div><span className="admin-eyebrow">USAGE SNAPSHOT</span><h2>Top tenants by recorded requests</h2></div><button type="button" className="admin-link-button" onClick={() => setActiveView('tenants')}>Open tenant list <span aria-hidden="true">→</span></button></div>
                      <TenantTable tenants={[...(overview?.tenants ?? [])].sort((left, right) => (usageByTenant.get(right.tenant_id)?.requests_today ?? -1) - (usageByTenant.get(left.tenant_id)?.requests_today ?? -1)).slice(0, 5)} usageByTenant={usageByTenant} emptyMessage="No tenant records were returned." />
                    </section>
                  </>}
                  {activeView === 'services' && <section className="admin-section admin-section--first">
                    <div className="admin-section-heading"><div><span className="admin-eyebrow">INFRASTRUCTURE</span><h2>Reported service health</h2></div><span>{healthEntries.length ? `${healthEntries.length} records · fetched ${fetchedAtLabel}` : 'No health snapshot available'}</span></div>
                    {healthEntries.length ? <div className="admin-health-grid">{healthEntries.map(([name, item]) => <article className="admin-health-card" key={name}><div><span className="admin-health-name">{prettify(name)}</span><span className={`admin-status ${statusTone(item.status)}`}><i />{statusLabel(item.status)}</span></div><small>{[item.provider, item.region, item.latency_ms != null ? `${item.latency_ms} ms` : null].filter(Boolean).join(' · ') || 'No additional detail reported'}</small></article>)}</div> : <div className="admin-inline-state"><strong>Health data unavailable</strong><span>No service records were returned. A missing response is not treated as healthy.</span></div>}
                  </section>}
                  {activeView === 'tenants' && <section className="admin-section admin-section--first">
                    <div className="admin-section-heading"><div><span className="admin-eyebrow">TENANT MANAGEMENT</span><h2>Tenants</h2></div><span>{displayCount(overview?.total ?? (overview ? registeredTenants : undefined))} records · read only</span></div>
                    <label className="admin-search"><span aria-hidden="true">⌕</span><input type="search" value={tenantSearch} onChange={(event) => setTenantSearch(event.target.value)} placeholder="Search organization, tenant ID, or plan" aria-label="Search tenants" /></label>
                    <TenantTable tenants={filteredTenants} usageByTenant={usageByTenant} emptyMessage={tenantSearch ? 'No tenants match this search.' : 'No tenant records were returned.'} />
                    {overview?.truncated && <p className="admin-form-footnote">The service returned a truncated tenant list. Refine the search or use the administration API for a paginated export.</p>}
                  </section>}
                </>
              ) : data?.scope === 'tenant' ? (
                <>
                  <section className="admin-metric-grid admin-metric-grid--tenant"><article className="admin-metric-card"><span>PLAN</span><strong>{data.tenant?.billing_tier || '—'}</strong><small>Assigned tenant plan</small></article><article className="admin-metric-card"><span>REQUESTS TODAY</span><strong>{displayCount(data.usage?.requests_today)}</strong><small>UTC daily total</small></article><article className="admin-metric-card"><span>TOKENS TODAY</span><strong>{displayCount(data.usage?.tokens_today)}</strong><small>UTC daily total</small></article><article className="admin-metric-card"><span>COST TODAY</span><strong>{displayCost(data.usage?.cost_today)}</strong><small>Recorded usage</small></article></section>
                  <section className="admin-section"><div className="admin-section-heading"><div><span className="admin-eyebrow">WORKSPACE DETAILS</span><h2>{data.tenant?.org_name || 'Tenant workspace'}</h2></div><span className="admin-status admin-status--neutral"><i />assignment verified by server</span></div><div className="admin-detail-grid"><div><span>Request limit</span><strong>{displayCount(data.tenant?.requests_per_minute)} / minute</strong></div><div><span>Daily token limit</span><strong>{displayCount(data.tenant?.max_tokens_per_day)}</strong></div><div><span>Concurrent sessions</span><strong>{displayCount(data.tenant?.max_concurrent_sessions)}</strong></div></div><p className="admin-form-footnote">This view is scoped to the tenant assignment in your server-managed account. The desktop client cannot change or select that assignment.</p></section>
                </>
              ) : (
                <div className="admin-empty-state"><strong>Dashboard data is not loaded.</strong><p>Use Refresh to try again or sign in again.</p><button className="admin-button admin-button--primary" onClick={() => void refreshDashboard()} disabled={loadingData}>{loadingData ? 'Refreshing…' : 'Load dashboard'}</button></div>
              )}
            </main>
          </div>
        )}
      </section>
    </div>
  );
}
