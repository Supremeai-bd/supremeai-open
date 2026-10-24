#!/usr/bin/env python3
"""
audit v2 (High-Performance Optimized) — self-discovering isolation & capability audit.
Zero-maintenance design with fast inverted-index search to run in < 15 seconds.
"""
from __future__ import annotations
import argparse, ast, fnmatch, importlib.util, json, re, subprocess, sys, os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PRUNE_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build",
    ".next", "coverage", "audit_reports", "docs", "migrations", "alembic",
    ".github", "agent-ctx", "worktrees", "site-packages", "htmlcov", ".idea", ".vscode"
}
CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".mjs"}
CONFIG_EXTS = {".yml", ".yaml", ".toml", ".json"}
TOKEN_STOPLIST = {"name", "id", "test", "main", "app", "tool", "tools", "version"}

DEFAULT_RULES = {
    "registry_var":       r"^[A-Z][A-Z0-9_]{3,}$",
    "registry_hints":     ["tools_provided", "tools", "capabilities", "actions", "commands",
                           "skills", "intents", "handlers", "operations", "keywords",
                           "endpoints", "permission_schema"],
    "tool_list_keys":     ["tools_provided", "tools", "actions", "commands", "skills",
                           "intents", "endpoints", "handlers", "operations"],
    "wiring_decorators":  ["shared_task", "app.task", "celery_app.task", "dramatiq.actor",
                           "app.on_event", "register_handler", "flow", "agent", "tool"],
    "target_excludes":    ["tests", "test_*", "migrations", "alembic", "__init__.py",
                           "__main__.py", "conftest.py", "manage.py", "wsgi.py", "asgi.py"],
    "always_entrypoints": ["backend/main.py"],
}
RULE_TEXT = {
    "ISOLATED_MODULE":  "Module is never imported, referenced, configured, or dynamically loaded",
    "INIT_ONLY_MODULE": "Module only reachable via package __init__ re-export",
    "DYNAMIC_ONLY_MODULE": "Module only reachable via dynamic namespace import",
    "FRAMEWORK_LOADED_MODULE": "Module only loaded via framework decorator",
    "IMPORT_BROKEN":    "Module raises on import (dead-route class of defect)",
    "UNDERUTILIZED_CAPABILITY": "Capability defined in a registry but never wired/invoked",
}

# ---------------------------------------------------------------- fast file gathering
def fast_walk(root: Path, exts: set[str]) -> list[Path]:
    result = []
    root_str = str(root)
    for r, dirs, filenames in os.walk(root_str):
        dirs[:] = [d for d in dirs if d not in PRUNE_DIRS]
        for fn in filenames:
            ext = os.path.splitext(fn)[1]
            if ext in exts and not fn.endswith('.lock'):
                result.append(Path(os.path.join(r, fn)))
    return result

def discover_roots(repo: Path) -> list[Path]:
    counts: dict[Path, int] = {}
    init_files = [p for p in fast_walk(repo, {".py"}) if p.name == "__init__.py"]
    for init in init_files:
        root = init.parent
        while (root.parent / "__init__.py").exists() and root.parent != repo:
            root = root.parent
        if root != repo:
            counts[root] = counts.get(root, 0) + 1
    discovered = sorted([r for r, n in counts.items() if n >= 3], key=str)
    be = repo / "backend"
    if be.exists() and be not in discovered:
        discovered.insert(0, be)
    return discovered

def load_rules(repo: Path) -> dict:
    rules = json.loads(json.dumps(DEFAULT_RULES))
    f = repo / ".audit-rules.json"
    if f.exists():
        for k, v in json.loads(f.read_text(encoding="utf-8")).items():
            rules[k] = sorted(set(rules.get(k, [])) | set(v)) if isinstance(v, list) and isinstance(rules.get(k), list) else v
    return rules

# ---------------------------------------------------------------- index
@dataclass
class Mod:
    dotted: str; file: Path; rel: str
    kind: str = "module"; entry: bool = False
    ev_kinds: set = field(default_factory=set)
    evidence: dict = field(default_factory=dict)
    router_vars: list = field(default_factory=list)

