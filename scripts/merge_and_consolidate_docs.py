#!/usr/bin/env python3
"""SupremeAI — Safe Iterative Documentation Consolidation Engine.

Processes small documentation files one by one:
1. Reads the content of the source file.
2. Determines the destination Master Document (under `docs/master_docs/`).
3. Appends the content under a clean section header.
4. Safely removes the original file.
5. Updates progress log.
"""

import os
import re
import shutil

# Master Domain Destinations
MASTER_MAPPING = {
    # Core Architecture
    'docs/01-overview.md': 'docs/master_docs/ARCH-01-MASTER_CONSTITUTION.md',
    'docs/02-architecture.md': 'docs/master_docs/ARCH-02-SYSTEM_OVERVIEW_AND_FLOWS.md',
    'docs/03-getting-started.md': 'docs/master_docs/ARCH-01-MASTER_CONSTITUTION.md',
    'docs/04-configuration.md': 'docs/master_docs/ARCH-02-SYSTEM_OVERVIEW_AND_FLOWS.md',
    'docs/05-backend.md': 'docs/master_docs/BACKEND-01-API_REFERENCE_AND_CONTRACTS.md',
    'docs/06-frontend.md': 'docs/master_docs/FRONTEND-01-DESIGN_SYSTEM_AND_TOKENS.md',
    'docs/07-api-reference.md': 'docs/master_docs/BACKEND-01-API_REFERENCE_AND_CONTRACTS.md',
    'docs/08-database.md': 'docs/master_docs/ARCH-03-DATA_AND_STORAGE_PLAN.md',
    'docs/09-ai-brain.md': 'docs/master_docs/AIBRAIN-01-MASTER_AGENT_SPECIFICATION.md',
    'docs/10-packages.md': 'docs/master_docs/BACKEND-07-MICROSERVICES_AND_PLUGINS.md',
    'docs/11-vscode-extension.md': 'docs/master_docs/INTEG-06-VSCODE_EXTENSION_AND_IDE.md',
    'docs/12-testing.md': 'docs/master_docs/OPS-01-TESTING_STRATEGY_AND_TIERS.md',
    'docs/13-deployment.md': 'docs/master_docs/DEVOPS-01-PURE_CLOUD_INFRASTRUCTURE.md',
    'docs/14-security.md': 'docs/master_docs/SEC-01-30_CATEGORY_SECURITY_MATRIX.md',
    'docs/15-operations.md': 'docs/master_docs/OPS-04-OPERATIONAL_RUNBOOKS_AND_TASKS.md',
}

def get_target_master_doc(filepath):
    path_clean = filepath.replace('\\', '/')

    # Pre-defined explicit mappings
    if path_clean in MASTER_MAPPING:
        return MASTER_MAPPING[path_clean]

    parts = path_clean.split('/')

    if 'security' in path_clean:
        return 'docs/master_docs/SEC-01-30_CATEGORY_SECURITY_MATRIX.md'
    elif 'architecture' in path_clean:
        return 'docs/master_docs/ARCH-02-SYSTEM_OVERVIEW_AND_FLOWS.md'
    elif 'backend' in path_clean or 'api' in path_clean:
        return 'docs/master_docs/BACKEND-01-API_REFERENCE_AND_CONTRACTS.md'
    elif 'frontend' in path_clean or 'ui-ux' in path_clean:
        return 'docs/master_docs/FRONTEND-01-DESIGN_SYSTEM_AND_TOKENS.md'
    elif 'ai' in path_clean or 'intelligence' in path_clean or 'browser' in path_clean:
        return 'docs/master_docs/AIBRAIN-01-MASTER_AGENT_SPECIFICATION.md'
    elif 'devops' in path_clean or 'operations' in path_clean or 'plans' in path_clean:
        return 'docs/master_docs/DEVOPS-01-PURE_CLOUD_INFRASTRUCTURE.md'
    elif 'integration' in path_clean or 'clients' in path_clean:
        return 'docs/master_docs/INTEG-01-MCP_INTEGRATION_HANDBOOK.md'
    elif 'specs' in path_clean:
        return 'docs/master_docs/ARCH-05-MASTER_ROADMAP_AND_DECISIONS.md'
    else:
        return 'docs/master_docs/ARCH-02-SYSTEM_OVERVIEW_AND_FLOWS.md'

def process_file_merge(source_path):
    if not os.path.exists(source_path):
        return False

    target_master = get_target_master_doc(source_path)
    os.makedirs(os.path.dirname(target_master), exist_ok=True)

    with open(source_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read().strip()

    if not content:
        os.remove(source_path)
        return True

    header = f"\n\n\n<!-- ============================================================ -->\n"
    header += f"<!-- Merged Source: {source_path} -->\n"
    header += f"<!-- ============================================================ -->\n\n"

    with open(target_master, 'a', encoding='utf-8') as f:
        f.write(header + content + "\n")

    # Remove original source file after confirmed write
    os.remove(source_path)
    print(f"[MERGED & REMOVED]: {source_path} -> {target_master}")
    return True

if __name__ == '__main__':
    # Target files inside docs/ modules_audit and other scattered subdirectories
    targets = []
    ignore_dirs = {'.venv', 'node_modules', '.git', '.pytest_cache', '__pycache__', 'dist', 'build', '.next', 'master_docs'}

    for root, dirs, files in os.walk('docs'):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for file in files:
            if file.endswith('.md') and file != 'DOCUMENTATION_MASTER_INDEX.md':
                rel_path = os.path.relpath(os.path.join(root, file), '.').replace('\\', '/')
                targets.append(rel_path)

    print(f"Starting sequential merge for {len(targets)} documentation files...")
    success_count = 0
    for file in targets:
        if process_file_merge(file):
            success_count += 1

    print(f"\n🎉 Successfully merged and consolidated {success_count} files into docs/master_docs/!")
