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
from typing import Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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


def extract_markdown_reflection(body: str) -> Optional[dict]:
    """Parse standard PR Markdown '## Reflection Evidence (why + alternatives_rejected)'.

    Transforms standard GitHub PR reflection sections into structured v2 knowledge data
    so all landed PRs automatically populate memory without requiring raw HTML comment tags.
    """
    if not body:
        return None

    lower_body = body.lower()
    if "reflection evidence" not in lower_body and "why + alternatives_rejected" not in lower_body:
        return None

    # 1. Extract 'why'
    why_match = re.search(
        r"(?:-\s*)?\*\*why:\*\*\s*(.+?)(?=(?:-\s*)?\*\*alternatives_rejected:\*\*|##|\Z)",
        body,
        re.DOTALL | re.IGNORECASE,
    )
    why_text = why_match.group(1).strip() if why_match else ""
    why_text = re.sub(r"\s+", " ", why_text).strip()

    # 2. Extract 'alternatives_rejected'
    alts_match = re.search(
        r"(?:-\s*)?\*\*alternatives_rejected:\*\*\s*(.+?)(?=(?:##|\Z))",
        body,
        re.DOTALL | re.IGNORECASE,
    )
    alts_raw = alts_match.group(1).strip() if alts_match else ""

    alts_list = []
    if alts_raw:
        for line in alts_raw.splitlines():
            line_str = line.strip()
            if not line_str or line_str.startswith("<!--"):
                continue
            cleaned = re.sub(r"^[-*]\s*", "", line_str).strip()
            if not cleaned or "replace:" in cleaned.lower():
                continue
            if ":" in cleaned:
                method, reason = cleaned.split(":", 1)
                alts_list.append({"method": method.strip(" *`_"), "why_rejected": reason.strip()})
            elif "rejected because" in cleaned.lower():
                parts = re.split(r"rejected because", cleaned, flags=re.IGNORECASE)
                alts_list.append({"method": parts[0].strip(" *`_"), "why_rejected": parts[1].strip()})
            else:
                alts_list.append({"method": cleaned.strip(" *`_"), "why_rejected": "Rejected during PR evaluation"})

    if not alts_list:
        alts_list = [{"method": "Ad-hoc workaround or speculative code expansion", "why_rejected": "Violates minimal elegance and fail-closed contract rules"}]

    # 3. Extract Summary / Title if present
    summary_match = re.search(r"##\s*Summary\s*(.+?)(?=(?:##|\Z))", body, re.DOTALL | re.IGNORECASE)
    summary_text = summary_match.group(1).strip() if summary_match else ""
    summary_text = re.sub(r"\s+", " ", summary_text).strip()

    if not why_text and not summary_text:
        return None

    fix_mechanism = summary_text or why_text or "Automated reflection extraction from merged PR"
    if not why_text:
        why_text = summary_text

    return {
        "schema": "pr-knowledge-envelope/2",
        "role": "coder",
        "knowledge": {
            "fix_mechanism": fix_mechanism,
            "why_this_way": why_text,
            "alternatives_rejected": alts_list,
            "pitfalls_to_avoid": ["Ensure backward compatibility and zero performance regressions"],
        },
    }


def extract_envelope_json(body: str) -> Tuple[Optional[dict], str]:
    """Extract and parse v2 envelope, v1 envelope, or markdown reflection."""
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

    # 3. Try Markdown Reflection Parsing Fallback
    md_envelope = extract_markdown_reflection(body)
    if md_envelope:
        return md_envelope, "v2"

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


def read_text_safe(path: str) -> str:
    """Read text file with auto-detection of UTF-16 and UTF-8 encoding."""
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    elif raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", errors="replace")
    return raw.decode("utf-8", errors="replace")


def parse_touched_files_from_diff(diff_text: str) -> List[str]:
    """Extract distinct modified file paths from a unified git diff."""
    if not diff_text:
        return []
    matches = re.findall(r"^diff --git a/(.+?) b/", diff_text, flags=re.MULTILINE)
    seen = set()
    result = []
    for path in matches:
        p = path.strip()
        if p and p not in seen:
            seen.add(p)
            result.append(p)
    return result


