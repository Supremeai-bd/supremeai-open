import os
import sys
import re
import ast
import json
from collections import defaultdict

def scan_underutilized_capabilities():
    print("1. Scanning Backend Classes & Methods for Usage Ratio...")

    # Subsystems to inspect
    target_dirs = [
        'backend/brain', 'backend/engine', 'backend/memory', 'backend/agents',
        'backend/adaptive_engine', 'backend/learning', 'backend/evolution',
        'backend/browser', 'backend/tools', 'backend/services', 'backend/pipelines',
        'backend/core/cache', 'backend/core/security', 'backend/core/orchestrator',
        'backend/core/routing', 'backend/core/rag', 'backend/core/audit'
    ]

    # Collect all Python files in the entire project
    all_py_files = []
    for root, _, files in os.walk('backend'):
        if any(ign in root for ign in ['.venv', '.venv_ci', '__pycache__', 'tests', 'htmlcov']):
            continue
        for f in files:
            if f.endswith('.py'):
                all_py_files.append(os.path.join(root, f).replace('\\', '/'))

    # Read all files into memory
    file_contents = {}
    for fp in all_py_files:
        try:
            with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                file_contents[fp] = f.read()
        except Exception as error:
            print(f"Unable to inspect capability input: {error}", file=sys.stderr)

    # Collect classes and their public methods in target_dirs
    class_registry = []

    for td in target_dirs:
        if not os.path.exists(td):
            continue
        for root, _, files in os.walk(td):
            for f in files:
                if f.endswith('.py') and not f.startswith('__'):
                    filepath = os.path.join(root, f).replace('\\', '/')
                    content = file_contents.get(filepath, "")
                    try:
                        tree = ast.parse(content)
                        for node in tree.body:
                            if isinstance(node, ast.ClassDef):
                                class_name = node.name
                                public_methods = []
                                for item in node.body:
                                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                        if not item.name.startswith('_') or item.name in ['__call__']:
                                            public_methods.append(item.name)
                                class_registry.append({
                                    "class_name": class_name,
                                    "filepath": filepath,
                                    "total_methods": len(public_methods),
                                    "methods": public_methods
                                })
                    except Exception as parse_error:
                        print(f"Unable to parse class source {filepath}: {parse_error}", file=sys.stderr)

    print(f"Total core classes identified: {len(class_registry)}")

    # Check method call usage across the codebase
    underutilized_classes = []

    for cls_info in class_registry:
        cname = cls_info["class_name"]
        fpath = cls_info["filepath"]
        methods = cls_info["methods"]

        # Check if class itself is imported anywhere outside its own file
        class_import_pattern = re.compile(rf"\b{re.escape(cname)}\b")
        class_refs = 0
        method_usage = defaultdict(int)

        for fp, code in file_contents.items():
            if fp == fpath:
                continue
            if class_import_pattern.search(code):
                class_refs += 1
                for m in methods:
                    if re.search(rf"\.{re.escape(m)}\b", code):
                        method_usage[m] += 1

        used_methods = [m for m, count in method_usage.items() if count > 0]
        dormant_methods = [m for m in methods if m not in used_methods]

        total_m = len(methods)
        if total_m > 0:
            usage_ratio = len(used_methods) / total_m
            # If class is imported, but > 50% of its capabilities/methods are completely uncalled
            if class_refs > 0 and usage_ratio <= 0.4 and total_m >= 3:
                underutilized_classes.append({
                    "class_name": cname,
                    "filepath": fpath,
                    "class_references": class_refs,
                    "total_methods": total_m,
                    "used_methods": used_methods,
                    "dormant_methods": dormant_methods,
                    "utilization_rate": round(usage_ratio * 100, 1)
                })

    print(f"Underutilized classes found: {len(underutilized_classes)}")

    # 2. Check Mounted Routes with Dormant Endpoints
    print("2. Scanning Mounted API Routes with Dormant/Unused Endpoints...")
    sys.path.insert(0, '.')
    from scripts.audit_isolated_components import audit_routes
    routes_data = audit_routes()

    # For mounted routes, check if their endpoints are called by frontend
    frontend_files = []
    fe_corpus = ""
    for root, _, files in os.walk('frontend/src'):
        for f in files:
            if f.endswith(('.ts', '.tsx', '.js', '.jsx')):
                p = os.path.join(root, f)
                frontend_files.append(p)
                try:
                    with open(p, 'r', encoding='utf-8', errors='ignore') as fe_f:
                        fe_corpus += fe_f.read() + "\n"
                except Exception as read_error:
                    print(f"Unable to read frontend source {p}: {read_error}", file=sys.stderr)

    # Check mounted route files for endpoints that frontend never calls
    underutilized_routes = []
    for rf_name in [f[:-3] for f in os.listdir('backend/api/routes') if f.endswith('.py') and not f.startswith('__')]:
        rf_path = f"backend/api/routes/{rf_name}.py"
        try:
            with open(rf_path, 'r', encoding='utf-8', errors='ignore') as rf_f:
                rf_content = rf_f.read()

            m_pref = re.search(r"APIRouter\s*\([^)]*prefix\s*=\s*['\"]([^'\"]+)['\"]", rf_content)
            prefix = m_pref.group(1) if m_pref else ""

            endpoints = []
            for match in re.finditer(r"@router\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]*)['\"]", rf_content):
                ep = match.group(2)
                endpoints.append(ep)

            if len(endpoints) >= 3:
                used_by_fe = []
                unused_by_fe = []
                for ep in endpoints:
                    # check if endpoint path or prefix is in fe_corpus
                    clean_ep = ep.strip('/').split('{')[0].strip('/')
                    if clean_ep and (clean_ep in fe_corpus or (prefix and prefix.strip('/') in fe_corpus)):
                        used_by_fe.append(ep)
                    else:
                        unused_by_fe.append(ep)

                if len(used_by_fe) == 0 or (len(unused_by_fe) / len(endpoints) >= 0.6):
                    underutilized_routes.append({
                        "route_file": rf_name,
                        "prefix": prefix,
                        "total_endpoints": len(endpoints),
                        "dormant_endpoints": unused_by_fe[:6],
                        "dormant_count": len(unused_by_fe)
                    })
        except Exception as error:
            print(f"Unable to inspect capability input: {error}", file=sys.stderr)

    print(f"Underutilized mounted route files: {len(underutilized_routes)}")

    # 3. Check Underutilized Advanced Frontend Components (Components imported but props/features ignored)
    print("3. Scanning Frontend Components with Dormant Modes/Props...")
    underutilized_fe = []
    # Check for components with multiple modes/tabs where only 1 is active
    for root, _, files in os.walk('frontend/src'):
        for f in files:
            if f.endswith('.tsx'):
                fp = os.path.join(root, f).replace('\\', '/')
                try:
                    with open(fp, 'r', encoding='utf-8', errors='ignore') as comp_f:
                        c_content = comp_f.read()

                    # detect enum or union modes
                    modes = re.findall(r"type\s+\w*Mode\s*=\s*([^\n;]+)", c_content)
                    tabs = re.findall(r"const\s+\w*TABS\s*=\s*\[([^\]]+)\]", c_content)

                    if modes or tabs:
                        comp_name = f[:-4]
                        # check how many occurrences in fe_corpus
                        refs = len(re.findall(rf"<{comp_name}\\b", fe_corpus))
                        if refs <= 1:
                            underutilized_fe.append({
                                "component": fp,
                                "name": comp_name,
                                "modes_or_tabs": (modes + tabs)[:2],
                                "usage_count": refs
                            })
                except Exception as component_error:
                    print(f"Unable to inspect frontend component {fp}: {component_error}", file=sys.stderr)

    output_data = {
        "underutilized_classes": underutilized_classes,
        "underutilized_routes": underutilized_routes,
        "underutilized_frontend": underutilized_fe
    }

    with open('docs/audit_reports/underutilized_capabilities_raw.json', 'w', encoding='utf-8') as out_f:
        json.dump(output_data, out_f, indent=2)

    print("Underutilized capabilities report written to docs/audit_reports/underutilized_capabilities_raw.json")

if __name__ == '__main__':
    scan_underutilized_capabilities()
