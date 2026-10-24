#!/usr/bin/env python3
"""Canonical Plan Governance Linter — docs/plans/ single source of truth tooling.

Implements the execution phases of
``docs/plans/CANONICAL_PLANNING_RECONCILIATION_AND_GUARDRAILS_PLAN.md``:

- Phase 1: repository-backed inventory (content + metadata analysis, not filenames)
- Phase 2: frontmatter scanner -> ``plan_registry.json`` (Decision 1: hybrid engine)
- Phase 5: archive-candidate extraction (cross-reference aware, non-destructive)
- Phase 6: automated guardrails (Decision 2 Stage 1: report-only by default)

Rollout contract (Decision 2): the default mode is **warn-only**. ``--check``
promotes findings to exit-code failures and is reserved for CI blocking mode
(Stage 2) after drift reaches a zero false-positive rate.

Usage:
    python scripts/governance/lint_plans.py                    # warn-only summary
    python scripts/governance/lint_plans.py --report out.md    # inventory report
    python scripts/governance/lint_plans.py --json out.json    # machine registry
    python scripts/governance/lint_plans.py --check            # blocking (Stage 2)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover — PyYAML ships with the backend env
    yaml = None  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PLANS_DIR = REPO_ROOT / "docs" / "plans"

# ── Canonical vocabulary (CANONICAL_…PLAN.md §3) ────────────────────────────
DOCUMENT_ROLES = {"architecture", "roadmap", "implementation", "policy", "audit"}
STATUSES = {"proposed", "active", "blocked", "complete", "superseded", "historical"}
EVIDENCE_STATES = {"verified", "partial", "unverified"}
DISPOSITIONS = {"retain", "merge", "archive", "redirect", "delete-approved"}
TARGET_SCOPES = {"supremeai_internal", "customer_facing", "combined_ecosystem"}

REQUIRED_FIELDS = ("id", "subject", "document_role", "planning_authority", "status", "target_scope")

# Legacy field aliases accepted from PLAN_LIFECYCLE_POLICY.md's older schema.
FIELD_ALIASES = {
    "owner_circle": "planning_authority",
    "owner": "planning_authority",
    "title": "subject",
}

# Naming-based versioning is banned (§2 posture #2): no `_v2`, `_final`,
# `_latest`, `_new`, `_v4.1`-style clones. Each file is a LIVING plan whose
# evolution lives inside an `evolution` section, not in a cloned filename.
VERSIONED_NAME_RE = re.compile(
    r"(_v\d+([._]\d+)*|[-_](final|latest|new|old|copy|backup|draft)\b|[-_]v\d+\b)",
    re.IGNORECASE,
)

# §5 unverified-claims ban — confident assertions without evidence markers.
CLAIM_PATTERNS = [
    re.compile(r"\ball\s+modes\s+operational\b", re.IGNORECASE),
    re.compile(r"\bzero\s+leaks\b", re.IGNORECASE),
    re.compile(r"\bproduction\s+deployed\b", re.IGNORECASE),
    re.compile(r"\bP50/P95\s+latency\s+achieved\b", re.IGNORECASE),
    re.compile(r"\b\d+\s*/\s*\d+\s+tests?\s+pass(ing)?\b", re.IGNORECASE),
    re.compile(r"\b\d{1,3}(?:\.\d+)?%\s+uptime\b", re.IGNORECASE),
    re.compile(r"\bis\s+fully\s+implemented\b", re.IGNORECASE),
    re.compile(r"\bnow\s+operational\b", re.IGNORECASE),
]
# Evidence markers that legitimize a measurable claim on the same line.
EVIDENCE_MARKERS = re.compile(
    r"(`[^`]+\.(py|ts|tsx|js|json|ya?ml|md|sh)`"  # backticked repo path
    r"|tests?[/#:][A-Za-z0-9_:.:-]+"
    r"|\bevidence\b"
    r"|\bpr\s*#\d+\b"
    r"|\bcommit\s+[0-9a-f]{7,}\b"
    r"|\bplanned\b|\btarget\b|\bgoal\b|\btodo\b)",
    re.IGNORECASE,
)

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "plan",
    "plans", "master", "roadmap", "guide", "blueprint", "system", "systems",
    "supremeai", "supreme", "ai", "bn", "bangla", "complete", "final", "new",
}

# High-conflict families (§7 Phase 1) — content-derived keyword maps.
FAMILY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "browser-automation": ("browser automation", "browser session", "browser center", "playwright", "cdp"),
    "free-tier-federation": ("free tier", "free-tier", "512mb", "federation", "zero cost", "zero-cost"),
    "dynamic-configuration": ("zero hardcode", "zero-hardcode", "dynamic configuration", "dynamic config", "runtime configuration", "provider abstraction"),
    "production-readiness": ("production readiness", "production hardening", "production upgrade", "release gate", "p1 p2", "hardening"),
    "control-tower-mcp": ("control tower", "mcp", "fastmcp", "multitenant hub", "gateway"),
    "intelligence-evolution": ("self evolution", "self-evolution", "self-learning", "autonomous intelligence", "living intelligence"),
    "memory-data-lifecycle": ("memory distillation", "memory engine", "knowledge acquisition", "data lifecycle", "retention"),
    "frontend-product-ux": ("frontend", "ui/ux", "dashboard design", "product ui", "chat interface"),
    "execution-phases": ("phase 1", "phase 2", "sprint", "milestone tracker", "release train"),
    "security-defense": ("anti-hacking", "antihacking", "security defense", "threat model", "hardening security"),
    "ci-cd-pipeline": ("ci pipeline", "ci/cd", "github actions", "build runtime"),
    "deployment-render": ("render deploy", "render.com", "ghcr", "deployment roadmap"),
    "unified-architecture": ("unified ecosystem", "master plan", "system architecture", "master blueprint", "crown jewel"),
}


class Finding:
    """A single governance finding on one plan document."""

    __slots__ = ("severity", "path", "code", "message")

    def __init__(self, severity: str, path: Path, code: str, message: str) -> None:
        self.severity = severity  # "error" | "warning" | "info"
        self.path = path
        self.code = code
        self.message = message

    def render(self, root: Path) -> str:
        try:
            rel = self.path.relative_to(root.parent)
        except ValueError:
            rel = self.path
        return f"[{self.severity.upper():7s}] {self.code:22s} {rel}: {self.message}"


class PlanDocument:
    """A scanned markdown plan document (frontmatter + body analysis)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.rel_path = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        self.frontmatter: dict = {}
        self.has_frontmatter = False
        self.fm_error: str | None = None
        self.title = ""
        self.headings: list[str] = []
        self.body_excerpt = ""
        self.line_count = 0
        self._scan()

    def _scan(self) -> None:
        try:
            raw = self.path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self.fm_error = f"unreadable: {exc}"
            return
        lines = raw.splitlines()
        self.line_count = len(lines)
        body_start = 0
        if lines and lines[0].strip() == "---":
            self.has_frontmatter = True
            end = None
            for idx in range(1, len(lines)):
                if lines[idx].strip() == "---":
                    end = idx
                    break
            if end is None:
                self.fm_error = "frontmatter opened with --- but never closed"
            elif yaml is None:
                self.fm_error = "PyYAML unavailable"
            else:
                try:
                    loaded = yaml.safe_load("\n".join(lines[1:end]))
                    self.frontmatter = loaded if isinstance(loaded, dict) else {}
                except yaml.YAMLError as exc:
                    self.fm_error = f"invalid YAML frontmatter: {str(exc)[:160]}"
            body_start = (end + 1) if end is not None else 0
        body = "\n".join(lines[body_start:])
        for line in lines[body_start:]:
            if line.startswith("# ") and not self.title:
                self.title = line[2:].strip()
            elif line.startswith("## "):
                self.headings.append(line[3:].strip())
        if not self.title and self.frontmatter:
            self.title = str(self.frontmatter.get("title", ""))
        # Subject signals: headings + first non-empty body lines (content-based,
        # per Phase 1 — never filename-based).
        excerpt_lines = [ln.strip() for ln in lines[body_start : body_start + 40] if ln.strip()]
        self.body_excerpt = " ".join(excerpt_lines)[:1500]

    # -- normalized metadata view ------------------------------------------
    @property
    def meta(self) -> dict:
        """Frontmatter with legacy aliases normalized to canonical names."""
        normalized: dict = {}
        for key, value in self.frontmatter.items():
            canonical_key = FIELD_ALIASES.get(str(key).strip().lower(), str(key).strip().lower())
            normalized.setdefault(canonical_key, value)
        return normalized

    @property
    def status(self) -> str:
        return str(self.meta.get("status", "")).strip().lower()

    @property
    def role(self) -> str:
        role = str(self.meta.get("document_role", "")).strip().lower()
        return role if role in DOCUMENT_ROLES else ""

    @property
    def authority(self) -> str:
        return str(self.meta.get("planning_authority", "")).strip()

    @property
    def disposition(self) -> str:
        return str(self.meta.get("disposition", "")).strip().lower()

    def supersedes(self) -> list[str]:
        value = self.meta.get("supersedes") or []
        if isinstance(value, str):
            return [value]
        return [str(v) for v in value if v]

    def superseded_by(self) -> list[str]:
        value = self.meta.get("superseded_by") or []
        if isinstance(value, str):
            return [value]
        return [str(v) for v in value if v]

    def text(self) -> str:
        return f"{self.title}\n{' '.join(self.headings)}\n{self.body_excerpt}".lower()


