# Web Bot Auth Explorer-Lane Probe — Measured Evidence (WO #1675, Job 479095)

**Dispatch:** continuous agent loop → pick_next_issue() → #1675 (P1-high, repo:browser), claimed 2026-10-28T01:58:48Z (GRANT_NEW), renewed 02:36:10Z.
**Scope:** Explorer lane only — a zero-new-dependency Python probe that (1) reproduces the IETF Web Bot Auth test vectors offline, (2) exercises the full keygen → directory → sign → verify lifecycle, and (3) verifies a live signed request against the Cloudflare Research endpoint. No runtime behavior of the browser satellite is changed.
**Method:** every number below is a measured tool/script output from 2026-10-28T02:05–02:38Z, never an assumption. Artifact: `browser/scripts/webbotauth/probe.py` (`--help` for stages), tests: `browser/tests/test_webbotauth_probe.py`.

## সারসংক্ষেপ (বাংলা)

প্রোবটি IETF Web Bot Auth খসড়ার (draft-ietf-webbotauth-httpsig-protocol-00) Ed25519 টেস্ট ভেক্টর দুটি **বাইট-ইক্যাক্ট** পুনরুৎপাদন করেছে (E.2.1 রিকোয়েস্ট সিগনেচার ও E.2.3 সাইনড ডিরেক্টরি রেসপন্স) — অর্থাৎ আমাদের বাস্তবায়ন ক্রিপ্টোগ্রাফিকভাবে সঠিক। Cloudflare Research-এর লাইভ ভেরিফায়ারে আমাদের সাইন করা রিকোয়েস্ট **"valid"** ভার্ডিক্ট পেয়েছে। সাথে দুটি বাস্তব আবিষ্কার: (১) লাইভ সার্ভার পুরনো http-message-sig 0.2.0 চালায়, তাই RFC 9421 §2.1.2-অনুযায়ী সাইন করলে সে প্রত্যাখ্যান করে — সংস্করণ-বিভ্রাট (version skew); (২) খসড়ার নিজস্ব E.2.3 ভেক্টরে `content-digest` অসামঞ্জস্যপূর্ণভাবে unquoted — খসড়া-ভেক্টর ত্রুটি। দুটোই নিচে প্রমাণসহ নথিভুক্ত।

## 1. What the probe does (architecture, zero new deps)

`browser/scripts/webbotauth/probe.py` is self-contained: stdlib + `cryptography` (already declared in `browser/pyproject.toml` — zero new dependencies). Stages:

| Stage | Network | What it proves |
|---|---|---|
| `selftest` | no | Byte-exact reproduction of draft E.2.1 (request signature) and E.2.3 (signed directory response) Ed25519 vectors; RFC 8037 A.3 JWK thumbprint |
| `keygen` | no | Fresh Ed25519 keypair; `kid` == JWK thumbprint; private material never persisted |
| `directory` | no | JWKS directory body (draft §5.5.1: `kty/crv/kid/x/use/nbf/exp`) + Appendix B possession proof (`("@authority";req "content-digest")`, `tag="http-message-signatures-directory"`) + Content-Digest (RFC 9530) |
| `loopback` | no | Full sign→verify cycle covering `("@authority" "@method" "@path" "signature-agent";key="sig1")`; tamper any byte → verify flips false (test-enforced) |
| `live` | yes | Directory fetch from the Research origin + signed GET to its `/v0/api/verify` endpoint, in two serialization modes (see §3) |

Protocol elements implemented per draft: `Signature-Input`/`Signature` (RFC 9421) with `created/expires/keyid/alg/nonce/tag="web-bot-auth"` (§5.2), `Signature-Agent` dictionary form with `type=directory` (§5.2.1), 5-minute expiry (≤ 24 h RECOMMENDED), 64-byte base64 nonce (reference-implementation shape).

## 2. Offline results (deterministic, byte-exact)

Final full run 2026-10-28T02:37:59Z, `probe.py all` exit 0, overall `pass: true`:

- E.2.1 signature base reconstructed exactly as printed in the draft; Ed25519 signature `CGokAoY/FrPpyuzTe1Fb2kLTAH9Idw6qSFd1+D77r1firsMRCxeuLu5e6O+ek3zQgDMAzjiXtLVfqE00xnABCQ==` matches the draft's expected value **byte-for-byte**.
- E.2.3 directory bytes hash to `sha-256=:CADMT2aBdV/rqQr/NIru64ERQkCobVvllA4V0fLFDu0=:` (matches), response signature `l6P8R67tm3kujAxbHWio7ll01qrEZ0dKD/WWlGhNYEmTnFZM8Wt0VQ9zqGfvo7T/UMkBxsigzChM1Gpz7gOVBg==` (matches byte-for-byte). The same proof also verifies under the normative all-string serialization.
- Test key thumbprint: x=`JrQLj5P_89iXES9-vFgrIy29clF9CC_oPPsw3c5D0bs` → `poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U` (matches the draft keyid — RFC 8037 A.3 canonical JSON, SHA-256, base64url-nopad).
- pytest: `browser/tests/test_webbotauth_probe.py` → **9 passed, 1 skipped** (the live test is opt-in via `SUPREMEAI_WBA_LIVE=1`; CI must not depend on an external endpoint).

## 3. Live results and the interop matrix (key finding)

