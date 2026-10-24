#!/usr/bin/env python3
"""
config_single_source_enforcer.py — SupremeAI Config Single-Source Enforcer

বাংলা: এই স্ক্রিপ্ট backend/core/config_fields.py এবং config_secrets.py থেকে
whitelist তৈরি করে এবং পুরো backend-এ hardcoded config values খুঁজে বের করে।
SupremeAI-এর মূল নীতি: "self-healing, no hardcode, DB-driven" —
সব কনফিগারেশন env var বা Pydantic Settings থেকে আসতে হবে।

Exit codes:
  0 = পরিষ্কার, কোনো hardcoded config পাওয়া যায়নি
  1 = hardcoded config পাওয়া গেছে
  2 = ত্রুটি ঘটেছে (ফাইল পড়তে সমস্যা, ইত্যাদি)

Usage:
  python scripts/config_single_source_enforcer.py
  python scripts/config_single_source_enforcer.py --ci
  python scripts/config_single_source_enforcer.py --json
  python scripts/config_single_source_enforcer.py --whitelist-file extra_whitelist.txt
  python scripts/config_single_source_enforcer.py --exclude-dir backend/agents
"""

# বাংলা: শুধুমাত্র Python stdlib ব্যবহার — কোনো third-party dependency নেই
import argparse
import ast
import json
import os
import re
import sys
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any


# ── ত্রুটি কোড ধ্রুবক ───────────────────────────────────────────────────────
EXIT_CLEAN = 0
EXIT_HARDCODES_FOUND = 1
EXIT_ERROR = 2

# রিপো রুট — এই স্ক্রিপ্ট scripts/ ফোল্ডারে আছে বলে ধরে নেওয়া হচ্ছে
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"

# কনফিগ ফাইলের পাথ — এগুলো হলো Single Source of Truth
CONFIG_FIELDS_PATH = BACKEND_DIR / "core" / "config_fields.py"
CONFIG_SECRETS_PATH = BACKEND_DIR / "core" / "config_secrets.py"
CONFIG_MAIN_PATH = BACKEND_DIR / "core" / "config.py"

# ── ডিটেকশন প্যাটার্ন ───────────────────────────────────────────────────────

# ম্যাজিক নম্বর প্যাটার্ন: keyword=value বা keyword: value ফর্ম্যাটে
MAGIC_NUMBER_PATTERNS: list[dict[str, Any]] = [
    # বাংলা: timeout, retry, limit, ttl — এগুলো প্রায়ই hardcoded হয়
    {"kw": "timeout", "values": {5, 10, 15, 20, 25, 30, 45, 60, 90, 120, 180, 300, 600}, "severity": "red"},
    {"kw": "connect_timeout", "values": {5, 10, 15, 30}, "severity": "red"},
    {"kw": "read_timeout", "values": {10, 15, 20, 30, 45, 60, 120}, "severity": "red"},
    {"kw": "write_timeout", "values": {5, 10, 15, 30}, "severity": "red"},
    {"kw": "pool_timeout", "values": {5, 10, 15, 30}, "severity": "red"},
    {"kw": "max_retries", "values": {1, 2, 3, 5, 10}, "severity": "red"},
    {"kw": "retry", "values": {1, 2, 3, 5}, "severity": "yellow"},
    {"kw": "max_tokens", "values": {50, 100, 200, 256, 300, 500, 800, 1000, 1500, 2000, 2048, 3000, 4096, 4097, 5000, 8192, 16384}, "severity": "red"},
    {"kw": "max_prompt_tokens", "values": {500, 1000, 2000, 4000, 8192, 32768}, "severity": "red"},
    {"kw": "max_response_tokens", "values": {256, 500, 1000, 1500, 2048, 4096}, "severity": "red"},
    {"kw": "limit", "values": {10, 25, 50, 100, 200, 500, 1000}, "severity": "yellow"},
    {"kw": "ttl", "values": {60, 300, 600, 900, 1800, 3600, 7200, 86400}, "severity": "red"},
    {"kw": "cache_ttl", "values": {60, 300, 600, 900, 1800, 3600, 7200, 86400}, "severity": "red"},
    {"kw": "batch_size", "values": {10, 20, 32, 50, 64, 100, 128, 256, 512, 1000}, "severity": "yellow"},
    {"kw": "page_size", "values": {10, 20, 25, 50, 100}, "severity": "yellow"},
    {"kw": "max_connections", "values": {10, 20, 50, 100, 200}, "severity": "red"},
    {"kw": "max_keepalive", "values": {5, 10, 20, 50}, "severity": "yellow"},
    {"kw": "port", "values": {3000, 5173, 5432, 6379, 7474, 7687, 8000, 8080, 8443, 8888, 9090, 9200, 27017}, "severity": "red"},
    {"kw": "rpm", "values": {10, 15, 19, 20, 28, 30, 38, 50, 60, 100, 500, 1000}, "severity": "red"},
    {"kw": "tpm", "values": {10000, 28500, 38000, 40000, 50000, 100000, 240000}, "severity": "red"},
    {"kw": "rpd", "values": {45, 475, 950, 1000, 5000, 9000, 10000, 13680}, "severity": "red"},
    {"kw": "temperature", "values": {0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 0.8, 1.0, 1.5, 2.0}, "severity": "yellow"},
    {"kw": "top_p", "values": {0.5, 0.8, 0.9, 0.95, 1.0}, "severity": "yellow"},
    {"kw": "frequency_penalty", "values": {0.0, 0.1, 0.5, 1.0}, "severity": "yellow"},
    {"kw": "presence_penalty", "values": {0.0, 0.1, 0.5, 1.0}, "severity": "yellow"},
    {"kw": "cooldown", "values": {5, 10, 30, 60, 120, 300, 3600}, "severity": "red"},
    {"kw": "interval", "values": {5, 10, 15, 30, 60, 120, 300, 600}, "severity": "yellow"},
    {"kw": "iterations", "values": {3, 5, 10, 20, 50, 100}, "severity": "red"},
    {"kw": "threshold", "values": {0.1, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95}, "severity": "yellow"},
    {"kw": "window_size", "values": {5, 10, 20, 50, 100}, "severity": "yellow"},
    {"kw": "max_cost", "values": {0.01, 0.05, 0.1, 0.5, 1.0}, "severity": "red"},
    {"kw": "cost_per_token", "values": {0.00001, 0.00002, 0.0001}, "severity": "red"},
    {"kw": "chunk_size", "values": {256, 512, 1000, 2000, 4096, 8192}, "severity": "yellow"},
    {"kw": "overlap", "values": {50, 100, 128, 200, 256}, "severity": "yellow"},
    {"kw": "max_file_size", "values": {1024, 5120, 10240, 1048576, 5242880, 10485760}, "severity": "yellow"},
    {"kw": "max_depth", "values": {1, 2, 3, 5, 10}, "severity": "yellow"},
    {"kw": "workers", "values": {1, 2, 4, 8, 16, 32}, "severity": "yellow"},
    {"kw": "concurrency", "values": {5, 10, 20, 50, 100}, "severity": "yellow"},
]

