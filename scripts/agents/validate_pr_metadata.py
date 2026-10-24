"""
scripts/agents/validate_pr_metadata.py
======================================
Issue #2158 — pre-create metadata assert for bot PR-creation wrappers.

Failure class (first observed on PR #2156): a wrapper intended
``--title "$(cat /tmp/wire_title.txt)"`` but passed the *path string* —
GitHub received ``/tmp/wire_title.txt`` as the PR title and body. Garbage
metadata poisons triage, labelers and the pr-verifier engine downstream,
and today's CI title check is warning-level, so it sails through.

This validator is the repo-visible half of the fix (the wrappers
themselves are per-agent sandbox tooling). Every bot wrapper SHOULD call
this before POSTing a pull request:

    python scripts/agents/validate_pr_metadata.py \\
        --title "$TITLE" --body "$BODY"

Blocks (exit 1):
  * title or body that *is* a filesystem path (the #2156 class)
  * title without the conventional ``type(scope): description`` form
    (AGENTS.md Rule #16)
  * empty / stub bodies

Warns (exit 0 unless ``--strict``):
  * title missing ``(#N)`` issue pointer (Rule #16 second half)
  * body not carrying exactly one keyword-prefixed issue ref
    (the Unified PR Gate contract: 0 refs => SG-01 BLOCK, >1 refs =>
    1-ISSUE-1-PR BLOCK)

CI-lane note (#2158 item 3): promoting the gate's warning-level title
check to blocking is a `.github/workflows` change and intentionally out
of scope here (coder-lane boundary).
"""

from __future__ import annotations

import argparse
import json
import re
import sys

__all__ = ["main", "validate"]

# Rule #16 first half: conventional prefix `type(scope): description` —
# scope is optional per the conventional-commits spec.
CONVENTIONAL_TITLE_RE = re.compile(r"^[a-zA-Z]+\([^)]*\): \S.*|^[a-zA-Z]+: \S.*")

# Rule #16 second half: a trailing `(#123)` pointer in the title.
TITLE_ISSUE_RE = re.compile(r"\(#(\d+)\)\s*$")

# Unified PR Gate contract: exactly ONE keyword-prefixed issue ref in the
# body (mirrors pr-gate.yml — plain `#N` mentions do not count).
KEYWORD_REF_RE = re.compile(
    r"\b(closes|closed|close|fixes|fixed|fix|resolves|resolved|resolve|refs|ref|see)\s+#\d+",
    re.IGNORECASE,
)

# Path-like metadata detection. A PR title/body should be prose; a bare
# filesystem path (absolute, dotted-relative, or extensioned with no
# whitespace) is virtually always the `$(cat ...)` missing-cat bug.
PATHLIKE_REASONS = (
    "starts with '/' (absolute path)",
    "starts with './' or '../' (relative path)",
    "matches a repo file path (no whitespace + known extension)",
)

_KNOWN_EXTENSIONS = (
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".py",
    ".sh",
    ".toml",
    ".cfg",
    ".ini",
    ".log",
    ".csv",
    ".html",
    ".js",
    ".ts",
    ".tsx",
)

MIN_BODY_CHARS = 40


def _pathlike_reason(value: str) -> str | None:
    """Return a reason string if the value looks like a file path, else None."""
    stripped = value.strip()
    if not stripped:
        return None
    if stripped.startswith("/"):
        return PATHLIKE_REASONS[0]
    if stripped.startswith(("./", "../")):
        return PATHLIKE_REASONS[1]
    # A single token with a known extension and no whitespace is a path in
    # practice (`/tmp/wire_body.md`, `docs/foo.md`); real titles/bodies have
    # spaces. Existence on disk is a bonus signal, not required.
    if (
        " " not in stripped
        and "\n" not in stripped
        and stripped.lower().endswith(_KNOWN_EXTENSIONS)
    ):
        return PATHLIKE_REASONS[2]
    return None


def validate(
    title: str, body: str, strict: bool = False
) -> tuple[list[str], list[str]]:
    """Validate PR metadata. Returns (errors, warnings).

    Errors are hard Rule #16 / #2158-class violations; warnings are gate
    contracts that today's CI enforces asynchronously (or at warning
    level). ``strict=True`` promotes every warning into an error so
    wrappers can opt into full enforcement.
    """
    errors: list[str] = []
    warnings: list[str] = []

    title = (title or "").strip()
    body = (body or "").strip()

    # --- #2156 failure class: paths as metadata -----------------------
    for field, value in (("title", title), ("body", body)):
        reason = _pathlike_reason(value)
        if reason:
            errors.append(
                f"{field} looks like a filesystem path ({reason}): '{value[:80]}' — "
                'pass the file\'s CONTENTS (e.g. --title "$(cat "$F")"), not its path'
            )
    if not title:
        errors.append("title is empty")
    if not body:
        errors.append("body is empty")
    elif len(body) < MIN_BODY_CHARS:
        errors.append(
            f"body is only {len(body)} chars (<{MIN_BODY_CHARS}) — "
            "Rule #17 requires a what/why/tested description"
        )

    # --- Rule #16: conventional title ---------------------------------
    if title and not CONVENTIONAL_TITLE_RE.match(title):
        errors.append(
            f"title '{title[:80]}' is not conventional `type(scope): description` "
            "(AGENTS.md Rule #16)"
        )
    if title and not TITLE_ISSUE_RE.search(title):
        warnings.append(
            "title has no trailing '(#N)' issue pointer (Rule #16 second half) — "
            "recommended: `type(scope): description (#N)`"
        )

    # --- Gate contract: exactly one keyword ref in body ----------------
    refs = KEYWORD_REF_RE.findall(body or "")
    if body and len(refs) == 0:
        warnings.append(
            "body has no keyword-prefixed issue ref (`Refs #N`) — the Unified PR Gate "
            "will BLOCK with issue_linked=false (SG-01)"
        )
    elif body and len(refs) > 1:
        warnings.append(
            f"body has {len(refs)} keyword-prefixed issue refs — the Unified PR Gate "
            "blocks on >1 (Rule 1-ISSUE-1-PR); keep exactly ONE"
        )

    if strict:
        errors.extend(warnings)
        warnings = []
    return errors, warnings


def main() -> int:
    p = argparse.ArgumentParser(
        description="Pre-create PR metadata assert for bot wrappers (issue #2158)"
    )
    p.add_argument("--title", required=True, help="PR title (contents, not a path)")
    p.add_argument("--body", required=True, help="PR body (contents, not a path)")
    p.add_argument(
        "--strict",
        action="store_true",
        help="promote warnings to hard failures (full enforcement)",
    )
    p.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format for wrapper consumption",
    )
    a = p.parse_args()

    errors, warnings = validate(a.title, a.body, strict=a.strict)

    if a.format == "json":
        print(
            json.dumps(
                {
                    "ok": not errors,
                    "errors": errors,
                    "warnings": warnings,
                }
            )
        )
    else:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        for w in warnings:
            print(f"WARNING: {w}", file=sys.stderr)
        if not errors and not warnings:
            print(
                "PR metadata OK (title conventional, body prose, gate contract satisfied)"
            )

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
