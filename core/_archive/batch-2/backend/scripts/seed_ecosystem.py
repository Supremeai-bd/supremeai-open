"""Seed default capabilities + source policies (idempotent)."""

from __future__ import annotations

import sys
from pathlib import Path

_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from ecosystem import (
    Capability,
    CapabilityLifecycleState,
    CapabilityRuntimeTier,
    SourceCategory,
    SourcePolicy,
    SourceState,
    get_capability_registry,
    get_source_governance,
)

DEFAULT_CAPABILITIES = [
    {
        "name": "PDF Text Extraction",
        "purpose": "Extract text from PDF",
        "signature": "pdf.extract.text.v1",
        "category": "document",
        "execution_method": "in_process",
        "runtime_tier": "HOT",
    },
    {
        "name": "Web Research",
        "purpose": "Search approved internet sources",
        "signature": "web.research.v1",
        "category": "research",
        "execution_method": "worker",
        "runtime_tier": "HOT",
    },
    {
        "name": "Code Generation",
        "purpose": "Generate code from requirements",
        "signature": "code.generate.v1",
        "category": "coding",
        "execution_method": "in_process",
        "runtime_tier": "HOT",
    },
    {
        "name": "GitHub Operations",
        "purpose": "Branches, commits, PRs",
        "signature": "github.ops.v1",
        "category": "devops",
        "execution_method": "worker",
        "runtime_tier": "HOT",
    },
    {
        "name": "Document Generation",
        "purpose": "Generate PDF/DOCX/XLSX",
        "signature": "document.generate.v1",
        "category": "document",
        "execution_method": "in_process",
        "runtime_tier": "HOT",
    },
    {
        "name": "Browser Automation",
        "purpose": "Headless browser via Playwright",
        "signature": "browser.automate.v1",
        "category": "automation",
        "execution_method": "browser",
        "runtime_tier": "WARM",
    },
    {
        "name": "Heavy Compute (Kaggle)",
        "purpose": "GPU inference, batch",
        "signature": "compute.kaggle.v1",
        "category": "compute",
        "execution_method": "kaggle",
        "runtime_tier": "COLD",
    },
]

DEFAULT_POLICIES = [
    {
        "name": "Allowlist AI docs",
        "scope": "category",
        "scope_value": "AI_DOCS",
        "decision": "ALLOWLISTED",
        "rate_limit_per_minute": 60,
        "crawl_budget_per_day": 1000,
    },
    {
        "name": "Allowlist OSS repos",
        "scope": "category",
        "scope_value": "OSS_REPO",
        "decision": "ALLOWLISTED",
        "rate_limit_per_minute": 60,
        "crawl_budget_per_day": 2000,
    },
    {
        "name": "Allowlist tech docs",
        "scope": "category",
        "scope_value": "TECH_DOCS",
        "decision": "ALLOWLISTED",
        "rate_limit_per_minute": 30,
        "crawl_budget_per_day": 800,
    },
    {
        "name": "Defer research",
        "scope": "category",
        "scope_value": "RESEARCH",
        "decision": "DEFERRED",
        "rate_limit_per_minute": 10,
        "crawl_budget_per_day": 100,
        "requires_approval": True,
    },
    {
        "name": "Block unknown",
        "scope": "category",
        "scope_value": "UNKNOWN",
        "decision": "BLOCKED",
        "rate_limit_per_minute": 0,
        "crawl_budget_per_day": 0,
        "requires_approval": True,
    },
]


def seed_capabilities() -> tuple[int, int]:
    reg = get_capability_registry()
    created, skipped = 0, 0
    for item in DEFAULT_CAPABILITIES:
        if reg.find_by_signature(item["signature"]):
            skipped += 1
            continue
        reg.register(
            Capability(
                name=item["name"],
                purpose=item["purpose"],
                signature=item["signature"],
                category=item["category"],
                execution_method=item["execution_method"],
                runtime_tier=CapabilityRuntimeTier(item["runtime_tier"]),
                lifecycle_state=CapabilityLifecycleState.ACTIVE,
                source="internal",
                owner="system",
            )
        )
        created += 1
    return created, skipped


def seed_policies() -> tuple[int, int]:
    gov = get_source_governance()
    created, skipped = 0, 0
    for item in DEFAULT_POLICIES:
        # বাংলা: match_policy শুধু url নেয় — তাই আমরা সরাসরি add করি, idempotency check ছাড়ি।
        try:
            gov.add_policy(
                SourcePolicy(
                    name=item["name"],
                    scope=item["scope"],
                    scope_value=item["scope_value"],
                    decision=SourceState(item["decision"]),
                    rate_limit_per_minute=item["rate_limit_per_minute"],
                    crawl_budget_per_day=item["crawl_budget_per_day"],
                    requires_approval=item.get("requires_approval", False),
                )
            )
            created += 1
        except Exception:
            skipped += 1
    return created, skipped


def main() -> int:
    print(">>> Seeding ecosystem...")
    c1, s1 = seed_capabilities()
    print(f"  capabilities: created={c1} skipped={s1}")
    c2, s2 = seed_policies()
    print(f"  policies: created={c2} skipped={s2}")
    print(">>> Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