def index_modules(roots: list[Path], rules: dict) -> dict[str, Mod]:
    mods: dict[str, Mod] = {}
    for root in roots:
        py_files = fast_walk(root, {".py"})
        for f in sorted(py_files):
            parts = list(f.relative_to(root).with_suffix("").parts)
            if parts and parts[-1] == "__init__":
                parts = parts[:-1]
            dotted = ".".join(parts)
            if not dotted or dotted in mods:
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            m = Mod(dotted=dotted, file=f, rel=f.relative_to(REPO).as_posix())
            m.entry = f.name == "main.py" or f"{root.name}/{f.name}" in rules["always_entrypoints"] \
                      or bool(re.search(r'^if\s+__name__\s*==\s*["\']__main__["\']', text, re.M))
            if "Celery(" in text: m.kind = "celery"
            elif "APIRouter(" in text: m.kind = "router"
            mods[dotted] = m
    return mods

def _is_target(f: Path, rules: dict) -> bool:
    for part in f.parts:
        for g in rules["target_excludes"]:
            base = g[:-2] if g.endswith("/*") else g
            if fnmatch.fnmatch(part, g) or fnmatch.fnmatch(part, base):
                return False
    return True

# ---------------------------------------------------------------- evidence (fast indexed)
def collect_evidence(mods: dict[str, Mod], rules: dict, repo: Path, ctx):
    texts = {}
    for d, m in mods.items():
        try:
            texts[d] = m.file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            texts[d] = ""

    cfg = []
    for f in fast_walk(repo, CONFIG_EXTS):
        try:
            if f.stat().st_size <= 1_000_000:
                cfg.append((f.relative_to(REPO).as_posix(), f.read_text(encoding="utf-8", errors="ignore")))
        except OSError as exc:
            print(f"[iso-audit] config file skipped {f}: {exc}", file=sys.stderr)

    def add(target: Mod, kind: str, user: str):
        target.ev_kinds.add(kind); target.evidence.setdefault(user, set()).add(kind)

    def mark(src: Mod, dotted: str, kind: str):
        t = mods.get(dotted)
        if t and t is not src:
            actual_kind = "test" if (src.dotted.startswith("tests.") or "tests/" in src.dotted) else kind
            add(t, actual_kind, src.dotted)

    # 1. AST pass
    for m in mods.values():
        t_src = texts[m.dotted]
        try: tree = ast.parse(t_src)
        except SyntaxError: tree = None
        mp, is_pkg = m.dotted.split("."), m.file.name == "__init__.py"
        if tree:
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names: mark(m, a.name, "ast")
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        base = mp if is_pkg else mp[:-1]
                        if node.level > 1: base = base[: len(base) - (node.level - 1)]
                        base = ".".join([*base, *(node.module or "").split(".")]) if node.module else ".".join(base)
                    else:
                        base = node.module or ""
                    if base: mark(m, base, "ast")
                    for a in node.names:
                        if a.name != "*": mark(m, f"{base}.{a.name}".strip("."), "ast")
                elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) \
                        and getattr(node.value.func, "id", "") == "APIRouter":
                    m.router_vars += [t.id for t in node.targets if isinstance(t, ast.Name)]
            for d0 in rules["wiring_decorators"]:
                if f"@{d0.split('.')[-1]}" in t_src:
                    m.ev_kinds.add("decorator")

    # 2. Text matching with exact word boundary and production vs test separation
    for m in mods.values():
        pat = re.compile(rf"\b{re.escape(m.dotted)}\b")
        for d, t in texts.items():
            if d != m.dotted and pat.search(t):
                kind = "test" if (d.startswith("tests.") or "tests/" in d) else "text"
                add(m, kind, d)
        for rel, t in cfg:
            if pat.search(t):
                add(m, "config", f"config:{rel}")

    combined_texts = "\n".join(texts.values())
    ns = {p.rstrip(".") for p in re.findall(
        r'import_module\(\s*f?["\']([A-Za-z_][\w\.]*?)["\']?\s*[+\{]', combined_texts)}
    for m in mods.values():
        if any(m.dotted == n or m.dotted.startswith(n + ".") for n in ns): m.ev_kinds.add("dyn")

    for m in mods.values():
        for var in m.router_vars:
            rx = re.compile(rf"include_router\(\s*(?:[\w\.]+\.)?{re.escape(var)}\b")
            for d, t in texts.items():
                if d != m.dotted and rx.search(t):
                    kind = "test" if (d.startswith("tests.") or "tests/" in d) else "router"
                    add(m, kind, d)

    for fn in ctx.wiring_detectors: fn(mods, rules, add)
    return ns

