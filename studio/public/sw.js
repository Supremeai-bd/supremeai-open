const CACHE_NAME = 'supremeai-pwa-cache-v5';

// #1761 ROOT CAUSE: the previous pattern (/(?:^|[-_.])[a-f0-9]{8,}(?:[-_.]|$)/i)
// accepted lowercase hex only, while Vite emits 8-char base64url hashes
// (A-Za-z0-9_-). Live probe 2026-10-28 matched 0/11 deployed assets
// (index-D_Trbe0G.js, vendor-events-Cp0iM0-l.js, ...), so the runtime
// cache-as-you-fetch branch below never cached anything — the warm path rode
// HTTP immutable cache alone and offline asset resilience was zero.
//
// Fix (two layers):
// 1. PRIMARY allowlist = build truth. /sw-assets.json is emitted by the
//    swAssetManifestPlugin (studio/vite.swAssets.ts) at build time with the
//    exact paths of every hashed asset this build produced — zero guessing,
//    zero false positives. Loaded once per SW version at install.
// 2. FAIL-SAFE fallback = the corrected shape regex below, used only when the
//    manifest is unreachable (dev servers emit unhashed assets and SW caching
//    is not needed there anyway). Anchored to Vite's emission shape: 8+
//    base64url chars as the LAST dash-separated segment immediately before
//    the extension (e.g. /assets/vendor-charts-CTAtHotd.js), which rejects
//    root-level public files with no hashed segment (logo.png, manifest.json,
//    manifest.webmanifest, robots.txt). Residual fallback-only false-positive
//    class (hyphenated-but-unhashed names like /apple-touch-icon.png) is
//    dev-only and benign — production builds always ship the manifest.
//
// Stale-allowlist note (fail-safe direction): an installed SW keeps its
// install-time allowlist until the SW itself updates. After a new deploy,
// newly named assets simply bypass SW caching and ride network + HTTP
// immutable cache — exactly the pre-fix behavior, never a stale-asset hazard.
// HTML is still never cached, so navigation always reaches the fresh deploy.
const HASHED_ASSET_PATTERN = /-[A-Za-z0-9_-]{8,}\.[A-Za-z0-9]+$/;
const PRECACHE_URLS = [];

// Set<string> of '/assets/...' pathnames from sw-assets.json; null until the
// install-time load resolves, null on failure (regex fallback takes over).
let swAssetAllowlist = null;

async function loadAssetAllowlist() {
  try {
    const res = await fetch('/sw-assets.json', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const assets = Array.isArray(data && data.assets) ? data.assets : [];
    swAssetAllowlist = new Set(assets);
    console.debug(`[SW] Asset allowlist loaded: ${assets.length} hashed assets`);
  } catch (err) {
    swAssetAllowlist = null;
    console.debug('[SW] sw-assets.json unavailable; using hash-shape fallback:', err);
  }
}

function isCacheableAsset(url) {
  if (url.origin !== self.location.origin) return false;
  if (swAssetAllowlist) return swAssetAllowlist.has(url.pathname);
  return HASHED_ASSET_PATTERN.test(url.pathname);
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async (cache) => {
      // #1761: load the build-truth allowlist before precache so the runtime
      // fetch handler uses exact manifest membership for this SW version.
      await loadAssetAllowlist();
      // বাংলা মন্তব্য: addAll ব্যবহার না করে একটা একটা করে ক্যাশ করা হচ্ছে — কোনো একটা ফেইল করলেও বাকিগুলো ক্যাশ হবে
      const results = await Promise.allSettled(
        PRECACHE_URLS.map((url) =>
          fetch(url)
            .then((res) => {
              if (res.ok) return cache.put(url, res);
              console.debug(`[SW] Skipping cache for ${url}: ${res.status}`);
            })
            .catch((err) => console.debug(`[SW] Failed to fetch ${url}:`, err))
        )
      );
      console.debug('[SW] Precache results:', results.map((r) => r.status));
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name))
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') {
    // For POST requests, ideally we'd queue them using Background Sync API
    return;
  }

  const url = new URL(event.request.url);

  // বাংলা মন্তব্য: API রেসপন্স ও থার্ড-পার্টি ডোমেইন ক্যাশ করলে stale বা CORS সমস্যা হবে — skip করা হলো
  if (
    url.pathname.startsWith('/admin-api/') ||
    url.pathname.startsWith('/api/') ||
    // থার্ড-পার্টি QR / external API কলগুলো SW intercept করলে CORS error হয় — তাই বাদ দেওয়া হলো
    url.hostname === 'api.qrserver.com' ||
    url.hostname === 'chart.googleapis.com' ||
    url.hostname === 'www.google-analytics.com'
  ) {
    return;
  }

  const isHtmlRequest = event.request.headers.get('accept')?.includes('text/html');
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Never cache HTML: stale index.html can point at an older deployment bundle.
        if (!isHtmlRequest && response.status === 200 && isCacheableAsset(url)) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseClone));
        }
        return response;
      })
      .catch(() => {
        // Fallback to cache on network failure
        return caches.match(event.request).then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }
          // Do not serve a cached HTML shell from a previous deployment.
          // A failed navigation should surface as unavailable rather than stale UI.
          // 🔥 ফিক্স: ক্যাশেও না থাকলে একটি Response না দিয়ে undefined return করলে
          // "Failed to convert value to 'Response'" error হয় — তাই একটি minimal Response দিন
          return new Response('', { status: 503, statusText: 'Service Unavailable' });
        });
      })
  );
});

// Background Sync
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-offline-actions') {
    event.waitUntil(syncOfflineActions());
  }
});

async function syncOfflineActions() {
  console.log('Background Sync: Triggering offline sync to backend');
  try {
    const response = await fetch('/api/offline/sync', { method: 'POST' });
    if (!response.ok) {
      throw new Error('Sync failed');
    }
  } catch (error) {
    console.error('Background sync failed:', error);
    throw error;
  }
}
