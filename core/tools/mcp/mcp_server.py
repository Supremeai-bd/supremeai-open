# backend/tools/mcp_server.py
import asyncio
import json
import time
from typing import Any

from mcp.server import Server

from core.kernel.audit_chain import args_fingerprint, get_audit_chain_store
from core.logging_config import logger
from core.mcp_audit import audit_tool_call
from core.mcp_policy import evaluate_tool
from mcp import types
from tools.graph_service import GraphService

# বাংলা মন্তব্য: নলেজ গ্রাফের জন্য একটি অফিসিয়াল MCP সার্ভার ইনিশিয়ালাইজ করা হচ্ছে
app = Server("supremeai-knowledge-graph")
graph_service = GraphService()


def _check_policy(name: str) -> dict[str, Any] | None:
    """Evaluate policy for a tool call. Returns None if allowed, or a dict with denial info."""
    decision, risk_level = evaluate_tool(name)
    if decision == "ALLOW":
        return None
    if decision == "REQUIRE_APPROVAL":
        return {
            "approval_required": True,
            "risk_level": risk_level,
            "tool": name,
            "reason": f"Tool '{name}' is classified as {risk_level}. Requires explicit human approval.",
        }
    return {
        "approval_required": True,
        "risk_level": risk_level,
        "tool": name,
        "reason": f"Tool '{name}' blocked by policy (decision={decision}).",
    }