# ম্যাজিক স্ট্রিং প্যাটার্ন — regex
MAGIC_STRING_PATTERNS: list[dict[str, Any]] = [
    # বাংলা: localhost এবং loopback address
    {"pattern": r'"(localhost)"', "severity": "red", "category": "host"},
    {"pattern": r"'(localhost)'", "severity": "red", "category": "host"},
    {"pattern": r'"(127\.0\.0\.1)"', "severity": "red", "category": "host"},
    {"pattern": r"'(127\.0\.0\.1)'", "severity": "red", "category": "host"},
    {"pattern": r'"(0\.0\.0\.0)"', "severity": "red", "category": "host"},
    {"pattern": r"'(0\.0\.0\.0)'", "severity": "red", "category": "host"},
    # বাংলা: ডাটাবেস ও ক্যাশে URL
    {"pattern": r'"(redis://[^"]+)"', "severity": "red", "category": "db_url"},
    {"pattern": r"'(redis://[^']+)'", "severity": "red", "category": "db_url"},
    {"pattern": r'"(rediss://[^"]+)"', "severity": "red", "category": "db_url"},
    {"pattern": r"'(rediss://[^']+)'", "severity": "red", "category": "db_url"},
    {"pattern": r'"(postgresql://[^"]+)"', "severity": "red", "category": "db_url"},
    {"pattern": r"'(postgresql://[^']+)'", "severity": "red", "category": "db_url"},
    {"pattern": r'"(postgres://[^"]+)"', "severity": "red", "category": "db_url"},
    {"pattern": r"'(postgres://[^']+)'", "severity": "red", "category": "db_url"},
    {"pattern": r'"(bolt://[^"]+)"', "severity": "red", "category": "db_url"},
    {"pattern": r"'(bolt://[^']+)'", "severity": "red", "category": "db_url"},
    {"pattern": r'"(sqlite:///[^"]+)"', "severity": "red", "category": "db_url"},
    {"pattern": r"'(sqlite:///[^']+)'", "severity": "red", "category": "db_url"},
    # বাংলা: API URLs
    {"pattern": r'"(https?://api\.openai\.com[^"]*?)"', "severity": "red", "category": "api_url"},
    {"pattern": r"'(https?://api\.openai\.com[^']*?)'", "severity": "red", "category": "api_url"},
    {"pattern": r'"(https?://generativelanguage\.googleapis\.com[^"]*?)"', "severity": "red", "category": "api_url"},
    {"pattern": r"'(https?://generativelanguage\.googleapis\.com[^']*?)'", "severity": "red", "category": "api_url"},
    {"pattern": r'"(https?://api\.groq\.com[^"]*?)"', "severity": "red", "category": "api_url"},
    {"pattern": r"'(https?://api\.groq\.com[^']*?)'", "severity": "red", "category": "api_url"},
    {"pattern": r'"(https?://openrouter\.ai[^"]*?)"', "severity": "red", "category": "api_url"},
    {"pattern": r"'(https?://openrouter\.ai[^']*?)'", "severity": "red", "category": "api_url"},
    {"pattern": r'"(https?://api\.anthropic\.com[^"]*?)"', "severity": "red", "category": "api_url"},
    {"pattern": r"'(https?://api\.anthropic\.com[^']*?)'", "severity": "red", "category": "api_url"},
    {"pattern": r'"(https?://api\.nvidia\.com[^"]*?)"', "severity": "red", "category": "api_url"},
    {"pattern": r"'(https?://api\.nvidia\.com[^']*?)'", "severity": "red", "category": "api_url"},
    {"pattern": r'"(https?://huggingface\.co[^"]*?)"', "severity": "red", "category": "api_url"},
    {"pattern": r"'(https?://huggingface\.co[^']*?)'", "severity": "red", "category": "api_url"},
    {"pattern": r'"(https?://api\.deepseek\.com[^"]*?)"', "severity": "red", "category": "api_url"},
    {"pattern": r"'(https?://api\.deepseek\.com[^']*?)'", "severity": "red", "category": "api_url"},
    # বাংলা: LLM মডেলের নাম (স্ট্রিং হিসেবে)
    {"pattern": r'"(gpt-[34][^"]*?)"', "severity": "red", "category": "model_name"},
    {"pattern": r"'(gpt-[34][^']*?)'", "severity": "red", "category": "model_name"},
    {"pattern": r'"(claude-[^"]+)"', "severity": "red", "category": "model_name"},
    {"pattern": r"'(claude-[^']+)'", "severity": "red", "category": "model_name"},
    {"pattern": r'"(gemini-[^"]+)"', "severity": "red", "category": "model_name"},
    {"pattern": r"'(gemini-[^']+)'", "severity": "red", "category": "model_name"},
    {"pattern": r'"(llama-[^"]+)"', "severity": "red", "category": "model_name"},
    {"pattern": r"'(llama-[^']+)'", "severity": "red", "category": "model_name"},
    {"pattern": r'"(mixtral-[^"]+)"', "severity": "red", "category": "model_name"},
    {"pattern": r"'(mixtral-[^']+)'", "severity": "red", "category": "model_name"},
    {"pattern": r'"(deepseek-[^"]+)"', "severity": "red", "category": "model_name"},
    {"pattern": r"'(deepseek-[^']+)'", "severity": "red", "category": "model_name"},
    {"pattern": r'"(anthropic/[^"]+)"', "severity": "red", "category": "model_name"},
    {"pattern": r"'(anthropic/[^']+)'", "severity": "red", "category": "model_name"},
    {"pattern": r'"(google/[^"]+)"', "severity": "yellow", "category": "model_name"},
    {"pattern": r"'(google/[^']+)'", "severity": "yellow", "category": "model_name"},
    {"pattern": r'"(meta-llama/[^"]+)"', "severity": "red", "category": "model_name"},
    {"pattern": r"'(meta-llama/[^']+)'", "severity": "red", "category": "model_name"},
    {"pattern": r'"(mistralai/[^"]+)"', "severity": "red", "category": "model_name"},
    {"pattern": r"'(mistralai/[^']+)'", "severity": "red", "category": "model_name"},
    # বাংলা: ফাইল সিস্টেম পাথ
    {"pattern": r'"(/tmp/[^"]+)"', "severity": "red", "category": "file_path"},
    {"pattern": r"'(/tmp/[^']+)'", "severity": "red", "category": "file_path"},
    {"pattern": r'"(/var/[^"]+)"', "severity": "red", "category": "file_path"},
    {"pattern": r"'(/var/[^']+)'", "severity": "red", "category": "file_path"},
    {"pattern": r'"(/etc/[^"]+)"', "severity": "yellow", "category": "file_path"},
    {"pattern": r"'(/etc/[^']+)'", "severity": "yellow", "category": "file_path"},
    {"pattern": r'"(/usr/[^"]+)"', "severity": "yellow", "category": "file_path"},
    {"pattern": r"'(/usr/[^']+)'", "severity": "yellow", "category": "file_path"},
]