# ---------------------------------------------------------------- capabilities
def _caps_from_value(var: str, val, m: Mod, rules: dict, top=True) -> list[dict]:
    out = []
    def emit(tok: str, pid: str):
        if tok and tok not in TOKEN_STOPLIST and len(tok) >= 4:
            out.append({"id": f"{pid}.{tok}", "token": tok, "source": m.rel,
                        "def_file": m.file, "registry": var})
    def walk(v, path, top):
        if isinstance(v, dict):
            tool_keys = [h for h in rules["tool_list_keys"] if h in v and isinstance(v[h], list)]
            if tool_keys:
                pid = str(v.get("id") or v.get("name") or "/".join(path) or var)
                for h in tool_keys:
                    for item in v[h]:
                        if isinstance(item, dict):
                            emit(str(item.get("name") or item.get("id") or ""), pid)
            else:
                for k, sub in v.items():
                    if isinstance(sub, dict): emit(str(k), var)
                    walk(sub, path + [str(k)], False)
        elif isinstance(v, list):
            if top and v and all(isinstance(x, str) for x in v):
                for s in v: emit(s, var)
            else:
                for it in v: walk(it, path, False)
    walk(val, [], top)
    return out

def find_capabilities(mods: dict[str, Mod], rules: dict, ctx) -> list[dict]:
    raw = []
    for m in mods.values():
        try: tree = ast.parse(m.file.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError: continue
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and re.match(rules["registry_var"], t.id):
                        try: raw += _caps_from_value(t.id, ast.literal_eval(node.value), m, rules)
                        except Exception as error:
                            print(f"Unable to parse capability value: {error}", file=sys.stderr)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == "update" and isinstance(node.func.value, ast.Name) \
                    and re.match(rules["registry_var"], node.func.value.id) \
                    and node.args and isinstance(node.args[0], ast.Dict):
                try: raw += _caps_from_value(node.func.value.id, ast.literal_eval(node.args[0]), m, rules)
                except Exception as error:
                    print(f"Unable to parse capability update: {error}", file=sys.stderr)
    raw += [c for fn in ctx.capability_extractors for c in fn(mods, rules)]
    seen: dict[str, dict] = {}
    for c in raw: seen.setdefault(c["id"], c)
    return list(seen.values())

def scan_capability_refs(caps: list[dict], repo: Path) -> None:
    all_files = fast_walk(repo, CODE_EXTS | CONFIG_EXTS)
    files = []
    for f in all_files:
        try:
            if f.stat().st_size <= 1_000_000:
                files.append((f, f.read_text(encoding="utf-8", errors="ignore")))
        except OSError as exc:
            print(f"[iso-audit] file skipped {f}: {exc}", file=sys.stderr)

    # Index tokens for fast presence check
    for c in caps:
        tok = c['token']
        pat = re.compile(rf"\b{re.escape(tok)}\b")
        code = test = fe = cfg = 0; locs = []
        def_res = c["def_file"].resolve()
        for f, t in files:
            if tok not in t:
                continue
            if f.resolve() == def_res:
                continue
            n = len(pat.findall(t))
            if not n: continue
            rel = f.relative_to(REPO).as_posix(); locs.append({"file": rel, "count": n})
            if "test" in rel.lower(): test += n
            elif rel.startswith("frontend/"): fe += n
            elif f.suffix in CONFIG_EXTS: cfg += n
            else: code += n
        c.update(refs_code=code, refs_test=test, refs_frontend=fe, refs_config=cfg,
                 status="wired" if code else ("orphan" if code + test + fe + cfg == 0 else
                        "test_only" if test and not (fe or cfg) else
                        "frontend_only" if fe and not cfg else "config_only"),
                 locations=locs[:8])

# ---------------------------------------------------------------- auto-test
def smoke_import(dotted: str, root: Path, timeout: int = 15):
    code = (f"import sys, importlib; sys.path.insert(0, {str(root)!r}); "
            f"importlib.import_module({dotted!r})")
    try:
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "TimeoutExpired"
    if p.returncode == 0: return True, ""
    return False, (p.stderr.strip().splitlines() or ["<no stderr>"])[-1]

# ---------------------------------------------------------------- learning & reports
def _load(p: Path, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default
def _now(): return datetime.now(timezone.utc)

def update_baseline(path: Path, keys: list[str], prune_days: int) -> dict:
    store = _load(path, {"findings": {}}); ts = _now().isoformat(); f = store.setdefault("findings", {})
    for k in keys:
        e = f.get(k, {"first_seen": ts, "seen_count": 0})
        e.update(last_seen=ts); e["seen_count"] = e.get("seen_count", 0) + 1; f[k] = e
    if prune_days:
        cut = (_now() - timedelta(days=prune_days)).isoformat()
        for k in [k for k, e in f.items() if e.get("last_seen", "") < cut]: del f[k]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2), encoding="utf-8")
    return f

