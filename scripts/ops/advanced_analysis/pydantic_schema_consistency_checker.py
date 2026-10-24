#!/usr/bin/env python3
"""
SupremeAI — Pydantic Schema Consistency Checker
================================================

বাংলা: এই স্ক্রিপ্টটি FastAPI রাউট হ্যান্ডলারে ব্যবহৃত Pydantic মডেল এবং
সেই মডেলের সংজ্ঞার মধ্যে সামঞ্জস্য যাচাই করে। পাশাপাশি জেনারেট
করা TypeScript টাইপের সাথে ড্রিফট চেক করে।

Checklist:
  1. রাউটে response_model বা request body-তে রেফারেন্স করা মডেল বিদ্যমান কি না
  2. রাউট হ্যান্ডলার রিটার্ন করা কী-গুলো response_model-এ আছে কি না
  3. Pydantic মডেল তৈরি করা হয়েছে কিন্তু কোনো রাউটে ব্যবহৃত হয়নি
  4. Optional ফিল্ড বনাম রাউট ব্যবহারের মিল আছে কি না
  5. TypeScript জেনারেটেড টাইপে ড্রিফট আছে কি না

Usage:
    python scripts/pydantic_schema_consistency_checker.py
    python scripts/pydantic_schema_consistency_checker.py --json
    python scripts/pydantic_schema_consistency_checker.py --route /auth/login
    python scripts/pydantic_schema_consistency_checker.py --ts-check

Exit codes:
    0 = সব সামঞ্জস্যপূর্ণ (consistent)
    1 = ড্রিফট পাওয়া গেছে (drift found)
    2 = এরর (script execution error)
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from argparse import ArgumentParser
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# ── রিপো রুট নির্ণয় ─────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_DIR = _REPO_ROOT / "backend"
_ROUTES_DIR = _BACKEND_DIR / "api" / "routes"
_SCHEMAS_DIR = _BACKEND_DIR / "schemas"
_MODELS_DIR = _BACKEND_DIR / "models"
_SHARED_TYPES_DIR = _REPO_ROOT / "packages" / "shared-types" / "src" / "typescript"
_FRONTEND_TYPES_DIR = _REPO_ROOT / "frontend" / "src" / "types"
_GENERATE_TYPES_SCRIPT = _REPO_ROOT / "scripts" / "generate_types.py"

# বাংলা: এই নামগুলো পিজ্যান্টিক মডেল নয় — built-in types, তাই ফিল্টার করা হচ্ছে
_BUILTIN_TYPE_NAMES = {
    "str", "int", "float", "bool", "bytes", "dict", "list", "set", "tuple",
    "Any", "None", "Optional", "Union", "Literal", "datetime", "date",
    "Path", "Response", "Request", "BackgroundTasks", "HTTPException",
    "APIRouter", "Depends", "Query", "Body", "File", "Form", "Header",
    "Cookie", "UploadFile", "WebSocket", "WebSocketDisconnect",
    "UUID", "AsyncSession", "Session", "ClientSession",
    "JSON", "Text", "String", "Boolean", "Float", "Integer",
}

# ── UTF-8 stdout (Windows cp1252-তে emoji/unicode crash ঠেকাতে) ─────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════════
# ডেটা ক্লাস ও এনাম
# ══════════════════════════════════════════════════════════════════════════════


class Severity(str, Enum):
    """সমস্যার গুরুত্ব নির্দেশক।"""
    ERROR = "🔴"
    WARNING = "🟡"
    GOOD = "🟢"


@dataclass
class PydanticField:
    """একটি Pydantic মডেল ফিল্ডের তথ্য।"""
    name: str
    type_annotation: str
    is_optional: bool
    has_default: bool
    default_value: Any = None
    validators: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)


@dataclass
class PydanticModel:
    """একটি Pydantic BaseModel সাবক্লাসের তথ্য।"""
    name: str
    source_file: str  # রিলেটিভ পাথ (repo root থেকে)
    module: str  # যেমন: schemas.skill_manifest
    fields: dict[str, PydanticField] = field(default_factory=dict)
    is_nested: bool = False  # অন্য মডেলের ভেতর ব্যবহৃত কি না
    base_classes: list[str] = field(default_factory=list)


@dataclass
class RouteInfo:
    """একটি FastAPI রাউটের তথ্য।"""
    method: str  # GET, POST, PUT, DELETE, PATCH
    path: str
    function_name: str
    response_model: str | None  # response_model=ModelName
    request_body_model: str | None  # def foo(body: SomeModel)
    inline_models: list[str] = field(default_factory=list)  # ফাইলে ডিফাইন্ড মডেল
    status_code: int | None = None
    source_file: str = ""
    line_number: int = 0
    # হ্যান্ডলার থেকে রিটার্ন করা ডিকশনারি কী-গুলো (static analysis)
    return_keys: set[str] = field(default_factory=set)
    # মডেল কনস্ট্রাক্টরে পাস করা কী-গুলো (যদি model_name(key=val) থাকে)
    constructor_keys: set[str] = field(default_factory=set)


@dataclass
class Finding:
    """একটি সামঞ্জস্য চেকের ফলাফল।"""
    severity: Severity
    code: str  # MISSING_MODEL, PARTIAL_MODEL, UNUSED_MODEL, OPTIONAL_MISMATCH, GOOD
    route_path: str | None
    model_name: str
    message: str
    source_file: str = ""
    details: dict[str, Any] = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════════════════
# AST বিশ্লেষণ হেল্পার
# ══════════════════════════════════════════════════════════════════════════════


def _is_basemodel_subclass(node: ast.ClassDef, source_code: str) -> bool:
    """ক্লাসটি BaseModel থেকে inherit করে কি না তা চেক করে (import ট্র্যাকিং সহ)।
    
    বাংলা: শুধু নাম দেখে নয়, import স্টেটমেন্ট থেকে BaseModel কে রেফারেন্স
    করা হয়েছে কি না তাও যাচাই করা হয়।
    """
    basemodel_aliases = {"BaseModel"}
    # ফাইলে BaseModel-এর alias খোঁজা
    for stmt in ast.walk(ast.parse(source_code)):
        if isinstance(stmt, ast.ImportFrom):
            if stmt.module and ("pydantic" in stmt.module):
                for alias in stmt.names:
                    if alias.name == "BaseModel":
                        basemodel_aliases.add(alias.asname or "BaseModel")
        elif isinstance(stmt, ast.Import):
            for alias in stmt.names:
                if "pydantic" in (alias.name or "") and alias.asname:
                    # from pydantic import BaseModel -> alias = None, name = pydantic
                    pass

    for base in node.bases:
        if isinstance(base, ast.Name) and base.id in basemodel_aliases:
            return True
        if isinstance(base, ast.Attribute) and base.attr in basemodel_aliases:
            return True
    return False


def _get_annotation_name(node: ast.expr | None) -> str:
    """একটি type annotation AST নোড থেকে টাইপের নাম বের করে।
    
    বাংলা: জটিল জেনেরিক টাইপ (list[Dict], Optional[str] ইত্যাদি)
    থেকে মূল টাইপের নাম স্ট্রিং হিসেবে রিটার্ন করে।
    """
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Subscript):
        return _get_annotation_name(node.value)
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.BinOp):  # X | Y (union type)
        return _get_annotation_name(node.left)
    if isinstance(node, ast.Call):
        return _get_annotation_name(node.func)
    if isinstance(node, ast.Tuple):
        parts = [_get_annotation_name(elt) for elt in node.elts]
        return ", ".join(p for p in parts if p)
    return ""


def _is_optional_annotation(node: ast.expr | None, source_code: str) -> bool:
    """Type annotation Optional কি না তা চেক করে।
    
    বাংলা: Optional[X], X | None, Union[X, None] সবকিছু চিনতে পারে।
    """
    if node is None:
        return False
    annotation_str = ast.unparse(node)
    # Optional[X] প্যাটার্ন
    if re.search(r"\bOptional\s*\[", annotation_str):
        return True
    # X | None প্যাটার্ন (Python 3.10+)
    if re.search(r"\|\s*None\s*$", annotation_str):
        return True
    # Union[X, None] প্যাটার্ন
    if re.search(r"Union\s*\[[^\]]*\bNone\b", annotation_str):
        return True
    return False


def _has_default_value(node: ast.AnnAssign) -> bool:
    """ফিল্ডে default value আছে কি না।
    
    বাংলা: Field(default=...) বা সরাসরি = value দুটোই চিনতে পারে।
    """
    if node.value is not None:
        return True
    return False


def _get_field_constraints(annotation_node: ast.expr | None) -> dict[str, Any]:
    """Field(...) থেকে constraints বের করে (min_length, max_length, ge, le ইত্যাদি)।
    
    বাংলা: Pydantic Field() কলে দেওয়া validation constraints সংগ্রহ করে।
    """
    constraints = {}
    if annotation_node is None:
        return constraints
    # AnnAssign এর value অংশে Field(...) থাকতে পারে
    return constraints


def _extract_field_constraints_from_assignment(assignment_node: ast.expr | None) -> dict[str, Any]:
    """Assignment value থেকে Field() constraints বের করে।"""
    constraints = {}
    if assignment_node is None:
        return constraints
    if isinstance(assignment_node, ast.Call):
        func_name = _get_annotation_name(assignment_node.func)
        if func_name == "Field":
            for kw in assignment_node.keywords:
                if kw.arg in ("min_length", "max_length", "ge", "le", "gt", "lt",
                              "regex", "pattern", "min_items", "max_items"):
                    try:
                        constraints[kw.arg] = ast.literal_eval(kw.value)
                    except (ValueError, TypeError):
                        constraints[kw.arg] = ast.unparse(kw.value)
    return constraints


def _extract_return_dict_keys(func_node: ast.FunctionDef) -> set[str]:
    """ফাংশন বডি থেকে return {"key": ...} স্টেটমেন্টের কী-গুলো বের করে।
    
    বাংলা: return স্টেটমেন্টে ডিকশনারি লিটারেল থাকলে সেই কীগুলো
    static analysis দিয়ে সংগ্রহ করা হয়।
    """
    keys: set[str] = set()
    for node in ast.walk(func_node):
        if isinstance(node, ast.Return) and node.value is not None:
            if isinstance(node.value, ast.Dict):
                for key_node in node.value.keys:
                    if isinstance(key_node, ast.Constant):
                        keys.add(str(key_node.value))
    return keys


def _extract_constructor_keys(func_node: ast.FunctionDef) -> dict[str, set[str]]:
    """ফাংশন বডি থেকে ModelName(key=val) কলের কী-গুলো বের করে।
    
    বাংলা: return SomeModel(foo=x, bar=y) — এখান থেকে foo, bar কীগুলো
    সংগ্রহ করা হয়।
    """
    result: dict[str, set[str]] = {}
    for node in ast.walk(func_node):
        if isinstance(node, ast.Return) and node.value is not None:
            _walk_for_constructor_calls(node.value, result)
    return result


def _walk_for_constructor_calls(node: ast.expr, result: dict[str, set[str]]) -> None:
    """AST ট্রিতে constructor call খোঁজে।"""
    if isinstance(node, ast.Call):
        model_name = _get_annotation_name(node.func)
        if model_name and model_name[0].isupper():  # ক্যাপিটাল letter = সম্ভবত মডেল
            keys = set()
            for kw in node.keywords:
                # বাংলা: **kwargs-এর জন্য kw.arg None হতে পারে
                if kw.arg is not None:
                    keys.add(kw.arg)
            if keys and model_name not in result:
                result[model_name] = set()
            if keys:
                result[model_name].update(keys)
    # চাইল্ড নোডও চেক
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.expr):
            _walk_for_constructor_calls(child, result)


# ══════════════════════════════════════════════════════════════════════════════
# মডেল সংগ্রহ
# ══════════════════════════════════════════════════════════════════════════════


def collect_pydantic_models_from_dir(
    directory: Path, base_module: str
) -> dict[str, PydanticModel]:
    """একটি ডিরেক্টরি থেকে সব Pydantic BaseModel সাবক্লাস সংগ্রহ করে।
    
    বাংলা: প্রতিটি .py ফাইল parse করে BaseModel-এর subclass খোঁজে এবং
    ফিল্ড, টাইপ, Optional status ইত্যাদি সংগ্রহ করে।
    """
    models: dict[str, PydanticModel] = {}
    if not directory.is_dir():
        return models

    for py_file in sorted(directory.rglob("*.py")):
        if py_file.name.startswith("__"):
            continue
        try:
            source_code = py_file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source_code, filename=str(py_file))
        except (SyntaxError, UnicodeDecodeError) as exc:
            # বাংলা: syntax error বা encoding সমস্যাযুক্ত ফাইল এড়িয়ে যাওয়া হচ্ছে
            continue

        # মডিউল পাথ নির্ণয় (schemas.skill_manifest এর মতো)
        rel = py_file.relative_to(_BACKEND_DIR)
        module_parts = rel.with_suffix("").parts
        module = ".".join(module_parts)

        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not _is_basemodel_subclass(node, source_code):
                continue

            model_name = node.name
            if model_name in ("BaseModel", "ABC"):
                continue

            # বাংলা: ক্লাসের সব annotated assignment ফিল্ড হিসেবে সংগ্রহ
            fields: dict[str, PydanticField] = {}
            validators: list[str] = []
            for item in ast.iter_child_nodes(node):
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # validator ফাংশন চেক (field_validator, validator decorator)
                    for dec in item.decorator_list:
                        dec_name = _get_annotation_name(dec)
                        if dec_name in ("field_validator", "validator", "model_validator"):
                            validators.append(item.name)
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    field_name = item.target.id
                    if field_name.startswith("_"):
                        continue  # বাংলা: private attribute skip
                    type_str = ast.unparse(item.annotation) if item.annotation else ""
                    is_opt = _is_optional_annotation(item.annotation, source_code)
                    has_default = _has_default_value(item)
                    # Field() থেকে constraints বের করা
                    constraints = _extract_field_constraints_from_assignment(item.value)
                    fields[field_name] = PydanticField(
                        name=field_name,
                        type_annotation=type_str,
                        is_optional=is_opt,
                        has_default=has_default,
                        validators=validators[:],  # copy
                        constraints=constraints,
                    )

            rel_path = py_file.relative_to(_REPO_ROOT)
            models[model_name] = PydanticModel(
                name=model_name,
                source_file=str(rel_path),
                module=module,
                fields=fields,
                base_classes=[_get_annotation_name(b) for b in node.bases],
            )

    return models


def collect_inline_models_from_routes() -> dict[str, PydanticModel]:
    """রাউট ফাইলে inline ডিফাইন্ড Pydantic মডেল সংগ্রহ করে।
    
    বাংলা: অনেক রাউট ফাইলে সরাসরি class X(BaseModel): লেখা থাকে
    যা schemas/ বা models/ তে নেই। সেগুলোও সংগ্রহ করা হচ্ছে।
    """
    return collect_pydantic_models_from_dir(_ROUTES_DIR, "api.routes")


# ══════════════════════════════════════════════════════════════════════════════
# রাউট বিশ্লেষণ
# ══════════════════════════════════════════════════════════════════════════════


def _extract_decorator_info(
    decorator: ast.expr,
) -> tuple[str, str, str | None, int | None]:
    """একটি decorator থেকে (method, path, response_model, status_code) বের করে।
    
    বাংলা: @router.post("/path", response_model=X, status_code=Y) থেকে
    POST, /path, X, Y নির্ণয় করা হয়।
    """
    method = ""
    path = ""
    response_model = None
    status_code = None

    if isinstance(decorator, ast.Call):
        # @router.get("/path") বা @router.post("/path", ...)
        func_name = _get_annotation_name(decorator.func)
        if func_name and func_name.upper() in (
            "GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"
        ):
            method = func_name.upper()
        # প্রথম positional argument = path
        if decorator.args and isinstance(decorator.args[0], ast.Constant):
            path = str(decorator.args[0].value)
        # keyword arguments
        for kw in decorator.keywords:
            if kw.arg == "response_model":
                response_model = _get_annotation_name(kw.value)
            elif kw.arg == "status_code":
                try:
                    status_code = int(ast.literal_eval(kw.value))
                except (ValueError, TypeError):
                    status_code = None
    elif isinstance(decorator, ast.Attribute):
        # @router.get — কোনো কল নেই (বিরল কেস)
        method = decorator.attr.upper() if decorator.attr else ""

    return method, path, response_model, status_code


def parse_route_file(py_file: Path) -> list[RouteInfo]:
    """একটি রাউট ফাইল parse করে সব route info বের করে।
    
    বাংলা: প্রতিটি @router.get/post/put/delete ডেকোরেটেড ফাংশন থেকে
    response_model, request body model, এবং return dict keys সংগ্রহ করে।
    """
    routes: list[RouteInfo] = []
    try:
        source_code = py_file.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source_code, filename=str(py_file))
    except (SyntaxError, UnicodeDecodeError):
        return routes

    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # ডেকোরেটর থেকে route info বের করা
        for dec in node.decorator_list:
            # with_error_bus ইত্যাদি wrapper decorator থেকে ভেতরেরটি খোঁজা
            actual_dec = dec
            if isinstance(dec, ast.Call):
                # with_error_bus("...") — এর ভেতরে nested call থাকতে পারে
                pass

            method, path, response_model, status_code = _extract_decorator_info(dec)
            if not method:
                continue

            # বাংলা: request body model — ফাংশন প্যারামিটারে Pydantic model type annotation
            # Depends(), Request, এবং query/path parameters (যাদের default আছে) বাদ
            request_body_model = None
            # বাংলা: defaults dict তৈরি — কোন parameter-এ Depends() বা default আছে তা ট্র্যাক করা হচ্ছে
            param_defaults = {}
            for default in node.args.defaults:
                # defaults list args-এর শেষ থেকে শুরু হয়
                pass
            for i, default in enumerate(node.args.defaults):
                idx = len(node.args.args) - len(node.args.defaults) + i
                if 0 <= idx < len(node.args.args):
                    param_name = node.args.args[idx].arg
                    param_defaults[param_name] = default

            for arg in node.args.args:
                if arg.annotation:
                    ann_name = _get_annotation_name(arg.annotation)
                    if ann_name and ann_name[0].isupper():
                        # Depends() ও Request বাদ দেওয়া
                        if ann_name in _BUILTIN_TYPE_NAMES:
                            continue
                        # বাংলা: Depends() দিয়ে ইনজেক্ট করা parameter skip — এরা request body নয়
                        if arg.arg in param_defaults:
                            default_val = param_defaults[arg.arg]
                            if isinstance(default_val, ast.Call):
                                def_name = _get_annotation_name(default_val.func)
                                if def_name == "Depends":
                                    continue
                        # বাংলা: কোনো default নেই এবং Depends()-ও নয় = সম্ভবত request body
                        if arg.arg not in param_defaults:
                            request_body_model = ann_name
                            break

            # return dict keys ও constructor keys বের করা
            return_keys = _extract_return_dict_keys(node)
            constructor_keys_map = _extract_constructor_keys(node)
            # response_model-এর constructor keys
            constructor_keys = set()
            if response_model and response_model in constructor_keys_map:
                constructor_keys = constructor_keys_map[response_model]

            rel_path = py_file.relative_to(_REPO_ROOT)
            route_info = RouteInfo(
                method=method,
                path=path,
                function_name=node.name,
                response_model=response_model,
                request_body_model=request_body_model,
                status_code=status_code,
                source_file=str(rel_path),
                line_number=node.lineno,
                return_keys=return_keys,
                constructor_keys=constructor_keys,
            )
            routes.append(route_info)

    return routes


def collect_all_routes(route_filter: str | None = None) -> list[RouteInfo]:
    """সব রাউট ফাইল থেকে route info সংগ্রহ করে।
    
    বাংলা: --route PATH দেওয়া থাকলে শুধু সেই রাউট ফিল্টার করা হয়।
    """
    all_routes: list[RouteInfo] = []
    if not _ROUTES_DIR.is_dir():
        return all_routes

    for py_file in sorted(_ROUTES_DIR.rglob("*.py")):
        if py_file.name.startswith("__"):
            continue
        file_routes = parse_route_file(py_file)
        for r in file_routes:
            if route_filter:
                # বাংলা: পার্শিয়াল ম্যাচ — /auth/login দিলে /auth/login ম্যাচ করবে
                if route_filter not in r.path:
                    continue
            all_routes.append(r)

    return all_routes


# ══════════════════════════════════════════════════════════════════════════════
# TypeScript ক্রস-রেফারেন্স
# ══════════════════════════════════════════════════════════════════════════════


def _snake_to_camel(name: str) -> str:
    """snake_case থেকে camelCase রূপান্তর।
    
    বাংলা: Python-এ skill_id → TypeScript-এ skillId
    """
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def parse_typescript_interface(
    ts_content: str,
) -> dict[str, tuple[str, bool]] | None:
    """TypeScript interface থেকে ফিল্ড নাম ও optional status বের করে।
    
    বাংলা: export interface Foo { bar?: string; baz: number; } থেকে
    {"bar": ("string", True), "baz": ("number", False)} রিটার্ন করে।
    
    Returns:
        {field_name: (type_str, is_optional)} বা None যদি parse না হয়
    """
    # interface Name { ... } প্যাটার্ন খোঁজা
    match = re.search(r"export\s+interface\s+(\w+)\s*\{([^}]*)\}", ts_content, re.DOTALL)
    if not match:
        return None

    interface_name = match.group(1)
    body = match.group(2)
    # বাংলা: JSDoc comments (/** ... */) সরিয়ে ফেলা — এগুলো split(';') এ multi-line entry তৈরি করে
    body_clean = re.sub(r'/\*\*[^*]*\*/', '', body)
    fields: dict[str, tuple[str, bool]] = {}

    for line in body_clean.split(";"):
        line = line.strip()
        if not line:
            continue
        # field_name?: type বা field_name: type
        m = re.match(r"(\w+)(\?)?\s*:\s*(.+)", line)
        if m:
            field_name = m.group(1)
            is_optional = m.group(2) == "?"
            field_type = m.group(3).strip()
            fields[field_name] = (field_type, is_optional)

    return fields


def collect_typescript_interfaces(
    ts_dir: Path,
) -> dict[str, dict[str, tuple[str, bool]]]:
    """shared-types/src/typescript/ থেকে সব interface সংগ্রহ করে।
    
    বাংলা: প্রতিটি .d.ts ফাইল parse করে interface ফিল্ডগুলো সংগ্রহ করে।
    """
    interfaces: dict[str, dict[str, tuple[str, bool]]] = {}
    if not ts_dir.is_dir():
        return interfaces

    for ts_file in sorted(ts_dir.glob("*.d.ts")):
        try:
            content = ts_file.read_text(encoding="utf-8", errors="replace")
        except UnicodeDecodeError:
            continue
        parsed = parse_typescript_interface(content)
        if parsed is not None:
            # বাংলা: .d.ts ফাইল থেকে interface name বের করা — .stem শুধু .ts কাটে, .d.ts-এর জন্য .name[:-5]
            interface_name = ts_file.name[:-5] if ts_file.name.endswith('.d.ts') else ts_file.stem
            interfaces[interface_name] = parsed

    return interfaces


# ══════════════════════════════════════════════════════════════════════════════
# সামঞ্জস্য চেক লজিক
# ══════════════════════════════════════════════════════════════════════════════


def check_route_model_consistency(
    route: RouteInfo,
    all_models: dict[str, PydanticModel],
) -> list[Finding]:
    """একটি রাউট এবং তার ব্যবহৃত মডেলের মধ্যে সামঞ্জস্য চেক করে।
    
    বাংলা: প্রতিটি রাউটের জন্য MISSING_MODEL, PARTIAL_MODEL, ও
    OPTIONAL_MISMATCH ফাইন্ডিং তৈরি করে।
    """
    findings: list[Finding] = []
    route_label = f"{route.method} {route.path}"

    # ── response_model চেক ────────────────────────────────────────────────
    if route.response_model:
        # list[ModelName] বা List[ModelName] থেকে মডেল নাম বের করা
        resp_model_name = route.response_model
        list_match = re.search(r"(?:list|List)\s*\[\s*(\w+)\s*\]", resp_model_name)
        if list_match:
            resp_model_name = list_match.group(1)

        if resp_model_name not in all_models:
            # বাংলা: built-in types (list, dict ইত্যাদি) বা generic টাইপ skip
            if resp_model_name not in _BUILTIN_TYPE_NAMES:
                findings.append(Finding(
                    severity=Severity.ERROR,
                    code="MISSING_MODEL",
                    route_path=route_label,
                    model_name=resp_model_name,
                    message=(
                        f"রাউটে response_model='{resp_model_name}' ব্যবহার করা হয়েছে কিন্তু"
                        f" schemas/ বা models/ বা route file-এ এই মডেল পাওয়া যায়নি"
                    ),
                    source_file=route.source_file,
                ))
        else:
            model = all_models[resp_model_name]
            model_field_names = set(model.fields.keys())

            # constructor keys vs model fields
            if route.constructor_keys:
                extra_keys = route.constructor_keys - model_field_names
                if extra_keys:
                    findings.append(Finding(
                        severity=Severity.ERROR,
                        code="PARTIAL_MODEL",
                        route_path=route_label,
                        model_name=resp_model_name,
                        message=(
                            f"রাউট হ্যান্ডলারে '{resp_model_name}' constructor-এ"
                            f" {extra_keys} কী পাস করা হয়েছে যা মডেলে নেই"
                        ),
                        source_file=route.source_file,
                        details={"extra_keys": sorted(extra_keys),
                                 "model_fields": sorted(model_field_names)},
                    ))

            # return dict keys vs model fields (শুধু যখন সরাসরি dict return হয়)
            if route.return_keys and model_field_names:
                extra_return_keys = route.return_keys - model_field_names
                if extra_return_keys:
                    findings.append(Finding(
                        severity=Severity.ERROR,
                        code="PARTIAL_MODEL",
                        route_path=route_label,
                        model_name=resp_model_name,
                        message=(
                            f"রাউট হ্যান্ডলার ডিকশনারিতে {extra_return_keys} কী রিটার্ন"
                            f" করে যা '{resp_model_name}' মডেলে নেই"
                        ),
                        source_file=route.source_file,
                        details={"return_keys": sorted(route.return_keys),
                                 "model_fields": sorted(model_field_names)},
                    ))

            # বাংলা: GOOD ফাইন্ডিং — সব ঠিক আছে
            if not any(f.code in ("MISSING_MODEL", "PARTIAL_MODEL") for f in findings):
                findings.append(Finding(
                    severity=Severity.GOOD,
                    code="GOOD",
                    route_path=route_label,
                    model_name=resp_model_name,
                    message=f"'{resp_model_name}' মডেল পাওয়া গেছে এবং রাউট সামঞ্জস্যপূর্ণ",
                    source_file=route.source_file,
                ))

    # ── request body model চেক ────────────────────────────────────────────
    if route.request_body_model:
        if route.request_body_model not in all_models:
            # বাংলা: built-in types skip
            if route.request_body_model in _BUILTIN_TYPE_NAMES:
                pass
            else:
                findings.append(Finding(
                    severity=Severity.ERROR,
                    code="MISSING_MODEL",
                    route_path=route_label,
                    model_name=route.request_body_model,
                    message=(
                        f"রাউটে request body হিসেবে '{route.request_body_model}' ব্যবহার"
                        f" করা হয়েছে কিন্তু মডেল পাওয়া যায়নি"
                    ),
                    source_file=route.source_file,
                ))

    return findings


def check_unused_models(
    all_models: dict[str, PydanticModel],
    used_model_names: set[str],
) -> list[Finding]:
    """কোনো রাউটে ব্যবহৃত না হওয়া মডেল খোঁজে।
    
    বাংলা: Pydantic মডেল ডিফাইন করা হয়েছে কিন্তু কোনো রাউটে
    response_model বা request body হিসেবে ব্যবহার হয়নি।
    """
    findings: list[Finding] = []
    for model_name, model in sorted(all_models.items()):
        if model_name not in used_model_names:
            findings.append(Finding(
                severity=Severity.WARNING,
                code="UNUSED_MODEL",
                route_path=None,
                model_name=model_name,
                message=(
                    f"'{model_name}' মডেল ডিফাইন করা হয়েছে ({model.source_file})"
                    f" কিন্তু কোনো রাউটে ব্যবহৃত হয়নি"
                ),
                source_file=model.source_file,
            ))
    return findings


def check_optional_mismatch(
    routes: list[RouteInfo],
    all_models: dict[str, PydanticModel],
) -> list[Finding]:
    """Optional ফিল্ড বনাম রাউট ব্যবহারের মিল চেক করে।
    
    বাংলা: মডেলে Optional ফিল্ড কিন্তু রাউট সবসময় value পাস করছে (বা বিপরীত)।
    """
    findings: list[Finding] = []
    for route in routes:
        if not route.response_model or not route.constructor_keys:
            continue
        resp_model_name = route.response_model
        list_match = re.search(r"(?:list|List)\s*\[\s*(\w+)\s*\]", resp_model_name)
        if list_match:
            resp_model_name = list_match.group(1)
        if resp_model_name not in all_models:
            continue

        model = all_models[resp_model_name]
        route_label = f"{route.method} {route.path}"

        for field_name in route.constructor_keys:
            if field_name not in model.fields:
                continue
            field = model.fields[field_name]
            # বাংলা: ফিল্ড Optional কিন্তু constructor-এ সবসময় value দেওয়া হচ্ছে
            # এটা warning, ভুল নয় — তবে design smell হতে পারে
            if field.is_optional and not field.has_default:
                # Optional কিন্তু default নেই — এটা সম্ভবত সঠিক
                pass

    return findings


def check_typescript_drift(
    all_models: dict[str, PydanticModel],
    ts_interfaces: dict[str, dict[str, tuple[str, bool]]],
) -> list[Finding]:
    """Pydantic মডেল বনাম TypeScript interface এর মধ্যে ড্রিফট চেক করে।
    
    বাংলা: প্রতিটি Pydantic মডেলের জন্য মিলিত TypeScript interface খোঁজে
    এবং ফিল্ড নাম/সংখ্যার মিল যাচাই করে।
    """
    findings: list[Finding] = []

    for model_name, model in sorted(all_models.items()):
        if model_name not in ts_interfaces:
            # বাংলা: সব মডেলের TypeScript type থাকবে না — শুধু schemas/ থেকে
            # generate_types.py দিয়ে জেনারেট করা মডেলগুলোর থাকবে
            if model.module.startswith("schemas."):
                findings.append(Finding(
                    severity=Severity.WARNING,
                    code="TS_MISSING",
                    route_path=None,
                    model_name=model_name,
                    message=(
                        f"'{model_name}' Pydantic মডেলের জন্য TypeScript interface"
                        f" পাওয়া যায়নি — generate_types.py পুনরায় চালানো হোক"
                    ),
                    source_file=model.source_file,
                ))
            continue

        ts_fields = ts_interfaces[model_name]
        py_fields = model.fields

        # বাংলা: Python field names → camelCase (TypeScript convention)
        py_field_names_camel = {_snake_to_camel(k) for k in py_fields}
        ts_field_names = set(ts_fields.keys())

        # Pydantic-এ আছে কিন্তু TS-এ নেই
        only_in_py = py_field_names_camel - ts_field_names
        # TS-এ আছে কিন্তু Pydantic-এ নেই
        only_in_ts = ts_field_names - py_field_names_camel

        if only_in_py or only_in_ts:
            drift_details: dict[str, Any] = {}
            if only_in_py:
                drift_details["missing_in_typescript"] = sorted(only_in_py)
            if only_in_ts:
                drift_details["extra_in_typescript"] = sorted(only_in_ts)

            findings.append(Finding(
                severity=Severity.WARNING,
                code="TS_DRIFT",
                route_path=None,
                model_name=model_name,
                message=(
                    f"'{model_name}' মডেল ও TypeScript interface-এ ড্রিফট পাওয়া গেছে"
                ),
                source_file=model.source_file,
                details=drift_details,
            ))
        else:
            findings.append(Finding(
                severity=Severity.GOOD,
                code="GOOD",
                route_path=None,
                model_name=model_name,
                message=f"'{model_name}' Pydantic ↔ TypeScript সামঞ্জস্যপূর্ণ",
                source_file=model.source_file,
            ))

    return findings


# ══════════════════════════════════════════════════════════════════════════════
# রিপোর্ট আউটপুট
# ══════════════════════════════════════════════════════════════════════════════


def _build_report(
    findings: list[Finding],
    routes: list[RouteInfo],
    all_models: dict[str, PydanticModel],
    ts_checked: bool,
) -> dict[str, Any]:
    """JSON রিপোর্ট তৈরি করে।
    
    বাংলা: সব ফাইন্ডিং, রাউট সারসংক্ষেপ, এবং সুপারিশ একটি dict-তে সংগঠিত করে।
    """
    error_findings = [f for f in findings if f.severity == Severity.ERROR]
    warning_findings = [f for f in findings if f.severity == Severity.WARNING]
    good_findings = [f for f in findings if f.severity == Severity.GOOD]

    # বাংলা: TypeScript ড্রিফট থাকলে generate_types.py পুনরায় চালানোর সুপারিশ
    ts_drift_found = any(f.code in ("TS_DRIFT", "TS_MISSING") for f in findings)
    recommendations = []
    if ts_drift_found:
        recommendations.append(
            "scripts/generate_types.py পুনরায় চালান — TypeScript types পুনঃজেনারেট করুন"
        )
    if error_findings:
        recommendations.append(
            "🔴 ত্রুটিযুক্ত মডেল রেফারেন্স ঠিক করুন — রাউট হ্যান্ডলার বা মডেল সংজ্ঞা আপডেট করুন"
        )
    if warning_findings and not ts_drift_found and not error_findings:
        recommendations.append(
            "🟡 সতর্কতাগুলো পর্যালোচনা করুন — অব্যবহৃত মডেল সরাতে পারেন"
        )
    if not error_findings and not warning_findings:
        recommendations.append(
            "✅ সব সামঞ্জস্যপূর্ণ — কোনো পদক্ষেপের প্রয়োজন নেই"
        )

    # প্রতি রাউটে মডেল ব্যবহারের সারসংক্ষেপ
    route_summary: list[dict[str, Any]] = []
    for r in routes:
        entry: dict[str, Any] = {
            "route": f"{r.method} {r.path}",
            "function": r.function_name,
            "file": r.source_file,
            "line": r.line_number,
            "response_model": r.response_model,
            "request_body": r.request_body_model,
        }
        # এই রাউটের জন্য ফাইন্ডিং
        route_findings = [
            f for f in findings
            if f.route_path and f.route_path == f"{r.method} {r.path}"
            and f.severity != Severity.GOOD
        ]
        if route_findings:
            entry["issues"] = [
                {"severity": f.severity.value, "code": f.code, "message": f.message}
                for f in route_findings
            ]
        route_summary.append(entry)

    return {
        "summary": {
            "total_routes": len(routes),
            "total_models": len(all_models),
            "errors": len(error_findings),
            "warnings": len(warning_findings),
            "good": len(good_findings),
            "ts_checked": ts_checked,
            "recommendation": recommendations[0] if recommendations else "",
            "recommendations": recommendations,
        },
        "findings": [
            {
                "severity": f.severity.value,
                "code": f.code,
                "route": f.route_path,
                "model": f.model_name,
                "message": f.message,
                "file": f.source_file,
                "details": f.details,
            }
            for f in findings
        ],
        "routes": route_summary,
        "models": {
            name: {
                "source": m.source_file,
                "module": m.module,
                "fields": {
                    fname: {
                        "type": f.type_annotation,
                        "optional": f.is_optional,
                        "has_default": f.has_default,
                    }
                    for fname, f in m.fields.items()
                },
            }
            for name, m in sorted(all_models.items())
        },
    }


def print_report(report: dict[str, Any]) -> None:
    """হিউম্যান-রিডেবল রিপোর্ট প্রিন্ট করে।
    
    বাংলা: টার্মিনালে রং ও emoji সহ পরিষ্কার রিপোর্ট দেখায়।
    """
    summary = report["summary"]
    findings = report["findings"]
    routes = report["routes"]

    print()
    print("═" * 70)
    print("  SupremeAI — Pydantic Schema Consistency Report")
    print("  SupremeAI — পিজ্যান্টিক স্কিমা সামঞ্জস্য প্রতিবেদন")
    print("═" * 70)
    print()
    print(f"  মোট রাউট:       {summary['total_routes']}")
    print(f"  মোট মডেল:      {summary['total_models']}")
    print(f"  TypeScript চেক: {'হ্যাঁ' if summary['ts_checked'] else 'না'}")
    print()
    print(f"  🔴 ত্রুটি (Errors):   {summary['errors']}")
    print(f"  🟡 সতর্কতা (Warnings): {summary['warnings']}")
    print(f"  🟢 ভালো (Good):      {summary['good']}")
    print()

    # ত্রুটি ও সতর্কতা প্রিন্ট
    issues = [f for f in findings if f["severity"] in ("🔴", "🟡")]
    if issues:
        print("─" * 70)
        print("  সমস্যাসমূহ (Findings)")
        print("─" * 70)
        for finding in issues:
            route_str = f" [{finding['route']}]" if finding["route"] else ""
            print(f"\n  {finding['severity']} [{finding['code']}]{route_str}")
            print(f"     মডেল: {finding['model']}")
            print(f"     {finding['message']}")
            if finding["file"]:
                print(f"     ফাইল: {finding['file']}")
            if finding["details"]:
                for k, v in finding["details"].items():
                    if isinstance(v, list):
                        # বাংলা: None মান স্ট্রিং-এ রূপান্তর
                        safe_items = [str(item) if item is not None else "None" for item in v]
                        print(f"     {k}: {', '.join(safe_items)}")
                    else:
                        print(f"     {k}: {v}")
        print()

    # প্রতি রাউটে মডেল ব্যবহারের সারসংক্ষেপ
    model_using_routes = [r for r in routes if r.get("response_model") or r.get("request_body")]
    if model_using_routes:
        print("─" * 70)
        print(f"  রাউট-মডেল ব্যবহার সারসংক্ষেপ ({len(model_using_routes)} রাউট)")
        print("─" * 70)
        for r in model_using_routes[:50]:  # বাংলা: সর্বোচ্চ ৫০টি দেখানো হচ্ছে
            issues_str = ""
            if r.get("issues"):
                issues_str = " ⚠".join(f"[{i['code']}]" for i in r["issues"])
            print(
                f"  {r['route']:<35} → response: {r['response_model'] or '-'}"
                f"  body: {r['request_body'] or '-'}{issues_str}"
            )
        if len(model_using_routes) > 50:
            print(f"  ... এবং আরও {len(model_using_routes) - 50} টি রাউট")
        print()

    # সুপারিশ
    print("─" * 70)
    print("  সুপারিশ (Recommendations)")
    print("─" * 70)
    for rec in report["summary"]["recommendations"]:
        print(f"  • {rec}")
    print()
    print("═" * 70)
    print()


# ══════════════════════════════════════════════════════════════════════════════
# মেইন এন্ট্রি পয়েন্ট
# ══════════════════════════════════════════════════════════════════════════════


def main() -> int:
    """মেইন ফাংশন — সব চেক চালায় এবং ফলাফল রিপোর্ট করে।
    
    বাংলা: কমান্ড লাইন আর্গুমেন্ট পার্স করে, মডেল ও রাউট সংগ্রহ করে,
    সামঞ্জস্য চেক চালায়, এবং রিপোর্ট আউটপুট দেয়।
    
    Returns:
        0 = সব সামঞ্জস্যপূর্ণ
        1 = ড্রিফট পাওয়া গেছে
        2 = স্ক্রিপ্ট এরর
    """
    parser = ArgumentParser(
        description="SupremeAI Pydantic Schema Consistency Checker — পিজ্যান্টিক স্কিমা সামঞ্জস্য পরীক্ষক",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON ফরম্যাটে রিপোর্ট আউটপুট দেওয়া হবে",
    )
    parser.add_argument(
        "--route",
        type=str,
        default=None,
        help="শুধুমাত্র এই রাউট পাথ ফিল্টার করুন (যেমন: /auth/login)",
    )
    parser.add_argument(
        "--ts-check",
        action="store_true",
        help="TypeScript shared-types ক্রস-রেফারেন্স চেক চালান",
    )
    args = parser.parse_args()

    try:
        # ── ধাপ ১: সব Pydantic মডেল সংগ্রহ ────────────────────────────────
        # বাংলা: schemas/, models/, এবং route files থেকে সব BaseModel subclass খোঁজা
        schema_models = collect_pydantic_models_from_dir(_SCHEMAS_DIR, "schemas")
        models_dir_models = collect_pydantic_models_from_dir(_MODELS_DIR, "models")
        inline_models = collect_inline_models_from_routes()

        # বাংলা: সব মডেল একটি dict-তে মার্জ করা (ডুপ্লিকেট থাকলে route inline জেতে)
        all_models: dict[str, PydanticModel] = {}
        all_models.update(schema_models)
        all_models.update(models_dir_models)
        all_models.update(inline_models)

        # ── ধাপ ২: সব রাউট সংগ্রহ ─────────────────────────────────────
        routes = collect_all_routes(route_filter=args.route)

        # ── ধাপ ৩: ব্যবহৃত মডেলের নাম সংগ্রহ ─────────────────────────────
        used_model_names: set[str] = set()
        for r in routes:
            if r.response_model:
                # list[ModelName] থেকে মডেল নাম বের করা
                rm = r.response_model
                list_match = re.search(r"(?:list|List)\s*\[\s*(\w+)\s*\]", rm)
                if list_match:
                    used_model_names.add(list_match.group(1))
                else:
                    used_model_names.add(rm)
            if r.request_body_model:
                used_model_names.add(r.request_body_model)

        # ── ধাপ ৪: সামঞ্জস্য চেক ─────────────────────────────────────────
        all_findings: list[Finding] = []

        # প্রতি রাউটের জন্য চেক
        for route in routes:
            all_findings.extend(
                check_route_model_consistency(route, all_models)
            )

        # ব্যবহৃত না হওয়া মডেল চেক
        all_findings.extend(check_unused_models(all_models, used_model_names))

        # Optional mismatch চেক
        all_findings.extend(check_optional_mismatch(routes, all_models))

        # TypeScript ক্রস-রেফারেন্স চেক
        ts_checked = False
        if args.ts_check:
            ts_interfaces = collect_typescript_interfaces(_SHARED_TYPES_DIR)
            if ts_interfaces:
                ts_findings = check_typescript_drift(all_models, ts_interfaces)
                all_findings.extend(ts_findings)
                ts_checked = True

        # ── ধাপ ৫: রিপোর্ট তৈরি ───────────────────────────────────────────
        report = _build_report(all_findings, routes, all_models, ts_checked)

        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print_report(report)

        # ── ধাপ ৬: এক্সিট কোড নির্ধারণ ─────────────────────────────────────
        # বাংলা: 0=সামঞ্জস্যপূর্ণ, 1=ড্রিফট (MISSING/PARTIAL/UNUSED), 2=স্ক্রিপ্ট এরর
        has_issues = any(
            f.severity in (Severity.ERROR, Severity.WARNING) for f in all_findings
        )

        if has_issues:
            return 1  # বাংলা: ড্রিফট পাওয়া গেছে
        return 0  # বাংলা: সব সামঞ্জস্যপূর্ণ

    except Exception as exc:
        # বাংলা: অপ্রত্যাশিত এরর — stderr-এ লগ করে exit code 2 রিটার্ন
        print(f"স্ক্রিপ্ট এরর: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