# বাংলা: এই কনটেক্সটগুলোতে hardcoded value গ্রহণযোগ্য — false positive এড়াতে
ACCEPTABLE_CONTEXTS = {
    "logger.",
    "logger.debug", "logger.info", "logger.warning", "logger.error", "logger.critical",
    "print(",
    "raise ",
    "assert ",
    "# ",
    "\"\"\"",
    "'''",
    "f\"", "f'",
    "TypeError", "ValueError", "KeyError", "RuntimeError",
    "HTTPException",
    ".format(",
    "__doc__",
    "__name__",
    "__all__",
    "help(",
    "TypeError(", "ValueError(", "KeyError(",
}

# বাংলা: এই ফাইলগুলো স্ক্যান করা হবে না (config source ফাইল)
CONFIG_SOURCE_FILES = {
    "config_fields.py",
    "config_secrets.py",
    "config_validation.py",
    "config.py",
    "secret_vault.py",
    "platform_detect.py",
}

# বাংলা: এই ডিরেক্টরিগুলো স্ক্যান থেকে বাদ দেওয়া হবে
DEFAULT_EXCLUDE_DIRS = {
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "migrations",
    "alembic",
    ".env",
    "scripts",
}


# ── ডাটা ক্লাস ──────────────────────────────────────────────────────────────

@dataclass
class ConfigField:
    """বাংলা: config_fields.py / config_secrets.py থেকে প্রাপ্ত Field তথ্য।"""
    name: str  # ফিল্ড নাম (যেমন: LLM_READ_TIMEOUT)
    alias: str  # validation_alias (যেমন: LLM_READ_TIMEOUT)
    default: Any  # ডিফল্ট ভ্যালু
    field_type: str  # int, float, str, bool, ইত্যাদি
    source_file: str  # বাংলা: কোন ফাইল থেকে এসেছে


@dataclass
class Finding:
    """বাংলা: একটি hardcoded config finding প্রতিনিধিত্ব করে।"""
    file: str
    line: int
    raw_line: str
    matched_value: str
    pattern_type: str  # magic_number, magic_string
    category: str  # timeout, host, db_url, api_url, model_name, file_path, ইত্যাদি
    severity: str  # red, yellow, green
    suggested_field: str  # প্রস্তাবিত config field নাম
    context: str  # পার্শ্ববর্তী কোড


# ── AST পার্সার: config whitelist তৈরি ────────────────────────────────────

def extract_config_whitelist(
    fields_path: Path, secrets_path: Path, main_path: Path
) -> dict[str, ConfigField]:
    """বাংলা: config_fields.py, config_secrets.py এবং config.py থেকে সব Field ডেফিনিশন
    এবং তাদের validation_alias, default values বের করে whitelist তৈরি করে।

    এই whitelist-এ থাকা ভ্যালুগুলো হলো "legitimate config" — অর্থাৎ এগুলো কেন্দ্রীয়ভাবে
    নিয়ন্ত্রিত এবং অন্য ফাইলে একই ভ্যালু থাকলে তা "acceptable reuse" বলে বিবেচিত হতে পারে।
    """
    whitelist: dict[str, ConfigField] = {}

    for path in [fields_path, secrets_path, main_path]:
        if not path.exists():
            print(f"⚠️  সতর্কতা: {path} পাওয়া যায়নি, স্কিপ করা হচ্ছে", file=sys.stderr)
            continue
        try:
            _parse_config_file(path, whitelist)
        except SyntaxError as e:
            print(f"❌ ত্রুটি: {path} পার্স করতে সমস্যা: {e}", file=sys.stderr)

    # বাংলা: MODEL_SWARM ডিকশনারি থেকেও model names whitelist করা হবে
    _extract_model_swarm(secrets_path, whitelist)

    return whitelist


def _parse_config_file(path: Path, whitelist: dict[str, ConfigField]) -> None:
    """বাংলা: একটি config ফাইল থেকে AST ব্যবহার করে Field ডেফিনিশন বের করে।"""
    source = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source, filename=str(path))

    for node in ast.walk(tree):
        # বাংলা: Class-level assignment — Field(default=..., validation_alias=...)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            field_name = node.target.id
            alias = ""
            default = None
            field_type = "unknown"

            # বাংলা: type annotation থেকে টাইপ বের করা
            if node.annotation:
                field_type = _ast_type_to_str(node.annotation)

            # বাংলা: value থেকে Field() কলের default ও alias বের করা
            if node.value:
                if isinstance(node.value, ast.Call):
                    # Field(default=..., validation_alias="...")
                    func_name = _get_call_name(node.value)
                    if func_name in ("Field", "SecretStr"):
                        default, alias = _extract_field_args(node.value)
                    elif func_name == "NoDecode":
                        # Annotated[dict, NoDecode] এর জন্য inner type
                        pass
                elif isinstance(node.value, ast.Constant):
                    # সরাসরি assignment: PORT: int = 8080
                    default = node.value.value
                    alias = field_name
                elif isinstance(node.value, ast.List):
                    default = _ast_literal_value(node.value)
                    alias = field_name
                elif isinstance(node.value, ast.Dict):
                    default = _ast_literal_value(node.value)
                    alias = field_name
                elif isinstance(node.value, ast.Lambda):
                    # default_factory=lambda: {...}
                    default = "<factory>"
                    alias = field_name

            # বাংলা: alias না থাকলে field_name ব্যবহার
            if not alias:
                alias = field_name

            # বাংলা: private attrs এবং internal fields স্কিপ
            if field_name.startswith("_"):
                continue

            whitelist[field_name] = ConfigField(
                name=field_name,
                alias=alias,
                default=default,
                field_type=field_type,
                source_file=path.name,
            )


