"""This module defines and manages a centralized allowlist for various "Master Control Program" (MCP) servers and their associated tools within the SupremeAI ecosystem. It provides comprehensive configuration details for launching and interacting with a diverse set of external AI agents and tools (e.g., GitHub, Slack, Gemini CLI, OpenHands, etc.), including their execution commands, required environment variables, and explicitly whitelisted API paths and functionalities. The module also offers utility functions to validate server access and precisely determine which specific tools are permitted for each server, thereby ensuring secure, controlled, and auditable interaction with external capabilities across the SupremeAI platform.

Key Components:
- `get_mcp_servers()`: Provides a comprehensive dictionary of all whitelisted MCP servers, including their execution commands, environment variables, and explicitly allowed API paths and tools.
- `MCPAllowlist`: A utility class for validating MCP server access and determining the permissibility of specific tools requested by or for a given server.
- `MCPAllowlist.validate_server()`: Checks if a specified MCP server is recognized and whitelisted, returning its configuration if found.
- `MCPAllowlist.allowed_tools()`: Compares a list of requested tools against the officially allowed tools for a given MCP server, identifying any unauthorized requests.

Dependencies:
- `os`: For accessing environment variables to configure MCP servers.
- `typing`: For type hinting to improve code readability and maintainability."""

from __future__ import annotations

import os
from typing import Any


