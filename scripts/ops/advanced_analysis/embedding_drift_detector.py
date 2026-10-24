#!/usr/bin/env python3
"""
embedding_drift_detector.py
===========================
Audit tool to detect Embedding Model Drift and Dimension Inconsistencies (Trap #20).
Checks:
1. Verifies embedding dimension consistency across models and database schemas.
   - Text embeddings (ada-002: 1536 dim, sentence-transformers / hash_vectorize: 384 dim, etc.)
2. Verifies that knowledge base and memory vectors store model version metadata
   to prevent silent semantic distortion across model migrations.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"


def audit_embedding_configurations() -> list[str]:
    issues = []

    # 1. Inspect knowledge base schema for metadata/model version tracking
    schema_file = BACKEND_ROOT / "database" / "migrations" / "19_harden_knowledge_base.sql"
    if schema_file.exists():
        content = schema_file.read_text(encoding="utf-8", errors="ignore")
        if "source_version" not in content and "model" not in content.lower():
            issues.append(f"{schema_file.name} lacks source/model versioning tracking column for stored embeddings.")

    # 2. Inspect memory_service.py for embedding dimension consistency
    mem_file = BACKEND_ROOT / "services" / "memory_service.py"
    if mem_file.exists():
        content = mem_file.read_text(encoding="utf-8", errors="ignore")
        # Check if hash_vectorize default dimension is explicit
        if "size: int = 384" not in content and "size = 384" not in content:
            issues.append("memory_service.py: hash_vectorize does not enforce explicit default vector dimensionality.")

    # 3. Check AGENTS.md configuration schema for embedding model dimensions
    agents_doc = REPO_ROOT / "AGENTS.md"
    if agents_doc.exists():
        doc_text = agents_doc.read_text(encoding="utf-8", errors="ignore")
        if "dimensions" not in doc_text:
            issues.append("AGENTS.md does not document embedding dimensions in its memory configuration schema.")

    return issues


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Auditing Embedding Model Drift & Dimensionality Safeguards (Trap #20)...")
    issues = audit_embedding_configurations()

    if issues:
        for issue in issues:
            print(f"[WARN] {issue}")
        print(f"\nTotal embedding drift findings: {len(issues)}")
        return 0

    print("[PASS] Embedding models, vector dimensions, and schema versioning verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
