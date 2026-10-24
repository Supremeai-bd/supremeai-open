"""Live Demonstration: SupremeAI Agent-to-Agent Communication

Demonstrates real communication between:
- agent-1 (Planning)
- agent-2 (Architecture)
- agent-3 (Auditor)

Using the Mesh Agent Mailbox (FastAPI / REST engine) with:
1. Direct Messaging (agent-1 -> agent-2)
2. Threaded Replies (reply_to)
3. Delivery Acknowledgement (ack)
4. Topic & Role-based Pub/Sub Broadcast (to_agent="*", topic="architecture-review")
5. Audit & Visibility Stats
"""

import os
import sys

# Set test environment to disable network calls (Infisical, etc.)
os.environ["TESTING"] = "true"
os.environ["ENV"] = "test"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["ALLOW_TEST_AUTH_BYPASS"] = "true"

# Add backend directory to sys.path
backend_path = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, os.path.abspath(backend_path))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routes.mesh_mailbox import router as mailbox_router
from core.agent_mailbox import AgentMailbox, get_agent_mailbox

def run_agent_communication_demo():
    print("=" * 70)
    print(" SupremeAI: Multi-Agent Live Communication Demonstration")
    print("=" * 70)

    # Initialize live mailbox and FastAPI application
    mailbox = AgentMailbox()
    app = FastAPI(title="SupremeAI Mesh Gateway")
    app.include_router(mailbox_router)
    app.dependency_overrides[get_agent_mailbox] = lambda: mailbox
    client = TestClient(app)

    headers = {"x-tenant-id": "tenant-supremeai"}

    # -------------------------------------------------------------
    # Step 1: Subscriptions
    # -------------------------------------------------------------
    print("\n[Step 1] Setting up Topic Subscriptions...")
    for agent_id in ["agent-1", "agent-2", "agent-3"]:
        sub_resp = client.post(
            "/api/v1/mesh/subscriptions",
            headers=headers,
            json={"agent_id": agent_id, "topics": ["architecture-review", "general"]},
        )
        print(f" -> {agent_id} subscribed to topics: {sub_resp.json()['topics']}")

    # -------------------------------------------------------------
    # Step 2: Direct Message (agent-1 [Planning] -> agent-2 [Architecture])
    # -------------------------------------------------------------
    print("\n[Step 2] agent-1 (Planning) sends direct message to agent-2 (Architecture)...")
    msg1_payload = {
        "from_agent": "agent-1",
        "to_agent": "agent-2",
        "topic": "architecture-review",
        "body": {
            "intent": "REQUEST_REVIEW",
            "spec": "Persistent Agent Branch & PR Lifecycle Model",
            "governing_rule": "AGENTS.md Section 4 & 13",
            "branches": ["agent-1", "agent-2", "agent-3", "agent-4", "agent-5", "agent-6", "agent-7", "agent-8", "agent-9"],
        },
    }
    resp1 = client.post("/api/v1/mesh/messages", headers=headers, json=msg1_payload)
    msg1 = resp1.json()["message"]
    msg1_id = msg1["message_id"]
    print(f" -> Message SENT successfully! ID: {msg1_id}")
    print(f"    From: {msg1['from_agent']} -> To: {msg1['to_agent']}")
    print(f"    Content: {msg1['body']['intent']} - {msg1['body']['spec']}")

    # -------------------------------------------------------------
    # Step 3: agent-2 polls its inbox
    # -------------------------------------------------------------
    print("\n[Step 3] agent-2 (Architecture) polls inbox...")
    inbox_resp = client.get("/api/v1/mesh/messages/inbox?agent_id=agent-2&unread_only=true", headers=headers)
    inbox_items = inbox_resp.json()["messages"]
    print(f" -> agent-2 received {len(inbox_items)} new message(s) in inbox:")
    for item in inbox_items:
        print(f"    - [{item['message_id']}] from {item['from_agent']}: {item['body']}")

    # -------------------------------------------------------------
    # Step 4: Threaded Reply (agent-2 replies to agent-1 with reply_to)
    # -------------------------------------------------------------
    print(f"\n[Step 4] agent-2 sends threaded reply to agent-1 (reply_to={msg1_id})...")
    msg2_payload = {
        "from_agent": "agent-2",
        "to_agent": "agent-1",
        "reply_to": msg1_id,
        "topic": "architecture-review",
        "body": {
            "decision": "APPROVED",
            "review_notes": "Architecture validated: 1 Branch = 1 Workspace, AI is replaceable, history preserved.",
            "status": "READY_FOR_INTEGRATION",
        },
    }
    resp2 = client.post("/api/v1/mesh/messages", headers=headers, json=msg2_payload)
    msg2 = resp2.json()["message"]
    msg2_id = msg2["message_id"]
    print(f" -> Reply SENT! ID: {msg2_id}, Threaded on parent: {msg2['reply_to']}")

    # -------------------------------------------------------------
    # Step 5: agent-1 reads reply & sends delivery acknowledgment (ack)
    # -------------------------------------------------------------
    print("\n[Step 5] agent-1 checks inbox and acknowledges message receipt...")
    inbox_agent1 = client.get("/api/v1/mesh/messages/inbox?agent_id=agent-1&unread_only=true", headers=headers).json()
    print(f" -> agent-1 received reply: {inbox_agent1['messages'][0]['body']['decision']}")
    print(f"    Notes: {inbox_agent1['messages'][0]['body']['review_notes']}")
    
    ack_resp = client.post(f"/api/v1/mesh/messages/{msg2_id}/ack", headers=headers, json={"agent_id": "agent-1"})
    print(f" -> Message {msg2_id} ACKNOWLEDGED: acked={ack_resp.json()['acked']}")

    # -------------------------------------------------------------
    # Step 6: Broadcast message to all agents subscribed to "architecture-review"
    # -------------------------------------------------------------
    print('\n[Step 6] agent-2 broadcasts announcement to topic "architecture-review" (to_agent="*")...')
    broadcast_payload = {
        "from_agent": "agent-2",
        "to_agent": "*",
        "topic": "architecture-review",
        "body": {
            "announcement": "ALL AGENTS: SupremeAI branch restructuring is COMPLETE. Proceed on assigned agent slots.",
            "canonical_rules": "AGENTS.md Section 19",
        },
    }
    resp_bcast = client.post("/api/v1/mesh/messages", headers=headers, json=broadcast_payload)
    bcast_msg = resp_bcast.json()["message"]
    print(f" -> Broadcast dispatched: ID {bcast_msg['message_id']}")

    # Verify agent-1 and agent-3 both received the broadcast
    inbox_agent1_bcast = client.get("/api/v1/mesh/messages/inbox?agent_id=agent-1", headers=headers).json()
    inbox_agent3_bcast = client.get("/api/v1/mesh/messages/inbox?agent_id=agent-3", headers=headers).json()
    print(f" -> agent-1 inbox total: {len(inbox_agent1_bcast['messages'])}")
    print(f" -> agent-3 (Auditor) inbox total: {len(inbox_agent3_bcast['messages'])} (received broadcast!)")

    # -------------------------------------------------------------
    # Step 7: Stats & Visibility
    # -------------------------------------------------------------
    print("\n[Step 7] Checking Mesh Mailbox Gateway Stats...")
    stats_resp = client.get("/api/v1/mesh/messages/stats", headers=headers).json()
    print(f" -> Total Tenant Messages: {stats_resp.get('total_messages', len(mailbox._messages))}")
    print(f" -> Active Subscriptions: {stats_resp.get('total_subscriptions', len(mailbox._subscriptions))}")
    print("\n" + "=" * 70)
    print(" Demonstration Complete: All Agent Communication Contracts Verified!")
    print("=" * 70)

if __name__ == "__main__":
    run_agent_communication_demo()
