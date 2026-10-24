import os
import sys
import re
import json

def audit_routes():
    routes_dir = os.path.join('backend', 'api', 'routes')
    all_route_files = sorted([f[:-3] for f in os.listdir(routes_dir) if f.endswith('.py') and not f.startswith('__')])

    with open(os.path.join('backend', 'api', 'routers.py'), 'r', encoding='utf-8') as f:
        routers_content = f.read()
    with open(os.path.join('backend', 'core', 'app.py'), 'r', encoding='utf-8') as f:
        app_content = f.read()
    with open(os.path.join('backend', 'main.py'), 'r', encoding='utf-8') as f:
        main_content = f.read()

    combined = routers_content + "\n" + app_content + "\n" + main_content

    unmounted = []
    mounted = []

    for rf in all_route_files:
        pattern = rf"\bapi\.routes\.{rf}\b|\bbackend\.api\.routes\.{rf}\b|\b{rf}\.router\b|['\"]api\.routes\.{rf}['\"]"
        if re.search(pattern, combined):
            mounted.append(rf)
        else:
            unmounted.append(rf)

    # Inspect unmounted files for router details (endpoints, methods, prefixes)
    unmounted_details = []
    for rf in unmounted:
        filepath = os.path.join(routes_dir, f"{rf}.py")
        endpoints = []
        router_prefix = ""
        tags = []
        loc = 0
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                loc = len(lines)
                content = "".join(lines)

                # router prefix
                m_pref = re.search(r"APIRouter\s*\([^)]*prefix\s*=\s*['\"]([^'\"]+)['\"]", content)
                if m_pref:
                    router_prefix = m_pref.group(1)

                # tags
                m_tags = re.search(r"APIRouter\s*\([^)]*tags\s*=\s*\[([^\]]+)\]", content)
                if m_tags:
                    tags = [t.strip().strip("'\"") for t in m_tags.group(1).split(',')]

                # endpoints (@router.get, @router.post, etc.)
                for match in re.finditer(r"@router\.(get|post|put|delete|patch|options|head|websocket)\s*\(\s*['\"]([^'\"]*)['\"]", content):
                    method = match.group(1).upper()
                    path = match.group(2)
                    endpoints.append(f"{method} {path}")
        except Exception as error:
            print(f"Unable to inspect route file {filepath}: {error}", file=sys.stderr)

        unmounted_details.append({
            "file": rf,
            "path": filepath.replace("\\", "/"),
            "loc": loc,
            "prefix": router_prefix,
            "tags": tags,
            "endpoint_count": len(endpoints),
            "endpoints": endpoints[:6]
        })

    return {
        "total_routes": len(all_route_files),
        "mounted_count": len(mounted),
        "unmounted_count": len(unmounted),
        "unmounted_details": unmounted_details
    }

def audit_backend_subsystems():
    backend_dirs = [
        'adapters', 'adaptive_engine', 'admin', 'agents', 'brain', 'browser',
        'byoc', 'ecosystem', 'engine', 'evolution', 'integrations', 'learning',
        'memory', 'models', 'monitoring', 'p2p', 'pipelines', 'pyerrorfix',
        'runtime', 'sandbox', 'scaling', 'scout', 'services', 'skills', 'storage',
        'tools', 'workers'
    ]

    all_target_files = []
    for d in backend_dirs:
        p = os.path.join('backend', d)
        if os.path.exists(p):
            for root, _, files in os.walk(p):
                if any(ign in root.replace('\\', '/') for ign in ['.venv', 'site-packages', '__pycache__', 'tests', 'htmlcov']):
                    continue
                for f in files:
                    if f.endswith('.py') and not f.startswith('__'):
                        rel = os.path.relpath(os.path.join(root, f), 'backend').replace('\\', '/')
                        all_target_files.append(rel)

    # Gather all searchable backend code files
    all_code_files = []
    for root, _, files in os.walk('backend'):
        if any(ign in root for ign in ['.venv', '.venv_ci', '__pycache__', 'tests', 'htmlcov']):
            continue
        for f in files:
            if f.endswith('.py'):
                all_code_files.append(os.path.join(root, f))

    # Read all code contents into memory
    code_corpus = {}
    for cf in all_code_files:
        try:
            with open(cf, 'r', encoding='utf-8', errors='ignore') as f:
                code_corpus[cf.replace('\\', '/')] = f.read()
        except Exception as error:
            print(f"Unable to read backend file {cf}: {error}", file=sys.stderr)

    unreferenced_files = []
    semi_referenced_files = []

    for target in all_target_files:
        mod_name = os.path.splitext(target)[0].replace('/', '.')
        simple_name = os.path.splitext(os.path.basename(target))[0]

        import_pat = re.compile(rf"\b(import|from)\s+[\w\.]*{re.escape(simple_name)}\b|['\"]{re.escape(mod_name)}['\"]|['\"]{re.escape(simple_name)}['\"]")

        referencing_files = []
        for cf, content in code_corpus.items():
            if cf.endswith(target):
                continue
            if import_pat.search(content):
                referencing_files.append(cf)

        target_full = 'backend/' + target
        if len(referencing_files) == 0:
            unreferenced_files.append({
                "file": target,
                "subsystem": target.split('/')[0],
                "references": 0
            })
        elif all(r.startswith('backend/tests/') or os.path.dirname(r) == os.path.dirname(target_full) for r in referencing_files):
            semi_referenced_files.append({
                "file": target,
                "subsystem": target.split('/')[0],
                "references": len(referencing_files),
                "ref_files": referencing_files[:3]
            })

    return {
        "total_subsystem_files": len(all_target_files),
        "unreferenced_count": len(unreferenced_files),
        "unreferenced_files": unreferenced_files,
        "semi_referenced_count": len(semi_referenced_files),
        "semi_referenced_files": semi_referenced_files
    }

