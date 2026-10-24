"""MCP Policy Engine — Python mirror of the TypeScript RiskEngine + PolicyEngine.

বাংলা মন্তব্য: এই মডিউলটি infrastructure/mcp-control-plane/src/policy/risk.engine.ts
এবং policy.engine.ts এর Python mirror। সমস্ত MCP tool call এখানের মাধ্যমে evaluate হয়।

Risk Levels (R0-R6):
  R0 = Safe Read-Only     → Auto-allow
  R1 = Safe Write         → Auto-allow
  R2 = Low Risk Write     → Require Approval
  R3 = Moderate Risk      → Require Approval
  R4 = High Risk          → Require Approval
  R5 = Critical           → Require Approval
  R6 = Catastrophic      → Require Approval (strict HITL)

Constitution Compliance:
  - Law #11 (Think Before You Act): every tool call evaluated before execution
  - Law #19 (Observable): every evaluation logged to audit
  - Law #1 (Centralized): single policy engine for ALL Python MCP servers
"""

from __future__ import annotations

from typing import Any, Literal

RiskLevel = Literal["R0", "R1", "R2", "R3", "R4", "R5", "R6"]
PolicyDecision = Literal["ALLOW", "REQUIRE_APPROVAL", "DENY"]


class RiskEngine:
    """Mirror of infrastructure/mcp-control-plane/src/policy/risk.engine.ts"""

    def evaluate(self, provider: str, action: str) -> RiskLevel:
        # R0: Safe Read-Only
        read_only_keywords = (
            "read",
            "list",
            "summary",
            "status",
            "search",
            "get",
            "query",
            "fetch",
            "open",
        )
        if provider in ("system", "health") or any(kw in action for kw in read_only_keywords):
            return "R0"

        # Provider-specific rules (mirror of TS)
        if provider == "render":
            if action in ("restart", "deploy"):
                return "R2"
            if action == "suspend":
                return "R4"
            if action == "delete":
                return "R6"

        if provider == "supabase":
            if action == "restart":
                return "R3"
            if action in ("delete_table", "drop_db"):
                return "R6"
            if action in ("insert", "update"):
                return "R2"

        if provider == "redis":
            if action == "flushall":
                return "R5"
            if action == "set":
                return "R1"
            if action == "del":
                return "R2"

        if provider == "github":
            if action in ("commit", "push"):
                return "R2"
            if action == "delete_repo":
                return "R6"

        if provider == "agent_tools":
            # M09 P-A: এজেন্ট-নিজস্ব টুল-শ্রেণি — read/health নিরাপদ (R0),
            # sandbox-যাচাইকৃত অতিথি-কোডও মানব-অনুমোদন ছাড়া চলবে না (R5)।
            # M09 P-G: "verify" — deterministic গাণিতিক যাচাই (পার্শ্বপ্রতিক্রিয়া-শূন্য
            # গণনা, কোনো কোড-নির্বাহ নয়) → R0।
            if action in ("execute", "execute_code"):
                return "R5"
            if action in ("health", "search", "read", "status", "verify"):
                return "R0"
            return "R3"

        if provider == "memory":
            if action in ("delete", "clear", "drop"):
                return "R2"
            if action in ("create", "add", "store", "save", "record", "remember", "ingest"):
                return "R1"
            return "R0"

        if provider == "mcp_tools":
            if action in ("refresh", "live_query"):
                return "R2"
            return "R0"

        if provider == "mesh":
            # MESH-6 (#926): Tower task-queue — queue-level অপারেশন নন-ডেস্ট্রাক্টিভ
            # (task record তৈরি/বাতিল, কোনো privileged resource স্পর্শ নয়)।
            # Task execution-এর আসল বিপদ নির্ভর করে task_type-এর উপর — সেটা
            # HITL gate (MESH-4) আলাদাভাবে যাচাই করবে। R1 = auto-allow + audit।
            if action in ("dispatch", "release", "renew"):
                return "R1"
            # MCP Tower gap-3 (#927): agent-to-agent messaging — messaging-level
            # operation (inbox read / message create / ack flip / topic union),
            # কোনো privileged resource স্পর্শ করে না। Spam/abuse traceability-এর
            # জন্য R1 = auto-allow + audit (gap-4 audit event)।
            if action in ("send", "inbox", "ack", "subscribe"):
                return "R1"
            return "R0"

        # Default fallback for unknown writes
        return "R3"