@app.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """বাংলা মন্তব্য: এআই এজেন্টের কাছে এভেইলেবল গ্রাফ টুলসগুলোর তালিকা প্রকাশ করবে।"""
    return [
        types.Tool(
            name="get_skill_dependencies",
            description="Exposes the entire dependency and connection graph of SupremeAI skills.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="find_optimal_learning_path",
            description="Finds the shortest, optimized chain between two complex skills.",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_skill": {
                        "type": "string",
                        "description": "The starting skill name",
                    },
                    "end_skill": {
                        "type": "string",
                        "description": "The target skill name",
                    },
                },
                "required": ["start_skill", "end_skill"],
            },
        ),
        types.Tool(
            name="get_render_deploy_preflight",
            description="Returns capability-aware preflight overview, limits, and deployment authorization across Render roles.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="get_render_account_status",
            description="Fetch the latest known state, plan, usage, and cooldown for a Render account role.",
            inputSchema={
                "type": "object",
                "properties": {
                    "account_role": {
                        "type": "string",
                        "description": "Render account role, e.g. 'core', 'worker', 'scraper', 'mcp'",
                    },
                },
            },
        ),
        types.Tool(
            name="refresh_render_account_status",
            description="Live query of Render deployment history and quota usage, updating database state and audit log.",
            inputSchema={
                "type": "object",
                "properties": {
                    "account_role": {
                        "type": "string",
                        "description": "Render account role to refresh",
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Force audit even if currently in cooldown (admin only)",
                    },
                },
                "required": ["account_role"],
            },
        ),
        # ── MESH-6 (#926): Tower task-queue tools (platform-level) ──
        types.Tool(
            name="mesh_dispatch_task",
            description="MESH-6: Submit a new task to the Tower-native mesh task queue (CAS claim/lease/failover handled by Tower).",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_type": {
                        "type": "string",
                        "description": "One of: bash, pytest, ollama, git_push, file_edit, custom",
                    },
                    "title": {"type": "string", "description": "Short human-readable task title"},
                    "payload": {"type": "object", "description": "Task-type specific payload"},
                    "required_capabilities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Node capabilities required to claim this task",
                    },
                    "target_role": {
                        "type": "string",
                        "description": "Optional role restriction: planner|coder|tester|gate|observer",
                    },
                    "priority": {
                        "type": "integer",
                        "description": "0 (highest) to 9 (lowest), default 5",
                    },
                },
                "required": ["task_type", "title"],
            },
        ),
        types.Tool(
            name="mesh_task_status",
            description="MESH-6: Get a mesh task's state by task_id, or the whole queue snapshot (stats + tasks) when task_id is omitted.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task id, or omit for full queue snapshot",
                    },
                },
            },
        ),
        types.Tool(
            name="mesh_release_task",
            description="MESH-6: Cancel/release a pending or leased mesh task (operator action).",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task id to cancel"},
                },
                "required": ["task_id"],
            },
        ),
        # ── MCP Tower gap-3 (#927): Agent mailbox tools (platform-level) ──
        types.Tool(
            name="agent_send",
            description="MCP gap-3: Send an agent-to-agent mailbox message (direct to_agent, role broadcast, or topic publish) with reply_to threading and TTL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "from_agent": {"type": "string", "description": "Sender agent id"},
                    "to_agent": {
                        "type": "string",
                        "description": "Recipient agent id, or '*' to broadcast",
                    },
                    "to_role": {
                        "type": "string",
                        "description": "Optional role broadcast gate: planner|coder|tester|gate|observer",
                    },
                    "topic": {
                        "type": "string",
                        "description": "Optional pub/sub topic (recipients must topic_subscribe)",
                    },
                    "body": {"type": "object", "description": "Message payload (max 256KB)"},
                    "reply_to": {
                        "type": "string",
                        "description": "Parent message id for delegation-thread replies",
                    },
                    "ttl_seconds": {
                        "type": "integer",
                        "description": "Time-to-live (default 86400, max 604800)",
                    },
                    "tenant_id": {
                        "type": "string",
                        "description": "Tenant scope — explicit non-default tenant id (required at call time)",
                    },
                },
                "required": ["from_agent", "to_agent"],
            },
        ),
        types.Tool(
            name="agent_inbox",
            description="MCP gap-3: Poll an agent mailbox — visible direct + subscribed/role/topic broadcasts (pull-based pub/sub).",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "Mailbox owner agent id"},
                    "role": {
                        "type": "string",
                        "description": "Role gate for broadcast visibility",
                    },
                    "unread_only": {
                        "type": "boolean",
                        "description": "Exclude already-acked messages",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max messages to return (default 50, max 200)",
                    },
                    "tenant_id": {
                        "type": "string",
                        "description": "Tenant scope — explicit non-default tenant id (required at call time)",
                    },
                },
                "required": ["agent_id"],
            },
        ),
        types.Tool(
            name="agent_ack",
            description="MCP gap-3: Acknowledge receipt of a mailbox message (idempotent; cross-tenant or wrong recipient denied).",
            inputSchema={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string", "description": "Message id to ack"},
                    "agent_id": {"type": "string", "description": "Acking agent id"},
                    "tenant_id": {
                        "type": "string",
                        "description": "Tenant scope — explicit non-default tenant id (required at call time)",
                    },
                },
                "required": ["message_id", "agent_id"],
            },
        ),
        types.Tool(
            name="topic_subscribe",
            description="MCP gap-3: Subscribe an agent to pub/sub topics so topic broadcasts appear in agent_inbox.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "Subscribing agent id"},
                    "topics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Topics to subscribe (idempotent union)",
                    },
                    "tenant_id": {
                        "type": "string",
                        "description": "Tenant scope — explicit non-default tenant id (required at call time)",
                    },
                },
                "required": ["agent_id", "topics"],
            },
        ),
        # ── MCP Tower gap-4 (issue #928): per-agent verified audit tools ──
        types.Tool(
            name="audit_query",
            description="MCP Tower gap-4 (#928): query the tamper-evident per-agent audit chain — filter by agent/tool/time-window.",
            inputSchema={
                "type": "object",
                "properties": {
                    "tenant_id": {
                        "type": "string",
                        "description": "Tenant scope (required, non-default)",
                    },
                    "agent_id": {"type": "string", "description": "Filter by agent id"},
                    "tool": {"type": "string", "description": "Filter by tool name"},
                    "limit": {
                        "type": "integer",
                        "description": "Max events (default 100, cap 1000)",
                    },
                },
                "required": ["tenant_id"],
            },
        ),
        types.Tool(
            name="audit_verify",
            description="MCP Tower gap-4 (#928): verify hash-chain integrity of the audit trail + anomaly flags (failure-rate → needs-human-review).",
            inputSchema={
                "type": "object",
                "properties": {
                    "tenant_id": {
                        "type": "string",
                        "description": "Tenant scope (required, non-default)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max events to verify (default 1000, cap 5000)",
                    },
                },
                "required": ["tenant_id"],
            },
        ),
    ]


