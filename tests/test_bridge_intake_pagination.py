#!/usr/bin/env python3
"""Pin + behavior: bridge intake closed-PR pagination — bounded recent window (#5188).

Live anatomy (GLM Agent 22, Job 486813, 2026-11-02): the Bridge Intake sync
phase on the monorepo exits non-zero on every scheduled run with
`pagination cap reached (5 pages)` — the repo crossed 500 closed PRs, the
`gh_paged(..., max_pages=5)` call in `cmd_sync` hit its fail-honest cap,
and landed/rejected reconciliation stopped (run 41369130502, issue #5188).

The cap-raise is *correct* fail-honest design for an unbounded historical
scan (E5, #58): silent truncation hides unreconciled PRs forever. The bug
was asking one paginator to be both the whole history AND the sync's
recent-window scan. Root fix pinned here (zero network — fake responses,
patched urlopen):
  1. `gh_paged_capped(path, token, max_pages) -> (items, has_more)` — the
     `gh_first_page` (#2265) cap-tolerant contract extended to multi-page:
     scans exactly the bounded recent window, returns `has_more=True` at the
     boundary instead of raising; HTTP errors still raise BridgeError.
  2. Sync keeps `sort=updated` (recent-first), so the 5-page window IS the
     actionable set; boundary coverage is reported via an explicit
     partial-coverage note (fail-honest), never swallowed.
Pinned behaviors below: >500 closed PRs (6 pages, cap 5) → 500 items +
has_more=True with NO raise; exact page boundary → has_more=False; under
cap → all pages, has_more=False; request count stops at the cap; HTTP
errors still fail honestly.
"""

import json
import sys
import urllib.error
from urllib.error import HTTPError

import pytest

from scripts.bridge import bridge_intake as bi
from scripts.bridge.bridge_intake import BridgeError, gh_paged_capped

PER_PAGE = 100


class FakeResp:
    def __init__(self, body: bytes, link: str = ""):
        self._body = body
        self.link = link

    # mimic urllib's response context-manager protocol
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._body

    class headers:  # noqa: N801 - mimics urllib response API
        @staticmethod
        def get(name: str, default=None):
            return default


def _make_opener(total_items: int, pages_live: int, requests_seen: list[str]):
    """Zero-network fake: `pages_live` real pages of PER_PAGE items, then a
    `Link: rel="next"` chain that keeps existing (a repo with more history
    than the window). Returns (callable, expected_page_count)."""

    def fake_urlopen(req, timeout=45):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        requests_seen.append(url)
        page = len(requests_seen)
        if page > pages_live:
            raise AssertionError(f"fetcher walked past the live page chain: {url}")
        start = (page - 1) * PER_PAGE
        chunk = [
            {"number": start + i + 1, "merged_at": "2026-11-01T00:00:00Z"}
            for i in range(min(PER_PAGE, max(0, total_items - start)))
        ]
        has_next = page < pages_live  # chain continues beyond the window
        link = f'<https://api.github.com/pulls?page={page + 1}>; rel="next"' if has_next else ""
        resp = FakeResp(json.dumps(chunk).encode())
        resp.link = link
        # gh_paged_capped reads headers.get("Link") off the response object
        resp.headers = type("H", (), {"get": staticmethod(lambda n, d=None: link if n == "Link" else d)})()
        return resp

    return fake_urlopen


def _patch_urlopen(monkeypatch, fn):
    monkeypatch.setattr(bi.urllib.request, "urlopen", fn)


def test_over_500_closed_prs_returns_window_with_has_more(monkeypatch):
    """#5188 regression: 501+ closed PRs, cap 5 → 500 items + has_more, NO raise.

    Old behavior: gh_paged raised `pagination cap reached (5 pages)` → sync
    exited non-zero on every run. New contract: the bounded recent window
    scans cleanly and reports the boundary through has_more.
    """
    seen: list[str] = []
    _patch_urlopen(monkeypatch, _make_opener(total_items=501, pages_live=6, requests_seen=seen))
    items, has_more = gh_paged_capped(
        "/repos/x/y/pulls?state=closed&sort=updated&per_page=100", "t", max_pages=5
    )
    assert len(items) == 500
    assert has_more is True
    assert len(seen) == 5  # stopped exactly at the window, did not walk page 6


def test_page_boundary_exactly_max_pages_no_more(monkeypatch):
    """Exactly `max_pages` pages with no further Link → complete scan, has_more=False."""
    seen: list[str] = []
    _patch_urlopen(monkeypatch, _make_opener(total_items=500, pages_live=5, requests_seen=seen))
    items, has_more = gh_paged_capped("/repos/x/y/pulls", "t", max_pages=5)
    assert len(items) == 500
    assert has_more is False
    assert len(seen) == 5


def test_under_cap_scans_all_pages(monkeypatch):
    """Fewer pages than the cap → every page scanned, has_more=False."""
    seen: list[str] = []
    _patch_urlopen(monkeypatch, _make_opener(total_items=137, pages_live=2, requests_seen=seen))
    items, has_more = gh_paged_capped("/repos/x/y/pulls", "t", max_pages=5)
    assert len(items) == 137
    assert has_more is False
    assert len(seen) == 2


def test_http_error_still_raises_bridge_error(monkeypatch):
    """Fail-honest unchanged: HTTP errors raise BridgeError, never a partial result."""

    def fake_urlopen(req, timeout=45):
        raise HTTPError("https://api.github.com/x", 401, "Bad credentials", {}, None)

    _patch_urlopen(monkeypatch, fake_urlopen)
    with pytest.raises(BridgeError):
        gh_paged_capped("/repos/x/y/pulls", "t", max_pages=5)


def test_legacy_gh_paged_still_raises_at_cap(monkeypatch):
    """E5/#58 contract intact: the unbounded scan keeps its fail-honest cap-raise."""
    seen: list[str] = []
    _patch_urlopen(monkeypatch, _make_opener(total_items=501, pages_live=6, requests_seen=seen))
    with pytest.raises(BridgeError, match="pagination cap reached"):
        bi.gh_paged("/repos/x/y/pulls", "t", max_pages=5)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
