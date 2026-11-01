#!/usr/bin/env python3
"""#2811 window class — Render month-window build-minute accounting battery.

Witness #2811 (platform-guardian cycle-47): render build-minute counters moved
DOWNWARD during the retry-fail deploy loop, once with an exact dual-account
mirror (ΔbuildMin == −ΔfreeLimit on both accounts in the same hour). Usage
cannot decrease — every drop was a truncated deploys window sliding: as new
deploys pushed older, longer builds out of a fixed first page, the computed
month-to-date total fell and the derived free-limit remainder rose by exactly
that amount. A truncated window under-counts month-to-date burn during
retry-fail months and can present a false safe posture to the autoDeploy
toggles these guards control.

Pinned here, offline and deterministic:
- a 120-deploy month sums to 120 minutes, not to whatever fits the old
  fixed window (quota guard limit=50, tower adapter limit=20);
- pre-month deploys exclude themselves and flag saturation (the cursor stop
  rule shared by the guards and the tower adapter's render_build_window.ts);
- both guards cursor-paginate (limit=100 + after=<id>) until the month window
  is saturated, with the page cap as the last-resort bound;
- render_build_budget_guard imports again at all (its scripts/lib path died in
  the ops/ relocation and crashed the module in every context).
"""

import importlib.util
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
QUOTA_PATH = REPO_ROOT / "scripts" / "ci" / "render_build_quota_guard.py"
BUDGET_PATH = REPO_ROOT / "scripts" / "ci" / "render_build_budget_guard.py"

MONTH_START = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _dep(created_iso, duration_seconds, dep_id="d"):
    """Build a Render-shaped {deploy: {...}} record."""
    created = datetime.fromisoformat(created_iso.replace("Z", "+00:00"))
    finished = created + timedelta(seconds=duration_seconds)
    return {
        "deploy": {
            "id": f"{dep_id}-{created_iso}",
            "createdAt": created.isoformat().replace("+00:00", "Z"),
            "finishedAt": finished.isoformat().replace("+00:00", "Z"),
        }
    }