async def _audit_chain_append(
    *,
    tenant_id: str,
    tool: str,
    decision: str,
    risk_level: str,
    latency_ms: float,
    agent_id: str,
    client_role: str,
    provider: str,
    args_hash: str,
    result_status: str,
    error: str | None = None,
) -> None:
    """issue #928: প্রতিটি tool call → tamper-evident chain event।

    বাংলা: chain store-এ লেখা ব্যর্থ হলেও tool call নিজে ব্যর্থ হবে না — শুধু
    জোরালো warning (audit path degraded); file log (audit_tool_call) সবসময়
    থাকে, তাই observability হারায় না।
    """
    try:
        await get_audit_chain_store().append(
            tenant_id=tenant_id,
            tool=tool,
            agent_id=agent_id,
            client_role=client_role,
            provider=provider,
            args_hash=args_hash,
            result_status=result_status,
            error=error,
        )
    except Exception as exc:  # noqa: BLE001 — audit failure must not break tool calls
        logger.warning(
            f"MCP audit-chain append failed for tool '{tool}': {exc}",
            extra={"mcp_audit_chain_degraded": True},
        )


@app.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    """বাংলা মন্তব্য: এআই এজেন্টের রিকোয়েস্ট অনুযায়ী নির্দিষ্ট গ্রাফ কোয়েরি এক্সিকিউট করে কনটেক্সট রিটার্ন করবে।"""
    if not arguments:
        arguments = {}

    tenant_id = str(arguments.get("tenant_id") or "").strip()
    # MESH-6 (#926): Tower task-queue tools are platform-level — mesh task-এ
    # কোনো tenant context নেই, তাই এই ৩টি tool tenant check বাইপাস করে
    # (বাকি সব tool-এর জন্য আগের মতোই বাধ্যতামূলক)।
    # MCP Tower gap-3 (#927): agent mailbox tools বাইপাসে নেই — MCPAuditEntry
    # প্রতিটি কলে explicit (non-default) tenant_id চায়, তাই এগুলোও সাধারণ
    # tenant contract মানে (tenant isolation issue #927-এর acceptance criteria)।
    _MESH_PLATFORM_TOOLS = ("mesh_dispatch_task", "mesh_task_status", "mesh_release_task")
    if name not in _MESH_PLATFORM_TOOLS and (not tenant_id or tenant_id == "default"):
        return [types.TextContent(type="text", text=json.dumps({"error": "tenant_id is required"}))]

    # ── MCP Tower gap-4 (#928): per-agent audit context + args fingerprint ──
    _agent_id = str(arguments.get("agent_id") or "unknown")
    _client_role = str(arguments.get("client_role") or arguments.get("role") or "agent")
    _provider = str(arguments.get("provider") or "unknown")
    _args_hash = args_fingerprint(arguments)
    _result_status = "ok"

    # ── Policy evaluation (Constitution Law #11: Think Before You Act) ──
    decision, risk_level = evaluate_tool(name)
    start_time = time.monotonic()

    policy_block = _check_policy(name)
    if policy_block is not None:
        latency = (time.monotonic() - start_time) * 1000
        _result_status = "policy_blocked"
        audit_tool_call(
            name,
            decision,
            risk_level,
            latency_ms=latency,
            error="policy_blocked",
            tenant_id=tenant_id,
            agent_id=_agent_id,
            client_role=_client_role,
            provider=_provider,
            args_hash=_args_hash,
            result_status=_result_status,
        )
        await _audit_chain_append(
            tenant_id=tenant_id,
            tool=name,
            decision=decision,
            risk_level=risk_level,
            latency_ms=latency,
            agent_id=_agent_id,
            client_role=_client_role,
            provider=_provider,
            args_hash=_args_hash,
            result_status=_result_status,
            error="policy_blocked",
        )
        logger.warning(f"MCP tool '{name}' blocked by policy: {risk_level}")
        return [types.TextContent(type="text", text=json.dumps(policy_block, indent=2))]

    try:
        if name == "get_render_deploy_preflight":
            from services.render_account_service import RenderAccountService

            overview = RenderAccountService.get_status_overview()
            return [types.TextContent(type="text", text=json.dumps(overview, indent=2))]

        elif name == "get_render_account_status":
            from services.render_account_service import RenderAccountService

            role = arguments.get("account_role")
            from database.supabase_client import db

            states = db.get_render_account_states(role=role)
            return [types.TextContent(type="text", text=json.dumps(states, indent=2))]

        elif name == "refresh_render_account_status":
            from services.render_account_service import RenderAccountService

            role = arguments.get("account_role", "")
            force = bool(arguments.get("force", False))
            result = RenderAccountService.refresh_account_status(
                account_role=role, force=force, manual_by="mcp_tool"
            )
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "get_skill_dependencies":
            # ডাটাবেস সেশন বা মক ডেটা থেকে কনটেক্সট গ্যাদারিং
            if graph_service.dry_run:
                graph_data = {
                    "status": "dry-run",
                    "nodes": ["Python", "FastAPI", "Redis"],
                }
            else:
                async with graph_service.driver.session() as session:
                    result = await session.run("MATCH (n:Skill) RETURN n.name AS name LIMIT 50")
                    records = await result.data()
                    graph_data = {"nodes": [r["name"] for r in records]}

            return [
                types.TextContent(
                    type="text",
                    text=f"SupremeAI Skills Graph Context:\n{json.dumps(graph_data, indent=2)}",
                )
            ]

        elif name == "find_optimal_learning_path":
            start = arguments.get("start_skill")
            end = arguments.get("end_skill")

            path = await graph_service.get_skill_path(start, end)
            return [
                types.TextContent(
                    type="text",
                    text=f"Optimal execution path from {start} to {end}:\n{' -> '.join(path) if path else 'No path found.'}",
                )
            ]

        elif name == "mesh_dispatch_task":
            # MESH-6 (#926): নতুন task Tower queue-তে জমা দাও।
            from core.task_router import get_task_router

            _router = await get_task_router()
            rec = await _router.submit_task(
                task_type=str(arguments.get("task_type") or "custom"),
                title=str(arguments.get("title") or ""),
                payload=arguments.get("payload") or {},
                required_capabilities=arguments.get("required_capabilities") or [],
                target_role=arguments.get("target_role"),
                priority=int(arguments.get("priority", 5)),
            )
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps({"submitted": rec.task_id, "status": rec.status}, indent=2),
                )
            ]

        elif name == "mesh_task_status":
            # MESH-6 (#926): নির্দিষ্ট task বা পুরো queue-র বর্তমান state।
            from core.task_router import get_task_router

            _router = await get_task_router()
            task_id = str(arguments.get("task_id") or "").strip()
            if task_id:
                rec = await _router.get_task(task_id)
                payload_out = rec.model_dump() if rec else {"error": f"task {task_id!r} not found"}
            else:
                payload_out = {
                    "stats": await _router.queue_stats(),
                    "tasks": [t.model_dump() for t in await _router.list_tasks()],
                }
            return [types.TextContent(type="text", text=json.dumps(payload_out, indent=2))]

        elif name == "mesh_release_task":
            # MESH-6 (#926): task cancel/release (operator action)।
            from core.task_router import get_task_router

            _router = await get_task_router()
            task_id = str(arguments.get("task_id") or "").strip()
            rec = await _router.cancel_task(task_id)
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps({"released": rec.task_id, "status": rec.status}, indent=2),
                )
            ]

        elif name == "agent_send":
            # MCP Tower gap-3 (#927): একটি mailbox বার্তা পাঠাও (direct/role/topic)।
            from core.agent_mailbox import get_agent_mailbox

            _mailbox = await get_agent_mailbox()
            msg = await _mailbox.send(
                from_agent=str(arguments.get("from_agent") or ""),
                to_agent=str(arguments.get("to_agent") or ""),
                tenant_id=tenant_id or "default",
                to_role=arguments.get("to_role"),
                topic=arguments.get("topic"),
                body=arguments.get("body") or {},
                reply_to=arguments.get("reply_to"),
                ttl_seconds=arguments.get("ttl_seconds"),
            )
            return [types.TextContent(type="text", text=json.dumps(msg.model_dump(), indent=2))]

        elif name == "agent_inbox":
            # MCP Tower gap-3 (#927): pull-based inbox poll (direct + broadcast)।
            from core.agent_mailbox import get_agent_mailbox

            _mailbox = await get_agent_mailbox()
            messages = await _mailbox.inbox(
                agent_id=str(arguments.get("agent_id") or ""),
                tenant_id=tenant_id or "default",
                role=arguments.get("role"),
                unread_only=bool(arguments.get("unread_only", False)),
                limit=int(arguments.get("limit") or 50),
            )
            payload_out = {
                "agent_id": arguments.get("agent_id"),
                "tenant_id": tenant_id or "default",
                "count": len(messages),
                "messages": [m.model_dump() for m in messages],
            }
            return [types.TextContent(type="text", text=json.dumps(payload_out, indent=2))]

        elif name == "agent_ack":
            # MCP Tower gap-3 (#927): বার্তা ack (idempotent; cross-tenant → error)।
            from core.agent_mailbox import get_agent_mailbox

            _mailbox = await get_agent_mailbox()
            msg = await _mailbox.ack(
                message_id=str(arguments.get("message_id") or ""),
                agent_id=str(arguments.get("agent_id") or ""),
                tenant_id=tenant_id or "default",
            )
            return [types.TextContent(type="text", text=json.dumps(msg.model_dump(), indent=2))]

        elif name == "topic_subscribe":
            # MCP Tower gap-3 (#927): topic pub/sub subscription (idempotent union)।
            from core.agent_mailbox import get_agent_mailbox

            _mailbox = await get_agent_mailbox()
            topics = await _mailbox.subscribe(
                agent_id=str(arguments.get("agent_id") or ""),
                topics=list(arguments.get("topics") or []),
                tenant_id=tenant_id or "default",
            )
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "status": "ok",
                            "agent_id": arguments.get("agent_id"),
                            "tenant_id": tenant_id or "default",
                            "topics": topics,
                        },
                        indent=2,
                    ),
                )
            ]

        elif name == "audit_query":
            # ── MCP Tower gap-4 (#928): per-agent verified audit query ──
            from datetime import UTC, datetime

            since_raw = str(arguments.get("since") or "").strip()
            since = datetime.fromisoformat(since_raw) if since_raw else None
            events = await get_audit_chain_store().query(
                tenant_id,
                agent_id=str(arguments.get("agent_id") or "") or None,
                tool=str(arguments.get("tool") or "") or None,
                since=since,
                limit=int(arguments.get("limit") or 100),
            )
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {"status": "ok", "count": len(events), "events": events}, indent=2
                    ),
                )
            ]

        elif name == "audit_verify":
            # ── MCP Tower gap-4 (#928): hash-chain integrity + anomaly flags ──
            report = await get_audit_chain_store().verify(
                tenant_id,
                limit=int(arguments.get("limit") or 1000),
            )
            report["status"] = "ok" if report["chain_intact"] else "TAMPERED"
            return [types.TextContent(type="text", text=json.dumps(report, indent=2))]

        else:
            raise ValueError(f"Unknown MCP tool: {name}")

    except Exception as e:
        _result_status = "error"
        logger.error(f"MCP Server execution error: {e}")
        return [types.TextContent(type="text", text=f"Error gathering graph context: {e!s}")]
    finally:
        # ── Audit logging (Constitution Law #19: Observable) ──
        latency = (time.monotonic() - start_time) * 1000
        audit_tool_call(
            name,
            decision,
            risk_level,
            latency_ms=latency,
            tenant_id=tenant_id,
            agent_id=_agent_id,
            client_role=_client_role,
            provider=_provider,
            args_hash=_args_hash,
            result_status=_result_status,
        )
        # ── MCP Tower gap-4 (#928): tamper-evident chain event (awaited) ──
        await _audit_chain_append(
            tenant_id=tenant_id,
            tool=name,
            decision=decision,
            risk_level=risk_level,
            latency_ms=latency,
            agent_id=_agent_id,
            client_role=_client_role,
            provider=_provider,
            args_hash=_args_hash,
            result_status=_result_status,
        )


async def main():
    # Stdio ট্রান্সপোর্টের মাধ্যমে সার্ভারটি রান করানো (Standard Input/Output)
    from mcp.server.stdio import stdio_server

    logger.info("Starting SupremeAI MCP Graph Server over Stdio...")
    async with stdio_server() as (read_stream, write_server):
        await app.run(read_stream, write_server, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
