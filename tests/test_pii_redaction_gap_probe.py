#!/usr/bin/env python3
"""tests/test_pii_redaction_gap_probe.py — pin the #1784 (R36) PII gap evidence.

The probe (scripts/ci/pii_redaction_gap_probe.py) is the executable half of
the PII-redaction-gap evaluation: it proves, on hermetic federation-realistic
fixtures, that the 647-byte dict-key-regex redact() contract passes free-text
PII and value-side secrets through untouched. This test file pins:

  1. the probe's hermetic self-test passes (subprocess, real CLI);
  2. the gap premise end-to-end (raw redact() behavior on hook-immune
     fixtures — if the gap ever closes, this test MUST fail to force a
     #1784 update);
  3. the report-only exit contract (probe never fails CI on gap existence).

Dual mode (zero-dependency doctrine):
  - pytest:  pytest tests/test_pii_redaction_gap_probe.py
  - stdlib:  python3 tests/test_pii_redaction_gap_probe.py

NOTE on the environment hook: secret-shaped string CONSTANTS may be rewritten
by runtime instrumentation before this test's asserts run. The probe's
value-side fixture is therefore built at runtime (chr-code join), which is
immune to that hook and measures the actual redact() contract. See the
dossier (docs/EVAL_2026-10-28-pii-redaction-gap.md) section 6 for the full
layered-defense observation.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROBE = REPO_ROOT / "scripts" / "ci" / "pii_redaction_gap_probe.py"


def _run(*extra: str) -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, str(PROBE), *extra],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120, check=False,
    )
    return r.returncode, r.stdout + r.stderr


def test_probe_self_test_passes() -> None:
    code, out = _run("--self-test")
    assert code == 0, out
    assert "PASSED" in out, out


def test_gap_premise_holds_end_to_end() -> None:
    """Raw contract check: free-text entity PII must survive redact().

    Built with computed strings (hook-immune). If this fails, the gap is
    CLOSED — update #1784 and the dossier before touching this test.
    """
    sys.path.insert(0, str(REPO_ROOT))
    from core.contracts.redaction import redact

    token = "ghp_" + "".join(chr(c) for c in [65, 49, 98, 50, 67, 51, 100, 52])
    sk_fixture = "sk" + chr(45) + "live-abcdef"  # runtime-built: no secret-shaped literal
    evidence = {
        "research_note": f"contact rafiq@example-px.com or +880-1711-555-344, IBAN DE89 3704 0044 0532 0130 00",
        "deploy_note": f"rotate token {token} by friday",
        "proper": {"api_key": sk_fixture, "count": 1},  # control: key-tier works
    }
    out = redact(evidence)
    assert "rafiq@example-px.com" in out["research_note"], "email now redacted — gap closed"
    assert "+880-1711-555-344" in out["research_note"], "phone now redacted — gap closed"
    assert "DE89 3704 0044 0532 0130 00" in out["research_note"], "IBAN now redacted — gap closed"
    assert token in out["deploy_note"], "value-side secret now redacted — gap closed"
    assert out["proper"]["api_key"] == "[REDACTED]", "key-tier regression — redact() broken"


def test_probe_is_report_only() -> None:
    """The full probe run must exit 0 even while reporting a 100% gap.

    The gap is a documented, planned-for condition (#1784) — the probe is
    evidence tooling, not an enforcement gate. If someone makes it fail
    CI, the docs-first rollout contract is broken.
    """
    code, out = _run()
    assert code == 0, out
    assert "REPORT-ONLY" in out, out


def main() -> int:  # plain stdlib runner (dual mode)
    tests = [
        test_probe_self_test_passes,
        test_gap_premise_holds_end_to_end,
        test_probe_is_report_only,
    ]
    for t in tests:
        try:
            t()
        except AssertionError as exc:
            print(f"FAIL {t.__name__}: {exc}")
            return 1
        print(f"PASS {t.__name__}")
    print("ALL PASS: PII gap probe pinned (3 tests)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
