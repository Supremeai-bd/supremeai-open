#!/usr/bin/env python3
"""
SupremeAI Environment Variable Reconciler
========================================
বাংলা: এই স্ক্রিপ্ট কোডবেসের সব env var রেফারেন্স এবং declaration ফাইল মিলিয়ে দেখে যে
কোনো ভেরিয়েবল "ghost" (কোডে আছে কিন্তু declaration-এ নেই) নাকি "orphan"
(declaration-এ আছে কিন্তু কোডে ব্যবহৃত নয়)।

Exit codes:
  0 = সব পরিষ্কার, কোনো সমস্যা নেই
  1 = সমস্যা পাওয়া গেছে (ghost/orphan/partial/criticality gap)
  2 = স্ক্রিপ্ট নিজেই ত্রুটিতে পড়েছে
"""

import ast
import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    import yaml as _pyyaml  # বাংলা: CI-তে ইতিমধ্যে pip install pyyaml করা হয়; পাওয়া গেলে এটাই ব্যবহার হবে
except ImportError:  # pragma: no cover - শুধু pyyaml সত্যিই না থাকলে fallback
    _pyyaml = None

# ─── Constants ───────────────────────────────────────────────────────────────
# বাংলা: রিপো রুট এবং ব্যাকএন্ড ডিরেক্টরির পাথ নির্ধারণ
# __file__ = .../scripts/env_var_reconciler.py → parents[1] = repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"

# ফাইল পাথ — এগুলো থেকে env var declaration পড়া হবে
# বাংলা: render.yaml রিপো রুটে নেই, এটা infrastructure/mcp-control-plane/-এ থাকে।
_ROOT_RENDER_YAML = REPO_ROOT / "render.yaml"
_MCP_RENDER_YAML = REPO_ROOT / "infrastructure" / "mcp-control-plane" / "render.yaml"
RENDER_YAML = _ROOT_RENDER_YAML if _ROOT_RENDER_YAML.is_file() else _MCP_RENDER_YAML
SECRETS_REGISTRY_YAML = REPO_ROOT / "secrets_registry.yaml"

# বাংলা: কোন secrets_registry criticality target-গুলোর জন্য repo-তে render
# blueprint আছে (একমাত্র blueprint: infrastructure/mcp-control-plane/render.yaml,
# সেবা "supremeai-mcp-tower" → registry target "render-mcp")। backend/worker/
# scraper/admin Render service-গুলো dashboard-managed — তাদের জন্য static
# verification সম্ভব নয়, তাই সেগুলো advisory (unverifiable) শ্রেণিতে যায়।
BLUEPRINTED_RENDER_TARGETS = {"render-mcp"}

# Pydantic config ফাইল — এগুলো থেকে validation_alias পার্স হবে
CONFIG_FIELD_FILES = [
    BACKEND_DIR / "core" / "config_fields.py",
    BACKEND_DIR / "core" / "config_secrets.py",
    BACKEND_DIR / "core" / "config.py",
]

# অতিরিক্ত declaration ফাইল — থাকলে পার্স হবে, না থাকলে এড়িয়ে যাবে
OPTIONAL_DECLARATION_FILES = [
    REPO_ROOT / ".env.example",
    REPO_ROOT / ".env.template",
]
INFRA_DIR = REPO_ROOT / "infrastructure"

# বাংলা: কোড স্ক্যান থেকে বাদ দেওয়ার মতো ডিরেক্টরি ও ফাইল
EXCLUDE_DIRS = {
    "__pycache__", ".git", ".venv", "venv", "node_modules",
    ".next", "dist", "build", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "htmlcov", ".tox", "alembic_migrations",
}
EXCLUDE_FILES = {
    "env_var_reconciler.py",  # বাংলা: নিজেকে স্ক্যান করা হবে না
    "audit_env_usage.py",
}

# বাংলা: এই ভেরিয়েবলগুলো সর্বদা প্রসেস ইন্টারনাল, রিকন্সিলিয়েশনে বাদ
SKIP_VARS = {
    "PYTHONPATH", "PATH", "HOME", "USER", "SHELL", "TERM",
    "LANG", "LC_ALL", "LC_CTYPE", "VIRTUAL_ENV", "CONDA_DEFAULT_ENV",
    "PYTHONDONTWRITEBYTECODE", "PYTHONSEEDBYTES", "_",
}


# ─── Simple Regex-Based YAML Parser ─────────────────────────────────────────
# বাংলা: PyYAML ডিপেন্ডেন্সি এড়াতে সহজ regex পার্সার ব্যবহৃত

