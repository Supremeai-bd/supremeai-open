// MarketplacePage — user-facing skill marketplace (ERR-B05 fix)
// বাংলা মন্তব্য: /marketplace পেজটি আগে একটি স্ট্যাটিক মার্কেটিং কার্ড ছিল
// (ERR-B05, canonical defect register 2026-09-15) — আসল marketplace কম্পোনেন্ট
// (EnhancedSkillMarketplace) admin-এ চাপা পড়ে ছিল, আর সাধারণ user-এর জন্য
// কোনো install flow বা category filter ছিল না। এখন real `/api/skills/*`
// backend কনট্র্যাক্টের ওপরে user-facing marketplace: catalog + search +
// category filters + install/uninstall।

import { useEffect, useMemo, useState } from 'react';
import { Check, Download, Plug, RefreshCw, Search, Sparkles } from 'lucide-react';
import { WorkspaceLayout } from '../components/layout/WorkspaceLayout';
import { useListResource } from '../hooks/useListResource';
import {
  fetchSkillCatalog,
  getStatusBadge,
  installSkill,
  listInstalledSkills,
  searchSkills,
  uninstallSkill,
  type SkillManifest,
} from '../services/skillsService';
import {
  BUNDLED_PLUGINS,
  connectMarketplacePlugin,
  discoverMarketplaceServer,
  listMarketplacePlugins,
  looksLikePlaintextSecret,
  type DiscoverResult,
  type MarketplaceConnection,
  type MarketplacePlugin,
} from '../services/marketplaceService';

