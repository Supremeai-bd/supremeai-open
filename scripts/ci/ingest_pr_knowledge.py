#!/usr/bin/env python3
"""Autonomous PR Knowledge Ingestion Engine.

Extracts structured, role-specific intelligence from merged Pull Requests
and stores it permanently into Supabase (knowledge_base & learned_facts)
and Qdrant (supremeai_memory) vector store.

Supports 7 Specialized Agent Roles:
  - coder: fix_mechanism, why_this_way, alternatives_rejected, pitfalls_to_avoid
  - auditor: audit_methodology, alternative_audit_methods, improper_audit_traps, prevention_gate
  - ci-fixer: root_cause_analysis, cross_platform_guarantee, fast_path_quota_impact
  - planner: reused_components, rejected_speculative_complexity, contract_compatibility
  - human-eye: permanent_system_learning, admin_work_budget_check
  - third-party: zero_credential_preservation, cold_start_resilience
  - ecosystem-scout: board_parity_finding, drift_detected_and_remedied

Stdlib-only for core execution, fail-soft on network errors (never breaks merge pipeline).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Dict, List, Optional, Tuple

MARKER_OPEN_V2 = "<!-- pr-knowledge-envelope v2 -->"
MARKER_CLOSE_V2 = "<!-- /pr-knowledge-envelope -->"
MARKER_OPEN_V1 = "<!-- pr-evidence-envelope v1 -->"
MARKER_CLOSE_V1 = "<!-- /pr-evidence-envelope -->"

VALID_ROLES = {
    "coder",
    "auditor",
    "ci-fixer",
    "planner",
    "human-eye",
    "third-party",
    "ecosystem-scout",
}

ROLE_REQUIRED_FIELDS: Dict[str, List[str]] = {
    "coder": ["fix_mechanism", "why_this_way", "alternatives_rejected", "pitfalls_to_avoid"],
    "auditor": ["audit_methodology", "alternative_audit_methods", "improper_audit_traps", "prevention_gate"],
    "ci-fixer": ["root_cause_analysis", "cross_platform_guarantee", "fast_path_quota_impact"],
    "planner": ["reused_components", "rejected_speculative_complexity", "contract_compatibility"],
    "human-eye": ["permanent_system_learning", "admin_work_budget_check"],
    "third-party": ["zero_credential_preservation", "cold_start_resilience"],
    "ecosystem-scout": ["board_parity_finding", "drift_detected_and_remedied"],
}


def extract_envelope_json(body: str) -> Tuple[Optional[dict], str]:
    """Extract and parse either v2 (knowledge) or v1 (evidence) envelope."""
    if not body:
        return None, "empty_body"

    # 1. Try V2 Knowledge Envelope
    if MARKER_OPEN_V2 in body and MARKER_CLOSE_V2 in body:
        start = body.index(MARKER_OPEN_V2) + len(MARKER_OPEN_V2)
        end = body.index(MARKER_CLOSE_V2, start)
        raw = body[start:end].strip()
        try:
            return json.loads(raw), "v2"
        except json.JSONDecodeError as err:
            return None, f"v2_json_error: {err}"

    # 2. Try V1 Evidence Envelope (backward compatibility)
    if MARKER_OPEN_V1 in body and MARKER_CLOSE_V1 in body:
        start = body.index(MARKER_OPEN_V1) + len(MARKER_OPEN_V1)
        end = body.index(MARKER_CLOSE_V1, start)
        raw = body[start:end].strip()
        try:
            return json.loads(raw), "v1"
        except json.JSONDecodeError as err:
            return None, f"v1_json_error: {err}"

    return None, "no_envelope_found"


def validate_knowledge(data: dict, version: str) -> Tuple[bool, str, str, dict]:
    """Validate envelope and extract role-specific structured knowledge."""
    if version == "v2":
        role = str(data.get("role", "coder")).strip().lower()
        if role not in VALID_ROLES:
            role = "coder"

        knowledge = data.get("knowledge", {})
        if not isinstance(knowledge, dict):
            return False, role, "knowledge field must be a dictionary", {}

        # Validate that required keys are present
        required = ROLE_REQUIRED_FIELDS.get(role, [])
        missing = [k for k in required if k not in knowledge or not knowledge[k]]
        if missing:
            return False, role, f"Missing role fields for '{role}': {', '.join(missing)}", knowledge

        return True, role, "valid_v2", knowledge

    elif version == "v1":
        # Adapt v1 envelope to coder role
        role = "coder"
        why = data.get("reflection_why", "")
        alts = data.get("alternatives_rejected", [])
        knowledge = {
            "fix_mechanism": f"Delivered via bridge envelope: {why}",
            "why_this_way": why,
            "alternatives_rejected": [{"method": str(a), "why_rejected": "Rejected during PR evaluation"} for a in alts],
            "pitfalls_to_avoid": ["Ensure backward compatibility with envelope v1 contract"],
        }
        return True, role, "valid_v1_adapted", knowledge

    return False, "unknown", "unsupported_version", {}


def format_learned_facts(pr_num: int, role: str, knowledge: dict, title: str) -> List[dict]:
    """Generate concise, impactful learned facts for Supabase learned_facts."""
    facts = []
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    if role == "coder":
        facts.append({
            "id": str(uuid.uuid4()),
            "content": f"[PR #{pr_num} Coder Solution]: {knowledge.get('why_this_way')} (Mechanism: {knowledge.get('fix_mechanism')[:200]})",
            "tags": ["pr_learning", "coder", f"pr_{pr_num}"],
            "created_at": now,
        })
        pitfalls = knowledge.get("pitfalls_to_avoid", [])
        if pitfalls:
            p_text = pitfalls[0] if isinstance(pitfalls[0], str) else str(pitfalls[0])
            facts.append({
                "id": str(uuid.uuid4()),
                "content": f"[PR #{pr_num} Pitfall Warning]: {p_text}",
                "tags": ["pitfall", "coder", f"pr_{pr_num}"],
                "created_at": now,
            })

    elif role == "auditor":
        facts.append({
            "id": str(uuid.uuid4()),
            "content": f"[PR #{pr_num} Audit Gate]: {knowledge.get('prevention_gate')} (Method: {knowledge.get('audit_methodology')[:200]})",
            "tags": ["audit_prevention", "auditor", f"pr_{pr_num}"],
            "created_at": now,
        })

    elif role == "ci-fixer":
        facts.append({
            "id": str(uuid.uuid4()),
            "content": f"[PR #{pr_num} CI Root Cause]: {knowledge.get('root_cause_analysis')} (Cross-platform: {knowledge.get('cross_platform_guarantee')[:200]})",
            "tags": ["ci_fix", "ci_root_cause", f"pr_{pr_num}"],
            "created_at": now,
        })

    elif role == "planner":
        facts.append({
            "id": str(uuid.uuid4()),
            "content": f"[PR #{pr_num} Architectural Reuse]: {knowledge.get('reused_components')} (Avoided: {knowledge.get('rejected_speculative_complexity')[:200]})",
            "tags": ["architecture", "reuse", f"pr_{pr_num}"],
            "created_at": now,
        })

    elif role == "human-eye":
        facts.append({
            "id": str(uuid.uuid4()),
            "content": f"[PR #{pr_num} System Learning]: {knowledge.get('permanent_system_learning')}",
            "tags": ["governance", "zero_admin", f"pr_{pr_num}"],
            "created_at": now,
        })

    elif role == "third-party":
        facts.append({
            "id": str(uuid.uuid4()),
            "content": f"[PR #{pr_num} MCP Resilience]: {knowledge.get('cold_start_resilience')} (Boundary: {knowledge.get('zero_credential_preservation')[:200]})",
            "tags": ["mcp", "resilience", f"pr_{pr_num}"],
            "created_at": now,
        })

    elif role == "ecosystem-scout":
        facts.append({
            "id": str(uuid.uuid4()),
            "content": f"[PR #{pr_num} Parity Finding]: {knowledge.get('board_parity_finding')} (Remedy: {knowledge.get('drift_detected_and_remedied')[:200]})",
            "tags": ["federation_parity", "scout", f"pr_{pr_num}"],
            "created_at": now,
        })

    return facts


def generate_embedding_gemini(text: str, gemini_key: str, dim: int = 768) -> Optional[List[float]]:
    """Generate dense vector embedding via Gemini API."""
    if not gemini_key:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={gemini_key}"
    payload = {
        "content": {"parts": [{"text": text[:8000]}]},
        "outputDimensionality": dim,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("embedding", {}).get("values")
    except Exception as err:
        print(f"::warning::Gemini embedding failed: {err}", file=sys.stderr)
        return None


def post_to_supabase(url: str, key: str, table: str, record: dict) -> bool:
    """Insert a record into Supabase PostgREST table."""
    endpoint = f"{url.rstrip('/')}/rest/v1/{urllib.parse.quote(table)}"
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(record).encode("utf-8"),
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return resp.status in (200, 201)
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")
        print(f"::warning::Supabase insert into {table} failed ({err.code}): {body[:300]}", file=sys.stderr)
        return False
    except Exception as err:
        print(f"::warning::Supabase connection error: {err}", file=sys.stderr)
        return False


def upsert_to_qdrant(url: str, key: str, collection: str, point: dict) -> bool:
    """Upsert vector point into Qdrant vector database."""
    endpoint = f"{url.rstrip('/')}/collections/{urllib.parse.quote(collection)}/points?wait=true"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["api-key"] = key
    payload = {"points": [point]}
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return resp.status == 200
    except Exception as err:
        print(f"::warning::Qdrant upsert failed: {err}", file=sys.stderr)
        return False


def run_ingest(
    pr_num: int,
    body: str,
    title: str = "",
    author: str = "agent",
    dry_run: bool = False,
) -> bool:
    """Main extraction and ingestion routine."""
    data, version = extract_envelope_json(body)
    if not data:
        print(f"::notice::PR #{pr_num} carried no knowledge envelope ({version}). Skipping ingestion.")
        return True

    is_valid, role, reason, knowledge = validate_knowledge(data, version)
    if not is_valid:
        print(f"::warning::PR #{pr_num} envelope invalid ({reason}). Ingestion skipped.")
        return False

    print(f"[OK] PR #{pr_num} validated as Role '{role}' ({version})")

    # 1. Prepare Supabase knowledge_base record
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    kb_record = {
        "id": str(uuid.uuid4()),
        "knowledge_key": f"pr-{pr_num}-{role}",
        "title": f"PR #{pr_num} [{role.upper()}]: {title or 'Agent Solution'}",
        "domain": role,
        "namespace": "pr-intelligence",
        "content": json.dumps(knowledge, indent=2),
        "source": f"PR #{pr_num}",
        "confidence": 1.0,
        "risk_level": "low",
        "status": "active",
        "metadata": {
            "pr_number": pr_num,
            "author": author,
            "role": role,
            "version": version,
            "ingested_at": now,
        },
        "updated_at": now,
    }

    # 2. Prepare Supabase learned_facts
    facts = format_learned_facts(pr_num, role, knowledge, title)

    # 3. Prepare Qdrant Vector Point
    semantic_summary = (
        f"PR #{pr_num} Role: {role}\nTitle: {title}\n"
        + "\n".join([f"{k}: {v}" for k, v in knowledge.items() if isinstance(v, (str, list))])
    )

    if dry_run:
        print("\n--- DRY RUN: knowledge_base record ---")
        print(json.dumps(kb_record, indent=2))
        print(f"\n--- DRY RUN: {len(facts)} learned_facts ---")
        for f in facts:
            print(f"- {f['content']}")
        print(f"\n--- DRY RUN: Semantic Summary ({len(semantic_summary)} chars) ---")
        print(semantic_summary[:300] + "...")
        return True

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_key = os.getenv("QDRANT_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    success = True
    if supabase_url and supabase_key:
        kb_ok = post_to_supabase(supabase_url, supabase_key, "knowledge_base", kb_record)
        print(f"Supabase knowledge_base: {'✓ Saved' if kb_ok else '✗ Failed'}")
        for fact in facts:
            f_ok = post_to_supabase(supabase_url, supabase_key, "learned_facts", fact)
            print(f"Supabase learned_facts ({fact['tags'][0]}): {'✓ Saved' if f_ok else '✗ Failed'}")
    else:
        print("::notice::Supabase credentials not set; skipping Supabase ingestion.")

    if qdrant_url and gemini_key:
        embedding = generate_embedding_gemini(semantic_summary, gemini_key, dim=768)
        if embedding:
            point = {
                "id": str(uuid.uuid4()),
                "vector": embedding,
                "payload": {
                    "pr_number": pr_num,
                    "role": role,
                    "title": title,
                    "summary": semantic_summary[:1200],
                    "timestamp": now,
                    "source": "pr_knowledge_envelope",
                },
            }
            q_ok = upsert_to_qdrant(qdrant_url, qdrant_key, "supremeai_memory", point)
            print(f"Qdrant supremeai_memory: {'✓ Upserted' if q_ok else '✗ Failed'}")
        else:
            print("::warning::Could not generate vector embedding; skipping Qdrant upsert.")
    else:
        print("::notice::Qdrant or Gemini credentials not set; skipping Qdrant upsert.")

    return success


def run_self_test() -> int:
    """Comprehensive offline self-test verifying all 7 role templates."""
    print("Running ingest_pr_knowledge self-tests...")

    for role in VALID_ROLES:
        sample_knowledge = {}
        for field_name in ROLE_REQUIRED_FIELDS[role]:
            if field_name == "alternatives_rejected":
                sample_knowledge[field_name] = [
                    {"method": "Alt 1", "why_rejected": "Too complex"},
                    {"method": "Alt 2", "why_rejected": "Performance cost"},
                ]
            elif field_name == "pitfalls_to_avoid":
                sample_knowledge[field_name] = ["Watch out for concurrency deadlock"]
            else:
                sample_knowledge[field_name] = f"Detailed explanation for {field_name} in {role}"

        envelope = {
            "schema": "pr-knowledge-envelope/2",
            "task_issue_ref": 100,
            "role": role,
            "knowledge": sample_knowledge,
        }
        body = f"Here is the PR description.\n\n{MARKER_OPEN_V2}\n{json.dumps(envelope, indent=2)}\n{MARKER_CLOSE_V2}\nEnd."

        ok = run_ingest(100, body, title=f"Test PR for {role}", dry_run=True)
        assert ok, f"Self-test failed for role: {role}"

    # Test v1 backward compatibility
    v1_body = (
        f"{MARKER_OPEN_V1}\n"
        + json.dumps({
            "schema": "pr-evidence-envelope/1",
            "task_issue_ref": 457,
            "claim_marker_id": "atomic-claim:123",
            "reflection_why": "Structured envelopes prevent text scraping failures",
            "alternatives_rejected": ["regex parsing", "external service"],
            "scope_paths": ["scripts/test.py"],
        })
        + f"\n{MARKER_CLOSE_V1}"
    )
    ok_v1 = run_ingest(457, v1_body, title="Test V1 PR", dry_run=True)
    assert ok_v1, "Self-test failed for v1 envelope fallback"

    print("PASS: All 7 role templates and v1 fallback self-tests passed!")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="PR Knowledge Ingestion Engine")
    parser.add_argument("--pr-num", type=int, help="PR number to fetch via gh CLI")
    parser.add_argument("--body-file", type=str, help="Path to file containing PR body text")
    parser.add_argument("--title", type=str, default="", help="PR title")
    parser.add_argument("--author", type=str, default="agent", help="PR author")
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate without database writes")
    parser.add_argument("--self-test", action="store_true", help="Run offline contract self-tests")

    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    if args.body_file:
        with open(args.body_file, "r", encoding="utf-8") as fh:
            body = fh.read()
        return 0 if run_ingest(args.pr_num or 0, body, title=args.title, author=args.author, dry_run=args.dry_run) else 1

    if args.pr_num:
        cmd = ["gh", "pr", "view", str(args.pr_num), "--json", "body,title,author"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            info = json.loads(res.stdout)
            body = info.get("body", "")
            title = args.title or info.get("title", "")
            author = args.author or info.get("author", {}).get("login", "unknown")
            return 0 if run_ingest(args.pr_num, body, title=title, author=author, dry_run=args.dry_run) else 1
        except Exception as err:
            print(f"::warning::Failed to fetch PR #{args.pr_num} via gh: {err}", file=sys.stderr)
            return 0  # Fail-soft: do not fail merge pipeline

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
