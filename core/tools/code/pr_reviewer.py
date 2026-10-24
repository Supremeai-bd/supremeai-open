import json
import re
from typing import Any

from core.config import settings
from core.logging_config import logger

try:
    from github import Github

    _GITHUB_AVAILABLE = True
except ImportError:
    _GITHUB_AVAILABLE = False
    Github = None


class PRReviewer:
    """
    Automated Pull Request Reviewer.
    (Closes Gap #21)

    নতুন ফ্লো:
      GitHub PR → Webhook → pr_reviewer.py →
        ├── Security Scan
        ├── Style Check (style_learner.py)
        ├── Code Smell (code_smell_detector.py)
        └── Post Comments → GitHub PR Review
    """

    def __init__(self, github_token: str | None = None):
        self.github_token = github_token or getattr(settings, "github_token", None)
        if not self.github_token:
            logger.warning("GITHUB_TOKEN not found. PR reviewer will run in dry-run mode.")
            self.gh = None
        else:
            if not _GITHUB_AVAILABLE:
                raise ImportError("PyGithub is not installed. Please run 'pip install PyGithub'")
            self.gh = Github(self.github_token)

    async def analyze_diff(self, diff_content: str) -> list[dict[str, Any]]:
        """
        Analyzes a diff content and returns a list of issues including security issues.
        Uses ModelRouter for LLM-based review, falling back to regex.
        """
        # বাংলা মন্তব্য: প্রথমে লোকাল রেগুলার এক্সপ্রেশন (regex) প্যাটার্ন দিয়ে কিছু সাধারণ সিকিউরিটি ইস্যু চেক করা হচ্ছে।
        issues = []
        lines = diff_content.split("\n")

        security_patterns = {
            r"AKIA[0-9A-Z]{16}": {"type": "AWS API Key", "severity": "critical"},
            r"sk_(?:test|live)_[a-zA-Z0-9]{20,}": {
                "type": "Stripe Secret Key",
                "severity": "critical",
            },
            r"(gh[pua]_[0-9a-zA-Z]{36}|github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59})": {
                "type": "GitHub Personal Access Token",
                "severity": "critical",
            },
            r"(?i)password\s*=\s*['\"][^'\"]+['\"]": {
                "type": "Hardcoded Password",
                "severity": "high",
            },
            r"(?i)secret\s*=\s*['\"][^'\"]+['\"]": {
                "type": "Hardcoded Secret",
                "severity": "high",
            },
            r"(?i)api.?key\s*=\s*['\"][^'\"]+['\"]": {
                "type": "API Key",
                "severity": "high",
            },
        }

        for i, line in enumerate(lines):
            if line.startswith("+"):
                found_security_issue = False
                for pattern, info in security_patterns.items():
                    if re.search(pattern, line):
                        issues.append(
                            {
                                "path": "unknown",
                                "line": i + 1,
                                "severity": info["severity"],
                                "body": f"Security Issue: {info['type']} detected in diff",
                            }
                        )
                        found_security_issue = True
                        break
                if not found_security_issue and "TODO" in line:
                    issues.append(
                        {
                            "path": "unknown",
                            "line": i + 1,
                            "severity": "low",
                            "body": "Found a 'TODO' comment. Please add a ticket reference.",
                        }
                    )

        # বাংলা মন্তব্য: যদি ModelRouter উপলব্ধ থাকে, তবে আমরা এআই দিয়ে ডিফটি আরও গভীরভাবে বিশ্লেষণ করব।
        try:
            from brain.model_router import ModelRouter

            router = ModelRouter()

            prompt = (
                "You are an expert code reviewer. Analyze the following Git diff and identify potential bugs, "
                "performance issues, or security flaws. Format your findings as a JSON list of objects, "
                "each containing 'severity' (low/high/critical) and 'body' (description of the issue). "
                "Do not return any markdown wrapping or text, just the raw JSON list.\n\n"
                f"Diff:\n{diff_content[:4000]}"
            )

            result = await router.async_route_and_generate(
                prompt, task_type="coding", max_cost=0.03
            )
            text = result.get("text", "") if isinstance(result, dict) else str(result)

            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = "\n".join(cleaned.splitlines()[1:])
            if cleaned.endswith("```"):
                cleaned = "\n".join(cleaned.splitlines()[:-1])

            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict) and "body" in item:
                            issues.append(
                                {
                                    "path": "unknown",
                                    "line": item.get("line", 0),
                                    "severity": item.get("severity", "low"),
                                    "body": item["body"],
                                }
                            )
            except (json.JSONDecodeError, ValueError) as _json_err:
                logger.warning(f"Failed to parse LLM response in PRReviewer: {_json_err}")
        except BaseException as _router_err:
            # বাংলা মন্তব্য: ExceptionGroup (Python 3.11+ TaskGroup) সহ সব ধরনের exception gracefully হ্যান্ডেল করা হচ্ছে।
            logger.warning(f"ModelRouter call failed in PRReviewer: {_router_err}")

        return issues

    async def check_style_compliance(
        self, diff_content: str, repo_path: str = "default"
    ) -> list[dict[str, Any]]:
        """ব্যবহারকারীর শেখা স্টাইল দিয়ে কমপ্লায়েন্স চেক করে।"""
        issues: list[dict[str, Any]] = []
        try:
            from tools.learning.style_learner import StyleLearner

            learner = StyleLearner()
            if repo_path in learner.learned_styles:
                style_prompt = learner.generate_style_prompt(repo_path, "python")
                # বাংলা মন্তব্য: স্টাইল গাইডলাইন লঙ্ঘন হলে সেটি ইস্যু হিসেবে যোগ করা হচ্ছে।
                if "snake_case" in style_prompt:
                    for i, line in enumerate(diff_content.split("\n")):
                        if line.startswith("+") and re.search(r"def\s+[a-z]+[A-Z]", line):
                            issues.append(
                                {
                                    "path": "unknown",
                                    "line": i + 1,
                                    "severity": "info",
                                    "body": "Style: function naming should follow snake_case convention.",
                                }
                            )
        except Exception as e:
            logger.debug(f"Style compliance check skipped: {e}")
        return issues

    async def run_code_smell_scan(self, diff_content: str) -> list[dict[str, Any]]:
        """code_smell_detector.py দিয়ে প্যাচ করা ফাইলগুলোর স্মেল স্ক্যান করে।"""
        issues: list[dict[str, Any]] = []
        try:
            import tempfile

            from tools.code.code_smell_detector import CodeSmellDetector

            detector = CodeSmellDetector()
            # বাংলা মন্তব্য: ডিফ থেকে শুধু যোগ করা (+) লাইনগুলো নিয়ে অস্থায়ী ফাইল বানিয়ে স্ক্যান করা হচ্ছে।
            added_lines = [
                ln[1:]
                for ln in diff_content.split("\n")
                if ln.startswith("+") and not ln.startswith("+++")
            ]
            with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as tmp:
                tmp.write("\n".join(added_lines))
                tmp_path = tmp.name
            try:
                smells = detector.analyze_python_file(tmp_path)
                for s in smells:
                    issues.append(
                        {
                            "path": "unknown",
                            "line": s.get("line", 0),
                            "severity": ("warning" if s.get("severity") == "warning" else "info"),
                            "body": f"Code Smell: {s.get('type')} — {s.get('message', '')}",
                        }
                    )
            finally:
                import os

                os.unlink(tmp_path)
        except Exception as e:
            logger.debug(f"Code smell scan skipped: {e}")
        return issues

    async def review_pr(self, repo_full_name: str, pr_number: int) -> dict[str, Any]:
        """
        Reviews a pull request by fetching the diff and analyzing it for issues.
        """
        if not self.gh:
            logger.warning(f"Dry-run: Would review {repo_full_name}#{pr_number}")
            return {"status": "success", "action_taken": "COMMENT", "comments": []}

        # বাংলা মন্তব্য: গিটহাব ক্লায়েন্ট ব্যবহার করে নির্দিষ্ট পুল রিকোয়েস্টের ফাইল এবং তাদের ডিফারেন্স সংগ্রহ করা হচ্ছে।
        try:
            repo = self.gh.get_repo(repo_full_name)
            pr = repo.get_pull(pr_number)
            diff = pr.get_files()

            comments = []
            has_critical = False

            for file_diff in diff:
                diff_content = file_diff.patch or ""
                file_comments = await self.analyze_diff(diff_content)
                file_comments += await self.check_style_compliance(diff_content)
                file_comments += await self.run_code_smell_scan(diff_content)
                for c in file_comments:
                    c["path"] = file_diff.filename
                comments.extend(file_comments)
                if any(c["severity"] == "critical" for c in file_comments):
                    has_critical = True

            action = "REQUEST_CHANGES" if has_critical else "COMMENT"

            # বাংলা মন্তব্য: রিভিউয়ের ফলাফল একটি কমেন্ট আকারে পুল রিকোয়েস্টে পোস্ট করা হচ্ছে।
            if comments:
                summary_lines = ["### 🤖 AI Code Review Findings", ""]
                for c in comments:
                    sev_icon = (
                        "🔴"
                        if c["severity"] == "critical"
                        else ("🟡" if c["severity"] == "high" else "🔵")
                    )
                    summary_lines.append(
                        f"- {sev_icon} **[{c['severity'].upper()}]** in `{c['path']}`: {c['body']}"
                    )

                await self._post_pr_comment(repo_full_name, pr_number, "\n".join(summary_lines))

            # বাংলা মন্তব্য: সব চেক পাস করলে অটো-অপ্রুভ করা হচ্ছে।
            if not comments and not has_critical:
                await self._auto_approve(repo_full_name, pr_number)

            return {"status": "success", "action_taken": action, "comments": comments}
        except Exception as e:
            logger.error(f"Error reviewing PR: {e}")
            return {"status": "error", "error": str(e), "comments": []}

    async def _auto_approve(self, repo_full_name: str, pr_number: int) -> dict[str, Any]:
        """সব চেক পাস করলে PR অটো-অপ্রুভ করে।"""
        if not self.gh:
            logger.warning(f"Dry-run: Would auto-approve {repo_full_name}#{pr_number}")
            return {"status": "success", "approved": True}
        try:
            repo = self.gh.get_repo(repo_full_name)
            pr = repo.get_pull(pr_number)
            pr.create_review(
                event="APPROVE",
                body="✅ All automated checks passed. Auto-approved by SupremeAI.",
            )
            return {"status": "success", "approved": True}
        except Exception as e:
            logger.error(f"Auto-approve failed: {e}")
            return {"status": "error", "error": str(e)}

    async def _post_pr_comment(
        self, repo_full_name: str, pr_number: int, comment_body: str
    ) -> dict[str, Any]:
        """Posts a comment on a pull request."""
        # বাংলা মন্তব্য: গিটহাব এপিআই দিয়ে পিআর-এ রিভিউ কমেন্ট পোস্ট করা হচ্ছে।
        if not self.gh:
            logger.warning(f"Dry-run: Would post to {repo_full_name}#{pr_number}: {comment_body}")
            return {"status": "success", "comment_url": "dry-run-url"}

        try:
            repo = self.gh.get_repo(repo_full_name)
            pr = repo.get_pull(pr_number)
            comment = pr.create_issue_comment(comment_body)
            return {"status": "success", "comment_url": comment.html_url}
        except Exception as e:
            logger.error(f"Failed to post comment to GitHub: {e}")
            return {"status": "error", "error": str(e)}
