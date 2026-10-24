#!/usr/bin/env python3
"""
SupremeAI Agent Capability Registry Sync
==========================================
বাংলা: এই স্ক্রিপ্টটি সমগ্র `backend/` ডিরেক্টরি থেকে সব Agent ক্লাস আবিষ্কার করে,
কেন্দ্রীয় রেজিস্ট্রিগুলোর সাথে ক্রস-রেফারেন্স করে, এবং ফ্যাগমেন্টেশন স্কোর বের করে।

ব্যবহার:
    python agent_capability_registry_sync.py
    python agent_capability_registry_sync.py --json
    python agent_capability_registry_sync.py --fix-suggestions

এক্সিট কোড:
    0 = সব এজেন্ট রেজিস্টার্ড
    1 = আনরেজিস্টার্ড এজেন্ট আছে
    2 = ত্রুটি ঘটেছে
"""

from __future__ import annotations

# বাংলা: শুধুমাত্র স্ট্যান্ডার্ড লাইব্রেরি ব্যবহার — কোনো বাহ্যিক ডিপেন্ডেন্সি নেই
import argparse
import ast
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════════
# বাংলা: ডেটা মডেল — এজেন্ট ক্লাস, রেজিস্ট্রি, এবং রিপোর্টের জন্য ডাটা ক্লাস
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class AgentMethod:
    """বাংলা: এজেন্টের একটি পাবলিক মেথডের তথ্য।"""
    name: str
    line: int
    has_docstring: bool = False
    docstring: str = ""


@dataclass
class AgentClass:
    """বাংলা: আবিষ্কৃত এজেন্ট ক্লাসের সম্পূর্ণ তথ্য।"""
    name: str
    file_path: str  # রিপো রুট থেকে relative path
    line_number: int
    methods: list[AgentMethod] = field(default_factory=list)
    description: str = ""
    name_attr: str = ""
    decorators: list[str] = field(default_factory=list)
    docstring: str = ""
    # বাংলা: কোন কোন রেজিস্ট্রিতে এই এজেন্ট আছে
    registries: list[str] = field(default_factory=list)
    # বাংলা: এজেন্টের স্ট্যাটাস
    status: str = "UNREGISTERED"  # REGISTERED, PARTIALLY_REGISTERED, UNREGISTERED, REGISTRY_GHOST


@dataclass
class RegistryEntry:
    """বাংলা: একটি কেন্দ্রীয় রেজিস্ট্রি এন্ট্রি।"""
    registry_name: str
    registry_file: str
    entry_name: str
    entry_value: str = ""  # বাংলা: যদি ক্লাস রেফারেন্স থাকে তার নাম
    line_number: int = 0


# ═══════════════════════════════════════════════════════════════════════════════
# বাংলা: AST ভিত্তিক পার্সার — পাইথন ফাইল থেকে ক্লাস ও মেথড বের করে
# ═══════════════════════════════════════════════════════════════════════════════


# বাংলা: ডেটা মডেল/রিকোয়েস্ট-রেসপন্স ক্লাস — এগুলো আসল এজেন্ট নয়
_MODEL_SUFFIXES = frozenset([
    "request", "response", "config", "result", "output",
    "input", "params", "options", "settings", "state",
    "log", "record", "entry", "event", "genome", "offspring",
    "performance", "reflection", "capability", "circuitbreaker",
    "dagscheduler", "health", "execute", "task", "session",
    "status", "breeder", "department", "base",
])


def _is_real_agent_class(name: str, node: ast.ClassDef) -> bool:
    """বাংলা: ক্লাসটি আসল এজেন্ট কিনা যাচাই করে। ডেটা মডেল ও প্যাটার্ন ক্লাস ফিল্টার করে।"""
    if "Agent" not in name:
        return False
    # বাংলা: রিকোয়েস্ট/রেসপন্স/ডেটা মডেল বাদ
    lower = name.lower()
    for suffix in _MODEL_SUFFIXES:
        if lower.endswith(suffix) or lower == suffix:
            return False
    # বাংলা: Pydantic BaseModel-এর সরাসরি চাইল্ড যদি শুধু data ধারণ করে
    # (no public methods other than model methods) তাহলে বাদ
    return True