def _ast_type_to_str(annotation: ast.expr) -> str:
    """বাংলা: AST type annotation থেকে মানুষের পাঠযোগ্য টাইপ স্ট্রিং তৈরি করে।"""
    if isinstance(annotation, ast.Name):
        return annotation.id
    elif isinstance(annotation, ast.Subscript):
        outer = _ast_type_to_str(annotation.value) if hasattr(annotation, 'value') else ""
        # বাংলা: slicing handling
        if isinstance(annotation.slice, ast.Tuple):
            inner = ", ".join(_ast_type_to_str(s) for s in annotation.slice.elts)
        else:
            inner = _ast_type_to_str(annotation.slice) if hasattr(annotation, 'slice') else ""
        return f"{outer}[{inner}]"
    elif isinstance(annotation, ast.Constant):
        return str(annotation.value)
    elif isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return f"{_ast_type_to_str(annotation.left)} | {_ast_type_to_str(annotation.right)}"
    return "any"


def _get_call_name(call: ast.Call) -> str:
    """বাংলা: ast.Call থেকে function name বের করে (getattr chain সাপোর্ট সহ)।"""
    if isinstance(call.func, ast.Name):
        return call.func.id
    elif isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _extract_field_args(call: ast.Call) -> tuple[Any, str]:
    """বাংলা: Field(default=..., validation_alias="...") থেকে default ও alias বের করে।"""
    default = None
    alias = ""

    # বাংলা: positional argument (প্রথমটি সাধারণত default)
    if call.args:
        default = _ast_literal_value(call.args[0])

    # বাংলা: keyword arguments
    for kw in call.keywords:
        if kw.arg == "default":
            default = _ast_literal_value(kw.value)
        elif kw.arg == "default_factory":
            default = "<factory>"
        elif kw.arg == "validation_alias":
            alias_val = _ast_literal_value(kw.value)
            if isinstance(alias_val, str):
                alias = alias_val

    return default, alias


def _ast_literal_value(node: ast.expr) -> Any:
    """বাংলা: AST node থেকে Python literal value বের করে।"""
    if isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.List):
        return [_ast_literal_value(e) for e in node.elts]
    elif isinstance(node, ast.Tuple):
        return tuple(_ast_literal_value(e) for e in node.elts)
    elif isinstance(node, ast.Dict):
        return {
            _ast_literal_value(k): _ast_literal_value(v)
            for k, v in zip(node.keys, node.values)
            if k is not None
        }
    elif isinstance(node, ast.Call):
        func_name = _get_call_name(node)
        if func_name == "SecretStr":
            if node.args:
                return _ast_literal_value(node.args[0])
            return "<secret>"
        return f"<{func_name}()>"
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_ast_literal_value(node.operand) if isinstance(node.operand, ast.Constant) else None
    return None


def _extract_model_swarm(secrets_path: Path, whitelist: dict[str, ConfigField]) -> None:
    """বাংলা: config_secrets.py থেকে MODEL_SWARM dict-এর model names বের করে whitelist-এ যোগ করে।"""
    if not secrets_path.exists():
        return
    source = secrets_path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source, filename=str(secrets_path))

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "MODEL_SWARM":
                    if isinstance(node.value, ast.Dict):
                        for val_node in node.value.values:
                            model_name = _ast_literal_value(val_node)
                            if isinstance(model_name, str):
                                # বাংলা: HuggingFace model path — whitelist-এ যোগ
                                whitelist[f"model:{model_name}"] = ConfigField(
                                    name=f"model:{model_name}",
                                    alias=model_name,
                                    default=model_name,
                                    field_type="str",
                                    source_file=secrets_path.name,
                                )


# ── Whitelist normalization helpers ─────────────────────────────────────────

def build_default_values_set(whitelist: dict[str, ConfigField]) -> set:
    """বাংলা: whitelist থেকে সব default values এর একটি set তৈরি করে।
    এই set-এ থাকা ভ্যালু অন্য ফাইলে পাওয়া গেলে তা 'acceptable' হিসেবে চিহ্নিত হবে।"""
    defaults = set()
    for cf in whitelist.values():
        if cf.default is not None and cf.default != "<factory>" and cf.default != "<secret>":
            if isinstance(cf.default, (int, float, str, bool)):
                defaults.add(cf.default)
            elif isinstance(cf.default, (list, tuple)):
                for item in cf.default:
                    if isinstance(item, (int, float, str, bool)):
                        defaults.add(item)
    return defaults


def build_suggested_field_map(whitelist: dict[str, ConfigField]) -> dict[str, str]:
    """বাংলা: keyword name থেকে suggested config field name-এ ম্যাপিং তৈরি করে।
    যেমন: 'timeout' → 'LLM_READ_TIMEOUT', 'max_tokens' → 'MAX_RESPONSE_TOKENS'"""
    mapping: dict[str, list[tuple[str, ConfigField]]] = {}
    for cf in whitelist.values():
        name_lower = cf.name.lower()
        alias_lower = cf.alias.lower()
        for key in [name_lower, alias_lower]:
            mapping.setdefault(key, []).append((key, cf))

    result: dict[str, str] = {}

    # বাংলা: সরাসরি ম্যাচিং
    for keyword in [p["kw"] for p in MAGIC_NUMBER_PATTERNS]:
        kw_lower = keyword.lower()
        # প্রথমে সরাসরি match খোঁজা
        if kw_lower in mapping:
            result[keyword] = mapping[kw_lower][0][1].alias
            continue

        # বাংলা: partial match — যেমন 'timeout' খুঁজলে 'LLM_READ_TIMEOUT' পাওয়া যাবে
        best_match = ""
        for key, entries in mapping.items():
            if keyword in key or key in keyword:
                if len(entries[0][1].alias) > len(best_match):
                    best_match = entries[0][1].alias
        if best_match:
            result[keyword] = best_match

    return result


