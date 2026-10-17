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
