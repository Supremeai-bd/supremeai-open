#!/usr/bin/env python3
"""Pin + behavior: bounded closed-PR pagination in bridge_intake sync (#5188).

Live anatomy (GLM Agent 13, Job 486783, 2026-11-02T03:27Z): the private
monorepo crossed 500 closed PRs, so cmd_sync's exhaustive-with-cap scan
(gh_paged, max_pages=5, per_page=100) hit its own cap on EVERY scheduled run:
"pagination cap reached (5 pages)" -> sync_errors -> exit 2 -> workflow red
(run 41369130502; five ci-failed WOs minted from this single root cause in the
2026-11-02 wave-4 refill alone). The intake phase completed fine — the sync
phase's verdict-reporting was collateral-blinded by a contract mismatch: E5's
exhaustive history scan is structurally impossible at high-volume repos (a
page 6 of 100 always exists once closed PRs pass 500).

Root fix pinned here (zero network — fake responses and patched fakes):
  1. gh_paged_bounded: N-page Link-follower that returns (items, has_more)
     at the cap instead of raising — the N-page generalization of
     gh_first_page's #2265 (items, has_more) idiom; decision moves to the
     caller.
  2. cmd_sync consumes has_more as a LOUD informational note (own stdout
     section), never a sync_error — truncation is the designed steady state
     for repos with >500 closed PRs, so the exit code returns to 0 when
     everything else is clean. The note is not silent (E5 anti-regression).
  3. Fail-honest rails preserved: transport errors (HTTPError) still raise
     BridgeError -> sync_errors -> exit 2; no tokens printed anywhere.
  4. Landed verdicts still flow inside the window: a merged bridge-land PR
     (head ref bridge-land/<TASK_ID_RE-conforming task id>) on page 1 reports
     LANDED on its open work-order issue and closes it (comment + label +
     PATCH close), proving the bounded scan kept its reporting purpose.
  5. Helper purity: has_more is False exactly when no rel="next" link
     remains, so callers can never mistake a complete scan for a truncated
     one (and vice versa).

Dual-mode: runs under both `python3 -m unittest` and `pytest`.
"""

from __future__ import annotations

import io
import json
import re
import sys
import unittest
import unittest.mock
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "bridge"))

import bridge_intake as bi  # noqa: E402

TASK_ID = "bridge-20261102-bridge-intake-pagination"  # TASK_ID_RE-conforming


class FakeResp:
    """urlopen stand-in: serves a JSON list page + a Link header dict."""

    def __init__(self, payload: list, link: str = ""):
        self._body = json.dumps(payload).encode()
        self.headers = {"Link": link}

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def link_header(next_url: str | None) -> str:
    return f'<{next_url}>; rel="next"' if next_url else ""


def fake_pr(number: int, ref: str | None, merged: bool) -> dict:
    head = {"ref": ref} if ref is not None else {}
    return {
        "number": number,
        "head": head,
        "merged_at": "2026-11-02T03:00:00Z" if merged else None,
        "merge_commit_sha": "a" * 40 if merged else None,
    }


def fake_issue(number: int, task_id: str) -> dict:
    return {
        "number": number,
        "body": f"### Task ID\n{task_id}\n",
        "labels": [],
        "state": "open",
    }


def pages_response(pages: list[list[dict]], next_after_last: bool, first_url: str = ""):
    """Build a urlopen router: len(pages) sequential pages, rel=next chaining;
    the LAST page carries a next-link iff next_after_last (simulates >cap).
    Next URLs preserve the first page's real query string (GitHub Link headers
    do the same), so URL-substring routers keep matching every page."""
    base = "https://api.github.com/x"
    first = first_url or base

    def router(_request, timeout=None):  # noqa: ANN001 - fake signature
        m = re.search(r"[?&]p=(\d+)", _request.full_url)
        idx = min(int(m.group(1)), len(pages) - 1) if m else 0
        last = idx == len(pages) - 1
        if last and not next_after_last:
            nxt = None
        else:
            sep = "&" if "?" in first else "?"
            nxt = f"{first}{sep}p={idx + 1}"
        return FakeResp(pages[idx], link_header(nxt))

    return router