class AgentClassVisitor(ast.NodeVisitor):
    """বাংলা: AST ভিজিটর যা Agent ক্লাসগুলো খুঁজে বের করে এবং তাদের মেথড তালিকা করে।"""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.agents: list[AgentClass] = []
        # বাংলা: রেজিস্ট্রেশন সম্ভাব্য ডেকোরেটর প্যাটার্ন
        self._registration_decorators = {
            "register", "skill", "register_agent", "register_skill",
            "agent", "register_tool", "tool",
        }

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # বাংলা: শুধুমাত্র আসল এজেন্ট ক্লাস গণনায় নেওয়া হবে
        if not _is_real_agent_class(node.name, node):
            self.generic_visit(node)
            return

        # বাংলা: এই ক্লাসের জন্য মেথড সংগ্রহ করা হচ্ছে
        methods: list[AgentMethod] = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # বাংলা: ডান্ডার মেথড বাদ দেওয়া হচ্ছে (যেমন __init__)
                if item.name.startswith("_"):
                    continue
                has_doc = (ast.get_docstring(item) is not None)
                methods.append(AgentMethod(
                    name=item.name,
                    line=item.lineno,
                    has_docstring=has_doc,
                    docstring=ast.get_docstring(item) or "",
                ))

        # বাংলা: ক্লাস ডেকোরেটর সংগ্রহ
        decorators: list[str] = []
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                decorators.append(dec.id)
            elif isinstance(dec, ast.Attribute):
                decorators.append(f"{ast.dump(dec.attr)}")
            elif isinstance(dec, ast.Call):
                if isinstance(dec.func, ast.Name):
                    decorators.append(dec.func.id)
                elif isinstance(dec.func, ast.Attribute):
                    decorators.append(dec.func.attr)

        # বাংলা: ক্লাসের description ও name অ্যাট্রিবিউট খোঁজা (docstring ও class body থেকে)
        class_docstring = ast.get_docstring(node) or ""
        description = ""
        name_attr = ""
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        if target.id == "description":
                            # বাংলা: স্ট্রিং ভ্যালু বের করা
                            if isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                                description = item.value.value
                        elif target.id == "name":
                            if isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                                name_attr = item.value.value

        agent = AgentClass(
            name=node.name,
            file_path=self.file_path,
            line_number=node.lineno,
            methods=methods,
            description=description,
            name_attr=name_attr,
            decorators=decorators,
            docstring=class_docstring,
        )
        self.agents.append(agent)
        self.generic_visit(node)


def parse_agent_classes(file_path: Path, repo_root: Path) -> list[AgentClass]:
    """বাংলা: একটি পাইথন ফাইল থেকে Agent ক্লাস পার্স করে।"""
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
        visitor = AgentClassVisitor(str(file_path.relative_to(repo_root)))
        visitor.visit(tree)
        return visitor.agents
    except (SyntaxError, UnicodeDecodeError, OSError) as e:
        # বাংলা: পার্স ত্রুটি হলে রেজেক্স ফলব্যাক ব্যবহার
        return _regex_fallback_discover(file_path, repo_root, str(e))


def _regex_fallback_discover(file_path: Path, repo_root: Path, error_detail: str) -> list[AgentClass]:
    """বাংলা: AST পার্স ব্যর্থ হলে রেজেক্স দিয়ে ক্লাস খোঁজা।"""
    agents: list[AgentClass] = []
    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError:
        return agents

    # বাংলা: ক্লাস ডেফিনিশন খোঁজা
    for match in re.finditer(r"^class\s+(\w*[Aa]gent\w*)\s*\(?", source, re.MULTILINE):
        class_name = match.group(1)
        line_num = source[:match.start()].count("\n") + 1
        agents.append(AgentClass(
            name=class_name,
            file_path=str(file_path.relative_to(repo_root)),
            line_number=line_num,
        ))
    return agents


# ═══════════════════════════════════════════════════════════════════════════════
# বাংলা: রেজিস্ট্রি পার্সার — বিভিন্ন ফরম্যাটের রেজিস্ট্রি থেকে এন্ট্রি বের করে
# ═══════════════════════════════════════════════════════════════════════════════


def parse_skill_registry(repo_root: Path) -> list[RegistryEntry]:
    """বাংলা: skill_registry.py থেকে স্কিল/এজেন্ট এন্ট্রি বের করে।"""
    entries: list[RegistryEntry] = []
    reg_file = repo_root / "backend" / "skills" / "skill_registry.py"
    if not reg_file.exists():
        return entries

    # বাংলা: এই রেজিস্ট্রি JSON ম্যানিফেস্ট ফাইল থেকে লোড করে, তাই manifests/ ডিরেক্টরি স্ক্যান
    manifests_dir = repo_root / "backend" / "skills" / "manifests"
    if manifests_dir.exists():
        for mf in manifests_dir.glob("*.json"):
            try:
                data = json.loads(mf.read_text(encoding="utf-8"))
                skill_id = data.get("id") or mf.stem
                entries.append(RegistryEntry(
                    registry_name="skill_registry",
                    registry_file=str(mf.relative_to(repo_root)),
                    entry_name=skill_id,
                ))
            except (json.JSONDecodeError, OSError):
                continue

    # বাংলা: রেজিস্ট্রি ফাইলে সরাসরি ক্লাস রেফারেন্স থাকলে সেটাও স্ক্যান
    try:
        source = reg_file.read_text(encoding="utf-8")
        # বাংলা: Agent শব্দযুক্ত স্ট্রিং লিটারেল খোঁজা
        for m in re.finditer(r'["\']([\w]*[Aa]gent[\w]*)["\']', source):
            entries.append(RegistryEntry(
                registry_name="skill_registry",
                registry_file=str(reg_file.relative_to(repo_root)),
                entry_name=m.group(1),
                line_number=source[:m.start()].count("\n") + 1,
            ))
    except OSError:
        print('Silenced error in except block')

    return entries


