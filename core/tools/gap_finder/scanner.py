from __future__ import annotations

import ast
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .config import (
    AUTH_SECURITY_HINTS,
    DANGEROUS_EXEC_PATTERNS,
    DEFAULT_IGNORES,
    DOC_HINTS,
    PROJECT_MANIFESTS,
    PROTECTED_HINTS,
    SECRET_PATTERNS,
    SMELL_PATTERNS,
    TEST_HINTS,
    TEXT_EXTENSIONS,
)
from .helpers import (
    add_finding,
    is_text_candidate,
    iter_files,
    looks_like_generated,
    read_text,
    relpath,
    severity_rank,
)
from .models import AuditReport, AuditStats, Finding

# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class GapScanner:
    def __init__(
        self,
        root: Path,
        *,
        ignores: set[str] | None = None,
        max_files: int = 20_000,
        profile: str = "universal",
        focus: set[str] | None = None,
    ) -> None:
        self.root = root.resolve()
        self.ignores = ignores or set(DEFAULT_IGNORES)
        self.max_files = max_files
        self.profile = profile
        self.focus = focus or set()
        self.findings: list[Finding] = []
        self.stats = AuditStats()
        self.files: list[Path] = []
        self.text_cache: dict[Path, str] = {}
        self.python_asts: dict[Path, ast.AST] = {}

    def enabled(self, category: str) -> bool:
        return not self.focus or category in self.focus

    def _language_from_suffix(self, path: Path) -> str | None:
        mapping = {
            ".py": "python", ".js": "javascript", ".jsx": "javascript",
            ".ts": "typescript", ".tsx": "typescript", ".dart": "dart",
            ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin",
            ".kts": "kotlin", ".rb": "ruby", ".php": "php", ".swift": "swift",
            ".c": "c", ".cc": "cpp", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
            ".cs": "csharp", ".sh": "shell", ".ps1": "powershell",
            ".yaml": "yaml", ".yml": "yaml", ".json": "json", ".toml": "toml",
            ".md": "markdown", ".sql": "sql",
        }
        return mapping.get(path.suffix.lower())

    def scan(self) -> AuditReport:
        started = time.perf_counter()

        self.files = iter_files(self.root, self.ignores, self.max_files)

        for path in self.files:
            self.stats.files_scanned += 1

            if path.suffix.lower():
                lang = self._language_from_suffix(path)
                if lang:
                    self.stats.languages[lang] = self.stats.languages.get(lang, 0) + 1

            if is_text_candidate(path):
                text = read_text(path)
                if text is not None:
                    self.text_cache[path] = text
                    self.stats.text_files_scanned += 1
                    self.stats.total_lines += text.count("\n") + (1 if text else 0)
                    self._scan_text_file(path, text)

            if path.suffix == ".py":
                self.stats.python_files_scanned += 1
                self._scan_python(path)

        self._scan_project_structure()
        self._scan_manifests()
        self._scan_tests()
        self._scan_ci_cd()
        self._scan_docs_drift()
        self._scan_architecture_signals()
        self._scan_autonomy_governance()
        self._scan_dependency_hygiene()
        self._scan_dead_code_and_duplicates()
        self._scan_operational_resilience()

        self.findings.sort(
            key=lambda f: (
                severity_rank(f.severity),
                -f.confidence,
                f.category,
                f.path or "",
                f.line or 0,
            )
        )

        self._populate_stats()

        duration = time.perf_counter() - started
        signals = self._build_signals()
        recommendations = self._build_recommendations()

        return AuditReport(
            tool="SupremeAI Universal Gap Finder",
            version="1.0.0",
            root=str(self.root),
            generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            duration_seconds=round(duration, 3),
            profile=self.profile,
            stats=self.stats,
            findings=self.findings,
            signals=signals,
            recommendations=recommendations,
        )

    # -------------------------
    # Primitive scanners
    # -------------------------

    def _scan_text_file(self, path: Path, text: str) -> None:
        rel = relpath(self.root, path)
        lines = text.splitlines()

        # Secrets
        if self.enabled("security"):
            for idx, line in enumerate(lines, 1):
                if any(p.search(line) for p in SECRET_PATTERNS):
                    # Reduce obvious false positives in examples.
                    low = line.lower()
                    if "example" in low or "placeholder" in low or "<your-" in low:
                        continue
                    add_finding(
                        self.findings,
                        rule_id="SEC-001",
                        category="security",
                        severity="CRITICAL",
                        confidence=0.92,
                        title="Potential hardcoded secret",
                        message="A credential-like value appears directly in source.",
                        path=rel,
                        line=idx,
                        evidence=[line[:300]],
                        impact="Credential leakage can become account compromise, data theft, or infrastructure takeover.",
                        remediation="Move the secret to a secret manager/environment variable and rotate the exposed credential.",
                        verification="Run secret scanning and verify the value is absent from Git history and runtime source.",
                    )

        # Dangerous execution
        if self.enabled("security"):
            for idx, line in enumerate(lines, 1):
                for pattern in DANGEROUS_EXEC_PATTERNS:
                    if pattern.search(line):
                        add_finding(
                            self.findings,
                            rule_id="SEC-002",
                            category="security",
                            severity="HIGH",
                            confidence=0.85,
                            title="Potential unsafe command execution",
                            message="Dynamic or shell-backed process execution was detected.",
                            path=rel,
                            line=idx,
                            evidence=[line[:300]],
                            impact="If inputs are attacker-controlled or AI-generated, this can become command injection or sandbox escape.",
                            remediation="Prefer argv-based execution, strict allowlists, sandboxing, timeouts, resource limits, and input validation.",
                            verification="Add negative tests for command injection, shell metacharacters, path traversal, and unexpected executables.",
                        )
                        break

        # TODO/FIXME/HACK/stubs
        if self.enabled("maintainability"):
            for tag, pattern, subtype in SMELL_PATTERNS:
                for match in pattern.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    sev = "MEDIUM" if tag != "PASS_STUB" else "LOW"
                    add_finding(
                        self.findings,
                        rule_id=f"DEBT-{tag}",
                        category="maintainability",
                        severity=sev,
                        confidence=0.82,
                        title=f"Maintenance signal: {tag}",
                        message=f"Potential {subtype} or unresolved maintenance marker detected.",
                        path=rel,
                        line=line,
                        evidence=[lines[line - 1][:300] if line <= len(lines) else tag],
                        impact="Unresolved maintenance debt can become hidden functional risk and reduce change safety.",
                        remediation="Convert the marker into a tracked issue, implement it, or document why it is intentionally retained.",
                        verification="Re-run this scanner and confirm the marker is removed or explicitly allowlisted.",
                    )

        # Weak fail-open hints
        if self.enabled("security") and re.search(r"(?i)fail[-_ ]open", text):
            add_finding(
                self.findings,
                rule_id="SEC-003",
                category="security",
                severity="HIGH",
                confidence=0.89,
                title="Fail-open behavior present",
                message="The code/documentation explicitly references fail-open behavior.",
                path=rel,
                impact="Security and consistency controls can silently disappear during dependency or infrastructure failure.",
                remediation="For auth, tenant isolation, billing, idempotency, sandboxing and security policy, prefer fail-closed behavior.",
                verification="Simulate dependency failure and verify protected operations return denial/503 rather than proceed.",
            )

        # Disabled checks
        if self.enabled("ci"):
            disabled_markers = ("if: false", "enabled: false", "skip_security", "skip_tests")
            for idx, line in enumerate(lines, 1):
                if any(marker in line.lower() for marker in disabled_markers):
                    add_finding(
                        self.findings,
                        rule_id="CI-001",
                        category="ci",
                        severity="MEDIUM",
                        confidence=0.72,
                        title="Potentially disabled verification path",
                        message="A test/build/security path appears explicitly disabled.",
                        path=rel,
                        line=idx,
                        evidence=[line[:300]],
                        impact="Dead CI paths create false confidence and configuration drift.",
                        remediation="Remove obsolete disabled jobs or document and isolate them from required gates.",
                        verification="Compare active CI coverage to intended release gates.",
                    )

    def _scan_python(self, path: Path) -> None:
        rel = relpath(self.root, path)
        text = self.text_cache.get(path)
        if text is None:
            text = read_text(path)
        if not text:
            return

        try:
            tree = ast.parse(text, filename=str(path))
            self.python_asts[path] = tree
        except SyntaxError as exc:
            add_finding(
                self.findings,
                rule_id="PY-001",
                category="correctness",
                severity="CRITICAL",
                confidence=1.0,
                title="Python syntax error",
                message=f"Python parser rejected the file: {exc.msg}",
                path=rel,
                line=exc.lineno,
                evidence=[exc.text.strip() if exc.text else ""],
                impact="The file cannot execute or import successfully.",
                remediation="Fix the syntax error and add syntax/import checks to CI.",
                verification="python -m py_compile <file> and the relevant test suite.",
            )
            return

        # Complexity heuristic
        branch_nodes = sum(
            isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With,
                               ast.AsyncWith, ast.Match, ast.IfExp, ast.BoolOp))
            for node in ast.walk(tree)
        )
        if branch_nodes >= 80:
            add_finding(
                self.findings,
                rule_id="ARCH-001",
                category="architecture",
                severity="HIGH",
                confidence=0.88,
                title="Very high local control-flow complexity",
                message=f"AST contains approximately {branch_nodes} control-flow constructs.",
                path=rel,
                impact="High complexity increases defect probability and makes safe AI-assisted modification harder.",
                remediation="Split orchestration, policy, I/O and domain logic into smaller functions/classes with explicit contracts.",
                verification="Track cyclomatic complexity and require tests around extracted seams.",
            )
        elif branch_nodes >= 40:
            add_finding(
                self.findings,
                rule_id="ARCH-002",
                category="architecture",
                severity="MEDIUM",
                confidence=0.80,
                title="High local control-flow complexity",
                message=f"AST contains approximately {branch_nodes} control-flow constructs.",
                path=rel,
                impact="Dense logic is harder to test and evolve safely.",
                remediation="Refactor repeated branches and isolate decision policies.",
                verification="Review function complexity and add focused tests.",
            )

        # Long functions
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = getattr(node, "end_lineno", node.lineno)
                length = end - node.lineno + 1
                if length >= 220:
                    add_finding(
                        self.findings,
                        rule_id="ARCH-003",
                        category="maintainability",
                        severity="HIGH",
                        confidence=0.96,
                        title="Very large function",
                        message=f"Function '{node.name}' is approximately {length} lines.",
                        path=rel,
                        line=node.lineno,
                        impact="Large functions become high-risk change surfaces and are difficult to reason about automatically.",
                        remediation="Split the function by responsibilities and introduce tested interfaces.",
                        verification="Measure function size after refactor and preserve behavior with regression tests.",
                    )
                elif length >= 120:
                    add_finding(
                        self.findings,
                        rule_id="ARCH-004",
                        category="maintainability",
                        severity="MEDIUM",
                        confidence=0.91,
                        title="Large function",
                        message=f"Function '{node.name}' is approximately {length} lines.",
                        path=rel,
                        line=node.lineno,
                        impact="Long procedures increase hidden coupling and regression risk.",
                        remediation="Extract cohesive subroutines and side-effect boundaries.",
                        verification="Run unit tests for extracted responsibilities.",
                    )

        # Broad exception swallowing
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    line = node.lineno
                    add_finding(
                        self.findings,
                        rule_id="PY-002",
                        category="correctness",
                        severity="HIGH",
                        confidence=0.93,
                        title="Bare except handler",
                        message="A bare 'except:' can intercept unexpected exceptions.",
                        path=rel,
                        line=line,
                        impact="Unexpected failures may be silently transformed into incorrect behavior.",
                        remediation="Catch specific exception types and preserve cancellation/system exceptions.",
                        verification="Add tests for expected errors and unexpected propagation.",
                    )

        # Mutable/global singleton signals
        singleton_count = len(re.findall(r"(?m)^\s*_[A-Za-z0-9_]+\s*=\s*None\s*$", text))
        if singleton_count >= 4:
            add_finding(
                self.findings,
                rule_id="ARCH-005",
                category="architecture",
                severity="MEDIUM",
                confidence=0.70,
                title="Many module-level singleton placeholders",
                message=f"Detected {singleton_count} module-level None-backed singleton patterns.",
                path=rel,
                impact="Implicit global state increases test interference and lifecycle ambiguity.",
                remediation="Use explicit dependency injection or narrowly scoped factories.",
                verification="Run tests in random order and parallel mode.",
            )

        # Imports from sensitive and evolution components
        if self.enabled("security") and "evolution" in rel.lower():
            joined = "\n".join(
                alias.name if isinstance(alias, ast.alias) else ""
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            )
            joined += "\n" + "\n".join(
                node.module or ""
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
            )
            if any(token in joined for token in ("security", "dependencies", "billing", "tenant_db", "config")):
                add_finding(
                    self.findings,
                    rule_id="GOV-001",
                    category="security",
                    severity="HIGH",
                    confidence=0.86,
                    title="Evolution code imports protected-domain components",
                    message="An evolution-related module appears coupled directly to security/auth/config/tenant/billing internals.",
                    path=rel,
                    impact="Coupling increases the chance that autonomous evolution can cross governance boundaries.",
                    remediation="Depend on immutable policy interfaces, not protected implementation modules.",
                    verification="Build an import-graph rule that blocks protected dependencies from evolution packages.",
                )

    # -------------------------
    # Project-level scanners
    # -------------------------

    def _scan_project_structure(self) -> None:
        names = {p.name.lower() for p in self.files}
        root_dirs = {
            p.name.lower()
            for p in self.root.iterdir()
            if p.is_dir()
        }

        if self.enabled("architecture"):
            if "archive" in root_dirs or "_archive" in root_dirs:
                add_finding(
                    self.findings,
                    rule_id="ARCH-006",
                    category="architecture",
                    severity="LOW",
                    confidence=0.65,
                    title="Archive/legacy tree exists",
                    message="The repository contains an active-looking archive directory.",
                    impact="Legacy code can remain accidentally importable or confuse agents and maintainers.",
                    remediation="Move historical artifacts outside the executable tree or explicitly exclude them from tooling.",
                    verification="Run import/path scans and confirm archived modules cannot be loaded accidentally.",
                )

        if self.enabled("security"):
            env_examples = [p for p in self.files if p.name == ".env.example"]
            secrets_files = [
                p for p in self.files
                if any(token in p.name.lower() for token in ("secret", "credentials", "service-account"))
            ]
            if env_examples and secrets_files:
                add_finding(
                    self.findings,
                    rule_id="SEC-004",
                    category="security",
                    severity="MEDIUM",
                    confidence=0.76,
                    title="Secret-like files exist in repository tree",
                    message="Files with names associated with credentials/secrets are present and should be verified.",
                    evidence=[relpath(self.root, p) for p in secrets_files[:10]],
                    impact="Even non-secret examples or generated credentials can be accidentally committed or packaged.",
                    remediation="Ensure secret artifacts are excluded, documented, and stored only in a secret manager.",
                    verification="Run gitleaks/secret scanning and inspect repository history.",
                )

        if self.enabled("testing"):
            test_dirs = [p for p in self.root.rglob("*") if p.is_dir() and p.name.lower() in TEST_HINTS]
            source_dirs = [p for p in self.root.iterdir() if p.is_dir() and p.name not in self.ignores]
            if source_dirs and not test_dirs:
                add_finding(
                    self.findings,
                    rule_id="TEST-001",
                    category="testing",
                    severity="HIGH",
                    confidence=0.90,
                    title="No obvious test tree detected",
                    message="The repository has source directories but no obvious test directory.",
                    impact="Critical regressions may reach production without automated detection.",
                    remediation="Create tests around core business rules, authentication, data boundaries, external integrations and failure modes.",
                    verification="Add a required CI test gate.",
                )

        if self.enabled("docs"):
            if "readme.md" not in names:
                add_finding(
                    self.findings,
                    rule_id="DOC-001",
                    category="docs",
                    severity="MEDIUM",
                    confidence=0.98,
                    title="README missing",
                    message="No root README.md was detected.",
                    impact="New developers and AI agents lack an obvious canonical entry point.",
                    remediation="Create a concise root README with architecture, setup, test and deployment truth.",
                    verification="Require README validation in project checks.",
                )

    def _scan_manifests(self) -> None:
        manifest_map: dict[str, str] = {}
        for p in self.root.iterdir():
            if p.name in PROJECT_MANIFESTS:
                manifest_map[p.name] = PROJECT_MANIFESTS[p.name]

        # Also look one level down for monorepos.
        for p in self.files:
            if p.name in PROJECT_MANIFESTS:
                manifest_map[relpath(self.root, p)] = PROJECT_MANIFESTS[p.name]

        self.stats.manifests = manifest_map

        if len(set(manifest_map.values())) >= 3:
            add_finding(
                self.findings,
                rule_id="ARCH-007",
                category="architecture",
                severity="MEDIUM",
                confidence=0.86,
                title="Polyglot/monorepo complexity detected",
                message=f"Multiple ecosystems/manifests detected: {sorted(set(manifest_map.values()))}.",
                impact="Toolchains, dependency graphs and CI environments become harder to keep consistent.",
                remediation="Document the intentional boundaries and establish per-app ownership/build contracts.",
                verification="Ensure each app has isolated dependency/build/test commands.",
            )

        # Python dependency drift
        pyproject = self.root / "backend" / "pyproject.toml"
        if not pyproject.exists():
            pyproject = self.root / "pyproject.toml"
        if pyproject.exists() and (self.root / "backend" / "poetry.lock").exists():
            text = read_text(pyproject) or ""
            if "python-jose" in text and "PyJWT" in text:
                add_finding(
                    self.findings,
                    rule_id="DEP-001",
                    category="dependencies",
                    severity="HIGH",
                    confidence=0.91,
                    title="Legacy JWT dependency and replacement coexist",
                    message="Dependency configuration appears to reference both python-jose and PyJWT.",
                    path=relpath(self.root, pyproject),
                    impact="Mixed JWT libraries create inconsistent security behavior and migration drift.",
                    remediation="Complete the migration to one supported JWT library and regenerate the lockfile.",
                    verification="Search all imports for 'jose' and require zero remaining runtime imports.",
                )

    def _scan_tests(self) -> None:
        test_files = [
            p for p in self.files
            if p.suffix in {".py", ".ts", ".tsx", ".js", ".dart"}
            and any(token in p.as_posix().lower() for token in TEST_HINTS)
        ]
        prod_files = [
            p for p in self.files
            if p.suffix in {".py", ".ts", ".tsx", ".js", ".dart"}
            and not any(token in p.as_posix().lower() for token in TEST_HINTS)
            and not looks_like_generated(p)
        ]

        if not prod_files:
            return

        ratio = len(test_files) / max(1, len(prod_files))

        if self.enabled("testing") and ratio < 0.05:
            add_finding(
                self.findings,
                rule_id="TEST-002",
                category="testing",
                severity="CRITICAL",
                confidence=0.82,
                title="Very low test-to-source ratio",
                message=f"Detected {len(test_files)} test files vs {len(prod_files)} production-like source files.",
                impact="The repository has a large behavioral surface with little automated protection.",
                remediation="Prioritize tests by risk: auth, tenant isolation, billing, execution, provider routing, persistence, webhooks and state transitions.",
                verification="Track coverage and critical-path test counts as separate release metrics.",
            )
        elif ratio < 0.15:
            add_finding(
                self.findings,
                rule_id="TEST-003",
                category="testing",
                severity="HIGH",
                confidence=0.78,
                title="Low test-to-source ratio",
                message=f"Detected {len(test_files)} test files vs {len(prod_files)} production-like source files.",
                impact="Many production behaviors may be untested.",
                remediation="Add targeted contract, integration and negative-path tests.",
                verification="Set minimum critical-path coverage requirements.",
            )

        # Look for tests that only assert basic import/true.
        suspicious = 0
        for p in test_files[:5000]:
            text = self.text_cache.get(p) or read_text(p) or ""
            if re.search(r"assert\s+True\s*$", text, re.MULTILINE) or re.search(r"assert\s+\w+ is not None\s*$", text):
                suspicious += 1
        if suspicious >= 5:
            add_finding(
                self.findings,
                rule_id="TEST-004",
                category="testing",
                severity="MEDIUM",
                confidence=0.74,
                title="Potentially weak assertions",
                message=f"Found {suspicious} tests containing trivially weak assertion patterns.",
                impact="High test counts can still provide low behavioral confidence.",
                remediation="Replace existence-only assertions with state, boundary, error and invariant assertions.",
                verification="Mutation testing or targeted fault injection should fail these tests when behavior is broken.",
            )

    def _scan_ci_cd(self) -> None:
        workflow_files = [
            p for p in self.files
            if ".github/workflows" in p.as_posix().replace("\\", "/")
            and p.suffix in {".yml", ".yaml"}
        ]

        if not workflow_files:
            if self.enabled("ci"):
                add_finding(
                    self.findings,
                    rule_id="CI-002",
                    category="ci",
                    severity="MEDIUM",
                    confidence=0.95,
                    title="No GitHub Actions workflow detected",
                    message="No GitHub Actions workflow was found.",
                    impact="Projects may lack automated validation and deployment safeguards.",
                    remediation="If GitHub Actions is the intended CI platform, add a minimal required quality gate.",
                    verification="Create a PR and confirm required checks block known-bad changes.",
                )
            return

        if len(workflow_files) >= 10:
            add_finding(
                self.findings,
                rule_id="CI-003",
                category="ci",
                severity="HIGH",
                confidence=0.90,
                title="High workflow count / CI fragmentation",
                message=f"{len(workflow_files)} GitHub Actions workflow files were detected.",
                evidence=[relpath(self.root, p) for p in workflow_files[:20]],
                impact="Duplicated and overlapping workflows increase cost, failure surface and maintenance burden.",
                remediation="Consolidate by lifecycle: PR CI, deploy, release, scheduled maintenance, disaster recovery.",
                verification="Map each workflow to one unique purpose and remove duplicate jobs.",
            )

        text = "\n".join(self.text_cache.get(p) or read_text(p) or "" for p in workflow_files)
        if "if: false" in text.lower():
            add_finding(
                self.findings,
                rule_id="CI-004",
                category="ci",
                severity="MEDIUM",
                confidence=0.86,
                title="Disabled CI steps exist",
                message="At least one workflow step/job appears permanently disabled.",
                impact="The repository may contain dead verification or obsolete deployment paths.",
                remediation="Delete obsolete steps or isolate them into explicitly manual workflows.",
                verification="Rebuild the intended required-check graph and test it with a failing commit.",
            )

        # Detect workflow sprawl with repeated task keywords.
        keyword_counts = {
            key: len(re.findall(key, text, flags=re.IGNORECASE))
            for key in (
                "pytest", "npm run build", "pnpm", "ruff", "black", "gitleaks",
                "codeql", "deploy", "render", "firebase", "vercel",
            )
        }
        if keyword_counts["pytest"] > 6 or keyword_counts["deploy"] > 8:
            add_finding(
                self.findings,
                rule_id="CI-005",
                category="ci",
                severity="MEDIUM",
                confidence=0.78,
                title="Likely duplicated CI responsibilities",
                message="Common CI commands appear across many workflows.",
                evidence=[f"{k}={v}" for k, v in keyword_counts.items() if v > 3],
                impact="The same quality or deployment action may be running in multiple places.",
                remediation="Extract shared logic into reusable workflows/actions and keep one canonical gate.",
                verification="Produce a workflow-to-purpose matrix and check each action has one owner.",
            )

    def _scan_docs_drift(self) -> None:
        docs = [
            p for p in self.files
            if p.suffix.lower() == ".md" and not looks_like_generated(p)
        ]
        {
            relpath(self.root, p)
            for p in self.files
            if p.suffix in {".py", ".ts", ".tsx", ".js", ".dart", ".go", ".rs"}
        }

        stale_dates = 0
        future_dates = 0
        for p in docs:
            text = self.text_cache.get(p) or read_text(p) or ""
            years = [int(y) for y in re.findall(r"\b(20\d{2})[-/]\d{2}[-/]\d{2}\b", text)]
            if years:
                stale_dates += sum(y <= 2024 for y in years)
                future_dates += sum(y >= 2030 for y in years)

        if stale_dates >= 3:
            add_finding(
                self.findings,
                rule_id="DOC-002",
                category="docs",
                severity="MEDIUM",
                confidence=0.78,
                title="Documentation appears stale",
                message=f"Found {stale_dates} date references from 2024 or earlier.",
                impact="AI agents and developers may trust obsolete deployment, auth or architecture claims.",
                remediation="Tag docs as current/historical or refresh them from current source-of-truth files.",
                verification="Run doc/source consistency checks during scheduled maintenance.",
            )

        if future_dates:
            add_finding(
                self.findings,
                rule_id="DOC-003",
                category="docs",
                severity="LOW",
                confidence=0.90,
                title="Suspicious future dates in documentation",
                message=f"Found {future_dates} date references in 2030 or later.",
                impact="May indicate templating, generated-data or versioning problems.",
                remediation="Verify whether the dates are intentional.",
                verification="Review the affected documents.",
            )

        # File references that look local but don't exist.
        for p in docs[:2000]:
            text = self.text_cache.get(p) or read_text(p) or ""
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
                if target.startswith(("http://", "https://", "mailto:", "#", "file://")):
                    continue
                target_path = (p.parent / target.split("#", 1)[0]).resolve()
                if not target_path.exists() and target.strip():
                    add_finding(
                        self.findings,
                        rule_id="DOC-004",
                        category="docs",
                        severity="LOW",
                        confidence=0.86,
                        title="Broken local documentation link",
                        message=f"Markdown link points to a missing path: {target}",
                        path=relpath(self.root, p),
                        impact="Broken docs links reduce onboarding and make architecture knowledge unreliable.",
                        remediation="Update or remove the broken reference.",
                        verification="Run a markdown link checker in CI.",
                    )

    def _scan_architecture_signals(self) -> None:
        # Duplicate conceptual subsystems.
        groups = {
            "error": ["error_bus", "error_handler", "error_pattern", "error_remediation"],
            "router": ["router", "routing"],
            "cache": ["cache", "redis"],
            "config": ["config", "settings", "configuration"],
            "memory": ["memory", "knowledge", "experience"],
            "queue": ["queue", "pubsub", "nats", "event_bus"],
            "auth": ["auth", "jwt", "rbac", "token"],
        }

        path_text = "\n".join(relpath(self.root, p).lower() for p in self.files)
        for group, words in groups.items():
            matches = [w for w in words if w in path_text]
            if len(matches) >= 4:
                add_finding(
                    self.findings,
                    rule_id=f"ARCH-COLL-{group.upper()}",
                    category="architecture",
                    severity="MEDIUM",
                    confidence=0.68,
                    title=f"Potential {group} subsystem duplication",
                    message=f"Repository paths suggest multiple overlapping {group}-related abstractions.",
                    evidence=sorted(matches),
                    impact="Multiple abstractions for the same concern can cause split-brain behavior and inconsistent policy.",
                    remediation="Define one canonical interface and migrate older paths behind compatibility shims.",
                    verification="Search imports and call sites to verify there is one actual source of truth.",
                )

        # Nested backend trees
        if (self.root / "backend" / "backend").exists():
            add_finding(
                self.findings,
                rule_id="ARCH-008",
                category="architecture",
                severity="HIGH",
                confidence=0.98,
                title="Nested backend/backend tree detected",
                message="A backend/backend directory exists.",
                impact="Nested application roots commonly create import ambiguity and duplicate packages.",
                remediation="Flatten or explicitly define the packaging/import root.",
                verification="Run import tests from a clean environment and inspect sys.path.",
            )

        # Multiple theme/config systems in Flutter
        theme_candidates = [
            relpath(self.root, p)
            for p in self.files
            if p.suffix == ".dart" and re.search(r"/theme/.*(theme|token|color)", p.as_posix(), re.IGNORECASE)
        ]
        if len(theme_candidates) >= 4:
            add_finding(
                self.findings,
                rule_id="ARCH-009",
                category="architecture",
                severity="MEDIUM",
                confidence=0.76,
                title="Multiple UI theme/token implementations",
                message="Several theme/token/color files suggest potentially duplicated design-system layers.",
                evidence=theme_candidates[:12],
                impact="Visual consistency and maintenance become harder when multiple theme systems coexist.",
                remediation="Choose one canonical token/theme source and expose compatibility adapters temporarily.",
                verification="Trace imports and remove unused theme paths.",
            )

    def _scan_autonomy_governance(self) -> None:
        evolution_files = [
            p for p in self.files
            if re.search(r"(evolution|self[_-]?improv|auto[_-]?skill|autonomous|self[_-]?healing)",
                         p.as_posix(), re.IGNORECASE)
        ]

        if not evolution_files:
            return

        protected_files = [
            p for p in self.files
            if any(hint in relpath(self.root, p).lower().replace("\\", "/") for hint in PROTECTED_HINTS)
        ]

        if protected_files:
            add_finding(
                self.findings,
                rule_id="GOV-002",
                category="security",
                severity="HIGH",
                confidence=0.88,
                title="Autonomy and protected-domain code coexist",
                message="The project contains autonomous/evolution code alongside protected auth/security/billing/config/tenant surfaces.",
                evidence=[relpath(self.root, p) for p in evolution_files[:12]]
                        + [relpath(self.root, p) for p in protected_files[:12]],
                impact="Without explicit governance boundaries, self-modifying systems can cross critical trust boundaries.",
                remediation="Implement centralized allowlist-first target validation, immutable protected paths, multi-stage revalidation and mandatory audit events.",
                verification="Add negative tests for path traversal and protected-target proposals.",
            )

        # Look for governance terms but no obvious policy file.
        policy_candidates = [
            p for p in self.files
            if re.search(r"(governance|policy|protected|allowlist|denylist)", p.name, re.IGNORECASE)
        ]
        if not policy_candidates:
            add_finding(
                self.findings,
                rule_id="GOV-003",
                category="security",
                severity="HIGH",
                confidence=0.91,
                title="No obvious autonomous-change policy file",
                message="Autonomous/evolution code exists without a clearly named governance policy artifact.",
                impact="Governance rules may be scattered and bypassable.",
                remediation="Create one canonical immutable governance policy module and enforce it at generation, proposal, benchmark and promotion stages.",
                verification="Search all evolution code paths and ensure they call the policy API.",
            )

    def _scan_dependency_hygiene(self) -> None:
        # Detect duplicate package families across lock/manifest contents.
        if not self.enabled("dependencies"):
            return

        files = [
            p for p in self.files
            if p.name in {
                "pyproject.toml", "requirements.txt", "package.json",
                "pubspec.yaml", "Cargo.toml",
            }
        ]
        text = "\n".join(self.text_cache.get(p) or read_text(p) or "" for p in files)

        suspicious_pairs = [
            (("requests", "httpx", "aiohttp"), "multiple HTTP clients"),
            (("redis", "valkey", "nats", "celery", "rq"), "multiple queue/cache transports"),
            (("sqlite", "postgres", "supabase", "firestore", "mongodb"), "multiple persistence technologies"),
        ]
        for tokens, label in suspicious_pairs:
            found = [t for t in tokens if re.search(rf"\b{re.escape(t)}\b", text, re.IGNORECASE)]
            if len(found) >= 3:
                add_finding(
                    self.findings,
                    rule_id="DEP-002",
                    category="dependencies",
                    severity="MEDIUM",
                    confidence=0.73,
                    title=f"Potentially excessive dependency variants: {label}",
                    message=f"Detected {found}.",
                    evidence=found,
                    impact="More infrastructure libraries increase attack surface, configuration burden and runtime complexity.",
                    remediation="Keep multiple implementations only when their roles are explicit and justified.",
                    verification="Document one canonical library per concern or remove unused alternatives.",
                )

    def _scan_dead_code_and_duplicates(self) -> None:
        if not self.enabled("maintainability"):
            return

        # Same basename in multiple locations.
        by_name: dict[str, list[Path]] = defaultdict(list)
        for p in self.files:
            if p.suffix in {".py", ".ts", ".tsx", ".js", ".dart", ".yaml", ".yml"}:
                by_name[p.name.lower()].append(p)

        for name, paths in by_name.items():
            if len(paths) >= 3 and not looks_like_generated(paths[0]):
                add_finding(
                    self.findings,
                    rule_id="DEAD-001",
                    category="maintainability",
                    severity="LOW",
                    confidence=0.60,
                    title="Repeated filename across repository",
                    message=f"'{name}' exists in {len(paths)} locations.",
                    evidence=[relpath(self.root, p) for p in paths[:10]],
                    impact="Repeated names can hide duplicate implementations and make AI navigation unreliable.",
                    remediation="Confirm ownership and rename/move obsolete or compatibility files.",
                    verification="Search imports and references before deletion.",
                )

        # Very small Python files that look like redirect shims.
        for p in self.files:
            if p.suffix != ".py":
                continue
            text = self.text_cache.get(p) or read_text(p) or ""
            non_comment = [
                line for line in text.splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]
            if 1 <= len(non_comment) <= 6 and any(x in text for x in ("deprecated", "redirect", "importlib", "__getattr__")):
                add_finding(
                    self.findings,
                    rule_id="DEAD-002",
                    category="maintainability",
                    severity="LOW",
                    confidence=0.80,
                    title="Compatibility/deprecation shim detected",
                    message="This file appears to be a compatibility bridge rather than a canonical implementation.",
                    path=relpath(self.root, p),
                    impact="Large numbers of shims can preserve old architecture indefinitely.",
                    remediation="Track shim owners and remove them after migration completion.",
                    verification="Search for imports of the shim and require zero remaining consumers before deletion.",
                )

    def _scan_operational_resilience(self) -> None:
        # Health/observability signals
        health_terms = ("health", "readiness", "liveness")
        observability_terms = ("prometheus", "otel", "opentelemetry", "metrics", "tracing")
        path_text = "\n".join(relpath(self.root, p).lower() for p in self.files)
        all_text = "\n".join(self.text_cache.values())

        if self.enabled("operations") and not any(t in path_text for t in health_terms):
            add_finding(
                self.findings,
                rule_id="OPS-001",
                category="operations",
                severity="MEDIUM",
                confidence=0.72,
                title="No obvious health/readiness component",
                message="No health/readiness-related path was detected.",
                impact="Deployment systems may have weak visibility into startup or dependency health.",
                remediation="Expose lightweight liveness and readiness checks separately.",
                verification="Test behavior during DB/Redis/LLM dependency failure.",
            )

        if self.enabled("operations") and not any(t in all_text.lower() for t in observability_terms):
            add_finding(
                self.findings,
                rule_id="OPS-002",
                category="operations",
                severity="MEDIUM",
                confidence=0.72,
                title="Weak observability signals detected",
                message="No strong evidence of standardized metrics/tracing tooling was found.",
                impact="Production failures can become difficult to diagnose and correlate.",
                remediation="Standardize request IDs, structured logs, metrics and traces.",
                verification="Perform a synthetic request and confirm the trace is visible end-to-end.",
            )

        # Disaster recovery signals
        if self.enabled("operations"):
            dr_terms = ("backup", "restore", "disaster", "recovery")
            if not any(t in path_text for t in dr_terms):
                add_finding(
                    self.findings,
                    rule_id="OPS-003",
                    category="operations",
                    severity="HIGH",
                    confidence=0.74,
                    title="No obvious disaster-recovery implementation",
                    message="No backup/restore/disaster-recovery path was detected.",
                    impact="A data loss or infrastructure failure may become unrecoverable.",
                    remediation="Define backups, restore procedures, RPO/RTO and at least one automated drill.",
                    verification="Perform a restore drill from a real backup artifact.",
                )

    # -------------------------
    # Report intelligence
    # -------------------------

    def _populate_stats(self) -> None:
        counts = Counter(f.severity for f in self.findings)
        self.stats.findings = len(self.findings)
        self.stats.critical = counts.get("CRITICAL", 0)
        self.stats.high = counts.get("HIGH", 0)
        self.stats.medium = counts.get("MEDIUM", 0)
        self.stats.low = counts.get("LOW", 0)
        self.stats.info = counts.get("INFO", 0)

    def _build_signals(self) -> dict[str, Any]:
        categories = Counter(f.category for f in self.findings)
        paths = Counter(f.path for f in self.findings if f.path)
        top_files = [
            {"path": p, "findings": n}
            for p, n in paths.most_common(15)
        ]

        risk_score = (
            self.stats.critical * 12
            + self.stats.high * 7
            + self.stats.medium * 3
            + self.stats.low * 1
        )

        if risk_score >= 100:
            risk_band = "CRITICAL"
        elif risk_score >= 50:
            risk_band = "HIGH"
        elif risk_score >= 20:
            risk_band = "MEDIUM"
        else:
            risk_band = "LOW"

        return {
            "risk_score": risk_score,
            "risk_band": risk_band,
            "category_counts": dict(categories),
            "top_problem_files": top_files,
            "architecture_pressure": self._architecture_pressure(),
            "test_pressure": self._test_pressure(),
            "governance_pressure": self._governance_pressure(),
        }

    def _architecture_pressure(self) -> str:
        arch = sum(1 for f in self.findings if f.category == "architecture")
        maintain = sum(1 for f in self.findings if f.category == "maintainability")
        if arch + maintain >= 20:
            return "VERY_HIGH"
        if arch + maintain >= 10:
            return "HIGH"
        if arch + maintain >= 5:
            return "MEDIUM"
        return "LOW"

    def _test_pressure(self) -> str:
        testing = sum(1 for f in self.findings if f.category == "testing")
        if testing >= 5:
            return "HIGH"
        if testing >= 2:
            return "MEDIUM"
        return "LOW"

    def _governance_pressure(self) -> str:
        gov = sum(1 for f in self.findings if f.rule_id.startswith("GOV-"))
        return "HIGH" if gov >= 2 else "MEDIUM" if gov else "LOW"

    def _build_recommendations(self) -> list[str]:
        recs: list[str] = []

        if self.stats.critical:
            recs.append("Fix CRITICAL findings before feature work or autonomous evolution.")
        if any(f.rule_id.startswith("GOV-") for f in self.findings):
            recs.append("Centralize self-modification policy and enforce it at generation, proposal, benchmark and promotion boundaries.")
        if any(f.rule_id.startswith("TEST-") for f in self.findings):
            recs.append("Prioritize high-risk behavioral tests instead of maximizing raw test count.")
        if any(f.rule_id.startswith("CI-") for f in self.findings):
            recs.append("Reduce CI fragmentation and make one canonical required quality gate.")
        if any(f.rule_id.startswith("DEP-") for f in self.findings):
            recs.append("Remove overlapping dependency families and complete in-progress migrations.")
        if any(f.rule_id.startswith("SEC-") for f in self.findings):
            recs.append("Treat auth, tenant isolation, billing, secrets and execution boundaries as fail-closed trust zones.")
        if any(f.rule_id.startswith("DOC-") for f in self.findings):
            recs.append("Create a machine-checkable source of truth for architecture and deployment topology.")
        if not recs:
            recs.append("No dominant gap cluster detected; use baseline mode to detect newly introduced drift over time.")

        return recs


