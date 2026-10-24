#!/usr/bin/env python3
"""
SupremeAI Error Handling Consistency Checker
সমস্ত route handler-এ error handling-এর সামঞ্জস্য পরীক্ষা করে।
AST ব্যবহার করে backend/api/routes/*.py ফাইলগুলো বিশ্লেষণ করে।
"""

import ast
import argparse
import json
import os
import re
import sys
import textwrap
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Optional


# ──────────────────────────────────────────────
# ডেটা ক্লাস ও এনাম — ফলাফল ধারণ করার জন্য
# ──────────────────────────────────────────────

class Severity(Enum):
    """তীব্রতার স্তর"""
    CRITICAL = "CRITICAL"    # 🔴 গুরুতর — swallowed error, unhandled external call
    WARNING = "WARNING"      # 🟡 সতর্কতা — inconsistent status codes, mixed patterns
    GOOD = "GOOD"            # 🟢 ভালো — proper error handling


@dataclass
class Finding:
    """একটি একক পরীক্ষার ফলাফল"""
    severity: str           # CRITICAL, WARNING, GOOD
    category: str           # প্যাটার্নের ধরন
    message: str            # বিস্তারিত বর্ণনা
    file: str               # ফাইলের পথ
    function: str           # ফাংশনের নাম
    line: int = 0           # লাইন নম্বর


@dataclass
class FunctionAnalysis:
    """একটি route handler ফাংশনের বিশ্লেষণ"""
    name: str
    line: int
    decorators: list[str] = field(default_factory=list)
    has_try_except: bool = False
    has_http_exception: bool = False
    has_custom_exception: bool = False
    has_error_dict_return: bool = False
    has_swallowed_error: bool = False
    has_unhandled_external: bool = False
    has_logging_in_except: bool = False
    has_sensitive_leak: bool = False
    has_bare_try: bool = False
    external_calls: list[dict] = field(default_factory=list)
    http_exception_codes: list[int] = field(default_factory=list)
    http_exception_details: list[dict] = field(default_factory=list)  # [(code, detail_line), ...]
    findings: list[Finding] = field(default_factory=list)
    error_patterns_used: list[str] = field(default_factory=list)
    has_db_call_outside_try: bool = False
    has_db_call: bool = False
    db_calls: list[dict] = field(default_factory=list)


@dataclass
class FileAnalysis:
    """একটি ফাইলের সামগ্রিক বিশ্লেষণ"""
    filepath: str
    functions: list[FunctionAnalysis] = field(default_factory=list)
    consistency_score: float = 0.0
    findings: list[Finding] = field(default_factory=list)
    dominant_pattern: str = ""  # সবচেয়ে বেশি ব্যবহৃত error pattern
    pattern_counts: dict[str, int] = field(default_factory=dict)


# ──────────────────────────────────────────────
# সেনসিটিভ ডেটা সনাক্তকরণের প্যাটার্ন
# এই প্যাটার্নগুলো error response-এ থাকলে তা লিক হতে পারে
# ──────────────────────────────────────────────

SENSITIVE_PATTERNS = [
    (r'strace|stack.?trace|traceback', 'Stack trace লিক'),
    (r'/home/|/root/|/var/|/etc/|/opt/', 'অভ্যন্তরীণ পথ লিক'),
    (r'\bENV\b|os\.environ|getenv', 'Environment variable রেফারেন্স লিক'),
    (r'database_url|db_pass|connection_string', 'ডেটাবেস সংযোগ স্ট্রিং লিক'),
]

# f-string interpolation সহ সনাক্ত করার প্যাটার্ন
# এগুলো শুধুমাত্র f-string-এ ভেরিয়েবল ইন্টারপোলেশন থাকলে ফ্ল্যাগ হয়
SENSITIVE_FSTRING_PATTERNS = [
    (r'(?i)(password|passwd|secret).*(?:\{|%)', 'সংবেদনশীল ক্রেডেনশিয়াল f-string-এ লিক'),
    (r'(?i)(api_key|apikey|private_key).*(?:\{|%)', 'API কী/প্রাইভেট কী f-string-এ লিক'),
    (r'(?i)(?:\{|%s).*(?:token|secret|password|key)', 'সংবেদনশীল মান interpolation লিক'),
]

# লম্বা স্ট্রিং কনস্ট্যান্ট (সম্ভাব্য hardcoded secret)
QUOTES = '"' + "'"  # ডাবল ও সিঙ্গেল কোটেশন
LONG_STRING_PATTERN = ('f[' + QUOTES + '].*[A-Za-z0-9+/]{32,}.*[' + QUOTES + ']', 'সম্ভাব্য hardcoded secret লিক')


# ──────────────────────────────────────────────
# বহিরাগত API/HTTP কল সনাক্তকরণের প্যাটার্ন
# ──────────────────────────────────────────────

EXTERNAL_CALL_PATTERNS = {
    # (module, attribute) → বর্ণনা
    'httpx': ('httpx ক্লায়েন্ট কল', ['Client', 'AsyncClient', 'get', 'post', 'put', 'delete', 'patch', 'request']),
    'aiohttp': ('aiohttp কল', ['ClientSession', 'get', 'post', 'put', 'delete', 'request']),
    'requests': ('requests কল', ['get', 'post', 'put', 'delete', 'patch', 'request']),
    'fetch': ('fetch কল', ['fetch']),
    'urllib': ('urllib কল', ['urlopen', 'request']),
}


# ──────────────────────────────────────────────
# DB কল সনাক্তকরণের প্যাটার্ন
# ──────────────────────────────────────────────

DB_CALL_INDICATORS = [
    'execute', 'fetchall', 'fetchone', 'fetchmany', 'commit', 'rollback',
    'add', 'delete', 'query', 'get_or_404', 'scalar', 'stream',
    '.create(', '.find(', '.filter(', '.update(', '.first(', '.all(',
    'session.execute', 'session.add', 'session.commit', 'session.refresh',
    'db.execute', 'db.add', 'db.commit', 'db.refresh', 'db.delete',
    'async_session', 'AsyncSession',
]