# ── ফাইল স্ক্যানার ──────────────────────────────────────────────────────────

def is_test_file(file_path: Path) -> bool:
    """বাংলা: ফাইলটি কি টেস্ট ফাইল কিনা চেক করে।"""
    parts = file_path.parts
    if "tests" in parts:
        return True
    name = file_path.name
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    return False


def is_config_source(file_path: Path) -> bool:
    """বাংলা: ফাইলটি কি config source file কিনা চেক করে।"""
    return file_path.name in CONFIG_SOURCE_FILES


def is_in_exclude_dir(file_path: Path, exclude_dirs: set[str]) -> bool:
    """বাংলা: ফাইলটি কোনো excluded directory-তে আছে কিনা চেক করে।
    Path part match এবং prefix match উভয় সাপোর্ট করে।"""
    # বাংলা: relative path ব্যবহার করা হয় যাতে --exclude-dir backend/agents কাজ করে
    try:
        rel_path = str(file_path.relative_to(REPO_ROOT))
    except ValueError:
        rel_path = str(file_path)
    for exc in exclude_dirs:
        # বাংলা: exact path part match
        if exc in file_path.parts:
            return True
        # বাংলা: prefix match (যেমন 'backend/agents' → 'backend/agents/devops/...')
        if rel_path.startswith(exc + "/") or rel_path == exc:
            return True
    return False


def collect_python_files(
    base_dir: Path, exclude_dirs: set[str], extra_exclude_dirs: list[str]
) -> list[Path]:
    """বাংলা: base_dir থেকে সব .py ফাইল সংগ্রহ করে (exclude ফিল্টার সহ)।"""
    # বাংলা: simple name excludes আলাদাভাবে রাখা হয় (os.walk dirs filtering-এর জন্য)
    simple_excludes = exclude_dirs.copy()
    all_excludes = exclude_dirs | set(extra_exclude_dirs)
    py_files: list[Path] = []

    for root, dirs, files in os.walk(base_dir):
        root_path = Path(root)

        # বাংলা: simple name excludes দিয়ে dirs ফিল্টার
        dirs[:] = [d for d in dirs if d not in simple_excludes and not d.startswith(".")]

        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = root_path / fname

            if is_test_file(fpath):
                continue
            if is_config_source(fpath):
                continue
            if is_in_exclude_dir(fpath, all_excludes):
                continue

            py_files.append(fpath)

    return sorted(py_files)


# ── হার্ডকোড ডিটেক্টর ────────────────────────────────────────────────────────

def _is_in_log_or_error_context(line: str, col_start: int) -> bool:
    """বাংলা: চেক করে ম্যাচিং পজিশনটি কি logger/error message-এর মধ্যে আছে কিনা।"""
    prefix = line[:col_start].rstrip()
    for ctx in ACCEPTABLE_CONTEXTS:
        if ctx in prefix:
            return True
    return False


def _is_in_string_literal(line: str, col_start: int) -> bool:
    """বাংলা: চেক করে ম্যাচিং পজিশনটি কি অন্য string literal-এর ভেতরে আছে কিনা
    (যেমন f-string, docstring, বা concatenation)।"""
    # বাংলা: f-string detection
    before = line[:col_start]
    if 'f"' in before or "f'" in before:
        # f-string-এর মধ্যে থাকলে skip — এটি লগ মেসেজ হতে পারে
        return True
    return False


def _is_comment_line(line: str) -> bool:
    """বাংলা: পুরো লাইনটি কি comment কিনা চেক করে।"""
    stripped = line.lstrip()
    return stripped.startswith("#")


def _is_docstring_line(line: str) -> bool:
    """বাংলা: লাইনটি docstring-এর অংশ কিনা আনুমানিকভাবে চেক করে।"""
    stripped = line.strip()
    return stripped.startswith('"""') or stripped.startswith("'''")


def _value_matches_default(value: Any, default_values: set) -> bool:
    """বাংলা: ভ্যালুটি কি config-এর default value-এর সাথে মেলে কিনা চেক করে।
    মিললে এটি 'acceptable reuse' — কারণ centralized config-এ একই ডিফল্ট আছে।"""
    # বাংলা: সংখ্যাগত তুলনা — int ও float মেলানো
    if isinstance(value, (int, float)) and value in default_values:
        return True
    if isinstance(value, str) and value in default_values:
        return True
    return False


def scan_magic_numbers(
    file_path: Path,
    lines: list[str],
    default_values: set,
    suggested_fields: dict[str, str],
) -> list[Finding]:
    """বাংলা: একটি ফাইলে magic number patterns (keyword=value) স্ক্যান করে।"""
    findings: list[Finding] = []

    for i, line in enumerate(lines, start=1):
        # বাংলা: comment এবং docstring lines স্কিপ
        if _is_comment_line(line) or _is_docstring_line(line):
            continue

        for pattern_info in MAGIC_NUMBER_PATTERNS:
            keyword = pattern_info["kw"]
            values = pattern_info["values"]
            severity = pattern_info["severity"]

            # বাংলা: keyword=value এবং keyword: value উভয় ফর্ম্যাট চেক
            for separator in ["=", ":"]:
                for quote in ["\"", "'"]:
                    # বাংলা: pattern — keyword<sep><number> বা keyword<sep><number>.<number>
                    regex = re.compile(
                        rf'\b{re.escape(keyword)}\s*{re.escape(separator)}\s*([0-9]+(?:\.[0-9]+)?)'
                    )
                    for m in regex.finditer(line):
                        matched_str = m.group(1)
                        try:
                            # বাংলা: int বা float হিসেবে parse
                            if '.' in matched_str:
                                value = float(matched_str)
                            else:
                                value = int(matched_str)
                        except (ValueError, OverflowError):
                            continue

                        if value not in values:
                            continue

                        col_start = m.start()

                        # বাংলা: log/error context স্কিপ
                        if _is_in_log_or_error_context(line, col_start):
                            continue

                        # বাংলা: f-string context স্কিপ
                        if _is_in_string_literal(line, col_start):
                            continue

                        # বাংলা: default value match — acceptable
                        if _value_matches_default(value, default_values):
                            final_severity = "green"
                        else:
                            final_severity = severity

                        # বাংলা: প্রস্তাবিত config field
                        suggested = suggested_fields.get(keyword, f"<সুপারিশকৃত_{keyword.upper()}>")

                        findings.append(Finding(
                            file=str(file_path.relative_to(REPO_ROOT)),
                            line=i,
                            raw_line=line.rstrip(),
                            matched_value=f"{keyword}{separator}{value}",
                            pattern_type="magic_number",
                            category=keyword,
                            severity=final_severity,
                            suggested_field=suggested,
                            context=line.strip(),
                        ))

    return findings


