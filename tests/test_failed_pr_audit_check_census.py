#!/usr/bin/env python3
"""U6 Zero-Recurrence guard — per-PR check census (workflow-runs join).

The 2026-10-31 17:04+08 defect: the revived PR-plane (R78-mirror + #4264
name-wave tolerance) still printed the permanent honest line "per-PR check
status UNSEEN (tower payload carries no statusCheckRollup; gh absent)" on
every gh-less boot. Root cause was never payload-absence — the SAME
zero-credential tower exposes github.workflow_runs, and every pull_request
run carries display_title == the PR title verbatim (live-verified
2026-10-31, run 41186411655). The status was invisible because the JOIN was
missing, not because the data was.

Contract pinned here:

1. Census alive ⇒ the revived branch classifies every visible open PR as
   green / RED / UNSEEN from the LATEST completed pull_request run
   (title join primary, "(branch-name)" head_branch join secondary);
   report-only — no "✅" and no "zero open PRs" substring may ever ride the
   revived branch (U2: classification is observation, not clean-certification).
2. Census dark (None) ⇒ the previous UNSEEN line survives byte-identically
   (pinned in test_failed_pr_audit_tower_fallback.py via stubbed-dark).
3. The census probe is never allowed to raise or hang into the audit — an
   exploding probe degrades to the honest UNSEEN line.
4. Parser is pure and total: malformed payloads yield empty maps, never
   exceptions; in_progress / non-pull_request runs are not evidence.
5. Title rows keep full length (no [:120] truncation) — a truncated title
   can never join display_title, which would fake UNSEEN on long titles.
6. _classify_tower_pr_failure default label stays "github.list_prs" (old
   note bytes pinned); the census probe passes its own tool label so a
   workflow-runs denial never reports itself as a list_prs failure (U6:
   false-cause class closed).

All tests are offline: transports and list_failed_open_prs are stubbed at
the module boundary — zero network, zero gh dependency.
"""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import continuous_agent_loop as cal  # noqa: E402


def _run_entry(
    title: str, conclusion: str, updated_at: str,
    event: str = "pull_request", status: str = "completed",
    branch: str = "some/branch",
) -> dict:
    return {
        "event": event,
        "status": status,
        "display_title": title,
        "head_branch": branch,
        "conclusion": conclusion,
        "updated_at": updated_at,
        "html_url": "https://github.com/r/x/actions/runs/1",
        "head_sha": "abc123def4567890",
    }


def _capture_report_census(
    tower_rows: list | None,
    census_stub: object,
) -> tuple[list, str]:
    """Dark gh-plane + live tower PR rows + (alive|dark) census probe."""
    buf = io.StringIO()
    with mock.patch.object(cal, "list_failed_open_prs", return_value=None):
        with mock.patch.object(cal, "_tower_open_prs", return_value=(tower_rows, "tower PR fallback: stubbed")):
            with mock.patch.object(
                cal, "_tower_board_rows", return_value=([], "board probe stubbed dark")
            ):
                with mock.patch.object(cal, "_tower_workflow_run_census", return_value=census_stub):
                    with redirect_stdout(buf):
                        failed = cal.report_failed_open_prs(repo="r/x", limit=30)
    return failed, buf.getvalue()


