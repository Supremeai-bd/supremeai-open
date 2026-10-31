import puppeteer from "@cloudflare/puppeteer";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return Response.json({
        status: "healthy",
        service: "supremeai-browser-worker",
        tier: "Cloudflare Browser Run Free (24/7 Cloud Engine)",
        timestamp: Date.now()
      });
    }

    const targetUrlRaw = url.searchParams.get("url");
    if (!targetUrlRaw) {
      return Response.json({ success: false, error: "missing url parameter" }, { status: 400 });
    }
    let targetUrl;
    try {
      targetUrl = new URL(targetUrlRaw);
    } catch {
      return Response.json({ success: false, error: "invalid url" }, { status: 400 });
    }
    if (!["http:", "https:"].includes(targetUrl.protocol)) {
      return Response.json({ success: false, error: "unsupported protocol" }, { status: 400 });
    }
    const host = targetUrl.hostname.toLowerCase();
    if (
      host === "localhost" ||
      host === "127.0.0.1" ||
      host === "::1" ||
      host.startsWith("10.") ||
      host.startsWith("192.168.") ||
      /^172\.(1[6-9]|2\d|3[01])\./.test(host) ||
      host === "169.254.169.254"
    ) {
      return Response.json({ success: false, error: "target host not allowed" }, { status: 403 });
    }

    // Never expose an unauthenticated browser proxy in production.
    const expectedToken = env.SUPREMEAI_WORKER_TOKEN;
    if (!expectedToken) {
      return Response.json({ success: false, error: "worker authentication is not configured" }, { status: 503 });
    }
    const auth = request.headers.get("authorization") || "";
    if (auth !== `Bearer ${expectedToken}`) {
      return Response.json({ success: false, error: "unauthorized" }, { status: 401 });
    }

    let browser;
    try {
      browser = await puppeteer.launch(env.MYBROWSER);
      const page = await browser.newPage();

      // Optimize: block heavy assets (images, stylesheets, fonts) to execute under 3s
      await page.setRequestInterception(true);
      page.on("request", (req) => {
        const type = req.resourceType();
        if (["image", "stylesheet", "font", "media"].includes(type)) {
          req.abort();
        } else {
          req.continue();
        }
      });

      await page.goto(targetUrl.href, { waitUntil: "domcontentloaded", timeout: 15000 });
      const title = await page.title();
      const text = await page.evaluate(() => document.body ? document.body.innerText.slice(0, 2500) : "");
      await browser.close();

      return Response.json({
        success: true,
        url: targetUrl.href,
        title: title,
        content: text
      });
    } catch (err) {
      if (browser) {
        try { await browser.close(); } catch (_) {}
      }
      return Response.json({
        success: false,
        error: "browser operation failed",
        url: targetUrl.href
      }, { status: 500 });
    }
  }
};