def scan_magic_strings(
    file_path: Path,
    lines: list[str],
    default_values: set,
    whitelist: dict[str, ConfigField],
) -> list[Finding]:
    """বাংলা: একটি ফাইলে magic string patterns (URLs, hosts, model names) স্ক্যান করে।"""
    findings: list[Finding] = []

    for i, line in enumerate(lines, start=1):
        if _is_comment_line(line) or _is_docstring_line(line):
            continue

        for pattern_info in MAGIC_STRING_PATTERNS:
            regex = re.compile(pattern_info["pattern"])
            severity = pattern_info["severity"]
            category = pattern_info["category"]

            for m in regex.finditer(line):
                matched_value = m.group(1)
                col_start = m.start()

                # বাংলা: log/error context স্কিপ
                if _is_in_log_or_error_context(line, col_start):
                    continue

                # বাংলা: f-string context স্কিপ
                if _is_in_string_literal(line, col_start):
                    continue

                # বাংলা: default value match — acceptable
                if _value_matches_default(matched_value, default_values):
                    final_severity = "green"
                else:
                    final_severity = severity

                # বাংলা: whitelist model names check
                if category == "model_name":
                    is_whitelisted = any(
                        matched_value in str(cf.default)
                        for cf in whitelist.values()
                    )
                    if is_whitelisted:
                        final_severity = "green"

                # বাংলা: প্রস্তাবিত config field
                suggested = _suggest_field_for_string(matched_value, category, whitelist)

                findings.append(Finding(
                    file=str(file_path.relative_to(REPO_ROOT)),
                    line=i,
                    raw_line=line.rstrip(),
                    matched_value=matched_value,
                    pattern_type="magic_string",
                    category=category,
                    severity=final_severity,
                    suggested_field=suggested,
                    context=line.strip(),
                ))

    return findings


def _suggest_field_for_string(
    value: str, category: str, whitelist: dict[str, ConfigField]
) -> str:
    """বাংলা: magic string-এর জন্য প্রস্তাবিত config field name বানায়।"""
    value_lower = value.lower()

    if category == "host":
        if "localhost" in value_lower or "127.0.0.1" in value_lower:  # is_local()
            return "HOST"
        if "0.0.0.0" in value_lower:
            return "HOST"
    elif category == "db_url":
        if "redis" in value_lower:
            return "REDIS_URL"
        if "postgres" in value_lower:
            return "SUPABASE_DATABASE_URL_POOLER"
        if "bolt" in value_lower:
            return "NEO4J_URI"
        if "sqlite" in value_lower:
            return "<DATABASE_URL>"
    elif category == "api_url":
        if "openai" in value_lower:
            return "OPENAI_BASE_URL"
        if "googleapis" in value_lower:
            return "GEMINI_BASE_URL"
        if "groq" in value_lower:
            return "GROQ_BASE_URL"
        if "openrouter" in value_lower:
            return "OPENROUTER_BASE_URL"
        if "anthropic" in value_lower:
            return "ANTHROPIC_BASE_URL"
        if "nvidia" in value_lower:
            return "NVIDIA_BASE_URL"
        if "huggingface" in value_lower:
            return "HF_BASE_URL"
        if "deepseek" in value_lower:
            return "DEEPSEEK_BASE_URL"
    elif category == "model_name":
        if "claude" in value_lower or "anthropic" in value_lower:
            return "CLAUDE_OPENROUTER_MODEL"
        if "gemini" in value_lower:
            return "GEMINI_MODEL_NAME"
        return "<LLM_MODEL_CONFIG>"
    elif category == "file_path":
        if "/tmp/" in value:
            return "WORKSPACE_BASE_DIR বা SANDBOX_ROOT"
        if "/var/" in value:
            return "<CONFIGURABLE_PATH>"
        if "/etc/" in value:
            return "<CONFIGURABLE_PATH>"
        if "/usr/" in value:
            return "<CONFIGURABLE_PATH>"

    return f"<সুপারিশকৃত_{category.upper()}>"


# ── রিপোর্ট জেনারেটর ──────────────────────────────────────────────────────────