def parse_adaptive_registry(repo_root: Path) -> list[RegistryEntry]:
    """বাংলা: adaptive_engine/registry.py থেকে এজেন্ট/প্ল্যাটফর্ম এন্ট্রি বের করে।"""
    entries: list[RegistryEntry] = []
    reg_file = repo_root / "backend" / "adaptive_engine" / "registry.py"
    if not reg_file.exists():
        return entries

    try:
        source = reg_file.read_text(encoding="utf-8")
        # বাংলা: PlatformRegistry তে name= প্যারামিটারে এজেন্ট/প্ল্যাটফর্ম নাম থাকতে পারে
        for m in re.finditer(r'name=["\']([\w]+)["\']', source):
            name = m.group(1)
            # বাংলা: শুধুমাত্র Agent শব্দযুক্ত নাম নেওয়া হবে
            if "Agent" in name or "agent" in name:
                entries.append(RegistryEntry(
                    registry_name="adaptive_registry",
                    registry_file=str(reg_file.relative_to(repo_root)),
                    entry_name=name,
                    line_number=source[:m.start()].count("\n") + 1,
                ))
    except OSError:
        print('Silenced error in except block')

    return entries


def parse_json_registry(repo_root: Path) -> list[RegistryEntry]:
    """বাংলা: core/agent_registry.json থেকে এজেন্ট এন্ট্রি বের করে।"""
    entries: list[RegistryEntry] = []
    json_file = repo_root / "backend" / "core" / "agent_registry.json"
    if not json_file.exists():
        return entries

    try:
        data = json.loads(json_file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for key in data.keys():
                entries.append(RegistryEntry(
                    registry_name="agent_registry_json",
                    registry_file=str(json_file.relative_to(repo_root)),
                    entry_name=key,
                ))
    except (json.JSONDecodeError, OSError):
        print('Silenced error in except block')

    return entries


def parse_headless_registry(repo_root: Path) -> list[RegistryEntry]:
    """বাংলা: tools/headless_agent_registry.py থেকে এজেন্ট এন্ট্রি বের করে।"""
    entries: list[RegistryEntry] = []
    reg_file = repo_root / "backend" / "tools" / "headless_agent_registry.py"
    if not reg_file.exists():
        return entries

    try:
        source = reg_file.read_text(encoding="utf-8")
        # বাংলা: dict key হিসেবে agent নাম থাকে (যেমন "gemini-cli": { ... })
        for m in re.finditer(r'["\']([\w][\w\-]*)["\']\s*:', source):
            name = m.group(1)
            if "agent" in name.lower() or any(
                kw in name.lower()
                for kw in ("openhands", "aider", "cline", "devika", "plandex",
                            "codeium", "gemini", "gpt-pilot", "continue", "swe")
            ):
                entries.append(RegistryEntry(
                    registry_name="headless_agent_registry",
                    registry_file=str(reg_file.relative_to(repo_root)),
                    entry_name=name,
                    line_number=source[:m.start()].count("\n") + 1,
                ))
    except OSError:
        print('Silenced error in except block')

    return entries


def scan_additional_agent_maps(repo_root: Path) -> list[RegistryEntry]:
    """বাংলা: অন্যান্য ফাইলে থাকা Agent-ম্যাপিং ডিকশনারি/লিস্ট স্ক্যান করে।
    শুধুমাত্র সত্যিকারের রেজিস্ট্রি-প্যাটার্ন (dict/list অ্যাসাইনমেন্ট) ধরা হয়।
    """
    entries: list[RegistryEntry] = []
    backend_dir = repo_root / "backend"

    # বাংলা: ইতিমধ্যে পার্স করা রেজিস্ট্রি ফাইল বাদ
    skip_files = (
        "skill_registry.py", "adaptive_engine/registry.py",
        "headless_agent_registry.py", "agent_factory.py",
        "agent_capability_registry_sync.py",
    )

    for py_file in backend_dir.rglob("*.py"):
        rel = str(py_file.relative_to(repo_root))
        if any(skip in rel for skip in skip_files):
            continue
        if "__pycache__" in rel or "/test" in rel:
            continue

        try:
            source = py_file.read_text(encoding="utf-8")
        except OSError:
            continue

        # বাংলা: শুধুমাত্র এগুলোকে রেজিস্ট্রি হিসেবে গণ্য করা হবে:
        # ১. VARIABLE = { ... } যেখানে কী/ভ্যালুতে Agent আছে
        # ২. VARIABLE = [ ... ] যেখানে Agent ক্লাস রেফারেন্স আছে
        # প্যাটার্ন: ভেরিয়েবল অ্যাসাইনমেন্টে Agent শব্দ সহ dict/list
        # বাংলা: প্রথমে ভেরিয়েবল অ্যাসাইনমেন্ট খোঁজা
        for block_match in re.finditer(
            r'^\s*(?:AGENTS?|AGENT_REGISTRY|AGENT_MAP|_AGENTS?|_REGISTRY)\s*[=]\s*\{',
            source,
            re.MULTILINE,
        ):
            # বাংলা: ডিকশনারি ব্লক থেকে Agent নাম বের করা
            start = block_match.start()
            # বাংলা: ব্লকের শেষ খুঁজে বের করা (simplified)
            chunk = source[start:start + 2000]
            for key_m in re.finditer(r'["\']([\w]*[Aa]gent[\w]*)["\']\s*:', chunk):
                name = key_m.group(1)
                if not _is_real_agent_class(name, ast.ClassDef()):
                    continue
                entries.append(RegistryEntry(
                    registry_name="discovered_agent_map",
                    registry_file=rel,
                    entry_name=name,
                    line_number=source[:start].count("\n") + 1,
                ))

        # বাংলা: list অ্যাসাইনমেন্ট প্যাটার্ন
        for block_match in re.finditer(
            r'^\s*(?:AGENTS?|AGENT_REGISTRY|AGENT_LIST|_AGENTS?)\s*[=]\s*\[',
            source,
            re.MULTILINE,
        ):
            start = block_match.start()
            chunk = source[start:start + 2000]
            for key_m in re.finditer(r'["\']([\w]*[Aa]gent[\w]*)["\']', chunk):
                name = key_m.group(1)
                if not _is_real_agent_class(name, ast.ClassDef()):
                    continue
                entries.append(RegistryEntry(
                    registry_name="discovered_agent_map",
                    registry_file=rel,
                    entry_name=name,
                    line_number=source[:start].count("\n") + 1,
                ))

    return entries


# ═══════════════════════════════════════════════════════════════════════════════
# বাংলা: মূল স্ক্যানার লজিক — এজেন্ট আবিষ্কার ও ক্রস-রেফারেন্স
# ═══════════════════════════════════════════════════════════════════════════════


def discover_all_agents(repo_root: Path) -> list[AgentClass]:
    """বাংলা: backend/ ডিরেক্টরির সব .py ফাইল থেকে Agent ক্লাস আবিষ্কার করে।"""
    agents: list[AgentClass] = []
    backend_dir = repo_root / "backend"

    if not backend_dir.exists():
        print(f"ত্রুটি: backend/ ডিরেক্টরি পাওয়া যায়নি: {backend_dir}", file=sys.stderr)
        return agents

    # বাংলা: প্রাধান্য অনুযায়ী স্ক্যান করা হচ্ছে
    priority_dirs = [
        "adaptive_engine", "browser", "brain", "tools",
        "core", "agents", "models", "services",
    ]

    py_files: list[Path] = []
    for subdir in priority_dirs:
        target = backend_dir / subdir
        if target.exists():
            py_files.extend(target.rglob("*.py"))

    # বাংলা: বাকি ডিরেক্টরিও স্ক্যান
    seen: set[str] = set(str(f) for f in py_files)
    for py_file in backend_dir.rglob("*.py"):
        if str(py_file) not in seen:
            py_files.append(py_file)

    for py_file in py_files:
        # বাংলা: টেস্ট ফাইল বাদ দেওয়া হচ্ছে (শুধু মূল কোড স্ক্যান)
        rel = str(py_file.relative_to(repo_root))
        parts = rel.replace(os.sep, "/").split("/")
        if "test" in parts or "tests" in parts or "__pycache__" in parts:
            continue
        # বাংলা: ফাইল নামে test_ থাকলেও বাদ
        if py_file.stem.startswith("test_"):
            continue

        file_agents = parse_agent_classes(py_file, repo_root)
        agents.extend(file_agents)

    return agents


def discover_all_registries(repo_root: Path) -> dict[str, list[RegistryEntry]]:
    """বাংলা: সব কেন্দ্রীয় রেজিস্ট্রি থেকে এন্ট্রি সংগ্রহ করে।"""
    registries: dict[str, list[RegistryEntry]] = {}

    # বাংলা: পরিচিত রেজিস্ট্রি পার্সারগুলো কল
    parsers = [
        ("skill_registry", parse_skill_registry),
        ("adaptive_registry", parse_adaptive_registry),
        ("agent_registry_json", parse_json_registry),
        ("headless_agent_registry", parse_headless_registry),
    ]

    for name, parser_fn in parsers:
        entries = parser_fn(repo_root)
        if entries:
            registries[name] = entries

    # বাংলা: অতিরিক্ত ম্যাপিং স্ক্যান
    extra = scan_additional_agent_maps(repo_root)
    if extra:
        if "discovered_agent_map" not in registries:
            registries["discovered_agent_map"] = []
        registries["discovered_agent_map"].extend(extra)

    return registries


def normalize_name(name: str) -> str:
    """বাংলা: নাম নরমালাইজ করে — কেস-ইনসেনসিটিভ ম্যাচিং-এর জন্য।"""
    return re.sub(r"[_\-\s]+", "", name).lower()


def cross_reference(
    agents: list[AgentClass],
    registries: dict[str, list[RegistryEntry]],
) -> tuple[list[AgentClass], list[RegistryEntry]]:
    """বাংলা: এজেন্ট ক্লাস ও রেজিস্ট্রি এন্ট্রি ক্রস-রেফারেন্স করে।

    রিটার্ন:
        (agents_with_status, registry_ghosts)
    """
    # বাংলা: রেজিস্ট্রি থেকে নাম সেট তৈরি
    registry_names: dict[str, set[str]] = {}
    for reg_name, entries in registries.items():
        registry_names[reg_name] = {normalize_name(e.entry_name) for e in entries}

    # বাংলা: এজেন্ট নাম সেট
    agent_names = {normalize_name(a.name) for a in agents}

    # বাংলা: রেজিস্ট্রি ঘোস্ট (রেজিস্ট্রিতে আছে কিন্তু কোডে নেই)
    ghosts: list[RegistryEntry] = []
    for reg_name, entries in registries.items():
        # বাংলা: discovered_agent_map থেকে ঘোস্ট ধরা হবে না (কারণ এটি শুধু কোড রেফারেন্স)
        if reg_name == "discovered_agent_map":
            continue
        for entry in entries:
            norm = normalize_name(entry.entry_name)
            # বাংলা: এজেন্ট ক্লাসের সাথে ম্যাচ করা হচ্ছে (class name বা name_attr)
            matched = False
            for agent in agents:
                if (norm == normalize_name(agent.name)
                        or norm == normalize_name(agent.name_attr)
                        or norm in normalize_name(agent.name)):
                    matched = True
                    break
            if not matched and "agent" in norm:
                ghosts.append(entry)

    # বাংলা: প্রতিটি এজেন্টের রেজিস্ট্রেশন স্ট্যাটাস নির্ধারণ
    for agent in agents:
        matched_registries: list[str] = []
        agent_norm = normalize_name(agent.name)
        agent_attr_norm = normalize_name(agent.name_attr) if agent.name_attr else ""

        for reg_name, name_set in registry_names.items():
            if (agent_norm in name_set
                    or agent_attr_norm in name_set
                    or any(agent_norm in n or n in agent_norm for n in name_set)):
                matched_registries.append(reg_name)

        agent.registries = matched_registries

        # বাংলা: discovered_agent_map কে "আসল" রেজিস্ট্রি হিসেবে গণনা করা হবে না
        real_registries = {k: v for k, v in registries.items() if k != "discovered_agent_map"}
        real_matched = [r for r in matched_registries if r != "discovered_agent_map"]

        total_registries = len(real_registries)
        if total_registries == 0:
            # বাংলা: কোনো আসল রেজিস্ট্রি নেই — সব আনরেজিস্টার্ড
            agent.status = "UNREGISTERED"
        elif len(real_matched) == 0:
            agent.status = "UNREGISTERED"
        elif len(real_matched) < total_registries:
            agent.status = "PARTIALLY_REGISTERED"
        else:
            agent.status = "REGISTERED"

    return agents, ghosts


# ═══════════════════════════════════════════════════════════════════════════════
# বাংলা: ফ্যাগমেন্টেশন স্কোর ক্যালকুলেশন
# ═══════════════════════════════════════════════════════════════════════════════


def calculate_fragmentation_score(
    agents: list[AgentClass],
    ghosts: list[RegistryEntry],
    registries: dict[str, list[RegistryEntry]],
) -> int:
    """বাংলা: ০-১০০ স্কোর বের করে। কম স্কোর = বেশি সংগঠিত।

    স্কোরিং ফর্মুলা:
    - আনরেজিস্টার্ড এজেন্ট: প্রতিটি +৫ পয়েন্ট
    - পার্শিয়ালি রেজিস্টার্ড: প্রতিটি +৩ পয়েন্ট
    - রেজিস্ট্রি ঘোস্ট: প্রতিটি +৪ পয়েন্ট
    - ডকস্ট্রিংহীন ক্যাপাবিলিটি: প্রতিটি +১ পয়েন্ট
    - বেস পেনাল্টি: রেজিস্ট্রি সংখ্যা > ১ হলে +৫ (বিভাজন)
    """
    score = 0
    total_agents = len(agents)

    if total_agents == 0:
        return 0

    for agent in agents:
        if agent.status == "UNREGISTERED":
            score += 5
        elif agent.status == "PARTIALLY_REGISTERED":
            score += 3

        # বাংলা: ডকস্ট্রিংহীন ক্যাপাবিলিটি পেনাল্টি
        for method in agent.methods:
            if not method.has_docstring:
                score += 1

    # বাংলা: রেজিস্ট্রি ঘোস্ট পেনাল্টি
    score += len(ghosts) * 4

    # বাংলা: একাধিক র্যাপার-লেভেল রেজিস্ট্রি থাকলে বিভাজন পেনাল্টি
    # শুধুমাত্র "আসল" রেজিস্ট্রি গুনতে হবে, discovered_agent_map বাদ
    real_registries = {k: v for k, v in registries.items() if k != "discovered_agent_map"}
    if len(real_registries) > 1:
        score += 5

    # বাংলা: সর্বোচ্চ ১০০-এ ক্যাপ করা
    return min(100, score)


# ═══════════════════════════════════════════════════════════════════════════════
# বাংলা: রিপোর্ট জেনারেটর
# ═══════════════════════════════════════════════════════════════════════════════


def generate_markdown_report(
    agents: list[AgentClass],
    ghosts: list[RegistryEntry],
    registries: dict[str, list[RegistryEntry]],
    score: int,
) -> str:
    """বাংলা: মার্কডাউন ফরম্যাটে সম্পূর্ণ রিপোর্ট তৈরি করে।"""
    lines: list[str] = []

    # বাংলা: হেডার
    status_icon = "✅" if score < 20 else "⚠️" if score < 50 else "🔴"
    lines.append(f"# 🤖 SupremeAI Agent Registry Sync Report")
    lines.append(f"")
    lines.append(f"**Fragmentation Score: {score}/100** {status_icon}")
    lines.append(f"**Total Agents Found: {len(agents)}**")
    lines.append(f"**Registries Scanned: {len(registries)}**")
    lines.append("")

    # বাংলা: সামারি টেবিল
    unregistered = [a for a in agents if a.status == "UNREGISTERED"]
    partial = [a for a in agents if a.status == "PARTIALLY_REGISTERED"]
    registered = [a for a in agents if a.status == "REGISTERED"]

    lines.append("## 📊 Summary")
    lines.append("")
    lines.append("| Status | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| 🟢 REGISTERED | {len(registered)} |")
    lines.append(f"| 🟡 PARTIALLY REGISTERED | {len(partial)} |")
    lines.append(f"| 🔴 UNREGISTERED | {len(unregistered)} |")
    lines.append(f"| 🔵 REGISTRY GHOST | {len(ghosts)} |")
    lines.append("")

    # বাংলা: স্কোর ইন্টারপ্রিটেশন
    lines.append("## 📈 Fragmentation Score Interpretation")
    lines.append("")
    if score < 20:
        lines.append("> চমৎকার! এজেন্ট সিস্টেম অত্যন্ত সুসংগঠিত।")
    elif score < 40:
        lines.append("> মোটামুটি ভালো। কিছু এজেন্ট রেজিস্ট্রেশনের প্রয়োজন।")
    elif score < 60:
        lines.append("> মাঝারি ফ্যাগমেন্টেশন। উল্লেখযোগ্য সংখ্যক এজেন্ট আনরেজিস্টার্ড।")
    elif score < 80:
        lines.append("> উদ্বেগজনক ফ্যাগমেন্টেশন। অনেক এজেন্ট কেন্দ্রীয় রেজিস্ট্রিতে নেই।")
    else:
        lines.append("> গুরুতর ফ্যাগমেন্টেশন! এজেন্ট সিস্টেম চরমভাবে বিভক্ত।")
    lines.append("")

    # বাংলা: রেজিস্ট্রি তালিকা
    lines.append("## 📋 Registries Scanned")
    lines.append("")
    for reg_name, entries in registries.items():
        lines.append(f"- **{reg_name}**: {len(entries)} entries")
    lines.append("")

    # বাংলা: আনরেজিস্টার্ড এজেন্ট
    if unregistered:
        lines.append("## 🔴 UNREGISTERED Agents")
        lines.append("")
        for agent in sorted(unregistered, key=lambda a: a.name):
            lines.append(f"### `{agent.name}`")
            lines.append(f"- **File**: `{agent.file_path}:{agent.line_number}`")
            if agent.description:
                lines.append(f"- **Description**: {agent.description}")
            if agent.docstring:
                first_line = agent.docstring.split("\n")[0].strip()
                lines.append(f"- **Docstring**: {first_line}")
            if agent.decorators:
                lines.append(f"- **Decorators**: {', '.join(agent.decorators)}")
            lines.append("")

    # বাংলা: পার্শিয়ালি রেজিস্টার্ড
    if partial:
        lines.append("## 🟡 PARTIALLY REGISTERED Agents")
        lines.append("")
        for agent in sorted(partial, key=lambda a: a.name):
            lines.append(f"### `{agent.name}`")
            lines.append(f"- **File**: `{agent.file_path}:{agent.line_number}`")
            lines.append(f"- **In registries**: {', '.join(agent.registries)}")
            missing = [r for r in registries if r not in agent.registries]
            lines.append(f"- **Missing from**: {', '.join(missing)}")
            lines.append("")

    # বাংলা: রেজিস্টার্ড
    if registered:
        lines.append("## 🟢 REGISTERED Agents")
        lines.append("")
        for agent in sorted(registered, key=lambda a: a.name):
            lines.append(f"- `{agent.name}` — `{agent.file_path}`")
        lines.append("")

    # বাংলা: রেজিস্ট্রি ঘোস্ট
    if ghosts:
        lines.append("## 🔵 REGISTRY GHOSTS")
        lines.append("")
        lines.append("> এই এন্ট্রিগুলো রেজিস্ট্রিতে আছে কিন্তু কোডবেসে সম্মত ক্লাস নেই।")
        lines.append("")
        for ghost in sorted(ghosts, key=lambda g: g.entry_name):
            lines.append(
                f"- `{ghost.entry_name}` in **{ghost.registry_name}** "
                f"(`{ghost.registry_file}:{ghost.line_number}`)"
            )
        lines.append("")

    # বাংলা: ক্যাপাবিলিটি বিশ্লেষণ
    lines.append("## 🧩 Capability Analysis")
    lines.append("")
    for agent in sorted(agents, key=lambda a: a.name):
        if not agent.methods:
            continue
        lines.append(f"### `{agent.name}` Capabilities")
        lines.append("")
        lines.append("| Method | Has Docstring |")
        lines.append("|--------|---------------|")
        for method in agent.methods:
            icon = "✅" if method.has_docstring else "❌"
            lines.append(f"| `{method.name}()` | {icon} |")
        lines.append("")

    return "\n".join(lines)


def generate_json_report(
    agents: list[AgentClass],
    ghosts: list[RegistryEntry],
    registries: dict[str, list[RegistryEntry]],
    score: int,
) -> str:
    """বাংলা: JSON ফরম্যাটে রিপোর্ট তৈরি করে।"""
    report = {
        "fragmentation_score": score,
        "total_agents": len(agents),
        "total_registries": len(registries),
        "summary": {
            "registered": sum(1 for a in agents if a.status == "REGISTERED"),
            "partially_registered": sum(1 for a in agents if a.status == "PARTIALLY_REGISTERED"),
            "unregistered": sum(1 for a in agents if a.status == "UNREGISTERED"),
            "registry_ghosts": len(ghosts),
        },
        "registries": {
            name: [e.entry_name for e in entries]
            for name, entries in registries.items()
        },
        "agents": [],
        "registry_ghosts": [],
    }

    for agent in agents:
        agent_dict = {
            "name": agent.name,
            "file_path": agent.file_path,
            "line_number": agent.line_number,
            "status": agent.status,
            "registries": agent.registries,
            "description": agent.description,
            "name_attr": agent.name_attr,
            "docstring": agent.docstring[:200] if agent.docstring else "",
            "decorators": agent.decorators,
            "capabilities": [
                {
                    "name": m.name,
                    "line": m.line,
                    "has_docstring": m.has_docstring,
                    "docstring": m.docstring[:200] if m.docstring else "",
                }
                for m in agent.methods
            ],
        }
        report["agents"].append(agent_dict)

    for ghost in ghosts:
        report["registry_ghosts"].append({
            "name": ghost.entry_name,
            "registry": ghost.registry_name,
            "file": ghost.registry_file,
            "line": ghost.line_number,
        })

    return json.dumps(report, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════════
# বাংলা: ফিক্স সাজেশন জেনারেটর
# ═══════════════════════════════════════════════════════════════════════════════


def generate_fix_suggestions(
    agents: list[AgentClass],
    registries: dict[str, list[RegistryEntry]],
) -> str:
    """বাংলা: আনরেজিস্টার্ড এজেন্ট রেজিস্টার করার জন্য কোড স্নিপেট তৈরি করে।"""
    lines: list[str] = []
    unregistered = [a for a in agents if a.status == "UNREGISTERED"]

    if not unregistered:
        lines.append("# ✅ Fix Suggestions")
        lines.append("")
        lines.append("কোনো আনরেজিস্টার্ড এজেন্ট নেই — সব ঠিক আছে!")
        return "\n".join(lines)

    lines.append("# 🔧 Fix Suggestions — Register Unregistered Agents")
    lines.append("")
    lines.append(f"**Total unregistered agents: {len(unregistered)}**")
    lines.append("")

    # বাংলা: ১. JSON রেজিস্ট্রিতে যোগ করার স্নিপেট
    lines.append("## 1. Add to `backend/core/agent_registry.json`")
    lines.append("")
    lines.append("```jsonc")
    lines.append("// বাংলা: নিচের এন্ট্রিগুলো agent_registry.json-এ যোগ করুন")
    for agent in unregistered:
        desc = agent.description or agent.docstring.split("\n")[0].strip() if agent.docstring else f"{agent.name} agent"
        # বাংলা: স্ট্রিং এস্কেপ করা
        desc = desc.replace('"', "'").replace("\n", " ")[:200]
        name_attr = agent.name_attr or agent.name
        lines.append(f'  "{name_attr.lower().replace(" ", "_")}": {{')
        lines.append(f'    "agent_name": "{name_attr.lower().replace(" ", "_")}",')
        lines.append(f'    "description": "{desc}",')
        lines.append(f'    "source_class": "{agent.name}",')
        lines.append(f'    "source_file": "{agent.file_path}"')
        lines.append(f'  }},')
    lines.append("```")
    lines.append("")

    # বাংলা: ২. Skill Manifest তৈরির স্নিপেট
    lines.append("## 2. Create Skill Manifests")
    lines.append("")
    lines.append("```python")
    lines.append("# বাংলা: backend/skills/manifests/ ডিরেক্টরিতে নিচের JSON ফাইলগুলো তৈরি করুন")
    lines.append("")
    for agent in unregistered:
        desc = agent.description or agent.docstring.split("\n")[0].strip() if agent.docstring else f"{agent.name} agent"
        desc = desc.replace('"', "'").replace("\n", " ")[:200]
        manifest = {
            "id": agent.name.lower().replace(" ", "_"),
            "name": agent.name,
            "version": "0.1.0",
            "description": desc,
            "dependencies": [],
            "system_packages": [],
            "entrypoint": agent.file_path,
        }
        lines.append(f"# {agent.name}")
        lines.append(json.dumps(manifest, indent=2, ensure_ascii=False))
        lines.append("")
    lines.append("```")
    lines.append("")

    # বাংলা: ৩. ইম্পোর্ট রেজিস্ট্রেশন স্নিপেট
    lines.append("## 3. Add Registration Imports")
    lines.append("")
    lines.append("```python")
    lines.append("# বাংলা: একটি কেন্দ্রীয় agent_registry.py ফাইলে নিচের কোড যোগ করুন")
    lines.append("")
    lines.append("from typing import Any, Type")
    lines.append("")
    lines.append("")
    lines.append("# বাংলা: কেন্দ্রীয় এজেন্ট রেজিস্ট্রি — সব এজেন্ট ক্লাস এখানে রেজিস্টার করুন")
    lines.append("AGENT_CLASS_REGISTRY: dict[str, dict[str, Any]] = {")
    for agent in sorted(unregistered, key=lambda a: a.name):
        # বাংলা: মডিউল পাথ তৈরি
        module_path = agent.file_path.replace("/", ".").removesuffix(".py")
        lines.append(f'    "{agent.name}": {{')
        lines.append(f'        "module": "{module_path}",')
        lines.append(f'        "class": "{agent.name}",')
        lines.append(f'        "file": "{agent.file_path}",')
        desc = agent.description or agent.docstring.split("\n")[0].strip() if agent.docstring else ""
        if desc:
            desc = desc.replace('"', "'").replace("\n", " ")[:150]
            lines.append(f'        "description": "{desc}",')
        capabilities = [m.name for m in agent.methods]
        if capabilities:
            lines.append(f'        "capabilities": {json.dumps(capabilities)},')
        lines.append(f'    }},')
    lines.append("}")
    lines.append("")
    lines.append("")
    lines.append("def get_agent_class(agent_name: str) -> Type | None:")
    lines.append('    """বাংলা: নাম দিয়ে এজেন্ট ক্লাস খুঁজে বের করে।"""')
    lines.append('    entry = AGENT_CLASS_REGISTRY.get(agent_name)')
    lines.append('    if not entry:')
    lines.append('        return None')
    lines.append('    import importlib')
    lines.append('    module = importlib.import_module(entry["module"])')
    lines.append('    return getattr(module, entry["class"], None)')
    lines.append("")
    lines.append("")
    lines.append('def list_all_agents() -> list[str]:')
    lines.append('    """বাংলা: সব রেজিস্টার্ড এজেন্টের নাম তালিকা দেয়।"""')
    lines.append('    return list(AGENT_CLASS_REGISTRY.keys())')
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# বাংলা: মূল ফাংশন
# ═══════════════════════════════════════════════════════════════════════════════


def find_repo_root() -> Path:
    """বাংলা: রিপো রুট ডিরেক্টরি খুঁজে বের করে।"""
    # বাংলা: স্ক্রিপ্ট অবস্থান থেকে রিপো রুট নির্ধারণ
    script_dir = Path(__file__).resolve().parent
    # বাংলা: scripts/ ডিরেক্টরির প্যারেন্ট = রিপো রুট
    repo_root = script_dir.parent
    # বাংলা: ভেরিফিকেশন — backend/ আছে কিনা
    if not (repo_root / "backend").exists():
        # বাংলা: fallback — কারেন্ট ওয়ার্কিং ডিরেক্টরি চেক
        cwd = Path.cwd()
        if (cwd / "backend").exists():
            repo_root = cwd
        else:
            print("ত্রুটি: রিপো রুট খুঁজে পাওয়া যায়নি। 'backend/' ডিরেক্টরি প্রয়োজন।", file=sys.stderr)
            sys.exit(2)
    return repo_root


def main() -> int:
    """বাংলা: মূল এন্ট্রি পয়েন্ট।"""
    parser = argparse.ArgumentParser(
        description="SupremeAI Agent Capability Registry Sync — বাংলা: এজেন্ট রেজিস্ট্রি সিঙ্ক টুল",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="বাংলা: JSON ফরম্যাটে আউটপুট দেখান",
    )
    parser.add_argument(
        "--fix-suggestions",
        action="store_true",
        help="বাংলা: আনরেজিস্টার্ড এজেন্ট ঠিক করার কোড স্নিপেট দেখান",
    )
    parser.add_argument(
        "--repo-root",
        type=str,
        default=None,
        help="বাংলা: কাস্টম রিপো রুট পাথ (ডিফল্ট: অটো-ডিটেক্ট)",
    )

    args = parser.parse_args()

    try:
        # বাংলা: রিপো রুট নির্ধারণ
        repo_root = Path(args.repo_root) if args.repo_root else find_repo_root()

        # বাংলা: ধাপ ১ — সব এজেন্ট ক্লাস আবিষ্কার
        agents = discover_all_agents(repo_root)

        if not agents:
            print("কোনো Agent ক্লাস পাওয়া যায়নি।", file=sys.stderr)
            return 2

        # বাংলা: ধাপ ২ — সব রেজিস্ট্রি স্ক্যান
        registries = discover_all_registries(repo_root)

        # বাংলা: ধাপ ৩ — ক্রস-রেফারেন্স
        agents, ghosts = cross_reference(agents, registries)

        # বাংলা: ধাপ ৪ — ফ্যাগমেন্টেশন স্কোর
        score = calculate_fragmentation_score(agents, ghosts, registries)

        # বাংলা: আউটপুট
        if args.json:
            print(generate_json_report(agents, ghosts, registries, score))
        else:
            print(generate_markdown_report(agents, ghosts, registries, score))

        # বাংলা: ফিক্স সাজেশন চাইলে
        if args.fix_suggestions:
            print("\n" + "=" * 60 + "\n")
            print(generate_fix_suggestions(agents, registries))

        # বাংলা: এক্সিট কোড নির্ধারণ
        has_unregistered = any(a.status == "UNREGISTERED" for a in agents)
        return 1 if has_unregistered else 0

    except Exception as e:
        print(f"ত্রুটি: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
