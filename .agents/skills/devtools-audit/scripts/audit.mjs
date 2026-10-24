#!/usr/bin/env node
// DevTools-style frontend audit using Playwright (Chromium + CDP).
// Collects: console, page errors, network (CDP), performance (LCP/CLS/FCP/long tasks),
// CSS/JS coverage, DOM/SEO/a11y signals, axe-core (if installed), security headers, cookie flags.
// It records evidence only: no request/response bodies, no header values except a small
// allowlist, no cookie values. Secret-looking strings are redacted before writing.
//
// Usage:
//   node audit.mjs <url> [--out audit.raw.json] [--device desktop|mobile] [--wait 3000]
//        [--throttle slow4g] [--screenshot shot.png] [--header "Name: value"]...
//        [--storage-state state.json]
//        [--login-url URL [--user-selector S] [--pass-selector S] [--submit-selector S]]
//   Login credentials come only from env vars AUDIT_USER / AUDIT_PASS.
import { createRequire } from 'node:module';
import fs from 'node:fs';
const require = createRequire(import.meta.url);

let playwright;
try { playwright = require('playwright'); }
catch { console.error('playwright not found. Run: npm i playwright && npx playwright install chromium'); process.exit(2); }
const { chromium, devices } = playwright;

// ---------- args ----------
const argv = process.argv.slice(2);
const opts = { headers: {}, wait: 3000, device: 'desktop', out: 'audit.raw.json', timeout: 45000 };
let target;
for (let i = 0; i < argv.length; i++) {
  const a = argv[i]; const next = () => argv[++i];
  if (a === '--out') opts.out = next();
  else if (a === '--wait') opts.wait = Number(next());
  else if (a === '--device') opts.device = next();
  else if (a === '--throttle') opts.throttle = next();
  else if (a === '--screenshot') opts.screenshot = next();
  else if (a === '--timeout') opts.timeout = Number(next());
  else if (a === '--storage-state') opts.storageState = next();
  else if (a === '--login-url') opts.loginUrl = next();
  else if (a === '--user-selector') opts.userSel = next();
  else if (a === '--pass-selector') opts.passSel = next();
  else if (a === '--submit-selector') opts.submitSel = next();
  else if (a === '--header') { const h = next(); const k = h.indexOf(':'); opts.headers[h.slice(0, k).trim()] = h.slice(k + 1).trim(); }
  else if (!a.startsWith('--')) target = a;
}
if (!target) { console.error('usage: node audit.mjs <url> [options]'); process.exit(2); }

// ---------- redaction ----------
const SECRET_RE = /(?:ghp_|ghs_|github_pat_|sk-|AKIA|xox[a-z]-|AIza)[A-Za-z0-9_\-]{8,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}|Bearer\s+[A-Za-z0-9._\-]{10,}|-----BEGIN [A-Z ]+-----/g;
const SENSITIVE_PARAM = /^(token|access_token|id_token|key|api_key|apikey|secret|password|pass|auth|sig|signature|code|session|sid)$/i;
const redact = (s) => String(s ?? '').replace(SECRET_RE, '[REDACTED]');
function cleanUrl(u) {
  try {
    const x = new URL(u);
    for (const k of [...x.searchParams.keys()]) if (SENSITIVE_PARAM.test(k)) x.searchParams.set(k, 'REDACTED');
    x.hash = '';
    return redact(x.toString()).slice(0, 300);
  } catch { return redact(u).slice(0, 300); }
}

// ---------- main ----------
const meta = { target: cleanUrl(target), startedAt: new Date().toISOString(), device: opts.device, throttle: opts.throttle || null, errors: [] };
const safe = async (label, fn, fallback = null) => { try { return await fn(); } catch (e) { meta.errors.push(`${label}: ${redact(e.message).split('\n')[0]}`); return fallback; } };

const browser = await chromium.launch();
meta.browserVersion = browser.version();
const ctxOpts = opts.device === 'mobile' ? { ...devices['Pixel 7'] } : { viewport: { width: 1366, height: 768 } };
if (opts.storageState) ctxOpts.storageState = opts.storageState;
if (Object.keys(opts.headers).length) ctxOpts.extraHTTPHeaders = opts.headers;
const context = await browser.newContext(ctxOpts);

