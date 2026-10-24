#!/usr/bin/env python3
"""SupremeAI — Frontend ↔ Backend API Contract Diff Tool.

বাংলা: এই স্ক্রিপ্ট backend FastAPI রুট এবং frontend API কলের মধ্যে তুলনা করে
মিসম্যাচ (orphan routes, broken calls, method mismatch, param mismatch) খুঁজে বের করে।

ব্যবহার:
    python scripts/api_contract_diff.py
    python scripts/api_contract_diff.py --json
    python scripts/api_contract_diff.py --backend-only
    python scripts/api_contract_diff.py --frontend-only

লেখক: SupremeAI Architecture Team
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
# বাংলা: রিপোজিটরির রুট ডিরেক্টরি নির্ধারণ — এই স্ক্রিপ্ট যেখান থেকেই চালানো হোক না কেন
# সবসময় সঠিক পাথ পাবে।
# ──────────────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
FRONTEND_SRC_DIR = ROOT / "frontend" / "src"
ROUTERS_FILE = BACKEND_DIR / "api" / "routers.py"
ROUTES_DIR = BACKEND_DIR / "api" / "routes"

# ──────────────────────────────────────────────────────────────────────────────
# বাংলা: সাপোর্টেড HTTP মেথড — FastAPI ডেকোরেটর এবং frontend কল উভয় ক্ষেত্রে
# এই ৫টি মেথড ট্র্যাক করা হয়।
# ──────────────────────────────────────────────────────────────────────────────
HTTP_METHODS = {"get", "post", "put", "delete", "patch"}

# বাংলা: ফ্রন্টএন্ড স্ক্যান করার সময় এই প্রিফিক্সগুলো এড়িয়ে যাওয়া হবে (Firebase internal path ইত্যাদি)
SKIP_FRONTEND_PREFIXES = ("/__/",)

# বাংলা: টেস্ট ফাইল স্ক্যান করা হবে না
TEST_SUFFIXES = (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")

# বাংলা: routes/ ফোল্ডারের বাইরেও রাউটার থাকতে পারে (যেমন tools/, api/v1/)
EXTRA_ROUTER_PATTERNS: list[str] = []  # routers.py থেকে dynamically পূরণ হবে


# ══════════════════════════════════════════════════════════════════════════════
# বাংলা: ডাটা ক্লাস — ব্যাকএন্ড রুট তথ্য ধারণ করে
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class BackendRoute:
    """বাংলা: একটি ব্যাকএন্ড API রুটের সম্পূর্ণ তথ্য।"""
    method: str                          # GET, POST, PUT, DELETE, PATCH
    path: str                            # পূর্ণ URL path (prefix + route path)
    normalized: str                      # নরমালাইজড path (param → {PARAM})
    response_model: str | None           # response_model ক্লাসের নাম
    request_body: str | None             # Pydantic request body মডেলের নাম
    path_params: list[str]               # path parameter নামের তালিকা
    source_file: str                     # কোন ফাইলে রুটটি আছে
    source_line: int                     # লাইন নম্বর
    router_prefix: str                   # APIRouter prefix
    registration_prefix: str             # routers.py এ register করার সময়কার prefix
    raw_decorator_line: str              # মূল ডেকোরেটর লাইন (debugging এর জন্য)


# ══════════════════════════════════════════════════════════════════════════════
# বাংলা: ডাটা ক্লাস — ফ্রন্টএন্ড API কল তথ্য ধারণ করে
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class FrontendCall:
    """বাংলা: ফ্রন্টএন্ড থেকে করা একটি API কলের তথ্য।"""
    method: str                          # GET, POST, PUT, DELETE, PATCH
    path: str                            # API path (base URL stripped)
    normalized: str                      # নরমালাইজড path
    path_params: list[str]               # path parameter নামের তালিকা
    source_file: str                     # কোন ফাইলে কলটি আছে
    source_line: int                     # লাইন নম্বর
    call_pattern: str                    # fetch / apiClient / apiCircuit.execute
    raw_line: str                        # মূল কোড লাইন (debugging এর জন্য)


# ══════════════════════════════════════════════════════════════════════════════
# বাংলা: ডাটা ক্লাস — তুলনার ফলাফল ধারণ করে
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class DiffResult:
    """বাংলা: সম্পূর্ণ diff রিপোর্ট — সব ধরনের মিসম্যাচ এখানে জমা হয়।"""
    backend_routes: list[dict] = field(default_factory=list)
    frontend_calls: list[dict] = field(default_factory=list)
    orphan_backend: list[dict] = field(default_factory=list)
    broken_frontend: list[dict] = field(default_factory=list)
    method_mismatches: list[dict] = field(default_factory=list)
    param_mismatches: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════════════════
# বাংলা: Path নরমালাইজেশন — {id}, :id, {param} সব {PARAM} হিসেবে রূপান্তর
# ══════════════════════════════════════════════════════════════════════════════
def normalize_path(p: str) -> str:
    """বাংলা: Path নরমালাইজ — trailing slash কাটা, path param একীভূত করা।"""
    # বাংলা: query string আলাদা করা
    p = p.split("?")[0]
    # বাংলা: FastAPI style {param} কে {PARAM} করা
    p = re.sub(r"\{[^}/]+(:[^}]*)?\}", "{PARAM}", p)
    # বাংলা: Express/colon style :param কে {PARAM} করা
    p = re.sub(r":([A-Za-z_][A-Za-z0-9_]*)(?=/|$)", "{PARAM}", p)
    # বাংলা: trailing slash কাটা (root path ব্যতিত)
    p = p.rstrip("/") or "/"
    return p


def extract_path_params(p: str) -> list[str]:
    """বাংলা: Path থেকে parameter নাম বের করা।"""
    params = []
    # FastAPI style: {param} or {param:type}
    for m in re.finditer(r"\{([^}/:}]+)", p):
        params.append(m.group(1))
    # Express style: :param
    for m in re.finditer(r":([A-Za-z_][A-Za-z0-9_]*)(?=/|$)", p):
        params.append(m.group(1))
    return params


def path_to_regex_pattern(p: str) -> re.Pattern[str]:
    """বাংলা: নরমালাইজড path থেকে regex বানানো — {PARAM} → [^/]+ রূপান্তর।"""
    escaped = re.escape(p)
    escaped = escaped.replace(r"\{PARAM\}", r"[^/]+")
    return re.compile("^" + escaped + r"(?:/.*)?$")


# ══════════════════════════════════════════════════════════════════════════════
# বাংলা: routers.py পার্সিং — কোন রাউটার মডিউল কোন prefix-এ register হয়েছে
# ══════════════════════════════════════════════════════════════════════════════
def parse_routers_registry() -> list[dict[str, str]]:
    """বাংলা: ALL_ROUTERS তালিকা থেকে (module_path, prefix) জোড়া বের করা।

    রিটার্ন: [{"path": "api.routes.auth", "prefix": "/api/v1"}, ...]
    """
    if not ROUTERS_FILE.exists():
        print(f"WARNING: রাউটার রেজিস্ট্রি ফাইল পাওয়া যায়নি: {ROUTERS_FILE}", file=sys.stderr)
        return []

    text = ROUTERS_FILE.read_text(encoding="utf-8", errors="ignore")

    # বাংলা: AST দিয়ে ALL_ROUTERS লিস্টের ডিকশনারিগুলো পার্স করি
    try:
        tree = ast.parse(text, filename=str(ROUTERS_FILE))
    except SyntaxError:
        # বাংলা: AST parse ব্যর্থ হলে regex fallback ব্যবহার করি
        pattern = re.compile(r'"path":\s*"([^"]+)",\s*"prefix":\s*"([^"]*)"')
        return [{"path": m.group(1), "prefix": m.group(2)} for m in pattern.finditer(text)]

    routers: list[dict[str, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "ALL_ROUTERS":
                    # বাংলা: ALL_ROUTERS হলো List[Dict] — প্রতিটি dict থেকে path ও prefix নিই
                    if isinstance(node.value, ast.List):
                        for item in node.value.elts:
                            if isinstance(item, ast.Dict):
                                entry: dict[str, str] = {}
                                for k, v in zip(item.keys, item.values):
                                    if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                                        entry[k.value] = v.value
                                if "path" in entry:
                                    routers.append(entry)

    # বাংলা: register_all_routers() ফাংশনে থাকা অতিরিক্ত register_router কলও স্ক্যান করি
    # (যেমন BYOC conditional router)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "register_router":
                args = node.args
                if len(args) >= 2:
                    if isinstance(args[0], ast.Constant) and isinstance(args[1], ast.Constant):
                        routers.append({
                            "path": args[0].value,
                            "prefix": args[1].value,
                        })

    return routers


def resolve_module_to_file(module_path: str) -> Path | None:
    """বাংলা: Dotted module path (যেমন 'api.routes.auth') থেকে ফাইল পাথ বের করা।"""
    relative = module_path.replace(".", os.sep) + ".py"
    candidate = BACKEND_DIR / relative
    if candidate.exists():
        return candidate
    return None


# ══════════════════════════════════════════════════════════════════════════════
# বাংলা: AST দিয়ে Backend রুট পার্সিং — FastAPI ডেকোরেটর, response_model, body
# ══════════════════════════════════════════════════════════════════════════════
class RouteASTVisitor(ast.NodeVisitor):
    """বাংলা: AST visitor যা FastAPI router decorator থেকে রুট তথ্য বের করে।"""

    def __init__(self, source_file: str, router_prefix: str = "", reg_prefix: str = ""):
        self.source_file = source_file
        self.router_prefix = router_prefix
        self.reg_prefix = reg_prefix
        self.routes: list[BackendRoute] = []
        self._decorator_lines: dict[int, str] = {}  # line_no → decorator text

    def _get_text_range(self, node: ast.AST) -> str | None:
        """বাংলা: AST node এর source text পড়া (line numbers ব্যবহার করে)।"""
        try:
            with open(self.source_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            start = getattr(node, "lineno", 0) - 1
            end = getattr(node, "end_lineno", start + 1)
            return "".join(lines[start:end]).strip()
        except Exception:
            return None

    def _extract_decorator_info(self, func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """বাংলা: ফাংশনের ডেকোরেটর থেকে method, path, response_model বের করা।"""
        for deco in func_node.decorator_list:
            method = None
            route_path = None
            response_model_name = None

            # বাংলা: @router.get("/path", response_model=SomeModel)
            # বাংলা: @router.post("/path")
            # বাংলা: @app.get("/path", ...)
            if isinstance(deco, ast.Call):
                func = deco.func
                # বাংলা: router.get / router.post / app.get ইত্যাদি
                if isinstance(func, ast.Attribute) and func.attr in HTTP_METHODS:
                    method = func.attr.upper()

                # বাংলা: path হলো প্রথম positional argument
                if deco.args and isinstance(deco.args[0], ast.Constant):
                    route_path = deco.args[0].value

                # বাংলা: keyword arguments থেকে response_model খোঁজা
                for kw in deco.keywords:
                    if kw.arg == "response_model":
                        response_model_name = self._extract_model_name(kw.value)

            # FIX: empty-string paths (e.g. @router.get("") with a router prefix) are
            # valid FastAPI registrations — truthiness here silently dropped them,
            # flagging their real frontend consumers as method mismatches.
            if method and route_path is not None:
                # বাংলা: পূর্ণ path তৈরি — registration prefix + router prefix + route path
                full_path = self._combine_path(self.reg_prefix, self.router_prefix, route_path)
                normalized = normalize_path(full_path)
                path_params = extract_path_params(full_path)

                # বাংলা: request body model — ফাংশনের parameter থেকে Pydantic model খোঁজা
                request_body = self._extract_request_body(func_node)

                raw_line = self._get_text_range(deco) or ""

                self.routes.append(BackendRoute(
                    method=method,
                    path=full_path,
                    normalized=normalized,
                    response_model=response_model_name,
                    request_body=request_body,
                    path_params=path_params,
                    source_file=self.source_file,
                    source_line=getattr(deco, "lineno", 0),
                    router_prefix=self.router_prefix,
                    registration_prefix=self.reg_prefix,
                    raw_decorator_line=raw_line,
                ))

    def _extract_model_name(self, node: ast.AST) -> str | None:
        """বাংলা: AST node থেকে model ক্লাসের নাম বের করা।

        উদাহরণ:
          - TokenResponse → "TokenResponse"
          - list[ConversationResponse] → "list[ConversationResponse]"
        """
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Subscript):
            # বাংলা: list[Model], dict[str, Model] ইত্যাদি
            container = self._extract_model_name(node.value)
            element = self._extract_model_name(node.slice)
            if container and element:
                return f"{container}[{element}]"
            return container or element
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Constant):
            return str(node.value)
        return None

    def _extract_request_body(self, func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
        """বাংলা: ফাংশনের parameter থেকে Pydantic request body model খোঁজা।

        Pydantic body parameter চেনার উপায়:
          ১. Type annotation যদি কোনো ক্লাসের নাম হয় (BaseModel subclass)
          ২. Parameter এর নাম body, payload, request_body ইত্যাদি হলে
          ৩. Depends() আর Query() বাদ দেওয়া হয়
        """
        body_param_names = {"body", "payload", "request_body", "data", "item", "dto", "model"}

        for arg in func_node.args.args:
            # বাংলা: self, cls, request, db বাদ দেওয়া
            if arg.arg in ("self", "cls", "request", "req"):
                continue

            # বাংলা: annotation থেকে টাইপ নাম বের করা
            if arg.annotation:
                type_name = self._extract_model_name(arg.annotation)
                if type_name:
                    # বাংলা: Depends() বা Request বাদ দেওয়া
                    if type_name in ("Depends", "Request", "HTTPException", "str",
                                     "int", "float", "bool", "dict", "list",
                                     "None", "Response"):
                        continue
                    # বাংলা: যদি annotation-এ Depends থাকে তাহলে বাদ
                    if isinstance(arg.annotation, ast.Call):
                        if isinstance(arg.annotation.func, ast.Name) and arg.annotation.func.id == "Depends":
                            continue
                    # বাংলা: path parameter না — query parameter ও বাদ দেওয়া হবে না কারণ
                    # সেগুলো body নয়
                    if arg.arg in body_param_names or not self._is_path_or_query_param(arg):
                        return type_name

            # বাংলা: নাম দিয়ে চেনা — body, payload ইত্যাদি
            if arg.arg in body_param_names and arg.annotation:
                type_name = self._extract_model_name(arg.annotation)
                if type_name and type_name not in ("Depends", "Request"):
                    return type_name

        return None

    def _is_path_or_query_param(self, arg: ast.arg) -> bool:
        """বাংলা: চেক করা parameter টি path/query param কি না।"""
        if arg.annotation is None:
            return False
        # বাংলা: Query(...), Path(...) annotation চেক
        if isinstance(arg.annotation, ast.Call):
            if isinstance(arg.annotation.func, ast.Name):
                if arg.annotation.func.id in ("Query", "Path", "Header", "Cookie",
                                               "Form", "File", "UploadFile"):
                    return True
        # বাংলা: simple type annotation (str, int, bool) path param হতে পারে
        if isinstance(arg.annotation, ast.Name):
            if arg.annotation.id in ("str", "int", "float", "bool"):
                return True
        # বাংলা: str | None style
        if isinstance(arg.annotation, ast.BinOp) and isinstance(arg.annotation.op, ast.BitOr):
            return True
        return False

    def _combine_path(self, *parts: str) -> str:
        """বাংলা: একাধিক path segment কে একটি পূর্ণ path হিসেবে যুক্ত করা।"""
        result = ""
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if result and not result.endswith("/") and not part.startswith("/"):
                result += "/"
            # বাংলা: double slash এড়ানো
            if result.endswith("/") and part.startswith("/"):
                part = part[1:]
            result += part
        return result or "/"

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """বাংলা: async def ফাংশনের ডেকোরেটর চেক করা।"""
        self._extract_decorator_info(node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """বাংলা: সাধারণ def ফাংশনের ডেকোরেটর চেক করা।"""
        self._extract_decorator_info(node)
        self.generic_visit(node)


def parse_backend_routes(
    registry: list[dict[str, str]] | None = None,
) -> list[BackendRoute]:
    """বাংলা: সমস্ত ব্যাকএন্ড রুট পার্স করা — routers.py রেজিস্ট্রি + AST parsing।

    ১. routers.py থেকে registered router তালিকা পড়া
    ২. প্রতিটি router module-এর ফাইল AST parse করা
    ৩. FastAPI decorator থেকে route info বের করা
    ৪. Registration prefix + Router prefix + Route path মিলিয়ে পূর্ণ path তৈরি
    """
    if registry is None:
        registry = parse_routers_registry()

    routes: list[BackendRoute] = []
    seen_files: set[str] = set()

    for entry in registry:
        module_path = entry.get("path", "")
        reg_prefix = entry.get("prefix", "")

        # বাংলা: module path থেকে ফাইল পাথ বের করা
        mod_file = resolve_module_to_file(module_path)
        if mod_file is None:
            continue

        if str(mod_file) in seen_files:
            continue
        seen_files.add(str(mod_file))

        try:
            text = mod_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        # বাংলা: AST parse করে router variable খোঁজা — APIRouter(prefix="...")
        router_prefix = ""
        try:
            tree = ast.parse(text, filename=str(mod_file))
        except SyntaxError:
            # বাংলা: syntax error থাকলে regex fallback দিয়ে prefix বের করি
            prefix_match = re.search(r'APIRouter\(.*?prefix\s*=\s*["\']([^"\']+)["\']', text, re.DOTALL)
            if prefix_match:
                router_prefix = prefix_match.group(1)
            tree = None

        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "router":
                            if isinstance(node.value, ast.Call):
                                for kw in node.value.keywords:
                                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                                        router_prefix = kw.value.value

        # বাংলা: RouteASTVisitor দিয়ে সব route বের করা
        visitor = RouteASTVisitor(
            source_file=str(mod_file),
            router_prefix=router_prefix,
            reg_prefix=reg_prefix,
        )
        if tree is not None:
            visitor.visit(tree)
        else:
            # বাংলা: AST parse ব্যর্থ হলে regex fallback
            fallback_routes = _regex_fallback_routes(text, str(mod_file), router_prefix, reg_prefix)
            routes.extend(fallback_routes)
            continue

        routes.extend(visitor.routes)

    return routes


def _regex_fallback_routes(
    text: str,
    source_file: str,
    router_prefix: str,
    reg_prefix: str,
) -> list[BackendRoute]:
    """বাংলা: AST parse ব্যর্থ হলে regex দিয়ে route বের করা (fallback)।"""
    routes: list[BackendRoute] = []
    lines = text.splitlines()

    # বাংলা: @router.get("/path", ...) / @app.post("/path", ...) প্যাটার্ন
    pattern = re.compile(
        r'@(\w+)\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']'
    )

    for i, line in enumerate(lines, 1):
        m = pattern.search(line)
        if m:
            method = m.group(2).upper()
            route_path = m.group(3)
            full_path = _combine_path_simple(reg_prefix, router_prefix, route_path)
            routes.append(BackendRoute(
                method=method,
                path=full_path,
                normalized=normalize_path(full_path),
                response_model=None,
                request_body=None,
                path_params=extract_path_params(full_path),
                source_file=source_file,
                source_line=i,
                router_prefix=router_prefix,
                registration_prefix=reg_prefix,
                raw_decorator_line=line.strip(),
            ))

    return routes


def _combine_path_simple(*parts: str) -> str:
    """বাংলা: সহজ path combination — double slash এড়িয়ে।"""
    result = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if result and not result.endswith("/") and not part.startswith("/"):
            result += "/"
        if result.endswith("/") and part.startswith("/"):
            part = part[1:]
        result += part
    return result or "/"


# ══════════════════════════════════════════════════════════════════════════════
# বাংলা: Regex দিয়ে Frontend API কল পার্সিং
# ══════════════════════════════════════════════════════════════════════════════

# বাংলা: fetch() কল প্যাটার্ন — template literal এবং string literal দুটোই handle করা হয়
# উদাহরণ: fetch(`${getApiBaseUrl()}/api/v1/auth/login`, { method: 'POST' })
# উদাহরণ: fetch('/api/v1/conversations', { ... })
FETCH_PATTERN = re.compile(
    r'fetch\(\s*[\x60"\x27]([^\x60"\x27]+)',
)

# বাংলা: apiClient.get/post/put/delete কল প্যাটার্ন
# উদাহরণ: apiClient.get('/api/v1/agents')
# উদাহরণ: apiClient.post<AgentTask>('/api/v1/agents/execute', { ... })
# বাংলা: TypeScript generic (e.g. <AgentTask>) মেথড ও parenthesis এর মাঝে থাকতে পারে
APICLIENT_PATTERN = re.compile(
    r'apiClient\.(get|post|put|delete)(?:<[^>]*>)?\s*\(\s*[\x60"\x27]([^\x60"\x27]+)',
)

# বাংলা: apiCircuit.execute(() => fetch(...)) প্যাটার্ন — inner fetch থেকে URL নেওয়া হয়
APICIRCUIT_PATTERN = re.compile(
    r'apiCircuit\.execute\s*\(\s*.*?fetch\s*\(\s*[\x60"\x27]([^\x60"\x27]+)',
    re.DOTALL,
)

# বাংলা: fetchWithRetry কল — এটিও fetch এর মতোই কাজ করে
FETCHRETRY_PATTERN = re.compile(
    r'fetchWithRetry\s*\(\s*[\x60"\x27]([^\x60"\x27]+)',
)

# বাংলা: sendTelemetry কল — method parameter আলাদাভাবে handle করতে হবে
TELEMETRY_PATTERN = re.compile(
    r'sendTelemetry\s*\(\s*[\x60"\x27]([^\x60"\x27]+)',
)

# বাংলা: URL থেকে base URL স্ট্রিপ করার প্যাটার্ন
# getApiBaseUrl(), API_BASE, BACKEND_URL, VITE_API_BASE, VITE_API_URL ইত্যাদি
BASE_URL_PATTERNS = [
    re.compile(r'\$\{\s*getApiBaseUrl\s*\(\)\s*\}'),
    re.compile(r'\$\{\s*API_BASE\s*\}'),
    re.compile(r'\$\{\s*BACKEND_URL\s*\}'),
    re.compile(r'\$\{\s*VITE_API_BASE\s*\}'),
    re.compile(r'\$\{\s*VITE_API_URL\s*\}'),
    re.compile(r'\$\{\s*ADMIN_BACKEND_URL\s*\}'),
    re.compile(r'\$\{\s*USER_BACKEND_URL\s*\}'),
    re.compile(r'\$\{\s*import\.meta\.env\.[A-Z_]+\s*\}'),
    re.compile(r'getApiBaseUrl\(\)\s*\+'),
]


def strip_base_url(url: str) -> str:
    """বাংলা: URL থেকে base URL / env variable / function call স্ট্রিপ করা।"""
    cleaned = url.strip()
    for pat in BASE_URL_PATTERNS:
        cleaned = pat.sub("", cleaned)
    # বাংলা: বাকি থাকা template expression স্ট্রিপ
    # CI FIX: previously this stripped ${...} entirely → URL became
    # /admin-api/backups//restore (double slash). Now replace ${...} with
    # {PARAM} so the path stays parseable AND matches FastAPI route templates
    # like /admin-api/backups/{backup_id}/restore (which backend normalizes
    # to {PARAM} via normalize_path()).
    cleaned = re.sub(r'\$\{[^}]*\}', "{PARAM}", cleaned)
    # বাংলা: leading/trailing + operator ও whitespace সরানো
    cleaned = re.sub(r'^\s*\+\s*', "", cleaned)
    cleaned = re.sub(r'\s*\+\s*$', "", cleaned)
    cleaned = cleaned.strip()
    # CI FIX: collapse multiple slashes introduced by empty ${} (rare) —
    # e.g. /admin-api/backups//restore → /admin-api/backups/restore
    # But only collapse runs of 2+ slashes, not the leading // of protocol.
    cleaned = re.sub(r'(?<!:)//+', '/', cleaned)
    return cleaned


def parse_frontend_calls() -> list[FrontendCall]:
    """বাংলা: সমস্ত frontend API কল পার্স করা।

    .ts এবং .tsx ফাইল স্ক্যান করে:
    ১. fetch() কল — method object থেকে HTTP method নির্ধারণ
    ২. apiClient.get/post/put/delete — method name থেকে HTTP method
    ৩. apiCircuit.execute — inner fetch থেকে URL
    ৪. fetchWithRetry — fetch এর মতোই
    ৫. sendTelemetry — default POST, GET parameter সাপোর্ট
    """
    calls: list[FrontendCall] = []
    seen: set[tuple[str, str, str]] = set()  # (method, normalized_path, source_file)

    if not FRONTEND_SRC_DIR.exists():
        print(f"WARNING: Frontend src ডিরেক্টরি পাওয়া যায়নি: {FRONTEND_SRC_DIR}", file=sys.stderr)
        return calls

    ts_files: list[Path] = []
    for ext in ("*.ts", "*.tsx"):
        for f in FRONTEND_SRC_DIR.rglob(ext):
            # বাংলা: node_modules এবং test ফাইল বাদ দেওয়া
            if "node_modules" in f.parts:
                continue
            if any(f.name.endswith(s) for s in TEST_SUFFIXES):
                continue
            ts_files.append(f)

    for ts_file in ts_files:
        try:
            text = ts_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        lines = text.splitlines()
        file_key = str(ts_file.relative_to(ROOT))

        for line_no, line in enumerate(lines, 1):
            # বাংলা: apiClient.get/post/put/delete প্যাটার্ন
            for m in APICLIENT_PATTERN.finditer(line):
                method = m.group(1).upper()
                raw_url = m.group(2)
                path = strip_base_url(raw_url)
                if not path or not path.startswith("/"):
                    continue
                if any(path.startswith(p) for p in SKIP_FRONTEND_PREFIXES):
                    continue
                if "${" in path and "/" not in path.replace("${", ""):
                    continue  # বাংলা: সম্পূর্ণ dynamic path — skip
                normalized = normalize_path(path)
                key = (method, normalized, file_key)
                if key not in seen:
                    seen.add(key)
                    calls.append(FrontendCall(
                        method=method,
                        path=path,
                        normalized=normalized,
                        path_params=extract_path_params(path),
                        source_file=file_key,
                        source_line=line_no,
                        call_pattern="apiClient",
                        raw_line=line.strip()[:200],
                    ))

            # বাংলা: fetch() কল প্যাটার্ন
            for m in FETCH_PATTERN.finditer(line):
                raw_url = m.group(1)
                path = strip_base_url(raw_url)
                if not path or not path.startswith("/"):
                    continue
                if any(path.startswith(p) for p in SKIP_FRONTEND_PREFIXES):
                    continue
                # বাংলা: fetch কলে method নির্ধারণ — ঐচ্ছিক options object থেকে
                method = _detect_fetch_method(line, line_no, lines)
                normalized = normalize_path(path)
                key = (method, normalized, file_key)
                if key not in seen:
                    seen.add(key)
                    calls.append(FrontendCall(
                        method=method,
                        path=path,
                        normalized=normalized,
                        path_params=extract_path_params(path),
                        source_file=file_key,
                        source_line=line_no,
                        call_pattern="fetch",
                        raw_line=line.strip()[:200],
                    ))

            # বাংলা: fetchWithRetry কল
            for m in FETCHRETRY_PATTERN.finditer(line):
                raw_url = m.group(1)
                path = strip_base_url(raw_url)
                if not path or not path.startswith("/"):
                    continue
                method = _detect_fetch_method(line, line_no, lines)
                normalized = normalize_path(path)
                key = (method, normalized, file_key)
                if key not in seen:
                    seen.add(key)
                    calls.append(FrontendCall(
                        method=method,
                        path=path,
                        normalized=normalized,
                        path_params=extract_path_params(path),
                        source_file=file_key,
                        source_line=line_no,
                        call_pattern="fetchWithRetry",
                        raw_line=line.strip()[:200],
                    ))

            # বাংলা: sendTelemetry কল
            for m in TELEMETRY_PATTERN.finditer(line):
                raw_url = m.group(1)
                path = strip_base_url(raw_url)
                if not path or not path.startswith("/"):
                    continue
                # বাংলা: sendTelemetry default method POST
                method = "POST"
                # বাংলা: কিন্তু third argument হিসেবে GET পাস করতে পারে
                # sendTelemetry('/path', body, 'GET')
                get_match = re.search(r"sendTelemetry\s*\([^)]*['\"]GET['\"]", line)
                if get_match:
                    method = "GET"
                normalized = normalize_path(path)
                key = (method, normalized, file_key)
                if key not in seen:
                    seen.add(key)
                    calls.append(FrontendCall(
                        method=method,
                        path=path,
                        normalized=normalized,
                        path_params=extract_path_params(path),
                        source_file=file_key,
                        source_line=line_no,
                        call_pattern="sendTelemetry",
                        raw_line=line.strip()[:200],
                    ))

    return calls


def _detect_fetch_method(line: str, line_no: int, lines: list[str]) -> str:
    """বাংলা: fetch কলের method নির্ধারণ — multi-line object স্ক্যান করা।

    ১. ঐচ্ছিক second argument (options object) এ method property খোঁজা
    ২. Default: GET (body না থাকলে)
    ৩. POST/PUT/PATCH যদি body property থাকে
    """
    # বাংলা: বর্তমান লাইনে method property আছে কি না
    method_match = re.search(r"method\s*:\s*['\"]?(GET|POST|PUT|DELETE|PATCH)['\"]?", line, re.IGNORECASE)
    if method_match:
        return method_match.group(1).upper()

    # বাংলা: পরবর্তী কয়েক লাইনে method property খোঁজা (multi-line options)
    context = "\n".join(lines[line_no:min(line_no + 10, len(lines))])
    method_match = re.search(r"method\s*:\s*['\"]?(GET|POST|PUT|DELETE|PATCH)['\"]?", context, re.IGNORECASE)
    if method_match:
        return method_match.group(1).upper()

    # বাংলা: body property আছে কি না — থাকলে POST
    body_match = re.search(r"body\s*:", context)
    if body_match:
        return "POST"

    # বাংলা: JSON.stringify আছে কি না — থাকলে POST
    # FIX (run 36059590695): খালি `"json()" in context` heuristic টি বাদ —
    # GET handler-এর `await res.json()` (RESPONSE parse) কেও POST ভেবে
    # false-positive method-mismatch হতো (প্রমাণ: MeshAgentsPanel.tsx:85 —
    # fetch-এ কোনো method নেই, কিন্তু response-এর .json() দেখে POST ধরেছিল)।
    # Request body বোঝাতে `body:` ও `JSON.stringify` যথেষ্ট।
    if "JSON.stringify" in context:
        return "POST"

    return "GET"


# ══════════════════════════════════════════════════════════════════════════════
# বাংলা: তুলনা (Comparison) লজিক — ব্যাকএন্ড vs ফ্রন্টএন্ড
# ══════════════════════════════════════════════════════════════════════════════
def compare_routes(
    backend_routes: list[BackendRoute],
    frontend_calls: list[FrontendCall],
) -> DiffResult:
    """বাংলা: ব্যাকএন্ড রুট এবং ফ্রন্টএন্ড কলের মধ্যে তুলনা করা।

    ৪ ধরনের মিসম্যাচ খোঁজা হয়:
    ১. Orphan backend routes — ব্যাকএন্ডে আছে কিন্তু ফ্রন্টএন্ড থেকে কল হয় না
    ২. Broken frontend calls — ফ্রন্টএন্ড কল করে কিন্তু ব্যাকএন্ডে রুট নেই
    ৩. Method mismatches — একই path কিন্তু ভিন্ন HTTP method
    ৪. Param mismatches — প্যারামিটার সংখ্যা বা নামে তারতম্য
    """
    result = DiffResult()

    # বাংলা: ব্যাকএন্ড রুট তথ্য serializable format এ রূপান্তর
    result.backend_routes = [
        {
            "method": r.method,
            "path": r.path,
            "normalized": r.normalized,
            "response_model": r.response_model,
            "request_body": r.request_body,
            "path_params": r.path_params,
            "source_file": r.source_file,
            "source_line": r.source_line,
        }
        for r in backend_routes
    ]

    # বাংলা: ফ্রন্টএন্ড কল তথ্য serializable format এ রূপান্তর
    result.frontend_calls = [
        {
            "method": c.method,
            "path": c.path,
            "normalized": c.normalized,
            "path_params": c.path_params,
            "source_file": c.source_file,
            "source_line": c.source_line,
            "call_pattern": c.call_pattern,
        }
        for c in frontend_calls
    ]

    # ──────────────────────────────────────────────────────────────────────────
    # বাংলা: ফ্রন্টএন্ড কলের indexed structure তৈরি — দ্রুত lookup এর জন্য
    # ──────────────────────────────────────────────────────────────────────────
    # frontend_lookup[normalized_path][method] = [FrontendCall, ...]
    frontend_lookup: dict[str, dict[str, list[FrontendCall]]] = defaultdict(lambda: defaultdict(list))
    for call in frontend_calls:
        frontend_lookup[call.normalized][call.method].append(call)

    # backend_lookup[normalized_path][method] = [BackendRoute, ...]
    backend_lookup: dict[str, dict[str, list[BackendRoute]]] = defaultdict(lambda: defaultdict(list))
    for route in backend_routes:
        backend_lookup[route.normalized][route.method].append(route)

    # বাংলা: সব normalized path এর সেট
    all_backend_paths: set[str] = set(backend_lookup.keys())
    all_frontend_paths: set[str] = set(frontend_lookup.keys())

    # ──────────────────────────────────────────────────────────────────────────
    # বাংলা: ১. Orphan Backend Routes — ব্যাকএন্ডে আছে, ফ্রন্টএন্ডে কল নেই
    # ──────────────────────────────────────────────────────────────────────────
    # বাংলা: regex pattern তৈরি করে prefix match চেক করা হয়
    # (যেমন /api/files/{PARAM} এর সাথে /api/files/src/main.ts match করবে)
    backend_regexes = [(p, path_to_regex_pattern(p)) for p in all_backend_paths]
    matched_backend_paths: set[str] = set()

    for fe_path in all_frontend_paths:
        for be_path, rx in backend_regexes:
            if rx.match(fe_path):
                matched_backend_paths.add(be_path)

    for route in backend_routes:
        if route.normalized not in all_frontend_paths and route.normalized not in matched_backend_paths:
            # বাংলা: আবারও regex check — হয়তো prefix match হয়
            is_matched = False
            for fe_path in all_frontend_paths:
                be_rx = path_to_regex_pattern(route.normalized)
                if be_rx.match(fe_path):
                    is_matched = True
                    break
            if not is_matched:
                result.orphan_backend.append({
                    "method": route.method,
                    "path": route.path,
                    "normalized": route.normalized,
                    "response_model": route.response_model,
                    "source_file": route.source_file,
                    "source_line": route.source_line,
                })

    # ──────────────────────────────────────────────────────────────────────────
    # বাংলা: ২. Broken Frontend Calls — ফ্রন্টএন্ড কল করে, ব্যাকএন্ডে নেই
    # ──────────────────────────────────────────────────────────────────────────
    for call in frontend_calls:
        found = False
        # বাংলা: প্রথমে exact match চেক
        if call.normalized in all_backend_paths:
            found = True
        else:
            # বাংলা: তারপর regex prefix match চেক
            for be_path, rx in backend_regexes:
                if rx.fullmatch(call.normalized) or rx.match(call.normalized):
                    found = True
                    break

        if not found:
            result.broken_frontend.append({
                "method": call.method,
                "path": call.path,
                "normalized": call.normalized,
                "source_file": call.source_file,
                "source_line": call.source_line,
                "call_pattern": call.call_pattern,
                "raw_line": call.raw_line,
            })

    # ──────────────────────────────────────────────────────────────────────────
    # বাংলা: ৩. Method Mismatches — একই path কিন্তু ভিন্ন HTTP method
    # ──────────────────────────────────────────────────────────────────────────
    # বাংলা: ফ্রন্টএন্ড কল যেগুলো exact বা regex match পেয়েছে কিন্তু method আলাদা
    for call in frontend_calls:
        matched_backends: list[BackendRoute] = []

        # বাংলা: Exact match
        if call.normalized in backend_lookup:
            for be_routes in backend_lookup[call.normalized].values():
                matched_backends.extend(be_routes)

        # বাংলা: Regex match
        if not matched_backends:
            for be_path, rx in backend_regexes:
                if rx.match(call.normalized):
                    for be_routes in backend_lookup[be_path].values():
                        matched_backends.extend(be_routes)
                    break

        # বাংলা: কোনো backend route match পায়নি — ইতিমধ্যে broken-এ আছে
        if not matched_backends:
            continue

        # বাংলা: একই method আছে কি না চেক
        has_matching_method = any(
            be.method == call.method for be in matched_backends
        )
        if not has_matching_method:
            be_methods = sorted(set(be.method for be in matched_backends))
            result.method_mismatches.append({
                "frontend_method": call.method,
                "backend_methods": be_methods,
                "path": call.path,
                "normalized": call.normalized,
                "source_file": call.source_file,
                "source_line": call.source_line,
                "call_pattern": call.call_pattern,
            })

    # ──────────────────────────────────────────────────────────────────────────
    # বাংলা: ৪. Path Parameter Mismatches — প্যারামিটার সংখ্যায় তারতম্য
    # ──────────────────────────────────────────────────────────────────────────
    for call in frontend_calls:
        matched_be: BackendRoute | None = None

        # বাংলা: Exact method + path match
        if call.normalized in backend_lookup and call.method in backend_lookup[call.normalized]:
            matched_be = backend_lookup[call.normalized][call.method][0]
        else:
            # বাংলা: Regex match
            for be_path, rx in backend_regexes:
                if rx.match(call.normalized):
                    if call.method in backend_lookup[be_path]:
                        matched_be = backend_lookup[be_path][call.method][0]
                    break

        if matched_be is None:
            continue  # বাংলা: কোনো match নেই — broken বা method mismatch

        # বাংলা: path parameter সংখ্যা তুলনা
        be_param_count = len(matched_be.path_params)
        fe_param_count = len(call.path_params)

        if be_param_count != fe_param_count:
            result.param_mismatches.append({
                "path": call.path,
                "normalized": call.normalized,
                "method": call.method,
                "frontend_params": call.path_params,
                "backend_params": matched_be.path_params,
                "frontend_param_count": fe_param_count,
                "backend_param_count": be_param_count,
                "source_file": call.source_file,
                "source_line": call.source_line,
            })

    # ──────────────────────────────────────────────────────────────────────────
    # বাংলা: Summary তৈরি
    # ──────────────────────────────────────────────────────────────────────────
    total_issues = (
        len(result.orphan_backend)
        + len(result.broken_frontend)
        + len(result.method_mismatches)
        + len(result.param_mismatches)
    )

    result.summary = {
        "total_backend_routes": len(backend_routes),
        "total_frontend_calls": len(frontend_calls),
        "unique_backend_paths": len(all_backend_paths),
        "unique_frontend_paths": len(all_frontend_paths),
        "orphan_backend_count": len(result.orphan_backend),
        "broken_frontend_count": len(result.broken_frontend),
        "method_mismatch_count": len(result.method_mismatches),
        "param_mismatch_count": len(result.param_mismatches),
        "total_issues": total_issues,
        "status": "OK" if total_issues == 0 else "ISSUES_FOUND",
    }

    return result


# ══════════════════════════════════════════════════════════════════════════════
# বাংলা: Markdown রিপোর্ট জেনারেশন — emoji indicators সহ
# ══════════════════════════════════════════════════════════════════════════════
def generate_markdown_report(result: DiffResult) -> str:
    """বাংলা: স্ট্রাকচার্ড Markdown রিপোর্ট তৈরি — emoji indicators সহ।"""
    lines: list[str] = []
    s = result.summary

    lines.append("# 🔍 SupremeAI API Contract Diff Report")
    lines.append("")
    lines.append(f"> Generated by `api_contract_diff.py` — static analysis only")
    lines.append("")

    # ──────────────────────────────────────────────────────────────────────────
    # বাংলা: Summary সেকশন
    # ──────────────────────────────────────────────────────────────────────────
    lines.append("## 📊 Summary")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| 🖥️ Backend Routes (total) | {s['total_backend_routes']} |")
    lines.append(f"| 🗺️ Unique Backend Paths | {s['unique_backend_paths']} |")
    lines.append(f"| 📱 Frontend API Calls (total) | {s['total_frontend_calls']} |")
    lines.append(f"| 📍 Unique Frontend Paths | {s['unique_frontend_paths']} |")
    lines.append(f"| 👻 Orphan Backend Routes | {s['orphan_backend_count']} |")
    lines.append(f"| 💔 Broken Frontend Calls | {s['broken_frontend_count']} |")
    lines.append(f"| 🔄 Method Mismatches | {s['method_mismatch_count']} |")
    lines.append(f"| ⚠️ Param Mismatches | {s['param_mismatch_count']} |")
    lines.append(f"| **Total Issues** | **{s['total_issues']}** |")
    lines.append("")

    if s["status"] == "OK":
        lines.append("> ✅ **No issues found!** All frontend API calls match backend routes.")
        lines.append("")
    else:
        lines.append(f"> ❌ **{s['total_issues']} issue(s) found.** See details below.")
        lines.append("")

    # ──────────────────────────────────────────────────────────────────────────
    # বাংলা: Orphan Backend Routes
    # ──────────────────────────────────────────────────────────────────────────
    if result.orphan_backend:
        lines.append("## 👻 Orphan Backend Routes")
        lines.append("")
        lines.append("> Routes defined in backend but **never called** from frontend.")
        lines.append("")
        lines.append("| Method | Path | Response Model | Source |")
        lines.append("|--------|------|----------------|--------|")
        for item in sorted(result.orphan_backend, key=lambda x: (x["path"], x["method"])):
            resp = item.get("response_model") or "—"
            src = f"{item['source_file']}:{item['source_line']}"
            lines.append(f"| `{item['method']}` | `{item['path']}` | `{resp}` | {src} |")
        lines.append("")

    # ──────────────────────────────────────────────────────────────────────────
    # বাংলা: Broken Frontend Calls
    # ──────────────────────────────────────────────────────────────────────────
    if result.broken_frontend:
        lines.append("## 💔 Broken Frontend Calls")
        lines.append("")
        lines.append("> Frontend calling endpoints that **don't exist** in backend.")
        lines.append("")
        lines.append("| Method | Path | Source | Pattern |")
        lines.append("|--------|------|--------|---------|")
        for item in sorted(result.broken_frontend, key=lambda x: (x["path"], x["method"])):
            src = f"{item['source_file']}:{item['source_line']}"
            pattern = item.get("call_pattern", "fetch")
            lines.append(f"| `{item['method']}` | `{item['path']}` | {src} | `{pattern}` |")
        lines.append("")

    # ──────────────────────────────────────────────────────────────────────────
    # বাংলা: Method Mismatches
    # ──────────────────────────────────────────────────────────────────────────
    if result.method_mismatches:
        lines.append("## 🔄 Method Mismatches")
        lines.append("")
        lines.append("> Frontend using **different HTTP method** than backend defines.")
        lines.append("")
        lines.append("| Frontend Method | Backend Methods | Path | Source |")
        lines.append("|----------------|----------------|------|--------|")
        for item in sorted(result.method_mismatches, key=lambda x: (x["path"], x["frontend_method"])):
            be_methods = ", ".join(f"`{m}`" for m in item["backend_methods"])
            src = f"{item['source_file']}:{item['source_line']}"
            lines.append(f"| `{item['frontend_method']}` | {be_methods} | `{item['path']}` | {src} |")
        lines.append("")

    # ──────────────────────────────────────────────────────────────────────────
    # বাংলা: Path Parameter Mismatches
    # ──────────────────────────────────────────────────────────────────────────
    if result.param_mismatches:
        lines.append("## ⚠️ Path Parameter Mismatches")
        lines.append("")
        lines.append("> Frontend sends params that backend route **doesn't accept** (or vice versa).")
        lines.append("")
        lines.append("| Method | Path | Frontend Params | Backend Params | Source |")
        lines.append("|--------|------|-----------------|----------------|--------|")
        for item in sorted(result.param_mismatches, key=lambda x: (x["path"], x["method"])):
            fe_params = item["frontend_params"] or ["(none)"]
            be_params = item["backend_params"] or ["(none)"]
            src = f"{item['source_file']}:{item['source_line']}"
            lines.append(
                f"| `{item['method']}` | `{item['path']}` | {fe_params} | {be_params} | {src} |"
            )
        lines.append("")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# বাংলা: CLI argument parsing এবং main entry point
# ══════════════════════════════════════════════════════════════════════════════
def build_arg_parser() -> argparse.ArgumentParser:
    """বাংলা: CLI argument parser তৈরি।"""
    parser = argparse.ArgumentParser(
        description="SupremeAI API Contract Diff — compare frontend calls vs backend routes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""উদাহরণ:
  python scripts/api_contract_diff.py                  # Full diff report
  python scripts/api_contract_diff.py --json            # Machine-readable JSON
  python scripts/api_contract_diff.py --backend-only    # Only scan backend routes
  python scripts/api_contract_diff.py --frontend-only   # Only scan frontend calls
""",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Machine-readable JSON output instead of Markdown",
    )
    parser.add_argument(
        "--backend-only",
        action="store_true",
        default=False,
        help="Only parse and list backend routes (no comparison)",
    )
    parser.add_argument(
        "--frontend-only",
        action="store_true",
        default=False,
        help="Only parse and list frontend API calls (no comparison)",
    )
    parser.add_argument(
        "--fail-on-critical",
        action="store_true",
        default=False,
        help="CI mode: exit non-zero only for genuinely critical issues "
        "(e.g. parse failures), not for routine drift/advisory findings. "
        "Without this flag any total_issues>0 fails as before.",
    )
    return parser


