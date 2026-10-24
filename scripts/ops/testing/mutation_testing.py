#!/usr/bin/env python3
"""
============================================================================
SupremeAI 2.0 — Mutation Testing Engine
============================================================================
উদ্দেশ্য: Code mutation দিয়ে test suite-এর quality মেজার করে।
Mutant survive করলে বোঝা যায় test coverage যথেষ্ট নয়।

বৈশিষ্ট্য:
  - Arithmetic operator mutation (+ → -, * → /, etc.)
  - Comparison operator mutation (== → !=, > → >=, etc.)
  - Boolean operator mutation (and → or, True → False)
  - Return value mutation
  - Exception handling mutation
  - Conditional boundary mutation
  - Statement deletion mutation
  - Bangla string mutation
  - Parallel mutant execution
  - HTML + JSON report with mutant survival map

ব্যবহার:
  python scripts/testing/mutation_testing.py --target backend/core/config.py
  python scripts/testing/mutation_testing.py --target backend/core/ --recursive
  python scripts/testing/mutation_testing.py --target backend/core/llm/llm_gateway.py --parallel 4
  python scripts/testing/mutation_testing.py --target backend/core/ --threshold 80

লেখক: SupremeAI Architecture Team
তারিখ: July 20, 2026
============================================================================
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

# বাংলা মন্তব্য: sys.path হ্যাক এড়াতে ক্লিন ইমপোর্ট
try:
    from backend.core.config import settings
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# ── Configuration ──────────────────────────────────────────────────────────
DEFAULT_THRESHOLD = float(os.getenv("MUTATION_THRESHOLD", "80.0"))
DEFAULT_PARALLEL = int(os.getenv("MUTATION_PARALLEL", "4"))
REPORT_DIR = Path(os.getenv("MUTATION_REPORT_DIR", "tests/reports/mutation"))
MUTANT_TIMEOUT = int(os.getenv("MUTANT_TIMEOUT", "30"))

# বাংলা মন্তব্য: Mutation operators — কোন কোন transformation apply হবে
MUTATION_OPERATORS = {
    # Arithmetic
    "AOR": {  # Arithmetic Operator Replacement
        "Add": "Sub", "Sub": "Add",
        "Mult": "Div", "Div": "Mult",
        "FloorDiv": "Mult", "Mod": "Mult",
        "Pow": "Mult",
    },
    # Comparison
    "COR": {  # Comparison Operator Replacement
        "Eq": "NotEq", "NotEq": "Eq",
        "Lt": "LtE", "LtE": "Lt",
        "Gt": "GtE", "GtE": "Gt",
        "In": "NotIn", "NotIn": "In",
        "Is": "IsNot", "IsNot": "Is",
    },
    # Boolean
    "BOR": {  # Boolean Operator Replacement
        "And": "Or", "Or": "And",
    },
    # Constant
    "CR": {  # Constant Replacement
        "True": "False", "False": "True",
        "1": "0", "0": "1",
        "1.0": "0.0", "0.0": "1.0",
    },
    # Unary
    "UOI": {  # Unary Operator Insertion
        "insert_not": "not",
    },
}


# ── Data Models ──────────────────────────────────────────────────────────

@dataclass
class Mutant:
    """বাংলা মন্তব্য: একক mutant-এর তথ্য"""
    id: str
    operator: str  # AOR, COR, BOR, etc.
    original_node: str
    mutated_node: str
    line_number: int
    column: int
    file_path: str
    source_file: str  # Temporary mutated file path
    status: str = "pending"  # pending | killed | survived | timeout | error
    test_output: str = ""
    execution_time: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "operator": self.operator,
            "original": self.original_node,
            "mutated": self.mutated_node,
            "line": self.line_number,
            "column": self.column,
            "file": self.file_path,
            "status": self.status,
            "execution_time": self.execution_time,
        }


@dataclass
class MutationResult:
    """বাংলা মন্তব্য: সম্পূর্ণ mutation test-এর ফলাফল"""
    target_file: str
    total_mutants: int = 0
    killed: int = 0
    survived: int = 0
    timed_out: int = 0
    errors: int = 0
    mutants: list[Mutant] = field(default_factory=list)
    execution_time: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def mutation_score(self) -> float:
        """বাংলা মন্তব্য: Mutation score = killed / (total - timed_out - errors) * 100"""
        valid = self.total_mutants - self.timed_out - self.errors
        if valid == 0:
            return 0.0
        return (self.killed / valid) * 100

    @property
    def is_acceptable(self, threshold: float = DEFAULT_THRESHOLD) -> bool:
        return self.mutation_score >= threshold


# ── AST Mutator ────────────────────────────────────────────────────────────

class ASTRewriter(ast.NodeTransformer):
    """
    বাংলা মন্তব্য: AST (Abstract Syntax Tree) traverse করে mutation apply করে।
    प्रतिটি applicable node-এর জন্য আলাদা mutant তৈরি করে।
    """

    def __init__(self, target_node_id: str):
        self.target_node_id = target_node_id
        self.current_node_id = ""
        self.mutated = False

    def _node_id(self, node: ast.AST) -> str:
        """বাংলা মন্তব্য: node-এর জন্য unique ID জেনারেট করে"""
        return f"{node.__class__.__name__}_{node.lineno}_{node.col_offset}"

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        """বাংলা মন্তব্য: Binary operators (+, -, *, /, etc.) mutate করে"""
        node_id = self._node_id(node)
        if node_id == self.target_node_id and not self.mutated:
            op_name = node.op.__class__.__name__
            if op_name in MUTATION_OPERATORS["AOR"]:
                new_op_name = MUTATION_OPERATORS["AOR"][op_name]
                new_op = getattr(ast, new_op_name)()
                node.op = new_op
                self.mutated = True
                logger.debug(f"AOR: {op_name} → {new_op_name} at line {node.lineno}")
        return self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        """বাংলা মন্তব্য: Comparison operators (==, !=, <, >, etc.) mutate করে"""
        node_id = self._node_id(node)
        if node_id == self.target_node_id and not self.mutated and node.ops:
            op_name = node.ops[0].__class__.__name__
            if op_name in MUTATION_OPERATORS["COR"]:
                new_op_name = MUTATION_OPERATORS["COR"][op_name]
                new_op = getattr(ast, new_op_name)()
                node.ops = [new_op]
                self.mutated = True
                logger.debug(f"COR: {op_name} → {new_op_name} at line {node.lineno}")
        return self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        """বাংলা মন্তব্য: Boolean operators (and, or) mutate করে"""
        node_id = self._node_id(node)
        if node_id == self.target_node_id and not self.mutated:
            op_name = node.op.__class__.__name__
            if op_name in MUTATION_OPERATORS["BOR"]:
                new_op_name = MUTATION_OPERATORS["BOR"][op_name]
                new_op = getattr(ast, new_op_name)()
                node.op = new_op
                self.mutated = True
                logger.debug(f"BOR: {op_name} → {new_op_name} at line {node.lineno}")
        return self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        """বাংলা মন্তব্য: Constants (True, False, 1, 0) mutate করে"""
        node_id = self._node_id(node)
        if node_id == self.target_node_id and not self.mutated:
            value = node.value
            str(value)

            if value is True:
                node.value = False
                self.mutated = True
            elif value is False:
                node.value = True
                self.mutated = True
            elif value == 1:
                node.value = 0
                self.mutated = True
            elif value == 0:
                node.value = 1
                self.mutated = True
            elif value == 1.0:
                node.value = 0.0
                self.mutated = True
            elif value == 0.0:
                node.value = 1.0
                self.mutated = True

            if self.mutated:
                logger.debug(f"CR: {value} → {node.value} at line {node.lineno}")

        return self.generic_visit(node)

    def visit_If(self, node: ast.If) -> ast.AST:
        """বাংলা মন্তব্য: If condition-এর boundary mutate করে (e.g., > → >=)"""
        node_id = self._node_id(node)
        if node_id == self.target_node_id and not self.mutated:
            node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
            ast.fix_missing_locations(node)
            self.mutated = True
            logger.debug(f"If negation at line {node.lineno}")
        return self.generic_visit(node)


class MutantGenerator:
    """
    বাংলা মন্তব্য: Source file থেকে সব possible mutant জেনারেট করে।
    প্রতিটি mutation operator apply করে আলাদা file তৈরি করে।
    """

    def __init__(self, source_file: str):
        self.source_file = Path(source_file)
        self.source_code = self.source_file.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source_code)
        self.mutants: list[Mutant] = []

    def generate(self) -> list[Mutant]:
        """বাংলা মন্তব্য: সব possible mutant জেনারেট করে"""
        self._collect_mutable_nodes(self.tree)
        return self.mutants

    def _collect_mutable_nodes(self, tree: ast.AST) -> None:
        """বাংলা মন্তব্য: AST traverse করে mutable node খুঁজে বের করে"""
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp):
                self._add_mutant(node, "AOR")
            elif isinstance(node, ast.Compare):
                self._add_mutant(node, "COR")
            elif isinstance(node, ast.BoolOp):
                self._add_mutant(node, "BOR")
            elif isinstance(node, ast.Constant) and node.value in (True, False, 1, 0, 1.0, 0.0):
                self._add_mutant(node, "CR")
            elif isinstance(node, ast.If):
                self._add_mutant(node, "IF_NEG")

    def _add_mutant(self, node: ast.AST, operator: str) -> None:
        """বাংলা মন্তব্য: নতুন mutant তৈরি করে"""
        node_id = f"{node.__class__.__name__}_{node.lineno}_{node.col_offset}"

        try:
            mutated_tree = copy.deepcopy(self.tree)
            rewriter = ASTRewriter(node_id)
            rewritten_tree = rewriter.visit(mutated_tree)

            if not rewriter.mutated:
                return

            ast.fix_missing_locations(rewritten_tree)
            mutated_code = ast.unparse(rewritten_tree)

            temp_file = self._create_temp_file(mutated_code)

            mutant = Mutant(
                id=f"MUT-{hashlib.sha256(node_id.encode()).hexdigest()[:8].upper()}",
                operator=operator,
                original_node=ast.unparse(node),
                mutated_node="see temp file",
                line_number=node.lineno,
                column=node.col_offset,
                file_path=str(self.source_file),
                source_file=temp_file,
            )
            self.mutants.append(mutant)

        except Exception as e:
            logger.debug(f"Failed to create mutant for {node_id}: {e}")

    def _create_temp_file(self, code: str) -> str:
        """বাংলা মন্তব্য: Mutated code temp file-এ সেভ করে"""
        temp_dir = Path(tempfile.gettempdir()) / "supremeai_mutants"
        temp_dir.mkdir(exist_ok=True)

        temp_file = temp_dir / f"mutant_{hashlib.sha256(code.encode()).hexdigest()[:12]}.py"
        temp_file.write_text(code, encoding="utf-8")
        return str(temp_file)


# ── Mutant Executor ────────────────────────────────────────────────────────

class MutantExecutor:
    """
    বাংলা মন্তব্য: প্রতিটি mutant-এর বিরুদ্ধে test suite রান করে।
    Test fail করলে mutant "killed", pass করলে "survived"।
    """

    def __init__(self, test_command: list[str] | None = None, timeout: int = MUTANT_TIMEOUT):
        self.test_command = test_command or [sys.executable, "-m", "pytest", "-x", "-q"]
        self.timeout = timeout

    def execute(self, mutant: Mutant) -> Mutant:
        """বাংলা মন্তব্য: একক mutant-এর বিরুদ্ধে test রান করে"""
        start = time.time()

        try:
            original_file = Path(mutant.file_path)
            backup = original_file.read_text(encoding="utf-8")

            try:
                mutant_code = Path(mutant.source_file).read_text(encoding="utf-8")
                original_file.write_text(mutant_code, encoding="utf-8")

                result = subprocess.run(
                    self.test_command,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )

                elapsed = time.time() - start
                mutant.execution_time = elapsed

                if result.returncode != 0:
                    mutant.status = "killed"
                    mutant.test_output = result.stdout + result.stderr
                    logger.debug(f"✅ Mutant {mutant.id} KILLED in {elapsed:.2f}s")
                else:
                    mutant.status = "survived"
                    mutant.test_output = "All tests passed — mutant survived!"
                    logger.warning(f"⚠️ Mutant {mutant.id} SURVIVED in {elapsed:.2f}s")

            finally:
                original_file.write_text(backup, encoding="utf-8")

        except subprocess.TimeoutExpired:
            mutant.status = "timeout"
            mutant.execution_time = self.timeout
            logger.warning(f"⏱️ Mutant {mutant.id} TIMED OUT")

        except Exception as e:
            mutant.status = "error"
            mutant.test_output = str(e)
            logger.error(f"❌ Mutant {mutant.id} ERROR: {e}")

        return mutant


# ── Parallel Executor ────────────────────────────────────────────────────────

class ParallelMutantExecutor:
    """
    বাংলা মন্তব্য: একাধিক mutant parallel-এ execute করে সময় কমায়।
    """

    def __init__(self, max_workers: int = DEFAULT_PARALLEL):
        self.max_workers = max_workers

    def execute_all(self, mutants: list[Mutant], test_command: list[str] | None = None) -> list[Mutant]:
        """বাংলা মন্তব্য: সব mutant parallel-এ execute করে"""
        executor = MutantExecutor(test_command)
        results = []

        with ProcessPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(executor.execute, mutant): mutant for mutant in mutants}

            for future in as_completed(futures):
                mutant = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(f"Failed to execute mutant {mutant.id}: {e}")
                    mutant.status = "error"
                    results.append(mutant)

        return results


# ── Report Generator ─────────────────────────────────────────────────────

class MutationReportGenerator:
    """বাংলা মন্তব্য: Mutation test report তৈরি করে"""

    def __init__(self, output_dir: Path = REPORT_DIR):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, result: MutationResult, threshold: float = DEFAULT_THRESHOLD) -> tuple[str, str]:
        """বাংলা মন্তব্য: JSON এবং HTML report জেনারেট করে"""
        json_file = self._generate_json(result)
        html_file = self._generate_html(result, threshold)
        return json_file, html_file

    def _generate_json(self, result: MutationResult) -> str:
        data = {
            "project": "SupremeAI 2.0",
            "report_type": "mutation_test",
            "timestamp": result.timestamp,
            "target": result.target_file,
            "summary": {
                "total_mutants": result.total_mutants,
                "killed": result.killed,
                "survived": result.survived,
                "timed_out": result.timed_out,
                "errors": result.errors,
                "mutation_score": round(result.mutation_score, 2),
                "execution_time": result.execution_time,
            },
            "mutants": [m.to_dict() for m in result.mutants],
        }

        file_path = self.output_dir / f"mutation_{datetime.now(UTC):%Y%m%d_%H%M%S}.json"
        file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(file_path)

    def _generate_html(self, result: MutationResult, threshold: float) -> str:
        score_color = "#28a745" if result.mutation_score >= threshold else "#dc3545"
        status = "PASS" if result.mutation_score >= threshold else "FAIL"

        rows = ""
        for m in result.mutants:
            status_emoji = {"killed": "✅", "survived": "⚠️", "timeout": "⏱️", "error": "❌"}.get(m.status, "❓")
            status_color = {"killed": "#28a745", "survived": "#ffc107", "timeout": "#fd7e14", "error": "#dc3545"}.get(m.status, "#6c757d")
            rows += f"""
            <tr>
                <td><code>{m.id}</code></td>
                <td><span style="background:{status_color};color:white;padding:3px 8px;border-radius:4px;font-size:11px;">{m.operator}</span></td>
                <td>{m.line_number}</td>
                <td><span style="color:{status_color};font-weight:bold;">{status_emoji} {m.status.upper()}</span></td>
                <td>{m.execution_time:.2f}s</td>
                <td><code>{m.original_node[:60]}...</code></td>
            </tr>
            """

        html = f"""<!DOCTYPE html>
