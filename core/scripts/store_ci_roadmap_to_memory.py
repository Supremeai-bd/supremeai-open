import asyncio
import json
import sys
from pathlib import Path

from core.logging_config import logger

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from services.memory_service import CascadeMemoryService


async def inject_roadmap_to_memory():
    mem = CascadeMemoryService()

    roadmap_steps = [
        {
            "step": 1,
            "title": "Environment Reproduction",
            "command": "git fetch origin main && git reset --hard origin/main",
            "description": "Always ensure working state matches latest remote main before starting triage.",
            "category": "ci_triage_step_1",
        },
        {
            "step": 2,
            "title": "Exact Dependency Install",
            "command": "pip install poetry && poetry install --only main --no-root && poetry install --with dev --no-root",
            "description": "Reproduce exact CI dependency tree from workflow definitions and pyproject.toml.",
            "category": "ci_triage_step_2",
        },
        {
            "step": 3,
            "title": "Import and Collection Level Bug Check",
            "command": "poetry run python scripts/ci/validate_router_imports.py --strict && poetry run pytest --collect-only -q",
            "description": "Catch syntax, missing import, and module-level collection errors instantly before running heavy tests.",
            "category": "ci_triage_step_3",
        },
        {
            "step": 4,
            "title": "Fast Parallel Test Failure Discovery",
            "command": 'poetry run pytest -n auto --dist=loadfile --timeout=120 -k "not chaos" -q --no-cov',
            "description": "Execute full test suite in fast parallel mode with --no-cov to quickly list all failing tests without coverage overhead.",
            "category": "ci_triage_step_4",
        },
        {
            "step": 5,
            "title": "Isolated Verbose Traceback Extraction",
            "command": "poetry run pytest tests/path/to_test.py::TestClass::test_name -q --no-cov --tb=long -p no:logging",
            "description": "Run failing test in isolation with --tb=long and -p no:logging to isolate the exact error stack without noise.",
            "category": "ci_triage_step_5",
        },
        {
            "step": 6,
            "title": "Source Code vs Test Tracing",
            "command": 'grep -n "<failing_function_or_attr>" -r . --include="*.py" | grep -v tests/',
            "description": "Determine whether bug originates from production source code or a stale test contract expectation.",
            "category": "ci_triage_step_6",
        },
        {
            "step": 7,
            "title": "Failure Classification Framework",
            "command": "Audit: 1. Production code bug -> fix logic/import. 2. Stale contract -> update assertion. 3. Flaky/env -> add skip mark.",
            "description": "Classify failure into Production Bug, Stale Test Contract, or Environment/Flaky dependency.",
            "category": "ci_triage_step_7",
        },
        {
            "step": 8,
            "title": "Isolated Test Verification",
            "command": "poetry run pytest tests/path/to_test.py -q --no-cov",
            "description": "Re-run only the target test suite to verify the fix immediately in isolation.",
            "category": "ci_triage_step_8",
        },
        {
            "step": 9,
            "title": "Full Suite Regression Validation",
            "command": 'poetry run pytest -n auto --dist=loadfile --timeout=120 -k "not chaos" -q --no-cov',
            "description": "Re-run the complete test suite across all workers to ensure zero regressions were introduced.",
            "category": "ci_triage_step_9",
        },
        {
            "step": 10,
            "title": "Clean Staged Commit",
            "command": "git status --short && git add <specific_files>",
            "description": "Verify working tree cleanliness and stage only intended source and test modifications.",
            "category": "ci_triage_step_10",
        },
    ]

    # 1. Store Master Playbook
    master_summary = (
        "📖 [MASTER CI ROADMAP] 10-Step CI Failure Root Cause & Resolution Command Roadmap\n"
        "1. git reset/sync -> 2. poetry install exact -> 3. validate imports & collect-only -> "
        "4. pytest -n auto --no-cov -> 5. isolated test --tb=long -p no:logging -> "
        "6. grep source code -> 7. classify failure -> 8. test verify -> 9. regression suite -> 10. clean stage"
    )
    mem.store_memory(
        file_path="docs/devops/CI_DEBUGGING_ROADMAP.md",
        content=json.dumps(roadmap_steps, indent=2),
        summary=master_summary,
        structure=json.dumps({"type": "ci_master_playbook", "steps_count": 10}),
        session_id="ci-root-cause-playbook",
        agent_type="ci_debugger",
        task_type="ci_debugging_standard",
        metadata={"category": "ci_standard", "doc_path": "docs/devops/CI_DEBUGGING_ROADMAP.md"},
    )
    logger.debug("[OK] Injected Master CI Debugging Playbook into ai_memory database.")

    # 2. Store Individual Steps for Granular Vector Search
    for s in roadmap_steps:
        step_summary = (
            f"[CI TRIAGE STEP {s['step']}] {s['title']}\n"
            f"Command: {s['command']}\n"
            f"Action: {s['description']}"
        )
        mem.store_memory(
            file_path=f"docs/devops/CI_DEBUGGING_ROADMAP.md#step-{s['step']}",
            content=f"Command:\n{s['command']}\n\nDescription:\n{s['description']}",
            summary=step_summary,
            structure=json.dumps(s),
            session_id="ci-root-cause-playbook",
            agent_type="ci_debugger",
            task_type="ci_debugging_standard",
            metadata={"step": s["step"], "title": s["title"], "category": s["category"]},
        )
        logger.debug(f"[OK] Injected Step {s['step']}: {s['title']}")


if __name__ == "__main__":
    asyncio.run(inject_roadmap_to_memory())
