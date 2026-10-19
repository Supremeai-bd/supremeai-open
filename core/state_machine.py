"""
Deterministic Agent Finite State Machine (FSM) — Core Decision Moat.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar


class AgentState(str, Enum):
    IDLE = "IDLE"
    PLANNING = "PLANNING"
    CLAIMED = "CLAIMED"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    TERMINATED = "TERMINATED"
    REJECTED = "REJECTED"


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal state transition is attempted."""


@dataclass(frozen=True)
class TransitionRecord:
    from_state: AgentState
    to_state: AgentState
    reason: str
    timestamp: float = field(default_factory=time.time)


class AgentStateMachine:
    """
    Deterministic FSM governing the lifecycle of an autonomous task agent.
    Maintains an immutable audit ledger of transitions.
    """

    ALLOWED_TRANSITIONS: ClassVar[dict[AgentState, set[AgentState]]] = {
        AgentState.IDLE: {AgentState.PLANNING, AgentState.CLAIMED},
        AgentState.PLANNING: {AgentState.CLAIMED, AgentState.IDLE, AgentState.REJECTED},
        AgentState.CLAIMED: {
            AgentState.EXECUTING,
            AgentState.REJECTED,
            AgentState.IDLE,
        },
        AgentState.EXECUTING: {AgentState.VERIFYING, AgentState.REJECTED},
        AgentState.VERIFYING: {
            AgentState.TERMINATED,
            AgentState.EXECUTING,
            AgentState.REJECTED,
        },
        AgentState.TERMINATED: set(),  # Terminal state
        AgentState.REJECTED: {
            AgentState.PLANNING,
            AgentState.IDLE,
        },  # Can be re-planned
    }

    def __init__(self, agent_id: str, initial_state: AgentState = AgentState.IDLE):
        self.agent_id = agent_id
        self._state = initial_state
        self._history: list[TransitionRecord] = []

    @property
    def current_state(self) -> AgentState:
        return self._state

    @property
    def is_terminal(self) -> bool:
        return self._state == AgentState.TERMINATED

    @property
    def history(self) -> list[TransitionRecord]:
        return list(self._history)

    def transition_to(self, new_state: AgentState, reason: str = "") -> None:
        if new_state == self._state:
            return  # Idempotent no-op

        valid_targets = self.ALLOWED_TRANSITIONS.get(self._state, set())
        if new_state not in valid_targets:
            raise InvalidStateTransitionError(
                f"Cannot transition agent '{self.agent_id}' from {self._state.value} to {new_state.value}. "
                f"Valid targets: {[s.value for s in valid_targets]}"
            )

        record = TransitionRecord(
            from_state=self._state, to_state=new_state, reason=reason
        )
        self._history.append(record)
        self._state = new_state
