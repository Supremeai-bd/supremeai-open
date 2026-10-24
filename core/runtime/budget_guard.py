# backend/runtime/budget_guard.py
"""Hard Enforcement Budget Guard for Canonical Task Runtime."""

from __future__ import annotations

from core.task_contract import TaskContract


class BudgetExceededError(Exception):
    """Raised when any task compute/cost/token budget threshold is violated."""

    pass


class BudgetGuard:
    """Enforces deterministic hard limits on tokens, costs, tool calls, and execution time."""

    @staticmethod
    def check_pre_execution(task: TaskContract) -> None:
        """Verify task has valid remaining budget before executing."""
        budget = task.budget
        if budget.tokens_used >= budget.max_tokens:
            raise BudgetExceededError(
                f"Token budget exhausted before execution: {budget.tokens_used}/{budget.max_tokens}"
            )
        if budget.cost_incurred >= budget.max_cost_usd:
            raise BudgetExceededError(
                f"Cost budget exhausted: ${budget.cost_incurred:.4f} >= ${budget.max_cost_usd:.4f}"
            )
        if budget.tool_calls_count >= budget.max_tool_calls:
            raise BudgetExceededError(
                f"Tool call limit reached: {budget.tool_calls_count}/{budget.max_tool_calls}"
            )

    @staticmethod
    def record_and_enforce(
        task: TaskContract,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
        tool_calls: int = 0,
    ) -> None:
        """Accumulate usage and immediately halt if limits are breached."""
        budget = task.budget
        budget.tokens_used += prompt_tokens + completion_tokens
        budget.cost_incurred += cost_usd
        budget.tool_calls_count += tool_calls

        if budget.tokens_used > budget.max_tokens:
            raise BudgetExceededError(
                f"Token limit exceeded during execution: {budget.tokens_used} > {budget.max_tokens}"
            )
        if budget.cost_incurred > budget.max_cost_usd:
            raise BudgetExceededError(
                f"Cost limit exceeded during execution: ${budget.cost_incurred:.4f} > ${budget.max_cost_usd:.4f}"
            )
        if budget.tool_calls_count > budget.max_tool_calls:
            raise BudgetExceededError(
                f"Tool call limit exceeded: {budget.tool_calls_count} > {budget.max_tool_calls}"
            )
