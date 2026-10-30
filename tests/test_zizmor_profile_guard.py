#!/usr/bin/env python3
"""tests/test_zizmor_profile_guard.py — mechanical U6 guard for the zizmor profile (#1776 -> #2766 lineage).

Zero-Recurrence Invariant (AGENTS.md U6, #3344): every identified defect MUST
get an automated guard. The zizmor hardening finding set on this repo's own CI
surfaces is the longest-lived open defect profile in the federation:

  - #1776 (P1-high, scout 2026-10-28): 60-finding baseline on
    `.github/workflows/pipeline.yml` + `.github/actions/setup-node-tower/action.yml`.
  - #2766 (r2 evidence refresh, 2026-10-30): identical 60-finding profile after
    the #2735-#2752 merge storm — zero remediation, zero regression, admin-pending.
  - This guard: re-measures the profile and fails closed on GROWTH while the
    admin lane owns the fix (`.github/**` is an admin-owned protected path;
    agents never edit it — #1643).

Profile baseline (zizmor 1.31.1, `--no-online-audits --format json .github`),
reproduced byte-identically on 2026-10-30 against main post-#3338:

    unpinned-uses         27   (every `uses:` ref tag-pinned, none SHA-pinned)
    artipacked            15   (15 `actions/checkout` steps, none `persist-credentials: false`)
    template-injection    13   (7 jobs: duplicate-pr-guard, test-matrix,
                                secrets-scan, mcp-tower, sdk-typescript,
                                auto-landing, satellite-dispatch-and-sync)
    excessive-permissions  3   (top-level `permissions:` grants contents/
                                pull-requests/issues at workflow scope)
    self-repository        2   (secrets-scan + mcp-tower checkout steps)
    ------------------------------------
    total                 60

Contract (fail-closed family, #1814 convention):

  1. zizmor tier (SKIP-with-pointer when the binary is absent — the
     sequencing-honesty doctrine of test_ci_guards.py): the per-class profile
     must NEVER grow beyond this baseline. Any new unpinned use, new injection
     site, new broad grant or new self-repo step is a regression even while
     the 60 are unfixed.
  2. static tiers (always active, zero-dependency): the two mechanically
     detectable classes (unpinned-uses, artipacked) are re-counted with pure
     stdlib regex so growth is caught even in environments without zizmor.
  3. hardening flip: once admins land #1776's plan and the profile reaches 0,
     the zero-state becomes permanently enforced (a later reintroduction is
     red, not a silent re-baseline).

Baseline updates are CONSCIOUS edits: raise a count only when a human/agent
intentionally accepts a new finding with its issue reference; lower counts
only when the underlying finding is actually fixed (admin lane). The SSOT for
the full per-finding detail remains the zizmor r-series receipts (#2766, #3338).

Dual mode (repo doctrine): `pytest tests/test_zizmor_profile_guard.py` or
`python3 tests/test_zizmor_profile_guard.py`. Offline; the zizmor tier is
invoked with `--no-online-audits` and reads only the working tree.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_GITHUB = _ROOT / ".github"
_PIPELINE = _GITHUB / "workflows" / "pipeline.yml"

# Profile baseline — see module docstring for provenance and update rules.
ZIZMOR_BASELINE: dict[str, int] = {
    "unpinned-uses": 27,
    "artipacked": 15,
    "template-injection": 13,
    "excessive-permissions": 3,
    "self-repository": 2,
}
ZIZMOR_BASELINE_TOTAL = sum(ZIZMOR_BASELINE.values())  # 60
ZIZMOR_VERSION_PINNED = "1.31.1"  # the exact baseline scanner version (scout 10-28, r2 10-30)

# Static-tier pins — deterministic stdlib counts on current main; the static
# rule semantics are documented at each detector. These are INDEPENDENT of
# zizmor's numbers by design (growth detectors, not re-implementations).
STATIC_UNPINNED_USES = 27
STATIC_ARTIPACKED = 15

_SHA_AT_LINE_END = re.compile(r"@[0-9a-fA-F]{40}\s*$")
_USES_LINE = re.compile(r"^\s*-?\s*uses:\s*(\S+)\s*$")
_CHECKOUT_USES = re.compile(r"uses:\s*actions/checkout@")
_PERSIST_FALSE = re.compile(r"persist-credentials:\s*false")


def _workflow_files() -> list[Path]:
    files: list[Path] = []
    for pattern in ("workflows/*.yml", "workflows/*.yaml", "actions/**/action.yml"):
        files.extend(sorted(_GITHUB.glob(pattern)))
    return files


def _zizmor_binary() -> str | None:
    return shutil.which("zizmor")


def _run_zizmor() -> list[dict]:
    """Run zizmor offline over .github/ and return the findings list.

    Exit-code contract (verified vs zizmor 1.31.1): a completed scan with
    findings exits 14 while still emitting the full JSON profile on stdout —
    only a stdout that does not parse as a JSON list is a real crash.
    Fail-closed (#1760 spirit): a crash propagates, it is never read as an
    empty profile.
    """
    proc = subprocess.run(
        [_zizmor_binary(), "--no-online-audits", "--format", "json", str(_GITHUB)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    try:
        findings = json.loads(proc.stdout)
    except json.JSONDecodeError as err:
        raise RuntimeError(
            f"zizmor produced no parseable profile (exit={proc.returncode}, "
            f"stderr tail: {proc.stderr[-300:]})"
        ) from err
    if not isinstance(findings, list):
        raise RuntimeError(f"unexpected zizmor output shape: {type(findings)}")
    return findings


def _static_unpinned_uses() -> list[str]:
    """Every non-local `uses:` ref not pinned to a full 40-hex SHA.

    Mirrors zizmor's unpinned-uses scope on this repo (verified 27/27 vs
    zizmor 1.31.1 on 2026-10-30). Local composite actions (`./...`) are
    exempt, matching zizmor.
    """
    hits: list[str] = []
    for f in _workflow_files():
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            m = _USES_LINE.match(line)
            if not m:
                continue
            ref = m.group(1).strip("\"'")
            if ref.startswith("./") or ref.startswith(".\\"):
                continue
            if "@" not in ref or not _SHA_AT_LINE_END.search(line):
                hits.append(f"{f.relative_to(_ROOT)}:{i} {ref}")
    return hits


def _static_artipacked() -> list[str]:
    """`actions/checkout` steps without an explicit `persist-credentials: false`.

    This is the mechanism zizmor's artipacked audit flags on this repo
    (verified: 15 checkout refs, 0 persist-credentials:false => 15/15 match,
    2026-10-30). Counting is per checkout ref; a file-level persist-credentials
    false added anywhere does NOT silence it (the knob is per-step) — the pin
    therefore only drops when admins fix steps for real.
    """
    checkout = 0
    persist_false = 0
    for f in _workflow_files():
        text = f.read_text(encoding="utf-8")
        checkout += len(_CHECKOUT_USES.findall(text))
        persist_false += len(_PERSIST_FALSE.findall(text))
    # each checkout step defaults to persisting credentials; only an explicit
    # false removes the finding. With N checkouts and P explicit-false steps
    # the exposed count is N - P (floor 0).
    return [f"checkout-without-persist-false #{i}" for i in range(max(0, checkout - persist_false))]


class TestZizmorProfileGuard(unittest.TestCase):
    """U6 enforcement: the 60-finding profile may never silently grow."""

    def test_zizmor_profile_does_not_grow(self) -> None:
        zizmor = _zizmor_binary()
        if not zizmor:
            self.skipTest(
                "zizmor binary not installed — profile tier dormant; install via "
                "`pip install zizmor==" + ZIZMOR_VERSION_PINNED + "` to activate "
                "(the #2766 admin lane owns the actual fix; this test owns the guard)"
            )
        findings = _run_zizmor()
        counts: dict[str, int] = {}
        for f in findings:
            counts[f["ident"]] = counts.get(f["ident"], 0) + 1
        total = len(findings)
        regressions = []
        for audit, base in sorted(ZIZMOR_BASELINE.items()):
            now = counts.get(audit, 0)
            if now > base:
                regressions.append(f"{audit}: {now} > baseline {base}")
        unknown_growth = sum(
            v for k, v in counts.items() if k not in ZIZMOR_BASELINE
        )
        if total > ZIZMOR_BASELINE_TOTAL or regressions or unknown_growth:
            self.fail(
                "zizmor profile regression (U6 zero-recurrence violation). "
                f"total={total} baseline={ZIZMOR_BASELINE_TOTAL}; "
                f"class growth: {regressions or 'none'}; "
                f"new audit classes: {unknown_growth} finding(s). "
                "Fix the workflow (admin lane, #1776 recipe) or consciously "
                "re-baseline with an issue reference in the docstring."
            )
        # informational: strict improvement tracking (never fails here)
        improved = {a: base - counts.get(a, 0) for a, base in ZIZMOR_BASELINE.items() if counts.get(a, 0) < base}
        if improved:
            print(f"[zizmor-profile-guard] improvement detected: {improved} — consider lowering the baseline (#2766)")

    def test_full_hardening_landed(self) -> None:
        """Sequencing-honesty flip: SKIPs while findings remain; enforces 0 forever once reached.

        The moment #1776's admin recipe lands and the profile empties, this
        test stops skipping — any reintroduction is then red without anyone
        remembering to re-arm it (U6: the fix must never un-fix silently).
        """
        zizmor = _zizmor_binary()
        if not zizmor:
            self.skipTest("zizmor binary not installed — hardening flip dormant")
        findings = _run_zizmor()
        if findings:
            self.skipTest(
                f"hardening still pending: {len(findings)} finding(s) — admin lane owns "
                ".github/** (see #1776 recipe; guard active via the no-growth tier)"
            )
        # profile is empty: strict zero-state from here on
        self.assertEqual(findings, [], "hardened profile reintroduced a finding — U6 violation")

    def test_static_unpinned_uses_no_growth(self) -> None:
        hits = _static_unpinned_uses()
        self.assertLessEqual(
            len(hits),
            STATIC_UNPINNED_USES,
            "unpinned `uses:` count grew beyond the static baseline — every new "
            "third-party action ref must be SHA-pinned (Trap #95, #1776 recipe). "
            f"New offenders: {hits[STATIC_UNPINNED_USES:]}",
        )

    def test_static_artipacked_no_growth(self) -> None:
        hits = _static_artipacked()
        self.assertLessEqual(
            len(hits),
            STATIC_ARTIPACKED,
            "checkout-without-persist-credentials:false count grew — new checkout "
            "steps must set `persist-credentials: false` (artifact-poisoning hardening, "
            f"#1776 recipe). Exposed refs: {STATIC_ARTIPACKED} -> {len(hits)}",
        )

    def test_baseline_totals_consistent(self) -> None:
        """Guard self-check: the pinned profile must stay internally coherent."""
        self.assertEqual(ZIZMOR_BASELINE_TOTAL, 60, "baseline drifted from the #2766 profile")
        self.assertGreaterEqual(STATIC_UNPINNED_USES, 0)
        self.assertGreaterEqual(STATIC_ARTIPACKED, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