class TestGhPagedBounded(unittest.TestCase):
    """Pins 1/3/5 — helper contract (raise-free cap, honest has_more, rails)."""

    def test_cap_returns_items_and_has_more_true_no_raise(self):
        pages = [[fake_pr(i, None, False) for i in range(1, 5)] for _ in range(5)]
        router = pages_response(pages, next_after_last=True)
        with unittest.mock.patch.object(bi.urllib.request, "urlopen", router):
            items, has_more = bi.gh_paged_bounded("/x", "fake-token", max_pages=5)
        self.assertTrue(has_more)  # pin 1: cap-tolerant, never BridgeError
        self.assertEqual(len(items), 20)

    def test_exhausted_returns_has_more_false(self):
        pages = [[fake_pr(1, None, False)], [fake_pr(2, None, False)]]
        router = pages_response(pages, next_after_last=False)
        with unittest.mock.patch.object(bi.urllib.request, "urlopen", router):
            items, has_more = bi.gh_paged_bounded("/x", "fake-token", max_pages=5)
        self.assertFalse(has_more)  # pin 5: complete scan is distinguishable
        self.assertEqual(len(items), 2)

    def test_http_error_still_raises_bridge_error(self):
        def boom(_request, timeout=None):
            raise urllib.error.HTTPError(
                "https://api.github.com/x", 502, "Bad Gateway", {}, io.BytesIO(b"down")
            )

        with unittest.mock.patch.object(bi.urllib.request, "urlopen", boom):
            with self.assertRaises(bi.BridgeError):  # pin 3: rails intact
                bi.gh_paged_bounded("/x", "fake-token", max_pages=5)


class TestCmdSyncBoundedWindow(unittest.TestCase):
    """Pins 2/4 — end-to-end sync over a >500-closed-PR repo (zero network)."""

    def setUp(self):
        # scan_repos = (OPEN_REPO,) only — the pagination decision is per-repo,
        # satellites add nothing to this contract.
        self._repos_patch = unittest.mock.patch.object(bi, "BRIDGE_TARGET_REPOS", ())
        self._repos_patch.start()
        self.addCleanup(self._repos_patch.stop)

        self.calls: dict[str, list] = {"comment": [], "labels": [], "patch": []}

        def fake_comment(repo, token, number, body):
            self.calls["comment"].append((number, body))

        def fake_labels(repo, token, number, labels):
            self.calls["labels"].append((number, labels))

        def fake_gh(method, path, token, payload=None):
            self.calls["patch"].append((method, path, payload))
            return 200, {}

        self._mocks = [
            unittest.mock.patch.object(bi, "ensure_public_labels", lambda token: None),
            unittest.mock.patch.object(bi, "comment_issue", fake_comment),
            unittest.mock.patch.object(bi, "set_labels", fake_labels),
            unittest.mock.patch.object(bi, "gh", fake_gh),
        ]
        for m in self._mocks:
            m.start()
            self.addCleanup(m.stop)

    def _run_sync(self, next_after_last: bool) -> tuple[int, str]:
        landed_page = [fake_pr(9001, f"bridge-land/{TASK_ID}", merged=True)]
        filler = [fake_pr(i, None, False) for i in range(500, 504)]
        pages = [landed_page, filler, filler, filler, filler]
        issues_page = [fake_issue(5188, TASK_ID)]
        open_pulls_page: list[dict] = []

        closed_router = pages_response(
            pages, next_after_last=next_after_last,
            first_url=f"https://api.github.com/repos/{bi.OPEN_REPO}/pulls?state=closed&sort=updated&per_page=100",
        )

        def urlopen_router(request, timeout=None):
            url = request.full_url
            if "state=closed" in url:
                return closed_router(request, timeout)
            if "/issues?state=open" in url:
                return FakeResp(issues_page)
            if "state=open" in url:
                return FakeResp(open_pulls_page)
            raise AssertionError(f"unexpected URL in test: {url}")

        with unittest.mock.patch.object(bi.urllib.request, "urlopen", urlopen_router):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = bi.cmd_sync("fake-token")
        return rc, buf.getvalue()

    def test_truncated_window_exits_zero_with_loud_note(self):
        rc, out = self._run_sync(next_after_last=True)
        self.assertEqual(rc, 0)  # pin 2: regression — was 2 via cap-raise
        self.assertIn("closed-PR window notes", out)
        self.assertIn("5x100 most-recently-updated", out)
        self.assertIn("not an error", out)  # loud, not silent (E5 pin)
        self.assertNotIn("pagination cap reached", out)
        # pin 4: landed verdict still reported inside the window
        self.assertEqual(len(self.calls["comment"]), 1)
        number, body = self.calls["comment"][0]
        self.assertEqual(number, 5188)
        self.assertIn("LANDED", body)
        self.assertEqual(self.calls["labels"], [(5188, [bi.LABEL_LANDED])])
        self.assertTrue(
            any(m == "PATCH" and "issues/5188" in p for m, p, _ in self.calls["patch"])
        )

    def test_complete_window_exits_zero_without_note(self):
        rc, out = self._run_sync(next_after_last=False)
        self.assertEqual(rc, 0)
        self.assertNotIn("closed-PR window notes", out)
        self.assertEqual(len(self.calls["comment"]), 1)  # landed still reported


if __name__ == "__main__":
    unittest.main()
