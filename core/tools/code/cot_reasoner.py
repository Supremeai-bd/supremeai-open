from __future__ import annotations

import ast
import contextlib
import operator
import secrets

random = secrets.SystemRandom()
from typing import Any

from core.logging_config import logger

_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}


def _safe_eval_math(expression: str) -> float:
    tree = ast.parse(expression, mode="eval")
    return _eval_node(tree.body)


def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return _ALLOWED_OPERATORS[op_type](left, right)
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        operand = _eval_node(node.operand)
        return _ALLOWED_OPERATORS[op_type](operand)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, int | float):
            return node.value
        raise ValueError("Only numeric constants are allowed")
    raise ValueError(f"Unsupported expression node: {type(node).__name__}")


def safe_execute(code: str) -> dict[str, Any]:
    """Safely execute user‑provided Python code.

    Uses :pyfunc:`backend.tools.safe_executor.run_restricted` which relies on
    **RestrictedPython** to sandbox the execution environment. The function
    returns a dictionary compatible with the previous contract.
    """
    try:
        # ``run_restricted`` returns the locals dictionary after sandboxed exec.
        from tools.code.safe_executor import run_restricted

        local_vars = run_restricted(code)
        if "result" in local_vars:
            return {"success": True, "value": local_vars["result"]}  # type: ignore
        return {"success": True, "value": None}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def verify_symbolic_math(expression: str, claimed_result: str) -> dict[str, Any]:
    import re

    try:
        import sympy

        expr = sympy.sympify(expression)
        claimed = sympy.sympify(claimed_result)
        is_correct = sympy.simplify(expr - claimed) == 0
        if not is_correct:
            with contextlib.suppress(Exception):
                is_correct = abs(expr.evalf() - claimed.evalf()) < 1e-9
        return {
            "is_verified": bool(is_correct),
            "expression_sympy": str(expr),
            "claimed_result": str(claimed),
            "method": "sympy_symbolic",
        }
    except Exception as e:
        try:
            clean_expr = re.sub(r"[^0-9\+\-\*\/\(\)\.\s]", "", expression)
            result = _safe_eval_math(clean_expr)
            claimed = float(claimed_result.strip())
            is_correct = abs(result - claimed) < 1e-9
            return {
                "is_verified": is_correct,
                "numerical_result": result,
                "claimed_result": claimed,
                "method": "numerical_fallback",
            }
        except Exception as inner_e:
            return {
                "is_verified": False,
                "error": f"Sympy error: {e}, Fallback error: {inner_e}",
            }


class Thought:
    def __init__(
        self,
        content: str,
        reasoning_depth: int = 0,
        parent: Thought | None = None,
        score: float = 0.0,
    ):
        self.content = content
        self.reasoning_depth = reasoning_depth
        self.parent = parent
        self.children: list[Thought] = []
        self.score = score

    def add_child(self, content: str, score: float = 0.0) -> Thought:
        child = Thought(
            content=content,
            reasoning_depth=self.reasoning_depth + 1,
            parent=self,
            score=score,
        )
        self.children.append(child)
        return child

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "thought",
            "content": self.content,
            "reasoning_depth": self.reasoning_depth,
            "score": self.score,
            "children": [child.to_dict() for child in self.children],
        }