def fetch_pr_diff(pr_num: int) -> Tuple[str, List[str]]:
    """Fetch PR unified diff and touched files list using local cache or gh CLI fallback."""
    if pr_num <= 0:
        return "", []

    diff_text = ""
    touched_files: List[str] = []

    # 1. Local archive cache (e.g. F:/pr diff/pr_<num>.diff)
    for archive_dir in ["F:/pr diff", "F:\\pr diff", os.path.expanduser("~/.cache/pr_diffs")]:
        candidate = os.path.join(archive_dir, f"pr_{pr_num}.diff")
        if os.path.isfile(candidate):
            try:
                diff_text = read_text_safe(candidate)
                if diff_text:
                    touched_files = parse_touched_files_from_diff(diff_text)
                    return diff_text, touched_files
            except Exception:
                pass

    # 2. Try gh pr diff
    try:
        res = subprocess.run(
            ["gh", "pr", "diff", str(pr_num)],
            capture_output=True,
            timeout=25,
            check=False,
        )
        if res.returncode == 0 and res.stdout:
            diff_text = res.stdout.decode("utf-8", errors="replace")
            touched_files = parse_touched_files_from_diff(diff_text)
    except Exception as err:
        print(f"::notice::gh pr diff #{pr_num} unavailable ({err})", file=sys.stderr)

    # 3. Fallback: local git diff if on merge commit referencing this PR
    if not diff_text:
        try:
            head_msg_res = subprocess.run(
                ["git", "log", "-1", "--pretty=%B"],
                capture_output=True,
                timeout=10,
                check=False,
            )
            head_msg = head_msg_res.stdout.decode("utf-8", errors="replace")
            if f"#{pr_num}" in head_msg:
                git_diff_res = subprocess.run(
                    ["git", "diff", "HEAD~1..HEAD"],
                    capture_output=True,
                    timeout=20,
                    check=False,
                )
                if git_diff_res.returncode == 0 and git_diff_res.stdout:
                    diff_text = git_diff_res.stdout.decode("utf-8", errors="replace")
                    touched_files = parse_touched_files_from_diff(diff_text)
        except Exception:
            pass

    # 4. Save to local archive if folder exists
    if diff_text:
        for archive_dir in ["F:/pr diff", "F:\\pr diff"]:
            if os.path.isdir(archive_dir):
                target_file = os.path.join(archive_dir, f"pr_{pr_num}.diff")
                if not os.path.isfile(target_file):
                    try:
                        with open(target_file, "w", encoding="utf-8", errors="replace") as out_f:
                            out_f.write(diff_text)
                    except Exception:
                        pass

    return diff_text, touched_files


