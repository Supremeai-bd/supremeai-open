import assert from "node:assert/strict";
import type { IncomingMessage } from "node:http";
import { autoRegisterGuestClient, detectProviderLabel } from "./src/policy/auto-register.js";
import { changeClientRole, listClients } from "./src/policy/client-registry.js";

/**
 * #2588 — vendor-agnostic auto-registration contract tests.
 *
 * Architecture under test (founder guidance): the tower accepts ANY AI by
 * TRANSPORT protocol alone (sse / streamable-http); provider labels from the
 * User-Agent are cosmetic. Every no-auth connect must leave a database
 * record with zero manual registration, and the record must follow the
 * client's latest transport.
 */

function fakeReq(userAgent: string, ip = "203.0.113.7"): IncomingMessage {
  return {
    headers: { "user-agent": userAgent, "x-forwarded-for": ip },
    socket: { remoteAddress: ip },
  } as unknown as IncomingMessage;
}

// 1. Signature label detection is best-effort cosmetics, never acceptance.
assert.equal(detectProviderLabel("Mozilla/5.0 Grok/1.0 xAI").provider, "xai");
assert.equal(detectProviderLabel("claude-web/2.1").provider, "claude");
assert.equal(detectProviderLabel("GeminiSpark custom-app").provider, "gemini");
assert.equal(detectProviderLabel("cursor/0.42 vscode-extension").provider, "cursor");
assert.equal(detectProviderLabel("ChatGPT-User/1.0").provider, "chatgpt");
assert.equal(detectProviderLabel("VS Code MCP Client").provider, "vscode");
assert.equal(detectProviderLabel("totally-unknown-bot/9").provider, "generic");

// 2. Zero-manual-registration: xAI Grok over /sse gets a database record.
const grokSse = autoRegisterGuestClient(fakeReq("Mozilla/5.0 Grok/1.0 xAI"), "sse");
assert.ok(grokSse.id.startsWith("guest_xai_"), `unexpected guest id: ${grokSse.id}`);
assert.equal(grokSse.provider, "xai");
assert.equal(grokSse.protocol, "sse");
assert.equal(grokSse.status, "active");
// #3663 (P0 root-cause): guests are born viewer with viewer scopes — the
// pre-production "admin" default was the unauthenticated global-admin hole.
assert.equal(grokSse.role, "viewer");
assert.deepEqual(grokSse.scopes, defaultClientScopes("viewer"));
assert.ok(!grokSse.scopes.includes("*"), "guest scopes must never be omni");

// 3. Idempotency: the same client reconnecting reuses its record.
const grokAgain = autoRegisterGuestClient(fakeReq("Mozilla/5.0 Grok/1.0 xAI"), "sse");
assert.equal(grokAgain.id, grokSse.id);

// 4. Cross-protocol reconnect: the registry follows the latest transport.
const grokHttp = autoRegisterGuestClient(fakeReq("Mozilla/5.0 Grok/1.0 xAI"), "streamable-http");
assert.equal(grokHttp.id, grokSse.id);
assert.equal(grokHttp.protocol, "streamable-http");

// 5. Unknown vendors register too (generic label) — protocol-driven acceptance.
const unknownAi = autoRegisterGuestClient(fakeReq("FutureAI-9000/0.1"), "streamable-http");
assert.equal(unknownAi.provider, "generic");
assert.ok(unknownAi.id.startsWith("guest_generic_"));
assert.equal(unknownAi.protocol, "streamable-http");
assert.equal(unknownAi.status, "active");

// 6. Same provider family + same IP (different UA version) still reuses; a
//    different IP gets a distinct record (per-IP guest identity preserved).
const grokNewerUa = autoRegisterGuestClient(fakeReq("Grok/2.0 xAI"), "sse");
assert.equal(grokNewerUa.id, grokSse.id);
const grokDifferentIp = autoRegisterGuestClient(fakeReq("Grok/2.0 xAI", "198.51.100.9"), "sse");
assert.notEqual(grokDifferentIp.id, grokSse.id);

