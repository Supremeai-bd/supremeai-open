#!/usr/bin/env python3
"""Report external-service calls that need resilience review.

This is intentionally report-only. It catches missing explicit timeouts at
common HTTP client construction/call sites and records a review queue for
retry/circuit-breaker policy rather than guessing whether a local abstraction
already provides those controls.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

DEFAULT_ROOTS = ("backend",)
EXCLUDED_PARTS = {"tests", "examples", "__pycache__", ".venv", "venv"}
HTTP_CALL_NAMES = {"get", "post", "put", "patch", "delete", "request", "send"}
HTTP_RECEIVER_HINTS = ("client", "http", "session", "request")
# SDK factories configure transport behavior outside the constructor call. They
# need policy review, but a timeout keyword cannot be passed to these APIs.
SDK_CLIENT_CONSTRUCTORS = {
    "supabase": {"create_client"},
    "google.cloud.firestore": {"Client"},
    "google.cloud.storage": {"Client"},
    "google.genai": {"Client"},
    "boto3": {"client"},
}


def iter_python_files(roots: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for root_name in roots:
        root = Path(root_name)
        if root.exists():
            files.extend(
                path
                for path in root.rglob("*.py")
                if not EXCLUDED_PARTS.intersection(path.parts)
            )
    return sorted(set(files))


def name_of(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def has_keyword(node: ast.Call, keyword: str) -> bool:
    return any(arg.arg == keyword for arg in node.keywords)


def audit_file(path: Path) -> list[dict[str, object]]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError) as exc:
        return [{"file": str(path), "line": 1, "kind": "parse_error", "severity": "high", "detail": str(exc)}]

    uses_shared_resilience = any(
        marker in source
        for marker in (
            "utils.http_client",
            "core.resilience",
            "core.retry_handler",
            "core.retry_budget",
        )
    )
    findings: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        called = name_of(node.func)
        if called in {"AsyncClient", "Client", "create_async_client", "create_client", "client"}:
            # The shared factory applies DEFAULT_TIMEOUT internally; do not
            # report its own implementation as an unbounded boundary.
            if called == "create_async_client" and path.name == "http_client.py":
                continue
            path_text = str(path).replace("\\", "/")
            sdk_markers = {
                "supabase": called == "create_client",
                "firestore": called == "Client",
                "storage": called == "Client",
                "genai": called == "Client",
                "boto3": called == "client",
                "firebase_admin": called == "client",
            }
            is_sdk_constructor = any(
                marker in source and matches for marker, matches in sdk_markers.items()
            )
            if called == "create_client" and "supabase" in source:
                is_sdk_constructor = True
            if called == "Client" and any(
                marker in source for marker in ("google.cloud.storage", "google.cloud.firestore", "google.genai")
            ):
                is_sdk_constructor = True
            if not has_keyword(node, "timeout") and not is_sdk_constructor:
                findings.append({
                    "file": str(path),
                    "line": node.lineno,
                    "kind": "missing_timeout",
                    "severity": "high",
                    "classification": "centralized_candidate" if not uses_shared_resilience else "explicit_review",
                    "call": called,
                })
            findings.append({
                "file": str(path),
                "line": node.lineno,
                "kind": "policy_review",
                "severity": "medium",
                "classification": "centralized_candidate" if not uses_shared_resilience else "explicit_review",
                "call": called,
                "detail": "Confirm bounded timeout, retry, circuit-breaker, and fallback behavior at this boundary.",
            })
        elif called in HTTP_CALL_NAMES and isinstance(node.func, ast.Attribute):
            receiver = name_of(node.func.value).lower()
            if any(hint in receiver for hint in HTTP_RECEIVER_HINTS):
                findings.append({
                    "file": str(path),
                    "line": node.lineno,
                    "kind": "policy_review",
                    "severity": "medium",
                    "classification": "centralized_candidate" if not uses_shared_resilience else "explicit_review",
                    "call": called,
                    "receiver": receiver,
                    "detail": "Confirm timeout is inherited and retry/circuit policy is bounded.",
                })
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="ci-reports/resilience-boundaries.json")
    parser.add_argument("roots", nargs="*", default=list(DEFAULT_ROOTS))
    args = parser.parse_args()
    findings = [finding for path in iter_python_files(tuple(args.roots)) for finding in audit_file(path)]
    report = {
        "status": "report-only",
        "roots": args.roots,
        "finding_count": len(findings),
        "missing_timeout_count": sum(item["kind"] == "missing_timeout" for item in findings),
        "high_severity_count": sum(item.get("severity") == "high" for item in findings),
        "centralized_candidate_count": sum(item.get("classification") == "centralized_candidate" for item in findings),
        "explicit_review_count": sum(item.get("classification") == "explicit_review" for item in findings),
        "findings": findings,
        "next_action": "Resolve high-severity missing timeouts first, then review centralized candidates before service-specific policy exceptions.",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Resilience boundary audit: {len(findings)} findings (report-only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
