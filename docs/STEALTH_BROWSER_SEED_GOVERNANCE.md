# supremeai-browser — Seed Governance & Apply Package (r2)

> **Why this doc exists (r2 hybrid lane):** the monorepo trunk already carries
> root `AGENTS.md` and `README.md`, so a new-file patch for those paths can
> never apply (measured: WO #546 rejected twice, `patch does not apply` on
> both). Their full contents therefore ship as the two byte-exact blocks
> below. Apply them ONCE into the `Supremeai-bd/supremeai-browser` satellite
> (which is 100% empty — zero collisions there) after the code files land.

## Block 1 — AGENTS.md (byte-exact)

````text AGENTS.md
# supremeai-browser — Agent Governance Constitution

## Superadmin Authority Mandate

This satellite is governed by the Superadmin Authority Mandate: the human
superadmin (via the supremeai-command control plane) holds final authority
over every push, merge, and runtime action performed inside this repository.
Autonomous agents are delegated workers; they never outrank the mandate.

## Two-Tier Ingress Invariant

Work enters this repository through exactly two gates, in strict order:

1. **No Claim → No Branch.** An agent must hold a verified claim (label plane
   `status:claimed` or an atomic-claim comment per S0.1 / Invariant #430) on
   an open work-order issue BEFORE creating any branch.
2. **No Branch → No Push.** A branch may only be pushed when it is bound to
   that claimed issue (TaskIssue token in the work order body), and only
   through the Bridge submission lane — never by direct credential push.

Violations are constitutional breaches, not style issues.

## Boundary Limits

- **Stdlib-only core.** `runtime/` imports the standard library only; heavy
  dependencies (playwright, lxml) are OPTIONAL execution-tier extras guarded
  by capability probes. Offline verification must always succeed.
- **No network in tests.** The verification battery is fully offline. Any
  test that dials out is defective by definition.
- **No real browser launches in CI.** Session lifecycle is exercised via
  capability probes and CDP endpoint validation only.
- **Fail-closed everywhere.** Missing capabilities, empty allowlists, and
  unknown inputs raise precise errors; nothing silently degrades.
- **Walled-garden discipline.** The cookie bridge starts with an EMPTY
  allowlist; domains are operator-approved, values are redacted in logs.
- **No banned driver strings.** The stealth normalization table carries
  standard vendor/renderer shapes only; the reflection grep must stay at
  zero hits inside `runtime/`.
- **Secret hygiene.** No credentials in code, config, or logs; env-only
  configuration; redacted reprs for anything sensitive.
````

## Block 2 — README.md (byte-exact)

````text README.md
# supremeai-browser

Stealth Automation Sandbox & Anti-Detect Headless Runtime for the SupremeAI
11-satellite federation (seed-foundation per issue #502).

## Triple-Tier Browser Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ TIER 1 — STEALTH (high security)                                 │
│   runtime/stealth_profile.py                                     │
│   • Coherent canvas PRNG: one session seed drives all noise       │
│   • Normalized WebGL vendor/renderer table (standard shapes)      │
│   • Natural input curves: bounded cubic-Bezier pointer gestures   │
├──────────────────────────────────────────────────────────────────┤
│ TIER 2 — CONTENT PRUNING (Crawl4AI pattern)                      │
│   runtime/content_pruner.py + runtime/semantic_extractor.py      │
│   • Link-density scoring strips navbars/footers/ads/boilerplate   │
│   • Messy HTML → clean Markdown with numbered citations           │
│   • Semantic DOM outline with token-budget estimate (Moli line)   │
├──────────────────────────────────────────────────────────────────┤
│ TIER 3 — WALLED GARDEN (Agent-Reach pattern)                     │
│   runtime/cookie_bridge.py                                       │
│   • Fail-closed, EMPTY-by-default domain allowlist                │
│   • JSON / Netscape cookies.txt import-export, byte-stable        │
│   • Values redacted in every log and repr                         │
└──────────────────────────────────────────────────────────────────┘
```

Supporting modules: `runtime/session_manager.py` (Playwright launch OR direct
CDP attachment; capability-probed, fail-closed), `runtime/infinite_scanner.py`
(deterministic scroll plans + lazy-load expansion JS), `runtime/config.py`
(immutable, validated browser profiles).

## Installation

```bash
pip install -e .            # core (stdlib-only)
pip install -e ".[runtime]" # optional playwright/lxml extras
```

## Usage

```python
from runtime.content_pruner import ContentPruner
from runtime.stealth_profile import generate, bezier_path
from runtime.cookie_bridge import CookieBridge

fp = generate("my-session-seed")           # deterministic fingerprint
path = bezier_path((0, 0), (300, 200))     # natural pointer gesture
out = ContentPruner().prune(html)          # markdown + numbered citations
bridge = CookieBridge(allowlist=["reddit.com"])  # walled garden, explicit
```

## Verification Contract (3-tier)

1. **Reflection check** — the banned driver-string grep over `runtime/`
   returns zero matches (guarded by a test in the battery as well).
2. **Boot smoke:**

```bash
python3 -c "from runtime.session_manager import BrowserSessionManager; from runtime.content_pruner import ContentPruner; print('Browser runtime boot smoke: SUCCESS')"
```

3. **Unit tests:**

```bash
python3 -m pytest tests/test_browser_foundation.py -v   # 15 passing, offline
```

## Honesty Notes

- The core package is stdlib-only by constitutional design; `playwright` and
  `lxml` are optional extras for the execution tier. Importing `runtime/`
  never requires them (capability probes fail closed with precise errors).
- The content pruner adapts the Crawl4AI heuristic school (text-vs-link
  density + tag/attribute scoring) in a pure-stdlib implementation; it is not
  a vendored copy of Crawl4AI code.
- The cookie bridge stores what you feed it in-process; it performs no
  network I/O and starts locked until an operator allowlists domains.
````

## Apply procedure (satellite mirror, after the code commit)

1. Copy Block 1 → `AGENTS.md` and Block 2 → `README.md` in
   `Supremeai-bd/supremeai-browser` (both paths are NEW there — the satellite
   starts empty).
2. Byte-exactness contract: each block, plus exactly one trailing newline,
   MUST equal the target file content. The builder gate asserts this against
   the staging sources; `diff` after apply must be empty.
3. Do NOT touch root `AGENTS.md`/`README.md` of the monorepo — this package
   never writes those paths (that is the r1 lesson, measured twice).

## Verification (3-tier, unchanged from the issue contract)

1. **Reflection:** banned driver-string case-insensitive grep over
   `runtime/` returns zero hits (also asserted inside the offline battery).
2. **Boot smoke:** `python3 -c "from runtime.session_manager import BrowserSessionManager; from runtime.content_pruner import ContentPruner; print('Browser runtime boot smoke: SUCCESS')"`
3. **Unit tests:** `python3 -m pytest tests/test_browser_foundation.py -v`
   (15 passing, minimum 10 required; fully offline).

## Honesty ledger

- r1 (WO #546) failed on monorepo trunk collisions for the two root doc
  paths ONLY; all 10 code paths applied cleanly by construction (new files).
- r2 moves those two contents into this governance doc; the code payload is
  byte-identical to r1 (same sha256 family, re-verified on staging).
- The satellite apply step is operator-side by design (private satellite
  mirror); the WO ships everything needed to perform it mechanically.
