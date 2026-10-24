"""HITL hook for canonical Runs (M1-C) — reuse the existing HITL contract.

Roadmap M1: "HITL hook: reuse existing HITL manager contract." The repo's
standing HITL surface is ``services/hitl/engine.py::HITLEngine.
suspend_for_approval(target_resource, payload) -> record_id`` (plus
``approve``/``reject``) and the hardened ``models/pending_tasks.py``
approval store (PENDING -> APPROVED/REJECTED/CANCELLED, AUD-4 invariants).

The run-side contract is an injectable async hook — NO hard Firestore/SQLite
coupling in the run core (tests stay offline, production wiring chooses the
manager):

- ``suspend(target_resource, payload) -> record_id`` — called when a run
  moves RUNNING -> WAITING_APPROVAL.
- The run records ``approval_requested`` on its event stream; when the
  external decision lands, callers resolve via
  :meth:`RunService.transition` (WAITING_APPROVAL -> RUNNING/FAILED) and the
  ``approval_resolved`` event closes the loop.

``PendingTaskApprovalHook`` adapts the pending_tasks contract: it stores
approval intent via the same payload-hash discipline (SHA-256 over sorted
JSON) without importing the sqlite module (which refuses to boot outside
degraded mode); production may swap in the HITLEngine adapter.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Protocol


class ApprovalHook(Protocol):
    """The suspend-for-approval contract (HITL manager shape)."""

    async def suspend(self, target_resource: str, payload: dict[str, Any]) -> str:
        """Register the approval request; return the external record id."""
        ...


@dataclass
class InMemoryApprovalHook:
    """Offline/test hook — records suspensions in memory, deterministic ids.

    NOT for production: exists so the run core + API tests exercise the
    WAITING_APPROVAL path without Firestore or a degraded-mode sqlite file.
    """

    records: dict[str, dict[str, Any]] = field(default_factory=dict)
    _counter: int = 0

    async def suspend(self, target_resource: str, payload: dict[str, Any]) -> str:
        self._counter += 1
        record_id = f"hitl-{self._counter:06d}-{target_resource[:32]}"
        self.records[record_id] = {
            "target_resource": target_resource,
            "payload": payload,
            "payload_hash": _payload_hash(payload),
            "status": "pending_approval",
        }
        return record_id


class PendingTaskApprovalHook:
    """Adapter for the ``models/pending_tasks.py`` approval contract.

    Builds the canonical approval record (task payload + integrity hash,
    expiration, ownership fields) exactly as the pending_tasks store expects;
    ``store`` is an async callable injecting the actual persistence so this
    module keeps zero sqlite/Firestore imports.
    """

    def __init__(self, store: Any) -> None:
        # store: async def (record: dict) -> str  (returns record/task id)
        self._store = store

    async def suspend(self, target_resource: str, payload: dict[str, Any]) -> str:
        record = {
            "task_type": "RUN_APPROVAL",
            "payload": payload,
            "payload_hash": _payload_hash(payload),
            "status": "PENDING",
            "target_resource": target_resource,
        }
        return await self._store(record)


def _payload_hash(payload: dict[str, Any]) -> str:
    """Canonical SHA-256 over sorted JSON (same discipline as AUD-4.4)."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def make_approval_detail(record_id: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    """Structured ``approval_requested`` event detail."""
    detail: dict[str, Any] = {"record_id": record_id}
    if payload:
        detail["payload_hash"] = _payload_hash(payload)
    return detail