def _n_month_deploys(n, duration_seconds=60.0):
    """n distinct one-minute builds on 2026-10-15, minute-spaced."""
    out = []
    for i in range(n):
        hh = i // 3600
        mm = (i // 60) % 60
        ss = i % 60
        out.append(_dep(f"2026-10-15T{hh:02d}:{mm:02d}:{ss:02d}Z", duration_seconds, f"d{i}"))
    return out


quota = _load(QUOTA_PATH, "render_build_quota_guard")
budget = _load(BUDGET_PATH, "render_build_budget_guard")


class SumMonthBuildSecondsQuota(unittest.TestCase):
    """The pure month-window sum (quota guard variant)."""

    def test_120_deploy_month_sums_fully(self):
        total, count, sat = quota.sum_month_build_seconds(_n_month_deploys(120), MONTH_START)
        self.assertAlmostEqual(round(total / 60.0, 2), 120.0)
        self.assertEqual(count, 120)
        self.assertFalse(sat)

    def test_pre_month_excluded_and_flags_saturation(self):
        items = [_dep("2026-09-20T10:00:00Z", 600.0)] + _n_month_deploys(120)
        total, count, sat = quota.sum_month_build_seconds(items, MONTH_START)
        self.assertEqual(count, 120)
        self.assertAlmostEqual(round(total / 60.0, 2), 120.0)
        self.assertTrue(sat)

    def test_calendar_boundary(self):
        total, count, sat = quota.sum_month_build_seconds(
            [_dep("2026-10-01T00:00:00Z", 60.0), _dep("2026-09-30T23:59:59Z", 60.0)],
            MONTH_START,
        )
        self.assertEqual(count, 1)
        self.assertAlmostEqual(round(total / 60.0, 2), 1.0)
        self.assertTrue(sat)

    def test_junk_never_crashes_or_counts(self):
        total, count, sat = quota.sum_month_build_seconds(
            [
                {"deploy": {"id": "j1", "createdAt": "not-a-date", "finishedAt": "junk"}},
                {"deploy": {"id": "j2"}},
                "garbage-item",
                None,
                _dep("2026-10-04T00:00:00Z", 30.0),
            ],
            MONTH_START,
        )
        self.assertEqual(count, 1)
        self.assertAlmostEqual(round(total, 2), 30.0)
        self.assertFalse(sat)


class FetchMonthDeploysQuota(unittest.TestCase):
    """Cursor pagination until the month window is saturated."""

    def test_pages_until_pre_month_seen(self):
        page1 = _n_month_deploys(100)
        page2 = _n_month_deploys(100, duration_seconds=90.0)
        page3 = [_dep("2026-09-28T00:00:00Z", 300.0)] + _n_month_deploys(2, duration_seconds=45.0)
        pages = [page1, page2, page3]
        seen_queries = []

        def fake_page(service_id, api_key, query):
            seen_queries.append(dict(query))
            return pages[len(seen_queries) - 1]

        with mock.patch.object(quota, "_fetch_deploys_page", side_effect=fake_page):
            collected = quota.fetch_month_deploys("srv-x", "key", MONTH_START)

        self.assertEqual(len(seen_queries), 3)
        self.assertEqual(seen_queries[0].get("limit"), 100)
        self.assertNotIn("after", seen_queries[0])
        self.assertIn("after", seen_queries[1], "page 2 must carry the cursor")
        self.assertEqual(len(collected), 100 + 100 + 3)

    def test_short_page_stops_without_cursor(self):
        pages = [_n_month_deploys(7)]
        seen = []

        def fake_page(service_id, api_key, query):
            seen.append(dict(query))
            return pages[len(seen) - 1]

        with mock.patch.object(quota, "_fetch_deploys_page", side_effect=fake_page):
            collected = quota.fetch_month_deploys("srv-x", "key", MONTH_START)
        self.assertEqual(len(seen), 1)
        self.assertEqual(len(collected), 7)

    def test_page_cap_bounds_runaway_months(self):
        seen = []

        def fake_page(service_id, api_key, query):
            seen.append(dict(query))
            return _n_month_deploys(100)  # always full, never pre-month

        with mock.patch.object(quota, "_fetch_deploys_page", side_effect=fake_page):
            collected = quota.fetch_month_deploys("srv-x", "key", MONTH_START)
        self.assertEqual(len(seen), quota.DEPLOY_WINDOW_MAX_PAGES)
        self.assertEqual(len(collected), 100 * quota.DEPLOY_WINDOW_MAX_PAGES)

    def test_calculate_uses_the_saturated_window(self):
        page1 = _n_month_deploys(100)  # full page, all in-month
        page2 = [_dep("2026-09-28T00:00:00Z", 300.0)] + _n_month_deploys(20)  # pre-month -> stop
        pages = [page1, page2]
        seen = []

        def fake_page(service_id, api_key, query):
            seen.append(dict(query))
            return pages[len(seen) - 1]

        with mock.patch.object(quota, "_fetch_deploys_page", side_effect=fake_page):
            minutes, deploys = quota.calculate_monthly_build_minutes("srv-x", "key", month_start=MONTH_START)
        # 100 + 20 one-minute builds = 120.0 min — the old fixed limit=50
        # window would have counted only the newest 50.
        self.assertEqual(minutes, 120.0)
        self.assertEqual(deploys, 120)
        self.assertEqual(len(seen), 2)


class BudgetGuardWindow(unittest.TestCase):
    """Same window class in the autoDeploy-acting guard — plus the import fix."""

    def test_module_imports_again(self):
        """Regression: scripts/lib/ vanished in the ops/ relocation; the guard
        crashed at import in every context. Loading it above in module scope is
        itself the assertion — reaching this test proves the import path works."""
        self.assertTrue(hasattr(budget, "calculate_monthly_build_minutes"))
        self.assertTrue(hasattr(budget, "sum_month_build_seconds"))

    def test_sum_month_build_seconds_matches_quota_semantics(self):
        total, count, sat = budget.sum_month_build_seconds(_n_month_deploys(120), MONTH_START)
        self.assertAlmostEqual(round(total / 60.0, 2), 120.0)
        self.assertEqual(count, 120)
        self.assertFalse(sat)

    def test_calculate_paginates_until_saturated(self):
        page1 = _n_month_deploys(100)
        page2 = [_dep("2026-09-28T00:00:00Z", 300.0)] + _n_month_deploys(30, duration_seconds=45.0)
        pages = [page1, page2]
        calls = {"n": 0}

        class FakeClient:
            def __init__(self, api_key=None):
                pass

            def paginate(self, path, page_size=100, max_pages=10):
                calls["n"] += 1
                calls["path"] = path
                calls["page_size"] = page_size
                for page in pages:
                    yield page

        # Pin the clock: the budget guard derives month_start from
        # datetime.now() (no month_start param, unlike the quota guard), so a
        # wall-clock call silently crossed the 2026-11-01 month boundary and
        # every pinned-October fixture read as pre-month (0.0 != 122.5).
        # Month-boundary time-bomb family (#4376, datum 2); pinning keeps this
        # battery deterministic as its own docstring promises.
        class _PinnedOctober(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 10, 15, tzinfo=timezone.utc)

        with mock.patch.object(budget, "RenderClient", FakeClient), \
                mock.patch.object(budget, "datetime", _PinnedOctober):
            minutes = budget.calculate_monthly_build_minutes("key", "srv-x")
        self.assertEqual(calls["page_size"], 100)
        self.assertIn("/deploys", calls["path"])
        # page1: 100 min; page2: 30 valid × 45 s = 22.5 min (pre-month excluded)
        self.assertAlmostEqual(minutes, 122.5, places=2)
        self.assertEqual(calls["n"], 1)

    def test_calculate_returns_zero_on_client_error(self):
        class BoomClient:
            def __init__(self, api_key=None):
                pass

            def paginate(self, path, page_size=100, max_pages=10):
                raise RuntimeError("render unreachable")

        with mock.patch.object(budget, "RenderClient", BoomClient):
            self.assertEqual(budget.calculate_monthly_build_minutes("key", "srv-x"), 0.0)


if __name__ == "__main__":
    unittest.main()
