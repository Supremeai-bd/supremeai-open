"""Security scorer — data exposure risk (#4047).

বাংলা: security score = inverse of data exposure risk। higher score = safer।
"""

from __future__ import annotations

from ..models import DimensionScore, ScoreDimension


def score_security(
    data_exposure_risk: float,
    pii_redaction_enabled: bool = True,
    sandbox_isolation: bool = True,
    egress_restricted: bool = False,
    benchmark_run_id: str = "",
) -> DimensionScore:
    """Score security from data exposure risk + hardening flags.

    Args:
        data_exposure_risk: 0.0-1.0 (0 = no risk, 1 = high risk)
        pii_redaction_enabled: whether PII redaction is on (#3415)
        sandbox_isolation: whether provider runs in isolated sandbox
        egress_restricted: whether network egress is restricted
        benchmark_run_id: for evidence trail

    Returns:
        DimensionScore with normalized score (lower risk = higher score)
    """
    if not 0.0 <= data_exposure_risk <= 1.0:
        raise ValueError(f"data_exposure_risk must be 0.0-1.0, got {data_exposure_risk}")

    # Base: inverse of risk
    score = 1.0 - data_exposure_risk

    # Bonuses for hardening (+0.05 each, capped at 1.0)
    if pii_redaction_enabled:
        score = min(1.0, score + 0.05)
    if sandbox_isolation:
        score = min(1.0, score + 0.05)
    if egress_restricted:
        score = min(1.0, score + 0.05)

    return DimensionScore(
        dimension=ScoreDimension.SECURITY,
        score=score,
        raw_value=data_exposure_risk,
        unit="ratio",
        evidence={
            "data_exposure_risk": data_exposure_risk,
            "pii_redaction_enabled": pii_redaction_enabled,
            "sandbox_isolation": sandbox_isolation,
            "egress_restricted": egress_restricted,
            "benchmark_run_id": benchmark_run_id,
        },
    )
