"""Offline verification battery for the supremeai-browser foundation seed.

Covers (issue #502 contract, minimum 10):
  stealth fingerprinting, content pruning, infinite scroll simulation,
  semantic tree extraction, walled-garden cookie bridge, session lifecycle.

ZERO network, ZERO browser launches, stdlib-only.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from browser.runtime.config import get_profile, profile_names
    from browser.runtime.content_pruner import ContentPruner, link_density
    from browser.runtime.cookie_bridge import (
        CookieBridge,
        CookieRecord,
        WalledGardenViolation,
    )
    from browser.runtime.infinite_scanner import (
        SCROLL_AND_EXPAND_JS,
        FeedExpander,
        ScrollPlan,
    )
    from browser.runtime.semantic_extractor import (
        estimate_tokens,
        extract_semantic_tree,
    )
    from browser.runtime.session_manager import (
        BrowserSessionManager,
        RuntimeCapabilityError,
        playwright_available,
    )
    from browser.runtime.stealth_profile import (
        StealthProfile,
        bezier_path,
        generate,
        webgl_pairs,
    )
except ImportError:
    from runtime.config import get_profile, profile_names
    from runtime.content_pruner import ContentPruner, link_density
    from runtime.cookie_bridge import (
        CookieBridge,
        CookieRecord,
        WalledGardenViolation,
    )
    from runtime.infinite_scanner import (
        SCROLL_AND_EXPAND_JS,
        FeedExpander,
        ScrollPlan,
    )
    from runtime.semantic_extractor import (
        estimate_tokens,
        extract_semantic_tree,
    )
    from runtime.session_manager import (
        BrowserSessionManager,
        RuntimeCapabilityError,
        playwright_available,
    )
    from runtime.stealth_profile import (
        StealthProfile,
        bezier_path,
        generate,
        webgl_pairs,
    )


# ---------------------------------------------------------------- stealth tier
def test_stealth_profile_deterministic() -> None:
    a = generate("satellite-alpha")
    b = generate("satellite-alpha")
    c = generate("satellite-beta")
    assert a.to_dict() == b.to_dict(), "same seed must produce identical fingerprint"
    assert a.to_dict() != c.to_dict(), "different seeds must differ"
    assert isinstance(a, StealthProfile)


def test_canvas_noise_coherent_and_bounded() -> None:
    fp = generate("coherence-check")
    m1 = fp.canvas_noise(8, 8)
    m2 = fp.canvas_noise(8, 8)
    assert m1 == m2, "canvas noise must be coherent across reads"
    assert len(m1) == 8 and all(len(row) == 8 for row in m1)
    assert all(0 <= v <= 255 for row in m1 for v in row)
    with pytest.raises(ValueError):
        fp.canvas_noise(0, 4)


def test_bezier_path_natural_motion() -> None:
    pts = bezier_path((0, 0), (300, 200), steps=40, seed="gesture-1")
    assert len(pts) == 40
    assert pts[0][0] < pts[-1][0], "path must progress toward the target"
    for x, y in pts:
        assert not (math.isnan(x) or math.isnan(y)), "no NaN coordinates"
        assert -50 <= x <= 350 and -50 <= y <= 250, "bounded jitter"
    again = bezier_path((0, 0), (300, 200), steps=40, seed="gesture-1")
    assert pts == again, "gesture paths are deterministic per seed"
    with pytest.raises(ValueError):
        bezier_path((0, 0), (1, 1), steps=1)


def test_webgl_table_standard_only() -> None:
    pairs = webgl_pairs()
    assert len(pairs) >= 3, "need a realistic normalization table"
    for vendor, renderer in pairs:
        assert vendor.startswith("Google Inc."), "normalized ANGLE vendor shape"
        assert "Direct3D" in renderer, "standard Windows/D3D renderer shape"
    joined = " ".join(v + " " + r for v, r in pairs).lower()
    assert "mesa dri" not in joined, "reflection guard: banned driver strings absent"


# --------------------------------------------------------- semantic extractor
def test_semantic_extractor_drops_layout_wrappers() -> None:
    html = (
        "<html><head><style>.x{}</style></head><body>"
        "<div><div><div><main><h1>Title</h1>"
        "<p>First paragraph with real content.</p>"
        "</main></div></div></div>"
        "<script>var tracking = 1;</script>"
        "</body></html>"
    )
    tree = extract_semantic_tree(html)
    outline = tree.outline()
    assert "<main>" in outline and "<h1>" in outline and "<p>" in outline
    assert "var tracking" not in tree.plain_text(), "script content discarded"
    assert ".x{}" not in tree.plain_text(), "style content discarded"
    assert "<div>" not in outline, "pure layout wrappers flattened"


def test_semantic_outline_token_budget() -> None:
    body = " ".join(
        f"Paragraph number {i} with some sentence content." for i in range(40)
    )
    html = f"<main><p>{body}</p></main>"
    tree = extract_semantic_tree(html)
    raw_tokens = estimate_tokens(html)
    outline_tokens = estimate_tokens(tree.outline())
    assert tree.node_count() >= 2
    assert outline_tokens < raw_tokens, "outline must be cheaper than raw HTML"


# ------------------------------------------------------------ content pruner
BOILERPLATE_HTML = """
<html><head><title>Article</title></head><body>
<nav><a href="/home">Home</a> <a href="/about">About</a> <a href="/c">Contact</a>
<a href="/p">Pricing</a> <a href="/j">Jobs</a></nav>
<div class="advert-container"><a href="/deal">BUY NOW 90% OFF</a>
<a href="/deal2">LIMITED</a> <a href="/d3">CLICK</a></div>
<article>
<h1>Deep Dive Into Deterministic Fingerprinting</h1>
<p>This long and informative paragraph explains how coherent canvas noise is
generated from a single session seed and why anti-bot engines flag unstable
fingerprints. It carries the substance of the page.</p>
<p>A second substantive paragraph discusses WebGL normalization tables and
bounded Bezier input jitter. See <a href="https://example.com/spec">the spec</a>
for the full normative reference.</p>
<pre>def sample(): return 42</pre>
</article>
<footer><a href="/terms">Terms</a> <a href="/privacy">Privacy</a></footer>
</body></html>
"""


def test_pruner_strips_boilerplate() -> None:
    pruner = ContentPruner()
    out = pruner.prune(BOILERPLATE_HTML)
    md = out.markdown
    assert "# Deep Dive Into Deterministic Fingerprinting" in md
    assert "coherent canvas noise" in md
    assert "BUY NOW" not in md, "ad container dropped"
    assert "Terms" not in md and "Privacy" not in md, "footer dropped"
    assert "Pricing" not in md, "nav dropped"
    assert out.blocks_dropped >= 1
    assert out.reduction_ratio > 0.3, "meaningful reduction achieved"


def test_pruner_markdown_numbered_citations() -> None:
    out = ContentPruner().prune(BOILERPLATE_HTML)
    assert "[1]" in out.markdown, "inline numbered citation present"
    urls = [u for _, u in out.citations]
    assert urls == ["https://example.com/spec"], "citation list ordered and deduped"
    assert out.citation_block.endswith("https://example.com/spec")


def test_pruner_link_density_ad_drop() -> None:
    assert link_density("buy now", 7) == 0.0 or link_density("buy now", 7) > 0
    ad = '<p><a href="/1">A</a> <a href="/2">B</a> <a href="/3">C</a></p>'
    out = ContentPruner().prune(ad)
    assert out.blocks_kept == 0, "short link-dominated blocks classified as ads"
    assert out.blocks_dropped == 1, "the ad block is counted as dropped"
    assert out.markdown == ""
    with pytest.raises(ValueError):
        ContentPruner(link_density_threshold=0.0)


# --------------------------------------------------------- infinite scanner
def test_scroll_plan_stall_detection() -> None:
    plan = ScrollPlan(page_height=5000, viewport_height=1000, max_rounds=50)
    steps = plan.build()
    assert steps, "plan must contain rounds"
    assert all(s.scroll_to_y <= 5000 for s in steps), "never scroll past page"
    ys = [s.scroll_to_y for s in steps]
    assert ys == sorted(ys), "monotone downward"
    assert len(steps) < 50, "stall detection stopped the plan early"
    tail = steps[-1]
    assert tail.wait_ms == 400
    with pytest.raises(ValueError):
        ScrollPlan(page_height=0)


def test_feed_expander_growth_and_stall() -> None:
    heights = iter([3000, 4000, 5000, 5000, 5000, 5000, 5000])

    def provider() -> int:
        return next(heights)

    def grow(round_index: int) -> None:
        return None

    expander = FeedExpander(height_provider=provider, grow=grow, initial_height=2000)
    final = expander.expand(max_rounds=10, stall_limit=3)
    assert final == 5000, "expansion stops at observed height"
    assert expander.stalled_rounds >= 3, "stall counted after growth ends"
    assert bool(SCROLL_AND_EXPAND_JS), "runtime JS constant embedded"
    assert "scrollBy" in SCROLL_AND_EXPAND_JS


# ------------------------------------------------------------ cookie bridge
def test_cookie_bridge_fail_closed_default() -> None:
    bridge = CookieBridge(allowlist=[])
    with pytest.raises(WalledGardenViolation):
        bridge.import_json(
            [{"name": "auth", "value": "s3cret", "domain": "twitter.com"}],
            "twitter.com",
        )
    strict = CookieBridge(allowlist=["twitter.com"])
    with pytest.raises(WalledGardenViolation):
        strict.import_json(
            [{"name": "auth", "value": "v", "domain": "evil-twitter.com"}],
            "evil-twitter.com",
        )
    assert strict.count() == 0, "nothing stored on refusal"


def test_cookie_bridge_netscape_roundtrip() -> None:
    bridge = CookieBridge(allowlist=["reddit.com"])
    accepted = bridge.import_json(
        [
            {"name": "session", "value": "abc123", "domain": "reddit.com", "path": "/"},
            {
                "name": "prefs",
                "value": "dark",
                "domain": "www.reddit.com",
                "path": "/",
                "secure": False,
            },
        ],
        "reddit.com",
    )
    assert accepted == 2
    exported = bridge.export_netscape("reddit.com")
    assert "session\tabc123" not in exported or "\tsession\t" in exported
    lines = [ln for ln in exported.splitlines() if ln and not ln.startswith("#")]
    assert len(lines) == 2
    second = CookieBridge(allowlist=["reddit.com"])
    second.import_netscape(exported, "reddit.com")
    assert second.export_netscape("reddit.com") == exported, "byte-stable roundtrip"
    summary = bridge.summary()
    assert summary["values"] == "redacted"
    rec = CookieRecord(name="n", value="super-secret-token-xyz", domain="reddit.com")
    shown = str(rec.redacted())
    assert "super-secret-token-xyz" not in shown, "redacted view hides values"
    assert "<redacted:22B>" in shown, "redaction marks carry length only"


# ---------------------------------------------------------- session manager
def test_session_manager_capability_fail_closed() -> None:
    mgr = BrowserSessionManager()  # default profile
    assert mgr.mode == "playwright"
    if not playwright_available():
        with pytest.raises(RuntimeCapabilityError):
            mgr.start()
    mgr2 = BrowserSessionManager(cdp_endpoint="ws://127.0.0.1:9222/devtools/page")
    assert mgr2.mode == "cdp"
    assert mgr2.cdp_endpoint.startswith("ws://")
    with pytest.raises(ValueError):
        BrowserSessionManager(cdp_endpoint="ftp://bad")
    with BrowserSessionManager(cdp_endpoint="http://127.0.0.1:9222") as live:
        assert live.started
    assert not mgr2.started, "unstarted manager stays unstarted"


def test_config_presets_valid() -> None:
    names = profile_names()
    assert "windows_chrome_stable" in names
    for name in names:
        get_profile(name).validate()
    mobile = get_profile("mobile_android_chrome")
    assert mobile.is_mobile and mobile.has_touch
    with pytest.raises(KeyError):
        get_profile("nonexistent_profile")
