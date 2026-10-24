from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.logging_config import logger

router = APIRouter(prefix="/pair", tags=["ai-pair-programmer"])


class IssueRequest(BaseModel):
    issue_description: str
    repo: str | None = None
    branch: str | None = "main"
    create_pr: bool = False


class AIPairProgrammer:
    def __init__(self):
        logger.info("Initialized AIPairProgrammer")

    async def _call_llm(
        self, prompt: str, task_type: str = "reasoning", max_cost: float = 0.03
    ) -> str:
        try:
            from brain.model_router import ModelRouter

            router = ModelRouter()
            result = await router.async_route_and_generate(
                prompt, task_type=task_type, max_cost=max_cost
            )
            return result.get("text", "") if isinstance(result, dict) else ""
        except Exception as exc:
            logger.error(f"LLM call failed: {exc}")
            return ""

    async def solve_issue(
        self,
        issue_description: str,
        repo: str | None = None,
        branch: str = "main",
        create_pr: bool = False,
    ) -> dict[str, Any]:
        logger.info(f"Starting pair programming session for: {issue_description[:80]}")

        # Step 1: Plan
        plan_prompt = (
            "You are a senior software engineer. Given the following issue, create a concise "
            "implementation plan. Return a numbered list with max 5 clear steps.\n\n"
            f"Issue: {issue_description}"
        )
        plan = await self._call_llm(plan_prompt, task_type="reasoning", max_cost=0.02)
        if not plan:
            plan = "1. Analyze issue\n2. Write fix\n3. Add tests\n4. Document changes"

        # Step 2: Generate code
        code_prompt = (
            "You are a senior software engineer. Generate the minimal, clean, production-ready "
            "code change needed to resolve the following issue. "
            "Return ONLY the code with file comments (# file: path/to/file.py). No markdown.\n\n"
            f"Issue: {issue_description}"
        )
        code = await self._call_llm(code_prompt, task_type="coding", max_cost=0.05)
        if not code:
            code = f"# No code change generated for: {issue_description}"

        # Step 3: Write tests
        test_prompt = f"Generate pytest unit tests for the following code change. Return ONLY the test code. No markdown.\n\nCode:\n{code}"
        tests = await self._call_llm(test_prompt, task_type="coding", max_cost=0.03)

        # Step 4: Optionally create PR
        pr_result = None
        if create_pr and repo:
            pr_result = await self._create_github_pr(repo, branch, issue_description, code)

        return {
            "status": "success",
            "issue": issue_description,
            "plan": plan,
            "code": code,
            "tests": tests,
            "review_request": "Please review the generated code and run: pytest",
            "pr": pr_result,
        }

    async def _create_github_pr(
        self, repo: str, branch: str, issue: str, code: str
    ) -> dict[str, Any]:
        """Delegate PR creation to the auto_pr_pipeline."""
        try:
            from tools.code.auto_pr_pipeline import AutoPRPipeline

            pipeline = AutoPRPipeline()
            return await pipeline.create_pr(
                repo=repo,
                branch=branch,
                title=f"AI Fix: {issue[:60]}",
                body=f"## AI Generated Fix\n\n**Issue:** {issue}\n\n**Changes:**\n```python\n{code[:500]}\n```",
                files={"ai_fix.py": code},
            )
        except Exception as exc:
            logger.error(f"PR creation failed: {exc}")
            return {"status": "error", "error": str(exc)}

    async def review_code(self, code: str, context: str | None = None) -> dict[str, Any]:
        """Perform AI code review."""
        prompt = (
            "You are a senior code reviewer. Analyze the following code and provide:\n"
            "1. Security issues (critical first)\n"
            "2. Logic bugs\n"
            "3. Performance improvements\n"
            "4. Code style suggestions\n\n"
            f"Code:\n{code}"
        )
        if context:
            prompt += f"\n\nContext: {context}"

        review = await self._call_llm(prompt, task_type="reasoning", max_cost=0.03)
        return {
            "status": "success",
            "review": review,
            "score": "pending",
        }


pair_programmer = AIPairProgrammer()


@router.post("/solve")
async def solve_issue(request: IssueRequest):
    try:
        result = await pair_programmer.solve_issue(
            issue_description=request.issue_description,
            repo=request.repo,
            branch=request.branch or "main",
            create_pr=request.create_pr,
        )
        return result
    except Exception as e:
        logger.error(f"Solve issue failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/review")
async def review_code(payload: dict[str, Any]):
    code = payload.get("code", "")
    context = payload.get("context")
    if not code:
        raise HTTPException(status_code=400, detail="No code provided")
    return await pair_programmer.review_code(code, context)
