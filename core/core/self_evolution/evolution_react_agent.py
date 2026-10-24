"""
Module for the `EvolutionReActAgent`, which autonomously generates and refines Python skill scripts.

It employs a ReAct (Reason + Act) and Reflexion loop, leveraging a large language model (LLM)
to iteratively reason, generate code, and self-correct based on compilation errors or previous failures.
This agent is central to the SupremeAI's capability for automatic skill evolution.
"""

# Evolution ReAct Agent for SupremeAI 2.0
# বাংলা মন্তব্য: এটি স্বয়ংক্রিয়ভাবে নতুন স্কিল তৈরির জন্য ReAct (Reason + Act) এবং Reflexion লুপ পরিচালনা করে।

from typing import Any

from brain.model_router import ModelRouter
from core.logging_config import logger


class EvolutionReActAgent:
    def __init__(self, model_router: ModelRouter | None = None):
        self.model_router = model_router or ModelRouter()
        self.max_reflexion_turns = 3

    def generate_skill(
        self, skill_name: str, requirement: str, failure_log: str | None = None
    ) -> dict[str, Any]:
        """
        Runs the ReAct Loop to generate and refine a python skill script.
        """
        reasoning_history: list[str] = []
        current_code = ""
        current_error = failure_log or ""

        logger.info(f"🤖 [EvolutionReActAgent] Starting autonomous loop for skill: {skill_name}")

        for turn in range(1, self.max_reflexion_turns + 1):
            logger.info(
                f"🔄 [EvolutionReActAgent] ReAct Loop Turn {turn}/{self.max_reflexion_turns}"
            )

            # Build prompt with Reasoning History to prevent repeating errors
            history_str = (
                "\n".join(reasoning_history) if reasoning_history else "No previous attempts."
            )

            prompt = f"""
System Prompt:
You are Aethel, the autonomous SupremeAI Core developer. Your job is to write a single Python class representing a "Skill".
The skill name must be: '{skill_name}' (represented as a class named '{self._to_class_name(skill_name)}').

Requirements:
{requirement}

Requirements for the class structure:
1. It must have an __init__ method initializing self.name = '{skill_name}'.
2. It must have a 'run(self, payload: dict) -> dict' method that executes the skill logic and returns a dict.

Execution History & Failures:
{history_str}

Current Syntax/Execution Error:
{current_error if current_error else "None. This is the first attempt."}

Task:
Reason through the requirements and any previous failure errors. Then output:
1. Thought: Your logical reasoning of how to build or fix the skill.
2. Code: The complete Python script inside a single block enclosed in ```python and ```. Do not include markdown text inside the python block.
"""
            # Turn 1 is hard, Turn 2 is medium/easy (analysis), Turn 3 escalates back to hard (code_generation) to fix complex logical bugs
            task_type = "code_generation" if turn in (1, 3) else "analysis"

            try:
                # Call LLM router
                response = self.model_router.route_and_generate(prompt, task_type=task_type)
                response_text = response.get("text", "")

                # Parse thought and code
                thought = self._extract_thought(response_text)
                code = self._extract_code(response_text)

                if not code:
                    logger.warning("⚠️ No code block found in LLM output, retrying...")
                    reasoning_history.append(
                        f"Turn {turn} Thought: {thought} | Observation: Failed to generate a valid ```python code block."
                    )
                    continue

                current_code = code
                logger.info(f"🛠️ Code generated on turn {turn}. Testing code compilation...")

                # Test compilation
                test_result = self._test_compile_code(code)
                if test_result["passed"]:
                    logger.info("✅ Skill code compilation passed!")
                    return {
                        "success": True,
                        "code": code,
                        "turns": turn,
                        "history": reasoning_history,
                        "thought": thought,
                    }
                else:
                    error_msg = test_result["reason"]
                    logger.warning(f"❌ Compilation failed: {error_msg}")
                    reasoning_history.append(
                        f"Turn {turn} Attempt:\nThought: {thought}\nObservation: Code compiled with error: {error_msg}"
                    )
                    current_error = error_msg
            except (RuntimeError, ValueError, TypeError) as e:
                logger.error(f"❌ ReAct agent loop exception: {e}")
                current_error = str(e)
                reasoning_history.append(f"Turn {turn} Exception: {e!s}")

        return {
            "success": False,
            "code": current_code,
            "error": current_error,
            "turns": self.max_reflexion_turns,
            "history": reasoning_history,
        }

    def _to_class_name(self, name: str) -> str:
        return "".join(part.capitalize() for part in name.split("_"))

    def _extract_thought(self, text: str) -> str:
        if "Thought:" in text:
            parts = text.split("Thought:")
            rest = parts[1]
            if "Code:" in rest:
                return rest.split("Code:")[0].strip()
            elif "```" in rest:
                return rest.split("```")[0].strip()
            return rest.strip()
        return "Thinking process not explicitly labeled."

    def _extract_code(self, text: str) -> str:
        if "```python" in text:
            return text.split("```python")[1].split("```", maxsplit=1)[0].strip()
        elif "```" in text:
            return text.split("```")[1].split("```", maxsplit=1)[0].strip()
        return ""

    def _test_compile_code(self, code: str) -> dict[str, Any]:
        try:
            # Inline compilation verification using compile()
            compile(code, "<string>", "exec")
            return {"passed": True}
        except SyntaxError as e:
            return {
                "passed": False,
                "reason": f"SyntaxError on line {e.lineno}: {e.msg}",
            }
        except (ValueError, OverflowError) as e:
            return {"passed": False, "reason": str(e)}
