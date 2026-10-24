"""Local durable execution store for offline verification.

Production adapters must implement the same semantics against the approved database.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .canonical import EventEnvelope, ExecutionContext, ExecutionResult


class SQLiteExecutionStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            create table if not exists executions (
                execution_id text primary key, tenant_id text not null, idempotency_key text not null,
                context_json text not null, result_json text, created_at text not null,
                unique (tenant_id, idempotency_key)
            );
            create table if not exists events (
                event_id text primary key, execution_id text not null, tenant_id text not null,
                fingerprint text not null unique, sequence integer not null, payload_json text not null
            );
        """)
        self.db.commit()

    def start(self, context: ExecutionContext) -> bool:
        try:
            self.db.execute(
                "insert into executions(execution_id,tenant_id,idempotency_key,context_json,created_at) values(?,?,?,?,datetime('now'))",
                (
                    context.execution_id,
                    context.tenant_id,
                    context.idempotency_key,
                    json.dumps(context.to_dict(), sort_keys=True),
                ),
            )
            self.db.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def finish(self, execution_id: str, result: ExecutionResult) -> None:
        cursor = self.db.execute(
            "update executions set result_json=? where execution_id=?",
            (json.dumps(result.to_dict(), sort_keys=True), execution_id),
        )
        if cursor.rowcount != 1:
            raise KeyError(execution_id)
        self.db.commit()

    def append_event(self, event: EventEnvelope) -> EventEnvelope:
        existing = self.db.execute(
            "select payload_json from events where fingerprint=?", (event.fingerprint,)
        ).fetchone()
        if existing:
            payload = json.loads(existing["payload_json"])
            return EventEnvelope(
                payload["event_type"],
                event.context,
                payload["payload"],
                event.event_id,
                event.occurred_at,
                payload["sequence"],
            )
        sequence = self.db.execute(
            "select coalesce(max(sequence),0)+1 as next from events where execution_id=?",
            (event.context.execution_id,),
        ).fetchone()["next"]
        payload: dict[str, Any] = {
            "event_type": event.event_type,
            "payload": event.payload,
            "sequence": sequence,
        }
        self.db.execute(
            "insert into events(event_id,execution_id,tenant_id,fingerprint,sequence,payload_json) values(?,?,?,?,?,?)",
            (
                event.event_id,
                event.context.execution_id,
                event.context.tenant_id,
                event.fingerprint,
                sequence,
                json.dumps(payload, sort_keys=True),
            ),
        )
        self.db.commit()
        return EventEnvelope(
            event.event_type,
            event.context,
            event.payload,
            event.event_id,
            event.occurred_at,
            sequence,
        )

    def close(self) -> None:
        self.db.close()