Live endpoint: `https://http-message-signatures-example.research.cloudflare.com` (the draft's own demonstration deployment; directory served as `application/http-message-signatures-directory+json`).

1. `GET /.well-known/http-message-signatures-directory` → HTTP 200, media type correct, exactly one key with kid `poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U` — the published RFC 9421 test key.
2. Signed `GET /v0/api/verify` (the worker's plain-text verdict endpoint) with our Ed25519 request signature covering `("@authority" "@method" "@path" "signature-agent";key="sig1")`:

| Base style for the `signature-agent;key=` component | Live verdict |
|---|---|
| **RFC-correct** — dictionary member value `"https://…"` (RFC 9421 §2.1.2; draft E.2.1; http-message-sig 0.3.0 `extractComponentValue`) | `invalid: invalid signature` |
| **Legacy** — FULL `Signature-Agent` field value `sig1="https://…"` (http-message-sig 0.2.0 `extractHeader`, which has no dictionary-member extraction) | **`valid`** |

**Finding F1 (deployment version skew).** The deployed Research verifier rejects a signature built exactly per RFC 9421 §2.1.2 and the draft's own E.2.1 vector, and accepts one built per http-message-sig 0.2.0's legacy full-field-value behavior. We pinned this by error-message fingerprinting: the live failure `Failed to parse component … in component list: type is not string` exists only in http-message-sig **0.2.0** (absent from 0.0.x and 0.3.0). Impact: the demo server currently fails the draft's own E.2.1 vector. Resolution belongs upstream (upgrade the worker to 0.3.0+ / current `web-bot-auth` npm); our probe supports both modes and records the matrix honestly instead of hiding it.

**Finding F2 (draft-vector inconsistency).** Draft E.2.3 prints `content-digest` unquoted (sf-token) inside the `@signature-params` inner list, while RFC 9421 §2.3 step 3 normatively serializes covered component identifiers as an Inner List of **String values** (all quoted), RFC 9421 B.2.6 quotes all identifiers, and the draft's own E.2.1 quotes `signature-agent`. We reproduce the E.2.3 vector verbatim (it is self-consistent, so it verifies) but ship only the normative all-string serializer for production paths. Worth an upstream draft issue.

## 4. Adoption read for supremeai-browser

The WO asked whether a web-bot-auth lane is viable. Measured answer: **yes, technically trivial and dependency-free** — key generation, directory hosting format, request signing, and verification all work with the satellite's existing `cryptography` dependency; no Playwright/network-stack changes needed. The binding constraint is operational, not technical: an in-federation lane is only useful once the federation publishes a directory at a stable HTTPS origin (the probe's `directory` stage produces exactly the artifact that deployment needs), and preferential treatment only materializes at verifiers (Cloudflare/Akamai/Vercel/HUMAN today). Per the WO's own honesty clause: identity ≠ access; the stealth plane remains necessary for non-verifying destinations. This probe deliberately changes no runtime behavior; step 2 of the WO's adoption path (optional signing mode in the stealth fetch adapter) is deliberately NOT attempted here — it would be scope creep without a production directory origin to point `Signature-Agent` at.

## 5. Reflection Evidence (why + alternatives_rejected)

- **why:** The loop dispatched #1675 (P1-high). The WO's step 1 explicitly asks for a signing probe with measured results filed back as evidence. U4 (3-tier verify) requires the evidence chain to be reproducible, so the probe self-certifies against IETF test vectors (deterministic) before any live call, and the live stage records both interop modes rather than a single convenient verdict (NO Ghost Fixes: we did not stop at the first "valid" — the earlier loose keyword classification would have mislabeled the invalid page as valid; the exact verdict strings from the worker templates replaced it).
- **alternatives_rejected:**
  1. *Pure-Python Ed25519 embedded in the probe* — rejected: `cryptography>=41.0` is already a declared satellite dependency; vendoring ~150 lines of crypto would add audit surface for zero benefit (zero NEW deps achieved either way).
  2. *Ship only the RFC-correct mode and report the live server as "broken"* — rejected: unactionable finger-pointing; shipping both modes with the matrix gives upstream an exact repro and keeps our verifier interop honest (a verifier we build will meet 0.2.0-era deployments in the wild).
  3. *Implement step 2 (signing mode inside the stealth fetch adapter) in the same WO* — rejected: no production directory origin exists yet, and bundling would violate cohesive task sizing (Rule P7); the probe's `directory` stage emits the deployable artifact instead.
  4. *File the two upstream findings as separate SupremeAI issues* — rejected: they are upstream (IETF draft / Cloudflare Research) defects, not SupremeAI codebase defects; filing them here would create unclaimable ticket noise. They are documented in this evidence artifact with exact repros instead.
  5. *Skip the pytest file (probe self-validates)* — rejected: CI runs `browser/tests`; the vector tests make the probe's correctness regression-proof without network.

## 6. Test Evidence (3-tier contract)

1. **Reflection** — this document §5 (why + 5 alternatives_rejected).
2. **Boot smoke** — MCP tower handshake OK (sessions re-established during this cycle: `6fa610f7…`, `0e8d9a75…`); `probe.py all` exit 0 (all 5 stages PASS, run 2026-10-28T02:37:59Z); live directory fetch + signed verify captured in the same run; `pytest browser/tests/test_webbotauth_probe.py` → 9 passed / 1 skipped / 0 failed.
3. **Tests** — 3 new files (probe, tests, this evidence doc), ~19 KB total — far under the 30-file / 200 KB bridge caps; zero source/runtime/CI surface touched; no protected paths (`browser/scripts/webbotauth/`, `browser/tests/`); no secrets (the embedded RFC 9421 key is a published public test fixture, labeled as such; freshly generated private keys exist only in process memory and are never persisted or printed).

## 7. Rollback Path

git revert-safe: three additive files, zero modifications to existing files. Reverting removes the probe, its tests, and this evidence doc; nothing else references them (no imports wired into the satellite runtime), so removal is behaviorally silent.