class ChainOfThoughtReasoner:
    def __init__(self, max_iterations: int = 3):
        self.max_iterations = max_iterations
        self._sympy_available = self._check_sympy()

    def _check_sympy(self) -> bool:
        import importlib.util

        return importlib.util.find_spec("sympy") is not None

    def build_prompt(self, problem: str, context: str | None = None) -> str:
        parts = [
            "You are a step-by-step reasoning engine. Carefully analyze the problem solving steps.",
            "For each step, wrap your chain-of-thought inside <thought>...</thought> tags.",
            "After finishing thinking, return the final answer only inside <answer>...</answer> tags with no extra explanation.",
            "",
            f"Problem: {problem}",
        ]
        if context:
            parts.extend(["", f"Context: {context}"])
        parts.extend(["", "Begin your thought process now:"])
        return "\n".join(parts)

    def parse(self, raw: str) -> dict[str, Any]:
        thoughts: list[str] = []
        answer = ""
        import re

        for tag in re.findall(r"<thought>(.*?)</thought>", raw, flags=re.DOTALL | re.IGNORECASE):
            thoughts.append(tag.strip())
        answer_match = re.search(r"<answer>(.*?)</answer>", raw, flags=re.DOTALL | re.IGNORECASE)
        if answer_match:
            answer = answer_match.group(1).strip()
        return {
            "thoughts": [Thought(t, idx).to_dict() for idx, t in enumerate(thoughts)],
            "final_answer": answer,
            "raw": raw,
        }

    def verify(self, answer: str, expected: str | None = None) -> dict[str, Any]:
        if expected is not None:
            math_matches = __import__("re").findall(
                r"(\d+[\+\-\*\/\(\)\d\s]+?)\s*=\s*(\S+)", answer
            )
            for expr, claimed in math_matches:
                mv = verify_symbolic_math(expr, claimed)
                if not mv.get("is_verified"):
                    return {"matches": False, "math_error": mv}
            return {
                "matches": answer.strip().lower() == expected.strip().lower(),
                "symbolic_verification": "passed",
            }
        return {"answer": answer}

    def symbolic_verify(self, expression: str, claimed: str) -> dict[str, Any]:
        return verify_symbolic_math(expression, claimed)

    def _verify_execution(self, thought_payload: dict[str, Any]) -> dict[str, Any]:
        raw_code = thought_payload.get("exec_code") or ""
        if not raw_code:
            return {"verified": True, "reason": "no_exec"}
        return safe_execute(raw_code)

    def evaluate_thought(self, thought: Thought, context: str | None = None) -> float:
        score = 0.5
        text = thought.content.lower()
        if any(word in text for word in ["therefore", "thus", "conclusion", "final answer"]):
            score += 0.2
        if any(word in text for word in ["however", "but", "although", "alternatively"]):
            score += 0.1
        if len(thought.content.split()) >= 8:
            score += 0.1
        if context and any(word in text for word in context.lower().split()):
            score += 0.1
        return min(score, 1.0)

    def tree_search(
        self,
        problem: str,
        branches: int = 3,
        depth: int = 2,
        context: str | None = None,
    ) -> dict[str, Any]:
        if depth == 0 or branches <= 0:
            return {"status": "ok", "best_branch": [], "best_score": 0.0}

        self.build_prompt(problem, context)
        raw = __import__("os").environ.get("COT_DEBUG_INPUT", "")
        if not raw:
            raw = f"<thought>Initial analysis of: {problem}</thought>"
        parsed = self.parse(raw)
        root_thoughts = parsed.get("thoughts", [])
        if not root_thoughts:
            return {"status": "ok", "best_branch": [], "best_score": 0.0}

        best_score = 0.0
        best_branch: list[str] = []
        for thought_obj in root_thoughts[:branches]:
            thought = Thought(content=thought_obj.get("content", ""), reasoning_depth=0)
            thought.score = self.evaluate_thought(thought, context)
            if thought.score > best_score:
                best_score = thought.score
                best_branch = [thought.content]
            if depth > 1:
                self.build_prompt(f"{thought.content}\nContinue reasoning.", context)
                ext_raw = (
                    f"<thought>{thought.content} - continued</thought><answer>{problem}</answer>"
                )
                ext_parsed = self.parse(ext_raw)
                ext_thoughts = ext_parsed.get("thoughts", [])
                if ext_thoughts:
                    ext = ext_thoughts[0]
                    child = thought.add_child(
                        ext, score=self.evaluate_thought(Thought(ext), context)
                    )
                    total_score = thought.score + child.score
                    if total_score > best_score:
                        best_score = total_score
                        best_branch = [thought.content, child.content]

        return {"status": "ok", "best_branch": best_branch, "best_score": best_score}

    def monte_carlo_search(
        self,
        problem: str,
        branches: int = 3,
        depth: int = 3,
        simulations: int = 8,
        context: str | None = None,
    ) -> dict[str, Any]:
        seed = self.tree_search(problem=problem, branches=branches, depth=2, context=context)
        seed_path = seed.get("best_branch") or []
        if not seed_path:
            return {
                "status": "ok",
                "best_path": [],
                "best_score": 0.0,
                "simulations": 0,
            }

        best_path = list(seed_path)
        best_score = float(seed.get("best_score") or 0.0)
        rollout_nodes = [
            "verify assumptions",
            "look for counterexamples",
            "compare alternatives",
            "validate final answer",
            "explain tradeoffs",
        ]

        for _ in range(simulations):
            path = list(seed_path)
            score = float(seed.get("best_score") or 0.0)
            for _depth_idx in range(max(0, depth - len(path))):
                node_text = path[-1] if path else problem
                expansion = random.choice(rollout_nodes)
                thought = Thought(
                    content=f"{node_text}; {expansion} for {problem}",
                    reasoning_depth=len(path),
                    score=self.evaluate_thought(
                        Thought(
                            content=f"{node_text}; {expansion} for {problem}",
                            reasoning_depth=len(path),
                        ),
                        context,
                    ),
                )
                path.append(thought.content)
                score += thought.score + random.uniform(0.0, 0.1)
            if score > best_score:
                best_score = score
                best_path = path

        return {
            "status": "ok",
            "best_path": best_path,
            "best_score": round(best_score, 4),
            "simulations": simulations,
        }

    def refine_loop(
        self, problem: str, context: str | None = None, expected: str | None = None
    ) -> dict[str, Any]:
        last_output: dict[str, Any] = {"thoughts": [], "exec_results": []}
        for iteration in range(self.max_iterations):
            prompt = self.build_prompt(problem, context)
            logger.info(f"CoT iteration {iteration} initiated")
            last_output["iter"] = iteration
            last_output["prompt_used"] = prompt
            if "answer" in last_output:
                exec_result = self._verify_execution({"exec_code": str(last_output.get("answer"))})
                last_output["exec_results"].append(exec_result)
        return {
            "status": "ok",
            "iterations": self.max_iterations,
            "thoughts": last_output.get("thoughts", []),
            "final_answer": last_output.get("answer", ""),
            "last_output": last_output,
        }


class DeepReasoningChain:
    def __init__(self, max_iterations: int = 3) -> None:
        self.max_iterations = max_iterations

    def multi_step_think(self, problem: str, steps: int = 5) -> str:
        prompt = (
            "Perform step-by-step reasoning. For each step, number it explicitly "
            "and derive only from prior steps. Use the following format:\n"
            f"Step 1: ...\nStep 2: ...\n...\nFinal Answer: ...\n\nProblem: {problem}"
        )
        return prompt

    def self_critique(self, solution: str) -> str:
        prompt = (
            "Review the following solution for logical gaps, unsupported claims, or errors. "
            "Return one concise paragraph of critique.\n\nSolution:\n" + solution
        )
        return prompt

    def iterative_refinement(self, answer: str, iterations: int = 3) -> str:
        current = answer
        for _i in range(iterations):
            critique = self.self_critique(current)
            refined_prompt = (
                "Given the critique, refine the previous answer. "
                "Keep reasoning concise.\n\nCurrent Answer:\n"
                + current
                + "\n\nCritique:\n"
                + critique
            )
            current = refined_prompt
        return current