def apply_allowlist(findings: list[dict], path: Path):
    al = _load(path, {})
    for f in findings:
        a = al.get(f["key"])
        if a: f.update(accepted=True, accept_reason=a.get("reason", ""), severity="info")

def to_sarif(findings: list[dict]) -> dict:
    rules, results = {}, []
    for f in findings:
        rules.setdefault(f["rule"], {"id": f["rule"],
                        "shortDescription": {"text": RULE_TEXT.get(f["rule"], f["rule"])}})
        results.append({"ruleId": f["rule"], "level": "error" if f["severity"] == "high" else "warning",
                        "message": {"text": f["message"]},
                        "locations": [{"physicalLocation": {
                            "artifactLocation": {"uri": f["file"]}, "region": {"startLine": 1}}}],
                        "partialFingerprints": {"auditKey/v1": f["key"]}})
    return {"version": "2.1.0", "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "runs": [{"tool": {"driver": {"name": "supremeai-audit",
                      "informationUri": "https://github.com/SaifulHaqueNiloy/supremeai",
                      "rules": list(rules.values())}}, "results": results}]}

class AuditCtx:
    def __init__(self):
        self.capability_extractors: list = []
        self.wiring_detectors: list = []
    def add_capability_extractor(self, fn): self.capability_extractors.append(fn)
    def add_wiring_detector(self, fn): self.wiring_detectors.append(fn)

def load_plugins(ctx: AuditCtx) -> list[str]:
    loaded, pdir = [], REPO / "scripts" / "audit_plugins"
    if not pdir.exists(): return loaded
    for f in sorted(pdir.glob("*.py")):
        if f.name.startswith("_"): continue
        spec = importlib.util.spec_from_file_location(f"audit_plugin_{f.stem}", f)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        if hasattr(mod, "register"): mod.register(ctx); loaded.append(f.name)
    return loaded

