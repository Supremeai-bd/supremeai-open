---
name: playwright-browser-control
description: Autonomous browser automation, visual testing, responsive screenshots, and end-to-end web inspection using Playwright MCP without cloud dependencies or login requirements.
---

# Playwright Browser Control & Visual Audit Guide

This skill enables running Playwright directly from the command line or via Playwright MCP (`@playwright/mcp`) for browser automation, screenshot capture, DOM scraping, and visual testing.

## 🚀 1. Running Playwright MCP Locally (Zero-Cloud)

You can launch a headless or headful browser automation server directly using Node:

```powershell
# Launch Playwright MCP in interactive stdio mode
npx --yes @playwright/mcp --browser chrome

# Launch with Vision capabilities & console monitoring
npx --yes @playwright/mcp --browser chrome --caps vision,devtools --console-level info
```

---

## 📸 2. Quick Visual Inspection & Screenshot Script (Python/Node)

### Take an Instant Full-Page Screenshot:
```powershell
python -c "
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    page.goto('http://localhost:5173')
    page.screenshot(path='ui-audit-desktop.png', full_page=True)
    browser.close()
print('Audit screenshot captured: ui-audit-desktop.png')
"
```

### Mobile Responsive Audit (iPhone 15 Simulation):
```powershell
python -c "
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    iphone = p.devices['iPhone 15']
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(**iphone).new_page()
    page.goto('http://localhost:5173')
    page.screenshot(path='ui-audit-mobile.png')
    browser.close()
print('Mobile screenshot captured: ui-audit-mobile.png')
"
```

---

## 🎯 3. Core Capabilities
- **Responsive Layout Verification:** Verify desktop, tablet, and mobile breakpoints with pixel-perfect accuracy.
- **Console & Network Error Sniffing:** Detect uncaught JavaScript exceptions and broken API requests (404/500).
- **Zero Login Required:** Test public pages, staging environments, and localhost dev servers completely offline.

