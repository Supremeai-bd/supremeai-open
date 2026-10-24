"""Merge-learning integration for the evolution module (#1939).

বাংলা: এই মডিউলটি merge_learning_reports টেবিল থেকে শেখে — কোন PR-এ
held_history ছিল (merge train-এ আটকেছিল), সেই pattern-গুলো SkillFitness
মেট্রিক্সে penalty হিসেবে যায়। ক্লিন মার্জ (held_history ছাড়া) reward পায়।

Signal formula (config-driven, no magic numbers):
    skill.failure_count += Σ(held entries for skill) × MERGE_LEARNING_HOLD_PENALTY
    skill.success_count += Σ(clean merges for skill) × MERGE_LEARNING_CLEAN_REWARD
    fitness_score = success_count / max(1, success_count + failure_count)

Skill naming convention: ``lane:merge-execution`` (e.g. ``coder:merge-execution``).
The lane is derived from the merge_learning_reports.lane column. If lane is NULL,
``unknown:merge-execution`` is used.

Wired into SelfEvolutionAgent._tick via ``learn_from_merge_reports`` — gated by
``settings.enable_evolution_learning`` (config_fields.py:524, default False).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.logging_config import logger

if TYPE_CHECKING:
    pass


async def learn_from_merge_reports(
    fitness_engine: Any,
    *,
    lookback_days: int | None = None,
    hold_penalty: float | None = None,
    clean_reward: float | None = None,
) -> dict[str, dict[str, float]]:
    """Read merge_learning_reports and feed signals into FitnessEngine.

    বাংলা: গত ``lookback_days`` দিনের merge_learning_reports পড়ে — যেগুলোতে
    held_history আছে সেগুলো penalty, যেগুলোতে নেই সেগুলো reward। প্রতিটি lane
    আলাদা skill (``lane:merge-execution``)।

    Args:
        fitness_engine: FitnessEngine instance (has ``track_execution`` method).
        lookback_days: how many days back to read (default: from settings).
        hold_penalty: failure_count weight per held entry (default: from settings).
        clean_reward: success_count weight per clean merge (default: from settings).

    Returns:
        Per-skill summary: ``{skill_name: {"holds": N, "cleans": M, "delta_f": X}}``.
    """
    # Lazy import to avoid module-load cycle (settings → evolution → settings)
    from core.config import settings
    from models.merge_learning_report import list_merge_learning

    if lookback_days is None:
        lookback_days = getattr(settings, "merge_learning_lookback_days", 7)
    if hold_penalty is None:
        hold_penalty = getattr(settings, "merge_learning_hold_penalty", 1.0)
    if clean_reward is None:
        clean_reward = getattr(settings, "merge_learning_clean_reward", 0.5)

    cutoff = datetime.now(UTC) - timedelta(days=lookback_days)

    # Fetch ALL merges in the lookback window (not just held — we need clean ones too)
    try:
        all_merges = await list_merge_learning(limit=500)
    except Exception as exc:  # noqa: BLE001 — DB may be unavailable in degraded mode
        logger.warning(
            f"learn_from_merge_reports: could not read merge_learning_reports ({exc}) — skipping tick"
        )
        return {}

    # Filter by lookback window (merged_at is ISO timestamp string or epoch)
    recent: list[dict[str, Any]] = []
    for row in all_merges:
        merged_at = row.get("merged_at")
        if merged_at is None:
            continue
        try:
            if isinstance(merged_at, (int, float)):
                dt = datetime.fromtimestamp(float(merged_at), tz=UTC)
            else:
                dt = datetime.fromisoformat(str(merged_at).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if dt >= cutoff:
            recent.append(row)

    if not recent:
        logger.debug("learn_from_merge_reports: no recent merges in lookback window")
        return {}

    # Aggregate by lane → skill_name = "lane:merge-execution"
    per_skill: dict[str, dict[str, int]] = {}
    for row in recent:
        lane = row.get("lane") or "unknown"
        skill_name = f"{lane}:merge-execution"
        held_history = row.get("held_history")
        # held_history is a list (JSONB) — non-empty means the merge was held
        held_count = 0
        if held_history:
            if isinstance(held_history, str):
                # JSONB may come back as string in some drivers
                import json

                try:
                    held_history = json.loads(held_history)
                except (ValueError, TypeError):
                    held_history = []
            if isinstance(held_history, list):
                held_count = len(held_history)

        if skill_name not in per_skill:
            per_skill[skill_name] = {"holds": 0, "cleans": 0}
        if held_count > 0:
            per_skill[skill_name]["holds"] += held_count
        else:
            per_skill[skill_name]["cleans"] += 1

    # Feed signals into fitness_engine via track_execution.
    # track_execution increments by 1 per call; config weight applied via repeat count.
    # For fractional weights (e.g. 0.5), we round to nearest integer but track the
    # fractional delta in the summary for observability.
    summary: dict[str, dict[str, float]] = {}
    for skill_name, counts in per_skill.items():
        holds = counts["holds"]
        cleans = counts["cleans"]
        for _ in range(int(holds * hold_penalty)):
            fitness_engine.track_execution(skill_name, success=False, latency=0.0)
        for _ in range(int(cleans * clean_reward)):
            fitness_engine.track_execution(skill_name, success=True, latency=0.0)

        # Compute observed fitness delta for the summary
        total = holds * hold_penalty + cleans * clean_reward
        delta_f = (cleans * clean_reward) / max(1.0, total) if total > 0 else 0.0
        summary[skill_name] = {
            "holds": holds,
            "cleans": cleans,
            "delta_f": round(delta_f, 4),
        }

    logger.info(
        f"learn_from_merge_reports: processed {len(recent)} merges across "
        f"{len(per_skill)} skills (lookback={lookback_days}d, "
        f"penalty={hold_penalty}, reward={clean_reward})"
    )
    return summary
