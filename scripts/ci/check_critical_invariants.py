#!/usr/bin/env python3
"""Critical invariant guard — protects core logic from merge/rebase silent drops.

Issue #476: during a September-18 rebase, the atomic Upstash sliding-window
Lua rate limiter was silently dropped in conflict resolution (later recovered
in a separate fix). This guard makes such a drop FAIL the build instead of
passing silently.

বাংলা: রিবেস/মার্জ কনফ্লিক্ট রেজলিউশনে ক্রিটিকাল কোড নীরবে মুছে গেলে সেটি
এখন বিল্ড ব্যর্থ করবে — প্রতিটি ইনভেরিয়েন্টের সুনির্দিষ্ট মার্কার চেক করে।

Design:
  * Data-driven registry: (path, [required markers], description). Markers are
    literal substrings that MUST exist in the file — cheap, exact, no AST
    flakiness, and intentionally resistant to "reformatting" churn.
  * A missing FILE or a missing marker = failure with an actionable diff-style
    report. Never edits anything; read-only.
  * Wired into: CI (Operational Tooling Quality Gate) and the pre-push hook.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# (relative_path, [required substrings], why-it-is-critical)
INVARIANTS: list[tuple[str, list[str], str]] = [
    # ── Atomic Upstash sliding-window rate limiter (issue #460/#476) ──────
    (
        "backend/middleware/rate_limiter.py",
        ["ZREMRANGEBYSCORE", "ZCARD", "ZADD", "EXPIRE"],
        "Atomic Lua sliding-window (cleanup+count+add must stay in ONE script)",
    ),
    (
        "backend/core/rate_limit.py",
        ["RateLimitMiddleware"],
        "Global rate-limit middleware registration surface",
    ),
    # ── Tenant isolation invariants ───────────────────────────────────────
    (
        "backend/api/middleware.py",
        ["scoped_key", "idempotency:response:"],
        "Idempotency keys MUST stay principal-scoped (cross-tenant replay fix)",
    ),
    # ── Fail-closed readiness / schema gate (issue #478) ──────────────────
    (
        "backend/core/db_schema_gate.py",
        ["automation_executions", "ai_memory", "task_checkpoints"],
        "Production readiness schema gate — required-table registry",
    ),
    (
        "backend/core/health_policy.py",
        ["db_failure_readiness"],
        "Role-aware DB degradation policy (fail-closed on core in production)",
    ),
    # ── Vault fail-closed contract ─────────────────────────────────────────
    (
        "backend/core/security/secret_vault.py",
        ["ProductionSecretVault", "SecretNotFoundError"],
        "Enterprise vault fail-closed contract (Sep-14 crash-loop hardening)",
    ),
]


def main() -> int:
    failures: list[str] = []
    checked = 0
    for rel_path, markers, why in INVARIANTS:
        path = REPO_ROOT / rel_path
        checked += 1
        if not path.exists():
            failures.append(f"MISSING FILE: {rel_path}\n    why: {why}")
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        for marker in markers:
            if marker not in content:
                failures.append(f"MISSING MARKER in {rel_path}: `{marker}`\n    why: {why}")

    if failures:
        print(f"❌ Critical invariant guard FAILED — {len(failures)} violation(s):\n")
        for f in failures:
            print(f"  - {f}")
        print(
            "\nIf you just resolved a merge/rebase conflict: a critical code path "
            "was likely dropped. Restore the marker above (or, if the invariant "
            "genuinely moved/changed, update scripts/ci/check_critical_invariants.py "
            "in the SAME commit with a link to the issue explaining the move)."
        )
        return 1

    print(f"✅ Critical invariant guard OK — {checked} invariant targets verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