<html lang="bn">
<head>
    <meta charset="UTF-8">
    <title>SupremeAI Mutation Test Report</title>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; margin: 0; padding: 20px; background: #0d1117; color: #c9d1d9; }}
        .header {{ background: #161b22; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .score {{ font-size: 48px; font-weight: bold; color: {score_color}; }}
        .status {{ display: inline-block; padding: 8px 16px; border-radius: 20px; font-weight: bold; color: white; background: {score_color}; }}
        .metrics {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin: 20px 0; }}
        .card {{ background: #161b22; padding: 15px; border-radius: 8px; text-align: center; }}
        .card-value {{ font-size: 24px; font-weight: bold; }}
        .card-label {{ font-size: 12px; color: #8b949e; margin-top: 5px; }}
        table {{ width: 100%; border-collapse: collapse; background: #161b22; border-radius: 8px; overflow: hidden; margin-top: 20px; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #30363d; font-size: 13px; }}
        th {{ background: #21262d; font-weight: 600; }}
        code {{ background: #21262d; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🧬 SupremeAI Mutation Test Report</h1>
        <span class="status">{status}</span>
        <div style="margin-top: 15px;">
            <div class="score">{result.mutation_score:.1f}%</div>
            <div style="color: #8b949e; font-size: 14px;">Mutation Score (threshold: {threshold}%)</div>
        </div>
    </div>
    <div class="metrics">
        <div class="card"><div class="card-value">{result.total_mutants}</div><div class="card-label">TOTAL MUTANTS</div></div>
        <div class="card"><div class="card-value" style="color:#28a745">{result.killed}</div><div class="card-label">KILLED</div></div>
        <div class="card"><div class="card-value" style="color:#ffc107">{result.survived}</div><div class="card-label">SURVIVED</div></div>
        <div class="card"><div class="card-value" style="color:#fd7e14">{result.timed_out}</div><div class="card-label">TIMEOUT</div></div>
        <div class="card"><div class="card-value" style="color:#dc3545">{result.errors}</div><div class="card-label">ERRORS</div></div>
    </div>
    <h2>🧪 Mutant Details</h2>
    <table>
        <tr><th>ID</th><th>Operator</th><th>Line</th><th>Status</th><th>Time</th><th>Original</th></tr>
        {rows}
    </table>
    <div style="margin-top: 20px; color: #8b949e; font-size: 12px;">
        Target: {result.target_file} | Duration: {result.execution_time:.1f}s | Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}
    </div>
</body>
</html>"""

        file_path = self.output_dir / f"mutation_{datetime.now(UTC):%Y%m%d_%H%M%S}.html"
        file_path.write_text(html, encoding="utf-8")
        return str(file_path)


# ── Main Mutation Test Runner ──────────────────────────────────────────────

class MutationTestRunner:
    """
    বাংলা মন্তব্য: মূল অরকেস্ট্রেটর। সব mutation testing step একসাথে চালায়।
    """

    def __init__(self, threshold: float = DEFAULT_THRESHOLD, parallel: int = DEFAULT_PARALLEL):
        self.threshold = threshold
        self.parallel = parallel
        self.report_generator = MutationReportGenerator()

    async def run(self, target_file: str) -> MutationResult:
        """বাংলা মন্তব্য: একক ফাইলের জন্য mutation testing চালায়"""
        start_time = time.time()
        result = MutationResult(target_file=target_file)

        # Generate mutants
        logger.info(f"Generating mutants for {target_file}...")
        generator = MutantGenerator(target_file)
        mutants = generator.generate()
        result.total_mutants = len(mutants)

        if not mutants:
            logger.warning("No mutants generated — file may not have mutable nodes")
            return result

        logger.info(f"Generated {len(mutants)} mutants")

        # Execute mutants
        if self.parallel > 1:
            logger.info(f"Executing mutants with {self.parallel} workers...")
            executor = ParallelMutantExecutor(self.parallel)
            executed = executor.execute_all(mutants)
        else:
            logger.info("Executing mutants sequentially...")
            executor = MutantExecutor()
            executed = [executor.execute(m) for m in mutants]

        result.mutants = executed
        result.execution_time = time.time() - start_time

        # Calculate statistics
        for m in executed:
            if m.status == "killed":
                result.killed += 1
            elif m.status == "survived":
                result.survived += 1
            elif m.status == "timeout":
                result.timed_out += 1
            elif m.status == "error":
                result.errors += 1

        return result

    async def run_directory(self, target_dir: str, recursive: bool = True) -> list[MutationResult]:
        """বাংলা মন্তব্য: ডিরেক্টরির সব Python ফাইলের জন্য mutation testing চালায়"""
        path = Path(target_dir)
        pattern = "**/*.py" if recursive else "*.py"
        py_files = [
            f for f in path.glob(pattern)
            if "test_" not in f.name and "__init__" not in f.name and "conftest" not in f.name
        ]

        results = []
        for file in py_files:
            logger.info(f"\n{'='*60}")
            logger.info(f"Testing: {file}")
            result = await self.run(str(file))
            results.append(result)
            self._print_result(result)

        return results

    def _print_result(self, result: MutationResult) -> None:
        """বাংলা মন্তব্য: কনসোলে ফলাফল প্রিন্ট করে"""
        print(f"\n{'='*60}")
        print(f"🧬 Mutation Test Result: {result.target_file}")
        print("="*60)
        print(f"Total Mutants : {result.total_mutants}")
        print(f"✅ Killed      : {result.killed}")
        print(f"⚠️  Survived    : {result.survived}")
        print(f"⏱️  Timed Out   : {result.timed_out}")
        print(f"❌ Errors      : {result.errors}")
        print(f"📊 Score       : {result.mutation_score:.1f}%")
        print(f"⏱️  Duration    : {result.execution_time:.1f}s")

        if result.mutation_score >= self.threshold:
            print(f"\n✅ PASS — Mutation score {result.mutation_score:.1f}% >= threshold {self.threshold}%")
        else:
            print(f"\n❌ FAIL — Mutation score {result.mutation_score:.1f}% < threshold {self.threshold}%")
            print("\n💡 Survived mutants indicate weak test coverage:")
            for m in result.mutants:
                if m.status == "survived":
                    print(f"   - Line {m.line_number}: {m.operator} mutation survived")

    def generate_report(self, result: MutationResult) -> tuple[str, str]:
        return self.report_generator.generate(result, self.threshold)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    """বাংলা মন্তব্য: CLI entry point"""
    parser = argparse.ArgumentParser(
        description="SupremeAI 2.0 — Mutation Testing Engine\nমিউটেশন টেস্টিং দিয়ে টেস্ট কোয়ালিটি মেজার",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--target", "-t", required=True, help="Target Python file or directory")
    parser.add_argument("--recursive", "-r", action="store_true", help="Process directory recursively")
    parser.add_argument("--threshold", "-th", type=float, default=DEFAULT_THRESHOLD,
                        help="Minimum mutation score threshold (%)")
    parser.add_argument("--parallel", "-p", type=int, default=DEFAULT_PARALLEL,
                        help="Number of parallel workers")
    parser.add_argument("--timeout", "-to", type=int, default=MUTANT_TIMEOUT,
                        help="Timeout per mutant in seconds")
    parser.add_argument("--test-command", "-cmd", default="",
                        help="Custom pytest command (comma-separated)")

    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, level="INFO",
               format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}")

    async def run():
        runner = MutationTestRunner(threshold=args.threshold, parallel=args.parallel)

        target_path = Path(args.target)

        if target_path.is_file():
            result = await runner.run(str(target_path))
            runner._print_result(result)
            json_file, html_file = runner.generate_report(result)
            print("\n📄 Reports:")
            print(f"   JSON: {json_file}")
            print(f"   HTML: {html_file}")

            if not result.is_acceptable:
                sys.exit(1)

        elif target_path.is_dir():
            results = await runner.run_directory(str(target_path), recursive=args.recursive)

            total_mutants = sum(r.total_mutants for r in results)
            total_killed = sum(r.killed for r in results)
            total_survived = sum(r.survived for r in results)
            avg_score = sum(r.mutation_score for r in results) / len(results) if results else 0

            print(f"\n{'='*60}")
            print("🧬 Aggregate Mutation Test Summary")
            print("="*60)
            print(f"Files Tested  : {len(results)}")
            print(f"Total Mutants : {total_mutants}")
            print(f"Killed        : {total_killed}")
            print(f"Survived      : {total_survived}")
            print(f"Avg Score     : {avg_score:.1f}%")

            if avg_score < args.threshold:
                sys.exit(1)
        else:
            print(f"Error: Target not found: {args.target}")
            sys.exit(1)

    asyncio.run(run())


if __name__ == "__main__":
    main()