def detect_family(doc: PlanDocument) -> str:
    """Content-based family detection (title + headings + opening body)."""
    text = doc.text()
    best_family, best_hits = "unclassified", 0
    for family, keywords in FAMILY_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits > best_hits:
            best_family, best_hits = family, hits
    return best_family


def validate_document(doc: PlanDocument) -> list[Finding]:
    findings: list[Finding] = []

    # Naming-based versioning ban (§2 posture #2).
    if VERSIONED_NAME_RE.search(doc.path.stem):
        findings.append(
            Finding(
                "warning",
                doc.path,
                "versioned-filename",
                "filename uses banned versioning pattern (_v2/_final/_latest/…); "
                "changes belong in this living plan's evolution section",
            )
        )

    if not doc.has_frontmatter:
        findings.append(
            Finding(
                "warning",
                doc.path,
                "missing-frontmatter",
                "no YAML frontmatter — registry cannot classify this plan "
                f"(inferred family: {detect_family(doc)})",
            )
        )
        return findings

    if doc.fm_error:
        findings.append(Finding("error", doc.path, "invalid-frontmatter", doc.fm_error))
        return findings

    meta = doc.meta
    for field in REQUIRED_FIELDS:
        if not meta.get(field):
            findings.append(
                Finding("error", doc.path, "missing-field", f"required frontmatter field `{field}` is empty/missing")
            )

    status = meta.get("status", "")
    if status and str(status).strip().lower() not in STATUSES:
        findings.append(
            Finding(
                "error",
                doc.path,
                "invalid-status",
                f"status `{status}` not in canonical vocabulary {sorted(STATUSES)}",
            )
        )

    role = meta.get("document_role", "")
    if role and str(role).strip().lower() not in DOCUMENT_ROLES:
        findings.append(
            Finding(
                "error",
                doc.path,
                "invalid-role",
                f"document_role `{role}` not in {sorted(DOCUMENT_ROLES)}",
            )
        )

    evidence_state = meta.get("evidence_state", "")
    if evidence_state and str(evidence_state).strip().lower() not in EVIDENCE_STATES:
        findings.append(
            Finding("error", doc.path, "invalid-evidence-state", f"evidence_state `{evidence_state}` not in {sorted(EVIDENCE_STATES)}")
        )

    disposition = meta.get("disposition", "")
    if disposition and str(disposition).strip().lower() not in DISPOSITIONS:
        findings.append(
            Finding("error", doc.path, "invalid-disposition", f"disposition `{disposition}` not in {sorted(DISPOSITIONS)}")
        )

    target_scope = meta.get("target_scope", "")
    if target_scope and str(target_scope).strip().lower() not in TARGET_SCOPES:
        findings.append(
            Finding(
                "error",
                doc.path,
                "invalid-target-scope",
                f"target_scope `{target_scope}` not in {sorted(TARGET_SCOPES)}",
            )
        )

    last_verified = meta.get("last_verified")
    if last_verified:
        try:
            date.fromisoformat(str(last_verified)[:10])
        except ValueError:
            findings.append(
                Finding("error", doc.path, "invalid-date", f"last_verified `{last_verified}` is not YYYY-MM-DD")
            )

    canonical = meta.get("canonical")
    if canonical is not None and str(canonical).strip().lower() not in {"true", "false", "candidate"}:
        findings.append(
            Finding("error", doc.path, "invalid-canonical", f"canonical `{canonical}` must be true|false|candidate")
        )

    # Cross-link integrity: supersedes/superseded_by must point at real files.
    for link_field in ("supersedes", "superseded_by"):
        values = doc.supersedes() if link_field == "supersedes" else doc.superseded_by()
        for target in values:
            if not target:
                continue
            candidate = REPO_ROOT / str(target)
            if not candidate.exists():
                findings.append(
                    Finding("error", doc.path, "broken-lineage-link", f"{link_field} target does not exist: {target}")
                )

    # §5 unverified-claims ban (content scan, line-local evidence exemption).
    try:
        content = doc.path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        content = ""
    for line_no, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith(("#", ">", "|")) or len(stripped) > 400:
            # headings/quotes/tables: skip to keep false positives near zero
            continue
        for pattern in CLAIM_PATTERNS:
            match = pattern.search(stripped)
            if not match:
                continue
            before = stripped[match.start() - 2 : match.start()]
            after = stripped[match.end() : match.end() + 2]
            if '"' in before or '"' in after or '*"' in before or '"*' in after:
                # quoted mention (ban-list example, citation) — not an assertion
                continue
            if not EVIDENCE_MARKERS.search(stripped):
                findings.append(
                    Finding(
                        "warning",
                        doc.path,
                        "unverified-claim",
                        f"L{line_no}: confident claim without evidence marker — "
                        f"`{stripped[:110]}`",
                    )
                )
            break  # one warning per line is enough

    return findings


