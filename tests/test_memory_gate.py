"""tests/test_memory_gate.py — unit tests for gateway relevance-gated memory."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from gateway.memory_gate import MemoryEntry, MemoryGate


def test_relevant_retained():
    gate = MemoryGate(threshold=0.5)
    entries = [
        MemoryEntry("1", "css", "center a div with css grid"),
        MemoryEntry("2", "db", "run alter table sqlite migration"),
    ]
    res = gate.gate("how to center a div with css", entries)
    ids = {e.entry_id for e in res.retained}
    assert "1" in ids
    assert "2" not in ids


def test_empty_query_rejects_all():
    gate = MemoryGate(threshold=0.5)
    entries = [MemoryEntry("1", "css", "center a div")]
    res = gate.gate("", entries)
    assert res.retained == []
    assert res.leak_count == 1


def test_empty_entries():
    gate = MemoryGate()
    res = gate.gate("css", [])
    assert res.retained == [] and res.rejected == []


def test_default_threshold():
    gate = MemoryGate()
    assert gate.threshold == 0.72


def test_threshold_clamp():
    gate = MemoryGate(threshold=1.5)
    assert gate.threshold == 1.0
    gate2 = MemoryGate(threshold=-0.1)
    assert gate2.threshold == 0.0


def test_is_cross_domain_leak():
    gate = MemoryGate(threshold=0.9)
    e = MemoryEntry("1", "db", "sqlite migration")
    assert gate.is_cross_domain_leak("css grid center", e) is True


def test_leak_rate():
    gate = MemoryGate(threshold=0.5)
    entries = [
        MemoryEntry("1", "css", "center a div with css grid"),
        MemoryEntry("2", "db", "run alter table sqlite migration"),
    ]
    res = gate.gate("how to center a div with css", entries)
    assert 0.0 <= res.leak_rate <= 1.0
    assert res.leak_count == len(res.rejected)