// Optional form login (separate page so the login traffic is not part of the audit).
if (opts.loginUrl) {
  await safe('login', async () => {
    const user = process.env.AUDIT_USER, pass = process.env.AUDIT_PASS;
    if (!user || !pass) throw new Error('AUDIT_USER / AUDIT_PASS env vars not set');
    const lp = await context.newPage();
    await lp.goto(opts.loginUrl, { waitUntil: 'load', timeout: opts.timeout });
    await lp.fill(opts.userSel || 'input[type=email],input[name=email],input[name=username],input[type=text]', user);
    await lp.fill(opts.passSel || 'input[type=password]', pass);
    await Promise.all([lp.waitForLoadState('networkidle', { timeout: opts.timeout }).catch(() => {}), lp.click(opts.submitSel || 'button[type=submit],input[type=submit]')]);
    meta.loggedIn = true;
    await lp.close();
  });
}

await context.addInitScript(() => {
  window.__perf = { lcp: null, fcp: null, cls: 0, longTasks: [] };
  const obs = (type, cb) => { try { new PerformanceObserver((l) => l.getEntries().forEach(cb)).observe({ type, buffered: true }); } catch {} };
  obs('largest-contentful-paint', (e) => { window.__perf.lcp = e.startTime; });
  obs('paint', (e) => { if (e.name === 'first-contentful-paint') window.__perf.fcp = e.startTime; });
  obs('layout-shift', (e) => { if (!e.hadRecentInput) window.__perf.cls += e.value; });
  obs('longtask', (e) => window.__perf.longTasks.push({ start: Math.round(e.startTime), dur: Math.round(e.duration) }));
});

const page = await context.newPage();
const cdp = await context.newCDPSession(page);
const consoleMsgs = [], pageErrors = [], browserLogs = [];
page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) consoleMsgs.push({ type: m.type(), text: redact(m.text()).slice(0, 400), url: cleanUrl(m.location().url || ''), line: m.location().lineNumber }); });
page.on('pageerror', (e) => pageErrors.push({ message: redact(e.message).slice(0, 400), stack: redact((e.stack || '').split('\n').slice(0, 3).join(' | ')).slice(0, 400) }));

await cdp.send('Network.enable'); await cdp.send('Log.enable'); await cdp.send('Performance.enable');
const reqs = new Map();
cdp.on('Network.requestWillBeSent', (e) => { reqs.set(e.requestId, { url: cleanUrl(e.request.url), method: e.request.method, type: e.type, start: e.timestamp }); });
cdp.on('Network.responseReceived', (e) => { const r = reqs.get(e.requestId); if (r) Object.assign(r, { status: e.response.status, mime: e.response.mimeType, protocol: e.response.protocol, cached: !!(e.response.fromDiskCache || e.response.fromServiceWorker), encoding: e.response.headers?.['content-encoding'] || e.response.headers?.['Content-Encoding'] || null, cacheControl: e.response.headers?.['cache-control'] || e.response.headers?.['Cache-Control'] || null }); });
cdp.on('Network.loadingFinished', (e) => { const r = reqs.get(e.requestId); if (r) { r.end = e.timestamp; r.bytes = e.encodedDataLength; } });
cdp.on('Network.loadingFailed', (e) => { const r = reqs.get(e.requestId); if (r) Object.assign(r, { failed: true, error: e.errorText, blocked: e.blockedReason || null, cors: e.corsErrorStatus?.corsError || null, end: e.timestamp }); });
cdp.on('Log.entryAdded', (e) => browserLogs.push({ source: e.entry.source, level: e.entry.level, text: redact(e.entry.text).slice(0, 300), url: cleanUrl(e.entry.url || '') }));

if (opts.throttle === 'slow4g') {
  await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 150, downloadThroughput: (1.6 * 1024 * 1024) / 8, uploadThroughput: (750 * 1024) / 8 });
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
}

await safe('coverage-start', async () => { await page.coverage.startCSSCoverage(); await page.coverage.startJSCoverage({ resetOnNavigation: false }); });

let navResp = null;
await safe('navigation', async () => { navResp = await page.goto(target, { waitUntil: 'load', timeout: opts.timeout }); });
await page.waitForLoadState('networkidle', { timeout: 6000 }).catch(() => {});
await page.waitForTimeout(opts.wait);