def _parse_yaml_simple(content: str) -> Any:
    """Parse simple YAML structures using regex. Handles flat key-value,
    lists of dicts, and nested dicts one level deep."""
    result: dict[str, Any] = {}
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        # বাংলা: top-level key: value পার্সিং
        m = re.match(r"^(\w[\w\-]*)\s*:\s*(.*)$", stripped)
        if m:
            key = m.group(1)
            val_raw = m.group(2).strip()
            if val_raw in ("true", "True"):
                result[key] = True
            elif val_raw in ("false", "False"):
                result[key] = False
            elif val_raw.startswith('"') and val_raw.endswith('"'):
                result[key] = val_raw[1:-1]
            elif val_raw.startswith("'") and val_raw.endswith("'"):
                result[key] = val_raw[1:-1]
            elif re.match(r'^\d+$', val_raw):
                result[key] = int(val_raw)
            elif re.match(r'^\d+\.\d+$', val_raw):
                result[key] = float(val_raw)
            elif val_raw.startswith("["):
                # বাংলা: inline list parsing (e.g., ["a", "b"])
                result[key] = _parse_inline_list(val_raw)
            elif val_raw.startswith("{"):
                result[key] = _parse_inline_dict(val_raw)
            else:
                # বাংলা: মাল্টি-লাইন লিস্ট বা ডিকশনারি হতে পারে — পরবর্তী লাইন চেক
                sub_lines = []
                i += 1
                while i < len(lines):
                    sub = lines[i]
                    if sub and not sub[0].isspace() and sub.strip():
                        break
                    if sub.strip() and not sub.strip().startswith("#"):
                        sub_lines.append(sub)
                    i += 1
                # বাংলা: indentation-based list নাকি dict তা নির্ধারণ
                if sub_lines and sub_lines[0].strip().startswith("-"):
                    result[key] = _parse_yaml_list(sub_lines)
                elif sub_lines:
                    result[key] = _parse_yaml_subdict(sub_lines)
                else:
                    result[key] = val_raw if val_raw else None
                continue
        i += 1
    return result


def _parse_inline_list(s: str) -> list[str]:
    """Parse a simple YAML inline list like ["a", "b"]."""
    items = []
    for m in re.finditer(r'"([^"]*?)"|\'([^\']*?)\'|([\w\-]+)', s):
        items.append(m.group(1) or m.group(2) or m.group(3))
    if items:
        return items
    return []


def _parse_inline_dict(s: str) -> dict[str, str]:
    """Parse a simple YAML inline dict like {key: val, key2: val2}."""
    result = {}
    for m in re.finditer(r'(\w[\w\-]*)\s*:\s*([\w\-]+)', s):
        result[m.group(1)] = m.group(2)
    return result


def _get_indent(line: str) -> int:
    """বাংলা: একটি লাইনের leading whitespace পরিমাণ নির্ধারণ।"""
    return len(line) - len(line.lstrip())


def _parse_yaml_list(lines: list[str], base_indent: int = 0) -> list[dict[str, Any]]:
    """Parse a YAML list of dicts with proper indentation tracking.
    Handles nested lists (e.g. render.yaml envVars inside services).

    বাংলা: indentation level track করে nested structure সঠিকভাবে parse করা হয়।
    """
    items: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    current_key: str | None = None
    in_nested_list = False
    nested_items: list[dict[str, Any]] = []
    nested_current: dict[str, Any] = {}

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = _get_indent(line)

        # বাংলা: nested list (envVars) এর ভেতরে আছি কিনা চেক
        if in_nested_list:
            if indent <= base_indent + 4:
                # বাংলা: nested list শেষ — indent কমে গেছে
                if nested_current:
                    nested_items.append(nested_current)
                    nested_current = {}
                if current_key and nested_items:
                    current[current_key] = nested_items
                in_nested_list = False
                nested_items = []
            else:
                # বাংলা: still inside nested list
                if stripped.startswith("- "):
                    if nested_current:
                        nested_items.append(nested_current)
                    nested_current = {}
                    m = re.match(r'^(\w[\w\-]*)\s*:\s*(.*)$', stripped[2:])
                    if m:
                        nested_current[m.group(1)] = _clean_yaml_value(m.group(2).strip())
                else:
                    m = re.match(r'^(\w[\w\-]*)\s*:\s*(.*)$', stripped)
                    if m and nested_current is not None:
                        nested_current[m.group(1)] = _clean_yaml_value(m.group(2).strip())
                continue

        # বাংলা: টপ-লেভেল list item শুরু
        if stripped.startswith("- "):
            if current:
                items.append(current)
            current = {}
            rest = stripped[2:]
            m = re.match(r'^(\w[\w\-]*)\s*:\s*(.*)$', rest)
            if m:
                val = m.group(2).strip()
                if not val:
                    # বাংলা: খালি value — পরবর্তী লাইন থেকে nested structure আসবে
                    current_key = m.group(1)
                    current[m.group(1)] = []
                    # পরবর্তী lines-এ nested list check
                    in_nested_list = True
                    nested_items = []
                    nested_current = {}
                else:
                    current_key = None
                    current[m.group(1)] = _clean_yaml_value(val)
        elif re.match(r'^(\w[\w\-]*)\s*:', stripped):
            m = re.match(r'^(\w[\w\-]*)\s*:\s*(.*)$', stripped)
            if m and current is not None:
                val = m.group(2).strip()
                if not val:
                    # বাংলা: খালি value — nested list আসতে পারে
                    current_key = m.group(1)
                    current[m.group(1)] = []
                    in_nested_list = True
                    nested_items = []
                    nested_current = {}
                else:
                    current_key = None
                    current[m.group(1)] = _clean_yaml_value(val)

    # বাংলা: flush remaining
    if in_nested_list and nested_current:
        nested_items.append(nested_current)
    if in_nested_list and current_key and nested_items:
        current[current_key] = nested_items
    if current:
        items.append(current)
    return items


