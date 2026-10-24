import os
import re
import subprocess
from typing import Any, ClassVar

from core.logging_config import logger

try:
    from tools.code.pr_reviewer import PRReviewer

    _PR_REVIEWER_AVAILABLE = True
except Exception:
    _PR_REVIEWER_AVAILABLE = False
    PRReviewer = None  # type: ignore[misc,assignment]


class PreCommitAI:
    """
    Git hook integration that analyzes staged files before commit.
    Blocks commits with critical security issues or offers auto-fixes.
    Supports pre-commit framework via .pre-commit-config.yaml.
    (Closes Gap #22)
    """

    AUTO_FIX_RULES: ClassVar[Any] = {
        "trailing_whitespace": True,
        "end_of_file_newline": True,
        "import_sort": True,
        "line_length": 120,
    }

    def __init__(self):
        self.reviewer = PRReviewer() if _PR_REVIEWER_AVAILABLE and PRReviewer is not None else None
        self._check_tools()
        logger.info("Initialized PreCommitAI hook handler")

    def _check_tools(self) -> None:
        self.isort_available = False
        self.black_available = False
        try:
            import isort  # noqa: F401 -- শুধু availability probe

            self.isort_available = True
        except ImportError:
            logger.warning(
                "isort is not installed. Some auto-fixes will be unavailable. Run 'pip install isort'"
            )
        try:
            import black  # noqa: F401 -- শুধু availability probe

            self.black_available = True
        except ImportError:
            logger.warning(
                "black is not installed. Some auto-fixes will be unavailable. Run 'pip install black'"
            )
        logger.debug(f"PreCommit tools: isort={self.isort_available}, black={self.black_available}")

    def _get_staged_diff(self) -> str:
        """Gets the git diff for staged files."""
        try:
            import shlex

            cmd = shlex.split("git diff --cached")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except subprocess.CalledProcessError:
            logger.error("Failed to get staged git diff. Is this a git repository?")
            return ""
        except FileNotFoundError:
            logger.error("git not found in PATH.")
            return ""

    def _get_staged_files(self) -> list[str]:
        """Returns list of staged file paths."""
        try:
            import shlex

            cmd = shlex.split("git diff --cached --name-only --diff-filter=ACM")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            return [f for f in result.stdout.splitlines() if f.strip()]
        except Exception as exc:
            logger.error(f"Failed to list staged files: {exc}")
            return []

    def _auto_fix(self, files: list[str]) -> dict[str, Any]:
        """Apply simple auto-fixes: trailing whitespace, import sort."""
        fixes_applied: list[dict[str, str]] = []
        for filepath in files:
            if not os.path.exists(filepath):
                continue
            ext = os.path.splitext(filepath)[1].lower()
            original_content = ""
            try:
                with open(filepath, encoding="utf-8", errors="ignore") as f:
                    original_content = f.read()
            except Exception as e:
                try:
                    import loguru

                    loguru.logger.error(f"Tool execution error: {e}")
                except Exception as e:
                    logger.warning(f"Exception suppressed: {e}")
                continue  # Skip binary files that can't be read

            new_content = original_content
            content_changed = False

            try:
                # Python-specific fixes
                if ext == ".py":
                    if self.isort_available and self.AUTO_FIX_RULES.get("import_sort"):
                        import isort

                        sorted_content = isort.code(new_content)
                        if sorted_content != new_content:
                            new_content = sorted_content
                            fixes_applied.append({"file": filepath, "action": "isort"})
                            content_changed = True

                    if self.black_available:
                        import black

                        formatted_content = black.format_str(new_content, mode=black.Mode())
                        if formatted_content != new_content:
                            new_content = formatted_content
                            fixes_applied.append({"file": filepath, "action": "black"})
                            content_changed = True

                # Generic fixes for all file types
                if self.AUTO_FIX_RULES.get("trailing_whitespace"):
                    # Use a regex to remove trailing whitespace from each line
                    processed_content = re.sub(r"[ \t]+$", "", new_content, flags=re.MULTILINE)
                    if processed_content != new_content:
                        new_content = processed_content
                        fixes_applied.append(
                            {"file": filepath, "action": "trim_trailing_whitespace"}
                        )
                        content_changed = True

                if self.AUTO_FIX_RULES.get("end_of_file_newline") and not new_content.endswith(
                    "\n"
                ):
                    new_content += "\n"
                    fixes_applied.append({"file": filepath, "action": "add_final_newline"})
                    content_changed = True

                if content_changed:
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(new_content)

            except Exception as exc:
                logger.debug(f"Auto-fix failed for {filepath}: {exc}")
        return {"fixes": fixes_applied, "count": len(fixes_applied)}

    async def run_hook(self, auto_fix: bool = True) -> dict[str, Any]:
        """Runs the pre-commit analysis."""
        logger.info("Running AI Pre-Commit Hook...")

        diff = self._get_staged_diff()
        if not diff:
            return {"status": "success", "message": "No staged changes to analyze."}

        issues: list[dict[str, Any]] = []
        if self.reviewer is not None:
            try:
                issues = await self.reviewer.analyze_diff(diff)
            except Exception as exc:
                logger.error(f"AI analysis failed: {exc}")
                return {"status": "error", "message": f"AI analysis failed: {exc}"}
        else:
            issues = self._static_security_scan(diff)

        critical_issues = [
            i
            for i in issues
            if "critical" in str(i.get("severity", "")).lower()
            or "SECURITY" in str(i.get("body", "")).upper()
        ]

        if critical_issues:
            logger.error(
                f"Pre-commit blocked! Found {len(critical_issues)} critical security issues."
            )
            for issue in critical_issues:
                logger.error(
                    f"  - {issue.get('path', '?')}:{issue.get('line', '?')} -> {issue.get('body', issue.get('type', ''))}"
                )
            return {
                "status": "blocked",
                "reason": "Critical security vulnerabilities detected.",
                "issues": critical_issues,
            }

        files = self._get_staged_files()

        if auto_fix and files:
            fix_report = self._auto_fix(files)
            if fix_report["count"] > 0:
                import os
                import shlex

                for fp in files:
                    # Strict Path Traversal Whitelist Validation
                    abs_path = os.path.abspath(fp)
                    base_dir = os.path.abspath(os.getcwd())
                    if not abs_path.startswith(base_dir) or ".." in fp:
                        logger.error(f"Security Alert: Path traversal attempt blocked for {fp}")
                        continue

                    try:
                        cmd = shlex.split(f"git add {shlex.quote(fp)}")
                        subprocess.run(cmd, check=True, capture_output=True)
                    except Exception as exc:
                        logger.exception(f"git add failed for {fp}: {exc}")
                logger.info(f"Auto-fixed {fix_report['count']} issue(s).")
                # The commit was not blocked, files were fixed and re-staged.
                # Allow the commit to proceed.
                logger.info("Auto-fixed files were re-staged. Allowing commit to proceed.")
                # The hook should return success now. The calling pre-commit framework will handle the rest.

        if issues:
            logger.warning(
                f"Found {len(issues)} non-critical issues. Commit allowed but review is suggested."
            )

        logger.info("Pre-commit checks passed.")
        return {
            "status": "success",
            "message": "All checks passed.",
            "warnings": issues,
        }

    def _static_security_scan(self, diff_content: str) -> list[dict[str, Any]]:
        """Regex-based fallback when PRReviewer/LLM is unavailable."""
        issues: list[dict[str, Any]] = []
        lines = diff_content.split("\n")
        current_file = "unknown"
        line_num = 0
        secret_patterns = {
            "AWS API Key": r"AKIA[0-9A-Z]{16}",
            "Stripe Secret Key": r"sk_live_[0-9a-zA-Z]{24}",
            "Generic Secret/Password": r"(password|passwd|secret|api_key|token)\s*=\s*['\"][^'\"]{8,}['\"]",
        }
        for line in lines:
            if line.startswith("+++ b/"):
                current_file = line[6:]
                line_num = 0
                continue
            if line.startswith("@@"):
                match = re.search(r"\+(\d+)", line)
                line_num = int(match.group(1)) if match else 0
                continue
            if line.startswith("+") and not line.startswith("+++"):
                for name, pat in secret_patterns.items():
                    if re.search(pat, line, re.IGNORECASE):
                        issues.append(
                            {
                                "path": current_file,
                                "line": line_num,
                                "severity": "critical",
                                "body": f"SECURITY: Potential {name} exposure detected.",
                            }
                        )
                line_num += 1
            elif not line.startswith("-"):
                line_num += 1
        return issues


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SupremeAI Pre-Commit AI Gate")
    parser.add_argument("--no-fix", action="store_true", help="Run analysis without auto-fixing")
    parser.add_argument("files", nargs="*", help="Optional file list (ignored; uses staged diff)")
    args = parser.parse_args()

    hook = PreCommitAI()
    import asyncio

    result = asyncio.run(hook.run_hook(auto_fix=not args.no_fix))
    status = result.get("status", "error")
    if status == "blocked":
        logger.info("❌ Commit blocked:", result.get("reason"))
        for issue in result.get("issues", []):
            logger.info(
                f"  - {issue.get('path', '?')}:{issue.get('line', '?')} -> {issue.get('body', '')}"
            )
        raise SystemExit(1)
    elif status == "fixed":
        logger.info("⚠️  Auto-fixed issues. Review and re-commit.")
        raise SystemExit(1)
    elif status == "error":
        logger.info("❌ Error:", result.get("message"))
        raise SystemExit(1)
    else:
        logger.info("✅ Pre-commit checks passed.")
