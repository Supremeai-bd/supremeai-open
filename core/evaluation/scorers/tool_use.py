"""Tool-use success scorer — % of tool calls that succeed (#4047).

বাংলা: tool_use score = success rate of tool calls (MCP tools, browser, etc.)।
"""

from __future__ import annotations

from ..models import DimensionScore, ScoreDimension


def score_tool_use(
    tool_calls_total: int,
    tool_calls_succeeded: int,
    benchmark_run_id: str = "",
) -> DimensionScore:
    """Score tool-use success rate.

    Args:
        tool_calls_total: total number of tool calls attempted
        tool_calls_succeeded: number that succeeded
        benchmark_run_id: for evidence trail

    Returns:
        DimensionScore with normalized score (higher success rate = higher score)
    """
    if tool_calls_total < 0 or tool_calls_succeeded < 0:
        raise ValueError("tool_calls must be >= 0")
    if tool_calls_succeeded > tool_calls_total:
        raise ValueError(f"succeeded ({tool_calls_succeeded}) > total ({tool_calls_total})")

    if tool_calls_total == 0:
        # No tool calls → neutral score (provider doesn't use tools, not bad)
        score = 0.5
    else:
        score = tool_calls_succeeded / tool_calls_total

    return DimensionScore(
        dimension=ScoreDimension.TOOL_USE,
        score=score,
        raw_value=tool_calls_succeeded / tool_calls_total if tool_calls_total > 0 else 0.0,
        unit="ratio",
        evidence={
            "tool_calls_total": tool_calls_total,
            "tool_calls_succeeded": tool_calls_succeeded,
            "success_rate": tool_calls_succeeded / tool_calls_total
            if tool_calls_total > 0
            else 0.0,
            "benchmark_run_id": benchmark_run_id,
        },
    )