class PolicyEngine:
    """Mirror of infrastructure/mcp-control-plane/src/policy/policy.engine.ts"""

    def __init__(self) -> None:
        self.risk_engine = RiskEngine()

    def decide(self, risk_level: RiskLevel) -> PolicyDecision:
        if risk_level == "R6":
            return "REQUIRE_APPROVAL"
        if risk_level in ("R0", "R1"):
            return "ALLOW"
        return "REQUIRE_APPROVAL"

    def evaluate(self, provider: str, action: str) -> tuple[PolicyDecision, RiskLevel]:
        risk = self.risk_engine.evaluate(provider, action)
        decision = self.decide(risk)
        return decision, risk


# ── Tool → (provider, action) mapping ──────────────────────────────────
# Each MCP tool is mapped to a (provider, action) pair for risk evaluation.

TOOL_PROVIDER_ACTION: dict[str, tuple[str, str]] = {
    # ── Agent core tools (M09 P-A — governed ReAct execution) ──
    # এই ৩টি SUPREME_TOOLS-এর প্রবেশ: read-শাখা R0 (auto-allow),
    # অতিথি-কোড নির্বাহ R5 (সর্বদা human approval লাগবে)।
    "search_database": ("agent_tools", "search"),
    "check_system_health": ("agent_tools", "health"),
    "execute_python_code": ("agent_tools", "execute"),
    # M09 P-G first-fleet: deterministic symbolic-math verification — R0।
    "cot_verify_math": ("agent_tools", "verify"),
    # Memory MCP — Knowledge Graph
    "create_entities": ("memory", "create"),
    "create_relations": ("memory", "create"),
    "add_observations": ("memory", "add"),
    "delete_entities": ("memory", "delete"),
    "delete_observations": ("memory", "delete"),
    "delete_relations": ("memory", "delete"),
    "read_graph": ("memory", "read"),
    "search_nodes": ("memory", "search"),
    "open_nodes": ("memory", "open"),
    # Memory MCP — Vector / Semantic
    "store_document": ("memory", "store"),
    "search_semantic": ("memory", "search"),
    "ingest_document_rag": ("memory", "ingest"),
    # Memory MCP — Episodic
    "record_task": ("memory", "record"),
    "get_similar_tasks": ("memory", "search"),
    "get_recent_episodes": ("memory", "read"),
    # Memory MCP — Sliding Window
    "build_context": ("memory", "read"),
    "get_session_stats": ("memory", "status"),
    "clear_session": ("memory", "clear"),
    # Memory MCP — Long Term Facts
    "remember_fact": ("memory", "remember"),
    "recall_facts": ("memory", "search"),
    "save_learned_fact": ("memory", "save"),
    "search_learned_facts": ("memory", "search"),
    # Backend Tools MCP
    "get_skill_dependencies": ("mcp_tools", "read"),
    "find_optimal_learning_path": ("mcp_tools", "read"),
    "get_render_deploy_preflight": ("mcp_tools", "read"),
    "get_render_account_status": ("mcp_tools", "read"),
    "refresh_render_account_status": ("mcp_tools", "refresh"),
    # ── MESH-6 (#926): Tower task-queue tools (platform-level) ──
    "mesh_dispatch_task": ("mesh", "dispatch"),
    "mesh_task_status": ("mesh", "status"),
    "mesh_release_task": ("mesh", "release"),
    # ── MCP Tower gap-3 (#927): Agent mailbox tools (platform-level) ──
    "agent_send": ("mesh", "send"),
    "agent_inbox": ("mesh", "inbox"),
    "agent_ack": ("mesh", "ack"),
    "topic_subscribe": ("mesh", "subscribe"),
}


# ── Singleton ──────────────────────────────────────────────────────────

_global_policy_engine = PolicyEngine()


def get_policy_engine() -> PolicyEngine:
    """Returns the singleton PolicyEngine instance."""
    return _global_policy_engine


def evaluate_tool(tool_name: str) -> tuple[PolicyDecision, RiskLevel]:
    """Evaluate a tool call and return (decision, risk_level)."""
    provider, action = TOOL_PROVIDER_ACTION.get(tool_name, ("unknown", "unknown"))
    engine = get_policy_engine()
    return engine.evaluate(provider, action)


def is_tool_allowed(tool_name: str) -> bool:
    """Quick check: is this tool auto-allowed (R0/R1)?"""
    decision, _ = evaluate_tool(tool_name)
    return decision == "ALLOW"