class TestParseWorkflowRunCensus(unittest.TestCase):
    """Pure parser: evidence rules (event/status filter, latest-wins, shapes)."""

    def test_filters_non_pull_request_and_incomplete_runs(self) -> None:
        payload = {"workflow_runs": [
            _run_entry("t1", "failure", "2026-10-31T01:00:00Z", event="push"),
            _run_entry("t2", "failure", "2026-10-31T01:00:00Z", status="in_progress"),
            _run_entry("t3", "success", "2026-10-31T01:00:00Z"),
        ]}
        census = cal._parse_workflow_run_census(payload)
        self.assertIn("t3", census["by_title"])
        self.assertNotIn("t1", census["by_title"])
        self.assertNotIn("t2", census["by_title"])

    def test_latest_run_wins_per_title(self) -> None:
        payload = {"workflow_runs": [
            _run_entry("same title", "failure", "2026-10-31T01:00:00Z"),
            _run_entry("same title", "success", "2026-10-31T02:00:00Z"),
        ]}
        census = cal._parse_workflow_run_census(payload)
        self.assertEqual(census["by_title"]["same title"]["conclusion"], "success")

    def test_builds_both_key_spaces(self) -> None:
        payload = {"workflow_runs": [
            _run_entry("feat(bridge): x (bridge-branch-1)", "success", "2026-10-31T01:00:00Z",
                       branch="bridge-branch-1"),
        ]}
        census = cal._parse_workflow_run_census(payload)
        self.assertIn("bridge-branch-1", census["by_branch"])
        self.assertIn("feat(bridge): x (bridge-branch-1)", census["by_title"])
        self.assertEqual(census["by_branch"]["bridge-branch-1"]["head_sha"], "abc123def456")

    def test_malformed_payloads_yield_empty_maps_never_raise(self) -> None:
        for bad in (None, 42, "str", {}, {"workflow_runs": None}, {"workflow_runs": 7},
                    {"workflow_runs": [None, 1, "x", {}]}):
            census = cal._parse_workflow_run_census(bad)
            self.assertEqual(census, {"by_title": {}, "by_branch": {}}, bad)


class TestPrCheckClassification(unittest.TestCase):
    """Join ladder: title primary, branch-suffix secondary, miss ⇒ None."""

    def setUp(self) -> None:
        self.census = cal._parse_workflow_run_census({"workflow_runs": [
            _run_entry("exact title", "success", "2026-10-31T01:00:00Z", branch="br-1"),
            _run_entry("unrelated", "failure", "2026-10-31T01:00:00Z", branch="bridge-20261031-x"),
        ]})

    def test_title_join_primary(self) -> None:
        hit = cal._pr_check_classification("exact title", self.census)
        self.assertEqual(hit and hit.get("conclusion"), "success")

    def test_branch_suffix_join_secondary(self) -> None:
        hit = cal._pr_check_classification("feat: long title (bridge-20261031-x)", self.census)
        self.assertEqual(hit and hit.get("conclusion"), "failure")

    def test_miss_is_none(self) -> None:
        self.assertIsNone(cal._pr_check_classification("no such PR", self.census))
        self.assertIsNone(cal._pr_check_classification("exact title", {"by_title": {}, "by_branch": {}}))
        self.assertIsNone(cal._pr_check_classification("anything", None))


class TestReporterCensusAlive(unittest.TestCase):
    """Census alive ⇒ per-PR classification, honesty pins intact."""

    ROWS = [
        {"number": 1, "title": "green PR", "url": "u1"},
        {"number": 2, "title": "red PR (bridge-red-branch)", "url": "u2"},
        {"number": 3, "title": "ghost PR", "url": "u3"},
    ]
    CENSUS = cal._parse_workflow_run_census({"workflow_runs": [
        _run_entry("green PR", "success", "2026-10-31T01:00:00Z", branch="green-branch"),
        _run_entry("red PR (bridge-red-branch)", "failure", "2026-10-31T01:00:00Z",
                   branch="bridge-red-branch"),
    ]})

    def test_classification_lines_and_counts(self) -> None:
        failed, out = _capture_report_census(self.ROWS, (self.CENSUS, "census stubbed alive"))
        self.assertEqual(failed, [])
        self.assertIn("per-PR check census", out)
        self.assertIn("1 green / 1 red / 1 UNSEEN", out)
        self.assertIn("PR #1 [green/success]", out)
        self.assertIn("PR #2 [RED/failure]", out)
        self.assertIn("PR #3 [UNSEEN]", out)

    def test_honesty_pins_survive_census_alive(self) -> None:
        # Classification is observation, never clean-certification.
        _failed, out = _capture_report_census(self.ROWS, (self.CENSUS, "census stubbed alive"))
        self.assertNotIn("✅", out)
        self.assertNotIn("zero open PRs", out)
        self.assertIn("not certified clean", out)

    def test_unseen_counted_when_only_zero_red(self) -> None:
        rows = [{"number": 5, "title": "ghost only", "url": "u5"}]
        failed, out = _capture_report_census(rows, (self.CENSUS, "census stubbed alive"))
        self.assertEqual(failed, [])
        self.assertIn("0 green / 0 red / 1 UNSEEN", out)


