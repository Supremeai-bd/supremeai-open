from __future__ import annotations

import time
from typing import Any

from core.logging_config import logger
from core.security.cryptographic_ledger import CryptographicLedger
from database.tenant_db import TenantAwareFirestore


class HITLAuditLedger(CryptographicLedger):
    """
    Persistent Cryptographic Ledger for HITL approvals (Audit 7.5).
    Extends CryptographicLedger to persist append-only hash chains in Supabase / Firestore
    instead of ephemeral Redis with 30-day expiration.
    """

    def __init__(self, db: TenantAwareFirestore | None = None):
        super().__init__()
        self.db = db
        self.collection_name = "hitl_audit_ledger"
        self._initialize_from_db()

    def _initialize_from_db(self):
        """
        Load the last hash from the database to continue the chain.
        Tries Supabase first, then Firestore fallback.
        """
        # 1. Supabase Postgres check
        try:
            from database.supabase_client import db

            client = getattr(db, "service_client", None) or getattr(db, "client", None)
            if client:
                res = (
                    client.table(self.collection_name)
                    .select("*")
                    .order("index", desc=True)
                    .limit(1)
                    .execute()
                )
                if res and getattr(res, "data", None):
                    latest_block = res.data[0]
                    self.last_hash = latest_block.get("hash", self.genesis_hash)
                    self._current_index = latest_block.get("index", 0)
                    return
        except Exception as e:
            logger.debug(f"[HITLAuditLedger] Supabase init check: {e}")

        # 2. Firestore fallback
        if self.db and hasattr(self.db, "client") and self.db.client:
            try:
                ref = self.db.client.collection(self.collection_name)
                query = ref.order_by("index", direction="DESCENDING").limit(1)
                docs = list(query.stream())
                if docs:
                    latest_block = docs[0].to_dict()
                    self.last_hash = latest_block.get("hash", self.genesis_hash)
                    self._current_index = latest_block.get("index", 0)
                    return
            except Exception as e:
                logger.debug(f"[HITLAuditLedger] Firestore init check: {e}")

        self._current_index = 0
        self.last_hash = self.genesis_hash

    def record_entry_sync(
        self, agent_id: str, action: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Override to persist the block to Supabase/Firestore after computing hash chain.
        """
        timestamp = time.time()
        current_hash = self._compute_hash(self.last_hash, timestamp, agent_id, payload)

        self._current_index += 1
        block = {
            "index": self._current_index,
            "previous_hash": self.last_hash,
            "timestamp": timestamp,
            "agent_id": agent_id,
            "action": action,
            "payload": payload,
            "hash": current_hash,
        }

        self.last_hash = current_hash

        # 1. Save to Supabase append-only table
        try:
            from database.supabase_client import db

            client = getattr(db, "service_client", None) or getattr(db, "client", None)
            if client:
                client.table(self.collection_name).insert(block).execute()
                logger.info(
                    f"[HITLAuditLedger] Saved entry #{block['index']} to Supabase ledger. Hash: {current_hash[:12]}..."
                )
        except Exception as e:
            logger.debug(f"[HITLAuditLedger] Supabase save omitted or failed: {e}")

        # 2. Save to Firestore (as backup/fallback)
        if self.db and hasattr(self.db, "client") and self.db.client:
            try:
                doc_ref = self.db.client.collection(self.collection_name).document(current_hash)
                doc_ref.set(block)
                logger.info(
                    f"[HITLAuditLedger] Saved entry #{block['index']} to Firestore. Hash: {current_hash[:12]}..."
                )
            except Exception as e:
                logger.debug(f"[HITLAuditLedger] Failed to save entry to Firestore: {e}")

        return block
