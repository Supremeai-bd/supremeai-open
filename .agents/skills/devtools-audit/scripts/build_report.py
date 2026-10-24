#!/usr/bin/env python3
"""Turn audit.raw.json (from audit.mjs) into deliverables:

  report.json       machine-readable findings (stable rule ids) - for agents / MCP Tower
  report.md         Bangla report (technical terms stay in English)
  telegram.txt      short Bangla summary, <= 3800 chars (Telegram limit is 4096)
  tower_payload.json  arguments ready for the Tower's bridge_submit_patch tool

Usage: build_report.py audit.raw.json [--out-dir out] [--lighthouse lh.json] [--label "Customer X"]
"""
import argparse, json, re, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

SEV = ["critical", "high", "medium", "low", "info"]
ICON = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}
SECRET_RE = re.compile(r"(?:ghp_|ghs_|github_pat_|sk-|AKIA|xox[a-z]-|AIza)[A-Za-z0-9_\-]{8,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}|Bearer\s+[A-Za-z0-9._\-]{10,}|-----BEGIN [A-Z ]+-----")


def scrub(obj):
    """Defense in depth: redact secret-looking strings anywhere in the structure."""
    if isinstance(obj, str):
        return SECRET_RE.sub("[REDACTED]", obj)
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items()}
    return obj


def short(url, n=90):
    return url if len(url) <= n else url[: n - 1] + "…"


def kb(b):
    return f"{(b or 0) / 1024:.0f}KB"


