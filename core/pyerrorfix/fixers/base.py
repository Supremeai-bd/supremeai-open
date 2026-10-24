"""Base fixer + registry."""

from __future__ import annotations

from pyerrorfix.core.issue import Issue


class BaseFixer:
    """Each fixer transforms the source text.

    Fixers MUST be idempotent: applying twice = applying once. They MUST be
    conservative: if a transformation is ambiguous, skip it (return the source
    unchanged). A fixer never raises.
    """

    name: str = "base"
    applies_to: set[str] = set()  # rule_ids this fixer handles

    def __init__(self, source: str, issues: list[Issue]) -> None:
        self.source = source
        self.issues = issues

    def apply(self) -> str:
        raise NotImplementedError

    def relevant_issues(self) -> list[Issue]:
        return [i for i in self.issues if i.rule_id in self.applies_to]

    def _lines(self) -> list[str]:
        return self.source.splitlines(keepends=True)