meta.finalUrl = cleanUrl(page.url());
meta.status = navResp ? navResp.status() : null;

const docHeaders = navResp ? await safe('headers', () => navResp.allHeaders(), {}) : {};
const want = ['content-security-policy', 'strict-transport-security', 'x-content-type-options', 'x-frame-options', 'referrer-policy', 'permissions-policy', 'cache-control', 'content-encoding', 'server'];
const securityHeaders = Object.fromEntries(want.map((h) => [h, docHeaders?.[h] ? redact(docHeaders[h]).slice(0, 200) : null]));

const perf = await safe('perf', () => page.evaluate(() => {
  const nav = performance.getEntriesByType('navigation')[0] || {};
  return { ...window.__perf, longTaskTotal: window.__perf.longTasks.reduce((s, t) => s + Math.max(0, t.dur - 50), 0),
    ttfb: nav.responseStart ?? null, domContentLoaded: nav.domContentLoadedEventEnd ?? null, load: nav.loadEventEnd ?? null,
    transferSize: nav.transferSize ?? null };
}), {});
const metrics = await safe('cdp-metrics', async () => Object.fromEntries((await cdp.send('Performance.getMetrics')).metrics.filter((m) => ['JSHeapUsedSize', 'Nodes', 'LayoutCount', 'RecalcStyleCount', 'ScriptDuration', 'LayoutDuration', 'TaskDuration'].includes(m.name)).map((m) => [m.name, m.value])), {});

