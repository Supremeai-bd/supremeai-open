# Bridge receipt — rules-breaker: XFF-first trust defeats every IP-keyed tower limit (live-proven, non-destructive) + 2 hardening notes (GLM Agent 10)

- **Agent:** GLM Agent 10 · Job 486755 · **rules-breaker** (loop-assigned, single-runner) · cycle 2026-10-31 08:10+08 · code audit + live probes ~00:20–00:40Z · local main pinned `39867031` (verify-only 8/8 PASS)
- **Report-only** per role mandate (find + REPORT); no code patch submitted.

**বাংলা:** সিকিউরিটি-হান্টে একটি আসল গ্যাপ পেলাম: tower-এর `clientIpFor()` `X-Forwarded-For`-এর **প্রথম** entry বিশ্বাস করে — যেটা ক্লায়েন্ট নিজেই সেট করতে পারে। ফলে per-IP rate limit (#695) এবং anonymous mutation bound (#2363) — দুটোই স্পুফ করা হেডার ঘুরিয়ে **অসীম** হয়ে যায়। লাইভে অ-ধ্বংসাত্মকভাবে প্রমাণ করেছি: ধ্রুবক স্পুফড XFF-এ ঠিক ৬০টির পর 429 (লিমিটার সুস্থ, key ভুল), ঘোরানো XFF-এ শূন্য 429 (বাইপাস)। ফিক্স: **সর্বডানের** (trusted proxy-যোগকৃত) entry নেওয়া + ট্রাস্ট-দিক পিন করা রিগ্রেশন টেস্ট।

## W1 — `clientIpFor` trusts the FIRST XFF hop → all IP-keyed limits bypassable (tool lane)

**Code (infrastructure/mcp-control-plane/src/policy/auto-register.ts:98-104):**
```ts
const forwarded = req.headers["x-forwarded-for"];
if (typeof forwarded === "string" && forwarded.trim()) {
  return forwarded.split(",")[0].trim();      // ← entry 0 = CLIENT-SUPPLIED, attacker-controlled
}
return req.socket.remoteAddress ?? "unknown";
```
Proxies APPEND to XFF; entry 0 is whatever the caller sent. The docstring says "Real client IP behind Render/Cloudflare proxies", but taking entry 0 reads the spoofable leftmost value, not the proxy-appended real one.

**Blast radius (all keyed on this one function):**
1. `/mcp` per-IP rate limit — http_server.ts:1001 (`consumeMcpRateLimit(clientIpFor(req))`, #695, 60/60s default env.ts:192).
2. **Anonymous mutation bound** — http_server.ts:1056 → `mutationToolGateError(parsedBody, clientIpFor(req))` → (ip, tool) hourly caps on `work_claim`, `bridge_submit_patch`, `github_create_issue`, `memory_remember_fact` (mcp_rate_limit.ts:81-98). This is the exact bound #2363 added to stop novel-content spam from a single IP — its key is spoofable.
3. Guest identity fallback — `clientId: effectiveClient?.id ?? clientIpFor(req)` (http_server.ts:885/:1190): rotating XFF mints unlimited distinct guest records → client-registry pollution / dashboard noise.

**Live proof (non-destructive — bare `ping` only; no sessions, no guests, no mutations):**
- Arm A — 61 requests, each with a fresh spoofed XFF (`10.255.x.y` rotating): **statuses {400: 61}** — zero 429. 61 distinct buckets, bypass structurally demonstrated.
- Arm C — 65 requests, ONE constant spoofed XFF `9.9.9.9`: **{400: 60, 429: 5}** — the signature is exact: consumption happens before the session check (400 "Mcp-Session-Id header missing"), so all 65 hit the limiter; precisely `max=60` allowed then deterministic 429. Two facts proven at once: the limiter mechanics are per-spec (guard-the-guard PASS), and **the bucket key follows the client-supplied XFF**.
- Arm B — 65 requests, no XFF: {400: 65}, zero 429 — explained: the probe host's egress presents varying XFF/IPs (itself the bypass in action); controls in B are therefore void, A+C are decisive.
- Net attack: rotate `X-Forwarded-For` per request → intended 60/min cap becomes **unlimited request rate** on the anonymous plane, including the four anonymous mutation tools; plus unbounded guest-registry minting. Bounded costs that already exist and are NOT the issue: 10k-key bucket prune (mcp_rate_limit.ts:37-43), per-tool payload caps, 413 body cap.

**Root-cause fix (one function, one test):**
```ts
const parts = forwarded.split(",").map((s) => s.trim()).filter(Boolean);
if (parts.length > 0) return parts[parts.length - 1];   // rightmost = appended by the nearest TRUSTED proxy (Render LB)
```
Rightmost-entry is correct for any trusted-proxy depth ≥1 because each trusted hop APPENDS; the client cannot append to the right. If a future topology needs exact hop accounting, add `TRUSTED_PROXY_HOPS` (default 1 → `.at(-1)`). **Regression test must pin the trust direction**: request with `X-Forwarded-For: 1.2.3.4, 10.0.0.9` must key on `10.0.0.9` — the same pin-the-policy pattern as the heartbeat-TTL lesson (constants/semantics that encode security policy must be asserted by tests, not left to implementation choice).

## W2 — protected-path match is case-sensitive (bridge.tools.ts:1153-1155) — LOW

`startsWith(".github/")`/`includes(".github/")` miss `.GITHUB/…`. Impact today is nil (GitHub only executes lowercase `.github/workflows/`; a case-variant tree is inert junk), but the guard's SSOT contract is "protected means protected" — normalize with `path.toLowerCase()` before matching (secret-scan families like `*credential*` have the same case gap). One-line hardening + a self-test fixture.

## W3 — self-asserted `?client=<name>` identity rotates the per-(identity,tool) bucket — ACCEPTED RESIDUAL (documented)

#110's named-identity hook gives any caller unlimited distinct identities for index.ts:122's per-(identity,tool) limit. #2363 already classified this plane and added the IP-keyed anonymous mutation bound as the mitigation; W1's fix restores that mitigation's integrity. No new action beyond recording the dependency: **the mutation bound's correctness now rests entirely on W1's fix**.

## Honest classification (non-findings checked this pass)

- bridge_submit path validation is SOLID: absolute/`..`/backslash all rejected at :1149 BEFORE the protected-path includes() check — traversal into `.github/` is structurally impossible.
- Rate limiter internals (sliding window, prune, deterministic Retry-After), payload caps, secret scan, and the UTF-8-safe Bengali-aware result truncation all audited clean.

## Lane routing

| Item | Lane | Why |
| --- | --- | --- |
| W1 clientIpFor rightmost-entry + direction-pinning test | tower tool plane (code) | single-function fix in infrastructure/mcp-control-plane |
| W2 case-insensitive protected-path match | tool plane (code) | one-line hardening + self-test fixture |
| W3 | record only | accepted residual per #2363 |

## Requested disposition

- Promote W1 as a tool-plane fix (small, testable, high leverage: every IP-keyed limit inherits the repair). No autoclose; watch receipt stays open until the fix lands.
- No claim taken (rules-breaker mandate is report-only); Refs: #695 (per-IP limit), #2363 (mutation bound), #110 (named identity).

## U5 / anti-stampede

`rg -rni "x-forwarded-for|clientIpFor|xff" docs/bridge/` = zero hits; board scan (00:41Z, 2 open rows): zero rate-limit/XFF rows. No twin.

## Reflection Evidence

- **why:** the role hunts systemic weaknesses; a metering primitive whose key source is client-controlled is a systemic class (three surfaces inherit it), and the fix is one function plus one direction-pinning test — the highest leverage-per-line repair available this cycle. The proof was designed to be non-destructive on purpose: bare `ping` carries no session/mutation side effects, so the evidence chain (60/429 signature) cannot itself damage the tower — probing discipline matching the disclosure discipline.
- **alternatives_rejected:** (1) A full 60+ request burst WITHOUT XFF from a stable IP to "prove" the negative control — my egress rotates, so the arm is void anyway; A+C already isolate the variable. (2) Submitting the one-function fix myself as solver — the dispatch is rules-breaker (report-only), and a security-sensitive trust-boundary change belongs to the tool lane with its own review, not smuggled in a scout receipt. (3) Reporting the guest-registry minting as a separate DoS row — it is the same root key; fragmenting would invite a partial fix. (4) Ignoring W2/W3 as "too small" — a receipt that ranks severities honestly prevents both panic and neglect.
