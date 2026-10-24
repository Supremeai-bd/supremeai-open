"""
AutoTestGenerator — Real Implementation (Sprint G.3)
Generates pytest / Vitest / Flutter tests using ModelRouter.
Replaces old BanglaAiConnector pattern.
"""

from __future__ import annotations

import ast
import os
import pathlib
import subprocess
import sys
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from core.logging_config import logger
from core.upload_validator import validate_upload
from tools.learning.style_learner import StyleLearner

router = APIRouter(prefix="/test-gen", tags=["auto-test-generator"])


# ── Request/Response models ───────────────────────────────────────────────────


class TestGenRequest(BaseModel):
    __test__ = False

    source_code: str
    file_path: str = "unknown.py"
    stack: str | None = None  # python | typescript | dart | auto
    framework: str | None = None  # pytest | vitest | jest | flutter
    coverage_target: int = 80
    include_mocks: bool = True
    include_edge_cases: bool = True


class TestGenResponse(BaseModel):
    __test__ = False

    status: str
    file_path: str
    stack: str
    framework: str
    test_code: str
    test_file_path: str
    functions_found: int
    coverage_estimate: int
    error: str | None = None


# ── Language / framework detection ────────────────────────────────────────────


def _detect_stack(file_path: str, source_code: str) -> str:
    ext = pathlib.Path(file_path).suffix.lower()
    if ext in (".py",):
        return "python"
    if ext in (".ts", ".tsx"):
        return "typescript"
    if ext in (".js", ".jsx"):
        return "javascript"
    if ext in (".dart",):
        return "dart"
    if ext in (".java",):
        return "java"
    if ext in (".go",):
        return "go"
    if ext in (".rs",):
        return "rust"
    # Fallback: inspect source content
    if "import pytest" in source_code or "def test_" in source_code:
        return "python"
    if "describe(" in source_code or "it(" in source_code:
        return "typescript"
    return "python"


def _detect_framework(stack: str, framework: str | None) -> str:
    if framework:
        return framework
    return {
        "python": "pytest",
        "typescript": "vitest",
        "javascript": "jest",
        "dart": "flutter_test",
        "java": "junit5",
        "go": "testing",
        "rust": "cargo_test",
    }.get(stack, "pytest")


def _get_test_file_path(source_path: str, stack: str) -> str:
    p = pathlib.Path(source_path)
    if stack == "python":
        return str(p.parent / f"test_{p.stem}.py")
    if stack in ("typescript", "javascript"):
        return str(p.parent / f"{p.stem}.test{p.suffix}")
    if stack == "dart":
        return str(p.parent.parent / "test" / f"{p.stem}_test.dart")
    if stack == "java":
        return str(p).replace("src/main/java", "src/test/java").replace(".java", "Test.java")
    return str(p.parent / f"{p.stem}_test{p.suffix}")


# ── Python AST analysis ───────────────────────────────────────────────────────


def _extract_python_symbols(source_code: str) -> dict[str, list[str]]:
    """Extract classes, functions, and their signatures from Python source."""
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return {"functions": [], "classes": [], "async_functions": []}

    functions, classes, async_fns = [], [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            args = [a.arg for a in node.args.args]
            functions.append(f"{node.name}({', '.join(args)})")
        elif isinstance(node, ast.AsyncFunctionDef):
            args = [a.arg for a in node.args.args]
            async_fns.append(f"async {node.name}({', '.join(args)})")
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)

    return {"functions": functions, "classes": classes, "async_functions": async_fns}


# ── Prompt builders ───────────────────────────────────────────────────────────