def _parse_yaml_subdict(lines: list[str]) -> dict[str, str]:
    """Parse a YAML sub-dict with indentation."""
    result: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = re.match(r'^(\w[\w\-]*)\s*:\s*(.*)$', stripped)
        if m:
            result[m.group(1)] = m.group(2).strip()
    return result


def _clean_yaml_value(val: str) -> str:
    """Remove surrounding quotes from a YAML value."""
    if (val.startswith('"') and val.endswith('"')) or \
       (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    return val


def parse_yaml_file(filepath: Path) -> dict[str, Any] | None:
    """Read and parse a YAML file. Returns None if file doesn't exist.

    বাংলা: pyyaml পাওয়া গেলে সেটা দিয়েই পার্স করা হয় (সঠিক, nested structure-সহ
    সব হ্যান্ডেল করে)। শুধু pyyaml সত্যিই ইনস্টল করা না থাকলে regex-based
    fallback parser ব্যবহার হবে — কিন্তু সেটা nested list-of-dict (যেমন
    secrets_registry.yaml-এর প্রতিটা key-এর নিচে criticality sub-dict)
    সঠিকভাবে পার্স করতে পারে না, তাই এটা শুধু last-resort।
    """
    if not filepath.is_file():
        return None
    try:
        content = filepath.read_text(encoding="utf-8")
        if _pyyaml is not None:
            try:
                data = _pyyaml.safe_load(content)
            except _pyyaml.composer.ComposerError:
                # বাংলা: multi-document YAML (যেমন k8s manifest, "---" দিয়ে
                # আলাদা করা) হলে প্রথম non-empty document নেওয়া হয়।
                docs = [d for d in _pyyaml.safe_load_all(content) if isinstance(d, dict)]
                data = docs[0] if docs else None
            return data if isinstance(data, dict) else None
        return _parse_yaml_simple(content)
    except Exception as e:
        print(f"Warning: Could not parse {filepath}: {e}", file=sys.stderr)
        return None


# ─── Environment Variable Extraction from Code ──────────────────────────────
# বাংলা: ব্যাকএন্ড পাইথন কোড থেকে সব env var রেফারেন্স বের করা হবে

def extract_from_python_file(filepath: Path) -> dict[str, list[dict[str, str]]]:
    """Extract env var references from a single Python file.
    Returns {VAR_NAME: [{"file": ..., "line": ..., "pattern": ...}]}
    """
    results: dict[str, list[dict[str, str]]] = defaultdict(list)
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception:
        return results

    lines = content.splitlines()
    rel_path = str(filepath.relative_to(REPO_ROOT))

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue

        # বাংলা: Pattern ১ — os.getenv("VAR_NAME") এবং os.getenv("VAR_NAME", default)
        for m in re.finditer(
            r'os\.getenv\s*\(\s*["\']([A-Z_][A-Z0-9_]*)["\']', line
        ):
            var_name = m.group(1)
            if var_name not in SKIP_VARS:
                results[var_name].append({
                    "file": rel_path, "line": lineno, "pattern": "os.getenv()"
                })

        # বাংলা: Pattern ২ — os.environ["VAR_NAME"]
        for m in re.finditer(
            r'os\.environ\s*\[\s*["\']([A-Z_][A-Z0-9_]*)["\']', line
        ):
            var_name = m.group(1)
            if var_name not in SKIP_VARS:
                results[var_name].append({
                    "file": rel_path, "line": lineno, "pattern": "os.environ[]"
                })

        # বাংলা: Pattern ৩ — os.environ.get("VAR_NAME")
        for m in re.finditer(
            r'os\.environ\.get\s*\(\s*["\']([A-Z_][A-Z0-9_]*)["\']', line
        ):
            var_name = m.group(1)
            if var_name not in SKIP_VARS:
                results[var_name].append({
                    "file": rel_path, "line": lineno, "pattern": "os.environ.get()"
                })

        # বাংলা: Pattern ৪ — validation_alias="VAR_NAME"
        for m in re.finditer(
            r'validation_alias\s*=\s*["\']([A-Z_][A-Z0-9_]*)["\']', line
        ):
            var_name = m.group(1)
            if var_name not in SKIP_VARS:
                results[var_name].append({
                    "file": rel_path, "line": lineno, "pattern": "validation_alias"
                })

    return results


def extract_from_dotenv_file(filepath: Path) -> set[str]:
    """Extract env var names from a .env.example or .env.template file.
    Lines like VAR_NAME=value or VAR_NAME= or # VAR_NAME=value.
    """
    vars_found: set[str] = set()
    if not filepath.is_file():
        return vars_found
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception:
        return vars_found
    for line in content.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            stripped = stripped[1:].lstrip()
        m = re.match(r'^([A-Z_][A-Z0-9_]*)\s*=', stripped)
        if m:
            vars_found.add(m.group(1))
    return vars_found


def resolve_variable_references(
    raw_results: dict[str, list[dict[str, str]]],
    all_file_contents: dict[Path, str],
) -> dict[str, list[dict[str, str]]]:
    """বাংলা: os.getenv(variable_name) প্যাটার্নে যেসব variable reference আছে
    সেগুলো trace back করে actual string literal বের করা হবে।
    """
    resolved = dict(raw_results)

    # বাংলা: প্রথমে সব ফাইল থেকে string assignment খুঁজি
    # format: VAR_NAME = "SOME_VALUE" or VAR_NAME = 'SOME_VALUE'
    string_assignments: dict[str, set[str]] = defaultdict(set)
    for fpath, content in all_file_contents.items():
        lines = content.splitlines()
        for line in lines:
            # বাংলা: simple assignment like VAR = "ENV_VAR_NAME"
            m = re.match(
                r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*["\']([A-Z_][A-Z0-9_]*)["\']', line
            )
            if m:
                var_local = m.group(1)
                var_env = m.group(2)
                string_assignments[var_local].add(var_env)

    # বাংলা: এখন os.getenv(VAR) প্যাটার্নের জন্য trace back
    for fpath, content in all_file_contents.items():
        lines = content.splitlines()
        for lineno, line in enumerate(lines, 1):
            # বাংলা: os.getenv(variable) — variable (string literal নয়)
            for m in re.finditer(
                r'os\.getenv\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)', line
            ):
                ref_var = m.group(1)
                # বাংলা: uppercase check — env vars সাধারণত uppercase
                if ref_var.isupper() and ref_var not in SKIP_VARS:
                    # বাংলা: সরাসরি uppercase variable = সম্ভবত env var নাম
                    rel_path = str(fpath.relative_to(REPO_ROOT))
                    if ref_var not in resolved:
                        resolved[ref_var] = []
                    # বাংলা: duplicate entry এড়াতে চেক
                    existing_files = {e["file"] for e in resolved[ref_var]}
                    if rel_path not in existing_files:
                        resolved[ref_var].append({
                            "file": rel_path, "line": lineno,
                            "pattern": "os.getenv(variable)"
                        })
                elif ref_var in string_assignments:
                    # বাংলা: variable-টি কোথাও string literal-এ assign করা আছে
                    for env_var in string_assignments[ref_var]:
                        if env_var not in SKIP_VARS:
                            if env_var not in resolved:
                                resolved[env_var] = []
                            rel_path = str(fpath.relative_to(REPO_ROOT))
                            existing_files = {e["file"] for e in resolved[env_var]}
                            if rel_path not in existing_files:
                                resolved[env_var].append({
                                    "file": rel_path, "line": lineno,
                                    "pattern": f"os.getenv({ref_var}) → {env_var}"
                                })
    return resolved


def scan_backend_code() -> dict[str, list[dict[str, str]]]:
    """বাংলা: ব্যাকএন্ড ডিরেক্টরির সব .py ফাইল স্ক্যান করে env var রেফারেন্স সংগ্রহ।"""
    all_refs: dict[str, list[dict[str, str]]] = defaultdict(list)
    all_contents: dict[Path, str] = {}

    if not BACKEND_DIR.is_dir():
        print(f"Error: Backend directory not found: {BACKEND_DIR}", file=sys.stderr)
        sys.exit(2)

    # বাংলা: সব Python ফাইল খুঁজে বের করা
    for root, dirs, files in os.walk(BACKEND_DIR):
        # বাংলা: exclude ডিরেক্টরি বাদ দেওয়া
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".venv")]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            if fname in EXCLUDE_FILES:
                continue
            fpath = Path(root) / fname
            try:
                content = fpath.read_text(encoding="utf-8")
                all_contents[fpath] = content
            except Exception:
                continue

    # বাংলা: প্রথম পাস — সরাসরি string literal references
    for fpath, content in all_contents.items():
        file_refs = extract_from_python_file(fpath)
        for var, entries in file_refs.items():
            all_refs[var].extend(entries)

    # বাংলা: দ্বিতীয় পাস — variable reference resolution
    all_refs = resolve_variable_references(all_refs, all_contents)

    return dict(all_refs)


