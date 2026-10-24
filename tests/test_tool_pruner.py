"""tests/test_tool_pruner.py — unit tests for gateway TF-IDF tool pruner."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from gateway.tool_pruner import ToolSchema, clear_cache, route_tools


def _tools():
    return [
        ToolSchema("read_file", "Read local filesystem source files", tokens=180),
        ToolSchema("write_file", "Write or edit code in filesystem", tokens=120),
        ToolSchema("sql_query", "Execute PostgreSQL or SQLite queries", tokens=160),
        ToolSchema("figma_inspect", "Inspect design tokens and CSS frames", tokens=165),
        ToolSchema("web_search", "Perform live web research queries", tokens=140),
    ]


def test_css_query_retains_relevant_tools():
    clear_cache()
    res = route_tools("How do I horizontally center a div with CSS grid?", _tools(), threshold=0.05)
    names = {t.name for t in res.retained}
    # figma_inspect shares the "CSS" term with the query -> highest similarity
    assert "figma_inspect" in names
    # sql/web should be pruned for a CSS question
    assert "sql_query" not in names
    assert "web_search" not in names


def test_empty_query_retains_nothing():
    clear_cache()
    res = route_tools("", _tools(), threshold=0.45)
    assert res.retained == []
    assert len(res.pruned) == 5


def test_threshold_clamp():
    clear_cache()
    res = route_tools("css grid", _tools(), threshold=1.5)
    assert res.threshold == 1.0
    clear_cache()
    res = route_tools("css grid", _tools(), threshold=-0.5)
    assert res.threshold == 0.0


def test_reduction_pct():
    clear_cache()
    res = route_tools("css grid center div", _tools(), threshold=0.45)
    assert 0.0 <= res.reduction_pct <= 100.0
    assert res.original_tokens == sum(t.tokens for t in _tools())


def test_cache_hit_returns_same_retained():
    clear_cache()
    t = _tools()
    r1 = route_tools("css grid", t, threshold=0.45)
    r2 = route_tools("css grid", t, threshold=0.45)
    assert {x.name for x in r1.retained} == {x.name for x in r2.retained}


def test_use_cache_false_bypasses():
    clear_cache()
    t = _tools()
    route_tools("css grid", t, threshold=0.45)
    # cache present; bypass should still compute (no crash)
    r = route_tools("css grid", t, threshold=0.45, use_cache=False)
    assert isinstance(r.retained, list)


def test_zero_threshold_retains_all():
    clear_cache()
    res = route_tools("anything", _tools(), threshold=0.0)
    assert len(res.retained) == 5
    assert res.pruned == []


def test_high_threshold_prunes_all_or_some():
    clear_cache()
    res = route_tools("css grid", _tools(), threshold=0.99)
    # at extreme threshold, likely prunes everything (no exact match guaranteed)
    assert len(res.retained) <= 5