def _build_prompt(
    source_code: str,
    file_path: str,
    stack: str,
    framework: str,
    coverage_target: int,
    include_mocks: bool,
    include_edge_cases: bool,
    symbols: dict | None = None,
    style_guidelines: str | None = None,
) -> str:
    symbol_hint = ""
    if symbols:
        all_fns = symbols.get("functions", []) + symbols.get("async_functions", [])
        classes = symbols.get("classes", [])
        if all_fns or classes:
            symbol_hint = f"\n\nDetected symbols:\nFunctions: {', '.join(all_fns[:15]) or 'none'}\nClasses: {', '.join(classes[:10]) or 'none'}"

    style_instruction = ""
    if style_guidelines:
        style_instruction = f"\n\nCODING STYLE:\n{style_guidelines}\n"

    mock_instruction = (
        "Use mocks/patches for external dependencies (database, HTTP, file I/O)."
        if include_mocks
        else "Do not add mocking — use real implementations."
    )
    edge_instruction = (
        "Include edge cases: empty inputs, None values, large inputs, concurrent calls."
        if include_edge_cases
        else "Focus on happy-path tests only."
    )

    framework_notes = {
        "pytest": (
            "Use pytest + pytest-asyncio. Mark async tests with @pytest.mark.asyncio.\n"
            "Use @pytest.fixture for reusable setup. Use monkeypatch/patch for mocks.\n"
            "Group tests in classes named Test<ClassName>."
        ),
        "vitest": (
            "Use Vitest + @testing-library/react if React components.\n"
            "Use vi.mock() for module mocks. Use describe/it/expect.\n"
            "Import from 'vitest': { describe, it, expect, vi, beforeEach }."
        ),
        "jest": (
            "Use Jest. Use jest.mock() for mocks. describe/it/expect pattern.\nUse beforeEach/afterEach for setup/teardown."
        ),
        "flutter_test": (
            "Use flutter_test package. Use testWidgets for widget tests.\nUse mockito or mocktail for mocking."
        ),
        "junit5": (
            "Use JUnit 5 with @Test, @ExtendWith(MockitoExtension.class).\nUse Mockito for mocks. Follow AAA pattern (Arrange/Act/Assert)."
        ),
    }.get(framework, f"Use {framework} testing conventions.")

    return f"""You are an expert software engineer. Generate a comprehensive test file for the following {stack} source code.

TARGET: {coverage_target}%+ code coverage
FILE: {file_path}
STACK: {stack.upper()}
FRAMEWORK: {framework.upper()}{symbol_hint}
{style_instruction}
FRAMEWORK RULES:
{framework_notes}

ADDITIONAL REQUIREMENTS:
- {mock_instruction}
- {edge_instruction}
- Test every public function/method
- Add descriptive test names (test_<function>_<scenario>)
- Include docstrings for complex tests
- Return ONLY the complete test file. No markdown, no explanation.

SOURCE CODE:
```{stack}
{source_code[:6000]}
```

Generate the complete test file now:"""


# ── Main class ────────────────────────────────────────────────────────────────