const dom = await safe('dom', () => page.evaluate(() => {
  const all = document.getElementsByTagName('*'); let maxDepth = 0;
  const limit = Math.min(all.length, 6000);
  for (let i = 0; i < limit; i++) { let d = 0, n = all[i]; while (n.parentElement) { d++; n = n.parentElement; } if (d > maxDepth) maxDepth = d; }
  const imgs = [...document.images];
  const named = (el) => (el.textContent || '').trim() || el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || el.getAttribute('title') || el.querySelector('img[alt]:not([alt=""])') || el.querySelector('svg title');
  const labeled = (el) => el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || el.getAttribute('title') || (el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`)) || el.closest('label');
  const inputs = [...document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]), select, textarea')];
  const isHttps = location.protocol === 'https:';
  return {
    title: document.title || null, lang: document.documentElement.lang || null,
    viewportMeta: !!document.querySelector('meta[name=viewport]'), metaDescription: !!document.querySelector('meta[name=description]'),
    nodes: all.length, maxDepth, h1Count: document.querySelectorAll('h1').length,
    images: { total: imgs.length, missingAlt: imgs.filter((i) => !i.hasAttribute('alt')).length,
      noDimensions: imgs.filter((i) => !(i.getAttribute('width') && i.getAttribute('height')) && !i.style.aspectRatio).length,
      notLazy: imgs.filter((i) => i.loading !== 'lazy').length,
      oversized: imgs.filter((i) => i.clientWidth > 0 && i.naturalWidth > i.clientWidth * 2).slice(0, 8).map((i) => ({ src: (i.currentSrc || i.src).slice(0, 160), natural: i.naturalWidth, shown: i.clientWidth })) },
    linksWithoutName: [...document.querySelectorAll('a[href]')].filter((a) => !named(a)).length,
    buttonsWithoutName: [...document.querySelectorAll('button,[role=button]')].filter((b) => !named(b)).length,
    inputsWithoutLabel: inputs.filter((i) => !labeled(i)).length,
    iframes: document.querySelectorAll('iframe').length,
    inlineScripts: document.querySelectorAll('script:not([src])').length,
    renderBlockingScripts: document.querySelectorAll('head script[src]:not([async]):not([defer]):not([type=module])').length,
    stylesheets: document.querySelectorAll('link[rel=stylesheet]').length,
    mixedContent: isHttps ? [...document.querySelectorAll('[src^="http://"],link[href^="http://"]')].length : 0,
    horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 1,
    localStorageKeys: (() => { try { return localStorage.length; } catch { return null; } })()
  };
}), {});

const axeSrc = (() => { try { return fs.readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8'); } catch { return null; } })();
let axe = null;
if (axeSrc) axe = await safe('axe', async () => {
  await page.evaluate(axeSrc);
  const r = await page.evaluate(() => axe.run(document, { resultTypes: ['violations'] }));
  return r.violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, helpUrl: v.helpUrl, count: v.nodes.length, sample: v.nodes.slice(0, 3).map((n) => redact(n.html).slice(0, 160)) }));
});
else meta.errors.push('axe-core not installed: run `npm i axe-core` next to audit.mjs for full accessibility checks');

const coverage = await safe('coverage', async () => {
  const css = await page.coverage.stopCSSCoverage(); const js = await page.coverage.stopJSCoverage();
  const sum = (arr, usedOf) => { let total = 0, used = 0; const files = [];
    for (const e of arr) { const len = (e.text ?? e.source ?? '').length; if (!len || !e.url || e.url.startsWith('data:')) continue; const u = usedOf(e, len); total += len; used += u; files.push({ url: cleanUrl(e.url), total: len, unused: len - u }); }
    files.sort((a, b) => b.unused - a.unused);
    return { totalBytes: total, unusedBytes: total - used, unusedPct: total ? Math.round(((total - used) / total) * 100) : 0, top: files.slice(0, 5) }; };
  return {
    css: sum(css, (e) => e.ranges.reduce((s, r) => s + (r.end - r.start), 0)),
    js: sum(js, (e, len) => { if (!e.source) return len; const m = new Uint8Array(len);
      for (const f of e.functions) for (const r of f.ranges) m.fill(r.count > 0 ? 1 : 0, Math.min(r.startOffset, len), Math.min(r.endOffset, len));
      let u = 0; for (let i = 0; i < len; i++) u += m[i]; return u; })
  };
});

const cookies = await safe('cookies', async () => (await context.cookies()).map((c) => ({ name: redact(c.name).slice(0, 60), domain: c.domain, secure: c.secure, httpOnly: c.httpOnly, sameSite: c.sameSite })), []);
if (opts.screenshot) await safe('screenshot', () => page.screenshot({ path: opts.screenshot, fullPage: false }));

// network summary
const finish = (r) => (r.end && r.start ? Math.round((r.end - r.start) * 1000) : null);
const rows = [...reqs.values()].map((r) => ({ url: r.url, method: r.method, type: r.type, status: r.status ?? null, mime: r.mime || null, bytes: r.bytes ?? null, ms: finish(r), failed: !!r.failed, error: r.error || null, blocked: r.blocked || null, cors: r.cors || null, cached: !!r.cached, encoding: r.encoding || null, cacheControl: r.cacheControl || null, protocol: r.protocol || null }));
const byType = {}; for (const r of rows) { const t = r.type || 'Other'; byType[t] ??= { count: 0, bytes: 0 }; byType[t].count++; byType[t].bytes += r.bytes || 0; }
const network = { total: rows.length, totalBytes: rows.reduce((s, r) => s + (r.bytes || 0), 0), byType,
  failed: rows.filter((r) => r.failed || (r.status && r.status >= 400)).slice(0, 60),
  slow: rows.filter((r) => (r.ms || 0) > 1500).sort((a, b) => b.ms - a.ms).slice(0, 15),
  large: rows.filter((r) => (r.bytes || 0) > 500 * 1024).sort((a, b) => b.bytes - a.bytes).slice(0, 15),
  uncompressedText: rows.filter((r) => /javascript|css|json|html|svg/.test(r.mime || '') && (r.bytes || 0) > 20 * 1024 && !r.encoding && !r.cached).slice(0, 15),
  thirdPartyHosts: [...new Set(rows.map((r) => { try { return new URL(r.url).host; } catch { return null; } }).filter(Boolean))].slice(0, 40) };

await browser.close();
meta.finishedAt = new Date().toISOString();
const out = { meta, console: consoleMsgs.slice(0, 80), pageErrors: pageErrors.slice(0, 40), browserLogs: browserLogs.slice(0, 40), network, performance: { ...perf, cdp: metrics }, dom, axe, coverage, securityHeaders, cookies, mainDocument: { status: meta.status } };
fs.writeFileSync(opts.out, JSON.stringify(out, null, 2));
console.log(`audit ok -> ${opts.out} | requests=${network.total} failed=${network.failed.length} console=${consoleMsgs.length} pageErrors=${pageErrors.length} axe=${axe ? axe.length : 'n/a'}`);
