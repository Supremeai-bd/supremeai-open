"""tests/test_skill_dispatcher.py — Way 13 evidence (skill resolution + non-regression)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import pytest

try:
    from core.skills.skill_dispatcher import SkillDispatch, SkillDispatcher
    from core.skills.skill_registry import SkillRegistry
except ModuleNotFoundError as _exc:  # core runtime incomplete in the public mirror
    pytest.skip(
        "core runtime unavailable in this mirror (monitoring module lives in the "
        f"private core repo): {_exc}",
        allow_module_level=True,
    )



@pytest.fixture()
def dispatcher_with_tmp_manifests(monkeypatch):
    """Dispatcher over a tiny synthetic manifest dir (no dependency on repo manifests)."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        (base / "summarizer.json").write_text(
            '{"id": "core-doc-summarizer", "description": "Summarize core documentation",'
            ' "tags": ["docs", "summary", "summarize"]}'
        )
        (base / "qa.json").write_text(
            '{"id": "core-knowledge-qa", "description": "Answer questions over knowledge base",'
            ' "tags": ["question", "answer", "knowledge"]}'
        )
        (base / "installer.json").write_text(
            '{"id": "skill-installer", "description": "Install and provision new skills",'
            ' "tags": ["install", "provision"]}'
        )
        reg = SkillRegistry(manifests_path=base)
        monkeypatch.setattr(
            "core.skills.skill_dispatcher.SkillRegistry", lambda manifests_path=None: reg
        )
        yield SkillDispatcher()


def test_resolves_doc_summary_task(dispatcher_with_tmp_manifests):
    m = dispatcher_with_tmp_manifests.resolve_best("please summarize the core docs for me")
    assert m is not None
    assert m.skill_id == "core-doc-summarizer"
    assert m.matched


def test_resolves_qa_task(dispatcher_with_tmp_manifests):
    m = dispatcher_with_tmp_manifests.resolve_best("answer a question from the knowledge base")
    assert m is not None
    assert m.skill_id == "core-knowledge-qa"


def test_no_match_returns_none(dispatcher_with_tmp_manifests):
    assert dispatcher_with_tmp_manifests.resolve_best("xyzzy unrelated gibberish") is None


def test_empty_task_fail_open(dispatcher_with_tmp_manifests):
    assert dispatcher_with_tmp_manifests.resolve("") == []
    assert dispatcher_with_tmp_manifests.resolve_best("   ") is None


def test_deterministic_and_sorted(dispatcher_with_tmp_manifests):
    r1 = dispatcher_with_tmp_manifests.resolve("summarize docs", top_k=3)
    r2 = dispatcher_with_tmp_manifests.resolve("summarize docs", top_k=3)
    assert [x.skill_id for x in r1] == [x.skill_id for x in r2]
    assert all(r1[i].score >= r1[i + 1].score for i in range(len(r1) - 1))


def test_top_k_and_dataclass_shape(dispatcher_with_tmp_manifests):
    outs = dispatcher_with_tmp_manifests.resolve("docs knowledge install", top_k=3)
    assert 1 <= len(outs) <= 3
    assert all(isinstance(o, SkillDispatch) for o in outs)


def test_real_registry_still_discoverable():
    """Non-regression: the repo's real SkillRegistry still works through the dispatcher."""
    d = SkillDispatcher()
    ids = d.skill_ids
    assert len(ids) == len(set(ids))
