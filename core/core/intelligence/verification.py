from __future__ import annotations

import ast
from collections.abc import Callable
from typing import Any

from .models import VerificationResult


class VerificationEngine:
    """Evidence facade; never claims confidence when checks cannot run."""

    def verify_text(self, output: str, *, claims: list[str] | None = None) -> VerificationResult:
        evidence: list[dict[str, Any]] = [{"kind": "non_empty", "passed": bool(output.strip())}]
        contradictions = ["Output is empty"] if not output.strip() else []
        if claims:
            for claim in claims:
                passed = claim.casefold() in output.casefold()
                evidence.append({"kind": "claim_presence", "claim": claim, "passed": passed})
                if not passed:
                    contradictions.append(f"Claim not supported by output: {claim}")
        confidence = 0.0 if contradictions else 0.75
        return VerificationResult(
            status="contradicted" if contradictions else "verified",
            confidence=confidence,
            evidence=evidence,
            contradictions=contradictions,
        )

    def verify_python(self, source: str) -> VerificationResult:
        try:
            ast.parse(source)
        except SyntaxError as exc:
            return VerificationResult(
                status="contradicted",
                confidence=0,
                evidence=[{"kind": "ast_parse", "passed": False}],
                contradictions=[str(exc)],
            )
        return VerificationResult(
            status="verified", confidence=0.8, evidence=[{"kind": "ast_parse", "passed": True}]
        )

    def run_registered_check(self, check: Callable[[], bool], name: str) -> VerificationResult:
        try:
            passed = bool(check())
        except Exception as exc:
            return VerificationResult(
                status="degraded",
                confidence=0,
                degraded=True,
                evidence=[{"kind": "registered_check", "name": name, "passed": False}],
                contradictions=[f"Check unavailable: {exc}"],
            )
        return VerificationResult(
            status="verified" if passed else "contradicted",
            confidence=0.9 if passed else 0,
            evidence=[{"kind": "registered_check", "name": name, "passed": passed}],
            contradictions=[] if passed else [f"Registered check failed: {name}"],
        )


# Issue #895: contract alias — `backend/tests/core/test_security_and_intelligence_contracts.py`
# `VerifierEngine` নামে import করে, কিন্তু এই মডিউলে class নাম `VerificationEngine`।
# একই evidence facade — নামটা শুধু contract-এর সাথে match করার জন্য alias দেওয়া হলো।
VerifierEngine = VerificationEngine