def build_findings(raw, lh=None):
    f = []

    def add(rule, sev, area, title, detail, fix, evidence=None):
        f.append({"id": rule, "severity": sev, "area": area, "title": title, "detail": detail, "fix": fix, "evidence": evidence or []})

    meta, net, perf, dom = raw.get("meta", {}), raw.get("network", {}), raw.get("performance", {}), raw.get("dom") or {}
    if meta.get("status") is None:
        add("nav.failed", "critical", "navigation", "Page load-ই হয়নি", "Navigation failed বা timeout হয়েছে", "URL, DNS, TLS ও server availability check করুন", meta.get("errors", [])[:3])
    elif meta["status"] >= 400:
        add("nav.http-error", "critical", "navigation", f"Main document HTTP {meta['status']} দিচ্ছে", "Page-এর main request fail করেছে", "Route/deploy/auth ঠিক আছে কিনা দেখুন")
    if str(meta.get("target", "")).startswith("http://"):
        add("sec.no-https", "medium", "security", "Site HTTPS-এ serve হচ্ছে না", "Plain HTTP ব্যবহার হচ্ছে", "HTTPS enforce করুন ও HSTS চালু করুন")

    # errors
    for e in raw.get("pageErrors", [])[:10]:
        add("js.uncaught-exception", "high", "console", "Uncaught JavaScript exception", e.get("message", ""), "Stack trace অনুযায়ী source ঠিক করুন; Error Boundary/try-catch যোগ করুন", [e.get("stack", "")])
    errs = [m for m in raw.get("console", []) if m.get("type") == "error"]
    if errs:
        add("console.errors", "high" if len(errs) > 5 else "medium", "console", f"Console-এ {len(errs)}টি error", "; ".join(short(m["text"], 100) for m in errs[:3]), "প্রতিটি error-এর উৎস খুঁজে ঠিক করুন; production build-এ console clean রাখুন", [f"{short(m['url'],60)}:{m.get('line')}" for m in errs[:5]])
    warns = [m for m in raw.get("console", []) if m.get("type") == "warning"]
    if len(warns) > 10:
        add("console.warnings", "low", "console", f"Console-এ {len(warns)}টি warning", "; ".join(short(m["text"], 80) for m in warns[:2]), "Deprecation ও React/Vue dev warning পরিষ্কার করুন")
    for l in raw.get("browserLogs", []):
        if re.search(r"mixed content|content security policy|refused to|blocked", l.get("text", ""), re.I):
            add("browser.policy-violation", "high", "security", "Browser security policy violation", short(l["text"], 200), "Mixed content/CSP rule ঠিক করুন", [l.get("url", "")])
            break

    # network
    failed = net.get("failed", [])
    cors = [r for r in failed if r.get("cors")]
    five = [r for r in failed if (r.get("status") or 0) >= 500]
    four = [r for r in failed if 400 <= (r.get("status") or 0) < 500]
    neterr = [r for r in failed if r.get("failed") and not r.get("cors")]
    if cors:
        add("net.cors-blocked", "high", "network", f"{len(cors)}টি request CORS-এ block", f"{short(cors[0]['url'])} ({cors[0]['cors']})", "Backend-এ frontend origin allow করুন (CORS_ORIGINS); credentials ব্যবহার করলে wildcard নয়, নির্দিষ্ট origin দিন", [short(r["url"]) for r in cors[:5]])
    if five:
        add("net.server-errors", "high", "network", f"{len(five)}টি request 5xx দিচ্ছে", f"{five[0]['method']} {short(five[0]['url'])} → {five[0]['status']}", "Backend log দেখুন; ওই endpoint fix/health check করুন", [f"{r['status']} {short(r['url'])}" for r in five[:6]])
    if four:
        add("net.client-errors", "medium", "network", f"{len(four)}টি request 4xx দিচ্ছে", f"{four[0]['method']} {short(four[0]['url'])} → {four[0]['status']}", "ভুল URL/missing asset/auth token ঠিক করুন (404=missing file, 401/403=auth)", [f"{r['status']} {short(r['url'])}" for r in four[:6]])
    if neterr:
        add("net.request-failed", "high", "network", f"{len(neterr)}টি request network-level-এ fail", f"{short(neterr[0]['url'])} ({neterr[0]['error']})", "DNS/TLS/ad-blocker/timeout কারণ খুঁজুন", [f"{r['error']} {short(r['url'])}" for r in neterr[:6]])
    if net.get("slow"):
        s = net["slow"][0]
        add("net.slow-requests", "medium", "network", f"{len(net['slow'])}টি request ১.৫ সেকেন্ডের বেশি সময় নিচ্ছে", f"সবচেয়ে slow: {short(s['url'])} ({s['ms']}ms)", "Backend query/caching/CDN দেখুন; অপ্রয়োজনীয় request বাদ দিন বা lazy load করুন", [f"{r['ms']}ms {short(r['url'])}" for r in net["slow"][:5]])
    if net.get("large"):
        b = net["large"][0]
        add("net.large-assets", "medium", "performance", f"{len(net['large'])}টি asset ৫০০KB-র বেশি", f"সবচেয়ে বড়: {short(b['url'])} ({kb(b['bytes'])})", "Image WebP/AVIF-এ convert, code-splitting ও compression করুন", [f"{kb(r['bytes'])} {short(r['url'])}" for r in net["large"][:5]])
    if net.get("totalBytes", 0) > 3 * 1024 * 1024:
        add("net.heavy-page", "medium", "performance", f"Page weight {kb(net['totalBytes'])}", "মোট transfer ৩MB-র বেশি", "Bundle size কমান, unused dependency সরান")
    if net.get("uncompressedText"):
        add("net.no-compression", "medium", "performance", f"{len(net['uncompressedText'])}টি text asset compress করা নেই", short(net["uncompressedText"][0]["url"]), "Server/CDN-এ gzip বা brotli চালু করুন", [short(r["url"]) for r in net["uncompressedText"][:5]])

    # perf (Core Web Vitals)
    lcp, cls, fcp, ttfb, lt = perf.get("lcp"), perf.get("cls"), perf.get("fcp"), perf.get("ttfb"), perf.get("longTaskTotal")
    if lcp is not None and lcp > 2500:
        add("perf.lcp", "high" if lcp > 4000 else "medium", "performance", f"LCP {lcp/1000:.1f}s (লক্ষ্য ≤ 2.5s)", "সবচেয়ে বড় content দেরিতে দেখা যাচ্ছে", "Hero image preload/optimize, render-blocking resource কমান, server response দ্রুত করুন")
    if cls is not None and cls > 0.1:
        add("perf.cls", "high" if cls > 0.25 else "medium", "performance", f"CLS {cls:.2f} (লক্ষ্য ≤ 0.1)", "Layout লাফাচ্ছে", "Image/iframe-এ width-height বা aspect-ratio দিন; font-display ও dynamic content-এর জন্য জায়গা reserve করুন")
    if fcp is not None and fcp > 3000:
        add("perf.fcp", "medium", "performance", f"FCP {fcp/1000:.1f}s", "প্রথম content আসতে দেরি", "Render-blocking CSS/JS কমান, critical CSS inline করুন")
    if ttfb is not None and ttfb > 800:
        add("perf.ttfb", "medium", "performance", f"TTFB {ttfb:.0f}ms (লক্ষ্য ≤ 800ms)", "Server response ধীর (Render free tier cold start হতে পারে)", "Caching/CDN, keep-alive ping বা server optimization দেখুন")
    if lt and lt > 300:
        add("perf.long-tasks", "medium", "performance", f"Main thread {lt}ms block হয়েছে (long tasks)", "Heavy JavaScript UI আটকে দিচ্ছে", "Code-splitting, heavy কাজ Web Worker-এ নিন, অপ্রয়োজনীয় JS সরান")

    cov = raw.get("coverage") or {}
    for kind in ("js", "css"):
        c = cov.get(kind) or {}
        if c.get("unusedBytes", 0) > 100 * 1024 and c.get("unusedPct", 0) > 50:
            add(f"perf.unused-{kind}", "low", "performance", f"{kind.upper()}-এর {c['unusedPct']}% ({kb(c['unusedBytes'])}) unused", "Initial load-এ যা লাগে না তাও download হচ্ছে", "Route-based code splitting ও tree-shaking করুন" if kind == "js" else "Unused CSS purge করুন", [f"{kb(x['unused'])} unused: {short(x['url'])}" for x in c.get("top", [])[:3]])

    # DOM / SEO / a11y basics
    axe_ran = raw.get("axe") is not None
    if dom:
        if dom.get("nodes", 0) > 3000:
            add("dom.size", "high", "dom", f"DOM-এ {dom['nodes']}টি node", "খুব বড় DOM rendering ধীর করে", "Virtualization/pagination ব্যবহার করুন")
        elif dom.get("nodes", 0) > 1500:
            add("dom.size", "medium", "dom", f"DOM-এ {dom['nodes']}টি node", "DOM বড় হয়ে যাচ্ছে", "List virtualization ও component সরল করুন")
        im = dom.get("images", {})
        if im.get("missingAlt") and not axe_ran:
            add("a11y.img-alt", "medium", "accessibility", f"{im['missingAlt']}টি image-এ alt নেই", "Screen reader ও SEO-র জন্য alt দরকার", "অর্থপূর্ণ alt লিখুন (decorative হলে alt=\"\")")
        if im.get("noDimensions", 0) > 0 and im.get("total", 0):
            add("perf.img-dimensions", "low", "performance", f"{im['noDimensions']}টি image-এ width/height নেই", "Layout shift-এর কারণ", "width ও height attribute দিন")
        if im.get("oversized"):
            add("perf.oversized-images", "medium", "performance", f"{len(im['oversized'])}টি image প্রয়োজনের চেয়ে অনেক বড়", short(im["oversized"][0]["src"], 80), "Responsive srcset ও ছোট size serve করুন", [f"{o['natural']}px → {o['shown']}px {short(o['src'],60)}" for o in im["oversized"][:4]])
        if not dom.get("lang") and not axe_ran:
            add("a11y.html-lang", "medium", "accessibility", "<html> এ lang attribute নেই", "Screen reader ভাষা চিনতে পারে না", "<html lang=\"bn\"> বা সঠিক lang দিন")
        if not dom.get("title") and not axe_ran:
            add("seo.title", "medium", "seo", "Page title নেই", "", "অর্থপূর্ণ <title> দিন")
        if not dom.get("viewportMeta"):
            add("seo.viewport", "medium", "seo", "viewport meta নেই", "Mobile-এ ঠিকমতো দেখাবে না", "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"> দিন")
        if not dom.get("metaDescription"):
            add("seo.meta-description", "low", "seo", "meta description নেই", "", "Search result-এর জন্য description দিন")
        if dom.get("h1Count") != 1:
            add("seo.h1", "low", "seo", f"h1 আছে {dom.get('h1Count')}টি (১টি হওয়া উচিত)", "", "প্রতি page-এ একটাই h1 রাখুন")
        for key, rule, label in (("linksWithoutName", "a11y.link-name", "link"), ("buttonsWithoutName", "a11y.button-name", "button"), ("inputsWithoutLabel", "a11y.input-label", "input")):
            if dom.get(key) and not axe_ran:
                add(rule, "medium", "accessibility", f"{dom[key]}টি {label}-এর accessible name/label নেই", "", "Visible text, aria-label বা <label for> দিন")
        if dom.get("mixedContent"):
            add("sec.mixed-content", "high", "security", f"{dom['mixedContent']}টি http:// resource HTTPS page-এ", "Mixed content block হয়", "সব resource https করুন")
        if dom.get("horizontalOverflow"):
            add("ux.horizontal-overflow", "medium", "responsive", "Horizontal scroll হচ্ছে (content viewport-এর বাইরে যায়)", "", "overflow-causing element খুঁজে max-width: 100% দিন")
        if dom.get("renderBlockingScripts", 0) > 0:
            add("perf.render-blocking-js", "low", "performance", f"{dom['renderBlockingScripts']}টি render-blocking script", "", "defer/async ব্যবহার করুন")

    # axe
    rank = {"critical": "high", "serious": "high", "moderate": "medium", "minor": "low"}
    for v in (raw.get("axe") or [])[:15]:
        add(f"axe.{v['id']}", rank.get(v.get("impact"), "low"), "accessibility", f"{v['help']} ({v['count']} জায়গায়)", f"axe impact: {v.get('impact')}", f"axe rule `{v['id']}` অনুযায়ী ঠিক করুন (guide: {v.get('helpUrl','').split('?')[0]})", v.get("sample", [])[:2])

    # security headers & cookies
    sh = raw.get("securityHeaders", {})
    https = str(meta.get("finalUrl", "")).startswith("https://")
    if https and not sh.get("strict-transport-security"):
        add("sec.hsts", "low", "security", "HSTS header নেই", "", "Strict-Transport-Security header দিন")
    if not sh.get("content-security-policy"):
        add("sec.csp", "low", "security", "Content-Security-Policy নেই", "XSS ঝুঁকি কমানোর স্তর অনুপস্থিত", "ধাপে ধাপে CSP চালু করুন (report-only দিয়ে শুরু)")
    if not sh.get("x-content-type-options"):
        add("sec.nosniff", "low", "security", "X-Content-Type-Options নেই", "", "nosniff দিন")
    if not sh.get("x-frame-options") and "frame-ancestors" not in (sh.get("content-security-policy") or ""):
        add("sec.clickjacking", "low", "security", "Clickjacking protection নেই", "", "X-Frame-Options বা CSP frame-ancestors দিন")
    weak = [c for c in raw.get("cookies", []) if https and (not c.get("secure") or not c.get("httpOnly"))]
    if weak:
        add("sec.cookie-flags", "medium", "security", f"{len(weak)}টি cookie-তে Secure/HttpOnly নেই", ", ".join(c["name"] for c in weak[:5]), "Session/auth cookie-তে Secure, HttpOnly, SameSite দিন", [c["name"] for c in weak[:8]])

    # lighthouse (optional file from `npx lighthouse --output=json`)
    if lh:
        cats = {k: round((v.get("score") or 0) * 100) for k, v in lh.get("categories", {}).items()}
        low = [(k, s) for k, s in cats.items() if s < 90]
        for k, s in low:
            add(f"lighthouse.{k}", "high" if s < 50 else "medium", "lighthouse", f"Lighthouse {k}: {s}/100", "", "নিচের failed audit গুলো দেখুন")
        bad = [a for a in lh.get("audits", {}).values() if a.get("score") is not None and a["score"] < 0.9 and a.get("scoreDisplayMode") in ("numeric", "binary", "metricSavings")]
        bad.sort(key=lambda a: a["score"])
        for a in bad[:8]:
            add(f"lighthouse.audit.{a.get('id')}", "low", "lighthouse", a.get("title", ""), a.get("displayValue", "") or "", "Lighthouse suggestion অনুসরণ করুন")
    f.sort(key=lambda x: SEV.index(x["severity"]))
    return f


def verdict(counts):
    if counts["critical"] or counts["high"]:
        return "🔴", "জরুরি সমস্যা আছে"
    if counts["medium"]:
        return "🟡", "উন্নতি দরকার"
    return "🟢", "মোটামুটি ভালো"


def vitals_line(p):
    parts = []
    if p.get("ttfb") is not None: parts.append(f"TTFB {p['ttfb']:.0f}ms")
    if p.get("fcp") is not None: parts.append(f"FCP {p['fcp']/1000:.1f}s")
    if p.get("lcp") is not None: parts.append(f"LCP {p['lcp']/1000:.1f}s")
    if p.get("cls") is not None: parts.append(f"CLS {p['cls']:.2f}")
    return " · ".join(parts) or "n/a"


def to_markdown(label, raw, findings, counts, lh):
    meta, net, perf = raw["meta"], raw["network"], raw["performance"]
    ic, vt = verdict(counts)
    L = [f"# Frontend Audit Report: {label}", "", f"- **Target:** {meta['target']}", f"- **Device:** {meta['device']}" + (f" ({meta['throttle']})" if meta.get("throttle") else ""), f"- **সময়:** {meta['finishedAt']}", f"- **Browser:** {meta.get('browserVersion','')}", "", f"## ফলাফল: {ic} {vt}", "",
         "| Severity | সংখ্যা |", "|---|---|"] + [f"| {ICON[s]} {s} | {counts[s]} |" for s in SEV] + ["", "## মূল metrics", "",
         f"- Core Web Vitals: {vitals_line(perf)}", f"- Network: {net['total']}টি request, {kb(net['totalBytes'])} transfer, failed {len(net['failed'])}টি",
         f"- Console: error {len([m for m in raw['console'] if m['type']=='error'])}, page exception {len(raw['pageErrors'])}", f"- DOM nodes: {(raw.get('dom') or {}).get('nodes','n/a')}"]
    if lh:
        L.append("- Lighthouse: " + ", ".join(f"{k} {round((v.get('score') or 0)*100)}" for k, v in lh.get("categories", {}).items()))
    L += ["", "## Findings ও করণীয়", ""]
    if not findings:
        L.append("কোনো উল্লেখযোগ্য সমস্যা পাওয়া যায়নি।")
    for i, x in enumerate(findings, 1):
        L += [f"### {i}. {ICON[x['severity']]} {x['title']}", f"- **Area:** {x['area']} · **Rule:** `{x['id']}` · **Severity:** {x['severity']}"]
        if x["detail"]: L.append(f"- **বিস্তারিত:** {x['detail']}")
        L.append(f"- **Fix:** {x['fix']}")
        if x["evidence"]:
            L.append("- **Evidence:**"); L += [f"  - `{e}`" for e in x["evidence"][:5] if e]
        L.append("")
    if raw["meta"].get("errors"):
        L += ["## Audit চলাকালীন সীমাবদ্ধতা", ""] + [f"- {e}" for e in raw["meta"]["errors"]]
    return "\n".join(L) + "\n"


def to_telegram(label, raw, findings, counts):
    meta, net, perf = raw["meta"], raw["network"], raw["performance"]
    ic, vt = verdict(counts)
    lines = [f"{ic} Frontend Audit: {label}", f"🌐 {short(meta['target'], 70)}  ({meta['device']})", f"{vt} — 🔴{counts['critical']+counts['high']} 🟡{counts['medium']} 🔵{counts['low']}", f"⚡ {vitals_line(perf)}", f"📡 {net['total']} requests, failed {len(net['failed'])}, {kb(net['totalBytes'])}", "", "প্রধান সমস্যা ও fix:"]
    for x in [x for x in findings if x["severity"] in ("critical", "high", "medium")][:8]:
        lines.append(f"{ICON[x['severity']]} {x['title']}\n   ➜ {x['fix']}")
    rest = len(findings) - min(8, len([x for x in findings if x['severity'] in ('critical','high','medium')]))
    if rest > 0: lines.append(f"\n…আরও {rest}টি finding পূর্ণ report-এ আছে (MCP Tower)।")
    msg = "\n".join(lines)
    return msg if len(msg) <= 3800 else msg[:3790] + "…"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw"); ap.add_argument("--out-dir", default="audit-out"); ap.add_argument("--lighthouse"); ap.add_argument("--label")
    a = ap.parse_args()
    raw = scrub(json.loads(Path(a.raw).read_text(encoding="utf-8")))
    lh = json.loads(Path(a.lighthouse).read_text(encoding="utf-8")) if a.lighthouse else None
    host = urlparse(raw["meta"]["target"]).netloc or "site"
    label = a.label or host
    findings = build_findings(raw, lh)
    counts = {s: sum(1 for x in findings if x["severity"] == s) for s in SEV}
    now = datetime.now(timezone.utc)
    slug = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-")[:30] or "site"
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)

    report = scrub({"schema": "frontend-audit/v1", "label": label, "target": raw["meta"]["target"], "device": raw["meta"]["device"], "generatedAt": now.isoformat(), "counts": counts,
                    "verdict": verdict(counts)[1], "metrics": {"vitals": {k: raw["performance"].get(k) for k in ("ttfb", "fcp", "lcp", "cls", "longTaskTotal")}, "requests": raw["network"]["total"], "transferBytes": raw["network"]["totalBytes"], "failedRequests": len(raw["network"]["failed"]), "domNodes": (raw.get("dom") or {}).get("nodes")},
                    "findings": findings, "auditLimitations": raw["meta"].get("errors", [])})
    md = scrub(to_markdown(label, raw, findings, counts, lh))
    tg = scrub(to_telegram(label, raw, findings, counts))
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "report.md").write_text(md, encoding="utf-8")
    (out / "telegram.txt").write_text(tg, encoding="utf-8")

    base = f"reports/frontend-audit/{slug}/{now.strftime('%Y%m%d-%H%M')}"
    top = "; ".join(x["title"] for x in findings[:4])[:600]
    payload = {
        "taskId": f"bridge-{now.strftime('%Y%m%d')}-frontend-audit-{slug}",
        "summary": f"Frontend audit of {label}: {counts['critical']+counts['high']} high/critical, {counts['medium']} medium, {counts['low']} low findings. Top: {top}"[:1000],
        "files": [{"path": f"{base}.json", "content": json.dumps(report, ensure_ascii=False, indent=2)}, {"path": f"{base}.md", "content": md}],
        "scopePaths": [f"{base}.json", f"{base}.md"],
        "testsEvidence": f"Report-only submission (no source changes). Generated by Playwright {raw['meta'].get('browserVersion','Chromium')} audit: console, CDP network, Core Web Vitals, coverage, DOM/axe a11y, security headers. Tier1 reflection: findings carry rule ids + evidence. Tier2 boot smoke: target loaded status={raw['meta'].get('status')}. Tier3 tests: n/a (read-only audit).",
        "reflectionWhy": "Give other agents an instant, structured frontend health report (stable rule ids, severity, fix hints) so they can act without re-running the audit.",
        "alternativesRejected": "Telegram-only delivery (not machine-readable, 4096-char limit); raw HAR dump (large, may contain sensitive data, no prioritisation).",
        "agentIdentity": "claude-devtools-audit-skill",
    }
    (out / "tower_payload.json").write_text(json.dumps(scrub(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out_dir": str(out), "counts": counts, "files": ["report.json", "report.md", "telegram.txt", "tower_payload.json"], "telegram_chars": len(tg)}))


if __name__ == "__main__":
    sys.exit(main())