def generate_markdown_report(findings: list[Finding], whitelist: dict[str, ConfigField]) -> str:
    """বাংলা: Markdown ফর্ম্যাটে রিপোর্ট তৈরি করে।
    Severity অনুসারে গ্রুপ করা হয়: 🔴 🟡 🟢"""
    red = [f for f in findings if f.severity == "red"]
    yellow = [f for f in findings if f.severity == "yellow"]
    green = [f for f in findings if f.severity == "green"]

    lines: list[str] = []
    lines.append("# 🔍 SupremeAI Hardcoded Config Audit (Auto-Generated)")
    lines.append("")
    lines.append(f"**তারিখ**: {_now_str()}  ")
    lines.append(f"**মোট ফাইন্ডিং**: {len(findings)}  ")
    lines.append(f"🔴 কনফিগ করা উচিত: {len(red)}  |  🟡 হয়তো কনফিগ করা উচিত: {len(yellow)}  |  🟢 গ্রহণযোগ্য (default match): {len(green)}")
    lines.append("")
    lines.append("> বাংলা: এই রিপোর্ট `config_single_source_enforcer.py` দ্বারা স্বয়ংক্রিয়ভাবে তৈরি হয়েছে।")
    lines.append("> Single Source of Truth: `backend/core/config_fields.py` + `config_secrets.py`")
    lines.append("")

    # বাংলা: 🔴 Red সেকশন
    if red:
        lines.append("---")
        lines.append("")
        lines.append("## 🔴 কনফিগ করা উচিত (Should Be Config)")
        lines.append("")
        lines.append("এই ভ্যালুগুলো `backend/core/config.py` থেকে আসা উচিত, hardcoded নয়:")
        lines.append("")
        lines.append("```diff")
        for f in red:
            lines.append(f"- {f.file}:{f.line}: {f.matched_value}")
            lines.append(f"  # প্রস্তাবিত config: settings.{f.suggested_field}")
            lines.append(f"  # প্রসঙ্গ: {f.context[:120]}")
            lines.append("")
        lines.append("```")
        lines.append("")

    # বাংলা: 🟡 Yellow সেকশন
    if yellow:
        lines.append("---")
        lines.append("")
        lines.append("## 🟡 হয়তো কনফিগ করা উচিত (Maybe Should Be Config)")
        lines.append("")
        lines.append("এই ভ্যালুগুলো পর্যালোচনা করুন — context-এর উপর নির্ভর করে config হওয়া উচিত কিনা:")
        lines.append("")
        lines.append("```diff")
        for f in yellow:
            lines.append(f"? {f.file}:{f.line}: {f.matched_value}")
            lines.append(f"  # প্রস্তাবিত config: settings.{f.suggested_field}")
            lines.append(f"  # প্রসঙ্গ: {f.context[:120]}")
            lines.append("")
        lines.append("```")
        lines.append("")

    # বাংলা: 🟢 Green সেকশন
    if green:
        lines.append("---")
        lines.append("")
        lines.append("## 🟢 গ্রহণযোগ্য (Acceptable — Matches Config Default)")
        lines.append("")
        lines.append("এই ভ্যালুগুলো config-এর default value-এর সাথে মেলে — centralized config-এ আছে:")
        lines.append("")
        lines.append("```diff")
        for f in green:
            lines.append(f"  {f.file}:{f.line}: {f.matched_value}  ✓ (default match)")
        lines.append("```")
        lines.append("")

    # বাংলা: whitelist সারাংশ
    lines.append("---")
    lines.append("")
    lines.append("## 📋 Whitelist Summary")
    lines.append("")
    lines.append(f"মোট whitelist এন্ট্রি: {len(whitelist)}")
    lines.append("")
    lines.append("| Field Name | Alias | Default | Type | Source |")
    lines.append("|---|---|---|---|---|")
    for cf in sorted(whitelist.values(), key=lambda x: x.name):
        default_str = str(cf.default) if cf.default is not None else "(required)"
        if len(default_str) > 50:
            default_str = default_str[:47] + "..."
        lines.append(f"| `{cf.name}` | `{cf.alias}` | {default_str} | {cf.field_type} | {cf.source_file} |")

    return "\n".join(lines)


def generate_json_report(findings: list[Finding], whitelist: dict[str, ConfigField]) -> str:
    """বাংলা: JSON ফর্ম্যাটে রিপোর্ট তৈরি করে — CI pipeline-এ ব্যবহারের জন্য।"""
    report = {
        "generated_at": _now_str(),
        "summary": {
            "total": len(findings),
            "red": sum(1 for f in findings if f.severity == "red"),
            "yellow": sum(1 for f in findings if f.severity == "yellow"),
            "green": sum(1 for f in findings if f.severity == "green"),
        },
        "findings": [
            {
                "file": f.file,
                "line": f.line,
                "matched_value": f.matched_value,
                "pattern_type": f.pattern_type,
                "category": f.category,
                "severity": f.severity,
                "suggested_field": f.suggested_field,
                "context": f.context,
            }
            for f in findings
        ],
        "whitelist": {
            name: {
                "alias": cf.alias,
                "default": cf.default,
                "type": cf.field_type,
                "source": cf.source_file,
            }
            for name, cf in whitelist.items()
        },
    }
    return json.dumps(report, indent=2, ensure_ascii=False, default=str)


def _now_str() -> str:
    """বাংলা: বর্তমান সময় ISO format-এ রিটার্ন করে।"""
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")


# ── অতিরিক্ত whitelist লোডার ────────────────────────────────────────────────

def load_extra_whitelist(whitelist_file: str) -> set[str]:
    """বাংলা: --whitelist-file থেকে অতিরিক্ত whitelist patterns লোড করে।
    ফর্ম্যাট: প্রতি লাইনে একটি pattern (regex supported)।"""
    extra: set[str] = set()
    path = Path(whitelist_file)
    if not path.exists():
        print(f"❌ ত্রুটি: whitelist ফাইল '{whitelist_file}' পাওয়া যায়নি", file=sys.stderr)
        return extra

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        extra.add(line)

    return extra


def is_extra_whitelisted(finding: Finding, extra_patterns: set[str]) -> bool:
    """বাংলা: একটি finding কি extra whitelist-এ আছে কিনা চেক করে।"""
    for pattern in extra_patterns:
        try:
            if re.search(pattern, finding.file) or re.search(pattern, finding.matched_value):
                return True
        except re.error:
            # বাংলা: invalid regex — literal string match
            if pattern in finding.file or pattern in finding.matched_value:
                return True
    return False


# ── মূল এক্সিকিউশন ফাংশন ──────────────────────────────────────────────────

