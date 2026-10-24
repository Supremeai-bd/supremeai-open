"""Contract test for Batch 1: P0 Security & Autonomous Agent Bus (#3304, #2644, #4168)."""

import tempfile
from pathlib import Path
import pytest

from scripts.agents.a2a_messaging_bus import A2ABus
from scripts.agents.credential_manager import (
    build_scoped_env,
    CredentialError,
    FORBIDDEN_ENV_KEYS,
)
from scripts.agents.automation_watchdog import evaluate


def test_a2a_bus_send_and_receive():
    """Verify that A2ABus sends messages to inbox and clears on receive."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bus = A2ABus(inbox_dir=Path(tmpdir))
        msg = {"type": "intent", "action": "test_handoff"}
        msg_id = bus.send("lane-coder", msg, sender="tester")
        assert msg_id is not None

        # Verify inbox file exists and contains message
        inbox_file = bus._inbox_path("lane-coder")
        assert inbox_file.exists()

        # Receive clears inbox
        received = bus.receive("lane-coder")
        assert len(received) == 1
        assert received[0]["message_id"] == msg_id
        assert received[0]["body"] == msg
        assert received[0]["sender"] == "tester"

        # Subsequent receive is empty
        assert bus.receive("lane-coder") == []


def test_build_scoped_env_least_privilege():
    """Verify least-privilege scoping and forbidden keys rejection."""
    scoped = build_scoped_env(
        role="coder",
        token="gh_test_token_123",
        agent_name="agent-coder-1",
        slot="agent-1",
        repo="Supremeai-bd/supremeai-open",
        base_env={"INFISICAL_UNIVERSAL_AUTH_CLIENT_SECRET": "should_be_dropped", "CUSTOM_ALLOWED": "drop"},
    )
    assert scoped["GH_REPO"] == "Supremeai-bd/supremeai-open"
    assert scoped["AGENT_ROLE"] == "coder"
    assert scoped["AGENT_NAME"] == "agent-coder-1"
    assert scoped["AGENT_SLOT"] == "agent-1"
    assert scoped["GH_TOKEN"] == "gh_test_token_123"
    # Verify forbidden keys never leak into scoped env
    assert "INFISICAL_UNIVERSAL_AUTH_CLIENT_SECRET" not in scoped
    assert not (set(scoped) & FORBIDDEN_ENV_KEYS)

    # Unknown role raises CredentialError
    with pytest.raises(CredentialError, match="no scoped env contract for role"):
        build_scoped_env(role="unknown-rogue-role")


def test_watchdog_evaluate_healthy():
    """Verify watchdog evaluation reports no findings when heartbeats are fresh."""
    now = 1000000.0
    obs = {
        "heartbeats": [{"name": "loop", "last_seen_epoch": now - 100}],
        "claims": [],
        "evaluator": {"name": "evaluator", "last_success_epoch": now - 200},
    }
    findings = evaluate(obs, now)
    assert findings == []
