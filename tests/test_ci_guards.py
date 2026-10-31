#!/usr/bin/env python3
"""tests/test_ci_guards.py — fail-closed behavioral suite for the #392 CI guards.

Verifies the two constitutional guards mandated by issue #392
("fix(ci): enforce mandatory Claim Gate & Knowledge Sharing Guard in
pipeline.yml"), delivered via WO #395 as byte-exact appendices for the
protected ``.github/`` path:

  - ``claim-guard``              — no claim, no work (AGENTS.md Step 4)
  - ``knowledge-sharing-guard``  — reflection evidence on every PR body

Design (zero-dependency doctrine, dual mode — pytest + stdlib runners):

  - pytest:  pytest tests/test_ci_guards.py
  - stdlib:  python3 tests/test_ci_guards.py   (plain runner, no pytest import)

SSOT extraction: the guard run-blocks are pulled from the LIVE
``.github/workflows/pipeline.yml`` (never duplicated here), materialized
with a stubbed ``gh`` + fixture JSON payloads and executed for real under
bash. The suite therefore tests whatever the maintainers actually applied.

Sequencing honesty: if the guard jobs are not yet present in pipeline.yml
(WO #395 appendices pending application), every guard test SKIPS with a
pointer — absence of a pending handoff is a pending state, not a
regression. The moment the appendices land, the suite activates and
enforces the fail-closed contract permanently.

Every test is offline and deterministic; the only network-adjacent tool
(``gh``) is a local stub reading fixture files.

Contract-era note (oracle sync): the maintainers later evolved BOTH guards
from fail-closed to SELF-HEALING (7c44efd / PR #1459): a missing claim plane
auto-attaches an atomic-claim comment and a missing Reflection Evidence
section auto-injects the canonical snippet — both exit 0 (only a PR that
references NO issue at all still fails closed). Per this file's own SSOT
doctrine ("tests whatever the maintainers actually applied"), the oracles
pin the LANDED contract; the pre-#1459 verbatim ``::error::`` oracle was
retired with the workflow that emitted it (it left 5 red tests on pristine
main — pipeline.yml runs no pytest, the G2 gate gap). tests/ boundary only;
.github/ untouched (admin-owned path).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PIPELINE = REPO_ROOT / ".github" / "workflows" / "pipeline.yml"
PR_TEMPLATE = REPO_ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"

# Landed claim-guard fail-closed remnant (issue #392 acceptance criteria):
# fires only when a PR references NO issue at all — the single remaining
# blocking path after the self-healing era (7c44efd / PR #1459).
CLAIM_ERROR_PREFIX = "::error::PR opened without a prior claim on Issue #"
CLAIM_ERROR_TAIL = ". Per AGENTS.md Step 4 (No claim, no work), claim the issue before creating a branch or PR."
# Retired oracle (was CLAIM_ERROR_ISSUES_PREFIX): the "any referenced issue"
# ::error:: line is unreachable dead code in the landed workflow — the
# self-healing branch always exits 0 before it. Removed per Superior
# Replacement (never pin unreachable behavior).

# Self-healing contract constants (landed via 7c44efd / PR #1459, which
# evolved both guards from fail-closed to auto-repair-and-pass). Byte-exact
# with .github/workflows/pipeline.yml — the SSOT this suite tests.
KS_HEADER_REGEX = "^## Reflection Evidence"
KS_SELFHEAL_WARN = (
    "⚠️ PR body missing '## Reflection Evidence'. "
    "Self-healing: appending canonical reflection..."
)
KS_SELFHEAL_OK = "✅ Auto-injected Reflection Evidence via self-healing."
CLAIM_SELFHEAL_WARN_PREFIX = "⚠️ Unclaimed referenced issue #"
CLAIM_SELFHEAL_OK_PREFIX = "✅ Auto-claimed Issue #"
CLAIM_SELFHEAL_MARKER = "<!-- atomic-claim: issue #"
# Harness value substituted for ${{ github.event.pull_request.number }}.
HARNESS_PR_NUMBER = "6001"
CLAIM_SELFHEAL_LINK = f"Autonomous work linked via PR #{HARNESS_PR_NUMBER}."

# Byte-exact contract with the deployed claim-guard label plane. The plane
# accepts the bridge lifecycle labels (bridge:queued/in-gates/landed) in
# addition to the status labels — oracle re-synced after 4301d9a extended the
# guard without updating this constant (2 tests red on main since then).
CLAIM_JQ_LABEL = (
    'any(.labels[]?; .name == "status:claimed" or .name == "status:in-progress"'
    ' or .name == "bridge:queued" or .name == "bridge:in-gates"'
    ' or .name == "bridge:landed")'
)
CLAIM_JQ_MARKER = 'any(.comments[]?; (.body // "") | contains("<!-- atomic-claim -->"))'

# High fixture numbers — deliberately outside the real issue range.
FX_CLAIMED = 5001  # status:claimed label
FX_ATOMIC = 5002  # <!-- atomic-claim --> comment
FX_UNCLAIMED = 5003  # neither plane (non-claim label only)
FX_MISSING = 5004  # gh lookup fails (no fixture) -> fail-closed
FX_BRIDGE_QUEUED = 5005  # bridge:queued label — active claim plane per 4301d9a

FIXTURE_ISSUES = {
    str(FX_CLAIMED): {"labels": [{"name": "status:claimed"}], "comments": []},
    str(FX_ATOMIC): {
        "labels": [],
        "comments": [{"body": "<!-- atomic-claim -->\n🎯 **Claimed**"}],
    },
    str(FX_UNCLAIMED): {
        "labels": [{"name": "question"}],
        "comments": [{"body": "regular comment"}],
    },
    str(FX_BRIDGE_QUEUED): {"labels": [{"name": "bridge:queued"}], "comments": []},
}

GOOD_BODY = (
    "## Reflection Evidence (why + alternatives_rejected)\n"
    "- **why:** Guards fail closed at PR time so ghost PRs never reach triage.\n"
    "- **alternatives_rejected:**\n"
    "  - server-side push hook — needs admin tokens the bridge must never hold\n"
)


class _Skip(Exception):
    """Stdlib-mode skip signal (pytest path uses pytest.skip instead)."""


def _skip(reason: str) -> None:
    # Under pytest -> real pytest.skip; stdlib mode -> plain _Skip signal.
    if "PYTEST_CURRENT_TEST" in os.environ:
        import pytest

        pytest.skip(reason)
    raise _Skip(reason)


# --------------------------------------------------------------------------- #
# SSOT extraction from the live pipeline.yml (indent-scan; no PyYAML needed)  #
# --------------------------------------------------------------------------- #


def _load_pipeline_text() -> str:
    if not PIPELINE.is_file():
        raise AssertionError(
            f"pipeline.yml missing at {PIPELINE} — constitutional workflow file required"
        )
    return PIPELINE.read_text(encoding="utf-8")


def _extract_job_block(text: str, job_name: str) -> str | None:
    """Return the raw text of a 2-space-indented job key block, or None."""
    lines = text.splitlines()
    key_re = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
    start = None
    for i, ln in enumerate(lines):
        m = key_re.match(ln)
        if m and m.group(1) == job_name:
            start = i
            break
    if start is None:
        return None
    out = [lines[start]]
    for ln in lines[start + 1 :]:
        if key_re.match(ln) or (ln.strip() and not ln[0].isspace()):
            break
        out.append(ln)
    return "\n".join(out)


def _extract_run_script(block: str) -> str | None:
    """Return the decoded `run: |` literal of a job block, or None."""
    lines = block.splitlines()
    for i, ln in enumerate(lines):
        m = re.match(r"^(\s*)run:\s*\|\s*$", ln)
        if not m:
            continue
        indent = len(m.group(1)) + 2
        out: list[str] = []
        pending: list[str] = []
        for l2 in lines[i + 1 :]:
            if l2.strip() == "":
                pending.append("")
                continue
            if len(l2) - len(l2.lstrip()) < indent:
                break
            out.extend(pending)
            pending = []
            out.append(l2[indent:])
        while out and out[-1] == "":
            out.pop()
        return "\n".join(out)
    return None


_PIPELINE_TEXT = ""
CLAIM_BLOCK: str | None = None
KS_BLOCK: str | None = None

try:
    _PIPELINE_TEXT = _load_pipeline_text()
    CLAIM_BLOCK = _extract_job_block(_PIPELINE_TEXT, "claim-guard")
    KS_BLOCK = _extract_job_block(_PIPELINE_TEXT, "knowledge-sharing-guard")
except AssertionError:
    pass  # surfaced as a hard failure by test_pipeline_exists

GUARDS_PRESENT = bool(CLAIM_BLOCK) and bool(KS_BLOCK)
_SKIP_REASON = (
    "claim-guard / knowledge-sharing-guard not yet in .github/workflows/pipeline.yml — "
    "WO #395 appendices pending application (issue #392 handoff)"
)


def _require_guards() -> None:
    if PIPELINE.exists() and not GUARDS_PRESENT:
        _skip(_SKIP_REASON)


# --------------------------------------------------------------------------- #
# Harness: stubbed gh + fixture JSONs + materialization + real bash execution #
# --------------------------------------------------------------------------- #


def _find_bash() -> str:
    if sys.platform == "win32":
        candidates: list[Path] = []
        pf = os.environ.get("PROGRAMFILES")
        if pf:
            candidates.extend(
                [
                    Path(pf) / "Git" / "bin" / "bash.exe",
                    Path(pf) / "Git" / "usr" / "bin" / "bash.exe",
                ]
            )
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            candidates.append(Path(local_app) / "Programs" / "Git" / "bin" / "bash.exe")
        for cand in candidates:
            if cand.is_file():
                return str(cand)
    return shutil.which("bash") or "bash"


class _GuardHarness:
    """Event-context execution rig: stub `gh`, fixture issues, real bash."""

    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ci_guard_test_"))
        self.fixtures = self.root / "fixtures"
        self.fixtures.mkdir()
        shim_dir = self.root / "bin"
        shim_dir.mkdir()
        shim = shim_dir / "gh"
        self.call_log = self.root / "gh_calls.log"
        shim.write_text(
            "#!/bin/bash\n"
            "# gh shim: fixture-backed `issue view`; every invocation is logged\n"
            "# so tests can assert self-healing side effects (comment/edit\n"
            "# attempts) and their arguments. Non-view calls exit 1 — the landed\n"
            "# guards tolerate that via `|| true`, which the suite pins too.\n"
            'args=("$@")\n'
            'echo "${args[*]}" >> "CALL_LOG"\n'
            'if [ "${args[0]}" = "issue" ] && [ "${args[1]}" = "view" ]; then\n'
            '  num="${args[2]}"\n'
            '  f="FIXTURE_DIR/issue_${num}.json"\n'
            '  if [ -f "$f" ]; then cat "$f"; exit 0; fi\n'
            "  exit 1\n"
            "fi\n"
            "exit 1\n"
            .replace("CALL_LOG", str(self.call_log).replace("\\", "/"))
            .replace("FIXTURE_DIR", str(self.fixtures).replace("\\", "/")),
            encoding="utf-8",
        )
        shim.chmod(0o755)
        if not shutil.which("jq"):
            jq_shim = shim_dir / "jq"
            py_exe = sys.executable.replace("\\", "/")
            jq_shim.write_text(
                f'#!/bin/bash\n"{py_exe}" -c \'\n'
                "import sys, json\n"
                "try:\n"
                "    data = json.load(sys.stdin)\n"
                '    expr = sys.argv[-1] if len(sys.argv) > 1 else ""\n'
                '    if "labels" in expr:\n'
                '        targets = {"status:claimed", "status:in-progress", "bridge:queued", "bridge:in-gates", "bridge:landed"}\n'
                '        labels = [l.get("name") for l in data.get("labels", []) if isinstance(l, dict)]\n'
                "        sys.exit(0 if any(l in targets for l in labels) else 1)\n"
                '    if "atomic-claim" in expr:\n'
                '        comments = data.get("comments", [])\n'
                '        sys.exit(0 if any("<!-- atomic-claim -->" in (c.get("body") or "") for c in comments if isinstance(c, dict)) else 1)\n'
                "    sys.exit(0)\n"
                "except Exception:\n"
                "    sys.exit(1)\n"
                '\' "$@"\n',
                encoding="utf-8",
            )
            jq_shim.chmod(0o755)
        for num, obj in FIXTURE_ISSUES.items():
            (self.fixtures / f"issue_{num}.json").write_text(
                json.dumps(obj), encoding="utf-8"
            )

    def materialize(self, script: str) -> str:
        """Substitute every `${{ }}` expression; fail closed if any remain."""
        script = script.replace(
            "${{ github.repository }}", "Supremeai-bd/supremeai-open"
        )
        script = script.replace("${{ secrets.GITHUB_TOKEN }}", "testtoken")
        script = script.replace(
            "${{ github.event.pull_request.number }}", HARNESS_PR_NUMBER
        )
        if "${{" in script:
            i = script.index("${{")
            raise AssertionError(
                f"unsubstituted expression remains: {script[i : i + 60]!r}"
            )
        return script

    def gh_calls(self) -> str:
        """Everything the stubbed gh was asked to do (self-heal side effects)."""
        try:
            return self.call_log.read_text(encoding="utf-8")
        except OSError:
            return ""

    def run(self, script_text: str, **env: str) -> subprocess.CompletedProcess:
        path = self.root / "scenario.sh"
        path.write_text(self.materialize(script_text), encoding="utf-8")
        bin_dir = str(self.root / "bin").replace("\\", "/")
        e = {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(self.root).replace("\\", "/"),
            "LANG": "C.UTF-8",
            "GH_TOKEN": "testtoken",
        }
        e.update(env)
        return subprocess.run(
            [_find_bash(), str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=e,
            timeout=120,
            check=False,
        )

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def _claim_env(num: int, labels: str = "", head_ref: str | None = None) -> dict:
    return {
        "PR_TITLE": f"feat: x (Closes #{num})",
        "PR_BODY": f"Closes #{num}",
        "PR_LABELS": labels,
        "HEAD_REF": head_ref or f"contributor/issue-{num}",
    }


# --------------------------------------------------------------------------- #
# Static contract tests (structure of the applied jobs)                       #
# --------------------------------------------------------------------------- #


def test_pipeline_exists():
    assert PIPELINE.is_file(), f"pipeline.yml missing at {PIPELINE}"


def test_guards_present_in_pipeline():
    _require_guards()
    assert CLAIM_BLOCK and CLAIM_BLOCK.lstrip().startswith("claim-guard:")
    assert KS_BLOCK and KS_BLOCK.lstrip().startswith("knowledge-sharing-guard:")


def test_claim_guard_pr_only_zero_checkout_and_timeout():
    _require_guards()
    b = CLAIM_BLOCK or ""
    assert "github.event_name == 'pull_request'" in b, "guard must be PR-only"
    assert "timeout-minutes: 3" in b, "house style: fast zero-checkout guard"
    assert "actions/checkout" not in b, "zero-checkout: event-context env only"


def test_claim_guard_permissions_and_claim_planes():
    _require_guards()
    b = CLAIM_BLOCK or ""
    assert re.search(r"permissions:\s*\n\s+issues:\s*read", b), "needs issues:read only"
    assert CLAIM_JQ_LABEL in b, "label plane (CLAIMED_LABELS registry) missing"
    assert CLAIM_JQ_MARKER in b, "comment plane (<!-- atomic-claim -->) missing"


def test_claim_guard_exact_error_string():
    _require_guards()
    b = CLAIM_BLOCK or ""
    assert CLAIM_ERROR_PREFIX in b
    assert CLAIM_ERROR_TAIL in b, "issue #392 mandates this exact tail verbatim"


def test_claim_guard_escape_hatch_order():
    _require_guards()
    b = CLAIM_BLOCK or ""
    assert "guard-exempt" in b, "admin escape hatch required by issue #392"
    assert b.index("guard-exempt") < b.index("dependabot"), (
        "exempt check must come first"
    )
    assert "status:claimed" in b[b.index("guard-exempt") :], (
        "claim planes follow the hatch"
    )


def test_ks_guard_pr_only_zero_checkout_and_timeout():
    _require_guards()
    b = KS_BLOCK or ""
    assert "github.event_name == 'pull_request'" in b
    assert "timeout-minutes: 3" in b
    assert "actions/checkout" not in b


def test_ks_guard_self_heal_contract():
    # Landed (7c44efd / #1459): the KS guard self-heals a missing Reflection
    # Evidence section instead of blocking. The pre-#1459 verbatim ::error::
    # oracle was retired with the workflow that emitted it (Invariant 3:
    # never pin behavior the SSOT no longer exhibits).
    _require_guards()
    b = KS_BLOCK or ""
    assert KS_HEADER_REGEX in b, "landed header-presence check must stay"
    assert KS_SELFHEAL_WARN in b and KS_SELFHEAL_OK in b, (
        "self-healing messages must match the landed workflow verbatim"
    )
    assert "gh pr edit" in b, "self-heal must attempt the PR body auto-injection"
    assert "**why:**" in b and "**alternatives_rejected:**" in b, (
        "canonical injected snippet carries the #392 knowledge fields"
    )
    assert "guard-exempt" in b, "admin escape hatch required by issue #392"


# --------------------------------------------------------------------------- #
# Behavioral matrix (real bash execution; issue #392 acceptance criteria)     #
# --------------------------------------------------------------------------- #


def _claim_script(h: _GuardHarness) -> str:
    block = CLAIM_BLOCK or ""
    script = _extract_run_script(block)
    if script is None:
        raise AssertionError("claim-guard run literal not extractable")
    return script


def _ks_script(h: _GuardHarness) -> str:
    block = KS_BLOCK or ""
    script = _extract_run_script(block)
    if script is None:
        raise AssertionError("knowledge-sharing-guard run literal not extractable")
    return script


def test_claim_guard_behavior_matrix():
    _require_guards()
    h = _GuardHarness()
    try:
        script = _claim_script(h)
        cases = [
            ("claim label passes", _claim_env(FX_CLAIMED), 0, None),
            (
                "bridge:queued label passes (4301d9a plane)",
                _claim_env(FX_BRIDGE_QUEUED),
                0,
                None,
            ),
            ("atomic-claim comment passes", _claim_env(FX_ATOMIC), 0, None),
            # Self-healing era (7c44efd): an unclaimed referenced issue no
            # longer blocks — the guard auto-attaches the atomic-claim comment
            # and passes; gh failure is tolerated via `|| true`.
            (
                "unclaimed self-heals with atomic-claim comment",
                _claim_env(FX_UNCLAIMED),
                0,
                f"issue comment {FX_UNCLAIMED}",
            ),
            (
                "gh lookup failure self-heals instead of blocking",
                _claim_env(FX_MISSING),
                0,
                f"issue comment {FX_MISSING}",
            ),
            (
                "guard-exempt bypasses",
                _claim_env(FX_UNCLAIMED, labels="guard-exempt"),
                0,
                None,
            ),
            (
                "bot branch bypasses",
                _claim_env(FX_UNCLAIMED, head_ref="dependabot/npm_and_yarn/pkg-1.2.3"),
                0,
                None,
            ),
            # No issue ref: the guard echoes the literal #<num> template form.
            # The single remaining fail-closed path post-self-healing.
            (
                "no issue reference fails closed",
                {
                    "PR_TITLE": "feat: nothing",
                    "PR_BODY": "no refs here",
                    "PR_LABELS": "",
                    "HEAD_REF": "agent/work-1",
                },
                1,
                None,
            ),
        ]
        for name, env, want, want_gh_call in cases:
            log_before = h.gh_calls()
            r = h.run(script, **env)
            assert r.returncode == want, (
                f"{name}: exit {r.returncode} != {want}; out={r.stdout[:200]!r}"
            )
            if want_gh_call:
                delta = h.gh_calls()[len(log_before) :]
                assert want_gh_call in delta, (
                    f"{name}: expected gh self-heal call {want_gh_call!r}; "
                    f"log delta={delta[:240]!r}"
                )
                assert CLAIM_SELFHEAL_WARN_PREFIX in r.stdout, (
                    f"{name}: self-heal warning missing; out={r.stdout[:240]!r}"
                )
                assert CLAIM_SELFHEAL_OK_PREFIX in r.stdout, (
                    f"{name}: self-heal confirmation missing; out={r.stdout[:240]!r}"
                )
            elif want == 0:
                assert CLAIM_SELFHEAL_WARN_PREFIX not in r.stdout, (
                    f"{name}: unexpected self-heal attempt; out={r.stdout[:240]!r}"
                )
            if want != 0:
                assert CLAIM_ERROR_PREFIX in r.stdout and CLAIM_ERROR_TAIL in r.stdout, (
                    f"{name}: exact issue-#392 error not emitted; out={r.stdout[:240]!r}"
                )
        # Side-effect contract: the auto-claim body carries the atomic-claim
        # marker AND the PR link with the materialized event-context number.
        calls = h.gh_calls()
        assert CLAIM_SELFHEAL_MARKER in calls and CLAIM_SELFHEAL_LINK in calls, (
            f"atomic-claim self-heal body missing marker/link; calls={calls[:300]!r}"
        )
    finally:
        h.close()


def test_ks_guard_behavior_matrix():
    _require_guards()
    h = _GuardHarness()
    try:
        script = _ks_script(h)

        def body(section: str) -> str:
            return f"## Summary\n{section}"

        header = "## Reflection Evidence (why + alternatives_rejected)"
        cases = [
            # (name, pr_body, want_exit, want_selfheal) — landed contract:
            # header PRESENCE passes; header ABSENCE self-heals and passes.
            # The pre-#1459 placeholder-depth checks are no longer enforced
            # by the workflow; the oracles follow the SSOT (Invariant 3).
            ("valid body passes", GOOD_BODY, 0, False),
            ("missing section self-heals", body("nothing here"), 0, True),
            (
                "empty why passes (header-presence contract)",
                f"{header}\n- **why:**\n- **alternatives_rejected:**\n  - a\n",
                0,
                False,
            ),
            (
                "placeholder why passes (header-presence contract)",
                f"{header}\n- **why:** <replace: rationale>\n- **alternatives_rejected:**\n  - real reason\n",
                0,
                False,
            ),
            (
                "inline alternatives passes",
                f"{header}\n- **why:** because\n- **alternatives_rejected:** did it inline instead\n",
                0,
                False,
            ),
            (
                "empty alternatives passes (header-presence contract)",
                f"{header}\n- **why:** because\n- **alternatives_rejected:**\n",
                0,
                False,
            ),
            (
                "placeholder alternatives passes (header-presence contract)",
                f"{header}\n- **why:** because\n- **alternatives_rejected:**\n  - <replace: alternative approach 1, rejected because ...>\n",
                0,
                False,
            ),
        ]
        edit_attempts = 0
        for name, pr_body, want, want_heal in cases:
            log_before = h.gh_calls()
            r = h.run(
                script, PR_BODY=pr_body, PR_LABELS="", HEAD_REF="contributor/issue-392"
            )
            assert r.returncode == want, (
                f"{name}: exit {r.returncode} != {want}; out={r.stdout[:200]!r}"
            )
            delta = h.gh_calls()[len(log_before) :]
            assert ("pr edit" in delta) == want_heal, (
                f"{name}: self-heal pr-edit attempt mismatch; delta={delta[:200]!r}"
            )
            if want_heal:
                assert KS_SELFHEAL_WARN in r.stdout and KS_SELFHEAL_OK in r.stdout, (
                    f"{name}: self-heal messages missing; out={r.stdout[:240]!r}"
                )
                assert HARNESS_PR_NUMBER in delta, (
                    f"{name}: auto-injection must target the event-context PR; "
                    f"delta={delta[:200]!r}"
                )
                edit_attempts += 1
            else:
                assert "✅ Reflection Evidence present." in r.stdout, (
                    f"{name}: pass confirmation missing; out={r.stdout[:240]!r}"
                )
        assert edit_attempts >= 1, (
            "at least one self-heal case must attempt the auto-injection"
        )

        # escape hatches (unchanged by the self-healing era)
        r = h.run(script, PR_BODY="empty", PR_LABELS="guard-exempt", HEAD_REF="agent/x")
        assert r.returncode == 0, "guard-exempt must bypass reflection check"
        r = h.run(script, PR_BODY="", PR_LABELS="", HEAD_REF="github-actions[bot]/auto")
        assert r.returncode == 0, "bot branch must bypass reflection check"
    finally:
        h.close()


def test_combined_claim_and_reflection_pass_together():
    # Issue #392 acceptance: claimed issue + valid reflection -> both guards pass.
    _require_guards()
    h = _GuardHarness()
    try:
        r1 = h.run(_claim_script(h), **_claim_env(FX_CLAIMED))
        r2 = h.run(
            _ks_script(h),
            PR_BODY=GOOD_BODY,
            PR_LABELS="",
            HEAD_REF="contributor/issue-392",
        )
        assert r1.returncode == 0 and r2.returncode == 0, (
            f"combined pass failed: claim={r1.returncode}, reflection={r2.returncode}"
        )
    finally:
        h.close()


def test_unfilled_template_body_passes_header_contract():
    # Tier-4 dogfood, self-healing era: the template's own unfilled body
    # carries the required section HEADER, so the landed header-presence
    # guard passes it WITHOUT any self-healing side effect. (Placeholder-
    # depth enforcement was retired with the fail-closed contract; note the
    # template's HTML comment still claims fail-closed — .github/ is
    # admin-owned, so the observation lives here.)
    _require_guards()
    if not PR_TEMPLATE.is_file():
        _skip(".github/PULL_REQUEST_TEMPLATE.md not yet applied (WO #395 appendix C)")
    tpl = PR_TEMPLATE.read_text(encoding="utf-8")
    unfilled = re.sub(r"<!--.*?-->", "", tpl, flags=re.DOTALL)
    unfilled = re.sub(r"\n{3,}", "\n\n", unfilled).strip()
    h = _GuardHarness()
    try:
        log_before = h.gh_calls()
        r = h.run(
            _ks_script(h),
            PR_BODY=unfilled,
            PR_LABELS="",
            HEAD_REF="contributor/issue-392",
        )
        assert r.returncode == 0, (
            "template body carries the required header -> guard passes"
        )
        assert "✅ Reflection Evidence present." in r.stdout, (
            f"header-presence pass confirmation missing; out={r.stdout[:240]!r}"
        )
        assert h.gh_calls() == log_before, "no self-heal side effect expected"
    finally:
        h.close()


# --------------------------------------------------------------------------- #
# Dual-mode runner (stdlib path; pytest discovers test_* above directly)      #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    fns = [
        v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)
    ]
    failed = skipped = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS | {fn.__name__}")
        except _Skip as exc:
            skipped += 1
            print(f"  SKIP | {fn.__name__}: {exc}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL | {fn.__name__}: {exc}")
        except (
            RuntimeError,
            ValueError,
            TypeError,
            OSError,
            TimeoutError,
            ConnectionError,
            AttributeError,
            KeyError,
            ImportError,
            ModuleNotFoundError,
        ) as exc:
            failed += 1
            print(f"  ERROR | {fn.__name__}: {type(exc).__name__}: {exc}")
    passed = len(fns) - failed - skipped
    if skipped:
        print(f"{passed}/{len(fns)} tests passed ({skipped} skipped, guards pending)")
    else:
        print(f"{passed}/{len(fns)} tests passed")
    sys.exit(1 if failed else 0)