class AutoTestGenerator:
    def __init__(self, llm_client: Any | None = None):
        """
        Initializes the test generator.
        An optional llm_client can be injected for testing purposes.
        """
        self._llm_client = llm_client
        self.style_learner = StyleLearner()

    async def _llm(self, prompt: str) -> str:
        if self._llm_client:
            return await self._llm_client(prompt)

        try:
            from brain.model_router import ModelRouter

            r = ModelRouter()
            result = await r.async_route_and_generate(prompt, task_type="coding", max_cost=0.05)
            return result.get("text", "") if isinstance(result, dict) else str(result)  # type: ignore
        except Exception as exc:
            logger.error(f"LLM call failed: {exc}")
            return ""

    async def generate(
        self,
        source_code: str,
        file_path: str = "unknown.py",
        stack: str | None = None,
        framework: str | None = None,
        coverage_target: int = 80,
        include_mocks: bool = True,
        include_edge_cases: bool = True,
    ) -> dict[str, Any]:
        detected_stack = stack or _detect_stack(file_path, source_code)
        detected_framework = _detect_framework(detected_stack, framework)
        test_file = _get_test_file_path(file_path, detected_stack)

        # Extract symbols for better prompt context
        symbols = None
        if detected_stack == "python":
            symbols = _extract_python_symbols(source_code)

        # Get style guidelines
        # Assumes file_path is relative to a repo root that can be analyzed.
        repo_root_for_style = "."  # Use current directory as a proxy for the repo root.
        style_guidelines = self.style_learner.generate_style_prompt(
            repo_root_for_style, detected_stack
        )

        fn_count = (
            len(symbols.get("functions", []) + symbols.get("async_functions", [])) if symbols else 0
        )

        prompt = _build_prompt(
            source_code=source_code,
            file_path=file_path,
            stack=detected_stack,
            framework=detected_framework,
            coverage_target=coverage_target,
            include_mocks=include_mocks,
            include_edge_cases=include_edge_cases,
            symbols=symbols,
            style_guidelines=style_guidelines,
        )

        logger.info(
            f"Generating tests: {file_path} | stack={detected_stack} | framework={detected_framework}"
        )
        test_code = await self._llm(prompt)

        if not test_code:
            return {
                "status": "error",
                "file_path": file_path,
                "stack": detected_stack,
                "framework": detected_framework,
                "test_code": "",
                "test_file_path": test_file,
                "functions_found": fn_count,
                "coverage_estimate": 0,
                "error": "LLM returned empty response",
            }

        # Clean up code fences if present
        test_code = self._clean_code(test_code, detected_stack)

        # Coverage estimate (heuristic: 1 function → ~15 lines of tests → ~80% coverage)
        lines = len([line for line in test_code.splitlines() if line.strip()])
        coverage_estimate = min(95, max(40, lines * 2))

        return {
            "status": "success",
            "file_path": file_path,
            "stack": detected_stack,
            "framework": detected_framework,
            "test_code": test_code,
            "test_file_path": test_file,
            "functions_found": fn_count,
            "coverage_estimate": coverage_estimate,
        }

    def _clean_code(self, code: str, stack: str) -> str:
        lang_map = {
            "python": "python",
            "typescript": "typescript",
            "javascript": "javascript",
            "dart": "dart",
            "java": "java",
        }
        lang_map.get(stack, "")
        lines = code.splitlines()
        # Strip leading ```lang and trailing ```
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()

    async def generate_and_save(self, source_path: str, run_tests: bool = False) -> dict[str, Any]:
        """Read file, generate tests, save to disk, optionally run them."""
        if not os.path.exists(source_path):
            return {"status": "error", "error": f"File not found: {source_path}"}

        with open(source_path, encoding="utf-8") as f:
            source_code = f.read()

        result = await self.generate(source_code=source_code, file_path=source_path)
        if result["status"] != "success":
            return result

        test_file_path = result["test_file_path"]
        os.makedirs(os.path.dirname(os.path.abspath(test_file_path)), exist_ok=True)
        with open(test_file_path, "w", encoding="utf-8") as f:
            f.write(result["test_code"])
        logger.info(f"Saved test file: {test_file_path}")
        result["saved"] = True

        if run_tests and result["stack"] == "python":
            run_result = self._run_pytest(test_file_path)
            result["run_result"] = run_result

        return result

    def _run_pytest(self, test_file_path: str) -> dict[str, Any]:
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    test_file_path,
                    "-v",
                    "--tb=short",
                    "--timeout=30",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            return {
                "returncode": proc.returncode,
                "passed": proc.returncode == 0,
                "stdout": proc.stdout[-2000:],
                "stderr": proc.stderr[-500:],
            }
        except Exception as exc:
            return {"returncode": -1, "passed": False, "error": str(exc)}

    async def batch_generate(self, source_paths: list[str], save: bool = True) -> dict[str, Any]:
        """Generate tests for multiple files."""
        if len(source_paths) > 20:
            raise ValueError("Max 20 files per batch")
        results = []
        for path in source_paths:
            if save:
                r = await self.generate_and_save(path)
            else:
                code = (
                    pathlib.Path(path).read_text(encoding="utf-8") if os.path.exists(path) else ""
                )
                r = await self.generate(source_code=code, file_path=path)
            results.append({"path": path, **r})
        return {
            "status": "success",
            "total": len(source_paths),
            "generated": sum(1 for r in results if r.get("status") == "success"),
            "results": results,
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
_generator = AutoTestGenerator()


# ── REST Endpoints ────────────────────────────────────────────────────────────


@router.post("/generate", response_model=TestGenResponse)
async def generate_tests(request: TestGenRequest):
    """Generate unit tests for submitted source code."""
    if not request.source_code.strip():
        raise HTTPException(status_code=400, detail="source_code cannot be empty")
    result = await _generator.generate(
        source_code=request.source_code,
        file_path=request.file_path,
        stack=request.stack,
        framework=request.framework,
        coverage_target=request.coverage_target,
        include_mocks=request.include_mocks,
        include_edge_cases=request.include_edge_cases,
    )
    if result["status"] == "error":
        raise HTTPException(status_code=503, detail=result.get("error", "Generation failed"))
    return TestGenResponse(**result)


@router.post("/generate-file")
async def generate_from_file(file: UploadFile = File(...)):
    """Upload a source file and get back a test file."""
    await validate_upload(file)
    content = (await file.read()).decode("utf-8", errors="replace")
    result = await _generator.generate(
        source_code=content,
        file_path=file.filename or "uploaded.py",
    )
    if result["status"] == "error":
        raise HTTPException(status_code=503, detail=result.get("error", "Generation failed"))
    return result


@router.post("/batch")
async def batch_generate(paths: list[str]):
    """Generate tests for multiple source file paths (server-side paths)."""
    if len(paths) > 20:
        raise HTTPException(status_code=400, detail="Max 20 files per batch")
    return await _generator.batch_generate(paths, save=True)


@router.get("/supported-stacks")
async def supported_stacks():
    return {
        "stacks": ["python", "typescript", "javascript", "dart", "java", "go", "rust"],
        "frameworks": {
            "python": "pytest",
            "typescript": "vitest",
            "javascript": "jest",
            "dart": "flutter_test",
            "java": "junit5",
        },
        "features": ["mocks", "edge_cases", "async_support", "fixture_generation"],
    }