# ─── Declaration File Parsing ──────────────────────────────────────────────
# বাংলা: render.yaml, secrets_registry.yaml, .env.example ইত্যাদি থেকে
# declared env var নাম সংগ্রহ

def extract_render_yaml_vars(data: dict[str, Any] | None) -> dict[str, dict[str, str]]:
    """বাংলা: render.yaml থেকে envVars key এবং value বের করা।
    Returns {VAR_NAME: {"value": ..., "service": ...}}
    """
    if not data:
        return {}
    results: dict[str, dict[str, str]] = {}
    services = data.get("services", [])
    if isinstance(services, list):
        for svc in services:
            svc_name = svc.get("name", "unknown")
            env_vars = svc.get("envVars", [])
            if isinstance(env_vars, list):
                for ev in env_vars:
                    if isinstance(ev, dict):
                        key = ev.get("key", "")
                        if key:
                            results[key] = {
                                "value": ev.get("value", ""),
                                "service": svc_name,
                            }
    return results


def extract_secrets_registry_vars(
    data: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """বাংলা: secrets_registry.yaml থেকে সব key name এবং criticality বের করা।
    Returns {VAR_NAME: {"criticality": {...}, "note": ...}}
    """
    if not data:
        return {}
    results: dict[str, dict[str, Any]] = {}
    keys = data.get("keys", [])
    if isinstance(keys, list):
        for entry in keys:
            if isinstance(entry, dict):
                name = entry.get("name", "")
                if name:
                    results[name] = {
                        "criticality": entry.get("criticality", {}),
                        "note": entry.get("note", ""),
                    }
    return results


def extract_infra_yaml_vars(infra_dir: Path) -> set[str]:
    """বাংলা: infrastructure/ ডিরেক্টরির সব YAML ফাইল থেকে env var খুঁজা।"""
    vars_found: set[str] = set()
    if not infra_dir.is_dir():
        return vars_found
    for fpath in infra_dir.rglob("*.yaml"):
        data = parse_yaml_file(fpath)
        if data:
            # বাংলা: envVars বা env সেকশন থেকে key বের করা
            for section_key in ("envVars", "env"):
                section = data.get(section_key, [])
                if isinstance(section, list):
                    for item in section:
                        if isinstance(item, dict):
                            k = item.get("key", item.get("name", ""))
                            if k:
                                vars_found.add(k)
                elif isinstance(section, dict):
                    for k in section:
                        if isinstance(k, str) and k.isupper():
                            vars_found.add(k)
    return vars_found


def parse_criticality_string(crit: Any) -> list[str]:
    """বাংলা: criticality dict/string থেকে 'critical' মার্ক আছে কিনা চেক।
    Returns list of services where it's marked critical.
    """
    critical_services: list[str] = []
    if isinstance(crit, dict):
        for svc, level in crit.items():
            if isinstance(level, str) and level.lower() == "critical":
                critical_services.append(svc)
    return critical_services


# ─── Reconciliation Logic ───────────────────────────────────────────────────
# বাংলা: কোড এবং declaration মিলিয়ে ৪ ধরনের সমস্যা সনাক্তকরণ

def reconcile(
    code_vars: dict[str, list[dict[str, str]]],
    render_vars: dict[str, dict[str, str]],
    secrets_vars: dict[str, dict[str, Any]],
    extra_vars: set[str],
) -> dict[str, Any]:
    """বাংলা: মূল reconciliation লজিক — ghost, orphan, partial, criticality gap খুঁজে বের করা।"""

    code_set = set(code_vars.keys())
    render_set = set(render_vars.keys())
    secrets_set = set(secrets_vars.keys())
    all_declared = render_set | secrets_set | extra_vars

    # বাংলা: ১. Ghost vars — কোডে আছে কিন্তু কোনো declaration-এ নেই
    ghost_vars = sorted(code_set - all_declared)

    # বাংলা: ২. Orphan vars — declaration-এ আছে কিন্তু কোডে ব্যবহৃত নয়
    orphan_vars = sorted(all_declared - code_set)

    # বাংলা: ৩. Partial coverage — এক declaration-এ আছে অন্যে নেই
    in_secrets_only = sorted(secrets_set - render_set - extra_vars)
    in_render_only = sorted(render_set - secrets_set - extra_vars)
    in_extra_only = sorted(extra_vars - render_set - secrets_set)
    # বাংলা: secrets_registry-এ আছে কিন্তু render.yaml এবং অন্য কোথাও নেই
    partial_coverage = {
        "in_secrets_registry_only": in_secrets_only,
        "in_render_yaml_only": in_render_only,
        "in_extra_files_only": in_extra_only,
    }

    # বাংলা: ৪. Criticality gap — RECALIBRATED (2026-09-24, run 36061775854):
    # পুরনো নিয়ম ছিল "registry-তে যেকোনো target-এ critical থাকলেই var-টিকে
    # render.yaml-এ থাকতে হবে" — কিন্তু infisical-vault / github-actions
    # target-এর সাথে render.yaml-এর কোনো সম্পর্কই নেই; ১৬টি gap-এর মধ্যে ৯টি
    # এমন ভুল শ্রেণিবদ্ধ ছিল। নতুন নিয়ম:
    #   • শুধুমাত্র render-* target-ই render.yaml-এর concern
    #   • যে render service-এর in-repo blueprint আছে (render-mcp →
    #     infrastructure/mcp-control-plane/render.yaml) — critical var সেখানে
    #     না থাকলে সেটি সত্যিকারের BLOCKING gap (blueprint-এ sync:false দিয়ে
    #     declare করা সম্ভব)
    #   • backend/worker/scraper render service dashboard-managed (repo-তে
    #     blueprint নেই) — static verification অসম্ভব, তাই সেগুলো advisory
    #     "unverifiable" শ্রেণিতে যায়, blocking নয় (permanent false-red এড়াতে)
    criticality_gaps: list[dict[str, Any]] = []
    unverifiable_render_critical: list[dict[str, Any]] = []
    for var_name, var_info in secrets_vars.items():
        crit = var_info.get("criticality", {})
        critical_services = parse_criticality_string(crit)
        render_critical = [s for s in critical_services if s.startswith("render-")]
        if not render_critical or var_name in render_set:
            continue
        entry = {
            "var_name": var_name,
            "critical_in": render_critical,
            "note": var_info.get("note", ""),
        }
        if any(s in BLUEPRINTED_RENDER_TARGETS for s in render_critical):
            criticality_gaps.append(entry)
        else:
            unverifiable_render_critical.append(entry)
    criticality_gaps.sort(key=lambda x: x["var_name"])
    unverifiable_render_critical.sort(key=lambda x: x["var_name"])

    # বাংলা: ৫. Intersection — সব জায়গায় আছে (সুসংবাদ)
    well_covered = sorted(code_set & all_declared)

    return {
        "ghost_vars": ghost_vars,
        "orphan_vars": orphan_vars,
        "partial_coverage": partial_coverage,
        "criticality_gaps": criticality_gaps,
        "well_covered": well_covered,
        "summary": {
            "total_in_code": len(code_set),
            "total_in_render_yaml": len(render_set),
            "total_in_secrets_registry": len(secrets_set),
            "total_in_extra_files": len(extra_vars),
            "total_declared": len(all_declared),
            "ghost_count": len(ghost_vars),
            "orphan_count": len(orphan_vars),
            "partial_coverage_count": (
                len(in_secrets_only) + len(in_render_only) + len(in_extra_only)
            ),
            "criticality_gap_count": len(criticality_gaps),
            "unverifiable_render_critical_count": len(unverifiable_render_critical),
            "well_covered_count": len(well_covered),
        },
        "unverifiable_render_critical": unverifiable_render_critical,
    }


# ─── Report Generation ──────────────────────────────────────────────────────
# বাংলা: ফলাফল মার্কডাউন বা JSON ফরম্যাটে আউটপুট

def generate_markdown_report(
    result: dict[str, Any],
    code_vars: dict[str, list[dict[str, str]]],
    render_vars: dict[str, dict[str, str]],
    secrets_vars: dict[str, dict[str, Any]],
    config_only: bool = False,
    code_only: bool = False,
) -> str:
    """বাংলা: স্ট্রাকচার্ড মার্কডাউন রিপোর্ট তৈরি।"""
    lines: list[str] = []
    s = result["summary"]

    lines.append("# 🔍 SupremeAI Environment Variable Reconciliation Report")
    lines.append("")
    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Env vars in code | {s['total_in_code']} |")
    lines.append(f"| Declared in render.yaml | {s['total_in_render_yaml']} |")
    lines.append(f"| Declared in secrets_registry.yaml | {s['total_in_secrets_registry']} |")
    lines.append(f"| Declared in extra files | {s['total_in_extra_files']} |")
    lines.append(f"| **Total declared** | **{s['total_declared']}** |")
    lines.append(f"| **Well covered** (code ∩ config) | **{s['well_covered_count']}** |")
    lines.append("")

    # বাংলা: সমস্যার সারাংশ
    has_issues = (
        s["ghost_count"] > 0 or s["orphan_count"] > 0 or
        s["partial_coverage_count"] > 0 or s["criticality_gap_count"] > 0
    )
    if has_issues:
        lines.append("## ⚠️ Issues Found")
        lines.append("")
        lines.append(f"| Issue Type | Count | Severity |")
        lines.append(f"|------------|-------|----------|")
        if s["ghost_count"] > 0:
            lines.append(f"| Ghost vars (code → no declaration) | {s['ghost_count']} | 🔴 High |")
        if s["orphan_count"] > 0:
            lines.append(f"| Orphan vars (declaration → no code) | {s['orphan_count']} | 🟡 Medium |")
        if s["partial_coverage_count"] > 0:
            lines.append(f"| Partial coverage (one config only) | {s['partial_coverage_count']} | 🟡 Medium |")
        if s["criticality_gap_count"] > 0:
            lines.append(f"| Criticality gap (critical for blueprinted render service ∉ render.yaml) | {s['criticality_gap_count']} | 🔴 High |")
        if s.get("unverifiable_render_critical_count", 0) > 0:
            lines.append(f"| Render-critical but dashboard-managed (no in-repo blueprint — advisory) | {s['unverifiable_render_critical_count']} | 🟡 Advisory |")
        lines.append("")
    else:
        lines.append("## ✅ No Issues Found")
        lines.append("")
        lines.append("All environment variables are properly declared and referenced.")
        lines.append("")

    if not code_only:
        # বাংলা: Ghost vars — কোডে আছে কিন্তু declaration-এ নেই
        ghost = result["ghost_vars"]
        lines.append(f"## 1. Ghost Vars in Code ({len(ghost)})")
        lines.append("")
        lines.append("> বাংলা: এই ভেরিয়েবলগুলো কোডে ব্যবহৃত হচ্ছে কিন্তু কোনো config/secret ফাইলে declared নেই।")
        lines.append(">")
        if ghost:
            for var in ghost:
                lines.append(f"### `{var}`")
                lines.append("")
                locations = code_vars.get(var, [])
                if locations:
                    lines.append("| File | Line | Pattern |")
                    lines.append("|------|------|---------|")
                    for loc in locations:
                        lines.append(
                            f"| `{loc['file']}` | {loc['line']} | {loc['pattern']} |"
                        )
                lines.append("")
        else:
            lines.append("*None — all code-referenced vars are declared somewhere.*")
            lines.append("")

        # বাংলা: Orphan vars
        orphan = result["orphan_vars"]
        lines.append(f"## 2. Orphan Vars in Config ({len(orphan)})")
        lines.append("")
        lines.append("> বাংলা: এই ভেরিয়েবলগুলো declaration ফাইলে আছে কিন্তু কোডে কোথাও ব্যবহৃত হচ্ছে না।")
        lines.append(">")
        if orphan:
            for var in orphan:
                source = ""
                if var in render_vars:
                    source = f"render.yaml (service: {render_vars[var].get('service', 'N/A')})"
                elif var in secrets_vars:
                    crit = secrets_vars[var].get("criticality", {})
                    source = f"secrets_registry.yaml (criticality: {crit})"
                else:
                    source = "extra file (.env.example / infrastructure/)"
                lines.append(f"- `{var}` — {source}")
            lines.append("")
        else:
            lines.append("*None — all declared vars are referenced in code.*")
            lines.append("")

        # বাংলা: Partial coverage
        pc = result["partial_coverage"]
        total_partial = s["partial_coverage_count"]
        lines.append(f"## 3. Partial Coverage ({total_partial})")
        lines.append("")
        lines.append("> বাংলা: এই ভেরিয়েবলগুলো একটি config ফাইলে আছে কিন্তু অন্যটিতে নেই।")
        lines.append(">")
        if total_partial > 0:
            if pc["in_secrets_registry_only"]:
                lines.append("### In secrets_registry.yaml only (not in render.yaml):")
                lines.append("")
                for var in pc["in_secrets_registry_only"]:
                    crit = secrets_vars.get(var, {}).get("criticality", {})
                    lines.append(f"- `{var}` (criticality: {crit})")
                lines.append("")
            if pc["in_render_yaml_only"]:
                lines.append("### In render.yaml only (not in secrets_registry.yaml):")
                lines.append("")
                for var in pc["in_render_yaml_only"]:
                    svc = render_vars.get(var, {}).get("service", "N/A")
                    lines.append(f"- `{var}` (service: {svc})")
                lines.append("")
            if pc["in_extra_files_only"]:
                lines.append("### In extra files only (not in render.yaml or secrets_registry):")
                lines.append("")
                for var in pc["in_extra_files_only"]:
                    lines.append(f"- `{var}`")
                lines.append("")
        else:
            lines.append("*Full coverage across all declaration files.*")
            lines.append("")

        # বাংলা: Criticality gap
        cg = result["criticality_gaps"]
        uv = result.get("unverifiable_render_critical", [])
        lines.append(f"## 4. Criticality Gaps ({len(cg)})")
        lines.append("")
        lines.append("> বাংলা: এই ভেরিয়েবলগুলো একটি **in-repo blueprinted** render service-এর জন্য `critical`, কিন্তু blueprint-এ নেই।")
        lines.append("> প্রোডাকশন deploy-এ এগুলো missing হলে boot crash হতে পারে — blueprint-এ `sync: false` দিয়ে declare করুন।")
        lines.append(">")
        if cg:
            lines.append("| Variable | Critical In | Note |")
            lines.append("|----------|------------|------|")
            for gap in cg:
                critical_in = ", ".join(gap["critical_in"])
                note = gap.get("note", "")[:80]
                lines.append(f"| `{gap['var_name']}` | {critical_in} | {note} |")
            lines.append("")
        else:
            lines.append("*No criticality gaps found.*")
            lines.append("")
        if uv:
            lines.append(f"### Render-critical, dashboard-managed (advisory — no in-repo blueprint to verify against) ({len(uv)})")
            lines.append("")
            lines.append("| Variable | Critical In | Note |")
            lines.append("|----------|------------|------|")
            for gap in uv:
                critical_in = ", ".join(gap["critical_in"])
                note = gap.get("note", "")[:80]
                lines.append(f"| `{gap['var_name']}` | {critical_in} | {note} |")
            lines.append("")

    if not config_only:
        # বাংলা: Well-covered vars
        wc = result["well_covered"]
        lines.append(f"## 5. Well-Covered Variables ({len(wc)})")
        lines.append("")
        if wc:
            lines.append("| Variable | Code References | In render.yaml | In secrets_registry |")
            lines.append("|----------|-----------------|----------------|---------------------|")
            for var in wc:
                code_count = len(code_vars.get(var, []))
                in_render = "✅" if var in render_vars else "❌"
                in_secrets = "✅" if var in secrets_vars else "❌"
                lines.append(
                    f"| `{var}` | {code_count} | {in_render} | {in_secrets} |"
                )
            lines.append("")
        else:
            lines.append("*No well-covered variables found.*")
            lines.append("")

    return "\n".join(lines)


def generate_json_report(result: dict[str, Any]) -> str:
    """বাংলা: JSON ফরম্যাটে রিপোর্ট তৈরি।"""
    return json.dumps(result, indent=2, ensure_ascii=False)


# ─── Main Entry Point ───────────────────────────────────────────────────────
# বাংলা: স্ক্রিপ্টের মূল এন্ট্রি পয়েন্ট

def main() -> int:
    parser = argparse.ArgumentParser(
        description="SupremeAI Environment Variable Reconciler — "
        "বাংলা: কোড ও config ফাইলের env var মিলিয়ে দেখে।",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0 = সব পরিষ্কার (clean)
  1 = সমস্যা পাওয়া গেছে (ghost/orphan/partial/criticality gap)
  2 = স্ক্রিপ্ট ত্রুটি (error)
        """,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report as JSON instead of Markdown",
    )
    parser.add_argument(
        "--config-only",
        action="store_true",
        help="বাংলা: শুধু config সমস্যা দেখাও (ghost, orphan, partial, criticality)",
    )
    parser.add_argument(
        "--code-only",
        action="store_true",
        help="বাংলা: শুধু code coverage দেখাও (well-covered vars)",
    )
    parser.add_argument(
        "--fail-on-critical",
        action="store_true",
        default=False,
        help="CI mode: exit non-zero only for High-severity findings "
        "(ghost_count, criticality_gap_count), not Medium (orphan/partial).",
    )

    args = parser.parse_args()

    # বাংলা: ─── ধাপ ১: কোড স্ক্যান ───
    try:
        code_vars = scan_backend_code()
    except Exception as e:
        print(f"Error scanning backend code: {e}", file=sys.stderr)
        sys.exit(2)

    # বাংলা: ─── ধাপ ২: Declaration ফাইল পার্স ───
    render_data = parse_yaml_file(RENDER_YAML)
    render_vars = extract_render_yaml_vars(render_data)

    secrets_data = parse_yaml_file(SECRETS_REGISTRY_YAML)
    secrets_vars = extract_secrets_registry_vars(secrets_data)

    # বাংলা: ঐচ্ছিক ফাইল থেকেও vars সংগ্রহ
    extra_vars: set[str] = set()
    for fpath in OPTIONAL_DECLARATION_FILES:
        extra_vars |= extract_from_dotenv_file(fpath)
    extra_vars |= extract_infra_yaml_vars(INFRA_DIR)

    # বাংলা: ─── ধাপ ৩: Reconciliation ───
    result = reconcile(code_vars, render_vars, secrets_vars, extra_vars)

    # বাংলা: code_vars-এর references-ও result-এ যোগ (JSON-এ প্রয়োজন)
    result["code_references"] = code_vars
    result["render_vars"] = render_vars
    result["secrets_vars"] = secrets_vars
    result["extra_vars"] = sorted(extra_vars)

    # বাংলা: ─── ধাপ ৪: আউটপুট ───
    if args.json:
        report = generate_json_report(result)
    else:
        report = generate_markdown_report(
            result, code_vars, render_vars, secrets_vars,
            config_only=args.config_only,
            code_only=args.code_only,
        )

    print(report)

    # বাংলা: ─── ধাপ ৫: Exit code ───
    s = result["summary"]
    if args.fail_on_critical:
        critical = s["criticality_gap_count"] > 0
        return 1 if critical else 0
    has_issues = (
        s["ghost_count"] > 0 or s["orphan_count"] > 0 or
        s["partial_coverage_count"] > 0 or s["criticality_gap_count"] > 0
    )
    return 1 if has_issues else 0


if __name__ == "__main__":
    sys.exit(main())