# ──────────────────────────────────────────────
# AST বিশ্লেষণ ক্লাস
# ──────────────────────────────────────────────

class RouteAnalyzer(ast.NodeVisitor):
    """
    একটি Python ফাইলের AST ভিজিট করে route handler ফাংশনগুলো বিশ্লেষণ করে।
    প্রতিটি ফাংশনের error handling প্যাটার্ন সনাক্ত করে।
    """

    def __init__(self, filepath: str, source: str):
        self.filepath = filepath
        self.source = source
        self.source_lines = source.splitlines()
        self.functions: list[FunctionAnalysis] = []
        self._current_func: Optional[FunctionAnalysis] = None
        self._in_try: int = 0  # try ব্লকের নেস্টিং গভীরতা ট্র্যাক করে
        self._in_except: int = 0  # except ব্লকের নেস্টিং গভীরতা ট্র্যাক করে

    def _is_route_decorator(self, node: ast.expr) -> bool:
        """চেক করে কোনো ডেকোরেটর route handler কিনা"""
        # @router.get/post/put/delete/patch/options/head
        # @app.get/post/put/delete/patch/options/head
        # @api_router.get/post/...
        name = ""
        if isinstance(node, ast.Attribute):
            name = node.attr
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                name = node.func.attr
            elif isinstance(node.func, ast.Name):
                name = node.func.id
        route_methods = {'get', 'post', 'put', 'delete', 'patch', 'options', 'head', 'api_route', 'route'}
        return name.lower() in route_methods

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """প্রতিটি ফাংশন ডেফিনিশন পরিদর্শন করে"""
        # route decorator আছে কিনা চেক করি
        is_route = any(self._is_route_decorator(d) for d in node.decorator_list)
        if not is_route:
            self.generic_visit(node)
            return

        func = FunctionAnalysis(name=node.name, line=node.lineno)
        func.decorators = [ast.dump(d)[:100] for d in node.decorator_list]

        self._current_func = func
        self._in_try = 0
        self._in_except = 0
        self._analyze_function_body(node)

        # বিশ্লেষণ শেষে ফাংশন যোগ করি
        self.functions.append(func)
        self._current_func = None

        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def _analyze_function_body(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        """ফাংশনের বডি বিশ্লেষণ করে — সকল চেক এখানে"""
        self._check_try_except_patterns(node)
        self._check_raise_statements(node)
        self._check_return_error_dicts(node)
        self._check_external_calls(node)
        self._check_db_calls(node)
        self._check_sensitive_data(node)

    def _check_try_except_patterns(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        """
        try/except ব্লক বিশ্লেষণ:
        - bare try (except ছাড়া)
        - swallowed error (catch করে re-raise/return করছে না)
        - logging আছে কিনা
        """
        for child in ast.walk(node):
            if isinstance(child, ast.Try):
                # bare try চেক — except ব্লক নেই কিনা
                if not child.handlers:
                    if self._current_func:
                        self._current_func.has_bare_try = True
                        self._current_func.findings.append(Finding(
                            severity=Severity.CRITICAL.value,
                            category="BARE_TRY",
                            message=f"try ব্লকে কোনো except নেই — এক্সেপশন অপ্রত্যাশিতভাবে প্রপাগেট হবে",
                            file=self.filepath,
                            function=self._current_func.name,
                            line=child.lineno,
                        ))

                for handler in child.handlers:
                    if handler.type is None:
                        # bare except:
                        exception_name = "bare except"
                    elif isinstance(handler.type, ast.Name):
                        exception_name = handler.type.id
                    elif isinstance(handler.type, ast.Attribute):
                        exception_name = handler.type.attr
                    elif isinstance(handler.type, ast.Tuple):
                        # একাধিক exception type
                        names = []
                        for elt in handler.type.elts:
                            if isinstance(elt, ast.Name):
                                names.append(elt.id)
                            elif isinstance(elt, ast.Attribute):
                                names.append(elt.attr)
                        exception_name = ", ".join(names)
                    else:
                        exception_name = str(ast.dump(handler.type))[:50]

                    # swallowed error চেক — except ব্লকে raise/return আছে কিনা
                    body_has_raise = any(isinstance(n, ast.Raise) for n in ast.walk(handler))
                    body_has_return = any(isinstance(n, ast.Return) for n in handler.body)
                    body_has_return_with_error = False

                    for ret_node in handler.body:
                        if isinstance(ret_node, ast.Return) and ret_node.value is not None:
                            # return করা value-তে "error" আছে কিনা চেক
                            ret_str = ast.dump(ret_node.value).lower()
                            if 'error' in ret_str or 'detail' in ret_str or 'message' in ret_str:
                                body_has_return_with_error = True
                                break

                    # logging চেক
                    has_logging = False
                    for stmt in handler.body:
                        stmt_str = ast.dump(stmt)
                        if 'logger' in stmt_str or 'logging' in stmt_str or 'log.' in stmt_str:
                            has_logging = True
                            break

                    # শুধু logger.error(e) আছে কিনা — response নেই
                    is_only_logging = (
                        has_logging
                        and not body_has_raise
                        and not body_has_return
                        and not body_has_return_with_error
                    )

                    # Exception (বা তার subclass) catch করে কিছুই return/raise করছে না
                    is_generic_except = (
                        exception_name == 'Exception'
                        or exception_name == 'bare except'
                        or 'Exception' in exception_name
                        or 'BaseException' in exception_name
                    )

                    if self._current_func:
                        if is_generic_except and is_only_logging:
                            self._current_func.has_swallowed_error = True
                            self._current_func.findings.append(Finding(
                                severity=Severity.CRITICAL.value,
                                category="SWALLOWED_ERROR",
                                message=f"Exception caught but no response returned to client (only logging in except {exception_name})",
                                file=self.filepath,
                                function=self._current_func.name,
                                line=handler.lineno,
                            ))
                        elif is_generic_except and not body_has_raise and not body_has_return:
                            self._current_func.has_swallowed_error = True
                            self._current_func.findings.append(Finding(
                                severity=Severity.CRITICAL.value,
                                category="SWALLOWED_ERROR",
                                message=f"Generic {exception_name} caught but not re-raised or returned to client",
                                file=self.filepath,
                                function=self._current_func.name,
                                line=handler.lineno,
                            ))

                        if has_logging:
                            self._current_func.has_logging_in_except = True

    def _check_raise_statements(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        """
        raise স্টেটমেন্ট বিশ্লেষণ:
        - HTTPException raise করছে কিনা
        - Custom exception raise করছে কিনা
        - status code সংগ্রহ
        """
        if not self._current_func:
            return

        for child in ast.walk(node):
            if not isinstance(child, ast.Raise):
                continue

            if child.exc is None:
                # bare raise — ঠিক আছে, re-raise
                continue

            if isinstance(child.exc, ast.Call):
                func_node = child.exc.func
                call_str = ast.dump(func_node)

                # HTTPException চেক
                if isinstance(func_node, ast.Name) and func_node.id == 'HTTPException':
                    self._current_func.has_http_exception = True
                    self._current_func.error_patterns_used.append('HTTPException')
                    self._extract_http_exception_info(child.exc)

                elif isinstance(func_node, ast.Attribute) and func_node.attr == 'HTTPException':
                    self._current_func.has_http_exception = True
                    self._current_func.error_patterns_used.append('HTTPException')
                    self._extract_http_exception_info(child.exc)

                else:
                    # HTTPException নয় — custom exception
                    exc_name = ""
                    if isinstance(func_node, ast.Name):
                        exc_name = func_node.id
                    elif isinstance(func_node, ast.Attribute):
                        exc_name = func_node.attr

                    if exc_name and exc_name not in ('HTTPException', 'print', 'type', 'ValueError',
                                                       'TypeError', 'KeyError', 'IndexError',
                                                       'AttributeError', 'RuntimeError',
                                                       'NotImplementedError', 'StopIteration'):
                        self._current_func.has_custom_exception = True
                        self._current_func.error_patterns_used.append(f'CustomException({exc_name})')

    def _extract_http_exception_info(self, call_node: ast.Call) -> None:
        """HTTPException কল থেকে status code, detail text ও line নম্বর বের করে"""
        if not self._current_func:
            return

        code = None
        detail_text = ""

        # keyword args থেকে status_code ও detail বের করা
        for kw in call_node.keywords:
            if kw.arg == 'status_code':
                code = self._extract_constant(kw.value)
            elif kw.arg == 'detail':
                detail_text = self._extract_string_value(kw.value)

        # positional arg থেকে status code বের করা
        if code is None and call_node.args and not call_node.keywords:
            code = self._extract_constant(call_node.args[0])
            if not isinstance(code, int) or not (100 <= code <= 599):
                code = None

        if code is not None:
            self._current_func.http_exception_codes.append(code)
            self._current_func.http_exception_details.append({
                'code': code,
                'detail': detail_text,
                'line': call_node.lineno,
            })

    def _extract_string_value(self, node: ast.AST) -> str:
        """AST node থেকে string value বের করার চেষ্টা"""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        # f-string থেকে template string বের করা (parts concatenation)
        if isinstance(node, ast.JoinedStr):
            parts = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
            return " ".join(parts)
        return ""

    def _check_return_error_dicts(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        """
        Error dict return চেক:
        return {"error": ..., "detail": ...} বা return {"detail": ...}
        """
        if not self._current_func:
            return

        for child in ast.walk(node):
            if not isinstance(child, ast.Return) or child.value is None:
                continue

            if isinstance(child.value, ast.Dict):
                dict_str = ast.dump(child.value).lower()
                keys = []
                for k in child.value.keys:
                    if isinstance(k, ast.Constant):
                        keys.append(str(k.value).lower())

                has_error_key = any(k in ('error', 'errors', 'message', 'msg', 'detail',
                                          'success', 'status') for k in keys)
                if has_error_key:
                    self._current_func.has_error_dict_return = True
                    if 'ErrorDict' not in self._current_func.error_patterns_used:
                        self._current_func.error_patterns_used.append('ErrorDict')

    def _check_external_calls(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        """
        বহিরাগত HTTP/API কল সনাক্ত করে এবং তা try/except-এর ভেতরে আছে কিনা চেক করে।
        """
        if not self._current_func:
            return

        # প্রথমে সকল external call সংগ্রহ করি
        external_call_nodes = []
        for child in ast.walk(node):
            call_info = self._detect_external_call(child)
            if call_info:
                external_call_nodes.append((child, call_info))

        # তারপর চেক করি কোনোটি try/except-এর বাইরে আছে কিনা
        try_except_ranges = self._get_try_except_ranges(node)

        for call_node, info in external_call_nodes:
            self._current_func.external_calls.append(info)
            # কলটি কোনো try-এর ভেতরে আছে কিনা
            in_try = any(
                start <= call_node.lineno <= end
                for start, end in try_except_ranges
            )
            if not in_try:
                self._current_func.has_unhandled_external = True
                self._current_func.findings.append(Finding(
                    severity=Severity.CRITICAL.value,
                    category="UNHANDLED_EXTERNAL",
                    message=f"{info['type']} — {info['description']} (line {call_node.lineno}) কোনো try/except-এর বাইরে",
                    file=self.filepath,
                    function=self._current_func.name,
                    line=call_node.lineno,
                ))

    def _check_db_calls(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        """
        DB কল সনাক্ত করে এবং try/except-এর ভেতরে আছে কিনা চেক করে।
        """
        if not self._current_func:
            return

        db_call_nodes = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call_str = ast.dump(child)
                if isinstance(child.func, ast.Attribute):
                    attr = child.func.attr
                    if any(indicator in attr for indicator in DB_CALL_INDICATORS):
                        db_call_nodes.append((child, attr))
                    # session.method() প্যাটার্ন
                    elif isinstance(child.func.value, ast.Name):
                        obj_name = child.func.value.id.lower()
                        if obj_name in ('session', 'db', 'async_session', 'conn', 'connection'):
                            db_call_nodes.append((child, f"{child.func.value.id}.{attr}"))

        try_except_ranges = self._get_try_except_ranges(node)

        for call_node, attr in db_call_nodes:
            self._current_func.has_db_call = True
            self._current_func.db_calls.append({'attribute': attr, 'line': call_node.lineno})
            in_try = any(
                start <= call_node.lineno <= end
                for start, end in try_except_ranges
            )
            if not in_try:
                self._current_func.has_db_call_outside_try = True
                self._current_func.findings.append(Finding(
                    severity=Severity.WARNING.value,
                    category="UNHANDLED_DB_CALL",
                    message=f"DB কল `.{attr}()` (line {call_node.lineno}) কোনো try/except-এর বাইরে",
                    file=self.filepath,
                    function=self._current_func.name,
                    line=call_node.lineno,
                ))

    def _check_sensitive_data(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        """
        Error response-এ সেনসিটিভ ডেটা লিক চেক করে।
        stack trace, internal paths, env var names ইত্যাদি।
        """
        if not self._current_func:
            return

        # ফাংশনের সোর্স কোড পরিদর্শন
        func_source = self._get_function_source(node)

        for pattern, description in SENSITIVE_PATTERNS:
            # শুধু error/raise/except context-এ সনাক্ত করি
            for line_idx, line in enumerate(func_source.splitlines()):
                line_lower = line.lower()
                # error context-এ আছে কিনা চেক
                if any(kw in line_lower for kw in ['error', 'raise', 'except', 'detail=', 'return', 'message']):
                    if re.search(pattern, line, re.IGNORECASE):
                        self._current_func.has_sensitive_leak = True
                        self._current_func.findings.append(Finding(
                            severity=Severity.WARNING.value,
                            category="SENSITIVE_LEAK",
                            message=f"{description} সনাক্ত — `{line.strip()[:80]}`",
                            file=self.filepath,
                            function=self._current_func.name,
                            line=node.lineno + line_idx,
                        ))
                        break  # প্রতিটি প্যাটার্নের জন্য একবারই রিপোর্ট

        # f-string interpolation-এর সাথে সংবেদনশীল ডেটা চেক
        for pattern, description in SENSITIVE_FSTRING_PATTERNS:
            for line_idx, line in enumerate(func_source.splitlines()):
                if 'f"' in line or "f'" in line:
                    if re.search(pattern, line, re.IGNORECASE):
                        self._current_func.has_sensitive_leak = True
                        self._current_func.findings.append(Finding(
                            severity=Severity.WARNING.value,
                            category="SENSITIVE_LEAK",
                            message=f"{description} সনাক্ত — `{line.strip()[:80]}`",
                            file=self.filepath,
                            function=self._current_func.name,
                            line=node.lineno + line_idx,
                        ))
                        break

        # লম্বা hardcoded string চেক
        pattern, description = LONG_STRING_PATTERN
        for line_idx, line in enumerate(func_source.splitlines()):
            if re.search(pattern, line):
                # শুধু error/raise context-এ
                if any(kw in line.lower() for kw in ['error', 'detail', 'return', 'raise']):
                    self._current_func.has_sensitive_leak = True
                    self._current_func.findings.append(Finding(
                        severity=Severity.WARNING.value,
                        category="SENSITIVE_LEAK",
                        message=f"{description} সনাক্ত — `{line.strip()[:80]}`",
                        file=self.filepath,
                        function=self._current_func.name,
                        line=node.lineno + line_idx,
                    ))
                    break

    def _detect_external_call(self, node: ast.AST) -> Optional[dict]:
        """একটি AST node থেকে external call সনাক্ত করে"""
        if not isinstance(node, ast.Call):
            return None

        call_str = ast.dump(node)

        # httpx.Client().get(...), httpx.post(...), ইত্যাদি
        if isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            # httpx/aiohttp/requests method calls
            if isinstance(node.func.value, ast.Name):
                obj = node.func.value.id
                if obj in EXTERNAL_CALL_PATTERNS:
                    desc, methods = EXTERNAL_CALL_PATTERNS[obj]
                    if attr in methods or any(m in attr for m in methods):
                        return {'type': obj, 'description': f'{obj}.{attr}()', 'line': node.lineno}

            # .client.get(...), .session.post(...) — common pattern
            if attr in ('get', 'post', 'put', 'delete', 'patch', 'request', 'fetch'):
                if isinstance(node.func.value, ast.Attribute):
                    if isinstance(node.func.value.value, ast.Name):
                        parent = node.func.value.value.id
                        if parent in ('httpx', 'aiohttp', 'requests', 'client', 'session',
                                      'http_client', 'api_client', 'async_client'):
                            return {
                                'type': parent,
                                'description': f'{parent}.{node.func.value.attr}.{attr}()',
                                'line': node.lineno
                            }

        # fetch() global call
        if isinstance(node.func, ast.Name) and node.func.id == 'fetch':
            return {'type': 'fetch', 'description': 'fetch()', 'line': node.lineno}

        return None

    def _get_try_except_ranges(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[tuple[int, int]]:
        """ফাংশনে সকল try/except ব্লকের (start, end) লাইন রেঞ্জ দেয়"""
        ranges = []
        for child in ast.walk(node):
            if isinstance(child, ast.Try):
                if child.handlers:  # শুধুমাত্র যেগুলোতে except আছে
                    start = child.lineno
                    end = child.end_lineno or child.lineno
                    # try body + all handlers + else + finally
                    for handler in child.handlers:
                        if handler.end_lineno:
                            end = max(end, handler.end_lineno)
                    if child.finalbody:
                        for fb in child.finalbody:
                            if hasattr(fb, 'end_lineno') and fb.end_lineno:
                                end = max(end, fb.end_lineno)
                    if child.orelse:
                        for ol in child.orelse:
                            if hasattr(ol, 'end_lineno') and ol.end_lineno:
                                end = max(end, ol.end_lineno)
                    ranges.append((start, end))
        return ranges

    def _get_function_source(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        """ফাংশনের সোর্স কোড টেক্সট রিটার্ন করে"""
        start = node.lineno - 1
        end = node.end_lineno or node.lineno
        lines = self.source_lines[start:end]
        return "\n".join(lines)

    def _extract_constant(self, node: ast.AST) -> Any:
        """AST node থেকে constant value বের করে"""
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            val = self._extract_constant(node.operand)
            if val is not None:
                return -val
        return None


# ──────────────────────────────────────────────
# সামগ্রিক বিশ্লেষণ ও স্কোর গণনা
# ──────────────────────────────────────────────

class ConsistencyChecker:
    """
    সকল ফাইল বিশ্লেষণ করে সামগ্রিক রিপোর্ট তৈরি করে।
    consistency score গণনা করে এবং cross-file চেক করে।
    """

    def __init__(self, routes_dir: str):
        self.routes_dir = Path(routes_dir)
        self.file_analyses: list[FileAnalysis] = []
        self.all_findings: list[Finding] = []
        self.total_functions = 0
        self.total_critical = 0
        self.total_warning = 0
        self.total_good = 0

    def analyze_all(self, target_file: Optional[str] = None) -> None:
        """সকল route ফাইল বিশ্লেষণ করে"""
        if target_file:
            files = [Path(target_file)]
        else:
            files = sorted(self.routes_dir.glob("*.py"))

        for filepath in files:
            if not filepath.exists():
                print(f"❌ ফাইল পাওয়া যায়নি: {filepath}", file=sys.stderr)
                continue

            try:
                source = filepath.read_text(encoding='utf-8', errors='replace')
                tree = ast.parse(source, filename=str(filepath))
            except SyntaxError as e:
                print(f"❌ সিনট্যাক্স ত্রুটি {filepath}: {e}", file=sys.stderr)
                continue

            analyzer = RouteAnalyzer(str(filepath), source)
            analyzer.visit(tree)

            file_analysis = FileAnalysis(filepath=str(filepath))
            file_analysis.functions = analyzer.functions

            # প্রতিটি ফাইলের error pattern গণনা
            pattern_counts = defaultdict(int)
            for func in analyzer.functions:
                for pattern in func.error_patterns_used:
                    pattern_counts[pattern] += 1
                # কোনো pattern না থাকলে "None" হিসেবে গণনা
                if not func.error_patterns_used and not func.has_try_except:
                    pattern_counts["NoErrorHandling"] += 1
            file_analysis.pattern_counts = dict(pattern_counts)

            # dominant pattern নির্ধারণ
            if pattern_counts:
                file_analysis.dominant_pattern = max(pattern_counts, key=pattern_counts.get)

            # ফাইলের findings সংগ্রহ
            for func in analyzer.functions:
                file_analysis.findings.extend(func.findings)

            # ফাইল-লেভেল mixed pattern চেক
            self._check_mixed_patterns(file_analysis)

            # সামঞ্জস্য স্কোর গণনা
            file_analysis.consistency_score = self._calculate_consistency_score(file_analysis)

            self.file_analyses.append(file_analysis)
            self.total_functions += len(analyzer.functions)
            self.all_findings.extend(file_analysis.findings)

        # Cross-file inconsistent status code চেক
        self._check_inconsistent_status_codes()

        # গণনা
        self.total_critical = sum(1 for f in self.all_findings if f.severity == Severity.CRITICAL.value)
        self.total_warning = sum(1 for f in self.all_findings if f.severity == Severity.WARNING.value)

    def _calculate_consistency_score(self, file_analysis: FileAnalysis) -> float:
        """
        প্রতিটি ফাইলের জন্য 0-100% consistency score গণনা করে।
        স্কোর নির্ধারণের নিয়ম:
        - সকল ফাংশন একই pattern ব্যবহার করলে 100%
        - প্রতিটি swallowed error-এ 20 পয়েন্ট কাটা যায়
        - প্রতিটি unhandled external call-এ 15 পয়েন্ট কাটা যায়
        - mixed pattern থাকলে 20 পয়েন্ট কাটা যায়
        - সেনসিটিভ ডেটা লিক থাকলে 10 পয়েন্ট কাটা যায়
        """
        if not file_analysis.functions:
            return 100.0

        score = 100.0
        func_count = len(file_analysis.functions)

        # pattern consistency চেক
        patterns_used = set()
        has_no_handling = False
        for func in file_analysis.functions:
            if func.error_patterns_used:
                patterns_used.update(func.error_patterns_used)
            elif not func.has_try_except:
                has_no_handling = True

        # একাধিক pattern থাকলে পয়েন্ট কাটা
        if len(patterns_used) > 1:
            score -= 20.0
        # কিছু ফাংশনে handling আছে, কিছুতে নেই
        if patterns_used and has_no_handling:
            score -= 15.0

        # প্রতিটি সমস্যার জন্য পয়েন্ট কাটা
        for finding in file_analysis.findings:
            if finding.severity == Severity.CRITICAL.value:
                if finding.category == "SWALLOWED_ERROR":
                    score -= 20.0
                elif finding.category in ("UNHANDLED_EXTERNAL", "BARE_TRY"):
                    score -= 15.0
            elif finding.severity == Severity.WARNING.value:
                if finding.category == "SENSITIVE_LEAK":
                    score -= 10.0
                elif finding.category == "MIXED_PATTERNS":
                    score -= 5.0

        # ফাংশন সংখ্যা অনুযায়ী প্রাপ্তি সংশোধন
        # অনেক ফাংশন থাকলে কিছু সমস্যা থাকা স্বাভাবিক
        if func_count > 5:
            score = min(100.0, score + 5.0)

        # logging আছে কিনা — বোনাস
        logged_funcs = sum(1 for f in file_analysis.functions if f.has_logging_in_except)
        if logged_funcs > 0 and func_count > 0:
            ratio = logged_funcs / func_count
            if ratio > 0.5:
                score = min(100.0, score + 5.0)

        return max(0.0, min(100.0, round(score, 1)))

    def _check_mixed_patterns(self, file_analysis: FileAnalysis) -> None:
        """
        একই ফাইলে ভিন্ন ভিন্ন error handling pattern ব্যবহার করা হচ্ছে কিনা চেক করে।
        """
        if len(file_analysis.functions) < 2:
            return

        patterns_by_func = {}
        for func in file_analysis.functions:
            if func.error_patterns_used:
                patterns_by_func[func.name] = set(func.error_patterns_used)
            else:
                patterns_by_func[func.name] = {"NoErrorHandling"}

        all_patterns = set()
        for pset in patterns_by_func.values():
            all_patterns.update(pset)

        # একাধিক ভিন্ন pattern থাকলে warning
        error_patterns = all_patterns - {"NoErrorHandling"}
        if len(error_patterns) > 1:
            pattern_list = ", ".join(sorted(error_patterns))
            file_analysis.findings.append(Finding(
                severity=Severity.WARNING.value,
                category="MIXED_PATTERNS",
                message=f"একই ফাইলে ভিন্ন error patterns ব্যবহৃত: {pattern_list}",
                file=file_analysis.filepath,
                function="(file-level)",
                line=0,
            ))

    def _check_inconsistent_status_codes(self) -> None:
        """
        Cross-file inconsistent status code চেক করে।
        উদাহরণ: এক রাউটে 404, অন্যে 400 ব্যবহার করে "not found" এর জন্য।
        HTTPException-এর detail/message-এর context অনুযায়ী status code match করে।
        """
        # scenario-অনুযায়ী keywords ও expected codes
        scenario_keywords = {
            'not_found': {
                'keywords': ['not found', 'not_found', 'does not exist', 'not exist',
                             'no such', 'not available', 'couldn\'t find', 'could not find'],
                'expected': 404,
            },
            'unauthorized': {
                'keywords': ['unauthorized', 'unauthenticated', 'not authenticated',
                             'invalid_token', 'token expired', 'expired token',
                             'authentication required', 'not authorized'],
                'expected': 401,
            },
            'forbidden': {
                'keywords': ['forbidden', 'access denied', 'no permission',
                             'insufficient permission', 'not allowed'],
                'expected': 403,
            },
            'validation': {
                'keywords': ['validation error', 'validation failed', 'invalid input',
                             'invalid request body', 'malformed request', 'invalid field',
                             'missing required', 'required field'],
                'expected': 422,
            },
            'conflict': {
                'keywords': ['already exists', 'conflict', 'duplicate', 'already taken'],
                'expected': 409,
            },
        }

        # প্রতিটি scenario-এর জন্য entries সংগ্রহ
        scenario_codes = {name: [] for name in scenario_keywords}

        for fa in self.file_analyses:
            for func in fa.functions:
                for detail_info in func.http_exception_details:
                    code = detail_info['code']
                    detail_lower = detail_info['detail'].lower()
                    if not detail_lower:
                        continue  # detail না থাকলে চেক করা যায় না

                    for scenario, config in scenario_keywords.items():
                        for kw in config['keywords']:
                            if kw in detail_lower:
                                scenario_codes[scenario].append({
                                    'code': code,
                                    'file': fa.filepath,
                                    'func': func.name,
                                    'line': detail_info['line'],
                                })
                                break  # প্রথম matching keyword-এ থামি

        # inconsistency চেক
        for scenario, entries in scenario_codes.items():
            expected = scenario_keywords[scenario]['expected']
            self._report_code_inconsistency(entries, scenario, expected)

    def _report_code_inconsistency(self, entries: list[dict], scenario: str, expected: int) -> None:
        """status code inconsistency রিপোর্ট করে"""
        if len(entries) < 2:
            return

        codes_used = set(e['code'] for e in entries)
        if len(codes_used) <= 1:
            return

        # প্রতিটি ভিন্ন code-এর জন্য finding তৈরি
        for entry in entries:
            if entry['code'] != expected:
                self.all_findings.append(Finding(
                    severity=Severity.WARNING.value,
                    category="INCONSISTENT_STATUS_CODE",
                    message=(f'"{scenario}" এর জন্য status_code={entry["code"]} ব্যবহৃত '
                            f'(প্রত্যাশিত {expected})'),
                    file=entry['file'],
                    function=entry['func'],
                    line=entry['line'],
                ))

    def _get_func_source_from_analysis(self, fa: FileAnalysis, func: FunctionAnalysis) -> str:
        """file analysis থেকে ফাংশনের সোর্স কোড আনার চেষ্টা করে"""
        try:
            source = Path(fa.filepath).read_text(encoding='utf-8', errors='replace')
            lines = source.splitlines()
            start = func.line - 1
            end = min(start + 80, len(lines))  # সর্বোচ্চ 80 লাইন পড়ি
            return "\n".join(lines[start:end])
        except Exception:
            return ""

    def get_good_handlers(self) -> list[FunctionAnalysis]:
        """সঠিকভাবে error handling করা ফাংশনগুলো দেয়"""
        good = []
        for fa in self.file_analyses:
            for func in fa.functions:
                if (func.has_try_except and (func.has_http_exception or func.has_error_dict_return)
                        and not func.has_swallowed_error and not func.has_unhandled_external
                        and not func.has_sensitive_leak):
                    good.append(func)
        return good

    def get_average_score(self) -> float:
        """সকল ফাইলের গড় consistency score"""
        if not self.file_analyses:
            return 0.0
        return round(sum(fa.consistency_score for fa in self.file_analyses) / len(self.file_analyses), 1)


# ──────────────────────────────────────────────
# রিপোর্ট জেনারেটর
# ──────────────────────────────────────────────

class ReportGenerator:
    """
    বিশ্লেষণের ফলাফল থেকে মার্কডাউন বা JSON রিপোর্ট তৈরি করে।
    """

    def __init__(self, checker: ConsistencyChecker, severity_only: bool = False):
        self.checker = checker
        self.severity_only = severity_only

    def generate_markdown(self) -> str:
        """সম্পূর্ণ মার্কডাউন রিপোর্ট তৈরি করে"""
        lines = []
        lines.append("# 🔍 Error Handling Consistency Report")
        lines.append("")
        lines.append(f"**পরীক্ষিত ফাইল:** {len(self.checker.file_analyses)}")
        lines.append(f"**পরীক্ষিত route handler:** {self.checker.total_functions}")
        lines.append(f"**গড় consistency score:** {self.checker.get_average_score()}%")
        lines.append("")

        # সারসংক্ষেপ টেবিল
        lines.append("## 📊 সারসংক্ষেপ")
        lines.append("")
        lines.append("| তীব্রতা | সংখ্যা |")
        lines.append("|--------|--------|")
        lines.append(f"| 🔴 CRITICAL | {self.checker.total_critical} |")
        lines.append(f"| 🟡 WARNING | {self.checker.total_warning} |")
        lines.append(f"| 🟢 সঠিক handler | {len(self.checker.get_good_handlers())} |")
        lines.append("")

        # per-file score
        lines.append("## 📁 ফাইল অনুযায়ী Consistency Score")
        lines.append("")
        lines.append("| ফাইল | Score | ফাংশন | প্রধান Pattern | সমস্যা |")
        lines.append("|------|-------|--------|---------------|--------|")

        for fa in sorted(self.checker.file_analyses, key=lambda x: x.consistency_score):
            fname = Path(fa.filepath).name
            issue_count = len([f for f in fa.findings if f.severity != Severity.GOOD.value])
            score_emoji = self._score_emoji(fa.consistency_score)
            lines.append(
                f"| {score_emoji} {fname} | {fa.consistency_score}% | "
                f"{len(fa.functions)} | {fa.dominant_pattern or 'N/A'} | {issue_count} |"
            )
        lines.append("")

        if self.severity_only:
            # শুধুমাত্র severity দেখাও
            lines.append("## 🔴🟡 সমস্যাগুলো (Severity Only)")
            lines.append("")
            self._append_findings_by_severity(lines)
            return "\n".join(lines)

        # সমস্যার বিস্তারিত
        lines.append("## 🔴 Critical সমস্যা")
        lines.append("")
        critical = [f for f in self.checker.all_findings if f.severity == Severity.CRITICAL.value]
        if critical:
            for finding in critical:
                fname = Path(finding.file).name
                lines.append(f"### `{fname}` → `{finding.function}` (line {finding.line})")
                lines.append(f"- **{finding.category}**: {finding.message}")
                lines.append("")
        else:
            lines.append("✅ কোনো critical সমস্যা নেই!")
            lines.append("")

        lines.append("## 🟡 Warning")
        lines.append("")
        warnings = [f for f in self.checker.all_findings if f.severity == Severity.WARNING.value]
        if warnings:
            for finding in warnings:
                fname = Path(finding.file).name
                lines.append(f"### `{fname}` → `{finding.function}` (line {finding.line})")
                lines.append(f"- **{finding.category}**: {finding.message}")
                lines.append("")
        else:
            lines.append("✅ কোনো warning নেই!")
            lines.append("")

        # ভালো প্র্যাকটিস তালিকা
        good_handlers = self.checker.get_good_handlers()
        if good_handlers:
            lines.append("## 🟢 সঠিক Error Handling")
            lines.append("")
            for func in good_handlers[:20]:  # সর্বোচ্চ 20টি দেখাও
                fname = Path(func.name).name if hasattr(func, 'filepath') else ""
                patterns = ", ".join(func.error_patterns_used) if func.error_patterns_used else "try/except"
                logging = "✅ logging" if func.has_logging_in_except else "⚠️ no logging"
                lines.append(f"- `{func.name}` — {patterns} — {logging}")
            if len(good_handlers) > 20:
                lines.append(f"- ... এবং আরো {len(good_handlers) - 20} টি")
            lines.append("")

        # প্যাটার্ন বিশ্লেষণ
        lines.append("## 📈 Pattern বিশ্লেষণ")
        lines.append("")
        pattern_totals = defaultdict(int)
        for fa in self.checker.file_analyses:
            for p, c in fa.pattern_counts.items():
                pattern_totals[p] += c

        if pattern_totals:
            lines.append("| Pattern | ব্যবহার |")
            lines.append("|---------|--------|")
            for pattern, count in sorted(pattern_totals.items(), key=lambda x: -x[1]):
                lines.append(f"| {pattern} | {count} |")
            lines.append("")

        # সুপারিশ
        lines.append("## 💡 সুপারিশ")
        lines.append("")
        recommendations = self._generate_recommendations()
        for rec in recommendations:
            lines.append(f"- {rec}")
        lines.append("")

        return "\n".join(lines)

    def _append_findings_by_severity(self, lines: list[str]) -> None:
        """শুধুমাত্র severity অনুযায়ী findings যোগ করে"""
        for finding in self.checker.all_findings:
            if finding.severity == Severity.GOOD.value:
                continue
            emoji = "🔴" if finding.severity == Severity.CRITICAL.value else "🟡"
            fname = Path(finding.file).name
            lines.append(
                f"{emoji} **[{finding.severity}]** `{fname}:{finding.function}:{finding.line}` "
                f"— {finding.category}: {finding.message}"
            )
        lines.append("")

    def generate_json(self) -> str:
        """JSON ফরম্যাটে রিপোর্ট তৈরি করে"""
        result = {
            "summary": {
                "files_analyzed": len(self.checker.file_analyses),
                "total_functions": self.checker.total_functions,
                "average_score": self.checker.get_average_score(),
                "critical_count": self.checker.total_critical,
                "warning_count": self.checker.total_warning,
                "good_handlers": len(self.checker.get_good_handlers()),
            },
            "files": [],
            "findings": [],
        }

        for fa in self.checker.file_analyses:
            file_data = {
                "filepath": fa.filepath,
                "consistency_score": fa.consistency_score,
                "functions": len(fa.functions),
                "dominant_pattern": fa.dominant_pattern,
                "pattern_counts": fa.pattern_counts,
                "function_details": [],
            }
            for func in fa.functions:
                func_data = {
                    "name": func.name,
                    "line": func.line,
                    "has_try_except": func.has_try_except,
                    "patterns_used": func.error_patterns_used,
                    "has_swallowed_error": func.has_swallowed_error,
                    "has_unhandled_external": func.has_unhandled_external,
                    "has_sensitive_leak": func.has_sensitive_leak,
                    "has_logging": func.has_logging_in_except,
                    "http_status_codes": func.http_exception_codes,
                    "findings": [asdict(f) for f in func.findings],
                }
                file_data["function_details"].append(func_data)
            result["files"].append(file_data)

        result["findings"] = [asdict(f) for f in self.checker.all_findings]

        return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    def _generate_recommendations(self) -> list[str]:
        """বিশ্লেষণের ভিত্তিতে সুপারিশ তৈরি করে"""
        recs = []

        swallowed = [f for f in self.checker.all_findings if f.category == "SWALLOWED_ERROR"]
        if swallowed:
            recs.append(
                f"🔴 **{len(swallowed)}টি swallowed error** পাওয়া গেছে। প্রতিটি `except` ব্লকে HTTPException raise করুন বা error dict return করুন।"
            )

        unhandled = [f for f in self.checker.all_findings if f.category == "UNHANDLED_EXTERNAL"]
        if unhandled:
            recs.append(
                f"🔴 **{len(unhandled)}টি unhandled external call** পাওয়া গেছে। সকল HTTP/API কল try/except-এ মুড়ুন।"
            )

        mixed = [f for f in self.checker.all_findings if f.category == "MIXED_PATTERNS"]
        if mixed:
            recs.append(
                f"🟡 **{len(mixed)}টি ফাইলে mixed patterns** আছে। একটি মাত্র error handling strategy বেছে নিন (HTTPException সুপারিশকৃত)।"
            )

        inconsistent = [f for f in self.checker.all_findings if f.category == "INCONSISTENT_STATUS_CODE"]
        if inconsistent:
            recs.append(
                f"🟡 **{len(inconsistent)}টি inconsistent status code** আছে। একই error condition-এ সবজায়গায় একই status code ব্যবহার করুন।"
            )

        leaks = [f for f in self.checker.all_findings if f.category == "SENSITIVE_LEAK"]
        if leaks:
            recs.append(
                f"🟡 **{len(leaks)}টি সম্ভাব্য sensitive data leak** পাওয়া গেছে। Error response-এ স্ট্যাক ট্রেস বা অভ্যন্তরীণ পথ দেবেন না।"
            )

        # Logging check
        total_excepts = 0
        logged_excepts = 0
        for fa in self.checker.file_analyses:
            for func in fa.functions:
                if func.has_try_except:
                    total_excepts += 1
                    if func.has_logging_in_except:
                        logged_excepts += 1

        if total_excepts > 0:
            log_ratio = (logged_excepts / total_excepts) * 100
            if log_ratio < 80:
                recs.append(
                    f"📝 শুধুমাত্র {log_ratio:.0f}% except ব্লকে logging আছে। সকল error handler-এ `logger.error()` যোগ করুন।"
                )

        if not recs:
            recs.append("✅ সকল route-এ error handling সামঞ্জস্যপূর্ণ! চমৎকার কাজ!")

        return recs

    def _score_emoji(self, score: float) -> str:
        """score অনুযায়ী emoji দেয়"""
        if score >= 90:
            return "🟢"
        elif score >= 70:
            return "🟡"
        elif score >= 50:
            return "🟠"
        else:
            return "🔴"


# ──────────────────────────────────────────────
# CLI এন্ট্রি পয়েন্ট
# ──────────────────────────────────────────────

def main():
    """
    স্ক্রিপ্টের মূল এন্ট্রি পয়েন্ট। CLI আর্গুমেন্ট পার্স করে বিশ্লেষণ চালায়।
    এক্সিট কোড: 0=consistent, 1=inconsistencies, 2=errors
    """
    # রিপো রুট থেকে routes ডিরেক্টরি নির্ধারণ
    repo_root = Path(__file__).resolve().parents[2]
    default_routes = repo_root / "backend" / "api" / "routes"

    parser = argparse.ArgumentParser(
        description="SupremeAI Error Handling Consistency Checker — route handler-এ error handling পরীক্ষা করে",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            উদাহরণ:
              python error_handling_consistency_checker.py
              python error_handling_consistency_checker.py --json
              python error_handling_consistency_checker.py --file backend/api/routes/users.py
              python error_handling_consistency_checker.py --severity-only
        """),
    )
    parser.add_argument(
        "--routes-dir",
        type=str,
        default=str(default_routes),
        help=f"routes ডিরেক্টরির পথ (default: {default_routes})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="JSON ফরম্যাটে আউটপুট",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="নির্দিষ্ট একটি ফাইল পরীক্ষা করুন",
    )
    parser.add_argument(
        "--severity-only",
        action="store_true",
        help="শুধুমাত্র severity সহ findings দেখান",
    )

    args = parser.parse_args()

    # routes ডিরেক্টরি আছে কিনা চেক
    routes_path = Path(args.routes_dir)
    if not args.file and not routes_path.exists():
        print(f"❌ Routes ডিরেক্টরি পাওয়া যায়নি: {routes_path}", file=sys.stderr)
        print(f"   --routes-dir দিয়ে সঠিক পথ নির্দিষ্ট করুন", file=sys.stderr)
        sys.exit(2)

    # বিশ্লেষণ চালানো
    try:
        checker = ConsistencyChecker(args.routes_dir)
        checker.analyze_all(target_file=args.file)
    except Exception as e:
        print(f"❌ বিশ্লেষণে ত্রুটি: {e}", file=sys.stderr)
        sys.exit(2)

    # রিপোর্ট তৈরি
    reporter = ReportGenerator(checker, severity_only=args.severity_only)

    if args.output_json:
        print(reporter.generate_json())
    else:
        print(reporter.generate_markdown())

    # এক্সিট কোড নির্ধারণ
    # 0 = সম্পূর্ণ সামঞ্জস্যপূর্ণ
    # 1 = inconsistency আছে
    # 2 = রান টাইম ত্রুটি (ইতিমধ্যে handle করা হয়েছে)
    if checker.total_critical > 0 or checker.total_warning > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