def _title_tokens(doc: PlanDocument) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (doc.title or doc.path.stem).lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


def competing_plans(docs: list[PlanDocument]) -> list[list[PlanDocument]]:
    """Same family + role + authority + overlapping subject + no lineage link.

    §1 definition of duplicate: same subject, same document_role, same
    planning authority, competing files. Only ``status: active`` documents
    compete (single-active-execution discipline); ``proposed`` candidates
    are queued, not competing.
    """
    groups: dict[tuple[str, str, str], list[PlanDocument]] = defaultdict(list)
    for doc in docs:
        family = detect_family(doc)
        if family == "unclassified" or not doc.has_frontmatter or doc.fm_error:
            continue
        if doc.status != "active":
            continue
        role = doc.role or "unmarked"
        authority = doc.authority.lower() or "unmarked"
        groups[(family, role, authority)].append(doc)

    competing: list[list[PlanDocument]] = []
    for (_family, _role, _authority), members in groups.items():
        if len(members) < 2:
            continue
        linked = {t for d in members for t in d.supersedes() + d.superseded_by()}
        unlinked = [
            m
            for m in members
            if not any(t and (t in m.rel_path or m.rel_path in t) for t in linked)
        ]
        # Subject-overlap gate: titles must share at least one distinctive
        # token, else the family match is keyword coincidence.
        overlapping: list[PlanDocument] = []
        for m in unlinked:
            tokens = _title_tokens(m)
            if any(tokens & _title_tokens(other) for other in unlinked if other is not m):
                overlapping.append(m)
        if len(overlapping) >= 2:
            competing.append(overlapping)
    return competing


