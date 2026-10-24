"""SupremeAI Task Dispatcher: Send START_TASK messages to all active agents.

Dispatches direct messages and topic broadcasts across all active agent slots
using SupremeAI Mesh AgentMailbox.

#1821 (single source of truth): the slot -> role map is NO LONGER hardcoded
here. It is resolved from the canonical governance registry
`docs/master_docs/AGENT_SLOT_REGISTRY.yaml` at runtime, so this script can
never drift from the governance YAML again. Drift is enforced by
`scripts/agents/check_slot_registry_drift.py` (pre-push gate).
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Set test bypass for environment safely
os.environ["TESTING"] = "true"
os.environ["ENV"] = "test"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["ALLOW_TEST_AUTH_BYPASS"] = "true"

backend_path = os.path.join(os.path.dirname(__file__), "..", "..", "backend")
sys.path.insert(0, os.path.abspath(backend_path))

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]
SLOT_REGISTRY_YAML = REPO_ROOT / "docs" / "master_docs" / "AGENT_SLOT_REGISTRY.yaml"

# Task text per governance role (roles come from the YAML; task wording stays here).
DEFAULT_TASKS = {
    "ci-action": "Watch GitHub Actions workflow runs, triage failures, keep pipelines green",
    "pr-helper": "Verify PR compliance, check test coverage, keep the merge train moving",
    "platform-agent": "Execute scheduled platform health sweep, remediate failing surfaces",
    "super agent": "Monitor mesh health, supervise slot allocation, maintain platform heartbeat",
    "coder": "Claim open implementation issues, write code & tests, open PR",
    "planner": "Audit the issue queue, decompose into structured handoff plans",
}
FALLBACK_TASK = "Commence your lane workflow and report status."


def resolve_active_agents(yaml_path: Path | None = None) -> dict:
    """Resolve the active slot -> {'role', 'task'} map FROM the governance YAML.

    Single source of truth: docs/master_docs/AGENT_SLOT_REGISTRY.yaml (#1821).
    Only slots with `active: true` are dispatched; role == the YAML `tool`
    value; task text is looked up per role family.
    """
    import yaml

    path = Path(yaml_path) if yaml_path else SLOT_REGISTRY_YAML
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    agents: dict = {}
    for slot in data.get("slots", []):
        slot_id = str(slot.get("slot", ""))
        if not slot_id.startswith("agent-") or not slot.get("active"):
            continue
        tool = str(slot.get("tool", "")).strip()
        if not tool:
            continue
        task = FALLBACK_TASK
        tool_lower = tool.lower()
        for key, text in DEFAULT_TASKS.items():
            if key in tool_lower:
                task = text
                break
        agents[slot_id] = {"role": tool, "task": task}
    return agents


async def dispatch_tasks():
    print("=" * 70)
    print(" SupremeAI Multi-Agent Task Dispatcher")
    print("=" * 70)

    # Lazy import — keeps this module importable by gates (check_slot_registry_drift)
    # without pulling in backend core/mesh dependencies.
    from core.agent_mailbox import get_agent_mailbox, BROADCAST_TARGET

    active_agents = resolve_active_agents()
    print(
        f" -> Resolved {len(active_agents)} active slots from {SLOT_REGISTRY_YAML.name} (governance truth)."
    )

    mailbox = await get_agent_mailbox()
    tenant_id = "tenant-supremeai"
    sender = "orchestrator-main"

    # 1. Topic Subscriptions
    print("\n[Step 1] Subscribing agents to topics...")
    for agent_id in active_agents:
        await mailbox.subscribe(
            agent_id=agent_id,
            topics=["task-dispatch", "general"],
            tenant_id=tenant_id,
        )
    print(f" -> Subscribed {len(active_agents)} agents to 'task-dispatch' & 'general'.")

    # 2. Broadcast Message to ALL agents
    print("\n[Step 2] Sending Broadcast Signal to ALL agents...")
    broadcast_body = {
        "intent": "START_TASK",
        "priority": "HIGH",
        "message": "All active agent slots: commence assigned workflows and report status.",
        "active_slots": list(active_agents.keys()),
    }
    broadcast_msg = await mailbox.send(
        from_agent=sender,
        to_agent=BROADCAST_TARGET,
        tenant_id=tenant_id,
        topic="task-dispatch",
        body=broadcast_body,
    )
    print(f" -> Broadcast sent! ID: {broadcast_msg.message_id}")

    # 3. Direct Targeted Messages to Each Agent Slot
    print("\n[Step 3] Sending Direct Task Assignments to Active Agents...")
    dispatched = []
    for agent_id, details in active_agents.items():
        direct_body = {
            "intent": "ASSIGN_TASK",
            "slot": agent_id,
            "role": details["role"],
            "instruction": details["task"],
            "status": "IN_PROGRESS",
            "governing_rule": "AGENTS.md Core Loop",
        }
        res = await mailbox.send(
            from_agent=sender,
            to_agent=agent_id,
            tenant_id=tenant_id,
            topic="task-dispatch",
            body=direct_body,
        )
        dispatched.append((agent_id, res.message_id, details["role"]))
        print(
            f" -> [{agent_id}] ({details['role']}): Dispatched Message {res.message_id}"
        )

    # 4. Verify inboxes
    print("\n[Step 4] Verifying Inboxes...")
    for agent_id in active_agents:
        inbox = await mailbox.inbox(
            agent_id=agent_id,
            tenant_id=tenant_id,
            unread_only=True,
        )
        print(f" -> {agent_id}: {len(inbox)} message(s) waiting in inbox.")

    print("\n" + "=" * 70)
    print(
        f" ✅ Dispatch complete — {len(dispatched)} agents engaged (roles derived from YAML)."
    )
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(dispatch_tasks())