export function MarketplacePage() {
  const [tab, setTab] = useState<'skills' | 'plugins'>('skills');
  const [installedIds, setInstalledIds] = useState<Set<string>>(new Set());
  const [category, setCategory] = useState<string>('all');
  const [query, setQuery] = useState('');
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  // বাংলা (Wave 3 dedup): skills/isLoading/loadError + load + useEffect ক্লাস্টারটি
  // এখন useListResource হুকে। fetcher-এর ভেতরে installed-set sync করা হয় —
  // এটি ক্যাটালগ load-এরই অংশ (catalog + installed একসাথে আসে), তাই page-local।
  const {
    items: skills,
    isLoading,
    loadError,
    reload: loadCatalog,
  } = useListResource<SkillManifest>({
    fetcher: async () => {
      const [catalog, installed] = await Promise.all([
        fetchSkillCatalog(),
        listInstalledSkills().catch(() => [] as SkillManifest[]),
      ]);
      setInstalledIds(new Set(installed.map((s) => s.skill_id)));
      return catalog.skills;
    },
  });

  // ── #1523 Marketplace MVP: MCP plugins (one-click BYO connect) ──────────
  // Credentials never touch this page's state in plaintext form: the form
  // accepts a vault REFERENCE (vault:<key>) and the plaintext guard mirrors
  // the server-side one, failing locally before any network call.
  const [plugins, setPlugins] = useState<MarketplacePlugin[] | null>(null);
  const [pluginsLoading, setPluginsLoading] = useState(false);
  const [pluginsOffline, setPluginsOffline] = useState(false);
  const [connectTarget, setConnectTarget] = useState<MarketplacePlugin | null>(null);
  const [connectEndpoint, setConnectEndpoint] = useState('');
  const [connectVaultRef, setConnectVaultRef] = useState('');
  const [pluginBusy, setPluginBusy] = useState(false);
  const [pluginNotice, setPluginNotice] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const [connections, setConnections] = useState<Record<string, MarketplaceConnection>>({});
  const [discovered, setDiscovered] = useState<Record<string, DiscoverResult>>({});

  const loadPlugins = async () => {
    setPluginsLoading(true);
    try {
      const live = await listMarketplacePlugins();
      setPlugins(live);
      setPluginsOffline(false);
    } catch {
      // Honest degradation: the offline snapshot is always visibly flagged.
      setPlugins([...BUNDLED_PLUGINS]);
      setPluginsOffline(true);
    } finally {
      setPluginsLoading(false);
    }
  };

  useEffect(() => {
    if (tab === 'plugins' && plugins === null && !pluginsLoading) void loadPlugins();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const openConnect = (plugin: MarketplacePlugin) => {
    setConnectTarget(plugin);
    setConnectEndpoint(plugin.endpointTemplate ?? '');
    setConnectVaultRef('');
    setPluginNotice(null);
  };

  const handleConnect = async () => {
    if (!connectTarget) return;
    const ref = connectVaultRef.trim();
    if (!ref) {
      setPluginNotice({ kind: 'error', text: 'Enter a vault reference (vault:<key>) for the credential.' });
      return;
    }
    if (looksLikePlaintextSecret(ref)) {
      setPluginNotice({
        kind: 'error',
        text: 'That looks like a live token. Store it in your vault and pass the reference (vault:<key>).',
      });
      return;
    }
    if (!connectEndpoint.trim()) {
      setPluginNotice({ kind: 'error', text: 'This plugin is self-hosted: enter your endpoint URL.' });
      return;
    }
    setPluginBusy(true);
    try {
      const res = await connectMarketplacePlugin({
        pluginId: connectTarget.pluginId,
        credentialVaultRef: ref,
        endpoint: connectEndpoint.trim(),
      });
      setConnections((prev) => ({ ...prev, [res.connection.pluginId]: res.connection }));
      setPluginNotice({
        kind: 'ok',
        text: `${connectTarget.name} connected (status: ${res.connection.status}). ${res.nextStep}`,
      });
      setConnectTarget(null);
    } catch (err) {
      setPluginNotice({ kind: 'error', text: err instanceof Error ? err.message : 'Connect failed' });
    } finally {
      setPluginBusy(false);
    }
  };

  const handleDiscover = async (pluginId: string) => {
    const conn = connections[pluginId];
    if (!conn) return;
    setPluginBusy(true);
    try {
      const res = await discoverMarketplaceServer(conn.remoteServerId);
      setDiscovered((prev) => ({ ...prev, [pluginId]: res }));
      setPluginNotice({
        kind: 'ok',
        text: `Discovered ${res.toolCount} tool(s) on ${conn.remoteServerId}. Descriptor pins now guard every remote call.`,
      });
    } catch (err) {
      setPluginNotice({ kind: 'error', text: err instanceof Error ? err.message : 'Discovery failed' });
    } finally {
      setPluginBusy(false);
    }
  };

  const categories = useMemo(() => {
    const set = new Set(skills.map((s) => s.category).filter(Boolean));
    return ['all', ...Array.from(set).sort()];
  }, [skills]);

  const visible = useMemo(() => {
    let list = skills;
    if (category !== 'all') list = list.filter((s) => s.category === category);
    if (query.trim()) {
      const q = query.trim().toLowerCase();
      list = list.filter(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          s.description.toLowerCase().includes(q) ||
          (s.tags ?? []).some((t) => t.toLowerCase().includes(q)),
      );
    }
    return list;
  }, [skills, category, query]);

  const runServerSearch = () => {
    // বাংলা: server-side keyword search (backend contract)। আগের মতোই ফলাফল
    // ক্যাটালগ *replace* করে না — search-only hits merge হয়। hook-এর override
    // closure বর্তমান items পায়, তাই stale-state ছাড়াই merge সম্ভব।
    void loadCatalog(async (current) => {
      const results = await searchSkills(query.trim());
      const byId = new Map(current.map((s) => [s.skill_id, s]));
      for (const s of results) if (!byId.has(s.skill_id)) byId.set(s.skill_id, s);
      return Array.from(byId.values());
    });
  };

  const handleInstall = async (skill: SkillManifest) => {
    setBusyId(skill.skill_id);
    setActionNotice(null);
    try {
      const res = await installSkill(skill.skill_id);
      if (res.success) {
        setInstalledIds((prev) => new Set(prev).add(skill.skill_id));
        setActionNotice(`${skill.name} installed${res.installedVersion ? ` (v${res.installedVersion})` : ''}.`);
      } else {
        setActionNotice(res.message || 'Install did not complete.');
      }
    } catch (err) {
      setActionNotice(err instanceof Error ? err.message : 'Install failed');
    } finally {
      setBusyId(null);
    }
  };

  const handleUninstall = async (skill: SkillManifest) => {
    setBusyId(skill.skill_id);
    setActionNotice(null);
    try {
      await uninstallSkill(skill.skill_id);
      setInstalledIds((prev) => {
        const next = new Set(prev);
        next.delete(skill.skill_id);
        return next;
      });
      setActionNotice(`${skill.name} uninstalled.`);
    } catch (err) {
      setActionNotice(err instanceof Error ? err.message : 'Uninstall failed');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <WorkspaceLayout>
      <div className="mx-auto w-full max-w-dash px-5 py-8 text-[var(--sa-ink)] sm:px-8 lg:py-10">
        <header className="flex flex-col gap-4 border-b border-[var(--sa-border)] pb-8">
          <div>
            <p className="sa-eyebrow">Extend / Marketplace</p>
            <h1 className="mt-2 max-w-3xl text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
              Extend the command center.
            </h1>
            <p className="mt-2 max-w-2xl text-[var(--sa-ink-muted)]">
              Discover reusable skills with clear permission boundaries — install
              what you need, when you need it.
            </p>
          </div>
          {/* #1523: skills vs MCP-plugins sections */}
          <div className="flex gap-2" role="tablist" aria-label="Marketplace sections">
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'skills'}
              data-testid="marketplace-tab-skills"
              onClick={() => setTab('skills')}
              className={`rounded-[var(--sa-radius-sm)] px-4 py-2 text-sm font-semibold transition ${
                tab === 'skills'
                  ? 'bg-[var(--sa-primary)] text-white'
                  : 'border border-[var(--sa-border)] text-[var(--sa-ink-muted)] hover:border-[var(--sa-primary)]'
              }`}
            >
              Skills
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'plugins'}
              data-testid="marketplace-tab-plugins"
              onClick={() => setTab('plugins')}
              className={`inline-flex items-center gap-2 rounded-[var(--sa-radius-sm)] px-4 py-2 text-sm font-semibold transition ${
                tab === 'plugins'
                  ? 'bg-[var(--sa-primary)] text-white'
                  : 'border border-[var(--sa-border)] text-[var(--sa-ink-muted)] hover:border-[var(--sa-primary)]'
              }`}
            >
              <Plug size={14} />
              MCP Plugins
            </button>
          </div>
          {tab === 'skills' && (
            <>
          <div className="flex flex-col gap-2 sm:flex-row">
            <div className="relative flex-1">
              <Search
                size={15}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--sa-ink-muted)]"
              />
              <input
                type="search"
                data-testid="marketplace-search-input"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void runServerSearch();
                }}
                placeholder="Search skills, tags, capabilities…"
                aria-label="Search skills"
                className="w-full rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] bg-[var(--sa-canvas)] py-2.5 pl-9 pr-3 text-sm outline-none transition focus:border-[var(--sa-primary)]"
              />
            </div>
            <button
              type="button"
              data-testid="marketplace-search-btn"
              onClick={() => void runServerSearch()}
              className="rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] px-4 py-2.5 text-sm font-semibold transition hover:border-[var(--sa-primary)]"
            >
              Search
            </button>
            <button
              type="button"
              data-testid="marketplace-refresh-btn"
              onClick={() => void loadCatalog()}
              className="inline-flex items-center justify-center gap-2 rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] px-4 py-2.5 text-sm font-semibold transition hover:border-[var(--sa-primary)]"
            >
              <RefreshCw size={15} />
              Refresh
            </button>
          </div>
          {/* Category filters */}
          <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by category">
            {categories.map((c) => (
              <button
                key={c}
                type="button"
                data-testid={`marketplace-category-${c}`}
                onClick={() => setCategory(c)}
                className={`rounded-full px-3 py-1.5 text-xs font-medium capitalize transition ${
                  category === c
                    ? 'bg-[var(--sa-primary)] text-white'
                    : 'border border-[var(--sa-border)] text-[var(--sa-ink-muted)] hover:border-[var(--sa-primary)]'
                }`}
              >
                {c}
              </button>
            ))}
          </div>
          {actionNotice && (
            <p
              role="status"
              data-testid="marketplace-notice"
              className="rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] bg-[var(--sa-surface)] px-3 py-2 text-sm"
            >
              {actionNotice}
            </p>
          )}
            </>
          )}
        </header>

        {tab === 'skills' && (
        <section className="mt-8" aria-label="Skill catalog">
          {isLoading ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {[0, 1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="sa-surface-raised h-44 animate-pulse rounded-[var(--sa-radius-sm)]"
                  aria-hidden="true"
                />
              ))}
            </div>
          ) : loadError ? (
            <div
              role="alert"
              data-testid="marketplace-error"
              className="flex flex-col gap-3 border border-red-500/40 bg-red-500/5 p-4 text-sm sm:flex-row sm:items-center"
            >
              <span className="text-red-400">{loadError}</span>
              <button
                type="button"
                onClick={() => void loadCatalog()}
                className="rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] px-3 py-1.5 font-medium transition hover:border-[var(--sa-primary)] sm:ml-auto"
              >
                Try again
              </button>
            </div>
          ) : visible.length === 0 ? (
            <div
              data-testid="marketplace-empty"
              className="sa-surface-raised flex flex-col items-center gap-2 p-10 text-center"
            >
              <Sparkles size={22} className="text-[var(--sa-primary)]" />
              <h2 className="text-lg font-semibold">No skills match</h2>
              <p className="max-w-md text-sm text-[var(--sa-ink-muted)]">
                Try a different category or clear your search to see the full
                catalog.
              </p>
            </div>
          ) : (
            <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {visible.map((skill) => {
                const badge = getStatusBadge(skill.status);
                const isInstalled = installedIds.has(skill.skill_id);
                return (
                  <li
                    key={skill.skill_id}
                    data-testid="marketplace-skill-card"
                    className="sa-surface-raised flex min-h-44 flex-col justify-between p-5 transition hover:border-[var(--sa-primary)]"
                  >
                    <div>
                      <div className="flex items-start justify-between gap-3">
                        <h2 className="text-sm font-semibold">{skill.name}</h2>
                        <span className="rounded-full bg-[var(--sa-primary-soft)] px-2 py-0.5 text-[10px] font-medium capitalize text-[var(--sa-primary)]">
                          {skill.category || 'general'}
                        </span>
                      </div>
                      <p className="mt-2 line-clamp-3 text-sm leading-6 text-[var(--sa-ink-muted)]">
                        {skill.description}
                      </p>
                      <p className="mt-2 text-[11px]" style={{ color: badge.color }}>
                        {badge.label} · v{skill.version}
                      </p>
                    </div>
                    <div className="mt-4 flex items-center justify-between border-t border-[var(--sa-border)] pt-3">
                      <span className="text-[11px] text-[var(--sa-ink-muted)]">
                        {(skill.tags ?? []).slice(0, 3).join(' · ')}
                      </span>
                      {isInstalled ? (
                        <button
                          type="button"
                          data-testid={`skill-uninstall-btn-${skill.skill_id}`}
                          onClick={() => void handleUninstall(skill)}
                          disabled={busyId === skill.skill_id}
                          className="inline-flex items-center gap-1.5 rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] px-3 py-1.5 text-xs font-medium transition hover:border-red-400 hover:text-red-400 disabled:opacity-50"
                        >
                          <Check size={13} />
                          {busyId === skill.skill_id ? 'Removing…' : 'Installed'}
                        </button>
                      ) : (
                        <button
                          type="button"
                          data-testid={`skill-install-btn-${skill.skill_id}`}
                          onClick={() => void handleInstall(skill)}
                          disabled={busyId === skill.skill_id}
                          className="inline-flex items-center gap-1.5 rounded-[var(--sa-radius-sm)] bg-[var(--sa-primary)] px-3 py-1.5 text-xs font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
                        >
                          <Download size={13} />
                          {busyId === skill.skill_id ? 'Installing…' : 'Install'}
                        </button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
        )}

        {tab === 'plugins' && (
        <section className="mt-8" aria-label="MCP plugin catalog">
          {/* #1523 Marketplace MVP — one-click BYO connect over the governed
              federation path. Vault REFERENCES only, never plaintext. */}
          {pluginsOffline && (
            <p
              role="status"
              data-testid="plugin-offline-notice"
              className="mb-4 rounded-[var(--sa-radius-sm)] border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-sm text-amber-400"
            >
              Control plane unreachable — showing the bundled offline catalog
              snapshot. Connecting requires a live control plane.
            </p>
          )}
          {pluginNotice && (
            <p
              role="status"
              data-testid="plugin-notice"
              className={`mb-4 rounded-[var(--sa-radius-sm)] border px-3 py-2 text-sm ${
                pluginNotice.kind === 'error'
                  ? 'border-red-500/40 bg-red-500/5 text-red-400'
                  : 'border-[var(--sa-border)] bg-[var(--sa-surface)]'
              }`}
            >
              {pluginNotice.text}
            </p>
          )}
          {pluginsLoading || plugins === null ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {[0, 1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="sa-surface-raised h-44 animate-pulse rounded-[var(--sa-radius-sm)]"
                  aria-hidden="true"
                />
              ))}
            </div>
          ) : (
            <>
              <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {plugins.map((plugin) => {
                  const conn = connections[plugin.pluginId];
                  const disc = discovered[plugin.pluginId];
                  return (
                    <li
                      key={plugin.pluginId}
                      data-testid={`marketplace-plugin-card-${plugin.pluginId}`}
                      className="sa-surface-raised flex min-h-44 flex-col justify-between p-5 transition hover:border-[var(--sa-primary)]"
                    >
                      <div>
                        <div className="flex items-start justify-between gap-3">
                          <h2 className="text-sm font-semibold">{plugin.name}</h2>
                          <span className="rounded-full bg-[var(--sa-primary-soft)] px-2 py-0.5 text-[10px] font-medium capitalize text-[var(--sa-primary)]">
                            {plugin.category}
                          </span>
                        </div>
                        <p className="mt-2 line-clamp-3 text-sm leading-6 text-[var(--sa-ink-muted)]">
                          {plugin.description}
                        </p>
                        <p className="mt-2 text-[11px] text-[var(--sa-ink-muted)]">
                          {plugin.endpointTemplate
                            ? `Hosted · ${plugin.endpointTemplate}`
                            : 'Self-hosted · bring your own endpoint'}{' '}
                          · trust: {plugin.trustLevel}
                        </p>
                      </div>
                      <div className="mt-4 flex items-center justify-between gap-2 border-t border-[var(--sa-border)] pt-3">
                        <span className="text-[11px] text-[var(--sa-ink-muted)]">
                          {disc
                            ? `${disc.toolCount} tool(s) pinned`
                            : conn
                              ? `Connected · ${conn.status}`
                              : 'Not connected'}
                        </span>
                        {conn && !disc ? (
                          <button
                            type="button"
                            data-testid={`plugin-discover-btn-${plugin.pluginId}`}
                            onClick={() => void handleDiscover(plugin.pluginId)}
                            disabled={pluginBusy}
                            className="rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] px-3 py-1.5 text-xs font-medium transition hover:border-[var(--sa-primary)] disabled:opacity-50"
                          >
                            Discover tools
                          </button>
                        ) : !conn ? (
                          <button
                            type="button"
                            data-testid={`plugin-connect-btn-${plugin.pluginId}`}
                            onClick={() => openConnect(plugin)}
                            className="inline-flex items-center gap-1.5 rounded-[var(--sa-radius-sm)] bg-[var(--sa-primary)] px-3 py-1.5 text-xs font-semibold text-white transition hover:opacity-90"
                          >
                            <Plug size={13} />
                            Connect
                          </button>
                        ) : (
                          <span
                            data-testid={`plugin-connected-${plugin.pluginId}`}
                            className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-400"
                          >
                            <Check size={13} />
                            Connected
                          </span>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
              {connectTarget && (
                <form
                  data-testid="plugin-connect-form"
                  aria-label={`Connect ${connectTarget.name}`}
                  onSubmit={(e) => {
                    e.preventDefault();
                    void handleConnect();
                  }}
                  className="sa-surface-raised mt-6 flex flex-col gap-4 p-5"
                >
                  <div>
                    <h3 className="text-sm font-semibold">
                      Connect {connectTarget.name}
                    </h3>
                    <p className="mt-1 text-xs text-[var(--sa-ink-muted)]">
                      Zero-risk BYO: pass a vault REFERENCE (vault:&lt;key&gt;) — never
                      a plaintext token. The connection starts pending and tool
                      relay stays blocked until tool descriptors are approved.
                    </p>
                  </div>
                  <label className="flex flex-col gap-1 text-xs font-medium">
                    Endpoint
                    <input
                      type="url"
                      data-testid="plugin-endpoint-input"
                      value={connectEndpoint}
                      onChange={(e) => setConnectEndpoint(e.target.value)}
                      placeholder="https://your-mcp-endpoint/mcp"
                      className="rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] bg-[var(--sa-canvas)] px-3 py-2 text-sm outline-none transition focus:border-[var(--sa-primary)]"
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-xs font-medium">
                    Credential vault reference
                    <input
                      type="text"
                      data-testid="plugin-vaultref-input"
                      value={connectVaultRef}
                      onChange={(e) => setConnectVaultRef(e.target.value)}
                      placeholder="vault:github-token"
                      autoComplete="off"
                      spellCheck={false}
                      className="rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] bg-[var(--sa-canvas)] px-3 py-2 text-sm outline-none transition focus:border-[var(--sa-primary)]"
                    />
                  </label>
                  <div className="flex items-center gap-2">
                    <button
                      type="submit"
                      data-testid="plugin-connect-submit"
                      disabled={pluginBusy}
                      className="rounded-[var(--sa-radius-sm)] bg-[var(--sa-primary)] px-4 py-2 text-xs font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
                    >
                      {pluginBusy ? 'Connecting…' : 'Connect plugin'}
                    </button>
                    <button
                      type="button"
                      data-testid="plugin-connect-cancel"
                      onClick={() => setConnectTarget(null)}
                      className="rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] px-4 py-2 text-xs font-medium transition hover:border-[var(--sa-primary)]"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}
            </>
          )}
        </section>
        )}
      </div>
    </WorkspaceLayout>
  );
}

export default MarketplacePage;
