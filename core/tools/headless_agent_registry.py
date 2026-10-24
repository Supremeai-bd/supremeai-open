# backend/tools/headless_agent_registry.py
"""
Headless, Zero-Cost Terminal-Based AI Agent Registry
=====================================================

স্থানীয় নথিপত্র: docs/-01-admin's plan/headless,zro cost terminal base ai agent/

এই মডিউলটি SupremeAI-এর প্যারালেল এজেন্ট এক্সিকিউটরের জন্য সব ধরনের টার্মিনাল-বেইজড এআই এজেন্টের কনফিগারেশন হারhibit করে।
প্রতিটি এজেন্টের জন্য MCP (Model Context Protocol) সার্ভার কনফিগারেশন এবং CLI কমান্ড সংজ্ঞায়িত করা হয়েছে।
"""

from __future__ import annotations

from typing import Any

from core.config import settings


def get_headless_agent_configs() -> dict[str, dict[str, Any]]:
    """বাংলা মন্তব্য: সব হেডলেস এজেন্টের কনফিগারেশন রিটার্ন করে। (ডাটাবেস থেকে)"""
    try:
        from core.logging_config import logger
        from tools.mcp.mcp_supabase import _get_connection

        conn = _get_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("SELECT agent_name, config_json FROM agent_configs WHERE status = 'active'")
            rows = cur.fetchall()
            if rows:
                return {row[0]: row[1] for row in rows}
    except Exception as e:
        logger.error(f"Failed to fetch agent configs from DB, falling back to local: {e}")

    agent_settings: dict[str, dict[str, Any]] = {
        # bangla: গুগল অফিসিয়াল ফ্রি এআই এজেন্ট, ১০০০ রিকোয়েস্ট/দিন ফ্রি, MCP সাপোর্ট করে
        "gemini-cli": {
            "description": "Google Gemini CLI - Official free terminal AI agent",
            "command": "uvx",
            "args": ["gemini-cli-mcp"],
            "env": {
                "GEMINI_API_KEY": getattr(settings, "gemini_api_key", ""),
                "GOOGLE_API_KEY": getattr(settings, "google_api_key", ""),
            },
            "startup_timeout": 15,
            "allowed_tools": [
                "read_file",
                "write_file",
                "run_command",
                "search_web",
            ],
            "mcp_servers": ["filesystem"],
        },
        # bangla: ওপেন-সোর্স Devin বিকল্প, MIT লাইসেন্স, Docker স্যান্ডবক্স ব্যবহার করে
        "openhands": {
            "description": "OpenHands (Open-Source Devin Alternative)",
            "command": "uvx",
            "args": ["openhands-mcp-server"],
            "env": {
                "OPENHANDS_API_KEY": getattr(settings, "openhands_api_key", ""),
            },
            "startup_timeout": 20,
            "allowed_tools": [
                "browse_web",
                "execute_command",
                "read_file",
                "write_file",
                "search_code",
            ],
            "mcp_servers": ["filesystem", "github"],
            "python_sdk": True,
        },
        # bangla: অটোনোমাস কোডিং এজেন্ট, ৬১K+ গিটহাব স্টার, CLI/হেডলেস মোড
        "cline-cli": {
            "description": "Cline CLI in headless mode - Autonomous coding agent",
            "command": "npx",
            "args": ["@cline/cli", "--headless"],
            "env": {
                "ANTHROPIC_API_KEY": getattr(settings, "anthropic_api_key", ""),
                "CLINE_API_KEY": getattr(settings, "cline_api_key", ""),
            },
            "startup_timeout": 15,
            "allowed_tools": [
                "edit_file",
                "run_terminal_command",
                "search_replace",
                "read_file",
            ],
            "mcp_servers": ["filesystem", "github", "slack"],
            "supported_providers": [
                "DeepSeek",
                "Groq",
                "Ollama",
                "Anthropic",
                "OpenAI",
            ],
        },
        # bangla: কাস্টমাইজেবল ওয়ার্কফ্লো প্ল্যাটফর্ম, IDE + CLI + ক্লাউড এজেন্ট কভার করে
        "continue-dev": {
            "description": "Continue.dev - Customizable AI coding workflow platform",
            "command": "uvx",
            "args": ["continue-mcp-server"],
            "env": {
                "CONTINUE_API_KEY": getattr(settings, "continue_api_key", ""),
            },
            "startup_timeout": 15,
            "allowed_tools": [
                "chat",
                "edit",
                "generate_code",
                "refactor",
            ],
            "mcp_servers": ["filesystem", "github"],
            "self_hosted_models": True,
        },
        # bangla: টার্মিনাল পেয়ার প্রোগ্রামার, লোকাল গিট এবং ওপেন-রাউটার/ডিপসিক সাপোর্ট
        "aider": {
            "description": "Aider - Terminal-based AI pair programming tool",
            "command": "uvx",
            "args": ["aider-mcp"],
            "env": {
                "AIDER_API_KEY": getattr(settings, "aider_api_key", ""),
                "OPENROUTER_API_KEY": getattr(settings, "openrouter_api_key", ""),
            },
            "startup_timeout": 10,
            "allowed_tools": [
                "git_commit",
                "edit_file",
                "lint_code",
                "run_tests",
            ],
            "mcp_servers": ["filesystem", "github"],
            "cli_fallback": "aider",
        },
        # bangla: প্রিন্সটন ইউনিভার্সিটির তৈরি, গিটহাব ইস্যু সলভ করার জন্য সেরা টার্মিনাল এজেন্ট
        "swe-agent": {
            "description": "SWE-agent (Princeton) - GitHub issue solver terminal agent",
            "command": "uvx",
            "args": ["swe-agent-mcp"],
            "env": {
                "GITHUB_TOKEN": getattr(settings, "github_token", ""),
                "OPENAI_API_KEY": getattr(settings, "openai_api_key", ""),
            },
            "startup_timeout": 20,
            "allowed_tools": [
                "resolve_github_issue",
                "create_pr",
                "run_tests",
                "browse_repo",
            ],
            "mcp_servers": ["github", "filesystem"],
        },
        # bangla: জটিল বড় প্রজেক্ট হ্যান্ডল করার জন্য তৈরি,_version control for AI_ ফিচার
        "plandex": {
            "description": "Plandex - Terminal-based AI coding engine for complex projects",
            "command": "uvx",
            "args": ["plandex-mcp-server"],
            "env": {
                "PLANDEX_API_KEY": getattr(settings, "plandex_api_key", ""),
            },
            "startup_timeout": 15,
            "allowed_tools": [
                "execute_plan",
                "rollback_change",
                "apply_patch",
                "run_command",
            ],
            "mcp_servers": ["filesystem", "github"],
            "local_model_support": True,
        },
        # bangla: ওপেন-সোর্স Devin বিকল্প, নিজস্ব ব্রাউজার এজেন্ট এবং প্ল্যানিং মেকানিজম
        "devika": {
            "description": "Devika - Open-source Devin alternative with browser agent",
            "command": "uvx",
            "args": ["devika-mcp-server"],
            "env": {
                "GEMINI_API_KEY": getattr(settings, "gemini_api_key", ""),
                "GROQ_API_KEY": getattr(settings, "groq_api_key", ""),
            },
            "startup_timeout": 20,
            "allowed_tools": [
                "web_search",
                "browser_automation",
                "code_execution",
                "plan_feature",
            ],
            "mcp_servers": ["filesystem", "github"],
            "local_models": ["Ollama", "Groq"],
        },
        # bangla: ৯৫% কোড নিজে লিখে অ্যাপ্লিকেশন দাঁড় করিয়ে দেয়, স্টেপ-বাই-স্টেপ ডেভেলপার মতো কাজ করে
        "gpt-pilot": {
            "description": "GPT Pilot / Pythagora - Step-by-step autonomous app builder",
            "command": "uvx",
            "args": ["gpt-pilot-mcp-server"],
            "env": {
                "OPENAI_API_KEY": getattr(settings, "openai_api_key", ""),
                "Pythagora_API_KEY": getattr(settings, "pythagora_api_key", ""),
            },
            "startup_timeout": 25,
            "allowed_tools": [
                "generate_full_app",
                "ask_clarification",
                "run_integration_tests",
                "write_tests",
            ],
            "mcp_servers": ["filesystem", "github"],
            "clarifying_questions": True,
        },
        # bangla: সম্পূর্ণ ফ্রি এবং আনলিমিটেড এআই কোডিং, সেলফ-হোস্টেড ইনফ্রাস্ট্রাকচার
        "codeium": {
            "description": "Codeium - Zero-cost unlimited AI coding engine",
            "command": "uvx",
            "args": ["codeium-lang-server"],
            "env": {
                "CODEIUM_API_KEY": getattr(settings, "codeium_api_key", ""),
            },
            "startup_timeout": 15,
            "allowed_tools": [
                "autocomplete",
                "chat",
                "refactor",
                "search_code",
            ],
            "mcp_servers": ["filesystem"],
            "ide_extension": True,
            "headless_mode": True,
        },
    }
    return agent_settings


def get_headless_agent_registry() -> dict[str, Any]:
    """
    বাংলা মন্তব্য: MCP রেজিস্ট্রির জন্য সব হেডলেস এজেন্টের কনফিগারেশন রিটার্ন করে।
    এই ফাংশনটি parallel_agent_executor.py-এর সাথে ইন্টিগ্রেট করতে ব্যবহৃত হবে।
    """
    configs = get_headless_agent_configs()
    registry = {}
    for name, cfg in configs.items():
        registry[name] = {
            "command": cfg.get("command", "uvx"),
            "args": cfg.get("args", []),
            "env": cfg.get("env", {}),
            "startup_timeout": cfg.get("startup_timeout", 10),
            "allowed_tools": cfg.get("allowed_tools", []),
        }
    return registry


def get_agent_mcp_servers(agent_name: str) -> list[str]:
    """বাংলা মন্তব্য: নির্দিষ্ট এজেন্টের জন্য প্রয়োজনীয় MCP সার্ভারLisTS রিটার্ন করে।"""
    configs = get_headless_agent_configs()
    agent = configs.get(agent_name)
    if not agent:
        return []
    return agent.get("mcp_servers", [])
