"""Learning Loop orchestrator — mine → write → inject → measure (#4054).

বাংলা: এটি main orchestrator। সম্পূর্ণ learning loop চালায়:
  1. DecisionMetadata থেকে patterns mine করে
  2. successful patterns → skill templates (L2 experience)
  3. failed patterns → regression guards
  4. skill templates L1 context-এ inject হয় (next agent শিখে)
  5. Evaluation Engine improvement measure করে

এই module শুধু steps 1-3 করে। Step 4 (inject) L1 context loader-এ হবে।
Step 5 (measure) Evaluation Engine-এ হবে।
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .pattern_miner import (
    DecisionPattern,
    filter_failed_patterns,
    filter_successful_patterns,
    mine_patterns,
)
from .skill_template_writer import write_regression_guard, write_skill_template


@dataclass(frozen=True)
class LearningLoopResult:
    """Result of running the learning loop."""

    total_decisions: int
    patterns_mined: int
    skill_templates_written: int
    regression_guards_written: int
    skill_template_paths: list[str] = field(default_factory=list)
    regression_guard_paths: list[str] = field(default_factory=list)
    top_patterns: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_decisions": self.total_decisions,
            "patterns_mined": self.patterns_mined,
            "skill_templates_written": self.skill_templates_written,
            "regression_guards_written": self.regression_guards_written,
            "skill_template_paths": self.skill_template_paths,
            "regression_guard_paths": self.regression_guard_paths,
            "top_patterns": self.top_patterns,
        }


def run_learning_loop(
    decisions: list[dict[str, Any]],
    min_occurrences: int = 3,
    skills_dir: str = "knowledge/skills",
    guards_dir: str = "knowledge/regression_guards",
) -> LearningLoopResult:
    """Run the full learning loop.

    বাংলা: সম্পূর্ণ learning loop চালায়। decisions থেকে patterns mine →
    skill templates + regression guards তৈরি।

    Args:
        decisions: list of DecisionMetadata dicts (from #4052)
        min_occurrences: minimum count to be a pattern
        skills_dir: output dir for skill templates
        guards_dir: output dir for regression guards

    Returns:
        LearningLoopResult with counts + file paths
    """
    # Step 1: Mine patterns
    patterns = mine_patterns(decisions, min_occurrences=min_occurrences)

    # Step 2: Separate successful + failed
    successful = filter_successful_patterns(patterns)
    failed = filter_failed_patterns(patterns)

    # Step 3: Write skill templates + regression guards
    skill_paths: list[str] = []
    for p in successful:
        path = write_skill_template(p, output_dir=skills_dir)
        skill_paths.append(path)

    guard_paths: list[str] = []
    for p in failed:
        path = write_regression_guard(p, output_dir=guards_dir)
        guard_paths.append(path)

    # Top patterns for summary (top 5 by count)
    top_patterns = [p.to_dict() for p in patterns[:5]]

    return LearningLoopResult(
        total_decisions=len(decisions),
        patterns_mined=len(patterns),
        skill_templates_written=len(skill_paths),
        regression_guards_written=len(guard_paths),
        skill_template_paths=skill_paths,
        regression_guard_paths=guard_paths,
        top_patterns=top_patterns,
    )