def main() -> int:
    """বাংলা: মূল entry point — argument parse, scanning, comparison, এবং output।"""
    parser = build_arg_parser()
    args = parser.parse_args()

    # বাংলা: পরস্পরবিরোধী flags চেক
    if args.backend_only and args.frontend_only:
        print("ERROR: --backend-only and --frontend-only cannot be used together.", file=sys.stderr)
        return 2

    registry = parse_routers_registry()
    backend_routes = parse_backend_routes(registry)
    frontend_calls = parse_frontend_calls()

    # ──────────────────────────────────────────────────────────────────────────
    # বাংলা: --backend-only mode — শুধু ব্যাকএন্ড রুট তালিকা দেখানো
    # ──────────────────────────────────────────────────────────────────────────
    if args.backend_only:
        if args.json:
            output = {
                "backend_routes": [
                    {
                        "method": r.method,
                        "path": r.path,
                        "normalized": r.normalized,
                        "response_model": r.response_model,
                        "request_body": r.request_body,
                        "path_params": r.path_params,
                        "source_file": r.source_file,
                        "source_line": r.source_line,
                    }
                    for r in backend_routes
                ],
                "total": len(backend_routes),
            }
            print(json.dumps(output, indent=2, ensure_ascii=False))
        else:
            print(f"# Backend Routes ({len(backend_routes)} found)")
            print("")
            print("| Method | Path | Response Model | Request Body | Source |")
            print("|--------|------|----------------|--------------|--------|")
            for r in sorted(backend_routes, key=lambda x: (x.path, x.method)):
                resp = r.response_model or "—"
                req = r.request_body or "—"
                src = f"{r.source_file}:{r.source_line}"
                print(f"| `{r.method}` | `{r.path}` | `{resp}` | `{req}` | {src} |")
        return 0

    # ──────────────────────────────────────────────────────────────────────────
    # বাংলা: --frontend-only mode — শুধু ফ্রন্টএন্ড কল তালিকা দেখানো
    # ──────────────────────────────────────────────────────────────────────────
    if args.frontend_only:
        if args.json:
            output = {
                "frontend_calls": [
                    {
                        "method": c.method,
                        "path": c.path,
                        "normalized": c.normalized,
                        "path_params": c.path_params,
                        "source_file": c.source_file,
                        "source_line": c.source_line,
                        "call_pattern": c.call_pattern,
                    }
                    for c in frontend_calls
                ],
                "total": len(frontend_calls),
            }
            print(json.dumps(output, indent=2, ensure_ascii=False))
        else:
            print(f"# Frontend API Calls ({len(frontend_calls)} found)")
            print("")
            print("| Method | Path | Pattern | Source |")
            print("|--------|------|---------|--------|")
            for c in sorted(frontend_calls, key=lambda x: (x.path, x.method)):
                src = f"{c.source_file}:{c.source_line}"
                print(f"| `{c.method}` | `{c.path}` | `{c.call_pattern}` | {src} |")
        return 0

    # ──────────────────────────────────────────────────────────────────────────
    # বাংলা: Full diff mode — তুলনা এবং রিপোর্ট
    # ──────────────────────────────────────────────────────────────────────────
    result = compare_routes(backend_routes, frontend_calls)

    if args.json:
        # বাংলা: JSON output — CI/CD pipeline এ ব্যবহারের জন্য
        print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
    else:
        # বাংলা: Markdown report — human-readable
        print(generate_markdown_report(result))

    # বাংলা: Exit code
    # --fail-on-critical মোডে শুধু genuinely-critical issue (broken_frontend:
    # ফ্রন্টএন্ড এমন route কল করছে যেটা ব্যাকএন্ডে নেই — production-এ 404 করবে;
    # method_mismatches: ভুল HTTP method — production-এ fail করবে) থাকলে fail করে।
    # orphan_backend (অব্যবহৃত backend route) ও param_mismatches (প্রায়ই dynamic
    # route-এর false positive) শুধু advisory — এগুলো report হয় কিন্তু build ভাঙে না।
    if args.fail_on_critical:
        critical_count = result.summary.get("method_mismatch_count", 0)
        return 1 if critical_count > 0 else 0

    return 1 if result.summary.get("total_issues", 0) > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
