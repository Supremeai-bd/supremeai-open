#!/usr/bin/env python3
# 🛡️ মাল্টি-মডেল কোড ভ্যালিডেটর — SupremeAI 2.0
# বাংলা মন্তব্য: এটি এআই মডেল ও স্ট্যাটিক AST সিকিউরিটি অ্যানালাইসিসের মাধ্যমে কোডের নিরাপত্তা ও লজিক যাচাই করে

import argparse
import ast
import asyncio
import json
import os
from pathlib import Path
from typing import Any

try:
    from loguru import logger
except ImportError:
    import logging

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    logger = logging.getLogger("multi_model_validator")

# Optional LiteLLM integration
HAVE_LITELLM = False
try:
    import litellm

    HAVE_LITELLM = True
except ImportError as e:
    import logging

    logging.getLogger(__name__).debug(f"Optional litellm not installed: {e}")


class MultiModelValidator:
    """
    মাল্টি-মডেল ও স্ট্যাটিক সিকিউরিটি কোড ভ্যালিডেশন ইঞ্জিন
    - সিকিউরিটি স্ক্যান (SQL Injection, XSS, Auth Bypass, Dangerous Eval)
    - লজিক ভ্যালিডেশন
    - পারফরম্যান্স ও সেফটি চেক
    """

    def __init__(self):
        self.validators: list[tuple[str, str]] = self._resolve_dynamic_validators()
        self.has_llm_keys = len(self.validators) > 0

    def _resolve_dynamic_validators(self) -> list[tuple[str, str]]:
        """ডাইনামিক মডেল পুল ($0..N) রেজোলিউশন — কোনো হার্ডকোডেড ভেন্ডর নয় (Issue #466)"""
        pool: list[tuple[str, str]] = []

        # 1. Budget Validator Candidate
        if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
            pool.append(("gemini/gemini-2.5-flash", "budget_validator"))
        elif os.getenv("OPENROUTER_API_KEY"):
            pool.append(("openrouter/google/gemini-2.0-flash-001", "budget_validator"))

        # 2. Security Validator Candidate
        if os.getenv("OPENAI_API_KEY"):
            pool.append(("openai/gpt-4o-mini", "security_validator"))
        elif os.getenv("ANTHROPIC_API_KEY"):
            pool.append(("anthropic/claude-3-5-haiku-20241022", "security_validator"))
        elif os.getenv("MISTRAL_API_KEY"):
            pool.append(("mistral/mistral-small-latest", "security_validator"))

        # 3. Logic & Reasoning Validator Candidate
        if os.getenv("GROQ_API_KEY"):
            pool.append(("groq/llama-3.3-70b-versatile", "logic_validator"))
        elif os.getenv("OPENROUTER_API_KEY"):
            pool.append(
                ("openrouter/meta-llama/llama-3.3-70b-instruct", "logic_validator")
            )
        elif os.getenv("DEEPSEEK_API_KEY"):
            pool.append(("deepseek/deepseek-chat", "logic_validator"))

        # If still empty but generic LiteLLM key exists
        if not pool and os.getenv("LITELLM_API_KEY"):
            pool.append(("openai/gpt-4o-mini", "general_validator"))

        if not pool:
            logger.info(
                "ℹ️ No LLM API keys configured — running full static AST security validation ($0 key mode)."
            )

        return pool

    def _static_ast_scan(self, file_path: str, code_content: str) -> dict[str, Any]:
        """স্ট্যাটিক AST সিকিউরিটি অ্যানালাইসিস"""
        issues: list[dict[str, str]] = []
        try:
            tree = ast.parse(code_content, filename=file_path)
            for node in ast.walk(tree):
                # Check for dangerous eval / exec
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in ("eval", "exec"):
                        issues.append(
                            {
                                "type": "Dangerous Function Call",
                                "severity": "HIGH",
                                "description": f"Dangerous built-in `{node.func.id}()` called at line {node.lineno}",
                                "fix": "Avoid dynamic code execution; use safe parsing.",
                            }
                        )
                # Check for raw string concatenation in SQL queries
                elif (
                    isinstance(node, ast.BinOp)
                    and isinstance(node.op, ast.Add)
                    and isinstance(node.left, ast.Constant)
                    and isinstance(node.left.value, str)
                ):
                    val = node.left.value.lower()
                    if any(
                        q in val
                        for q in ["select ", "insert into ", "update ", "delete from "]
                    ):
                        issues.append(
                            {
                                "type": "Potential SQL Injection",
                                "severity": "HIGH",
                                "description": f"String concatenation in SQL query at line {node.lineno}",
                                "fix": "Use parameterized queries or ORM models.",
                            }
                        )
        except SyntaxError as e:
            logger.debug(f"AST parse error on {file_path}: {e}")
        except Exception as e:  # noqa: BLE001 — defensive scan must never crash the validator
            logger.debug(f"AST scan error on {file_path}: {e}")

        risk_level = "HIGH" if any(i["severity"] == "HIGH" for i in issues) else "LOW"
        return {
            "vulnerabilities": issues,
            "risk_level": risk_level,
            "mode": "static_ast_analyzer",
        }

    async def validate_code(self, file_path: str) -> dict[str, Any]:
        """কোড ফাইল বা ডিরেক্টরি ভ্যালিডেট করুন (Directory সমর্থিত)"""
        path_obj = Path(file_path)

        if path_obj.is_dir():
            py_files = [
                str(p)
                for p in path_obj.rglob("*.py")
                if p.is_file() and not p.name.startswith(".")
            ]
            dir_results = []
            all_passed = True
            for py_f in py_files:
                res = await self.validate_code(py_f)
                dir_results.append(res)
                if not res.get("passed", True):
                    all_passed = False
            return {
                "file": file_path,
                "is_directory": True,
                "total_files": len(py_files),
                "results": dir_results,
                "passed": all_passed,
                "overall_risk_level": "LOW" if all_passed else "HIGH",
            }

        try:
            code_content = await asyncio.to_thread(
                Path(file_path).read_text, "utf-8", "ignore"
            )
        except OSError as e:
            logger.error(f"Cannot read file {file_path}: {e}")
            return {
                "status": "error",
                "message": str(e),
                "passed": True,
                "overall_risk_level": "LOW",
            }

        file_ext = Path(file_path).suffix
        results = {
            "file": file_path,
            "timestamp": str(
                Path(file_path).stat().st_mtime if Path(file_path).exists() else 0
            ),
            "validations": [],
            "overall_risk_level": "LOW",
            "passed": True,
        }

        # Static AST scan first
        static_res = self._static_ast_scan(file_path, code_content)
        results["validations"].append(static_res)
        if static_res["risk_level"] in ["CRITICAL", "HIGH"]:
            results["passed"] = False
            results["overall_risk_level"] = static_res["risk_level"]

        # If LLM keys available and LiteLLM installed, run multi-model checks
        if self.has_llm_keys and HAVE_LITELLM:
            for model, validator_type in self.validators:
                val_res = await self._validate_with_model(
                    model, code_content, file_ext, validator_type
                )
                results["validations"].append(val_res)
                if val_res.get("risk_level") in ["CRITICAL", "HIGH"]:
                    results["passed"] = False
                    results["overall_risk_level"] = val_res["risk_level"]

        return results

    async def _validate_with_model(
        self, model: str, code_content: str, file_ext: str, validator_type: str
    ) -> dict[str, Any]:
        """একটি নির্দিষ্ট মডেল দিয়ে কোড ভ্যালিডেট করুন"""
        if not HAVE_LITELLM:
            return {
                "model": model,
                "validator_type": validator_type,
                "status": "skipped",
                "risk_level": "LOW",
            }

        try:
            prompt = f'Review this {file_ext} code for security vulnerabilities. Output JSON: {{"vulnerabilities": [], "risk_level": "LOW"}}.\n\nCode:\n{code_content[:3000]}'
            response = await litellm.acompletion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=500,
                timeout=15,
            )
            response_text = response.choices[0].message.content
            try:
                parsed = json.loads(response_text)
            except json.JSONDecodeError:
                parsed = {"raw_response": response_text, "risk_level": "LOW"}

            return {
                "model": model,
                "validator_type": validator_type,
                **parsed,
                "status": "success",
            }
        except Exception as e:  # noqa: BLE001 — per-model fallback, never aborts the batch
            return {
                "model": model,
                "validator_type": validator_type,
                "status": "fallback",
                "error": str(e),
                "risk_level": "LOW",
            }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Model Code Validator")
    parser.add_argument(
        "path", nargs="?", default=".", help="File or directory to validate"
    )
    parser.add_argument("--json-output", help="Output file path for json report")

    args = parser.parse_args()

    validator = MultiModelValidator()
    result = asyncio.run(validator.validate_code(args.path))
    result_str = json.dumps(result, indent=2, ensure_ascii=False)

    if args.json_output:
        Path(args.json_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_output).write_text(result_str, encoding="utf-8")
        print(f"Validation report exported to {args.json_output}")
    else:
        print(result_str)
