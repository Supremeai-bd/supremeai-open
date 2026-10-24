import logging

"""Analyze coverage.json and identify high-priority files needing tests."""

import json

from core.logging_config import logger

with open("coverage.json") as f:
    data = json.load(f)

files = data["files"]

targets = [
    "api/routes/__init__.py",
    "core/evolution/daily_learner.py",
    "tools/sso_integrator.py",
    "api/routes/tenant_admin.py",
    "core/cache/multi_layer_cache.py",
    "services/memory_service.py",
    "tools/knowledge/local_search_rag.py",
    "tools/seed_database.py",
    "tools/self_planner.py",
    "services/rider_tracker.py",
    "core/llm_router.py",
    "tools/security_tools/multi_account_rotator.py",
    "core/queue/task_queue_enhanced.py",
    "api/routes/browser.py",
    "core/tier8/codebase_refactor_proposer.py",
    "tools/learning/style_learner.py",
    "api/routes/meta_ai.py",
    "core/security/input_sanitizer.py",
    "core/security/secret_vault.py",
    "core/security/audit_logger.py",
    "core/security/origin_validator.py",
    "core/security/autonoguard_middleware.py",
    "core/cache/redis_manager.py",
    "core/resilience/circuit_breaker.py",
    "core/security/auth_middleware.py",
    "core/security/rbac.py",
    "core/security/honeypot_middleware.py",
    "core/security/prompt_firewall.py",
    "core/security/guardian_ai.py",
    "core/security/compliance_bot.py",
]

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("=" * 80)
    logger.info("HIGH-PRIORITY TARGET COVERAGE STATUS")
    logger.info("=" * 80)
    for t in targets:
        if t in files:
            s = files[t]["summary"]
            status = (
                "LOW"
                if s["percent_covered"] < 50
                else "MEDIUM"
                if s["percent_covered"] < 80
                else "GOOD"
            )
            logger.info(
                f"  {status:6s} | {s['percent_covered']:5.1f}% | {s['num_statements']:5d} stmts | {t}"
            )
        else:
            logger.info(f"  MISS  |  N/A  |  N/A  | {t}")

    logger.info("")
    logger.info("=" * 80)
    logger.info("ALL FILES WITH < 30% COVERAGE (> 10 statements)")
    logger.info("=" * 80)
    low_files = []
    for name, info in files.items():
        s = info["summary"]
        if s["num_statements"] > 10 and s["percent_covered"] < 30:
            low_files.append((name, s["percent_covered"], s["num_statements"]))

    for name, pct, stmts in sorted(low_files, key=lambda x: x[1]):
        logger.info(f"  {pct:5.1f}% | {stmts:5d} stmts | {name}")

    logger.info(f"\nTotal low-coverage files: {len(low_files)}")
