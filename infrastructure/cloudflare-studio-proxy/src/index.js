/**
 * SupremeAI Studio — Ultra-Low Latency Edge Proxy
 * Routes traffic to https://supremeai-studio.vercel.app with:
 * 1. Cloudflare BDIX / DAC Edge caching for static chunks (/assets/*) and HTML
 * 2. caches.default RAM caching (sub-20ms TTFB in Dhaka)
 * 3. Proper CORS, Host, and Security header rewriting
 * 4. Automatic /v1/* API proxy to Render with whitelisted Origin (Zero CORS errors)
 * 5. In-flight URL rewriting so guest chat calls the edge proxy seamlessly
 */

const ORIGIN = "https://supremeai-studio.vercel.app";
const API_ORIGIN = "https://supremeai-api-ulw0.onrender.com";

// 5 Render nodes kept warm to eliminate 30-50s cold-start on free tiers
const RENDER_SERVICES = [
  { name: "api", url: "https://supremeai-api-ulw0.onrender.com/health" },
  { name: "controlTower", url: "https://supremeai-mcp-tower.onrender.com/health" },
  { name: "primary", url: "https://supremeai-primary-node-5xso.onrender.com/health" },
  { name: "worker", url: "https://supremeai-worker-node.onrender.com/health" },
  { name: "scraper", url: "https://supremeai-scraper-node.onrender.com/health" },
];

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
  "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept, Origin, X-SupremeAI-Key, x-supremeai-key, X-Requested-With, X-Request-ID",
  "Access-Control-Max-Age": "86400",
};

/**
 * Pings all 5 Render service health endpoints concurrently to keep free tier containers warm.
 * Render free tier dormant timeout is 15 minutes; running every 10 minutes guarantees zero sleep.
 */
async function keepWarmAllServices() {
  const settled = await Promise.allSettled(
    RENDER_SERVICES.map(async (svc) => {
      const start = Date.now();
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 12000);
      try {
        const res = await fetch(svc.url, {
          method: "GET",
          headers: {
            "User-Agent": "SupremeAI-KeepWarm/1.0 (Cloudflare-Cron)",
            "Accept": "application/json, text/plain, */*",
          },
          signal: controller.signal,
        });
        clearTimeout(timeout);
        return {
          service: svc.name,
          url: svc.url,
          status: res.status,
          ok: res.ok,
          latencyMs: Date.now() - start,
        };
      } catch (err) {
        clearTimeout(timeout);
        return {
          service: svc.name,
          url: svc.url,
          status: "error",
          error: err.message,
          latencyMs: Date.now() - start,
        };
      }
    })
  );

  return settled.map((r, i) =>
    r.status === "fulfilled"
      ? r.value
      : { service: RENDER_SERVICES[i].name, url: RENDER_SERVICES[i].url, status: "error", error: String(r.reason), latencyMs: 0 }
  );
}

/**
 * Triggers hourly empirical learning sync on SupremeAI Core API (24x daily cadence).
 */
