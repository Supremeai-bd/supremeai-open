from __future__ import annotations

import re

DEFAULT_IGNORES = {
    ".git", ".hg", ".svn", ".idea", ".vscode", ".venv", "venv", "node_modules",
    "dist", "build", "coverage", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".dart_tool", "target", ".next", ".nuxt", ".gradle", "Pods", "__pycache__",
    "_archive", ".kilo", ".system_generated",
}

TEXT_EXTENSIONS = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx",
    ".dart", ".java", ".kt", ".kts", ".go", ".rs",
    ".c", ".cc", ".cpp", ".h", ".hpp",
    ".cs", ".php", ".rb", ".swift",
    ".yaml", ".yml", ".json", ".toml", ".ini",
    ".cfg", ".conf", ".env", ".md", ".txt",
    ".sh", ".bash", ".ps1", ".sql",
    ".xml", ".html", ".css", ".scss", ".graphql",
}

PROJECT_MANIFESTS = {
    "pyproject.toml": "python",
    "requirements.txt": "python",
    "poetry.lock": "python",
    "package.json": "node",
    "pnpm-lock.yaml": "node",
    "yarn.lock": "node",
    "package-lock.json": "node",
    "pubspec.yaml": "flutter",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "pom.xml": "java",
    "build.gradle": "java",
    "build.gradle.kts": "java",
    "composer.json": "php",
    "Gemfile": "ruby",
}

SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token|private[_-]?key)\b\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
    re.compile(r"(?i)\b(password|passwd|pwd)\b\s*[:=]\s*['\"][^'\"]{6,}['\"]"),
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9._\-]{20,}"),
    re.compile(r"(?i)-----BEGIN (?:RSA|OPENSSH|EC|DSA|PGP) PRIVATE KEY-----"),
]

DANGEROUS_EXEC_PATTERNS = [
    re.compile(r"\bshell\s*=\s*True\b"),
    re.compile(r"\beval\s*\("),
    re.compile(r"\bexec\s*\("),
    re.compile(r"\bos\.system\s*\("),
    re.compile(r"\bsubprocess\.(?:run|Popen|call|check_call|check_output)\s*\("),
]

AUTH_SECURITY_HINTS = {
    "auth": ["auth", "authentication", "authorization", "jwt", "oauth", "rbac", "permission"],
    "security": ["security", "firewall", "sandbox", "sanitizer", "guard", "honeypot", "policy"],
    "billing": ["billing", "payment", "stripe", "wallet", "invoice", "quota", "credit"],
    "tenant": ["tenant", "multiten", "organization", "workspace"],
}

TEST_HINTS = ("test", "tests", "spec", "__tests__", "testing")
DOC_HINTS = ("docs", "documentation", "readme", "guide", "architecture", "adr", "design")

PROTECTED_HINTS = (
    "core/security/",
    "api/dependencies.py",
    "billing/",
    "tenant_db",
    "budget_guard",
    ".env",
    "secrets",
    "auth",
)

SMELL_PATTERNS = [
    ("TODO", re.compile(r"\bTODO\b", re.IGNORECASE), "debt"),
    ("FIXME", re.compile(r"\bFIXME\b", re.IGNORECASE), "debt"),
    ("HACK", re.compile(r"\bHACK\b", re.IGNORECASE), "debt"),
    ("XXX", re.compile(r"\bXXX\b", re.IGNORECASE), "debt"),
    ("NOT_IMPLEMENTED", re.compile(r"NotImplementedError|TODO.*implement", re.IGNORECASE), "incomplete"),
    ("PASS_STUB", re.compile(r"^\s*pass\s*(?:#.*)?$", re.MULTILINE), "stub"),
]
