# backend/core/tenant_db.py
"""বাংলা মন্তব্য: Tenant-aware Firestore client with hard-isolated subcollections.

Fixes Applied (Autonomous Architecture Audit):
- 🔴 [CRITICAL] ImportError-এ firestore undefined থেকে NameError হওয়ার রিস্ক fixed
- 🔴 [CRITICAL] try/except ব্লকে fallback `firestore.Client()` কল করার আগে existence check যোগ করা
"""

from __future__ import annotations

from fastapi import HTTPException, status

from core.errors.error_bus import with_error_bus
from core.logging_config import logger

# বাংলা মন্তব্য: Safe import with proper fallback — আর undefined NameError হবে না
try:
    from google.cloud import firestore

    _HAS_FIRESTORE = True
except ImportError:
    _HAS_FIRESTORE = False
    firestore = None  # type: ignore[assignment]
    logger.warning("google.cloud.firestore not available — tenant DB will use mock/test mode only")


class TenantAwareFirestore:
    """
    Hard-Isolated Multi-tenant Database Client.
    Forces all queries and writes into a specific user's subcollection.
    """

    def __init__(self, tenant_id: str):
        if not tenant_id:
            logger.critical("🚨 SECURITY BREACH: Attempted to initialize DB without a tenant_id!")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database access denied: Missing tenant isolation context.",
            )

        self.tenant_id = tenant_id
        # Use existing configured firestore client if available, fallback to default
        from utils.environment import is_test_environment

        if is_test_environment():
            self._db = self._create_mock_db()
        else:
            self._db = self._resolve_db_client()

        # 🛡️ হার্ড-আইসোলেটেড রুট রেফারেন্স
        self.tenant_root = self._db.collection("tenants").document(self.tenant_id)

    @staticmethod
    def _create_mock_db():
        class MockQuery:
            """Minimal chainable query surface (order_by/limit/stream) so
            tenant-scoped list endpoints can run in test environments."""

            def order_by(self, *args, **kwargs):
                return self

            def limit(self, *args, **kwargs):
                return self

            def where(self, *args, **kwargs):
                return self

            def stream(self):
                return iter(())

        class MockFirestore:
            def collection(self, *args, **kwargs):
                class MockCol:
                    def document(self, *args, **kwargs):
                        class MockDoc:
                            def get(self, *args, **kwargs):
                                class MockSnap:
                                    exists = False

                                    def to_dict(self):
                                        return {}

                                return MockSnap()

                            def set(self, *args, **kwargs):
                                pass

                            def collection(self, *args, **kwargs):
                                return MockCol()

                        return MockDoc()

                    # Issue #1472: expose query methods so list endpoints can
                    # be exercised in test mode without google-cloud-firestore.
                    def order_by(self, *args, **kwargs):
                        return MockQuery()

                    def limit(self, *args, **kwargs):
                        return MockQuery()

                    def where(self, *args, **kwargs):
                        return MockQuery()

                    def stream(self):
                        return iter(())

                return MockCol()

        return MockFirestore()

    @with_error_bus("_resolve_db_client")
    def _resolve_db_client(self):
        """Try to resolve a Firestore client — handling the case where google.cloud isn't installed."""
        try:
            from services.storage.gcp_firestore import get_firestore_client

            client = get_firestore_client()
            if client is not None:
                return client
        except Exception:
            logger.debug("get_firestore_client() failed, falling back to direct firestore.Client()")

        # বাংলা মন্তব্য: firestore module exists কিনা check করে তবেই কল
        if _HAS_FIRESTORE:
            return firestore.Client()  # type: ignore[union-attr]
        # No Firestore available — raise a clear error instead of NameError
        raise RuntimeError(
            "Firestore client not available. Install google-cloud-firestore or run in test environment."
        )

    def collection(self, collection_name: str):
        """ট্যানান্টের নিজস্ব সাব-কালেকশন রিটার্ন করবে"""
        return self.tenant_root.collection(collection_name)

    @property
    def conversations(self):
        """Tenant-scoped ``conversations`` collection (issue #1472).

        Previously the memory routes called ``db.conversations.<mongo-api>``
        which raised AttributeError — 'TenantAwareFirestore' object has no
        attribute 'conversations' — and GET /api/memory/conversations always
        returned 500. The collection is addressed through the same hard
        tenant-isolation path (tenants/<tenant_id>/conversations).
        """
        return self.collection("conversations")

    def get_tenant_profile(self):
        """ট্যানান্টের গ্লোবাল মেটাডাটা রিটার্ন করবে"""
        return self.tenant_root.get().to_dict()
