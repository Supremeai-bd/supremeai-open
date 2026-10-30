from pathlib import Path
import pytest
from scripts.agents.incident_fingerprint import (
    compute_incident_fingerprint,
    extract_incident_fingerprint,
    format_incident_marker,
    IncidentRegistrySSOT,
    check_pr_deduplication,
)


def test_incident_fingerprint_deterministic():
    fp1 = compute_incident_fingerprint(
        "production", "render-primary", "update_failed", "deployment", "render-deploy"
    )
    fp2 = compute_incident_fingerprint(
        "PRODUCTION ", "render-primary", "Update_Failed", "deployment", "render-deploy"
    )
    assert fp1 == fp2, "Fingerprint must be deterministic and case/whitespace-insensitive"


def test_incident_fingerprint_isolates_different_causes():
    fp1 = compute_incident_fingerprint(
        "production", "redis", "quota_exhausted", "upstash", "redis-quota"
    )
    fp2 = compute_incident_fingerprint(
        "production", "supabase", "schema_drift", "usage_metrics", "supabase-schema"
    )
    assert fp1 != fp2, "Different incidents must have distinct fingerprints"


def test_incident_marker_roundtrip():
    fp = compute_incident_fingerprint(
        "production", "render-primary", "update_failed", "deployment", "render-deploy"
    )
    marker = format_incident_marker(fp)
    assert f"<!-- incident-fp:{fp} -->" in marker

    body = f"{marker}\n\n## Incident Details\nDeploy degraded."
    extracted = extract_incident_fingerprint(body)
    assert extracted == fp


def test_incident_registry_atomic_winner(tmp_path: Path):
    reg_file = tmp_path / "test_incident_registry.json"
    registry = IncidentRegistrySSOT(reg_file)

    # First agent claims
    is_winner, record = registry.register_or_corroborate(
        "production", "render-primary", "update_failed", "deployment", "render-deploy", 3744
    )
    assert is_winner is True
    assert record.canonical_issue_number == 3744
    assert record.evidence_count == 1

    # Second agent observes same failure
    is_winner2, record2 = registry.register_or_corroborate(
        "production", "render-primary", "update_failed", "deployment", "render-deploy"
    )
    assert is_winner2 is False, "Second agent must NOT be winner; duplicate issue creation prevented"
    assert record2.canonical_issue_number == 3744
    assert record2.evidence_count == 2


def test_pr_deduplication_guard():
    open_prs = [
        {"number": 3781, "title": "fix(render): resolve deployment timeout (#3744)", "body": "Fixes #3744"},
        {"number": 3782, "title": "ci: fix pipeline gate", "body": "scope:pipeline"},
    ]

    is_dup, pr_num = check_pr_deduplication(3744, "render", open_prs)
    assert is_dup is True
    assert pr_num == 3781

    is_dup2, pr_num2 = check_pr_deduplication(9999, "unknown", open_prs)
    assert is_dup2 is False
    assert pr_num2 is None