def main() -> int:
    """বাংলা: মূল ফাংশন — স্ক্যান চালায়, রিপোর্ট তৈরি করে, উপযুক্ত exit code দেয়।"""
    # বাংলা: CLI argument parsing
    parser = argparse.ArgumentParser(
        description="SupremeAI Config Single-Source Enforcer — hardcoded config values খোঁজে",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0 = পরিষ্কার, কোনো hardcoded config পাওয়া যায়নি
  1 = hardcoded config পাওয়া গেছে
  2 = ত্রুটি ঘটেছে

Examples:
  python scripts/config_single_source_enforcer.py
  python scripts/config_single_source_enforcer.py --ci
  python scripts/config_single_source_enforcer.py --json > audit.json
  python scripts/config_single_source_enforcer.py --whitelist-file extra.txt
  python scripts/config_single_source_enforcer.py --exclude-dir backend/agents
        """,
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI মোড — 🔴 findings থাকলে exit code 1 দেবে",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON ফর্ম্যাটে আউটপুট (stdout)",
    )
    parser.add_argument(
        "--whitelist-file",
        type=str,
        default="",
        help="অতিরিক্ত whitelist patterns ফাইলের পাথ",
    )
    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        help="স্ক্যান থেকে বাদ দেওয়ার জন্য অতিরিক্ত directory (একাধিকবার ব্যবহার করা যাবে)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="রিপোর্ট ফাইলে সংরক্ষণ করুন (ডিফল্ট: stdout)",
    )

    args = parser.parse_args()

    try:
        # ── ধাপ ১: Whitelist তৈরি ────────────────────────────────────────
        # বাংলা: config_fields.py এবং config_secrets.py থেকে সব legitimate config values বের করা
        print("📋 ধাপ ১: Config whitelist তৈরি হচ্ছে...", file=sys.stderr)
        whitelist = extract_config_whitelist(CONFIG_FIELDS_PATH, CONFIG_SECRETS_PATH, CONFIG_MAIN_PATH)
        print(f"   ✅ {len(whitelist)}টি whitelist এন্ট্রি পাওয়া গেছে", file=sys.stderr)

        # ── ধাপ ২: Default values এবং suggested fields ───────────────────
        print("📋 ধাপ ২: Default values এবং field mapping তৈরি হচ্ছে...", file=sys.stderr)
        default_values = build_default_values_set(whitelist)
        suggested_fields = build_suggested_field_map(whitelist)
        print(f"   ✅ {len(default_values)}টি unique default value, {len(suggested_fields)}টি field mapping", file=sys.stderr)

        # ── ধাপ ৩: অতিরিক্ত whitelist লোড ─────────────────────────────
        extra_whitelist: set[str] = set()
        if args.whitelist_file:
            print(f"📋 ধাপ ২.৫: অতিরিক্ত whitelist লোড হচ্ছে ({args.whitelist_file})...", file=sys.stderr)
            extra_whitelist = load_extra_whitelist(args.whitelist_file)
            print(f"   ✅ {len(extra_whitelist)}টি অতিরিক্ত whitelist pattern", file=sys.stderr)

        # ── ধাপ ৪: ফাইল সংগ্রহ ────────────────────────────────────────
        print("📋 ধাপ ৩: Backend Python ফাইল সংগ্রহ করা হচ্ছে...", file=sys.stderr)
        py_files = collect_python_files(BACKEND_DIR, DEFAULT_EXCLUDE_DIRS, args.exclude_dir)
        print(f"   ✅ {len(py_files)}টি ফাইল স্ক্যানের জন্য প্রস্তুত", file=sys.stderr)

        # ── ধাপ ৫: স্ক্যান ─────────────────────────────────────────────
        print("📋 ধাপ ৪: Hardcoded values খোঁজা হচ্ছে...", file=sys.stderr)
        all_findings: list[Finding] = []

        for fpath in py_files:
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                file_lines = content.splitlines()

                # বাংলা: magic number scan
                num_findings = scan_magic_numbers(
                    fpath, file_lines, default_values, suggested_fields
                )
                all_findings.extend(num_findings)

                # বাংলা: magic string scan
                str_findings = scan_magic_strings(
                    fpath, file_lines, default_values, whitelist
                )
                all_findings.extend(str_findings)

            except OSError as e:
                print(f"   ⚠️  {fpath} পড়তে সমস্যা: {e}", file=sys.stderr)

        # বাংলা: extra whitelist ফিল্টার
        if extra_whitelist:
            before = len(all_findings)
            all_findings = [
                f for f in all_findings
                if not is_extra_whitelisted(f, extra_whitelist)
            ]
            filtered = before - len(all_findings)
            if filtered > 0:
                print(f"   ℹ️  {filtered}টি finding extra whitelist দ্বারা ফিল্টার হয়েছে", file=sys.stderr)

        # বাংলা: duplicate removal (একই ফাইল:লাইন:value)
        seen: set[tuple[str, int, str]] = set()
        unique_findings: list[Finding] = []
        for f in all_findings:
            key = (f.file, f.line, f.matched_value)
            if key not in seen:
                seen.add(key)
                unique_findings.append(f)
        all_findings = unique_findings

        # বাংলা: সর্ট — severity অনুসারে (red > yellow > green), তারপর ফাইল অনুসারে
        severity_order = {"red": 0, "yellow": 1, "green": 2}
        all_findings.sort(key=lambda f: (severity_order.get(f.severity, 99), f.file, f.line))

        red_count = sum(1 for f in all_findings if f.severity == "red")
        yellow_count = sum(1 for f in all_findings if f.severity == "yellow")
        green_count = sum(1 for f in all_findings if f.severity == "green")

        print(f"   ✅ স্ক্যান সম্পন্ন: {len(all_findings)}টি finding (🔴{red_count} 🟡{yellow_count} 🟢{green_count})", file=sys.stderr)

        # ── ধাপ ৬: রিপোর্ট আউটপুট ────────────────────────────────────
        if args.json:
            report = generate_json_report(all_findings, whitelist)
            if args.output:
                Path(args.output).write_text(report, encoding="utf-8")
                print(f"📄 JSON রিপোর্ট সংরক্ষিত: {args.output}", file=sys.stderr)
            else:
                print(report)
        else:
            report = generate_markdown_report(all_findings, whitelist)
            if args.output:
                Path(args.output).write_text(report, encoding="utf-8")
                print(f"📄 Markdown রিপোর্ট সংরক্ষিত: {args.output}", file=sys.stderr)
            else:
                # বাংলা: stdout-এ markdown রিপোর্ট
                print(report)

            # বাংলা: HARDCODED_AUDIT_AUTO.md-ও রিপোর্ট সংরক্ষণ
            default_report_path = REPO_ROOT / "HARDCODED_AUDIT_AUTO.md"
            default_report_path.write_text(report, encoding="utf-8")
            print(f"📄 স্বয়ংক্রিয় রিপোর্ট: {default_report_path}", file=sys.stderr)

        # ── ধাপ ৭: Exit code ─────────────────────────────────────────────
        if args.ci:
            # বাংলা: CI মোড — শুধু 🔴 findings থাকলে fail
            if red_count > 0:
                print(f"\n❌ CI FAIL: {red_count}টি 🔴 hardcoded config finding পাওয়া গেছে!", file=sys.stderr)
                return EXIT_HARDCODES_FOUND
            else:
                print("\n✅ CI PASS: কোনো 🔴 hardcoded config finding নেই", file=sys.stderr)
                return EXIT_CLEAN
        else:
            # বাংলা: সাধারণ মোড — যেকোনো 🔴 বা 🟡 থাকলে exit code 1
            if red_count > 0 or yellow_count > 0:
                return EXIT_HARDCODES_FOUND
            return EXIT_CLEAN

    except Exception as e:
        print(f"❌ ত্রুটি ঘটেছে: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return EXIT_ERROR


# ── এন্ট্রি পয়েন্ট ───────────────────────────────────────────────────────────
# বাংলা: সরাসরি execution-এ main() কল হবে
if __name__ == "__main__":
    sys.exit(main())
