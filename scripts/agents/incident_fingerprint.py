#!/usr/bin/env python3
"""Canonical Incident Fingerprint and Atomic Deduplication SSOT Engine.
========================================================================
Implements deterministic root-cause fingerprinting and atomic deduplication
for federation incidents across Render, Supabase, Redis, Infisical, CI, and Loops.

Invariant:
  - 1 Incident Class = 1 Deterministic Fingerprint = 1 Canonical Issue = 1 Active Fix PR
  - Submissions/agents observing an existing incident MUST append structured evidence
    rather than filing duplicate issues or speculative twin PRs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

INCIDENT_MARKER_RE = re.compile(r"<!--\s*incident-fp:([0-9a-f]{16,64})\s*-->")
INCIDENT_MARKER_PREFIX = "<!-- incident-fp:"

ROOT_CAUSE_FAMILIES = (
    "render-deploy",      # Render deployment failure / update_failed / timeout
    "redis-quota",        # Redis/Upstash rate limit / quota exhaustion
    "supabase-schema",    # DB migration / schema drift / TLS mismatch
    "secrets-missing",    # Missing Infisical / environment variables
    "ci-pipeline",        # CI workflow syntax / test failure / lint
    "agent-loop",         # Continuous loop crash / lease collision / timeout
    "bridge-intake",      # Bridge submission / stale base / CAS rejection
    "unspecified",
)


def normalize_token(text: str) -> str:
    """Normalize input strings by lowercasing, removing non-alphanumerics, and collapsing spaces."""
    lowered = (text or "").strip().lower()
    cleaned = re.sub(r"[^a-z0-9\-_./]+", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def compute_incident_fingerprint(
    environment: str,
    service: str,
    normalized_error_class: str,
    affected_component: str,
    root_cause_family: str,
) -> str:
    """Deterministic 16-hex fingerprint for an incident.

    Timestamp, agent name, run IDs, and random tokens are strictly EXCLUDED so repeated
    observations of the same failure map deterministically to the identical fingerprint.
    """
    family = root_cause_family if root_cause_family in ROOT_CAUSE_FAMILIES else "unspecified"
    parts = [
        normalize_token(environment) or "production",
        normalize_token(service),
        normalize_token(normalized_error_class),
        normalize_token(affected_component),
        normalize_token(family),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def format_incident_marker(fp: str) -> str:
    """Return formatted HTML comment marker for issue body injection."""
    return f"{INCIDENT_MARKER_PREFIX}{fp} -->"


def extract_incident_fingerprint(body: str) -> str | None:
    """Extract incident-fp marker from issue/PR body."""
    match = INCIDENT_MARKER_RE.search(body or "")
    return match.group(1) if match else None


@dataclass
class IncidentRecord:
    fingerprint: str
    environment: str
    service: str
    normalized_error: str
    affected_component: str
    root_cause_family: str
    canonical_issue_number: int | None = None
    active_pr_number: int | None = None
    status: str = "open"
    first_seen_at: str = ""
    last_seen_at: str = ""
    evidence_count: int = 1


class IncidentRegistrySSOT:
    """Local or atomic state ledger tracking active incidents and deduplicating creation."""

    def __init__(self, registry_path: Path | None = None):
        self.registry_path = registry_path or (
            Path(__file__).resolve().parents[2] / "scripts" / "agents" / "incident_registry_state.json"
        )
        self._load()

    def _load(self) -> None:
        if self.registry_path.exists():
            try:
                data = json.loads(self.registry_path.read_text(encoding="utf-8"))
                self.incidents: dict[str, dict[str, Any]] = data.get("incidents", {})
            except Exception:
                self.incidents = {}
        else:
            self.incidents = {}

    def save(self) -> None:
        data = {
            "schema": "incident-registry-state/1",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "incidents": self.incidents,
        }
        self.registry_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def register_or_corroborate(
        self,
        environment: str,
        service: str,
        normalized_error_class: str,
        affected_component: str,
        root_cause_family: str,
        reported_issue_number: int | None = None,
    ) -> tuple[bool, IncidentRecord]:
        """Atomic get-or-create ledger logic.

        Returns:
            (is_new_winner: bool, record: IncidentRecord)
            - If is_new_winner is True: the caller is the authoritative winner permitted
              to create a new canonical issue or claim the fix.
            - If is_new_winner is False: an incident already exists. The caller MUST NOT
              create a duplicate issue, but append corroborating evidence instead.
        """
        fp = compute_incident_fingerprint(
            environment, service, normalized_error_class, affected_component, root_cause_family
        )
        now = datetime.now(timezone.utc).isoformat()

        if fp in self.incidents:
            entry = self.incidents[fp]
            entry["last_seen_at"] = now
            entry["evidence_count"] = entry.get("evidence_count", 1) + 1
            if reported_issue_number and not entry.get("canonical_issue_number"):
                entry["canonical_issue_number"] = reported_issue_number
            self.save()
            return False, IncidentRecord(**entry)

        # New incident
        record = IncidentRecord(
            fingerprint=fp,
            environment=environment,
            service=service,
            normalized_error=normalized_error_class,
            affected_component=affected_component,
            root_cause_family=root_cause_family,
            canonical_issue_number=reported_issue_number,
            status="open",
            first_seen_at=now,
            last_seen_at=now,
            evidence_count=1,
        )
        self.incidents[fp] = asdict(record)
        self.save()
        return True, record


def check_pr_deduplication(
    target_issue_number: int,
    subsystem_scope: str,
    existing_open_prs: list[dict[str, Any]],
) -> tuple[bool, int | None]:
    """Verify whether an open PR already covers the given target issue or subsystem.

    Returns:
        (is_duplicate: bool, existing_pr_number: int | None)
    """
    for pr in existing_open_prs:
        title = pr.get("title", "")
        body = pr.get("body", "")
        # Check target issue match
        if f"#{target_issue_number}" in title or f"#{target_issue_number}" in body:
            return True, pr.get("number")
        # Check subsystem marker
        if f"scope:{subsystem_scope}" in body:
            return True, pr.get("number")
    return False, None

