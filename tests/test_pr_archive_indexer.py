#!/usr/bin/env python3
"""Hermetic tests for scripts/ci/pr_archive_indexer.py (#3665).

Pins the pure PR-record parser and the index roundtrip — the knowledge-base
persister (#3454) must extract reflection evidence, agent identity and touched
files without any network; the roundtrip runs against a tmp archive dir.
"""

from pathlib import Path
from unittest import mock

from scripts.ci import pr_archive_indexer as pai

BODY = """\
## Reflection Evidence
- **why:** the landing plane never confirmed receipt for #3210
- **alternatives_rejected:** re-filing a duplicate WO (anti-stampede U5)

## Agent Identity
GLM Agent 16 (Job 486792)

## Test Evidence
3-Tier verified locally.
"""


def test_parse_pr_details_full_record():
    rec = pai.parse_pr_details(
        {"number": 42, "title": "fix(x): something", "state": "MERGED",
         "author": {"login": "agent-16"}, "body": BODY,
         "files": [{"path": "a.py"}, {"path": "b.py"}]},
        diff_text="",
    )
    assert rec["pr_number"] == 42
    assert rec["agent_identity"] == "GLM Agent 16 (Job 486792)"
    assert rec["reflection_why"].startswith("the landing plane")
    assert rec["alternatives_rejected"].startswith("re-filing")
    assert rec["touched_files"] == ["a.py", "b.py"]
    assert rec["has_verification_signature"] is True
    assert rec["diff_path"] is None and rec["diff_size_bytes"] == 0


def test_parse_pr_details_diff_fallback_and_empty_body():
    rec = pai.parse_pr_details(
        {"number": 7, "title": "t", "state": "OPEN", "author": "someone", "body": ""},
        diff_text="diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n",
    )
    assert sorted(rec["touched_files"]) == ["x.py"]
    assert rec["agent_identity"] == "someone"  # honest author fallback
    assert rec["reflection_why"] == "" and rec["alternatives_rejected"] == ""
    assert rec["has_verification_signature"] is False
    assert rec["diff_path"] == "diffs/pr_7.diff" and rec["diff_size_bytes"] > 0


def test_index_roundtrip_in_tmp_archive(tmp_path: Path):
    fake_arch = tmp_path / "pr_archive"
    with mock.patch.object(pai, "ARCHIVE_DIR", fake_arch), \
         mock.patch.object(pai, "DIFFS_DIR", fake_arch / "diffs"), \
         mock.patch.object(pai, "INDEX_FILE", fake_arch / "pr_incident_index.json"):
        pai.save_index({"version": 2, "records": [{"pr_number": 1}]})
        data = pai.load_index()
        assert data["version"] == 2
        assert data["records"] == [{"pr_number": 1}]
        # corrupt file -> honest empty reset, never a crash
        pai.INDEX_FILE.write_text("not json{", encoding="utf-8")
        data = pai.load_index()
        assert data == {"version": 2, "records": []}
        # the corrupt bytes stay untouched on disk (reader is non-destructive)
        assert (fake_arch / "pr_incident_index.json").read_text() == "not json{"
