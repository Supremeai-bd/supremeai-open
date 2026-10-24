import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any


# dangerous patterns চেক করার পাইথনিক ও ফাস্ট মেকানিজম (Ruff SIM110 Fix)
def check_dangerous_code(code: str) -> bool:
    dangerous_patterns = [
        "os.system",
        "subprocess.Popen",
        "eval(",
        "exec(",
        "shutil.rmtree",
    ]
    return any(pattern in code for pattern in dangerous_patterns)


class HealingState:
    retries: int = 0
    code: str = ""
    tests: str = ""
    result: str | None = None


async def run_sandbox_tests(state: HealingState) -> HealingState:
    return state


async def analyze_with_litellm(state: HealingState) -> HealingState:
    return state


async def apply_patch(state: HealingState) -> HealingState:
    return state


async def send_to_approval_queue(state: HealingState) -> HealingState:
    return state


class VulnerabilityPredictor:
    @staticmethod
    def scan(code: str) -> bool:
        dangerous_patterns = ["os.system", "subprocess.call", "DROP TABLE", "eval("]
        return any(pattern in code for pattern in dangerous_patterns)


async def _single_healing_iteration(state: HealingState) -> HealingState:
    if VulnerabilityPredictor.scan(state.code):
        state.result = "vulnerable"
        return state

    state = await run_sandbox_tests(state)
    if state.result == "success":
        return state

    state = await analyze_with_litellm(state)
    state = await apply_patch(state)
    return state


def _quarantine_and_diagnose(state: HealingState, reason: str):
    import loguru

    quarantine_dir = Path("data/quarantine")
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    report_file = quarantine_dir / f"diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    report = {
        "reason": reason,
        "retries": state.retries,
        "code": state.code,
        "tests": state.tests,
        "timestamp": datetime.now().isoformat(),
    }

    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)

    loguru.logger.error(
        f"[Quarantine] Skill isolated due to {reason}. Diagnostic report saved to {report_file}"
    )


async def run_healing_loop(code: str, tests: str, max_retries: int = 3) -> dict[str, Any]:
    state = HealingState()
    state.code = code
    state.tests = tests
    state.retries = 0

    while state.retries < max_retries:
        try:
            # Enforce strict 5 second timeout on each healing iteration
            state = await asyncio.wait_for(_single_healing_iteration(state), timeout=5.0)

            if state.result == "vulnerable":
                _quarantine_and_diagnose(state, "CWE Vulnerability Detected")
                return {
                    "status": "quarantined",
                    "reason": "vulnerability",
                    "attempts": state.retries,
                }

            if state.result == "success":
                return {"status": "healed", "attempts": state.retries}

        except TimeoutError:
            _quarantine_and_diagnose(state, "Healing Loop Timeout (5s exceeded)")
            return {
                "status": "quarantined",
                "reason": "timeout",
                "attempts": state.retries,
            }

        state.retries += 1

    # After max retries (3 crashes/failures)
    _quarantine_and_diagnose(state, "Max retries exceeded (3 crashes)")
    return {
        "status": "quarantined",
        "reason": "max_retries_exceeded",
        "attempts": state.retries,
    }
