#!/usr/bin/env python3
"""...[truncated for brevity]..."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / 'backend'
FRONTEND_DIR = REPO_ROOT / 'frontend' / 'src'

HTTP_METHODS = ('get', 'post', 'put', 'delete', 'patch')
ALL_METHODS = HTTP_METHODS + ('websocket',)

HEALTH_PATTERNS = re.compile(
    r'(/health|/health/|/ready|/live|/healthz|/ping|/heartbeat)', re.IGNORECASE
)
WEBHOOK_PATTERNS = re.compile(
    r'(webhook|stripe|github.event|ci.webhook|cdc.webhook)', re.IGNORECASE
)
ADMIN_PATTERNS = re.compile(
    r'(/admin|/admin/|/metrics|/internal|/tenant.admin|/traffic.monitor|/simulator.admin|'
    r'/site.actions|/browser.routes|/cloud.mesh|/tools.ops|/execution.policies|'
    r'/living.brain|/admin.librarian|/admin.dashboard|/admin.v1|'
    r'/gcp/health|/gcp/|/free-tier)',
    re.IGNORECASE,
)


# pre-compute backtick as a variable to avoid shell/encoding issues
_BT = chr(96)

# regex patterns built without literal backticks in source
_FETCH_BT = _BT + r'\s*([^' + _BT + r']*?)\s*' + _BT
_FETCH_DQ = r'"\s*([^"\s]*?)\s*"'
_FETCH_SQ = r"'\\s*([^'\\s]*?)\\s*'"
_FETCH_BF = r'(getApiBaseUrl|API_BASE|API_BASE_URL|BACKEND_URL|USER_BACKEND_URL|ADMIN_BACKEND_URL)\s*\(\s*\)'

FETCH_CALL_RE = re.compile(
    r'(?:fetch|fetchWithRetry)\s*\(\s*'
    r'(?:' + _FETCH_BT
    + r'|' + _FETCH_DQ
    + r'|' + _FETCH_SQ
    + r'|' + _FETCH_BF + r')'
)

_APICLIENT_BT = _BT + r'\s*([^' + _BT + r']*?)\s*' + _BT
_APICLIENT_DQ = r'"\s*([^"\s]*?)\s*"'
_APICLIENT_SQ = r"'\\s*([^'\\s]*?)\\s*'"

API_CLIENT_RE = re.compile(
    r'apiClient\.(get|post|put|delete|performSensitiveAction|sendTelemetry)\s*\(\s*'
    r'(?:' + _APICLIENT_BT
    + r'|' + _APICLIENT_DQ
    + r'|' + _APICLIENT_SQ + r')'
)

WS_CALL_RE = re.compile(
    r'(?:new\s+EventSource|new\s+WebSocket|\.connect\(\s*)\(\s*'
    r'(?:' + _BT + r'\s*([^' + _BT + r']*?)\s*' + _BT
    + r'|' + _FETCH_DQ
    + r'|' + _FETCH_SQ + r')'
)

# Pattern for finding string literals after a getApiBaseUrl() call in concatenation
_CONCAT_STR_RE = re.compile(r'(["' + _BT + r'])([^"' + _BT + r']+)(["' + _BT + r'])')


@dataclass
class BackendRoute:
    path: str
    method: str
    file: str
    line: int
    is_admin: bool = False
    is_websocket: bool = False
    tags: list[str] = field(default_factory=list)


@dataclass
class FrontendCall:
    raw_path: str
    normalized: str
    method: str
    file: str
    line: int
    call_type: str = 'fetch'


@dataclass
class RouteMatchResult:
    backend_routes: list[BackendRoute] = field(default_factory=list)
    frontend_calls: list[FrontendCall] = field(default_factory=list)
    dead_apis: list[dict] = field(default_factory=list)
    phantom_calls: list[dict] = field(default_factory=list)


def normalize_path(path: str) -> str:
    path = path.strip()
    if not path.startswith('/'):
        path = '/' + path
    while '//' in path:
        path = path.replace('//', '/')
    if len(path) > 1 and path.endswith('/'):
        path = path.rstrip('/')
    return path


def path_to_pattern(path: str) -> str:
    pattern = re.sub(r'\{[^}]+\}', '{PARAM}', path)
    pattern = re.sub(r'\$\{[^}]+\}', '{PARAM}', pattern)
    return pattern


def paths_match(backend_pattern: str, frontend_pattern: str) -> bool:
    bp = backend_pattern.rstrip('/')
    fp = frontend_pattern.rstrip('/')
    if bp == fp:
        return True
    b_segments = bp.split('/')
    f_segments = fp.split('/')
    if len(b_segments) != len(f_segments):
        return False
    for bs, fs in zip(b_segments, f_segments):
        if bs == '{PARAM}' or fs == '{PARAM}':
            continue
        if bs != fs:
            return False
    return True


def extract_router_prefix_from_ast(file_path: Path) -> str:
    try:
        source = file_path.read_text(encoding='utf-8', errors='ignore')
    except (OSError, UnicodeDecodeError):
        return ''
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ''
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'router':
                    if isinstance(node.value, ast.Call):
                        call = node.value
                        if isinstance(call.func, ast.Name) and call.func.id == 'APIRouter':
                            for kw in call.keywords:
                                if kw.arg == 'prefix' and isinstance(kw.value, ast.Constant):
                                    return str(kw.value.value)
    return ''


def extract_routes_from_file(file_path: Path, extra_prefix: str = '') -> list[BackendRoute]:
    routes: list[BackendRoute] = []
    rel_path = str(file_path.relative_to(REPO_ROOT))

    try:
        source = file_path.read_text(encoding='utf-8', errors='ignore')
    except (OSError, UnicodeDecodeError):
        return routes

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _extract_routes_regex(source, rel_path, extra_prefix)

    router_names: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if isinstance(node.value, ast.Call):
                        func = node.value.func
                        if isinstance(func, ast.Attribute) and func.attr == 'APIRouter':
                            router_names.add(target.id)
                        elif isinstance(func, ast.Name) and func.id == 'APIRouter':
                            router_names.add(target.id)
                        elif isinstance(func, ast.Name) and func.id == 'FastAPI':
                            router_names.add(target.id)
    if not router_names:
        router_names = {'router', 'app'}

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                method, path = _parse_route_decorator(decorator, router_names)
                if method and path:
                    file_prefix = extract_router_prefix_from_ast(file_path)
                    full_prefix = extra_prefix + file_prefix
                    full_path = normalize_path(full_prefix + path)
                    is_ws = method.lower() == 'websocket'
                    routes.append(BackendRoute(
                        path=full_path,
                        method=method.upper() if not is_ws else 'WEBSOCKET',
                        file=rel_path,
                        line=node.lineno,
                        is_websocket=is_ws,
                    ))

    if not routes:
        routes = _extract_routes_regex(source, rel_path, extra_prefix)

    return routes


def _parse_route_decorator(decorator, router_names: set[str]) -> tuple:
    if isinstance(decorator, ast.Call):
        func = decorator.func
        if isinstance(func, ast.Attribute):
            obj_name = None
            if isinstance(func.value, ast.Name):
                obj_name = func.value.id
            elif isinstance(func.value, ast.Attribute):
                obj_name = func.value.attr
            if obj_name and obj_name in router_names and func.attr.lower() in ALL_METHODS:
                method = func.attr.lower()
                if decorator.args and isinstance(decorator.args[0], ast.Constant):
                    return method, str(decorator.args[0].value)
    return None, None


def _extract_routes_regex(source: str, rel_path: str, extra_prefix: str) -> list[BackendRoute]:
    routes: list[BackendRoute] = []
    pattern = re.compile(
        r'@(\w+)\.(get|post|put|delete|patch|websocket)\s*\(\s*["\x27](.*?)["\x27]\s*\)'
    )
    router_names = {'router', 'app', 'sub_router', 'admin_router'}
    for i, line in enumerate(source.splitlines(), 1):
        m = pattern.search(line)
        if m:
            obj = m.group(1)
            if obj not in router_names:
                continue
            method = m.group(2)
            path = m.group(3)
            full_path = normalize_path(extra_prefix + path)
            routes.append(BackendRoute(
                path=full_path,
                method=method.upper() if method != 'websocket' else 'WEBSOCKET',
                file=rel_path,
                line=i,
                is_websocket=(method == 'websocket'),
            ))
    return routes


def load_router_registry() -> dict[str, dict]:
    registry: dict[str, dict] = {}
    routers_file = BACKEND_DIR / 'api' / 'routers.py'
    if not routers_file.exists():
        return registry
    try:
        source = routers_file.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return registry
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return registry
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'ALL_ROUTERS':
                    if isinstance(node.value, ast.List):
                        for item in node.value.elts:
                            if isinstance(item, ast.Dict):
                                entry: dict[str, str] = {}
                                for k, v in zip(item.keys, item.values):
                                    if (isinstance(k, ast.Constant)
                                            and isinstance(v, ast.Constant)):
                                        entry[str(k.value)] = str(v.value)
                                mod_path = entry.get('path', '')
                                if mod_path:
                                    registry[mod_path] = {
                                        'prefix': entry.get('prefix', ''),
                                        'is_admin': entry.get('is_admin', '').lower() == 'true',
                                    }
    return registry


def load_tier_s_registry() -> dict[str, str]:
    registry: dict[str, str] = {}
    tier_s_file = BACKEND_DIR / 'api' / 'routes' / 'tier_s_routes.py'
    if not tier_s_file.exists():
        return registry
    try:
        source = tier_s_file.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return registry
    for m in re.finditer(r'(\w+_router)\s*,\s*["\x27](.*?)["\x27]\s*,', source):
        router_var = m.group(1)
        prefix = m.group(2)
        file_name = router_var.replace('_router', '')
        registry[file_name] = prefix
    return registry


def discover_all_backend_routes() -> list[BackendRoute]:
    all_routes: list[BackendRoute] = []

    router_registry = load_router_registry()
    for mod_path, info in router_registry.items():
        prefix = info['prefix']
        is_admin = info['is_admin']
        file_path = BACKEND_DIR / (mod_path.replace('.', '/') + '.py')
        if file_path.exists():
            file_routes = extract_routes_from_file(file_path, prefix)
            for r in file_routes:
                r.is_admin = is_admin
            all_routes.extend(file_routes)

    tier_s_registry = load_tier_s_registry()
    for file_name, prefix in tier_s_registry.items():
        candidates = list((BACKEND_DIR / 'api' / 'routes').glob(f'{file_name}.py'))
        if not candidates:
            candidates = list((BACKEND_DIR / 'api' / 'routes').glob(f'*{file_name}*.py'))
        for fp in candidates:
            routes = extract_routes_from_file(fp, prefix)
            all_routes.extend(routes)

    admin_routes_file = BACKEND_DIR / 'api' / 'routes' / 'admin_routes.py'
    if admin_routes_file.exists():
        routes = extract_routes_from_file(admin_routes_file, '')
        for r in routes:
            r.is_admin = True
        all_routes.extend(routes)

    health_routes_file = BACKEND_DIR / 'core' / 'health_routes.py'
    if health_routes_file.exists():
        routes = extract_routes_from_file(health_routes_file, '/health')
        all_routes.extend(routes)

    app_file = BACKEND_DIR / 'core' / 'app.py'
    if app_file.exists():
        routes = extract_routes_from_file(app_file, '')
        all_routes.extend(routes)

    tools_dirs = [
        BACKEND_DIR / 'tools',
        BACKEND_DIR / 'tools' / 'code',
        BACKEND_DIR / 'tools' / 'media',
        BACKEND_DIR / 'tools' / 'learning',
        BACKEND_DIR / 'tools' / 'social',
    ]
    for td in tools_dirs:
        if not td.exists():
            continue
        for py_file in td.glob('*.py'):
            if py_file.name.startswith('_'):
                continue
            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
            except OSError:
                continue
            if 'APIRouter' not in content and '@router.' not in content:
                continue
            mod_name = _file_to_module_name(py_file)
            prefix = ''
            for reg_mod, info in router_registry.items():
                if reg_mod.endswith(mod_name) or mod_name.endswith(reg_mod.split('.')[-1]):
                    prefix = info['prefix']
                    break
            routes = extract_routes_from_file(py_file, prefix)
            all_routes.extend(routes)

    routes_dir = BACKEND_DIR / 'api' / 'routes'
    if routes_dir.exists():
        processed_files: set[str] = set()
        for r in all_routes:
            processed_files.add(r.file)
        for py_file in sorted(routes_dir.rglob('*.py')):
            if py_file.name.startswith('_'):
                continue
            rel = str(py_file.relative_to(REPO_ROOT))
            if rel in processed_files:
                continue
            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
            except OSError:
                continue
            if '@router.' not in content and '@app.' not in content:
                continue
            mod_name = py_file.stem
            prefix = ''
            for reg_mod, info in router_registry.items():
                if reg_mod.endswith(mod_name):
                    prefix = info['prefix']
                    break
            for ts_name, ts_prefix in tier_s_registry.items():
                if mod_name == ts_name or mod_name.replace('_', '') == ts_name.replace('_', ''):
                    prefix = ts_prefix
                    break
            routes = extract_routes_from_file(py_file, prefix)
            all_routes.extend(routes)

    orch_file = BACKEND_DIR / 'core' / 'orchestration' / 'orchestrator.py'
    if orch_file.exists():
        try:
            content = orch_file.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            print('Silenced error in except block')
        else:
            if '@router.' in content or '@app.' in content:
                routes = extract_routes_from_file(orch_file, '')
                all_routes.extend(routes)

    return all_routes


def _file_to_module_name(file_path: Path) -> str:
    try:
        rel = file_path.relative_to(BACKEND_DIR)
    except ValueError:
        rel = file_path
    parts = list(rel.parts)
    if parts and parts[-1].endswith('.py'):
        parts[-1] = parts[-1][:-3]
    return '.'.join(parts)


def extract_template_path(raw: str) -> str:
    pattern = re.sub(r'\$\{[^}]+\}', '{PARAM}', raw)
    if '+' in pattern:
        parts = pattern.split('+')
        static_parts = []
        has_dynamic = False
        for p in parts:
            p = p.strip().strip(chr(34) + chr(39) + _BT)
            if p and p != '{PARAM}':
                static_parts.append(p)
            else:
                has_dynamic = True
        if has_dynamic and static_parts:
            pattern = '/'.join(static_parts) + '/{PARAM}'
        else:
            pattern = '{PARAM}'
    return normalize_path(pattern)


def discover_all_frontend_calls() -> list[FrontendCall]:
    calls: list[FrontendCall] = []
    if not FRONTEND_DIR.exists():
        print(f'Frontend directory not found: {FRONTEND_DIR}', file=sys.stderr)
        return calls
    for ts_file in sorted(FRONTEND_DIR.rglob('*.ts')):
        calls.extend(_extract_calls_from_frontend_file(ts_file))
    for tsx_file in sorted(FRONTEND_DIR.rglob('*.tsx')):
        calls.extend(_extract_calls_from_frontend_file(tsx_file))
    return calls


def _extract_calls_from_frontend_file(file_path: Path) -> list[FrontendCall]:
    calls: list[FrontendCall] = []
    rel_path = str(file_path.relative_to(REPO_ROOT))
    try:
        source = file_path.read_text(encoding='utf-8', errors='ignore')
    except (OSError, UnicodeDecodeError):
        return calls
    lines = source.splitlines()

    for i, line in enumerate(lines, 1):
        # apiClient calls
        for m in API_CLIENT_RE.finditer(line):
            method_hint = m.group(1).upper()
            raw = m.group(2) or m.group(3) or m.group(4) or ''
            if not raw:
                continue
            normalized = extract_template_path(raw)
            if not normalized or normalized == '/{PARAM}':
                continue
            effective_method = method_hint if method_hint != 'SENDTELEMETRY' else 'ANY'
            calls.append(FrontendCall(
                raw_path=raw, normalized=normalized, method=effective_method,
                file=rel_path, line=i, call_type='apiClient',
            ))

        # fetch / fetchWithRetry calls
        for m in FETCH_CALL_RE.finditer(line):
            # group 4 is getApiBaseUrl() match - need to find path in concatenation
            if m.group(4):
                rest_of_line = line[m.end():]
                cm = _CONCAT_STR_RE.search(rest_of_line)
                if cm:
                    raw = cm.group(2)
                    normalized = extract_template_path(raw)
                    if normalized and normalized != '/{PARAM}':
                        calls.append(FrontendCall(
                            raw_path=raw, normalized=normalized, method='ANY',
                            file=rel_path, line=i, call_type='fetch',
                        ))
                continue
            raw = m.group(1) or m.group(2) or m.group(3) or ''
            if not raw:
                continue
            normalized = extract_template_path(raw)
            if not normalized or normalized == '/{PARAM}':
                continue
            method = 'ANY'
            _mre = re.compile(r"method\s*:\s*[\x22'](GET|POST|PUT|DELETE|PATCH)[\x22']")
            method_match = _mre.search(line)
            if method_match:
                method = method_match.group(1)
            calls.append(FrontendCall(
                raw_path=raw, normalized=normalized, method=method,
                file=rel_path, line=i, call_type='fetch',
            ))

        # WebSocket / EventSource calls
        for m in WS_CALL_RE.finditer(line):
            raw = m.group(1) or m.group(2) or m.group(3) or ''
            if not raw:
                continue
            if 'getWebSocketBaseUrl' in raw or 'getApiBaseUrl' in raw:
                continue
            normalized = extract_template_path(raw)
            if not normalized or normalized == '/{PARAM}':
                continue
            calls.append(FrontendCall(
                raw_path=raw, normalized=normalized, method='WEBSOCKET',
                file=rel_path, line=i, call_type='websocket',
            ))

    return calls


def classify_dead_route(route: BackendRoute) -> str:
    if HEALTH_PATTERNS.search(route.path):
        return 'internal_health'
    if WEBHOOK_PATTERNS.search(route.path) or 'webhook' in route.file.lower():
        return 'webhook_receiver'
    if route.is_admin or ADMIN_PATTERNS.search(route.path):
        return 'admin_only'
    return 'orphan_user_facing'


def classify_phantom_call(call: FrontendCall) -> str:
    if HEALTH_PATTERNS.search(call.normalized):
        return 'middleware_only'
    return 'removed_or_renamed'


def match_routes_and_calls(
    backend_routes: list[BackendRoute],
    frontend_calls: list[FrontendCall],
) -> RouteMatchResult:
    result = RouteMatchResult(
        backend_routes=backend_routes,
        frontend_calls=frontend_calls,
    )

    backend_patterns: dict[str, list[BackendRoute]] = {}
    for r in backend_routes:
        pat = path_to_pattern(r.path)
        backend_patterns.setdefault(pat, []).append(r)

    frontend_patterns: dict[str, list[FrontendCall]] = {}
    for c in frontend_calls:
        pat = path_to_pattern(c.normalized)
        frontend_patterns.setdefault(pat, []).append(c)

    matched_backend: set[str] = set()
    matched_frontend: set[str] = set()

    for bp in backend_patterns:
        for fp in frontend_patterns:
            if paths_match(bp, fp):
                matched_backend.add(bp)
                matched_frontend.add(fp)
                break

    for bp, b_routes in backend_patterns.items():
        if bp not in matched_backend:
            for r in b_routes:
                category = classify_dead_route(r)
                result.dead_apis.append({
                    'path': r.path, 'method': r.method, 'file': r.file,
                    'line': r.line, 'category': category, 'is_websocket': r.is_websocket,
                })

    for fp, f_calls in frontend_patterns.items():
        if fp not in matched_frontend:
            for c in f_calls:
                category = classify_phantom_call(c)
                result.phantom_calls.append({
                    'path': c.normalized, 'raw_path': c.raw_path, 'method': c.method,
                    'file': c.file, 'line': c.line, 'call_type': c.call_type,
                    'category': category,
                })

    return result


def generate_markdown_report(result: RouteMatchResult, include_internal: bool) -> str:
    lines_out: list[str] = []
    lines_out.append('# SupremeAI Orphan Route Finder Report')
    lines_out.append('')
    lines_out.append(f'**Backend Routes**: {len(result.backend_routes)}')
    lines_out.append(f'**Frontend API Calls**: {len(result.frontend_calls)}')
    lines_out.append('')

    dead = result.dead_apis
    if include_internal:
        filtered_dead = dead
    else:
        filtered_dead = [d for d in dead if d['category'] == 'orphan_user_facing']

    lines_out.append('---')
    lines_out.append('')
    if not include_internal:
        lines_out.append(f'## Dead APIs (User-Facing Only) - {len(filtered_dead)} found')
    else:
        lines_out.append(f'## Dead APIs (All) - {len(dead)} found')
    lines_out.append('')

    if not filtered_dead:
        lines_out.append('No orphaned user-facing routes found.')
    else:
        categories: dict[str, list] = {}
        for d in filtered_dead:
            categories.setdefault(d['category'], []).append(d)

        cat_labels = {
            'orphan_user_facing': ('HIGH', 'Genuinely Orphaned User-Facing'),
            'internal_health': ('EXPECTED', 'Internal/Health Endpoints'),
            'webhook_receiver': ('EXPECTED', 'Webhook Receivers'),
            'admin_only': ('ADMIN', 'Admin-Only Endpoints'),
        }

        for cat_name, items in categories.items():
            severity, label = cat_labels.get(cat_name, ('OTHER', cat_name))
            lines_out.append(f'### [{severity}] {label} ({len(items)})')
            lines_out.append('')
            lines_out.append('| Method | Path | File | Line |')
            lines_out.append('|--------|------|------|------|')
            for item in sorted(items, key=lambda x: x['path']):
                ws_tag = ' [WS]' if item['is_websocket'] else ''
                lines_out.append(
                    f"| `{item['method']}`{ws_tag} | `{item['path']}` "
                    f"| `{item['file']}` | {item['line']} |"
                )
            lines_out.append('')

    phantoms = result.phantom_calls
    lines_out.append('---')
    lines_out.append('')
    lines_out.append(f'## Phantom Calls - {len(phantoms)} found')
    lines_out.append('')

    if not phantoms:
        lines_out.append('No phantom frontend calls found.')
    else:
        categories = {}
        for p in phantoms:
            categories.setdefault(p['category'], []).append(p)

        cat_labels_p = {
            'removed_or_renamed': ('HIGH', 'Removed/Renamed Endpoints'),
            'middleware_only': ('MIDDLEWARE', 'Might Hit Middleware'),
        }

        for cat_name, items in categories.items():
            severity, label = cat_labels_p.get(cat_name, ('OTHER', cat_name))
            lines_out.append(f'### [{severity}] {label} ({len(items)})')
            lines_out.append('')
            lines_out.append('| Method | Path | Call Type | File | Line |')
            lines_out.append('|--------|------|-----------|------|------|')
            for item in sorted(items, key=lambda x: x['path']):
                lines_out.append(
                    f"| `{item['method']}` | `{item['path']}` | {item['call_type']} "
                    f"| `{item['file']}` | {item['line']} |"
                )
            lines_out.append('')

    lines_out.append('---')
    lines_out.append('')
    lines_out.append('## Summary')
    lines_out.append('')

    orphan_high = len([d for d in dead if d['category'] == 'orphan_user_facing'])
    phantom_high = len([p for p in phantoms if p['category'] == 'removed_or_renamed'])

    lines_out.append('| Metric | Count |')
    lines_out.append('|--------|-------|')
    lines_out.append(f'| Total Backend Routes | {len(result.backend_routes)} |')
    lines_out.append(f'| Total Frontend Calls | {len(result.frontend_calls)} |')
    lines_out.append(f'| Dead APIs (all) | {len(dead)} |')
    lines_out.append(f'| Orphan User-Facing | {orphan_high} |')
    lines_out.append(f'| Phantom (removed/renamed) | {phantom_high} |')
    if include_internal:
        lines_out.append(f'| Health/Internal | {len([d for d in dead if d["category"] == "internal_health"])} |')
        lines_out.append(f'| Webhooks | {len([d for d in dead if d["category"] == "webhook_receiver"])} |')
        lines_out.append(f'| Admin-Only | {len([d for d in dead if d["category"] == "admin_only"])} |')
    lines_out.append('')

    if orphan_high == 0 and phantom_high == 0:
        lines_out.append('**Clean!** No high-severity orphans or phantoms detected.')
    else:
        lines_out.append(
            f'**Action Required**: {orphan_high} orphan(s) + {phantom_high} phantom(s) found.'
        )

    return '\n'.join(lines_out)


def generate_json_report(result: RouteMatchResult, include_internal: bool) -> str:
    dead = result.dead_apis
    if not include_internal:
        dead = [d for d in dead if d['category'] == 'orphan_user_facing']
    orphan_high = len([d for d in dead if d['category'] == 'orphan_user_facing'])
    phantom_high = len([p for p in result.phantom_calls if p['category'] == 'removed_or_renamed'])
    report = {
        'summary': {
            'total_backend_routes': len(result.backend_routes),
            'total_frontend_calls': len(result.frontend_calls),
            'dead_apis_count': len(dead),
            'phantom_calls_count': len(result.phantom_calls),
            'orphan_user_facing_count': orphan_high,
            'phantom_high_count': phantom_high,
            'clean': orphan_high == 0 and phantom_high == 0,
        },
        'dead_apis': dead,
        'phantom_calls': result.phantom_calls,
    }
    return json.dumps(report, indent=2, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(
        description='SupremeAI Orphan Route Finder: backend routes vs frontend API calls'
    )
    parser.add_argument('--json', action='store_true', dest='json_output',
                        help='JSON output (default: Markdown)')
    parser.add_argument('--dead-only', action='store_true', dest='dead_only',
                        help='Show only Dead APIs')
    parser.add_argument('--phantom-only', action='store_true', dest='phantom_only',
                        help='Show only Phantom Calls')
    parser.add_argument('--include-internal', action='store_true', dest='include_internal',
                        help='Include health/webhook/admin endpoints')
    args = parser.parse_args()

    print(f'Repo root: {REPO_ROOT}', file=sys.stderr)
    print(f'Backend: {BACKEND_DIR}', file=sys.stderr)
    print(f'Frontend: {FRONTEND_DIR}', file=sys.stderr)
    print('', file=sys.stderr)

    try:
        print('Discovering backend routes...', file=sys.stderr)
        backend_routes = discover_all_backend_routes()
        print(f'   Found {len(backend_routes)} backend routes', file=sys.stderr)

        print('Discovering frontend API calls...', file=sys.stderr)
        frontend_calls = discover_all_frontend_calls()
        print(f'   Found {len(frontend_calls)} frontend API calls', file=sys.stderr)

        print('Matching and classifying...', file=sys.stderr)
        result = match_routes_and_calls(backend_routes, frontend_calls)

        if args.dead_only:
            dead = result.dead_apis
            if not args.include_internal:
                dead = [d for d in dead if d['category'] == 'orphan_user_facing']
            if args.json_output:
                print(json.dumps(dead, indent=2, ensure_ascii=False))
            else:
                if not dead:
                    print('No orphaned routes found.')
                for d in sorted(dead, key=lambda x: (x['category'], x['path'])):
                    sev = {'orphan_user_facing': 'HIGH', 'admin_only': 'ADMIN'}.get(d['category'], 'LOW')
                    ws = ' [WS]' if d['is_websocket'] else ''
                    print(f'[{sev}] {d["method"]}{ws} {d["path"]}  ({d["file"]}:{d["line"]})')

        elif args.phantom_only:
            phantoms = result.phantom_calls
            if args.json_output:
                print(json.dumps(phantoms, indent=2, ensure_ascii=False))
            else:
                if not phantoms:
                    print('No phantom calls found.')
                for p in sorted(phantoms, key=lambda x: (x['category'], x['path'])):
                    sev = 'HIGH' if p['category'] == 'removed_or_renamed' else 'MIDDLEWARE'
                    print(f'[{sev}] {p["method"]} {p["path"]} ({p["file"]}:{p["line"]}) [{p["call_type"]}]')

        elif args.json_output:
            print(generate_json_report(result, args.include_internal))

        else:
            print(generate_markdown_report(result, args.include_internal))

        orphan_high = len([d for d in result.dead_apis if d['category'] == 'orphan_user_facing'])
        phantom_high = len([p for p in result.phantom_calls if p['category'] == 'removed_or_renamed'])

        if orphan_high > 0 or phantom_high > 0:
            print(f'Exit code 1: {orphan_high} orphan(s) + {phantom_high} phantom(s).', file=sys.stderr)
            return 1
        else:
            print('Exit code 0: Clean.', file=sys.stderr)
            return 0

    except Exception as e:
        print(f'Error: {e}', file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
