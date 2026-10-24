import ast
import json
import os
import subprocess
import tempfile
import time
from typing import Any

from core.errors.error_bus import with_error_bus
from core.logging_config import logger


class CodeSmellDetector:
    """
    Static analysis tool to detect cyclomatic complexity, code duplication, and other smells.
    Closes Gap #23
    """

    def __init__(self):
        self.radon_available = self._check_radon()
        self.pylint_available = self._check_pylint()
        logger.info(
            f"CodeSmellDetector initialized (radon={self.radon_available}, pylint={self.pylint_available})"
        )

    def _check_radon(self) -> bool:
        try:
            import radon.complexity  # noqa: F401 -- শুধু availability probe

            return True
        except ImportError:
            return False

    def _check_pylint(self) -> bool:
        try:
            subprocess.run(["pylint", "--version"], capture_output=True, check=False)
            return True
        except FileNotFoundError:
            return False

    def _calculate_complexity(self, node: ast.AST) -> int:
        complexity = 1
        for child in ast.walk(node):
            if isinstance(
                child,
                ast.If
                | ast.IfExp
                | ast.For
                | ast.While
                | ast.ExceptHandler
                | ast.With
                | ast.Assert
                | ast.BoolOp,
            ):
                complexity += 1
            if isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        return complexity

    def analyze_python_file(
        self, filepath: str, thresholds: dict[str, int] | None = None
    ) -> list[dict[str, Any]]:
        if not os.path.exists(filepath):
            return []

        t = thresholds or {}
        complexity_threshold = t.get("complexity", 10)
        args_threshold = t.get("args", 5)
        lines_threshold = t.get("lines", 50)
        class_methods_threshold = t.get("class_methods", 20)

        logger.info(f"Analyzing {filepath} for smells...")
        smells: list[dict[str, Any]] = []

        tree: ast.AST | None = None
        try:
            with open(filepath, encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    complexity = self._calculate_complexity(node)
                    if complexity > complexity_threshold:
                        smells.append(
                            {
                                "type": "High Cyclomatic Complexity",
                                "line": node.lineno,
                                "end_line": getattr(node, "end_lineno", node.lineno),
                                "function": node.name,
                                "complexity": complexity,
                                "threshold": complexity_threshold,
                                "message": (
                                    f"Cyclomatic complexity is {complexity} (threshold: {complexity_threshold}). "
                                    "Consider extracting helper functions."
                                ),
                                "severity": "warning",
                            }
                        )

                    if len(node.args.args) > args_threshold:
                        smells.append(
                            {
                                "type": "Too Many Arguments",
                                "line": node.lineno,
                                "end_line": getattr(node, "end_lineno", node.lineno),
                                "function": node.name,
                                "count": len(node.args.args),
                                "threshold": args_threshold,
                                "message": f"Function takes {len(node.args.args)} arguments (threshold: {args_threshold}).",
                                "severity": "info",
                            }
                        )

                    start = node.lineno
                    end = getattr(node, "end_lineno", start)
                    src_lines = end - start + 1 if end >= start else 1
                    if src_lines > lines_threshold:
                        smells.append(
                            {
                                "type": "Long Method",
                                "line": start,
                                "end_line": end,
                                "function": node.name,
                                "lines": src_lines,
                                "threshold": lines_threshold,
                                "message": f"Method spans {src_lines} lines (threshold: {lines_threshold}).",
                                "severity": "info",
                            }
                        )

                    return_count = sum(
                        1 for child in ast.walk(node) if isinstance(child, ast.Return)
                    )
                    if return_count > 7:
                        smells.append(
                            {
                                "type": "Too Many Returns",
                                "line": node.lineno,
                                "end_line": getattr(node, "end_lineno", node.lineno),
                                "function": node.name,
                                "return_count": return_count,
                                "message": f"Function has {return_count} return statements. Consider using guard clauses.",
                                "severity": "info",
                            }
                        )

                if isinstance(node, ast.ClassDef):
                    methods = sum(
                        1
                        for child in ast.iter_child_nodes(node)
                        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
                    )
                    if methods > class_methods_threshold:
                        smells.append(
                            {
                                "type": "Large Class",
                                "line": node.lineno,
                                "end_line": getattr(node, "end_lineno", node.lineno),
                                "class": node.name,
                                "method_count": methods,
                                "threshold": class_methods_threshold,
                                "message": f"Class has {methods} methods (threshold: {class_methods_threshold}).",
                                "severity": "info",
                            }
                        )

            if tree is not None:
                smells.extend(self._detect_duplicate_functions(tree, filepath))
                smells.extend(self._detect_broad_exceptions(tree, filepath))

        except SyntaxError as e:
            smells.append(
                {
                    "type": "Syntax Error",
                    "line": e.lineno or 0,
                    "message": str(e.msg),
                    "severity": "critical",
                }
            )
        except (ValueError, TypeError, RecursionError) as e:
            logger.error(f"Failed to analyze {filepath}: {e}")

        if tree is None:
            return smells

        if self.radon_available:
            try:
                smells.extend(self._analyze_radon(filepath, tree, complexity_threshold))
            except (ValueError, SyntaxError) as e:
                logger.warning(f"Radon analysis failed for {filepath}: {e}")

            coupling = self.compute_coupling_metrics(tree, filepath)
            if coupling.get("unique_modules", 0) > 15:
                smells.append(
                    {
                        "type": "High Coupling",
                        "line": 1,
                        "message": (
                            f"Module imports {coupling['unique_modules']} unique packages "
                            f"(fan_out={coupling['fan_out']}). Consider facade/wrapper layers."
                        ),
                        "severity": "warning",
                        "coupling": coupling,
                    }
                )

        return smells

    def _detect_duplicate_functions(self, tree: ast.AST, filepath: str) -> list[dict[str, Any]]:
        smells: list[dict[str, Any]] = []
        bodies: dict[str, list[dict[str, Any]]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                src = "\n".join(ast.dump(stmt) for stmt in node.body)
                norm = self._normalize(src)
                bodies.setdefault(norm, []).append(
                    {
                        "name": node.name,
                        "line": node.lineno,
                        "end_line": getattr(node, "end_lineno", node.lineno),
                    }
                )
        for _norm, items in bodies.items():
            if len(items) > 1:
                smells.append(
                    {
                        "type": "Duplicate Code",
                        "line": items[0]["line"],
                        "end_line": items[0]["end_line"],
                        "function": items[0]["name"],
                        "instances": len(items),
                        "locations": [(i["name"], i["line"]) for i in items],
                        "message": f"Potential duplicate logic detected in {len(items)} locations.",
                        "severity": "warning",
                    }
                )
        return smells

    @with_error_bus("_detect_broad_exceptions")
    def _detect_broad_exceptions(self, tree: ast.AST, file_path: str) -> list[dict[str, Any]]:
        """Detects broad exception handlers like `except Exception:` or bare `except:`."""
        smells: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                smell_type = ""
                details = ""
                # Check for bare `except:`
                if node.type is None:
                    smell_type = "Bare Except"
                    details = "A bare `except:` clause can catch system-exiting exceptions and hide bugs. Be more specific."
                # Check for `except Exception:` or `except BaseException:`
                elif isinstance(node.type, ast.Name) and node.type.id in {
                    "Exception",
                    "BaseException",
                }:
                    smell_type = "Broad Exception"
                    details = f"Catching a broad exception '{node.type.id}' can hide unexpected errors. Catch a more specific exception."

                if smell_type:
                    smells.append(
                        {
                            "type": smell_type,
                            "line": node.lineno,
                            "message": details,
                            "severity": "warning",
                            "source": "ast",
                        }
                    )
        return smells

    def _normalize(self, dump: str) -> str:
        import re

        dump = re.sub(r"\s+", " ", dump)
        dump = re.sub(r"'([^']*)'", "'<str>'", dump)
        dump = re.sub(r"\d+", "0", dump)
        return dump

    def _analyze_radon(
        self, filepath: str, tree: ast.AST | None, threshold: int
    ) -> list[dict[str, Any]]:
        try:
            from radon.complexity import cc_visit
            from radon.metrics import mi_visit

            if tree is None:
                with open(filepath, encoding="utf-8") as f:
                    tree = ast.parse(f.read())
            results: list[dict[str, Any]] = []
            blocks = cc_visit(tree)
            for block in blocks:
                if block.complexity > threshold:
                    results.append(
                        {
                            "type": "High Complexity (radon)",
                            "line": block.lineno,
                            "end_line": block.endline,
                            "function": block.name,
                            "complexity": block.complexity,
                            "message": f"Radon complexity {block.complexity} (threshold: {threshold}).",
                            "severity": "warning",
                        }
                    )
            try:
                mi = mi_visit(tree, True)
                if mi < 50:
                    results.append(
                        {
                            "type": "Low Maintainability",
                            "line": 1,
                            "message": f"Maintainability index is {mi:.1f} (target: > 50).",
                            "severity": "warning",
                        }
                    )
            except (ValueError, SyntaxError, TypeError) as e:
                # সুনির্দিষ্ট ত্রুটি (Specific exception) ক্যাচ করা হলো, যাতে অপ্রত্যাশিত ত্রুটি লুকিয়ে না যায়
                logger.warning(
                    f"Radon maintainability index calculation failed for {filepath}: {e}"
                )
            return results
        except ImportError:
            return []
        except SyntaxError:
            return []

    def analyze_directory(
        self, directory_path: str, thresholds: dict[str, int] | None = None
    ) -> dict[str, list[dict[str, Any]]]:
        results: dict[str, list[dict[str, Any]]] = {}
        if not os.path.isdir(directory_path):
            return results
        for root, _, files in os.walk(directory_path):
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    smells = self.analyze_python_file(full_path, thresholds=thresholds)
                    if smells:
                        results[full_path] = smells
                elif file.endswith((".js", ".ts", ".jsx", ".tsx")):
                    full_path = os.path.join(root, file)
                    smells = self.analyze_js_ts_file(full_path, thresholds=thresholds)
                    if smells:
                        results[full_path] = smells
        if self.pylint_available:
            try:
                results.update(self._analyze_pylint_directory(directory_path))
            except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
                logger.warning(f"Pylint directory analysis failed: {e}")

        jscpd_report = self.run_jscpd(directory_path)
        if jscpd_report.get("status") == "success" and jscpd_report.get("duplicates"):
            results.setdefault("_jscpd_", []).append(jscpd_report)

        return results

    def analyze_js_ts_file(
        self, filepath: str, thresholds: dict[str, int] | None = None
    ) -> list[dict[str, Any]]:
        if not os.path.exists(filepath):
            return []
        smells: list[dict[str, Any]] = []
        try:
            with open(filepath, encoding="utf-8") as f:
                content = f.read()
                lines = content.splitlines()

            max_lines = thresholds.get("lines", 200) if thresholds else 200
            max_params = thresholds.get("args", 5) if thresholds else 5

            for i, line in enumerate(lines, start=1):
                stripped = line.strip()
                if len(stripped) > 200:
                    smells.append(
                        {
                            "type": "Long Line",
                            "line": i,
                            "message": f"Line length {len(stripped)} exceeds 200 characters.",
                            "severity": "info",
                        }
                    )

            func_count = 0
            long_funcs = 0
            big_param_funcs = 0
            current_func_lines = 0
            in_func = False
            brace_depth = 0
            for line in lines:
                stripped = line.strip()
                if ("function" in stripped or "=>" in stripped) and not in_func:
                    in_func = True
                    current_func_lines = 0
                    func_count += 1
                    if "(" in stripped:
                        params = stripped.split("(")[1].split(")")[0]
                        if len(
                            [p.strip() for p in params.split(",") if p.strip()]
                        ) > max_params and not stripped.startswith("//"):
                            big_param_funcs += 1
                if in_func:
                    current_func_lines += 1
                    if current_func_lines > max_lines:
                        long_funcs += 1
                        in_func = False
                    if stripped == "}" or (stripped == "});" and "{" not in stripped):
                        in_func = False
                        brace_depth = 0
                    else:
                        brace_depth += stripped.count("{") - stripped.count("}")
                        brace_depth = max(brace_depth, 0)
                        if brace_depth == 0 and stripped:
                            brace_depth = 0

            if long_funcs:
                smells.append(
                    {
                        "type": "Long Function",
                        "line": 1,
                        "message": f"{long_funcs} JS/TS functions exceed {max_lines} lines.",
                        "severity": "info",
                    }
                )
            if big_param_funcs:
                smells.append(
                    {
                        "type": "Too Many Parameters",
                        "line": 1,
                        "message": f"{big_param_funcs} functions exceed {max_params} parameters.",
                        "severity": "info",
                    }
                )

            if "eval(" in content or "Function(" in content:
                smells.append(
                    {
                        "type": "Dangerous Patterns",
                        "line": 1,
                        "message": "Use of eval() or Function() detected.",
                        "severity": "critical",
                    }
                )
        except OSError as e:
            logger.error(f"Failed to analyze JS/TS file {filepath}: {e}")
        return smells

    def _analyze_pylint_directory(self, directory_path: str) -> dict[str, list[dict[str, Any]]]:
        output: dict[str, list[dict[str, Any]]] = {}
        with tempfile.TemporaryDirectory() as tmpdir:
            rcfile = os.path.join(tmpdir, ".pylintrc")
            with open(rcfile, "w", encoding="utf-8") as f:
                f.write("[MASTER]\nload-plugins=\n")
            try:
                # Strict Path Traversal Whitelist Validation
                abs_dir = os.path.abspath(directory_path)
                base_dir = os.path.abspath(os.getcwd())
                if not abs_dir.startswith(base_dir) or ".." in directory_path:
                    logger.error(
                        f"Security Alert: Path traversal attempt blocked for {directory_path}"
                    )
                    return output

                import shlex

                cmd = shlex.split(
                    f"pylint --output-format=json --rcfile={shlex.quote(rcfile)} {shlex.quote(directory_path)}"
                )
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
                import json

                for item in json.loads(proc.stdout or "[]"):
                    path = item.get("path")
                    if not path:
                        continue
                    output.setdefault(path, []).append(
                        {
                            "type": item.get("symbol") or item.get("message-id", "pylint"),
                            "line": item.get("line", 0),
                            "message": item.get("message", ""),
                            "severity": (
                                "warning"
                                if item.get("type") in ("convention", "refactor", "warning")
                                else "critical"
                            ),
                            "source": "pylint",
                        }
                    )
            except subprocess.TimeoutExpired:
                logger.warning("Pylint timed out")
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Pylint execution failed: {e}")
        return output

    def compute_coupling_metrics(self, tree: ast.AST, filepath: str) -> dict[str, Any]:
        """Compute fan-in/fan-out coupling metrics for a Python module."""
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module.split(".")[0])
        fan_out = len(imports)
        unique_modules = len(set(imports))
        return {
            "file": filepath,
            "fan_out": fan_out,
            "unique_modules": unique_modules,
            "imports": imports,
            "severity": "info",
        }

    def run_jscpd(self, directory_path: str) -> dict[str, Any]:
        """Run jscpd CLI to detect cross-file code duplication."""
        if not os.path.isdir(directory_path):
            return {"status": "skipped", "reason": "directory not found"}
        try:
            # Strict Path Traversal Whitelist Validation
            abs_dir = os.path.abspath(directory_path)
            base_dir = os.path.abspath(os.getcwd())
            if not abs_dir.startswith(base_dir) or ".." in directory_path:
                logger.error(f"Security Alert: Path traversal attempt blocked for {directory_path}")
                return {"status": "blocked", "reason": "Path traversal detected"}

            import shlex

            cmd = shlex.split(
                f"jscpd {shlex.quote(directory_path)} --silent --format json --min-lines 5 --min-tokens 50"
            )
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            import json

            stdout = proc.stdout.strip()
            if not stdout:
                return {"status": "success", "duplicates": []}
            data = json.loads(stdout) if stdout.startswith("{") else {}
            return {
                "status": "success",
                "duplicates": data.get("duplicates", []),
                "statistics": data.get("statistics", {}),
            }
        except FileNotFoundError:
            logger.debug("jscpd not installed; skipping cross-file duplication check")
            return {"status": "skipped", "reason": "jscpd not found"}
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            logger.warning(f"jscpd execution failed: {exc}")
            return {"status": "error", "reason": str(exc)}

    # ------------------------------------------------------------------ #
    # CI/CD Integration, SARIF, Pre-commit, History Tracking
    # ------------------------------------------------------------------ #
    def generate_sarif(
        self,
        results: dict[str, list[dict[str, Any]]],
        repo_uri: str = "file:///supremeai",
    ) -> dict[str, Any]:
        """
        GitHub Security tab-এ দেখানোর জন্য SARIF রিপোর্ট জেনারেট করে।

        results: analyze_directory()-এর আউটপুট (path -> list of smells)
        """
        rules: dict[str, Any] = {}
        sarif_results: list[dict[str, Any]] = []

        severity_map = {
            "critical": "error",
            "high": "error",
            "warning": "warning",
            "info": "note",
        }

        for filepath, smells in results.items():
            if filepath.startswith("_"):
                continue
            for smell in smells:
                rule_id = smell.get("type", "UnknownSmell")
                if rule_id not in rules:
                    rules[rule_id] = {
                        "id": rule_id,
                        "shortDescription": {"text": smell.get("message", rule_id)},
                        "helpUri": "https://supremeai.dev/docs/code-smells",
                    }
                sarif_results.append(
                    {
                        "ruleId": rule_id,
                        "level": severity_map.get(smell.get("severity", "info"), "note"),
                        "message": {"text": smell.get("message", "")},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": filepath},
                                    "region": {
                                        "startLine": smell.get("line", 1),
                                        "endLine": smell.get("end_line", smell.get("line", 1)),
                                    },
                                }
                            }
                        ],
                    }
                )

        return {
            "version": "2.1.0",
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "SupremeAICodeSmellDetector",
                            "version": "2.0.0",
                            "informationUri": repo_uri,
                            "rules": list(rules.values()),
                        }
                    },
                    "results": sarif_results,
                }
            ],
        }

    def install_pre_commit_hook(self, repo_path: str = ".") -> bool:
        """প্রি-কমিট হুক ইনস্টল করে যাতে কমিটের আগে স্মেল চেক হয়।"""
        hook_path = os.path.join(repo_path, ".git", "hooks", "pre-commit")
        if not os.path.isdir(os.path.join(repo_path, ".git")):
            logger.warning(f"No git repo found at {repo_path}; skipping pre-commit hook install.")
            return False
        try:
            os.makedirs(os.path.dirname(hook_path), exist_ok=True)
            with open(hook_path, "w", encoding="utf-8") as f:
                f.write(
                    "#!/bin/sh\n# বাংলা মন্তব্য: SupremeAI কোড স্মেল প্রি-কমিট হুক।\npython -m tools.code_smell_detector --check || true\n"
                )
            os.chmod(hook_path, 0o755)  # noqa: S103 -- git pre-commit hook script, executable প্রয়োজন (standard hook permission)
            logger.success(f"Pre-commit hook installed at {hook_path}")
            return True
        except (OSError, TypeError) as e:
            logger.error(f"Failed to install pre-commit hook: {e}", exc_info=True)
            return False

    def track_history(
        self,
        results: dict[str, list[dict[str, Any]]],
        history_file: str = "data/code_smell_history.json",
    ) -> dict[str, Any]:
        """
        রিপোর্ট ইতিহাস ট্র্যাক করে (কোড কোয়ালিটি সময়ের সাথে ভালো হচ্ছে কিনা)।

        প্রতি রানে মোট স্মেল সংখ্যা সংরক্ষণ করে ট্রেন্ড তৈরি করে।
        """
        total_smells = sum(len(v) for k, v in results.items() if not k.startswith("_"))
        record: dict[str, Any] = {
            "timestamp": time.time(),
            "total_smells": total_smells,
            "files_affected": len(results),
        }

        history: list[dict[str, Any]] = []
        try:
            if os.path.exists(history_file):
                with open(history_file, encoding="utf-8") as f:
                    history = json.load(f)
        except (json.JSONDecodeError, OSError, TypeError) as e:
            logger.warning(f"History file read failed for {history_file}: {e}")
            history = []

        history.append(record)
        try:
            os.makedirs(os.path.dirname(history_file), exist_ok=True)
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(history[-100:], f, indent=2)
        except (OSError, TypeError) as e:
            logger.debug(f"History tracking write failed: {e}")

        # বাংলা মন্তব্য: ট্রেন্ড — আগের রানের চেয়ে কম স্মেল হলে উন্নতি।
        trend = (
            "improving"
            if len(history) >= 2 and history[-1]["total_smells"] <= history[-2]["total_smells"]
            else "worsening"
        )
        record["trend"] = trend
        return record
