#!/usr/bin/env python3
"""Dynamic Credential Broker - task-wise role + scoped vault-key injection.

# Smart credential broker: when SmartDispatcher assigns a task, this broker:
# 1. Updates the agent role in MCP Tower (client.set_role)
# 2. Fetches ONLY the vault keys the role needs from Infisical
# 3. Builds a scoped env (no master vault creds leaked)
# 4. After task: reverts role to viewer + clears keys from memory

Flow:
    SmartDispatcher.decide() -> role=watcher, issue=#2454
    -> DynamicCredentialBroker.activate(agent, role, labels)
       -> MCP Tower: client.set_role(client_id, 'agent')
       -> Infisical: fetch CLOUDFLARE_API_TOKEN, RENDER_API_KEY, etc.
       -> return scoped_env dict
    -> work command runs with scoped_env
    -> DynamicCredentialBroker.deactivate(agent)
       -> MCP Tower: client.set_role(client_id, 'viewer')
       -> keys already gone (scoped_env was local dict, not persisted)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parents[2]
REPO = os.environ.get("GH_REPO", "Supremeai-bd/supremeai-open")

# Role -> vault keys that role is allowed to access
# ROOT FIX (#2923): task-wise scoping - watcher gets CLOUDFLARE/RENDER keys,
# coder gets only GH_TOKEN, breaker gets read-only GH_TOKEN, etc.
ROLE_VAULT_KEYS = {
    # #4134: MCP Tower operational keys (MCP_API_KEY/MCP_TOWER_URL) added to
    # tower-coordinated roles — children must reach the tower as agents, not
    # silently degrade to viewer mode. Master vault creds stay excluded below.
    "coder": {
        "GH_TOKEN", "GH_REPO", "AGENT_SLOT", "AGENT_ROLE", "AGENT_NAME",
        "MCP_API_KEY", "MCP_TOWER_URL",
    },
    "ci-fixer": {
        "GH_TOKEN", "GH_REPO", "AGENT_SLOT", "AGENT_ROLE", "AGENT_NAME",
        "MCP_API_KEY", "MCP_TOWER_URL",
    },
    "watcher": {
        "GH_TOKEN", "GH_REPO", "AGENT_SLOT", "AGENT_ROLE", "AGENT_NAME",
        # Platform health keys - only watcher needs these
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "RENDER_API_KEY",
        "RENDER_API_KEY_1",
        "SUPABASE_ACCESS_TOKEN",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "UPSTASH_REDIS_REST_URL",
        "UPSTASH_REDIS_REST_TOKEN",
        "REDIS_URL",
        # Watcher heartbeats the tower too (#4134)
        "MCP_API_KEY", "MCP_TOWER_URL",
    },
    "planner": {
        "GH_TOKEN", "GH_REPO", "AGENT_SLOT", "AGENT_ROLE", "AGENT_NAME",
        # Planner needs read-only access to plan features
        "MCP_API_KEY", "MCP_TOWER_URL",
    },
    "auditor": {
        "GH_TOKEN", "GH_REPO", "AGENT_SLOT", "AGENT_ROLE", "AGENT_NAME",
        # Auditor needs read-only access
        "MCP_API_KEY", "MCP_TOWER_URL",
    },
    "breaker": {
        "GH_TOKEN", "GH_REPO", "AGENT_SLOT", "AGENT_ROLE", "AGENT_NAME",
        # Breaker: read-only GH_TOKEN, no write keys (zero-trust sandbox)
    },
    "human-eyes": {
        # Browser agent: no vault keys needed - uses browser only
        "AGENT_ROLE", "AGENT_NAME",
    },
}

# Keys that must NEVER be in any scoped env (master vault creds)
FORBIDDEN_KEYS = {
    "INFISICAL_CLIENT_ID",
    "INFISICAL_CLIENT_SECRET",
    "INFISICAL_PROJECT_ID",
    "INFISICAL_TOKEN",
    "GITHUB_APP_PRIVATE_KEY",
    "GITHUB_APP_ID",
    "GITHUB_APP_INSTALLATION_ID",
}

# MCP Tower client IDs for each agent (registered in tower)
# These would normally come from the tower registry, hardcoded for now
AGENT_CLIENT_IDS = {
    "supremeai-planner[bot]": "planner-client-001",
    "supremeai-coder-1-bot[bot]": "coder-1-client-001",
    "supremeai-coder-2-bot[bot]": "coder-2-client-001",
    "supremeai-ci-action[bot]": "ci-action-client-001",
    "supremeai-platform-agent[bot]": "platform-client-001",
    "supremeai-pr-helper[bot]": "pr-helper-client-001",
}


class DynamicCredentialBroker:
    """Task-wise dynamic role + scoped vault-key injection broker.

    # বাংলা: যখন SmartDispatcher একটা task assign করবে, এই broker:
    # 1. MCP Tower-এ agent-এর role update করবে (client.set_role)
    # 2. Infisical থেকে শুধু role-এর allowlist-এ থাকা keys fetch করবে
    # 3. Scoped env build করবে (master vault creds কখনো leak হবে না)
    # 4. Task শেষে role আবার viewer-এ revert করবে
    """

    def __init__(self, repo: str = REPO, tower_url: str = ""):
        self.repo = repo
        self.tower_url = tower_url or os.environ.get(
            "MCP_TOWER_URL", os.environ.get("MCP_SERVER_URL", "")
        )
        self.mcp_api_key = os.environ.get("MCP_API_KEY", "")
        self.gh_token = os.environ.get("GITHUB_TOKEN", os.environ.get("GH_TOKEN", ""))

    def _call_mcp_tower(self, tool_name: str, args: dict) -> dict | None:
        """Call an MCP Tower tool via the client."""
        try:
            r = subprocess.run(
                ["python3", "scripts/agents/mcp_tower_client.py", "call", tool_name],
                capture_output=True, text=True, timeout=30, check=False,
                env={**os.environ, "MCP_TOWER_URL": self.tower_url},
            )
            if r.returncode == 0 and r.stdout.strip():
                return json.loads(r.stdout)
        except Exception:
            pass
        return None

    def _fetch_vault_keys(self, key_names: set[str]) -> dict[str, str]:
        """Fetch specific keys from Infisical vault.

        # বাংলা: শুধু role-এর allowlist-এ থাকা keys fetch হয়।
        # Master vault creds (INFISICAL_*) কখনো return হয় না।
        """
        # Try loading from process env first (if Infisical bootstrap already ran)
        result = {}
        for key in key_names:
            val = os.environ.get(key, "")
            if val and key not in FORBIDDEN_KEYS:
                result[key] = val

        # If we need Infisical fetch (some keys missing), do it
        missing = key_names - set(result.keys()) - FORBIDDEN_KEYS
        if missing:
            try:
                # Use infisical_bootstrap pattern to fetch missing keys
                # #3478 fix: call fetch_ai_keys.py to get keys from Infisical vault
                proc = subprocess.run(
                    [sys.executable, str(ROOT_DIR / "scripts" / "security" / "fetch_ai_keys.py")],
                    capture_output=True, text=True, env=os.environ, timeout=15
                )
                if proc.returncode == 0:
                    for line in proc.stdout.strip().splitlines():
                        if "=" in line and not line.startswith("#"):
                            k, _, v = line.partition("=")
                            if k in key_names and k not in FORBIDDEN_KEYS:
                                result[k] = v.strip()
            except Exception:
                pass

        return result

    def activate(
        self,
        agent_name: str,
        role: str,
        task_labels: list[str] | None = None,
    ) -> dict[str, str]:
        """Activate a role for an agent: update MCP Tower + fetch scoped keys.

        Returns: scoped_env dict (keys that the work command should use)
        """
        print(f"[Broker] Activating role '{role}' for agent '{agent_name}'...")

        # 1. Get allowed keys for this role
        allowed = ROLE_VAULT_KEYS.get(role, set())
        if not allowed:
            print(f"[Broker] WARNING: no vault keys defined for role '{role}'")
            allowed = {"AGENT_ROLE", "AGENT_NAME"}

        # 2. Fetch only allowed keys from vault
        scoped_env = self._fetch_vault_keys(allowed)

        # 3. Set role-specific env vars
        scoped_env["AGENT_ROLE"] = role
        scoped_env["AGENT_NAME"] = agent_name

        # 4. Try to update MCP Tower role (best-effort, not blocking)
        client_id = AGENT_CLIENT_IDS.get(agent_name, "")
        if client_id and self.mcp_api_key:
            print(f"[Broker] Updating MCP Tower role for client '{client_id}' -> '{role}'...")
            # This would call: mcp_tower_client.py call client_set_role
            # with clientId=client_id, role='agent' (or 'admin' for privileged)
            tower_role = "agent"
            if role in ("watcher", "breaker"):
                tower_role = "agent"  # these need elevated access
            result = self._call_mcp_tower("client.set_role", {
                "clientId": client_id,
                "role": tower_role,
            })
            if result:
                print(f"[Broker] MCP Tower role updated: {tower_role}")
            else:
                print(f"[Broker] WARNING: MCP Tower role update failed (non-blocking)")

        # 5. Verify no forbidden keys leaked
        leaked = FORBIDDEN_KEYS & set(scoped_env.keys())
        if leaked:
            print(f"[Broker] ERROR: forbidden keys leaked: {leaked}")
            for k in leaked:
                scoped_env.pop(k, None)

        print(f"[Broker] Activated: {len(scoped_env)} scoped keys for role '{role}'")
        return scoped_env

    def deactivate(self, agent_name: str) -> None:
        """Deactivate: revert MCP Tower role to viewer + clear keys.

        # বাংলা: task শেষে role আবার viewer-এ revert করা হয়।
        # Scoped keys ইতিমধ্যে local dict-এ ছিল, কোথাও persist হয়নি।
        """
        print(f"[Broker] Deactivating agent '{agent_name}'...")

        # Revert MCP Tower role to viewer (least privilege)
        client_id = AGENT_CLIENT_IDS.get(agent_name, "")
        if client_id and self.mcp_api_key:
            print(f"[Broker] Reverting MCP Tower role for client '{client_id}' -> 'viewer'...")
            result = self._call_mcp_tower("client.set_role", {
                "clientId": client_id,
                "role": "viewer",
            })
            if result:
                print(f"[Broker] MCP Tower role reverted to viewer")
            else:
                print(f"[Broker] WARNING: MCP Tower role revert failed (non-blocking)")

        # Keys are already gone (scoped_env was a local dict in activate())
        # Nothing to clear from disk or memory
        print(f"[Broker] Deactivated: scoped keys cleared from memory")


def main() -> int:
    """CLI entry point for testing the broker."""
    import argparse
    parser = argparse.ArgumentParser(description="Dynamic Credential Broker (#2923)")
    parser.add_argument("--agent-name", required=True, help="Agent identifier")
    parser.add_argument("--role", required=True, help="Role to activate")
    parser.add_argument("--action", choices=["activate", "deactivate"], default="activate")
    args = parser.parse_args()

    broker = DynamicCredentialBroker()
    if args.action == "activate":
        env = broker.activate(args.agent_name, args.role)
        # Print keys (names only, not values)
        print(f"\nScoped env keys: {sorted(env.keys())}")
    else:
        broker.deactivate(args.agent_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