def get_mcp_servers() -> dict[str, Any]:
    settings: dict[str, Any] = {
        "github": {
            "command": "uvx",
            "args": ["mcp-server-github"],
            "env": {"GITHUB_TOKEN": os.getenv("GITHUB_TOKEN", "")},
            "allowed_paths": ["/api/v1/gateway"],
            "allowed_tools": [
                "search_repositories",
                "get_file_contents",
                "create_issue",
            ],
        },
        "slack": {
            "command": "uvx",
            "args": ["mcp-server-slack"],
            "env": {"SLACK_BOT_TOKEN": os.getenv("SLACK_BOT_TOKEN", "")},
            "allowed_paths": ["/api/v1/gateway"],
            "allowed_tools": ["send_message", "list_channels"],
        },
        "filesystem": {
            "command": "uvx",
            "args": [
                "mcp-server-filesystem",
                os.getenv("MCP_ALLOWED_DIR", os.getcwd()),
            ],
            "allowed_paths": ["/api/v1/gateway"],
            "allowed_tools": ["read_file", "write_file", "list_directory"],
        },
        # bangla: গুগল অফিসিয়াল ফ্রি এআই CLI এজেন্ট
        "gemini-cli": {
            "command": "uvx",
            "args": ["gemini-cli-mcp"],
            "env": {
                "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY", ""),
                "GOOGLE_API_KEY": os.getenv("GOOGLE_API_KEY", ""),
            },
            "allowed_paths": ["/api/v1/gateway"],
            "allowed_tools": ["read_file", "write_file", "run_command", "search_web"],
        },
        # bangla: ওপেন-সোর্স Devin বিকল্প
        "openhands": {
            "command": "uvx",
            "args": ["openhands-mcp-server"],
            "env": {
                "OPENHANDS_API_KEY": os.getenv("OPENHANDS_API_KEY", ""),
            },
            "allowed_paths": ["/api/v1/gateway"],
            "allowed_tools": [
                "browse_web",
                "execute_command",
                "read_file",
                "write_file",
                "search_code",
            ],
        },
        # bangla: হেডলেস মোডে অটোনোমাস কোডিং এজেন্ট
        "cline-cli": {
            "command": "npx",
            "args": ["@cline/cli", "--headless"],
            "env": {
                "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", ""),
                "CLINE_API_KEY": os.getenv("CLINE_API_KEY", ""),
            },
            "allowed_paths": ["/api/v1/gateway"],
            "allowed_tools": [
                "edit_file",
                "run_terminal_command",
                "search_replace",
                "read_file",
            ],
        },
        # bangla: কাস্টমাইজেবল এআই কোডিং ওয়ার্কফ্লো প্ল্যাটফর্ম
        "continue-dev": {
            "command": "uvx",
            "args": ["continue-mcp-server"],
            "env": {
                "CONTINUE_API_KEY": os.getenv("CONTINUE_API_KEY", ""),
            },
            "allowed_paths": ["/api/v1/gateway"],
            "allowed_tools": [
                "chat",
                "edit",
                "generate_code",
                "refactor",
            ],
        },
        # bangla: টার্মিনাল পেয়ার প্রোগ্রামার
        "aider": {
            "command": "uvx",
            "args": ["aider-mcp"],
            "env": {
                "AIDER_API_KEY": os.getenv("AIDER_API_KEY", ""),
                "OPENROUTER_API_KEY": os.getenv("OPENROUTER_API_KEY", ""),
            },
            "allowed_paths": ["/api/v1/gateway"],
            "allowed_tools": [
                "git_commit",
                "edit_file",
                "lint_code",
                "run_tests",
            ],
        },
        # bangla: প্রিন্সটন ইউনিভার্সিটির গিটহাব ইস্যু সলভিং এজেন্ট
        "swe-agent": {
            "command": "uvx",
            "args": ["swe-agent-mcp"],
            "env": {
                "GITHUB_TOKEN": os.getenv("GITHUB_TOKEN", ""),
                "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
            },
            "allowed_paths": ["/api/v1/gateway"],
            "allowed_tools": [
                "resolve_github_issue",
                "create_pr",
                "run_tests",
                "browse_repo",
            ],
        },
        # bangla: টার্মিনাল-ড্রাইভেন AI কোডিং এঞ্জিন
        "plandex": {
            "command": "uvx",
            "args": ["plandex-mcp-server"],
            "env": {
                "PLANDEX_API_KEY": os.getenv("PLANDEX_API_KEY", ""),
            },
            "allowed_paths": ["/api/v1/gateway"],
            "allowed_tools": [
                "execute_plan",
                "rollback_change",
                "apply_patch",
                "run_command",
            ],
        },
        # bangla: ওপেন-সোর্স Devin বিকল্প, নিজস্ব ব্রাউজার এজেন্ট
        "devika": {
            "command": "uvx",
            "args": ["devika-mcp-server"],
            "env": {
                "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY", ""),
                "GROQ_API_KEY": os.getenv("GROQ_API_KEY", ""),
            },
            "allowed_paths": ["/api/v1/gateway"],
            "allowed_tools": [
                "web_search",
                "browser_automation",
                "code_execution",
                "plan_feature",
            ],
        },
        # bangla: অটোনোমাস অ্যাপ বিল্ডার, স্টেপ-বাই-স্টেপ ডেভেলপার
        "gpt-pilot": {
            "command": "uvx",
            "args": ["gpt-pilot-mcp-server"],
            "env": {
                "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
                "PYTHAGORA_API_KEY": os.getenv("PYTHAGORA_API_KEY", ""),
            },
            "allowed_paths": ["/api/v1/gateway"],
            "allowed_tools": [
                "generate_full_app",
                "ask_clarification",
                "run_integration_tests",
                "write_tests",
            ],
        },
        # bangla: জিরো-কস্ট আনলিমিটেড এআই কোডিং এঞ্জিন
        "codeium": {
            "command": "uvx",
            "args": ["codeium-lang-server"],
            "env": {
                "CODEIUM_API_KEY": os.getenv("CODEIUM_API_KEY", ""),
            },
            "allowed_paths": ["/api/v1/gateway"],
            "allowed_tools": [
                "autocomplete",
                "chat",
                "refactor",
                "search_code",
            ],
        },
    }
    return settings


class MCPAllowlist:
    @staticmethod
    def validate_server(name: str) -> dict[str, Any]:
        servers = get_mcp_servers()
        server = servers.get(name)
        if not server:
            return {"allowed": False, "reason": "unknown mcp server"}
        return {
            "allowed": True,
            "server": name,
            "tools": server.get("allowed_tools", []),
        }

    @staticmethod
    def allowed_tools(server_name: str, requested: list[str]) -> dict[str, Any]:
        info = MCPAllowlist.validate_server(server_name)
        if not info["allowed"]:
            return {"allowed": False, "denied": requested}
        allowed = list(info.get("tools", []))
        denied = [tool for tool in requested if tool not in allowed]
        return {"allowed": not bool(denied), "allowed_tools": allowed, "denied": denied}
