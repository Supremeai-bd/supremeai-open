#!/usr/bin/env python3
"""PR Evidence Envelope reference implementation — S0.2 (task #457).

Executable, network-free reference for docs/S02_STRUCTURED_EVIDENCE_SPEC.md.
Guards assert structured fields instead of scraping PR prose. Pure
functions in unit mode; every parser is fail-closed (garbage in -> None out,
never a raise, never a half-validation).

Marker format: exactly one fenced block

    <!-- pr-evidence-envelope v1 -->
    { ...json... }
    <!-- /pr-evidence-envelope -->
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

# --- Single sources of truth (imported by tests; never copy) ---------------
SCHEMA_VERSION = "pr-evidence-envelope/1"
MARKER_OPEN = "<!-- pr-evidence-envelope v1 -->"
MARKER_CLOSE = "<!-- /pr-evidence-envelope -->"
REFLECTION_HEADING = "## Reflection Evidence (why + alternatives_rejected)"

PROTECTED_PREFIXES = (".github/", "docs/ledger/", "docs/master_docs/", "prisma/", ".env")
PROTECTED_NAME_PATTERNS = (
    re.compile(r"(?i)(^|/)\.env"),
    re.compile(r"(?i)credential"),
    re.compile(r"(?i)\.pem$"),
    re.compile(r"(?i)(^|/)[^/]*key\.p12$"),
)
SHA256_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class EnvelopeError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass
class EvidenceEnvelope:
    task_issue_ref: int
    claim_marker_id: str
    reflection_why: str
    alternatives_rejected: List[str]
    scope_paths: List[str]
    file_digests: Dict[str, str] = field(default_factory=dict)
    rollback_path: str = "git revert bridge branch commits; additive scoped changes only."
    agent_id: str = "unknown-agent"
    created_ts: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "schema": SCHEMA_VERSION,
            "task_issue_ref": self.task_issue_ref,
            "claim_marker_id": self.claim_marker_id,
            "reflection_why": self.reflection_why,
            "alternatives_rejected": list(self.alternatives_rejected),
            "scope_paths": list(self.scope_paths),
            "file_digests": dict(self.file_digests),
            "rollback_path": self.rollback_path,
            "agent_id": self.agent_id,
            "created_ts": self.created_ts,
        }


def build_envelope(env: EvidenceEnvelope) -> str:
    """Deterministic serialization (sorted keys) inside the marker fence."""
    payload = json.dumps(env.to_dict(), sort_keys=True, ensure_ascii=False, indent=2)
    return f"{MARKER_OPEN}\n{payload}\n{MARKER_CLOSE}"


def parse_envelope(body: str) -> Optional[EvidenceEnvelope]:
    """Find + parse the envelope. Fail-closed: None for everything invalid."""
    if not body or MARKER_OPEN not in body:
        return None
    start = body.index(MARKER_OPEN) + len(MARKER_OPEN)
    end = body.find(MARKER_CLOSE, start)
    if end < 0:
        return None
    raw = body[start:end].strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("schema") != SCHEMA_VERSION:
        return None
    try:
        return EvidenceEnvelope(
            task_issue_ref=data["task_issue_ref"],
            claim_marker_id=data["claim_marker_id"],
            reflection_why=data["reflection_why"],
            alternatives_rejected=list(data["alternatives_rejected"]),
            scope_paths=list(data["scope_paths"]),
            file_digests=dict(data.get("file_digests", {})),
            rollback_path=data.get("rollback_path", ""),
            agent_id=data.get("agent_id", "unknown-agent"),
            created_ts=data.get("created_ts", ""),
        )
    except (KeyError, TypeError, ValueError):
        return None


def check_protected(path: str) -> bool:
    """True if the path hits a protected prefix or credential-like name."""
    if any(path.startswith(p) for p in PROTECTED_PREFIXES):
        return True
    return any(p.search(path) for p in PROTECTED_NAME_PATTERNS)


def validate(env: EvidenceEnvelope) -> List[str]:
    """Return a list of error codes; empty list == valid. Fail-closed."""
    errors: List[str] = []
    if not isinstance(env.task_issue_ref, int) or env.task_issue_ref <= 0:
        errors.append("E_BAD_ISSUE_REF")
    if not env.claim_marker_id or not env.claim_marker_id.strip():
        errors.append("E_CLAIM_MARKER_MISMATCH")
    why = (env.reflection_why or "").strip()
    if not (16 <= len(why) <= 500):
        errors.append("E_EMPTY_WHY")
    alts = [a for a in (env.alternatives_rejected or []) if str(a).strip()]
    if not (1 <= len(alts) <= 5):
        errors.append("E_NO_ALTERNATIVES")
    paths = [p for p in (env.scope_paths or []) if str(p).strip()]
    if not (1 <= len(paths) <= 30):
        errors.append("E_SCOPE_PROTECTED")
    for p in paths:
        if check_protected(p):
            if "E_SCOPE_PROTECTED" not in errors:
                errors.append("E_SCOPE_PROTECTED")
    for _path, digest in (env.file_digests or {}).items():
        if not SHA256_RE.match(str(digest)):
            if "E_BAD_DIGEST" not in errors:
                errors.append("E_BAD_DIGEST")
    if not TS_RE.match(env.created_ts or ""):
        errors.append("E_BAD_TIMESTAMP")
    if not (env.rollback_path or "").strip():
        errors.append("E_NO_ENVELOPE")  # rollback must be stated; reuse no-envelope code family
    return errors


def render_reflection_section(env: EvidenceEnvelope) -> str:
    """Human-readable section the Knowledge Sharing Guard requires —
    generated FROM the structured fields so prose and data never disagree."""
    alts = "\n".join(f"- {a}" for a in env.alternatives_rejected)
    return (
        f"{REFLECTION_HEADING}\n\n"
        f"**Why:** {env.reflection_why.strip()}\n"
        f"**Alternatives rejected:**\n{alts}\n"
        f"**Task issue:** #{env.task_issue_ref}\n"
        f"**Agent:** {env.agent_id}\n"
        f"**Created:** {env.created_ts}\n"
    )


def build_full_pr_body(env: EvidenceEnvelope, summary: str) -> str:
    """Summary prose + envelope block + rendered reflection section."""
    return f"{summary.strip()}\n\n{build_envelope(env)}\n\n{render_reflection_section(env)}"


def demo() -> int:
    env = EvidenceEnvelope(
        task_issue_ref=457,
        claim_marker_id="atomic-claim:issue=457,agent=zai,ts=2026-10-17T03:30:00Z,ttl=30m",
        reflection_why="structured assertions replace brittle regex ladders on PR bodies",
        alternatives_rejected=["keep regex ladders", "external validation service"],
        scope_paths=["docs/S02_STRUCTURED_EVIDENCE_SPEC.md", "scripts/tower/pr_evidence_envelope.py"],
        file_digests={},
    )
    block = build_envelope(env)
    back = parse_envelope(block)
    errs = validate(env)
    print("round-trip ok:", back is not None and back.task_issue_ref == 457)
    print("validate:", errs or "VALID (0 errors)")
    print("reflection heading present:", REFLECTION_HEADING in render_reflection_section(env))
    print("protected catch:", check_protected("prisma/schema.prisma"), check_protected("scripts/tower/x.py"))
    return 0


if __name__ == "__main__":
    sys.exit(demo())
