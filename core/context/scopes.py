"""Scope chain for the Context Engine (M2-B) — ecosystem Ph2 / OSS plan §3.

Roadmap M2: scope chain ``GLOBAL → USER → WORKSPACE → PROJECT → CHAT → RUN →
STEP``, with RUN/STEP anchored to M1's canonical ``run_id`` (parent_run_id on
``runs`` = STEP). This module is the scope vocabulary + chain validation.

No DB coupling — pure module (same discipline as runs/state_machine.py).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class ScopeLevel(enum.StrEnum):
    """One step of the scope chain, narrowest last."""

    GLOBAL = "global"
    USER = "user"
    WORKSPACE = "workspace"
    PROJECT = "project"
    CHAT = "chat"
    RUN = "run"
    STEP = "step"


#: Chain order (broadest → narrowest).
SCOPE_ORDER: tuple[ScopeLevel, ...] = (
    ScopeLevel.GLOBAL,
    ScopeLevel.USER,
    ScopeLevel.WORKSPACE,
    ScopeLevel.PROJECT,
    ScopeLevel.CHAT,
    ScopeLevel.RUN,
    ScopeLevel.STEP,
)


class ScopeChainError(ValueError):
    """Raised when a scope violates the chain's containment requirements."""


@dataclass(frozen=True)
class Scope:
    """A resolved scope: how broad the context request is allowed to be.

    ``level`` declares the narrowest level honored; the identity fields
    (user_id … step_id) must be filled for every level at or below the
    requested one (chain containment, see :func:`validate_scope`).
    """

    level: ScopeLevel = ScopeLevel.USER
    user_id: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    chat_id: str | None = None
    run_id: str | None = None
    step_id: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "level": self.level.value,
            "user_id": self.user_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "chat_id": self.chat_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
        }


def _level_index(level: ScopeLevel) -> int:
    return SCOPE_ORDER.index(level)


def validate_scope(scope: Scope) -> None:
    """Enforce chain containment.

    - Required levels (GLOBAL → USER → CHAT → RUN → STEP): when the request
      is at-or-below a level, that level's id must be present.
    - Optional branch levels (WORKSPACE, PROJECT): may be present at any
      request level, but never NARROWER than the requested level.
    - No level narrower than the request may carry an id.
    """
    idx = _level_index(scope.level)
    required: dict[int, str | None] = {
        _level_index(ScopeLevel.USER): scope.user_id,
        _level_index(ScopeLevel.CHAT): scope.chat_id,
        _level_index(ScopeLevel.RUN): scope.run_id,
        _level_index(ScopeLevel.STEP): scope.step_id,
    }
    optional: dict[int, str | None] = {
        _level_index(ScopeLevel.WORKSPACE): scope.workspace_id,
        _level_index(ScopeLevel.PROJECT): scope.project_id,
    }
    for level_idx, value in required.items():
        if level_idx <= idx and not value:
            raise ScopeChainError(
                f"scope level {SCOPE_ORDER[level_idx].value!r} requires an id "
                f"(requested level: {scope.level.value!r})"
            )
        if level_idx > idx and value:
            raise ScopeChainError(
                f"scope level {SCOPE_ORDER[level_idx].value!r} is narrower than "
                f"the requested level {scope.level.value!r} — it must be empty"
            )
    for level_idx, value in optional.items():
        if value and level_idx > idx:
            raise ScopeChainError(
                f"scope level {SCOPE_ORDER[level_idx].value!r} is narrower than "
                f"the requested level {scope.level.value!r} — it must be empty"
            )


def scope_distance(a: ScopeLevel, b: ScopeLevel) -> int:
    """Chain distance between two levels (0 = same level)."""
    return abs(_level_index(a) - _level_index(b))


def scope_match_score(item_level: ScopeLevel, request_level: ScopeLevel) -> float:
    """Narrower-or-equal items score higher (1.0 exact, decays by distance).

    Items NARROWER than the request (e.g. a RUN-scoped note for a STEP
    request) still match (distance-based decay); items BROADER than the
    request are also acceptable (GLOBAL background) with the same decay —
    the caller's budgeter decides via combined score.
    """
    if item_level == request_level:
        return 1.0
    return max(0.0, 1.0 - 0.15 * scope_distance(item_level, request_level))
