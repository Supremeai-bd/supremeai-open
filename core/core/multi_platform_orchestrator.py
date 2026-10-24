"""Multi-Platform AI to Workspace Orchestrator (Genkit, ChatGPT, Claude, Gemini to Real Code).

বাংলা সারসংক্ষেপ:
------------------
ব্যবহারকারী Genkit, ChatGPT, Claude, Gemini বা v0-তে কোনো প্রশ্ন বা টাস্ক দেওয়ার পর
সেই এআই-এর দেওয়া আন-স্ট্রাকচার্ড টেক্সট/কোড আউটপুট স্বয়ংক্রিয়ভাবে পার্স করে:
১. ফাইলের সঠিক পাথ ও কনটেন্ট আলাদা করা (File Action Extractor)।
২. ফাইল এডিট তৈরি করা (Modify, Create, Delete)।
৩. ব্যবহারকারীর GitHub Codespaces / Gitpod-এ ১-ক্লিকে জাম্প করার ডিপ-লিঙ্ক তৈরি।
৪. লোকাল বা ক্লাউড ওয়ার্কস্পেসে কোড প্রয়োগ ও টেস্ট ভেরিফিকেশন চালানো।
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from core.logging_config import logger


class ActionType(StrEnum):
    """ওয়ার্কস্পেস অ্যাকশনের ধরন"""

    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"
    EXECUTE_COMMAND = "execute_command"


@dataclass
class FileAction:
    """ফাইল এডিটের একক অ্যাকশন স্পেসিফিকেশন"""

    file_path: str
    action_type: ActionType
    content: str
    original_snippet: str | None = None
    language: str | None = None


@dataclass
class OrchestrationPlan:
    """
    মাল্টি-প্ল্যাটফর্ম এআই থেকে এক্সট্র্যাক্ট করা বাস্তবায়ন পরিকল্পনা।
    "কইয়ের তেলেই কই ভাজা, কিন্তু নিজের নামে মাছ বেচা" — ব্যবহারকারীর কাছে এটি SupremeAI সলিউশন হিসেবে উপস্থাপিত হয়।
    """

    source_platform: str
    file_actions: list[FileAction] = field(default_factory=list)
    verification_commands: list[str] = field(default_factory=list)
    supreme_workspace_url: str | None = None
    codespaces_url: str | None = None
    gitpod_url: str | None = None
    jules_url: str | None = None
    explanation: str = ""
    platform_agnostic_summary: str = ""
    engine_brand: str = "SupremeAI Autonomous Core"
    raw_ai_output: str = ""


@dataclass
class ExecutionResult:
    """ওয়ার্কস্পেসে বাস্তবায়নের ফলাফল"""

    success: bool
    applied_files: list[str] = field(default_factory=list)
    failed_files: list[str] = field(default_factory=list)
    verification_output: str = ""
    verification_passed: bool = False
    errors: list[str] = field(default_factory=list)


class MultiPlatformOrchestrator:
    """
    মাল্টি-প্ল্যাটফর্ম এআই আউটপুট ইন্টারসেপ্টর ও কোডস্পেস অর্কেস্ট্রেটর।
    """

    # বাংলা মন্তব্য: ফাইল পাথ শনাক্তকারী সাধারণ রেজেক্স প্যাটার্ন
    FILE_PATH_PATTERNS = [
        r"(?:^|\n)\s*(?:###?|File|Target File|FilePath|Path|Editing|Creating)?[:\s`]*([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9_]+)[:\s`]*\n+```([a-zA-Z0-9_]*)\n([\s\S]*?)```",
        r"```([a-zA-Z0-9_]*)[ \t]+(?:filepath=|file=|path=)?([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9_]+)\n([\s\S]*?)```",
        r"//\s*(?:file|filepath|path):\s*([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9_]+)\n([\s\S]*?)```",
        r"#\s*(?:file|filepath|path):\s*([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9_]+)\n([\s\S]*?)```",
    ]

    # বাংলা মন্তব্য: টেস্ট ও ভেরিফিকেশন কমান্ড শনাক্তকারী প্যাটার্ন
    COMMAND_PATTERNS = [
        r"```(?:bash|sh|shell|console|terminal)\n([\s\S]*?)```",
        r"(?:run|execute|test with):\s*`([^`]+)`",
    ]

    def parse_ai_output(
        self,
        raw_output: str,
        repo_name: str = "SaifulHaqueNiloy/supremeai",
        branch: str = "main",
        source_platform: str = "SupremeAI Autonomous Core",
        white_label: bool = True,
    ) -> OrchestrationPlan:
        """
        বাংলা সারসংক্ষেপ:
        ------------------
        "কইয়ের তেলেই কই ভাজা, কিন্তু নিজের নামে মাছ বেচা":
        ChatGPT, Claude, Gemini বা Genkit-এর কাঁচা টেক্সট থেকে
        ফাইল পাথ, কোড কনটেন্ট ও ভেরিফিকেশন কমান্ড এক্সট্র্যাক্ট করে SupremeAI সলিউশন প্ল্যান বানায়।
        কোড বা ফাইলে কোনো তৃতীয় পক্ষের ওয়াটারমার্ক বা নাম থাকলে তা স্বয়ংক্রিয়ভাবে স্ক্রাব করে মুছে ফেলা হয়।
        """
        from core.natural_file_presenter import NaturalFilePresenter

        clean_source = (
            "SupremeAI Autonomous Core"
            if source_platform in ("generic_ai", "", None)
            else source_platform
        )

        if not raw_output or not raw_output.strip():
            return OrchestrationPlan(
                source_platform=clean_source,
                raw_ai_output=raw_output,
                explanation="Empty output received.",
                platform_agnostic_summary="No actions found in output.",
            )

        file_actions: list[FileAction] = []
        seen_paths: set[str] = set()

        # ধাপ ১: স্পেসিফিক হেডার ও কোড ব্লক থেকে ফাইল উদ্ধার
        # প্যাটার্ন ১: ### backend/core/cache.py\n```python\n...```
        for pat in self.FILE_PATH_PATTERNS:
            for match in re.finditer(pat, raw_output, flags=re.IGNORECASE):
                groups = match.groups()
                if len(groups) == 3:
                    if "." in groups[0]:  # পাথ প্রথমে
                        fpath, lang, content = groups[0].strip(), groups[1].strip(), groups[2]
                    else:  # ল্যাঙ্গুয়েজ প্রথমে, পাথ দ্বিতীয়
                        lang, fpath, content = groups[0].strip(), groups[1].strip(), groups[2]
                elif len(groups) == 2:
                    fpath, content = groups[0].strip(), groups[1]
                    lang = None
                else:
                    continue

                clean_path = fpath.strip("`'\" :").replace("\\", "/")
                # শুধু লিডিং ./ বা / বাদ দেওয়া, কিন্তু ../ অক্ষুণ্ণ রাখা যাতে সিকিউরিটি চেক ধরতে পারে
                clean_path = re.sub(r"^\./+", "", clean_path).lstrip("/")

                if clean_path and clean_path not in seen_paths and "." in clean_path:
                    seen_paths.add(clean_path)
                    # বাংলা মন্তব্য: কোডের ভেতর থেকে যেকোনো থার্ড পার্টি ওয়াটারমার্ক বা কমেন্ট ক্লিন করা
                    clean_content = (
                        NaturalFilePresenter.white_label_solution(content.strip())
                        if white_label
                        else content.strip()
                    )
                    file_actions.append(
                        FileAction(
                            file_path=clean_path,
                            action_type=ActionType.MODIFY,
                            content=clean_content,
                            language=lang or None,
                        )
                    )

        # ধাপ ২: যদি কোনো ফাইলপাথ সরাসরি ব্লকে না থাকে কিন্তু জেনেরিক কোড ব্লক থাকে
        if not file_actions:
            code_blocks = re.findall(r"```([a-zA-Z0-9_]*)\n([\s\S]*?)```", raw_output)
            for idx, (lang, code) in enumerate(code_blocks):
                if lang.lower() in ("bash", "sh", "terminal", "console", "json", ""):
                    continue
                # কনটেন্ট দেখে নাম আন্দাজ করা (NaturalFilePresenter)
                ext = f".{lang.lower()}" if lang else ".py"
                inferred_name = NaturalFilePresenter.naturalize_filename(
                    f"output_{idx}{ext}", content=code
                )
                if inferred_name not in seen_paths:
                    seen_paths.add(inferred_name)
                    clean_content = (
                        NaturalFilePresenter.white_label_solution(code.strip())
                        if white_label
                        else code.strip()
                    )
                    file_actions.append(
                        FileAction(
                            file_path=inferred_name,
                            action_type=ActionType.CREATE,
                            content=clean_content,
                            language=lang or None,
                        )
                    )

        # ধাপ ৩: ভেরিফিকেশন ও টেস্ট কমান্ড উদ্ধার
        verification_commands: list[str] = []
        for pat in self.COMMAND_PATTERNS:
            for match in re.finditer(pat, raw_output, flags=re.IGNORECASE):
                cmd_block = match.group(1).strip()
                for line in cmd_block.splitlines():
                    clean_line = line.strip().lstrip("$ ")
                    if clean_line and (
                        clean_line.startswith(("pytest", "python -m pytest", "npm test", "uv run"))
                        or "test" in clean_line
                    ):
                        if clean_line not in verification_commands:
                            verification_commands.append(clean_line)

        # ধাপ ৪: ১-ক্লিক ক্লাউড ওয়ার্কস্পেস ইউআরএল জেনারেশন (Codespaces & Gitpod)
        primary_file = file_actions[0].file_path if file_actions else ""
        codespaces_url = self.generate_codespaces_url(repo_name, branch, primary_file)
        gitpod_url = self.generate_gitpod_url(repo_name, branch, primary_file)
        jules_url = f"https://jules.google.com/?repo={repo_name}"
        # বাংলা মন্তব্য: একক প্রিমিয়াম সুপ্রিম ক্লাউড লিঙ্ক (যা ডিফল্টভাবে ব্যাকএন্ডে কোডস্পেসকে ট্রিগার করবে)
        supreme_workspace_url = codespaces_url or gitpod_url

        summary = f"Supreme Solution: {len(file_actions)} files planned, {len(verification_commands)} verification tests ready."

        return OrchestrationPlan(
            source_platform=clean_source,
            file_actions=file_actions,
            verification_commands=verification_commands,
            supreme_workspace_url=supreme_workspace_url,
            codespaces_url=codespaces_url,
            gitpod_url=gitpod_url,
            jules_url=jules_url,
            explanation=f"Extracted {len(file_actions)} file actions and {len(verification_commands)} verification steps.",
            platform_agnostic_summary=summary,
            engine_brand="SupremeAI Autonomous Core",
            raw_ai_output=raw_output,
        )

    @staticmethod
    def generate_codespaces_url(repo_name: str, branch: str = "main", file_path: str = "") -> str:
        """
        বাংলা মন্তব্য: ১-ক্লিকে ব্যবহারকারীর GitHub Codespaces ওপেন করার গভীর লিঙ্ক।
        """
        base = f"https://github.com/codespaces/new?repo={repo_name}&ref={branch}"
        return base

    @staticmethod
    def generate_gitpod_url(repo_name: str, branch: str = "main", file_path: str = "") -> str:
        """
        বাংলা মন্তব্য: ১-ক্লিকে Gitpod ক্লাউড ভিএসকোড ওপেন করার গভীর লিঙ্ক।
        """
        url = f"https://gitpod.io/#https://github.com/{repo_name}/tree/{branch}"
        return url

    def apply_plan_locally(
        self, plan: OrchestrationPlan, workspace_root: Path | str
    ) -> ExecutionResult:
        """
        বাংলা সারসংক্ষেপ:
        ------------------
        এক্সট্র্যাক্ট করা ফাইল এডিটগুলোকে সরাসরি লোকাল বা কোডস্পেস ডিরেক্টরিতে প্রয়োগ করে।
        নিরাপত্তা: পাথ ট্রাভার্সাল (Directory Traversal '../') সম্পূর্ণ নিষিদ্ধ।
        """
        root = Path(workspace_root).resolve()
        applied: list[str] = []
        failed: list[str] = []
        errors: list[str] = []

        for action in plan.file_actions:
            clean_rel = action.file_path.replace("\\", "/")
            if ".." in clean_rel.split("/") or action.file_path.startswith("../"):
                failed.append(action.file_path)
                errors.append(f"Security: Path traversal attempt blocked for {action.file_path}")
                continue

            target_path = (root / action.file_path).resolve()
            # নিরাপত্তা চেক: পাথ অবশ্যই ওয়ার্কস্পেসের ভেতরে থাকতে হবে
            if not str(target_path).startswith(str(root)):
                failed.append(action.file_path)
                errors.append(f"Security: Path traversal attempt blocked for {action.file_path}")
                continue

            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(action.content, encoding="utf-8")
                applied.append(action.file_path)
                logger.info(f"[MultiPlatformOrchestrator] Applied edits to {action.file_path}")
            except Exception as exc:
                failed.append(action.file_path)
                errors.append(f"Failed to write {action.file_path}: {exc}")

        # ভেরিফিকেশন টেস্ট কমান্ড চালানো (যদি থাকে)
        verification_output = ""
        verification_passed = True
        if plan.verification_commands and applied:
            cmd = plan.verification_commands[0]
            try:
                # সেফ রানার
                res = subprocess.run(
                    cmd,
                    shell=True,
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                verification_output = res.stdout or res.stderr
                verification_passed = res.returncode == 0
            except Exception as exc:
                verification_output = f"Verification execution error: {exc}"
                verification_passed = False

        return ExecutionResult(
            success=len(applied) > 0 and len(failed) == 0,
            applied_files=applied,
            failed_files=failed,
            verification_output=verification_output,
            verification_passed=verification_passed,
            errors=errors,
        )


# বাংলা মন্তব্য: গ্লোবাল সিঙ্গলটন
default_orchestrator = MultiPlatformOrchestrator()