// 7. Admin visibility: every auto-registered guest shows up in client_list.
const listed = listClients("*");
assert.ok(listed.some((c) => c.id === grokSse.id), "auto-registered guest missing from client_list");
assert.ok(listed.some((c) => c.id === unknownAi.id), "generic guest missing from client_list");


// ── #110 Part 2: Named Client Identity (?client=<name>) ──────────────────
// বাংলা মন্তব্য: URL প্যারামিটার থেকে named identity — টোকেন ছাড়া স্থায়ী পরিচয়।
import { namedClientFromUrl, isValidClientName } from "./src/policy/auto-register.js";

// 1. URL parsing: valid names, absent param, invalid chars, weird URLs.
assert.equal(namedClientFromUrl("/mcp?client=groq_main")?.id, "named_groq_main");
assert.equal(namedClientFromUrl("/mcp?client=groq_main")?.name, "groq_main");
assert.equal(namedClientFromUrl("https://tower.onrender.com/mcp?client=claude.web-01&x=1")?.id, "named_claude.web-01");
assert.equal(namedClientFromUrl("/mcp"), null, "no param must yield null");
assert.equal(namedClientFromUrl(undefined), null, "undefined URL must yield null");
assert.equal(namedClientFromUrl("/mcp?client="), null, "empty name must yield null");
assert.equal(namedClientFromUrl("/mcp?client=../etc/passwd"), null, "path traversal must be rejected");
assert.equal(namedClientFromUrl("/mcp?client=%2e%2e%2fwin"), null, "encoded traversal must be rejected");
assert.equal(namedClientFromUrl("/mcp?client=has space"), null, "spaces must be rejected");
assert.equal(namedClientFromUrl("/mcp?client=" + "a".repeat(65)), null, "65-char name must be rejected");
assert.ok(isValidClientName("groq_main") && isValidClientName("A.b-9"));
assert.ok(!isValidClientName("-leading-dash"));

// 2. Zero-token persistent identity: ?client= binds named_<name>, not IP.
function namedReq(url: string, ip: string): IncomingMessage {
  return {
    url,
    headers: { "user-agent": "Mozilla/5.0 Grok/1.0 xAI", "x-forwarded-for": ip },
    socket: { remoteAddress: ip },
  } as unknown as IncomingMessage;
}
changeClientRole("named_grok_prod", "admin");
const namedFromIpA = autoRegisterGuestClient(namedReq("/mcp?client=grok_prod", "203.0.113.10"), "streamable-http");
assert.equal(namedFromIpA.id, "named_grok_prod", "named identity must win over IP guest id");
assert.equal(namedFromIpA.status, "active");
assert.equal(namedFromIpA.role, "admin");

// 3. IP-DRIFT IMMUNITY (the issue's core scenario): the SAME ?client= name
//    reconnecting from a COMPLETELY different egress IP reuses the SAME
//    record — role upgrades survive.
const namedFromIpB = autoRegisterGuestClient(namedReq("/mcp?client=grok_prod", "198.51.100.77"), "sse");
assert.equal(namedFromIpB.id, "named_grok_prod");
assert.equal(namedFromIpB.provider, "xai");
assert.equal(namedFromIpB.protocol, "sse"); // follows latest transport
const listedNamed = listClients("*").find((c) => c.id === "named_grok_prod");
assert.ok(listedNamed, "named record must be listed for admin dashboards");

// 4. Invalid/absent client name degrades to the legacy IP-guest path.
const fallback = autoRegisterGuestClient(namedReq("/mcp?client=bad%20name", "203.0.113.99"), "streamable-http");
assert.ok(fallback.id.startsWith("guest_xai_"), `invalid name must fall back to guest id: ${fallback.id}`);
const noParam = autoRegisterGuestClient(namedReq("/mcp", "203.0.113.100"), "streamable-http");
assert.ok(noParam.id.startsWith("guest_xai_"));

console.log("auto-register contract tests passed");
