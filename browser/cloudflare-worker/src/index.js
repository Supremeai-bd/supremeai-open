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

    const targetUrl = url.searchParams.get("url") || "https://example.com";

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

      await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 15000 });
      const title = await page.title();
      const text = await page.evaluate(() => document.body ? document.body.innerText.slice(0, 2500) : "");
      await browser.close();

      return Response.json({
        success: true,
        url: targetUrl,
        title: title,
        content: text
      });
    } catch (err) {
      if (browser) {
        try { await browser.close(); } catch (_) {}
      }
      return Response.json({
        success: false,
        error: err.message,
        url: targetUrl
      }, { status: 500 });
    }
  }
};