async function triggerHourlyLearningSync() {
  const syncUrl = `${API_ORIGIN}/api/v1/kaggle/cron-learn`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const res = await fetch(syncUrl, {
      method: "POST",
      headers: {
        "User-Agent": "SupremeAI-EdgeCron/1.0 (Cloudflare-Worker)",
        "X-Cron-Source": "cloudflare-edge-hourly",
        "Content-Type": "application/json",
      },
      signal: controller.signal,
    });
    clearTimeout(timeout);
    return { ok: res.ok, status: res.status };
  } catch (err) {
    clearTimeout(timeout);
    return { ok: false, error: err.message };
  }
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // 1. Health check endpoint
    if (url.pathname === "/cf-health") {
      return new Response(JSON.stringify({
        status: "healthy",
        edge: "cloudflare-dac-edge",
        origin: ORIGIN,
        api: API_ORIGIN,
        keepwarm: {
          cron: "*/10 * * * *",
          targets: RENDER_SERVICES.map((s) => s.name),
        },
        timestamp: new Date().toISOString()
      }), {
        headers: { "Content-Type": "application/json", ...CORS_HEADERS }
      });
    }

    // 1b. On-demand keep-warm ping & diagnostic endpoint
    if (url.pathname === "/cf-keepwarm") {
      const results = await keepWarmAllServices();
      return new Response(JSON.stringify({
        status: "success",
        timestamp: new Date().toISOString(),
        services: results,
      }, null, 2), {
        headers: { "Content-Type": "application/json", ...CORS_HEADERS }
      });
    }

    // 1c. On-demand hourly learning sync probe endpoint
    if (url.pathname === "/cf-sync-learning") {
      const result = await triggerHourlyLearningSync();
      return new Response(JSON.stringify({
        status: result.ok ? "success" : "failed",
        timestamp: new Date().toISOString(),
        result,
      }, null, 2), {
        headers: { "Content-Type": "application/json", ...CORS_HEADERS }
      });
    }

    // 2. Handle /v1/* API calls: proxy directly to supremeai-api on Render
    if (url.pathname.startsWith("/v1/")) {
      if (request.method === "OPTIONS") {
        return new Response(null, { status: 204, headers: CORS_HEADERS });
      }

      const apiUrl = new URL(url.pathname + url.search, API_ORIGIN);
      const forwardHeaders = new Headers(request.headers);
      forwardHeaders.set("Host", "supremeai-api-ulw0.onrender.com");
      // Use whitelisted Vercel origin so Render's CORS never blocks it
      forwardHeaders.set("Origin", "https://supremeai-studio.vercel.app");
      if (!forwardHeaders.get("X-SupremeAI-Key")) {
        forwardHeaders.set("X-SupremeAI-Key", "guest");
      }

       try {
         let reqBody = undefined;
         if (request.method !== "GET" && request.method !== "HEAD") {
           let text = await request.text();
           // If model requested is hardcoded groq/reasoning, map to auto for Webhook -> API -> Fallback
           try {
             const parsed = JSON.parse(text);
             if (parsed.model === "supremeai/groq" || parsed.model === "supremeai/openrouter") {
               parsed.model = "auto";
               text = JSON.stringify(parsed);
             }
           } catch (_) {}
           reqBody = text;
         }

         const apiController = new AbortController();
         const apiTimeout = setTimeout(() => apiController.abort(), 15000);
         const apiResp = await fetch(apiUrl.toString(), {
           method: request.method,
           headers: forwardHeaders,
           body: reqBody,
           redirect: "follow",
           signal: apiController.signal,
         });
         clearTimeout(apiTimeout);

        const respHeaders = new Headers(apiResp.headers);
        for (const [k, v] of Object.entries(CORS_HEADERS)) {
          respHeaders.set(k, v);
        }

        return new Response(apiResp.body, {
          status: apiResp.status,
          statusText: apiResp.statusText,
          headers: respHeaders,
        });
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message, status: "gateway_proxy_error" }), {
          status: 502,
          headers: { "Content-Type": "application/json", ...CORS_HEADERS }
        });
      }
    }

    // 3. Edge Cache Lookup (RAM speed) for static pages & assets
    // NOTE: cache key is normalized to the URL only (no request headers) so that
    // browsers sending different Accept/User-Agent headers still share one cache
    // entry. Otherwise every distinct header combination missed the cache and
    // fell through to the (slow) origin fetch.
    const cache = caches.default;
    const cacheKey = new Request(url.toString(), { method: "GET" });
    if (request.method === "GET") {
      const cached = await cache.match(cacheKey);
      if (cached) {
        const h = new Headers(cached.headers);
        h.set("X-Edge-Cache", "HIT-DAC");
        return new Response(cached.body, {
          status: cached.status,
          headers: h
        });
      }
    }

    const targetUrl = new URL(url.pathname + url.search, ORIGIN);

    // Forward headers with appropriate Host
    const forwardHeaders = new Headers(request.headers);
    forwardHeaders.set("Host", "supremeai-studio.vercel.app");
    forwardHeaders.set("X-Forwarded-Host", url.host);
    forwardHeaders.set("X-Forwarded-Proto", "https");

    const isAsset = url.pathname.startsWith("/assets/") || 
                    url.pathname.endsWith(".js") || 
                    url.pathname.endsWith(".css") || 
                    url.pathname.endsWith(".png") || 
                    url.pathname.endsWith(".svg") || 
                    url.pathname.endsWith(".ico") || 
                    url.pathname.endsWith(".woff2");

    // Origin fetch with a hard timeout so a slow/unreachable Vercel origin can
    // never hang the worker until Cloudflare returns 522 (the "takes too long"
    // symptom). On timeout/failure we serve a cached copy if available, else a
    // degraded offline page.
    const ORIGIN_TIMEOUT_MS = 8000;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), ORIGIN_TIMEOUT_MS);

    let response;
    try {
      response = await fetch(targetUrl.toString(), {
        method: request.method,
        headers: forwardHeaders,
        body: request.method !== "GET" && request.method !== "HEAD" ? request.body : undefined,
        redirect: "follow",
        signal: controller.signal,
        cf: {
          cacheEverything: isAsset,
          cacheTtl: isAsset ? 86400 * 7 : 120,
        }
      });
    } catch (err) {
      clearTimeout(timeoutId);
      // Try to serve any cached copy (even stale) before failing.
      const stale = await cache.match(cacheKey);
      if (stale) {
        const h = new Headers(stale.headers);
        h.set("X-Edge-Cache", "STALE-FALLBACK");
        return new Response(stale.body, { status: stale.status, headers: h });
      }
      // Degraded offline state (per frontend_degraded_state_on_health_failure):
      // never block the whole UI; show a minimal offline page.
      const offlineHtml = `<!doctype html><html><head><meta charset="utf-8"><title>SupremeAI Studio — Offline</title></head><body style="background:#09090b;color:#fafafa;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0"><div style="text-align:center"><h1>SupremeAI Studio</h1><p>Temporarily unavailable. Please retry in a moment.</p></div></body></html>`;
      return new Response(offlineHtml, {
        status: 503,
        headers: { "Content-Type": "text/html; charset=utf-8", ...CORS_HEADERS, "Cache-Control": "no-store" }
      });
    }
    clearTimeout(timeoutId);

    // SPA fallback: If client requested a non-asset page that returned 404, fallback to index.html
    if (response.status === 404 && !isAsset && request.method === "GET") {
      response = await fetch(`${ORIGIN}/index.html`, {
        method: "GET",
        headers: forwardHeaders,
      });
    }

    // Inject a fetch override into HTML so even cached JS routes API calls through this worker
    if (!isAsset && request.method === "GET" && response.headers.get("content-type")?.includes("text/html")) {
      let html = await response.text();
      const script = `<script>(function(){var o=window.fetch;window.fetch=function(u,init){try{if(typeof u==="string"&&u.indexOf("supremeai-api-ulw0.onrender.com")!==-1){u=u.replace("https://supremeai-api-ulw0.onrender.com",window.location.origin);}else if(u instanceof Request&&u.url.indexOf("supremeai-api-ulw0.onrender.com")!==-1){u=new Request(u.url.replace("https://supremeai-api-ulw0.onrender.com",window.location.origin),u);} }catch(e){}return o(u,init);};})();</script>`;
      html = html.replace("</head>", script + "</head>");
      const headers = new Headers(response.headers);
      headers.set("Content-Length", String(new TextEncoder().encode(html).length));
      response = new Response(html, { status: response.status, statusText: response.statusText, headers });
    }

    // Rewrite API URL inside JS assets so browser client calls this edge proxy (Zero CORS)
    let body = response.body;
    if (url.pathname.endsWith(".js") || url.pathname.includes("/assets/")) {
      const text = await response.text();
      const rewritten = text.replace(
        /https:\/\/supremeai-api-ulw0\.onrender\.com/g,
        `https://${url.host}`
      );
      body = rewritten;
    }

    // Build optimized response headers
    const respHeaders = new Headers(response.headers);
    for (const [k, v] of Object.entries(CORS_HEADERS)) {
      respHeaders.set(k, v);
    }
    respHeaders.set("X-Edge-Proxy", "SupremeAI-Cloudflare-DAC");
    respHeaders.set("X-Edge-Cache", "MISS-ORIGIN-FETCH");

    if (isAsset) {
      respHeaders.set("Cache-Control", "public, max-age=31536000, immutable");
    } else {
      respHeaders.set("Cache-Control", "public, max-age=60, s-maxage=300, stale-while-revalidate=600");
    }

    const finalResponse = new Response(body, {
      status: response.status,
      statusText: response.statusText,
      headers: respHeaders,
    });

    // Store in Edge Cache asynchronously for subsequent requests
    if (request.method === "GET" && response.status === 200) {
      ctx.waitUntil(cache.put(cacheKey, finalResponse.clone()));
    }

    return finalResponse;
  },

  // Cloudflare Cron Trigger (fires per [triggers] in wrangler.toml)
  async scheduled(event, env, ctx) {
    // 1. Keep-warm ping across all 5 Render nodes (every 10m to defeat 15m idle timeout)
    ctx.waitUntil(keepWarmAllServices());

    // 2. Hourly Empirical Learning Sync (24x daily cadence)
    // Runs at the top of each hour (minute 0-9)
    const minutes = new Date().getUTCMinutes();
    if (minutes < 10) {
      ctx.waitUntil(triggerHourlyLearningSync());
    }
  }
};