class TestReporterCensusDark(unittest.TestCase):
    """Census dark/exploding ⇒ previous honest UNSEEN line, never a crash."""

    ROWS = [{"number": 9, "title": "any PR", "url": "u9"}]

    def test_census_dark_degrades_to_unseen_line(self) -> None:
        # The dark line stays byte-identical to the pre-census contract — the
        # census failure note is intentionally NOT spliced into it.
        failed, out = _capture_report_census(self.ROWS, (None, "workflow-runs census failed (URLError)"))
        self.assertEqual(failed, [])
        self.assertIn("per-PR check status UNSEEN", out)
        self.assertIn("PR #9", out)

    def test_census_exploding_never_raises_into_audit(self) -> None:
        buf = io.StringIO()
        with mock.patch.object(cal, "list_failed_open_prs", return_value=None):
            with mock.patch.object(cal, "_tower_open_prs", return_value=(self.ROWS, "note")):
                with mock.patch.object(cal, "_tower_board_rows", return_value=([], "board dark")):
                    with mock.patch.object(
                        cal, "_tower_workflow_run_census", side_effect=RuntimeError("boom")
                    ):
                        with redirect_stdout(buf):
                            failed = cal.report_failed_open_prs(repo="r/x", limit=30)
        self.assertEqual(failed, [])
        self.assertIn("UNSEEN", buf.getvalue())
        # Degradation marker: the census probe's raise is caught (never into
        # the audit) and the classification collapses to the honest UNSEEN line.


class TestExtractMcpToolResponse(unittest.TestCase):
    """SSE event-block recovery: big payloads split across data: lines."""

    def _ok_envelope(self, payload_text: str, chunk_len: int = 0) -> str:
        env = json.dumps({
            "jsonrpc": "2.0", "id": "cal-wf-census-1",
            "result": {"content": [{"type": "text", "text": payload_text}], "isError": False},
        })
        if not chunk_len:
            return f"event: message\ndata: {env}\n\n"
        # Compact split: chop the envelope into data: line chunks (the live
        # 17:04+08 shape for per_page=30/100).
        chunks = [env[i:i + chunk_len] for i in range(0, len(env), chunk_len)]
        return "event: message\n" + "\n".join(f"data: {c}" for c in chunks) + "\n\n"

    PAYLOAD = '{"total_count": 1, "workflow_runs": [{"display_title": "t"}]}'

    def test_single_line_sse(self) -> None:
        text, err = cal._extract_mcp_tool_response(
            self._ok_envelope(self.PAYLOAD), "cal-wf-census-1", "github.workflow_runs"
        )
        self.assertEqual(err, "")
        self.assertIn("workflow_runs", text)

    def test_compact_split_across_data_lines(self) -> None:
        text, err = cal._extract_mcp_tool_response(
            self._ok_envelope(self.PAYLOAD, chunk_len=40), "cal-wf-census-1", "github.workflow_runs"
        )
        self.assertEqual(err, "")
        self.assertIn("workflow_runs", text)

    def test_raw_json_body_without_sse(self) -> None:
        text, err = cal._extract_mcp_tool_response(
            json.dumps({"jsonrpc": "2.0", "id": "cal-wf-census-1",
                        "result": {"content": [{"type": "text", "text": self.PAYLOAD}]}}),
            "cal-wf-census-1", "github.workflow_runs",
        )
        self.assertEqual(err, "")
        self.assertIn("workflow_runs", text)

    def test_error_envelope_classified(self) -> None:
        body = 'data: ' + json.dumps({
            "jsonrpc": "2.0", "id": "cal-wf-census-1",
            "error": {"code": -32602, "message": "MCP error -32602: Tool github.workflow_runs not found"},
        }) + "\n\n"
        text, err = cal._extract_mcp_tool_response(body, "cal-wf-census-1", "github.workflow_runs")
        self.assertEqual(text, "")
        self.assertIn("tool-absent", err)

    def test_other_id_envelopes_ignored(self) -> None:
        # Only the census call_id's envelope is evidence; a body with just
        # foreign ids yields ("", "") — the ladder's "in any window" honest
        # note owns that shape (transport answered, our call did not).
        body = 'data: ' + json.dumps({"jsonrpc": "2.0", "id": "other",
                                     "result": {"content": [{"text": "noise"}]}}) + "\n\n"
        text, err = cal._extract_mcp_tool_response(body, "cal-wf-census-1", "github.workflow_runs")
        self.assertEqual(text, "")
        self.assertEqual(err, "")