# ---------------------------------------------------------------------------
# Baseline / comparison
# ---------------------------------------------------------------------------

def load_baseline(path: Path) -> set[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            item.get("fingerprint")
            for item in data.get("findings", [])
            if item.get("fingerprint")
        }
    except Exception:
        return set()


def report_to_markdown(report: AuditReport, baseline: set[str] | None = None) -> str:
    baseline = baseline or set()
    lines: list[str] = []

    lines.append("# SupremeAI Universal Gap Report")
    lines.append("")
    lines.append(f"- Root: `{report.root}`")
    lines.append(f"- Generated: `{report.generated_at}`")
    lines.append(f"- Duration: `{report.duration_seconds}s`")
    lines.append(f"- Profile: `{report.profile}`")
    lines.append("")
    lines.append("## Risk Summary")
    lines.append("")
    lines.append(f"- Risk band: **{report.signals['risk_band']}**")
    lines.append(f"- Risk score: **{report.signals['risk_score']}**")
    lines.append(f"- Findings: **{report.stats.findings}**")
    lines.append(
        f"- Critical/High/Medium/Low: "
        f"**{report.stats.critical}/{report.stats.high}/{report.stats.medium}/{report.stats.low}**"
    )
    lines.append("")
    lines.append("## Key Pressure Signals")
    lines.append("")
    lines.append(f"- Architecture pressure: **{report.signals['architecture_pressure']}**")
    lines.append(f"- Test pressure: **{report.signals['test_pressure']}**")
    lines.append(f"- Governance pressure: **{report.signals['governance_pressure']}**")
    lines.append("")
    lines.append("## Recommendations")
    lines.append("")
    for rec in report.recommendations:
        lines.append(f"- {rec}")
    lines.append("")
    lines.append("## Findings")
    lines.append("")

    for finding in report.findings:
        marker = "🆕 " if finding.fingerprint not in baseline else ""
        loc = f"`{finding.path}`" if finding.path else "`project`"
        if finding.line:
            loc += f":L{finding.line}"
        lines.append(f"### {marker}{finding.severity} — {finding.title}")
        lines.append("")
        lines.append(f"- Rule: `{finding.rule_id}`")
        lines.append(f"- Category: `{finding.category}`")
        lines.append(f"- Confidence: `{finding.confidence:.2f}`")
        lines.append(f"- Location: {loc}")
        lines.append(f"- Message: {finding.message}")
        if finding.evidence:
            lines.append("- Evidence:")
            for item in finding.evidence[:6]:
                lines.append(f"  - `{item[:400]}`")
        if finding.impact:
            lines.append(f"- Impact: {finding.impact}")
        if finding.remediation:
            lines.append(f"- Remediation: {finding.remediation}")
        if finding.verification:
            lines.append(f"- Verification: {finding.verification}")
        lines.append("")

    return "\n".join(lines)


