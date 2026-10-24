#!/usr/bin/env python3
"""endpoint_timeout_auditor.py — এন্ডপয়েন্ট টাইমআউট অডিটর

SupremeAI কোডবেসের সকল route handler-এ বাহ্যিক কল (LLM, HTTP, DB, browser)
-এর timeout কভারেজ অডিট করে। প্রতিটি এন্ডপয়েন্টের জন্য:
  🔴 কোনো টাইমআউট নেই  |  🟡 গ্লোবাল ডিফল্ট নির্ভরশীল
  🟢 স্পষ্ট টাইমআউট    |  🔵 অত্যধিক দীর্ঘ/স্বল্প

ব্যবহার:
  python scripts/endpoint_timeout_auditor.py
  python scripts/endpoint_timeout_auditor.py --json
  python scripts/endpoint_timeout_auditor.py --route /api/chat/get_completion
  python scripts/endpoint_timeout_auditor.py --llm-only

এক্সিট কোড: 0=সব কভার্ড, 1=টাইমআউট অনুপস্থিত, 2=স্ক্রিপ্ট ত্রুটি
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
from enum import Enum
from pathlib import Path
from typing import Any


# ── ধ্রুবক ────────────────────────────────────────────────────────────────────
# বাংলা: রিপো রুট থেকে route ফাইলের পাথ কনফিগারেশন
REPO_ROOT = Path(__file__).resolve().parent.parent
ROUTES_DIR = REPO_ROOT / "backend" / "api" / "routes"
CONFIG_FIELDS_PATH = REPO_ROOT / "backend" / "core" / "config_fields.py"

# বাংলা: টাইমআউটের থ্রেশহোল্ড মান — এই মানের উপর ভিত্তি করে রেটিং নির্ধারিত হয়
OVERLY_LONG_THRESHOLD = 60.0   # সেকেন্ড — এর বেশি হলে কানেকশন ঝুঁকিপূর্ণ
OVERLY_SHORT_LLM = 2.0         # সেকেন্ড — LLM কলের জন্য এর কম হলে সম্ভবত ব্যর্থ
LLM_MIN_REASONABLE = 10.0     # সেকেন্ড — LLM কলের জন্য যুক্তিসঙ্গত ন্যূনতম
HTTP_REASONABLE = 15.0        # সেকেন্ড — সাধারণ HTTP কলের জন্য
BROWSER_REASONABLE = 60.0     # সেকেন্ড — ব্রাউজার/স্ক্র্যাপার কলের জন্য

# বাংলা: গ্লোবাল LLM টাইমআউট ডিফল্ট — config_fields.py থেকে পড়া হয়
GLOBAL_LLM_DEFAULTS: dict[str, float] = {
    "LLM_CONNECT_TIMEOUT": 5.0,
    "LLM_READ_TIMEOUT": 30.0,
    "LLM_WRITE_TIMEOUT": 5.0,
    "LLM_POOL_TIMEOUT": 5.0,
}


# ── টাইমআউট স্ট্যাটাস এনাম ─────────────────────────────────────────────────
class TimeoutStatus(str, Enum):
    """বাংলা: প্রতিটি বাহ্যিক কলের টাইমআউট অবস্থা নির্দেশ করে"""
    NO_TIMEOUT = "NO_TIMEOUT"             # 🔴 কোনো টাইমআউট সুরক্ষা নেই
    IMPLICIT_TIMEOUT = "IMPLICIT_TIMEOUT" # 🟡 গ্লোবাল ডিফল্টের উপর নির্ভরশীল
    EXPLICIT_TIMEOUT = "EXPLICIT_TIMEOUT" # 🟢 স্পষ্টভাবে timeout প্যারামিটার দেওয়া আছে
    OVERLY_LONG = "OVERLY_LONG"           # 🔵 অত্যধিক দীর্ঘ (>60s)
    OVERLY_SHORT = "OVERLY_SHORT"         # 🔵 অত্যধিক স্বল্প (<2s for LLM)


# ── ডাটা ক্লাস ────────────────────────────────────────────────────────────────
@dataclass
class ExternalCall:
    """বাংলা: একটি বাহ্যিক কলের তথ্য ধারণ করে"""
    call_type: str          # httpx, aiohttp, requests, llm_gateway, db, browser, fetch_wrapper, asyncio_wait_for
    method: str             # get, post, acompletion, execute, ইত্যাদি
    line_no: int            # ফাইলের লাইন নম্বর
    line_text: str          # আসল লাইনের কোড
    timeout_value: float | None = None  # পাওয়া গেলে টাইমআউটের মান
    timeout_source: str = ""  # কোথা থেকে টাইমআউট এসেছে (explicit, implicit, none)
    status: TimeoutStatus = TimeoutStatus.NO_TIMEOUT
    recommended: str = ""    # রেকমেন্ডেড টাইমআউট
    risk: str = ""           # টাইমআউট ফায়ার হলে কী হতে পারে


@dataclass
class EndpointReport:
    """বাংলা: একটি এন্ডপয়েন্টের সম্পূর্ণ টাইমআউট রিপোর্ট"""
    route_path: str
    http_method: str
    file_path: str
    function_name: str
    line_no: int
    external_calls: list[ExternalCall] = field(default_factory=list)
    total_timeout_budget: float | None = None
    budget_analysis: str = ""
    has_streaming: bool = False

    @property
    def worst_status(self) -> TimeoutStatus:
        """বাংলা: সবচেয়ে খারাপ টাইমআউট স্ট্যাটাস রিটার্ন করে"""
        priority = [
            TimeoutStatus.NO_TIMEOUT,
            TimeoutStatus.OVERLY_SHORT,
            TimeoutStatus.OVERLY_LONG,
            TimeoutStatus.IMPLICIT_TIMEOUT,
            TimeoutStatus.EXPLICIT_TIMEOUT,
        ]
        for s in priority:
            if any(c.status == s for c in self.external_calls):
                return s
        return TimeoutStatus.EXPLICIT_TIMEOUT


class RouteFileParser:
    """বাংলা: Python AST ব্যবহার করে route ফাইল পার্স করে বাহ্যিক কল খুঁজে বের করে"""

    # বাংলা: রেজেক্স প্যাটার্ন — AST দিয়ে সব ধরা না পড়লে ফলব্যাক হিসেবে ব্যবহৃত
    HTTPX_CLIENT_RE = re.compile(r"httpx\.AsyncClient\(.*?timeout\s*=\s*([\d.]+)", re.DOTALL)
    HTTPX_CLIENT_NO_TIMEOUT_RE = re.compile(r"httpx\.AsyncClient\(")
    HTTPX_CALL_TIMEOUT_RE = re.compile(r"\.(get|post|put|delete|patch|head|options)\(.*?timeout\s*=\s*([\d.]+)", re.DOTALL)
    AIOHTTP_TIMEOUT_RE = re.compile(r"aiohttp\.ClientSession\(.*?timeout\s*=\s*([\d.]+)", re.DOTALL)
    AIOHTTP_NO_TIMEOUT_RE = re.compile(r"aiohttp\.ClientSession\(")
    REQUESTS_RE = re.compile(r"requests\.(get|post|put|delete|patch|head|options)\(")
    REQUESTS_TIMEOUT_RE = re.compile(r"requests\.(get|post|put|delete|patch|head|options)\(.*?timeout\s*=\s*([\d.]+)", re.DOTALL)
    LLM_GATEWAY_RE = re.compile(r"llm_gateway\.(acompletion|completion|achat|chat|astream|stream)\(")
    LLM_GATEWAY_TIMEOUT_RE = re.compile(r"llm_gateway\.(acompletion|completion|achat|chat|astream|stream)\(.*?timeout\s*=\s*([\d.]+)", re.DOTALL)
    OPENAI_RE = re.compile(r"(openai|AsyncOpenAI|OpenAI)\.")
    ANTHROPIC_RE = re.compile(r"(anthropic|AsyncAnthropic)\.")
    GOOGLE_GENAI_RE = re.compile(r"google\.genai\.")
    ASYNCIO_WAIT_FOR_RE = re.compile(r"asyncio\.wait_for\(")
    ASYNCIO_TIMEOUT_RE = re.compile(r"asyncio\.timeout\(")
    FETCH_WRAPPER_RE = re.compile(r"(fetch|fetch_url|http_fetch|make_request|api_call)\(")
    BROWSER_AGENT_RE = re.compile(r"(BrowserAgent|AutonomousBrowserAgent|browser_agent)\.")
    SCRAPER_RE = re.compile(r"(WebScraper|web_scraper|scraper)\.")
    DB_HEAVY_RE = re.compile(r"\.(execute|fetchall|fetchone|fetchmany|scalars)\(")
    SUPABASE_TABLE_RE = re.compile(r".table([\"\x27][^\"\x27]+[\"\x27]).")

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.source_lines: list[str] = []
        self.tree: ast.AST | None = None
        self._imports: set[str] = set()
        self._from_imports: dict[str, set[str]] = {}
        self._router_prefix: str = ""  # বাংলা: APIRouter(prefix=...) থেকে প্রিফিক্স

    def parse(self) -> list[EndpointReport]:
        """বাংলা: ফাইল পার্স করে সকল এন্ডপয়েন্ট রিপোর্ট তৈরি করে"""
        try:
            raw = self.file_path.read_text(encoding="utf-8", errors="replace")
            self.source_lines = raw.splitlines()
            self.tree = ast.parse(raw, filename=str(self.file_path))
        except SyntaxError as exc:
            print(f"⚠️  পার্স ত্রুটি {self.file_path.name}: {exc}", file=sys.stderr)
            return []

        self._collect_imports()
        endpoints = self._extract_routes()
        return endpoints

    def _collect_imports(self) -> None:
        """বাংলা: ইম্পোর্ট স্টেটমেন্ট থেকে বাহ্যিক লাইব্রেরি সনাক্ত করে"""
        for node in ast.walk(self.tree):  # type: ignore[arg-type]
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self._imports.add(node.module.split(".")[0])
                    self._from_imports.setdefault(node.module, set())
                    for alias in node.names:
                        self._from_imports[node.module].add(alias.name)

    def _has_httpx(self) -> bool:
        return "httpx" in self._imports

    def _has_aiohttp(self) -> bool:
        return "aiohttp" in self._imports

    def _has_requests(self) -> bool:
        return "requests" in self._imports

    def _extract_routes(self) -> list[EndpointReport]:
        """বাংলা: @router.get/post/put/delete/patch ডেকোরেটর সহ ফাংশন খুঁজে বের করে"""
        reports: list[EndpointReport] = []
        self._extract_router_prefix()  # বাংলা: প্রিফিক্স আগে বের করা হয়
        for node in ast.iter_child_nodes(self.tree):  # type: ignore[arg-type]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                report = self._check_route_decorator(node)
                if report:
                    # বাংলা: রুটার প্রিফিক্স যুক্ত পূর্ণ পাথ
                    if self._router_prefix and not report.route_path.startswith(self._router_prefix):
                        report.route_path = self._router_prefix + report.route_path
                    report.external_calls = self._find_external_calls_in_function(node)
                    report.has_streaming = self._detect_streaming(node)
                    report.budget_analysis = self._analyze_timeout_budget(report)
                    reports.append(report)
        return reports

    def _extract_router_prefix(self) -> None:
        """বাংলা: router = APIRouter(prefix="/api/xxx") থেকে প্রিফিক্স বের করে"""
        for node in ast.iter_child_nodes(self.tree):  # type: ignore[arg-type]
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "router":
                        if isinstance(node.value, ast.Call):
                            call = node.value
                            # বাংলা: APIRouter(prefix="...") প্যাটার্ন
                            if isinstance(call.func, ast.Name) and call.func.id == "APIRouter":
                                for kw in call.keywords:
                                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                                        self._router_prefix = str(kw.value.value)
                                        return

    def _check_route_decorator(self, func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> EndpointReport | None:
        """বাংলা: ফাংশনের ডেকোরেটরে route প্যাটার্ন আছে কিনা পরীক্ষা করে"""
        for dec in func_node.decorator_list:
            method, path = self._parse_router_decorator(dec)
            if method:
                return EndpointReport(
                    route_path=path or f"/{func_node.name}",
                    http_method=method.upper(),
                    file_path=str(self.file_path.relative_to(REPO_ROOT)),
                    function_name=func_node.name,
                    line_no=func_node.lineno,
                )
        return None

    # বাংলা: ভুল পজিটিভ এড়াতে DB কোয়েরি ইনডিকেটর — SQLAlchemy নির্দিষ্ট
    _DB_QUERY_INDICATORS = [
        "db.execute(", "session.execute(", "sql_db.execute(",
        ".options(",
    ]
    # বাংলা: SQLAlchemy join প্যাটার্ন — ".join(" দিয়ে string.join বাদ দেওয়া হয়
    _SQLA_JOIN_RE = re.compile(r"\b(join|outerjoin|join_from)\s*\(")

    def _parse_router_decorator(self, dec: ast.expr) -> tuple[str | None, str | None]:
        """বাংলা: @router.get("/path") থেকে method ও path বের করে"""
        # সরাসরি @router.get("/path") প্যাটার্ন
        if isinstance(dec, ast.Call):
            func = dec.func
            if isinstance(func, ast.Attribute):
                method = func.attr.lower()
                if method in ("get", "post", "put", "delete", "patch", "head", "options"):
                    path = ""
                    if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                        path = dec.args[0].value
                    return method, path
            # @router.api_route("/path", methods=[...]) প্যাটার্ন
            if isinstance(func, ast.Attribute) and func.attr == "api_route":
                path = ""
                if dec.args and isinstance(dec.args[0], ast.Constant):
                    path = dec.args[0].value
                methods = ["GET"]
                for kw in dec.keywords:
                    if kw.arg == "methods" and isinstance(kw.value, ast.List):
                        methods = []
                        for elt in kw.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                methods.append(elt.value.upper())
                return methods[0] if methods else "GET", path
        return None, None

    def _find_external_calls_in_function(
        self, func_node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> list[ExternalCall]:
        """বাংলা: ফাংশন বডিতে সকল বাহ্যিক কল খুঁজে বের করে ও টাইমআউট পরীক্ষা করে"""
        calls: list[ExternalCall] = []
        # বাংলা: ফাংশনের শুরু ও শেষ লাইন নির্ধারণ করা হয়
        start_line = func_node.lineno
        end_line = func_node.end_lineno or start_line + 50
        func_source = "\n".join(self.source_lines[start_line - 1 : end_line])
        func_lines = self.source_lines[start_line - 1 : end_line]

        # বাংলা: লোকাল import পরীক্ষা — httpx/aiohttp/requests ফাংশনের ভেতরে import হতে পারে
        self._check_local_imports(func_node)

        # বাংলা: প্রতিটি ধরনের বাহ্যিক কল পরীক্ষা করা হয়
        calls.extend(self._find_httpx_calls(func_source, func_lines, start_line))
        calls.extend(self._find_aiohttp_calls(func_source, func_lines, start_line))
        calls.extend(self._find_requests_calls(func_source, func_lines, start_line))
        calls.extend(self._find_llm_calls(func_source, func_lines, start_line))
        calls.extend(self._find_llm_provider_calls(func_source, func_lines, start_line))
        calls.extend(self._find_asyncio_timeout_calls(func_source, func_lines, start_line))
        calls.extend(self._find_fetch_wrapper_calls(func_source, func_lines, start_line))
        calls.extend(self._find_browser_calls(func_source, func_lines, start_line))
        calls.extend(self._find_db_calls(func_node, func_source, func_lines, start_line))
        calls.extend(self._find_supabase_calls(func_source, func_lines, start_line))

        return calls

    def _check_local_imports(self, func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """বাংলা: ফাংশনের ভেতরে থাকা লোকাল import সনাক্ত করে"""
        for node in ast.walk(func_node):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self._imports.add(node.module.split(".")[0])

    def _make_call(
        self,
        call_type: str,
        method: str,
        line_no: int,
        line_text: str,
        timeout_value: float | None,
        timeout_source: str,
    ) -> ExternalCall:
        """বাংলা: ExternalCall অবজেক্ট তৈরি করে ও স্ট্যাটাস নির্ধারণ করে"""
        call = ExternalCall(
            call_type=call_type,
            method=method,
            line_no=line_no,
            line_text=line_text.strip(),
            timeout_value=timeout_value,
            timeout_source=timeout_source,
        )
        call.status = self._determine_status(call)
        call.recommended = self._recommend_timeout(call)
        call.risk = self._assess_risk(call)
        return call

    def _determine_status(self, call: ExternalCall) -> TimeoutStatus:
        """বাংলা: কলের টাইমআউট স্ট্যাটাস নির্ধারণ করে"""
        if call.timeout_value is not None:
            # বাংলা: স্পষ্ট টাইমআউট আছে — তবে মান যৌক্তিক কিনা পরীক্ষা
            if call.timeout_value > OVERLY_LONG_THRESHOLD:
                return TimeoutStatus.OVERLY_LONG
            if call.call_type in ("llm_gateway", "openai", "anthropic", "google_genai"):
                if call.timeout_value < OVERLY_SHORT_LLM:
                    return TimeoutStatus.OVERLY_SHORT
            return TimeoutStatus.EXPLICIT_TIMEOUT
        elif call.timeout_source == "implicit":
            return TimeoutStatus.IMPLICIT_TIMEOUT
        else:
            return TimeoutStatus.NO_TIMEOUT

    def _recommend_timeout(self, call: ExternalCall) -> str:
        """বাংলা: কলের ধরন অনুযায়ী রেকমেন্ডেড টাইমআউট প্রদান করে"""
        if call.status == TimeoutStatus.EXPLICIT_TIMEOUT:
            return "✓ বর্তমান মান গ্রহণযোগ্য"
        if call.call_type in ("llm_gateway", "openai", "anthropic", "google_genai"):
            return f"timeout={LLM_MIN_REASONABLE:.0f}~30.0 (LLM রেসপন্স জন্য)"
        if call.call_type in ("httpx", "aiohttp", "requests"):
            return f"timeout={HTTP_REASONABLE:.0f}.0 (HTTP API কল জন্য)"
        if call.call_type in ("browser", "scraper"):
            return f"timeout={BROWSER_REASONABLE:.0f}.0 (ব্রাউজার অটোমেশন জন্য)"
        if call.call_type == "asyncio_wait_for":
            return "asyncio.wait_for(coro, timeout=N) ব্যবহার করুন"
        if call.call_type in ("db_heavy", "supabase"):
            return "timeout=10.0 (DB কোয়েরি জন্য, জটিল কোয়েরিতে 30.0)"
        if call.call_type == "fetch_wrapper":
            return f"timeout={HTTP_REASONABLE:.0f}.0 (fetch wrapper-এ পাস করুন)"
        return "timeout=10.0 (ডিফল্ট)"

    def _assess_risk(self, call: ExternalCall) -> str:
        """বাংলা: টাইমআউট ফায়ার হলে সম্ভাব্য ঝুঁকি বর্ণনা করে"""
        if call.call_type in ("llm_gateway", "openai", "anthropic", "google_genai"):
            if call.status == TimeoutStatus.NO_TIMEOUT:
                return "কানেকশন হ্যাং হতে পারে — থ্রেড/worker ব্লক করবে, ক্যাসকেড ফেইলিওর সম্ভব"
            if call.status == TimeoutStatus.OVERLY_SHORT:
                return "LLM রেসপন্স আসার আগেই টাইমআউট — প্রতিটি রিকোয়েস্ট ব্যর্থ হবে"
            if call.status == TimeoutStatus.IMPLICIT_TIMEOUT:
                return "গ্লোবাল ডিফল্ট পরিবর্তন হলে এই এন্ডপয়েন্ট অপ্রত্যাশিতভাবে প্রভাবিত হতে পারে"
            return "টাইমআউট হলে partial response বা খালি রেসপন্স ফেরত যেতে পারে"
        if call.call_type in ("httpx", "aiohttp", "requests"):
            if call.status == TimeoutStatus.NO_TIMEOUT:
                return "অসীম অপেক্ষা — upstream down হলে কানেকশন লিক হবে, OOM সম্ভব"
            return "টাইমআউট হলে httpx.TimeoutException / aiohttp ত্রুটি ছুঁড়বে"
        if call.call_type in ("browser", "scraper"):
            return "ব্রাউজার প্রসেস অরফান হতে পারে — resource leak সম্ভব"
        if call.call_type in ("db_heavy", "supabase"):
            return "DB কানেকশন পুল নিঃশেষ হতে পারে — অন্য এন্ডপয়েন্টও প্রভাবিত"
        return "অনির্ধারিত ব্যর্থতা"

    def _find_httpx_calls(
        self, func_source: str, func_lines: list[str], start_line: int
    ) -> list[ExternalCall]:
        """বাংলা: httpx.AsyncClient ও httpx কল খুঁজে বের করে"""
        calls: list[ExternalCall] = []
        if not self._has_httpx():
            return calls

        seen_client_lines: set[int] = set()
        client_has_explicit_timeout = False
        for i, line in enumerate(func_lines):
            line_no = start_line + i
            if "httpx.AsyncClient(" in line:
                seen_client_lines.add(i)
                tm = re.search(r"timeout\s*=\s*([\d.]+)", line)
                if tm:
                    client_has_explicit_timeout = True
                    calls.append(self._make_call(
                        "httpx", "AsyncClient", line_no, line,
                        float(tm.group(1)), "explicit"
                    ))
                    continue
                # বাংলা: multiline কনস্ট্রাক্টর — পরবর্তি কয়েক লাইনে timeout থাকতে পারে
                remaining = chr(10).join(func_lines[i:i+5])
                tm2 = self.HTTPX_CLIENT_RE.search(remaining)
                if tm2:
                    client_has_explicit_timeout = True
                    calls.append(self._make_call(
                        "httpx", "AsyncClient", line_no, line,
                        float(tm2.group(1)), "explicit"
                    ))
                else:
                    rest = chr(10).join(func_lines[i:])
                    call_m = self.HTTPX_CALL_TIMEOUT_RE.search(rest)
                    if call_m:
                        calls.append(self._make_call(
                            "httpx", call_m.group(1), line_no, line,
                            float(call_m.group(2)), "explicit"
                        ))
                    else:
                        calls.append(self._make_call(
                            "httpx", "AsyncClient", line_no, line,
                            None, "none"
                        ))
                continue

            # বাংলা: ক্লায়েন্টে স্পষ্ট টাইমআউট থাকলে প্রতিটি কল কভার্ড — ডুপ্লিকেট রিপোর্ট এড়ানো হয়
            if seen_client_lines and client_has_explicit_timeout:
                continue
            if i in seen_client_lines:
                continue
            for method in ("get", "post", "put", "delete", "patch"):
                if f".{method}(" in line and "await" in line:
                    tm = re.search(r"timeout\s*=\s*([\d.]+)", line)
                    if tm:
                        calls.append(self._make_call(
                            "httpx", method, line_no, line,
                            float(tm.group(1)), "explicit"
                        ))
                    elif "httpx" in func_source:
                        calls.append(self._make_call(
                            "httpx", method, line_no, line,
                            None, "implicit"
                        ))
        return calls
    def _find_aiohttp_calls(
        self, func_source: str, func_lines: list[str], start_line: int
    ) -> list[ExternalCall]:
        """বাংলা: aiohttp.ClientSession কল খুঁজে বের করে"""
        calls: list[ExternalCall] = []
        if not self._has_aiohttp():
            return calls

        for i, line in enumerate(func_lines):
            line_no = start_line + i
            if "aiohttp.ClientSession(" in line or "ClientSession(" in line:
                m = self.AIOHTTP_TIMEOUT_RE.search(
                    func_source[max(0, i - 2): min(len(func_lines), i + 5)]
                )
                if m:
                    calls.append(self._make_call(
                        "aiohttp", "ClientSession", line_no, line,
                        float(m.group(1)), "explicit"
                    ))
                else:
                    calls.append(self._make_call(
                        "aiohttp", "ClientSession", line_no, line,
                        None, "none"
                    ))
        return calls

    def _find_requests_calls(
        self, func_source: str, func_lines: list[str], start_line: int
    ) -> list[ExternalCall]:
        """বাংলা: requests.get/post সিঙ্ক্রোনাস কল খুঁজে বের করে"""
        calls: list[ExternalCall] = []
        if not self._has_requests():
            return calls

        for i, line in enumerate(func_lines):
            line_no = start_line + i
            m = self.REQUESTS_RE.search(line)
            if m:
                tm = self.REQUESTS_TIMEOUT_RE.search(
                    func_source[max(0, i - 1): min(len(func_lines), i + 5)]
                )
                if tm:
                    calls.append(self._make_call(
                        "requests", m.group(1), line_no, line,
                        float(tm.group(2)), "explicit"
                    ))
                else:
                    calls.append(self._make_call(
                        "requests", m.group(1), line_no, line,
                        None, "none"
                    ))
        return calls

    def _find_llm_calls(
        self, func_source: str, func_lines: list[str], start_line: int
    ) -> list[ExternalCall]:
        """বাংলা: llm_gateway.acompletion ইত্যাদি LLM gateway কল খুঁজে বের করে"""
        calls: list[ExternalCall] = []
        seen_lines: set[int] = set()

        for i, line in enumerate(func_lines):
            line_no = start_line + i
            if "llm_gateway." in line and self.LLM_GATEWAY_RE.search(line):
                if line_no in seen_lines:
                    continue
                seen_lines.add(line_no)

                # বাংলা: কলে timeout প্যারামিটার আছে কিনা পরীক্ষা
                context = func_source[max(0, i - 1): min(len(func_lines), i + 8)]
                tm = self.LLM_GATEWAY_TIMEOUT_RE.search(context)
                if tm:
                    calls.append(self._make_call(
                        "llm_gateway", tm.group(1), line_no, line,
                        float(tm.group(2)), "explicit"
                    ))
                else:
                    # বাংলা: llm_gateway এর ভেতরে config থেকে ডিফল্ট টাইমআউট ব্যবহৃত হয়
                    # তাই implicit হিসেবে চিহ্নিত
                    calls.append(self._make_call(
                        "llm_gateway", "acompletion", line_no, line,
                        None, "implicit"
                    ))
        return calls

    def _find_llm_provider_calls(
        self, func_source: str, func_lines: list[str], start_line: int
    ) -> list[ExternalCall]:
        """বাংলা: OpenAI, Anthropic, Google GenAI সরাসরি কল খুঁজে বের করে"""
        calls: list[ExternalCall] = []
        patterns = [
            (self.OPENAI_RE, "openai"),
            (self.ANTHROPIC_RE, "anthropic"),
            (self.GOOGLE_GENAI_RE, "google_genai"),
        ]
        for i, line in enumerate(func_lines):
            line_no = start_line + i
            for pat, call_type in patterns:
                if pat.search(line):
                    # বাংলা: timeout প্যারামিটার আছে কিনা পরীক্ষা
                    timeout_match = re.search(r"timeout\s*=\s*([\d.]+)", line)
                    if timeout_match:
                        calls.append(self._make_call(
                            call_type, "api_call", line_no, line,
                            float(timeout_match.group(1)), "explicit"
                        ))
                    else:
                        calls.append(self._make_call(
                            call_type, "api_call", line_no, line,
                            None, "none"
                        ))
        return calls

    def _find_asyncio_timeout_calls(
        self, func_source: str, func_lines: list[str], start_line: int
    ) -> list[ExternalCall]:
        """বাংলা: asyncio.wait_for() ও asyncio.timeout() র‍্যাপার খুঁজে বের করে"""
        calls: list[ExternalCall] = []
        for i, line in enumerate(func_lines):
            line_no = start_line + i
            if self.ASYNCIO_WAIT_FOR_RE.search(line) or self.ASYNCIO_TIMEOUT_RE.search(line):
                # বাংলা: এই কলগুলো নিজেই টাইমআউট র‍্যাপার — স্ট্যাটাস EXPLICIT
                timeout_match = re.search(r"timeout\s*=\s*([\d.]+)", line)
                val = float(timeout_match.group(1)) if timeout_match else None
                method = "wait_for" if "wait_for" in line else "timeout"
                calls.append(self._make_call(
                    "asyncio_wait_for", method, line_no, line,
                    val, "explicit" if val else "none"
                ))
        return calls

    def _find_fetch_wrapper_calls(
        self, func_source: str, func_lines: list[str], start_line: int
    ) -> list[ExternalCall]:
        """বাংলা: fetch(), fetch_url(), http_fetch() ইত্যাদি wrapper কল খুঁজে বের করে"""
        calls: list[ExternalCall] = []
        # বাংলা: শুধুমাত্র llm_gateway, httpx, requests ইত্যাদি ইতিমধ্যে ধরা পড়ানি এমন কল
        for i, line in enumerate(func_lines):
            line_no = start_line + i
            if any(skip in line for skip in (
                "llm_gateway", "httpx", "aiohttp", "requests.",
                "asyncio.wait_for", "asyncio.timeout", "BrowserAgent",
                "AutonomousBrowserAgent", "WebScraper", "browser_agent",
            )):
                continue
            m = self.FETCH_WRAPPER_RE.search(line)
            if m:
                # বাংলা: await সহ কল কিনা পরীক্ষা
                if i > 0 and "await" in func_lines[i - 1]:
                    continue
                if "await" not in line and i + 1 < len(func_lines) and "await" not in func_lines[i]:
                    # বাংলা: non-await fetch wrapper — সম্ভবত sync
                    timeout_match = re.search(r"timeout\s*=\s*([\d.]+)", line)
                    calls.append(self._make_call(
                        "fetch_wrapper", m.group(1), line_no, line,
                        float(timeout_match.group(1)) if timeout_match else None,
                        "explicit" if timeout_match else "none"
                    ))
        return calls

    def _find_browser_calls(
        self, func_source: str, func_lines: list[str], start_line: int
    ) -> list[ExternalCall]:
        """বাংলা: ব্রাউজার এজেন্ট ও স্ক্র্যাপার কল খুঁজে বের করে"""
        calls: list[ExternalCall] = []
        for i, line in enumerate(func_lines):
            line_no = start_line + i
            if self.BROWSER_AGENT_RE.search(line) or self.SCRAPER_RE.search(line):
                # বাংলা: পদ্ধতি কল পরীক্ষা (navigate, fetch, scrape, achieve)
                method_match = re.search(r"\.(navigate|fetch_page|scrape|achieve|execute_recipe|navigate_and_interact)\(", line)
                method = method_match.group(1) if method_match else "call"
                # বাংলা: ব্রাউজার কলে সাধারণত সরাসরি timeout থাকে না
                timeout_match = re.search(r"timeout\s*=\s*([\d.]+)", line)
                calls.append(self._make_call(
                    "browser", method, line_no, line,
                    float(timeout_match.group(1)) if timeout_match else None,
                    "explicit" if timeout_match else "none"
                ))
        return calls

    def _find_db_calls(
        self,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        func_source: str,
        func_lines: list[str],
        start_line: int,
    ) -> list[ExternalCall]:
        """বাংলা: ভারী DB কোয়েরি (join, full scan সম্ভাব্য) খুঁজে বের করে"""
        calls: list[ExternalCall] = []
        # বাংলা: SQLAlchemy কোয়েরি প্যাটার্ন পরীক্ষা
        has_join = bool(self._SQLA_JOIN_RE.search(func_source))
        has_options = ".options(" in func_source
        has_complex = has_join or has_options

        for i, line in enumerate(func_lines):
            line_no = start_line + i
            stripped = line.strip()
            # বাংলা: শুধুমাত্র জটিল কোয়েরি (join/options সহ) বা execute কল
            is_db_execute = any(ind in stripped for ind in self._DB_QUERY_INDICATORS)
            if is_db_execute and has_complex:
                timeout_match = re.search(r"timeout\s*=\s*([\d.]+)", line)
                calls.append(self._make_call(
                    "db_heavy", "execute", line_no, line,
                    float(timeout_match.group(1)) if timeout_match else None,
                    "explicit" if timeout_match else "none"
                ))
        return calls

    def _find_supabase_calls(
        self, func_source: str, func_lines: list[str], start_line: int
    ) -> list[ExternalCall]:
        """বাংলা: Supabase client কল খুঁজে বের করে"""
        calls: list[ExternalCall] = []
        for i, line in enumerate(func_lines):
            line_no = start_line + i
            if self.SUPABASE_TABLE_RE.search(line):
                # বাংলা: Supabase Python client-এ সাধারণত timeout প্যারামিটার থাকে না
                calls.append(self._make_call(
                    "supabase", "table_query", line_no, line,
                    None, "none"
                ))
        return calls

    def _detect_streaming(self, func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        """বাংলা: SSE/StreamingResponse রিটার্ন কিনা পরীক্ষা করে"""
        func_source = "\n".join(self.source_lines[
            func_node.lineno - 1 : (func_node.end_lineno or func_node.lineno + 100)
        ])
        return "StreamingResponse" in func_source or "text/event-stream" in func_source

    def _analyze_timeout_budget(self, report: EndpointReport) -> str:
        """বাংলা: এন্ডপয়েন্টের মোট টাইমআউট বাজেট বিশ্লেষণ করে"""
        if not report.external_calls:
            return ""

        external = [c for c in report.external_calls
                     if c.call_type not in ("db_heavy", "supabase")]
        if not external:
            return ""

        # বাংলা: সকল কলের টাইমআউট যোগ করে মোট বাজেট হিসাব
        explicit_timeouts = [c.timeout_value for c in external if c.timeout_value is not None]
        implicit_count = sum(1 for c in external if c.status == TimeoutStatus.IMPLICIT_TIMEOUT)
        no_timeout_count = sum(1 for c in external if c.status == TimeoutStatus.NO_TIMEOUT)

        total_explicit = sum(explicit_timeouts) if explicit_timeouts else 0
        total_with_implicit = total_explicit + (implicit_count * GLOBAL_LLM_DEFAULTS.get("LLM_READ_TIMEOUT", 30.0))

        report.total_timeout_budget = total_with_implicit

        analyses: list[str] = []

        if no_timeout_count > 0:
            analyses.append(
                f"⚠️  {no_timeout_count}টি কলে কোনো টাইমআউট নেই — মোট বাজেট অনির্ধারিত"
            )

        if len(external) > 1 and total_with_implicit > OVERLY_LONG_THRESHOLD:
            analyses.append(
                f"⚠️  {len(external)}টি সিরিয়াল বাহ্যিক কল — "
                f"আনুমানিক মোট বাজেট: {total_with_implicit:.0f}s — "
                f"middleware/request timeout এর আগেই শেষ হতে পারে"
            )

        if report.has_streaming and any(c.call_type in ("llm_gateway",) for c in external):
            analyses.append(
                "ℹ️  SSE স্ট্রিমিং এন্ডপয়েন্ট — প্রথম টোকেনের জন্য LLM টাইমআউট প্রযোজ্য, পরবর্তী চাঙ্কের জন্য নয়"
            )

        return " | ".join(analyses) if analyses else ""


# ── মূল অডিটর ক্লাস ─────────────────────────────────────────────────────
class EndpointTimeoutAuditor:
    """বাংলা: সকল route ফাইল পার্স করে টাইমআউট অডিট রিপোর্ট তৈরি করে"""

    def __init__(
        self,
        routes_dir: Path = ROUTES_DIR,
        filter_route: str | None = None,
        llm_only: bool = False,
    ):
        self.routes_dir = routes_dir
        self.filter_route = filter_route
        self.llm_only = llm_only
        self.reports: list[EndpointReport] = []

    def audit(self) -> list[EndpointReport]:
        """বাংলা: সকল route ফাইল অডিট করে"""
        if not self.routes_dir.exists():
            print(f"❌ routes ডিরেক্টরি পাওয়া যায়নি: {self.routes_dir}", file=sys.stderr)
            sys.exit(2)

        route_files = sorted(self.routes_dir.glob("*.py"))
        # বাংলা: সাবডিরেক্টরিও অন্তর্ভুক্ত (যেমন commandcenter/)
        for sub_dir in sorted(self.routes_dir.iterdir()):
            if sub_dir.is_dir() and not sub_dir.name.startswith("__"):
                route_files.extend(sorted(sub_dir.glob("*.py")))

        for fp in route_files:
            if fp.name.startswith("__"):
                continue
            try:
                parser = RouteFileParser(fp)
                file_reports = parser.parse()
                self.reports.extend(file_reports)
            except Exception as exc:
                print(f"❌ {fp.name} পার্স করতে ত্রুটি: {exc}", file=sys.stderr)

        # বাংলা: ফিল্টার প্রয়োগ
        if self.filter_route:
            self.reports = [
                r for r in self.reports
                if self.filter_route in r.route_path
            ]

        # বাংলা: LLM-only ফিল্টার
        if self.llm_only:
            llm_types = ("llm_gateway", "openai", "anthropic", "google_genai")
            self.reports = [
                r for r in self.reports
                if any(c.call_type in llm_types for c in r.external_calls)
            ]
            # বাংলা: LLM-only মোডে non-LLM কলগুলো রিপোর্ট থেকে সরানো হয়
            for r in self.reports:
                r.external_calls = [c for c in r.external_calls if c.call_type in llm_types]
                r.budget_analysis = self._rebuild_budget(r)

        return self.reports

    def has_missing_timeouts(self) -> bool:
        """বাংলা: কোনো এন্ডপয়েন্টে টাইমআউট অনুপস্থিত কিনা পরীক্ষা করে"""
        return any(
            r.worst_status in (TimeoutStatus.NO_TIMEOUT, TimeoutStatus.OVERLY_SHORT)
            for r in self.reports
        )

    def _rebuild_budget(self, report: EndpointReport) -> str:
        """বাংলা: LLM-only ফিল্টারের পর বাজেট বিশ্লেষণ আবার তৈরি করে"""
        external = [c for c in report.external_calls
                     if c.call_type not in ("db_heavy", "supabase")]
        if not external:
            return ""
        no_timeout_count = sum(1 for c in external if c.status == TimeoutStatus.NO_TIMEOUT)
        implicit_count = sum(1 for c in external if c.status == TimeoutStatus.IMPLICIT_TIMEOUT)
        parts: list[str] = []
        if no_timeout_count > 0:
            parts.append(f"⚠️  {no_timeout_count}টি কলে কোনো টাইমআউট নেই")
        if implicit_count > 0:
            parts.append(f"🟡 {implicit_count}টি কল গ্লোবাল ডিফল্টে নির্ভরশীল")
        if report.has_streaming:
            parts.append("ℹ️  SSE স্ট্রিমিং এন্ডপয়েন্ট")
        return " | ".join(parts)


# ── আউটপুট ফরম্যাটার ─────────────────────────────────────────────────────
class ReportFormatter:
    """বাংলা: রিপোর্ট বিভিন্ন ফরম্যাটে আউটপুট করে"""

    STATUS_ICONS: dict[TimeoutStatus, str] = {
        TimeoutStatus.NO_TIMEOUT: "🔴",
        TimeoutStatus.IMPLICIT_TIMEOUT: "🟡",
        TimeoutStatus.EXPLICIT_TIMEOUT: "🟢",
        TimeoutStatus.OVERLY_LONG: "🔵",
        TimeoutStatus.OVERLY_SHORT: "🔵",
    }

    STATUS_LABELS: dict[TimeoutStatus, str] = {
        TimeoutStatus.NO_TIMEOUT: "কোনো টাইমআউট নেই",
        TimeoutStatus.IMPLICIT_TIMEOUT: "গ্লোবাল ডিফল্ট নির্ভরশীল",
        TimeoutStatus.EXPLICIT_TIMEOUT: "স্পষ্ট টাইমআউট",
        TimeoutStatus.OVERLY_LONG: "অত্যধিক দীর্ঘ (>60s)",
        TimeoutStatus.OVERLY_SHORT: "অত্যধিক স্বল্প (<2s LLM)",
    }

    @classmethod
    def format_terminal(cls, reports: list[EndpointReport]) -> str:
        """বাংলা: টার্মিনালে পড়তে সুবিধাজনক ফরম্যাটে রিপোর্ট আউটপুট করে"""
        if not reports:
            return "✅ কোনো এন্ডপয়েন্ট পাওয়া যায়নি।"

        lines: list[str] = []
        lines.append("=" * 72)
        lines.append("📋 SupremeAI এন্ডপয়েন্ট টাইমআউট অডিট রিপোর্ট")
        lines.append(f"   মোট এন্ডপয়েন্ট: {len(reports)}")
        lines.append("=" * 72)
        lines.append("")

        # বাংলা: সারাংশ পরিসংখ্যান
        total_calls = sum(len(r.external_calls) for r in reports)
        no_timeout = sum(1 for r in reports for c in r.external_calls if c.status == TimeoutStatus.NO_TIMEOUT)
        implicit = sum(1 for r in reports for c in r.external_calls if c.status == TimeoutStatus.IMPLICIT_TIMEOUT)
        explicit = sum(1 for r in reports for c in r.external_calls if c.status == TimeoutStatus.EXPLICIT_TIMEOUT)
        overly_long = sum(1 for r in reports for c in r.external_calls if c.status == TimeoutStatus.OVERLY_LONG)
        overly_short = sum(1 for r in reports for c in r.external_calls if c.status == TimeoutStatus.OVERLY_SHORT)

        lines.append(f"📊 সারাংশ: {total_calls}টি বাহ্যিক কল পাওয়া গেছে")
        lines.append(f"   🔴 কোনো টাইমআউট নেই:      {no_timeout}")
        lines.append(f"   🟡 গ্লোবাল ডিফল্ট:       {implicit}")
        lines.append(f"   🟢 স্পষ্ট টাইমআউট:       {explicit}")
        lines.append(f"   🔵 অত্যধিক দীর্ঘ:          {overly_long}")
        lines.append(f"   🔵 অত্যধিক স্বল্প (LLM):  {overly_short}")
        lines.append("")

        # বাংলা: প্রতিটি এন্ডপয়েন্টের বিস্তারিত রিপোর্ট
        for idx, report in enumerate(reports, 1):
            icon = cls.STATUS_ICONS.get(report.worst_status, "⚪")
            lines.append(f"{'─' * 72}")
            lines.append(
                f"{idx}. {icon} {report.http_method} {report.route_path}"
            )
            lines.append(f"   ফাইল: {report.file_path}:{report.line_no}")
            lines.append(f"   ফাংশন: {report.function_name}")

            if report.has_streaming:
                lines.append(f"   🌊 SSE স্ট্রিমিং এন্ডপয়েন্ট")

            if not report.external_calls:
                lines.append(f"   ℹ️  কোনো বাহ্যিক কল সনাক্ত হয়নি")
            else:
                for call in report.external_calls:
                    c_icon = cls.STATUS_ICONS.get(call.status, "⚪")
                    c_label = cls.STATUS_LABELS.get(call.status, call.status)
                    timeout_str = f"{call.timeout_value}s" if call.timeout_value is not None else "N/A"
                    lines.append(f"")
                    lines.append(f"   {c_icon} [{call.call_type}] {call.method}() — লাইন {call.line_no}")
                    lines.append(f"      স্ট্যাটাস: {c_label}")
                    lines.append(f"      টাইমআউট: {timeout_str} ({call.timeout_source})")
                    if call.recommended:
                        lines.append(f"      রেকমেন্ডেশন: {call.recommended}")
                    if call.risk:
                        lines.append(f"      ঝুঁকি: {call.risk}")

            if report.budget_analysis:
                lines.append(f"")
                lines.append(f"   📐 টাইমআউট বাজেট বিশ্লেষণ: {report.budget_analysis}")
            lines.append("")

        # বাংলা: গ্লোবাল কনফিগ রেফারেন্স
        lines.append(f"{'═' * 72}")
        lines.append("⚙️  গ্লোবাল LLM টাইমআউট কনফিগ (config_fields.py):")
        for key, val in GLOBAL_LLM_DEFAULTS.items():
            lines.append(f"   {key} = {val}s")
        lines.append(f"{'═' * 72}")

        return "\n".join(lines)

    @classmethod
    def format_json(cls, reports: list[EndpointReport]) -> str:
        """বাংলা: JSON ফরম্যাটে রিপোর্ট আউটপুট করে — CI/CD pipeline-এ ব্যবহারের জন্য"""
        output = {
            "auditor": "endpoint_timeout_auditor",
            "total_endpoints": len(reports),
            "summary": {
                "total_external_calls": sum(len(r.external_calls) for r in reports),
                "no_timeout": sum(
                    1 for r in reports for c in r.external_calls
                    if c.status == TimeoutStatus.NO_TIMEOUT
                ),
                "implicit_timeout": sum(
                    1 for r in reports for c in r.external_calls
                    if c.status == TimeoutStatus.IMPLICIT_TIMEOUT
                ),
                "explicit_timeout": sum(
                    1 for r in reports for c in r.external_calls
                    if c.status == TimeoutStatus.EXPLICIT_TIMEOUT
                ),
                "overly_long": sum(
                    1 for r in reports for c in r.external_calls
                    if c.status == TimeoutStatus.OVERLY_LONG
                ),
                "overly_short": sum(
                    1 for r in reports for c in r.external_calls
                    if c.status == TimeoutStatus.OVERLY_SHORT
                ),
            },
            "global_llm_defaults": GLOBAL_LLM_DEFAULTS,
            "endpoints": [],
        }

        for report in reports:
            ep: dict[str, Any] = {
                "route": report.route_path,
                "method": report.http_method,
                "file": report.file_path,
                "function": report.function_name,
                "line": report.line_no,
                "worst_status": report.worst_status.value,
                "has_streaming": report.has_streaming,
                "total_timeout_budget": report.total_timeout_budget,
                "budget_analysis": report.budget_analysis,
                "external_calls": [
                    {
                        "type": c.call_type,
                        "method": c.method,
                        "line": c.line_no,
                        "line_text": c.line_text,
                        "timeout_value": c.timeout_value,
                        "timeout_source": c.timeout_source,
                        "status": c.status.value,
                        "recommended": c.recommended,
                        "risk": c.risk,
                    }
                    for c in report.external_calls
                ],
            }
            output["endpoints"].append(ep)

        return json.dumps(output, indent=2, ensure_ascii=False)


# ── গ্লোবাল কনফিগ পার্সার ──────────────────────────────────────────────────
def parse_global_config(config_path: Path) -> dict[str, float]:
    """বাংলা: config_fields.py থেকে বাস্তব টাইমআউট মান পড়ে"""
    if not config_path.exists():
        return GLOBAL_LLM_DEFAULTS

    try:
        source = config_path.read_text(encoding="utf-8")
        for match in re.finditer(
            r"(LLM_CONNECT_TIMEOUT|LLM_READ_TIMEOUT|LLM_WRITE_TIMEOUT|LLM_POOL_TIMEOUT)"
            r"[:\s]+(?:float\()?Field\(.*?default\s*=\s*([\d.]+)",
            source, re.DOTALL,
        ):
            key = match.group(1)
            val = float(match.group(2))
            GLOBAL_LLM_DEFAULTS[key] = val
    except Exception as exc:
        print(f"⚠️  config_fields.py পড়তে ত্রুটি: {exc}", file=sys.stderr)

    return GLOBAL_LLM_DEFAULTS


# ── CLI এন্ট্রি পয়েন্ট ─────────────────────────────────────────────────────
def main() -> None:
    """বাংলা: স্ক্রিপ্টের মূল এন্ট্রি পয়েন্ট"""
    parser = argparse.ArgumentParser(
        description="SupremeAI এন্ডপয়েন্ট টাইমআউট অডিটর",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""উদাহরণ:
  python scripts/endpoint_timeout_auditor.py
  python scripts/endpoint_timeout_auditor.py --json
  python scripts/endpoint_timeout_auditor.py --route /api/chat
  python scripts/endpoint_timeout_auditor.py --llm-only

এক্সিট কোড:
  0 = সকল এন্ডপয়েন্টে টাইমআউট কভার্ড
  1 = এক বা একাধিক এন্ডপয়েন্টে টাইমআউট অনুপস্থিত
  2 = স্ক্রিপ্ট এক্সিকিউশন ত্রুটি
""",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="JSON ফরম্যাটে আউটপুট (CI/CD pipeline-এ ব্যবহারের জন্য)",
    )
    parser.add_argument(
        "--route",
        type=str,
        default=None,
        help="নির্দিষ্ট রুট পাথ দিয়ে ফিল্টার করুন (যেমন: /api/chat/get_completion)",
    )
    parser.add_argument(
        "--llm-only",
        action="store_true",
        dest="llm_only",
        help="শুধুমাত্র LLM কল অডিট করুন",
    )

    args = parser.parse_args()

    try:
        # বাংলা: গ্লোবাল কনফিগ থেকে টাইমআউট মান লোড করা
        parse_global_config(CONFIG_FIELDS_PATH)

        # বাংলা: অডিট চালানো
        auditor = EndpointTimeoutAuditor(
            filter_route=args.route,
            llm_only=args.llm_only,
        )
        reports = auditor.audit()

        # বাংলা: আউটপুট ফরম্যাট নির্বাচন
        if args.json_output:
            print(ReportFormatter.format_json(reports))
        else:
            print(ReportFormatter.format_terminal(reports))

        # বাংলা: এক্সিট কোড নির্ধারণ
        if auditor.has_missing_timeouts():
            sys.exit(1)
        sys.exit(0)

    except KeyboardInterrupt:
        print("\n⏹️  ব্যবহারকারী দ্বারা বাতিল করা হয়েছে", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:
        print(f"❌ অপ্রত্যাশিত ত্রুটি: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
