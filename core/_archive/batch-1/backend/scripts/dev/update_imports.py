"""
বাংলা মন্তব্য: Reorganization-এর পরে সমস্ত import paths স্বয়ংক্রিয়ভাবে আপডেট করার স্ক্রিপ্ট।
old_path → new_path mapping ব্যবহার করে সব .py ফাইলে find-and-replace চালায়।
"""

from pathlib import Path

IMPORT_MAP = {
    # Security redirects
    "from core.prompt_firewall": "from core.security.protection.prompt_firewall",
    "from core.input_sanitizer": "from core.security.input_sanitizer",
    "from core.auth_middleware": "from core.security.authentication.auth_middleware",
    "from core.rbac": "from core.security.authentication.rbac",
    "from core.honeypot_middleware": "from core.security.protection.honeypot",
    "from core.secret_vault": "from core.security.secret_vault",
    "from core.secure_credential_store": "from core.security.secure_credential_store",
    "from core.security_vault": "from core.security.security_vault",
    "from core.origin_validator": "from core.security.origin_validator",
    "from core.api_key_middleware": "from core.security.api_key_middleware",
    # Cache redirects
    "from core.semantic_cache": "from core.cache.semantic_cache",
    "from core.multi_layer_cache": "from core.cache.multi_layer_cache",
    "from core.autocache_proxy": "from core.cache.autocache_proxy",
    "from core.redis_manager": "from core.cache.redis_manager",
    # Messaging redirects
    "from core.event_bus": "from core.messaging.event_bus",
    "from core.events": "from core.messaging.events",
    "from core.gcp_pubsub_queue": "from core.messaging.gcp_pubsub_queue",
    "from core.nats_messaging": "from core.messaging.nats_messaging",
    "from core.pubsub": "from core.messaging.pubsub",
    "from core.upstash_redis_queue": "from core.messaging.upstash_redis_queue",
    # Health redirects
    "from core.health_monitor": "from core.health.health_monitor",
    "from core.health_probes": "from core.health.health_probes",
    "from core.self_healer": "from core.health.self_healer",
    # LLM redirects
    "from core.llm_gateway": "from core.llm.llm_gateway",
    "from core.free_tier_tracker": "from core.llm.free_tier_tracker",
    "from core.token_budget": "from core.llm.token_budget",
    "from core.token_deductor": "from core.llm.token_deductor",
    # Orchestration moves
    "from core.swarm_orchestrator": "from core.orchestration.swarm_orchestrator",
    "from core.agent_orchestrator": "from core.orchestration.agent_orchestrator",
    "from core.orchestrator import": "from core.orchestration.orchestrator import",
    "from core.cloud_sandbox_orchestrator": "from core.orchestration.cloud_sandbox",
    "from core.orchestrators.crew_departments": "from core.orchestration.crew_departments",
    # Resilience moves
    "from core.circuit_breaker": "from core.resilience.circuit_breaker",
    "from core.auto_remediation": "from core.resilience.auto_remediation",
    "from core.chaos_engine": "from core.resilience.chaos_engine",
    "from core.rollback_monitor": "from core.resilience.rollback_monitor",
    # Observability moves
    "from core.telemetry": "from core.observability.telemetry",
    "from core.observability_middleware": "from core.observability.middleware",
    "from core.posthog_client": "from core.observability.posthog_client",
    "from core.audit_logger": "from core.observability.audit_logger",
    "from core.log_batcher": "from core.observability.log_batcher",
    # Queue moves
    "from core.task_queue_enhanced": "from core.queue.task_queue_enhanced",
    "from core.task_router": "from core.queue.task_router",
    # Evolution moves
    "from core.evolution_engine": "from core.self_evolution.evolution_engine",
}


def update_file(path: Path) -> int:
    """একটি ফাইলের সব পুরনো import নতুন path দিয়ে replace করে।"""
    content = path.read_text(encoding="utf-8")
    original = content
    count = 0
    for old, new in IMPORT_MAP.items():
        if old in content:
            content = content.replace(old, new)
            count += 1

    # Also handle some generic ones like "import core.X" maybe?
    # Usually it's "from core.X import Y"

    if content != original:
        path.write_text(content, encoding="utf-8")
        pass
    return count


if __name__ == "__main__":
    backend = Path(__file__).parent.parent.parent
    total = sum(update_file(f) for f in backend.rglob("*.py") if f != Path(__file__))
    pass