def print_summary(report: AuditReport, baseline: set[str] | None = None) -> None:
    baseline = baseline or set()
    new_count = sum(1 for f in report.findings if f.fingerprint not in baseline) if baseline else report.stats.findings

    print("=" * 78)
    print("SUPREMEAI UNIVERSAL GAP FINDER")
    print("=" * 78)
    print(f"Root:       {report.root}")
    print(f"Risk:       {report.signals['risk_band']} ({report.signals['risk_score']})")
    print(
        f"Findings:   {report.stats.findings} | "
        f"Critical={report.stats.critical} "
        f"High={report.stats.high} "
        f"Medium={report.stats.medium} "
        f"Low={report.stats.low}"
    )
    if baseline:
        print(f"New since baseline: {new_count}")
    print("-" * 78)

    for f in report.findings[:25]:
        loc = f"{f.path}:{f.line}" if f.path and f.line else (f.path or "project")
        print(f"[{f.severity:8}] {f.rule_id:14} {loc}")
        print(f"           {f.title}")
        print(f"           {f.message}")

    if len(report.findings) > 25:
        print(f"... {len(report.findings) - 25} more findings in report")

    print("-" * 78)
    print("Top recommendations:")
    for rec in report.recommendations:
        print(f" - {rec}")
    print("=" * 78)