def audit_frontend():
    frontend_src = os.path.join('frontend', 'src')
    if not os.path.exists(frontend_src):
        return {"error": "frontend/src not found"}

    all_components = []
    for root, _, files in os.walk(frontend_src):
        for f in files:
            if f.endswith(('.tsx', '.jsx')) and not f.endswith(('.test.tsx', '.test.jsx', '.stories.tsx', '.d.ts')):
                rel = os.path.relpath(os.path.join(root, f), frontend_src).replace('\\', '/')
                all_components.append(rel)

    all_frontend_files = []
    for root, _, files in os.walk(frontend_src):
        for f in files:
            if f.endswith(('.ts', '.tsx', '.js', '.jsx', '.json', '.html')):
                all_frontend_files.append(os.path.join(root, f))

    fe_corpus = {}
    for fpath in all_frontend_files:
        try:
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                fe_corpus[fpath.replace('\\', '/')] = f.read()
        except Exception as error:
            print(f"Unable to read frontend file {fpath}: {error}", file=sys.stderr)

    unused_components = []
    for comp in all_components:
        comp_base = os.path.splitext(os.path.basename(comp))[0]
        if comp_base in ['main', 'App', 'index', 'vite-env.d']:
            continue

        pat = re.compile(rf"\b(import|from)\s+.*{re.escape(comp_base)}\b|lazy\s*\(\s*\(\)\s*=>\s*import\([^)]*{re.escape(comp_base)}[^)]*\)\)|['\"].*{re.escape(comp_base)}['\"]")
        referencing = []
        for fp, content in fe_corpus.items():
            if fp.endswith(comp):
                continue
            if pat.search(content):
                referencing.append(fp)
                break

        if len(referencing) == 0:
            unused_components.append({
                "component": comp,
                "folder": comp.split('/')[0] if '/' in comp else 'root'
            })

    return {
        "total_components": len(all_components),
        "orphan_count": len(unused_components),
        "orphan_components": unused_components
    }

if __name__ == '__main__':
    print("Running Route Audit...")
    routes_res = audit_routes()
    print(f"Routes: {routes_res['unmounted_count']}/{routes_res['total_routes']} unmounted")

    print("Running Backend Subsystem Audit...")
    backend_res = audit_backend_subsystems()
    print(f"Backend: {backend_res['unreferenced_count']} completely unreferenced, {backend_res['semi_referenced_count']} isolated/test-only")

    print("Running Frontend UI Audit...")
    fe_res = audit_frontend()
    print(f"Frontend: {fe_res['orphan_count']}/{fe_res['total_components']} orphan components")

    report = {
        "routes": routes_res,
        "backend_subsystems": backend_res,
        "frontend": fe_res
    }

    os.makedirs('docs/audit_reports', exist_ok=True)
    with open('docs/audit_reports/deep_codebase_isolation_raw.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

    print("Raw report saved to docs/audit_reports/deep_codebase_isolation_raw.json")
