"""Idempotent seed for ecosystem demo data (ROADMAP §50, plan §5.1 / B12).

বাংলা: এই মডিউলটি standalone_app.py এর lifespan থেকে import হয়।
- ``seed_capabilities()`` — 7 demo capabilities across IDEA → ACTIVE lifecycle states.
- ``seed_policies()`` — 3 source policies (ALLOWLISTED / DEFERRED / BLOCKED).
- ``seed_learned()`` — a couple of learned items for the admin Learned tab.
- ``seed_proposals()`` — one PENDING proposal so the Proposals tab is not empty.

Idempotency: each function checks ``find_by_signature`` / ``match_policy`` /
explicit existence queries before insert, so re-running never raises.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure backend/ is on sys.path so ``import ecosystem`` works even when this
# file is imported as ``ecosystem.seed_ecosystem``.
_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from adaptive_engine.approval_workflow import ApprovalProposal
from adaptive_engine.learning_loop import LearningOpportunity, LearningStage
from ecosystem import (
    Capability,
    CapabilityLifecycleState,
    CapabilityRuntimeTier,
    LearnedItem,
    ProposalKind,
    ProposalPriority,
    SourceCategory,
    SourcePolicy,
    SourceState,
    get_approval_workflow,
    get_capability_registry,
    get_learning_loop,
    get_source_governance,
)

# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------

DEFAULT_CAPABILITIES = [
    {
        "name": "PDF Text Extraction",
        "purpose": "Extract text from PDF documents",
        "signature": "pdf.extract.text.v1",
        "category": "document",
        "execution_method": "in_process",
        "runtime_tier": "HOT",
        "lifecycle_state": CapabilityLifecycleState.ACTIVE,
    },
    {
        "name": "Web Research",
        "purpose": "Search approved internet sources for a query",
        "signature": "web.research.v1",
        "category": "research",
        "execution_method": "worker",
        "runtime_tier": "HOT",
        "lifecycle_state": CapabilityLifecycleState.ACTIVE,
    },
    {
        "name": "Code Generation",
        "purpose": "Generate code from natural-language requirements",
        "signature": "code.generate.v1",
        "category": "coding",
        "execution_method": "in_process",
        "runtime_tier": "HOT",
        "lifecycle_state": CapabilityLifecycleState.MEASURED,
    },
    {
        "name": "GitHub Operations",
        "purpose": "Branches, commits, PRs",
        "signature": "github.ops.v1",
        "category": "devops",
        "execution_method": "worker",
        "runtime_tier": "WARM",
        "lifecycle_state": CapabilityLifecycleState.BUILDING,
    },
    {
        "name": "Document Generation",
        "purpose": "Generate PDF/DOCX/XLSX from structured input",
        "signature": "document.generate.v1",
        "category": "document",
        "execution_method": "in_process",
        "runtime_tier": "WARM",
        "lifecycle_state": CapabilityLifecycleState.VALIDATING,
    },
    {
        "name": "Browser Automation",
        "purpose": "Headless browser via Playwright",
        "signature": "browser.automate.v1",
        "category": "automation",
        "execution_method": "browser",
        "runtime_tier": "WARM",
        "lifecycle_state": CapabilityLifecycleState.PROPOSED,
    },
    {
        "name": "Heavy Compute (Kaggle)",
        "purpose": "GPU inference, batch compute",
        "signature": "compute.kaggle.v1",
        "category": "compute",
        "execution_method": "kaggle",
        "runtime_tier": "COLD",
        "lifecycle_state": CapabilityLifecycleState.IDEA,
    },
]


def seed_capabilities() -> tuple[int, int]:
    """Insert demo capabilities. Returns ``(created, skipped)``."""
    reg = get_capability_registry()
    created, skipped = 0, 0
    for item in DEFAULT_CAPABILITIES:
        if reg.find_by_signature(item["signature"]):
            skipped += 1
            continue
        try:
            reg.register(
                Capability(
                    name=item["name"],
                    purpose=item["purpose"],
                    signature=item["signature"],
                    category=item["category"],
                    execution_method=item["execution_method"],
                    runtime_tier=CapabilityRuntimeTier(item["runtime_tier"]),
                    lifecycle_state=item["lifecycle_state"],
                    source="internal",
                    owner="system",
                )
            )
            created += 1
        except Exception:
            skipped += 1
    return created, skipped


# ---------------------------------------------------------------------------
# Source policies (uses the ACTUAL SourcePolicy fields)
# ---------------------------------------------------------------------------

DEFAULT_POLICIES = [
    {
        "url_pattern": r"https?://([a-z0-9\-]+\.)*python\.org/.*",
        "category": SourceCategory.TECH_DOCS,
        "state": SourceState.ALLOWLISTED,
        "allowed_actions": ["read", "crawl"],
        "source_weight": 1.0,
        "created_by": "seed",
    },
    {
        "url_pattern": r"https?://([a-z0-9\-]+\.)*github\.com/.*",
        "category": SourceCategory.OSS_REPO,
        "state": SourceState.ALLOWLISTED,
        "allowed_actions": ["read", "crawl", "clone"],
        "source_weight": 1.0,
        "created_by": "seed",
    },
    {
        "url_pattern": r"https?://([a-z0-9\-]+\.)*medium\.com/.*",
        "category": SourceCategory.TECH_BLOG,
        "state": SourceState.DEFERRED,
        "allowed_actions": ["read"],
        "source_weight": 0.5,
        "created_by": "seed",
    },
    {
        "url_pattern": r".*",
        "category": SourceCategory.UNKNOWN,
        "state": SourceState.BLOCKED,
        "allowed_actions": [],
        "source_weight": 0.0,
        "created_by": "seed",
    },
]


def seed_policies() -> tuple[int, int]:
    """Insert demo source policies. Returns ``(created, skipped)``."""
    gov = get_source_governance()
    created, skipped = 0, 0
    for item in DEFAULT_POLICIES:
        if gov.match_policy(item["url_pattern"].replace("\\", "")) and gov.match_policy(
            "https://python.org/docs"
        ):
            # Heuristic: if a policy already matches an obvious URL we trust that
            # the default seed is installed; cheap and avoids UNIQUE violations
            # across restarts when url_pattern is identical.
            pass
        # Build + insert. SourcePolicy table has UNIQUE on url_pattern, so we
        # rely on the SQLite UNIQUE constraint to dedupe — and count skip.
        try:
            gov.add_policy(
                SourcePolicy(
                    url_pattern=item["url_pattern"],
                    category=item["category"],
                    state=item["state"],
                    allowed_actions=item["allowed_actions"],
                    source_weight=item["source_weight"],
                    created_by=item["created_by"],
                )
            )
            created += 1
        except Exception:
            skipped += 1
    return created, skipped


# ---------------------------------------------------------------------------
# Learned items + a demo opportunity + a demo proposal
# ---------------------------------------------------------------------------

DEFAULT_LEARNED = [
    {
        "source_url": "https://docs.python.org/3/library/asyncio.html",
        "category": SourceCategory.TECH_DOCS,
        "title": "asyncio — Asynchronous I/O",
        "summary": "asyncio primitives: gather, wait_for, TaskGroup, Queue.",
        "value_score": 0.85,
    },
    {
        "source_url": "https://github.com/fastapi/fastapi",
        "category": SourceCategory.OSS_REPO,
        "title": "FastAPI",
        "summary": "Modern Python web framework built on Starlette + Pydantic.",
        "value_score": 0.92,
    },
]


def seed_learned() -> tuple[int, int]:
    gov = get_source_governance()
    created, skipped = 0, 0
    for item in DEFAULT_LEARNED:
        # Idempotency: check by source_url + title via list_learned.
        existing = gov.list_learned(category=item["category"], min_value=0.0, limit=500)
        if any(x.source_url == item["source_url"] and x.title == item["title"] for x in existing):
            skipped += 1
            continue
        try:
            gov.record_learned(
                LearnedItem(
                    source_url=item["source_url"],
                    category=item["category"],
                    title=item["title"],
                    summary=item["summary"],
                    value_score=item["value_score"],
                )
            )
            created += 1
        except Exception:
            skipped += 1
    return created, skipped


def seed_opportunities() -> tuple[int, int]:
    """Surface one demo opportunity if none exist."""
    loop = get_learning_loop()
    existing = loop.list_opportunities(include_archived=True, limit=10)
    if existing:
        return 0, len(existing)
    try:
        loop.surface_opportunity(
            LearningOpportunity(
                capability_hint="PDF → structured JSON",
                gap_description="No native PDF→JSON capability; users submit ad-hoc requests.",
                predicted_value=0.7,
                predicted_effort=2.5,
                stage=LearningStage.CAPABILITY_OPPORTUNITY,
            )
        )
        return 1, 0
    except Exception:
        return 0, 0


def seed_proposals() -> tuple[int, int]:
    """Create one PENDING proposal if none exist."""
    wf = get_approval_workflow()
    pending = wf.list_pending(limit=10)
    if pending:
        return 0, len(pending)
    try:
        wf.propose(
            ApprovalProposal(
                kind=ProposalKind.NEW_CAPABILITY,
                priority=ProposalPriority.MEDIUM,
                title="Add image-to-text capability",
                summary="OCR pipeline for embedded images in PDFs",
                risk_level="MEDIUM",
                requested_by="seed",
                payload={"target_format": "markdown", "languages": ["eng", "ben"]},
            )
        )
        return 1, 0
    except Exception:
        return 0, 0


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------


def main() -> int:
    print(">>> Seeding ecosystem...", flush=True)
    c1, s1 = seed_capabilities()
    print(f"  capabilities: created={c1} skipped={s1}", flush=True)
    c2, s2 = seed_policies()
    print(f"  policies:     created={c2} skipped={s2}", flush=True)
    c3, s3 = seed_learned()
    print(f"  learned:      created={c3} skipped={s3}", flush=True)
    c4, s4 = seed_opportunities()
    print(f"  opportunities:created={c4} skipped={s4}", flush=True)
    c5, s5 = seed_proposals()
    print(f"  proposals:    created={c5} skipped={s5}", flush=True)
    print(">>> Done.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