def _jsonable(value):
    """YAML dates/bools arrive as rich objects; coerce for the JSON cache."""
    if isinstance(value, (date,)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return str(value)


def build_registry(docs: list[PlanDocument]) -> dict:
    """Decision 1: machine-readable cache generated from frontmatter sources."""
    entries = []
    for doc in docs:
        meta = _jsonable(doc.meta)
        entries.append(
            {
                "id": meta.get("id") or f"auto:{Path(doc.rel_path).stem}",
                "subject": meta.get("subject") or doc.title or Path(doc.rel_path).stem,
                "document_role": doc.role or None,
                "planning_authority": doc.authority or None,
                "canonical": meta.get("canonical"),
                "status": doc.status or None,
                "source_file": doc.rel_path,
                "supersedes": doc.supersedes(),
                "superseded_by": doc.superseded_by(),
                "evidence_state": meta.get("evidence_state"),
                "last_verified": meta.get("last_verified"),
                "disposition": doc.disposition or None,
                "target_scope": meta.get("target_scope"),
                "family": detect_family(doc),
                "frontmatter_present": doc.has_frontmatter and not doc.fm_error,
                "lines": doc.line_count,
            }
        )
    families = Counter(entry["family"] for entry in entries)
    return {
        "generated_at": date.today().isoformat(),
        "generator": "scripts/governance/lint_plans.py",
        "source_of_truth": "per-document YAML frontmatter",
        "totals": {
            "documents": len(docs),
            "with_frontmatter": sum(1 for d in docs if d.has_frontmatter and not d.fm_error),
            "families": dict(sorted(families.items(), key=lambda kv: -kv[1])),
        },
        "documents": sorted(entries, key=lambda e: e["source_file"]),
    }


def render_report(docs: list[PlanDocument], findings: list[Finding], competing: list[list[PlanDocument]]) -> str:
    """Phase 1 inventory report (markdown, human view of the registry)."""
    registry = build_registry(docs)
    lines = [
        "# docs/plans/ Inventory & Governance Report",
        "",
        f"> Generated: {registry['generated_at']} by `{registry['generator']}` (report-only mode)  ",
        "> Machine cache: `docs/plans/plan_registry.json` · Source of truth: per-file YAML frontmatter",
        "",
        "## Totals",
        "",
        f"- Documents scanned: **{registry['totals']['documents']}**",
        f"- With valid frontmatter: **{registry['totals']['with_frontmatter']}**",
        f"- Findings: **{sum(1 for f in findings if f.severity == 'error')} errors / "
        f"{sum(1 for f in findings if f.severity == 'warning')} warnings**",
        "",
        "## Family distribution (content-derived)",
        "",
        "| Family | Documents |",
        "|---|---|",
    ]
    for family, count in registry["totals"]["families"].items():
        lines.append(f"| {family} | {count} |")

    lines += ["", "## Competing plan sets (same subject + role, unlinked)", ""]
    if competing:
        for group in competing:
            names = ", ".join(f"`{m.rel_path}`" for m in group)
            lines.append(f"- {names}")
    else:
        lines.append("- None detected among frontmatter-classified documents.")

    lines += ["", "## Findings", ""]
    by_code: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        by_code[f.code].append(f)
    for code, items in sorted(by_code.items()):
        lines.append(f"### `{code}` ({len(items)})")
        lines.append("")
        for item in items[:25]:
            lines.append(f"- {item.render(REPO_ROOT)}")
        if len(items) > 25:
            lines.append(f"- …and {len(items) - 25} more")
        lines.append("")

    return "\n".join(lines) + "\n"


def render_readme_catalog(docs: list[PlanDocument]) -> str:
    """Phase 4: status-based catalog rendered from the registry data."""
    groups: dict[str, list[PlanDocument]] = defaultdict(list)
    for doc in docs:
        if not doc.has_frontmatter or doc.fm_error:
            continue
        groups[doc.status or "unmarked"].append(doc)

    order = ["active", "proposed", "blocked", "complete", "superseded", "historical", "unmarked"]
    lines = ["<!-- BEGIN GENERATED PLAN CATALOG (scripts/governance/lint_plans.py --readme; do not hand-edit between markers) -->", ""]
    for status in order:
        members = groups.get(status, [])
        if not members:
            continue
        label = {"active": "🟢 ACTIVE", "proposed": "🟡 PROPOSED (queued candidates — not executable)", "blocked": "⛔ BLOCKED", "complete": "✅ COMPLETE", "superseded": "↪️ SUPERSEDED", "historical": "🗂️ HISTORICAL", "unmarked": "• FRONTMATTER-CLASSIFIED (no status)"}.get(status, status)
        lines.append(f"### {label} ({len(members)})")
        lines.append("")
        lines.append("| Plan | Role | Authority | Scope | Family |")
        lines.append("|---|---|---|---|---|")
        for m in sorted(members, key=lambda d: d.rel_path):
            title = (m.meta.get("subject") or m.title or m.path.stem).replace("|", "\\|")
            family = detect_family(m)
            scope = m.meta.get("target_scope") or "—"
            lines.append(
                f"| [`{m.path.stem}`](./{m.path.relative_to(REPO_ROOT / 'docs' / 'plans')}) | {m.role or '—'} | {m.authority or '—'} | {scope} | {family} |"
            )
        lines.append("")
    lines.append("<!-- END GENERATED PLAN CATALOG -->")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="docs/plans/ governance linter & registry generator")
    parser.add_argument("--root", type=Path, default=DEFAULT_PLANS_DIR, help="plans directory to scan")
    parser.add_argument("--check", action="store_true", help="exit 1 when errors exist (Stage-2 blocking mode)")
    parser.add_argument("--json", type=Path, help="write machine registry JSON here")
    parser.add_argument("--report", type=Path, help="write markdown inventory report here")
    parser.add_argument("--readme", action="store_true", help="print generated status-based catalog (Phase 4) to stdout")
    args = parser.parse_args(argv)

    if yaml is None:  # pragma: no cover
        print("PyYAML is required", file=sys.stderr)
        return 2

    docs = [PlanDocument(p) for p in sorted(args.root.rglob("*.md"))]
    findings: list[Finding] = []
    for doc in docs:
        findings.extend(validate_document(doc))
    competing = competing_plans(docs)

    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]

    print(f"Scanned {len(docs)} documents under {args.root}")
    print(f"  errors:   {len(errors)}")
    print(f"  warnings: {len(warnings)}")
    print(f"  competing plan sets: {len(competing)}")
    for finding in errors[:10]:
        print(" ", finding.render(args.root))
    if warnings:
        print("  first warnings:")
        for finding in warnings[:5]:
            print(" ", finding.render(args.root))

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(build_registry(docs), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"registry written: {args.json}")
    if args.readme:
        sys.stdout.write(render_readme_catalog(docs))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(render_report(docs, findings, competing), encoding="utf-8")
        print(f"report written: {args.report}")

    if args.check and errors:
        print(f"CHECK FAILED: {len(errors)} error-level findings", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