def run_query_file(file_path: str) -> int:
    """Find past PRs and commits that modified a file."""
    print(f"=== Searching PR history for file: {file_path} ===")
    clean_path = file_path.replace("\\", "/").strip()

    # 1. Check local git log
    try:
        res = subprocess.run(
            ["git", "log", "-n", "10", "--oneline", "--", clean_path],
            capture_output=True,
            timeout=10,
            check=False,
        )
        if res.returncode == 0 and res.stdout:
            print("\nRecent git commits touching this file:")
            print(res.stdout.decode("utf-8", errors="replace").strip())
    except Exception as err:
        print(f"git log check error: {err}")

    # 2. Check local F:/pr diff archive if present
    for archive_dir in ["F:/pr diff", "F:\\pr diff"]:
        if os.path.isdir(archive_dir):
            print(f"\nChecking local diff archive ({archive_dir})...")
            matches = []
            target_name = os.path.basename(clean_path)
            for entry in os.scandir(archive_dir):
                if entry.name.endswith(".diff"):
                    try:
                        with open(entry.path, "r", encoding="utf-8", errors="replace") as fh:
                            content = fh.read(64000)
                            if clean_path in content or target_name in content:
                                matches.append(entry.name.replace(".diff", ""))
                    except Exception:
                        continue
            if matches:
                print(f"Found {len(matches)} matching PR diffs in local archive: {', '.join(matches[:15])}")
            else:
                print("No direct matches in local diff archive header scan.")
            break

    # 3. Check Supabase knowledge_base if env is set
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if supabase_url and supabase_key:
        print("\nQuerying Supabase knowledge_base...")
        try:
            query_url = f"{supabase_url.rstrip('/')}/rest/v1/knowledge_base?select=id,title,domain,metadata&limit=10"
            req = urllib.request.Request(
                query_url,
                headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                records = json.loads(resp.read().decode("utf-8"))
                found = 0
                for rec in records:
                    meta = rec.get("metadata", {})
                    files = meta.get("touched_files", [])
                    if any(clean_path in f for f in files):
                        found += 1
                        print(f"- {rec.get('title')} (PR #{meta.get('pr_number')})")
                if found == 0:
                    print("No indexed PRs in Supabase matching this exact path yet.")
        except Exception as err:
            print(f"Supabase query error: {err}")

    return 0


def run_query_pr(pr_num: int) -> int:
    """Inspect stored knowledge and diff snippet for a PR."""
    print(f"=== Inspecting PR #{pr_num} ===")
    diff_text, touched_files = fetch_pr_diff(pr_num)
    print(f"Touched files ({len(touched_files)}):")
    for f in touched_files[:20]:
        print(f"  - {f}")
    if len(touched_files) > 20:
        print(f"  ... and {len(touched_files) - 20} more files")

    print(f"\nDiff size: {len(diff_text.encode('utf-8'))} bytes")
    if diff_text:
        print("\n--- Diff Snippet (first 1000 chars) ---")
        print(diff_text[:1000])
    return 0


def run_ingest(
    pr_num: int,
    body: str,
    title: str = "",
    author: str = "agent",
    dry_run: bool = False,
    touched_files: Optional[List[str]] = None,
    diff_text: Optional[str] = None,
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

    # Fetch PR diff and touched files if not provided
    if pr_num > 0 and diff_text is None:
        diff_text, files_from_diff = fetch_pr_diff(pr_num)
        if not touched_files:
            touched_files = files_from_diff

    if not touched_files and diff_text:
        touched_files = parse_touched_files_from_diff(diff_text)

    diff_snippet = diff_text[:5000] if diff_text else ""
    diff_size_bytes = len(diff_text.encode("utf-8")) if diff_text else 0

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
            "touched_files": touched_files or [],
            "files_count": len(touched_files or []),
            "diff_snippet": diff_snippet,
            "diff_size_bytes": diff_size_bytes,
        },
        "updated_at": now,
    }

    # 2. Prepare Supabase learned_facts
    facts = format_learned_facts(pr_num, role, knowledge, title)

    # 3. Prepare Qdrant Vector Point
    files_str = f"\nTouched files: {', '.join(touched_files[:10])}" if touched_files else ""
    semantic_summary = (
        f"PR #{pr_num} Role: {role}\nTitle: {title}{files_str}\n"
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
                    "touched_files": (touched_files or [])[:20],
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
    parser.add_argument("--query-file", type=str, help="Search PR knowledge base / local cache for past PRs touching a file")
    parser.add_argument("--query-pr", type=int, help="Inspect stored diff and knowledge for a specific PR")

    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    if args.query_file:
        return run_query_file(args.query_file)

    if args.query_pr:
        return run_query_pr(args.query_pr)

    if args.body_file:
        with open(args.body_file, "r", encoding="utf-8") as fh:
            body = fh.read()
        return 0 if run_ingest(args.pr_num or 0, body, title=args.title, author=args.author, dry_run=args.dry_run) else 1

    if args.pr_num:
        cmd = ["gh", "pr", "view", str(args.pr_num), "--json", "body,title,author,files"]
        try:
            res = subprocess.run(cmd, capture_output=True, check=True)
            info = json.loads(res.stdout.decode("utf-8", errors="replace"))
            body = info.get("body", "")
            title = args.title or info.get("title", "")
            author = args.author or info.get("author", {}).get("login", "unknown")
            files_info = info.get("files", [])
            touched_files = [f["path"] for f in files_info if "path" in f] if files_info else None
            return 0 if run_ingest(
                args.pr_num,
                body,
                title=title,
                author=author,
                dry_run=args.dry_run,
                touched_files=touched_files,
            ) else 1
        except Exception as err:
            print(f"::warning::Failed to fetch PR #{args.pr_num} via gh: {err}", file=sys.stderr)
            return 0  # Fail-soft: do not fail merge pipeline

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