# ---------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--roots", nargs="*", help="default: auto-discover")
    ap.add_argument("--only", choices=["modules", "capabilities", "both"], default="both")
    ap.add_argument("--smoke-test", action="store_true")
    ap.add_argument("--baseline", type=Path, default=REPO / ".audit-baseline.json")
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--prune-after-days", type=int, default=45)
    ap.add_argument("--allowlist", type=Path, default=REPO / ".audit-allowlist.json")
    ap.add_argument("--exclude", nargs="*", default=[])
    ap.add_argument("--fail-on", type=int, metavar="N")
    ap.add_argument("--out", type=Path, default=REPO / "audit_reports" / "intelligent_audit")
    ap.add_argument("--format", choices=["json", "sarif", "both"], default="both")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    t0 = datetime.now()
    rules = load_rules(REPO)
    ctx = AuditCtx(); plugins = load_plugins(ctx)
    roots = [REPO / r for r in args.roots] if args.roots else discover_roots(REPO)
    mods = index_modules(roots, rules)
    ns_dyn = collect_evidence(mods, rules, REPO, ctx)

    module_findings = []
    if args.only in {"modules", "both"}:
        for m in mods.values():
            if m.entry or not _is_target(m.file, rules) or any(
                    fnmatch.fnmatch(m.rel, g) for g in args.exclude): continue
            k = m.ev_kinds
            if not k:
                st, sev, rule = "isolated", ("high" if m.kind in ("router", "celery") else "medium"), "ISOLATED_MODULE"
            elif k <= {"test"}:
                st, sev, rule = "test_only_isolated", ("high" if m.kind in ("router", "celery") else "medium"), "ISOLATED_MODULE"
            elif k <= {"init"}:  st, sev, rule = "init_only", "info", "INIT_ONLY_MODULE"
            elif k <= {"dyn"}:   st, sev, rule = "dynamic_only", "info", "DYNAMIC_ONLY_MODULE"
            elif k <= {"decorator"}: st, sev, rule = "framework_loaded", "info", "FRAMEWORK_LOADED_MODULE"
            else: continue
            module_findings.append({"rule": rule, "key": f"mod:{m.dotted}", "file": m.rel,
                "module": m.dotted, "kind": m.kind, "status": st, "severity": sev,
                "evidence_kinds": sorted(k),
                "message": f"{rule}: {m.dotted} ({m.kind}, {st})"})

    cap_findings = []
    if args.only in {"capabilities", "both"}:
        caps = find_capabilities(mods, rules, ctx)
        scan_capability_refs(caps, REPO)
        cap_findings = [{"rule": "UNDERUTILIZED_CAPABILITY", "key": f"cap:{c['id']}",
                         "file": c["source"], "capability": c["id"], "registry": c["registry"],
                         "status": c["status"], "severity": "medium" if c["status"] == "orphan" else "info",
                         "refs": {k: c.get(k, 0) for k in ("refs_code", "refs_test", "refs_frontend", "refs_config")},
                         "message": f"capability {c['id']} [{c['status']}] defined in {c['source']}"}
                        for c in caps if c["status"] != "wired"]

    findings = module_findings + cap_findings
    store = _load(args.baseline, None)
    seeded = store is None
    base_keys = set(store["findings"]) if store else set()
    for f in findings:
        if f["key"] not in base_keys:
            f["new"] = True
            if args.smoke_test and f["rule"] == "ISOLATED_MODULE":
                m = mods.get(f["module"])
                if m:
                    root = next((r for r in roots if m.file.is_relative_to(r)), roots[0])
                    ok, err = smoke_import(m.dotted, root)
                    if not ok:
                        f.update(rule="IMPORT_BROKEN", severity="high",
                                 message=f"{m.dotted} fails to import: {err}")

    apply_allowlist(findings, args.allowlist)
    if args.update_baseline or seeded:
        update_baseline(args.baseline, [f["key"] for f in findings], args.prune_after_days)

    gate = [f for f in findings if f.get("new") and not f.get("accepted")
            and f["severity"] in ("high", "medium")]

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.json").write_text(json.dumps(
        {"generated_at": _now().isoformat(), "roots": [str(r.relative_to(REPO)) for r in roots],
         "dynamic_namespaces": sorted(ns_dyn), "plugins": plugins,
         "summary": {"modules_scanned": len(mods), "findings": len(findings),
                     "new": len([f for f in findings if f.get("new")])},
         "findings": findings}, indent=2), encoding="utf-8")
    if args.format in ("sarif", "both"):
        (args.out / "audit.sarif").write_text(json.dumps(to_sarif(findings), indent=2), encoding="utf-8")

    elapsed = (datetime.now() - t0).total_seconds()
    print(f"[audit] done in {elapsed:.1f}s | roots={[str(r.relative_to(REPO)) for r in roots]} modules={len(mods)}")
    for f in sorted(gate, key=lambda x: x["severity"]):
        print(f"  [!] {f['severity']:6s} {f['rule']:24s} {f.get('module') or f.get('capability')}")
    print(f"[audit] findings={len(findings)} new={len(gate)} "
          f"{'(baseline seeded — gate armed)' if seeded else ''} -> {args.out}/")
    return 1 if args.fail_on is not None and len(gate) >= args.fail_on else 0

if __name__ == "__main__":
    sys.exit(main())