class TestCensusWiringContract(unittest.TestCase):
    """Structural pins so the join cannot silently regress."""

    def test_census_probe_wired_into_revived_branch(self) -> None:
        source = Path(cal.__file__).read_text(encoding="utf-8")
        self.assertIn("def _tower_workflow_run_census(", source)
        self.assertIn("_tower_workflow_run_census(limit=limit)", source)
        self.assertIn("def _parse_workflow_run_census(", source)
        self.assertIn("def _pr_check_classification(", source)
        # Window ladder: the output-validation shape retries smaller windows
        # before declaring honest dark (live defect 17:04+08).
        self.assertIn("for per_page in (100, 30, 10):", source)

    def test_title_rows_keep_full_length(self) -> None:
        # A truncated title can never join display_title — [:120] must stay gone.
        source = Path(cal.__file__).read_text(encoding="utf-8")
        self.assertNotIn('"title": str(pr.get("title") or "")[:120]', source)

    def test_classifier_default_label_byte_stable(self) -> None:
        # Old note bytes (tool name in the note) stay pinned for the PR path.
        note_absent = cal._classify_tower_pr_failure("MCP error -32602: Tool github.list_prs not found")
        self.assertIn("tower github.list_prs tool-absent", note_absent)
        note_rbac = cal._classify_tower_pr_failure("Forbidden: role 'viewer' has no repository read access")
        self.assertIn("tower github.list_prs RBAC-forbidden", note_rbac)
        # Census path passes its own label — a workflow-runs denial never
        # reports itself as a list_prs failure (false-cause class closed, U6).
        note_wf = cal._classify_tower_pr_failure(
            "MCP error -32602: Tool github.workflow_runs not found", tool_label="github.workflow_runs"
        )
        self.assertIn("tower github.workflow_runs tool-absent", note_wf)
        self.assertNotIn("github.list_prs", note_wf)

    def test_output_validation_rejection_gets_truthful_window_note(self) -> None:
        # Live defect (17:04+08): tower's output-schema validation rejects big
        # windows with "-32602: Output validation error: Tool X has an output
        # schema but no structured content was provided". The old -32602
        # branch misread that as PERMANENT tool-absence (the tool IS in the
        # roster and the call DID land) — a false-cause note (U6). The note
        # must name the window-dependent response-shape instead.
        note = cal._classify_tower_pr_failure(
            "MCP error -32602: Output validation error: Tool github.workflow_runs "
            "has an output schema but no structured content was provided",
            tool_label="github.workflow_runs",
        )
        self.assertIn("output-validation rejection", note)
        self.assertIn("payload-window dependent", note)
        self.assertNotIn("tool-absent", note)
        self.assertNotIn("RBAC-forbidden", note)
        # Default label stays byte-stable for the PR path.
        note_pr = cal._classify_tower_pr_failure(
            "MCP error -32602: Output validation error: Tool github.list_prs "
            "has an output schema but no structured content was provided"
        )
        self.assertIn("tower github.list_prs output-validation rejection", note_pr)

    def test_red_conclusion_set_matches_gh_path_semantics(self) -> None:
        self.assertEqual(
            cal._PR_CHECK_RED_CONCLUSIONS,
            ("failure", "timed_out", "cancelled", "startup_failure"),
        )

    def test_census_transport_carries_429_retry_ladder(self) -> None:
        # Live defect (17:04+08): Render tower burst rate-limiting (HTTP 429,
        # Cloudflare interstitial) turned the census's very first live run
        # into an honest-dark classification — two consecutive 429s observed,
        # the third attempt (6s later) succeeded. The two-tier backoff ladder
        # must stay in the census transport (structural pin).
        source = Path(cal.__file__).read_text(encoding="utf-8")
        self.assertIn("exc.code == 429", source)
        self.assertIn("(0.0, 2.5, 5.0)", source)


if __name__ == "__main__":
    unittest.main()
