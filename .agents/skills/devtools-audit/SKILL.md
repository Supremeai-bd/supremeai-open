---
name: devtools-audit
description: Chrome DevTools-style audit of any frontend (SupremeAI's own or a customer's) - console errors, uncaught exceptions, network/API failures (404/5xx/CORS/slow), performance and Core Web Vitals, Lighthouse scores, DOM/CSS coverage, accessibility (axe), SEO and security headers - then delivers a Bangla report with concrete fixes to the Telegram bot and submits a structured copy to MCP Tower so other agents get it instantly. Use this whenever the user wants to check, debug, inspect, audit or "DevTools" a website, web app, dashboard, landing page or localhost build, or mentions slow page, console error, CORS error, broken API call on the frontend, Lighthouse, accessibility, customer site health, or sending a frontend report to Telegram/MCP Tower - even if they never say "DevTools" or "audit".
---

# DevTools Audit

Inspect a frontend the way a developer would with Chrome DevTools, turn the evidence into prioritized findings, and push the result to where the team and other agents will actually see it (Telegram + MCP Tower).

Everything is read-only and passive: load the page in headless Chromium, observe, report. No exploit payloads, no brute force, no form fuzzing.

## Why the workflow looks like this

- The sandbox Claude runs in can only reach an allowlist of hosts, so a customer URL is often unreachable from here. The audit script is therefore portable: it runs wherever the network can reach the site (the user's machine, Render, GitHub Actions), and Claude analyzes whatever raw output comes back.
- Telegram and the Tower are reached through the MCP Tower tools (`notify_send_telegram`, `bridge_submit_patch`), not by calling APIs directly, because the sandbox cannot reach those hosts and the tools already hold the credentials.
- Reports are read by humans (Telegram, Bangla) and by agents (JSON with stable rule ids), so both are generated from the same findings.

## Workflow

### 1. Pin down target and access
Collect only what is missing: the URL (or local build), device (desktop/mobile), and how to get past login if any. Audit only sites the user owns or is authorized to inspect. Credentials go through env vars (`AUDIT_USER`, `AUDIT_PASS`) or a Playwright `--storage-state` file, never into the report, memory or chat.

| Access | Flag |
|---|---|
| Public URL | just the URL |
| Localhost / own build | `http://localhost:PORT` (start the dev server first) |
| Login form | `--login-url URL` + env `AUDIT_USER`/`AUDIT_PASS` (+ optional `--user-selector/--pass-selector/--submit-selector`) |
| Pre-authenticated | `--storage-state state.json` |
| Token/API header | `--header "Authorization: Bearer ..."` |

### 2. Choose where to run
Check reachability first: `curl -s -o /dev/null -m 8 -w "%{http_code}" <url>`.

- **Reachable (localhost, allowlisted host, or a repo you cloned, built and served in the sandbox):** run the audit here (step 3).
- **Not reachable (typical for customer sites):** give the user the exact one-liner from `references/run-in-your-system.md` (local machine or GitHub Actions), ask them to upload `audit.raw.json`, then continue from step 4. If they only have a HAR, Lighthouse JSON or pasted console output, analyze that directly; `build_report.py --lighthouse` accepts Lighthouse JSON.

### 3. Run the audit
```bash
# one-time setup (skip what is already installed)
npm i playwright axe-core && npx playwright install chromium
# in the claude.ai sandbox Chromium already exists; install axe-core with:
#   npm i axe-core --prefix /tmp/axe && export NODE_PATH=/tmp/axe/node_modules:/home/claude/.npm-global/lib/node_modules

node scripts/audit.mjs <url> --out audit.raw.json [--device mobile] [--throttle slow4g] [--wait 3000] [--screenshot shot.png]
```
Run desktop and mobile when the user asks for a thorough check; mobile + `--throttle slow4g` exposes most real-world performance problems. If `axe-core` is missing the script says so in `meta.errors`; mention that limitation in the reply.

### 4. Build the report
```bash
python3 scripts/build_report.py audit.raw.json --out-dir audit-out --label "<site or customer name>" [--lighthouse lh.json]
```
Produces `report.json` (agents), `report.md` (Bangla, full), `telegram.txt` (<= 3800 chars) and `tower_payload.json` (ready arguments for `bridge_submit_patch`). Secrets are redacted at collection and again at build time. Read the findings yourself before sending: if the evidence points to a clear root cause (for example every failed request is the same CORS error), say so in the Bangla reply rather than just listing symptoms.

### 5. Deliver
Follow `references/delivery.md` for exact calls, limits and failure handling. In short:
1. Telegram: `notify_send_telegram` with the contents of `telegram.txt`.
2. MCP Tower: `bridge_submit_patch` with `tower_payload.json`.
3. Report honestly which deliveries succeeded; if one tool is unavailable or errors, give the user the generated files instead of claiming success.

### 6. Reply to the user
Reply in Bangla with technical terms in English. Keep it short: verdict, the 3 to 5 findings that matter most with the fix for each, what was delivered where, and anything the audit could not check (no axe, login not tested, site unreachable). If the user wants the fixes implemented, code changes go to `Supremeai-bd/supremeai-open` through the Tower bridge: call `bridge_guide` first and respect its diff caps and protected paths.

## Reading the numbers
Targets used for severity: LCP <= 2.5s, CLS <= 0.1, TTFB <= 800ms, FCP <= 3s, long-task blocking <= 300ms, DOM < 1500 nodes. Render free-tier backends often show high TTFB from cold starts; say that when TTFB is the outlier instead of blaming the frontend. A page that works on desktop but overflows horizontally on mobile is a responsive bug, not a performance one.

## Files
- `scripts/audit.mjs` - Playwright/CDP collector (console, network, vitals, coverage, DOM, axe, headers, cookie flags)
- `scripts/build_report.py` - findings engine and report/Telegram/Tower generators
- `references/delivery.md` - Telegram and Tower delivery contract
- `references/run-in-your-system.md` - run it locally, in GitHub Actions or on a schedule
