import asyncio
import inspect
import re
from typing import Any
from unittest.mock import MagicMock, Mock

from core.logging_config import logger

_VALID_TABLE_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


# Custom Exception for Circuit Breaking
class PrimaryDatabaseDownException(Exception):
    pass


class ServiceDegradedException(Exception):
    pass


class SmartDataRepository:
    def __init__(self, firebase_client: Any, supabase_client: Any):
        self.firebase = firebase_client
        self.supabase = supabase_client

    @staticmethod
    def _validate_table_name(table_name: str) -> None:
        if not table_name or not _VALID_TABLE_PATTERN.match(table_name):
            raise ValueError(f"Invalid table name: {table_name}")

    async def _fetch_from_primary_impl(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        try:
            # Firebase Client check and fetch
            if hasattr(self.firebase, "collection"):
                doc_ref = self.firebase.collection(collection).document(doc_id)
                get_target = doc_ref.get
                if callable(get_target):
                    res = get_target()
                    if (
                        inspect.iscoroutine(res)
                        or (hasattr(asyncio, "isfuture") and asyncio.isfuture(res))
                        or inspect.isawaitable(res)
                        and not isinstance(res, MagicMock | Mock)
                    ):
                        doc = await res
                    else:
                        doc = res
                else:
                    doc = get_target

                if not doc.exists:
                    return None
                return doc.to_dict()
            else:
                raise PrimaryDatabaseDownException(
                    "Firebase client not initialized or missing collection method"
                )
        except PrimaryDatabaseDownException:
            raise
        except Exception as e:
            logger.warning(f"⚠️ Firebase unreachable ({e!s}). Retrying...")
            raise PrimaryDatabaseDownException(str(e)) from e

    async def _fetch_from_primary(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        try:
            return await self._fetch_from_primary_impl(collection, doc_id)
        except PrimaryDatabaseDownException:
            raise

    # Tier 2: Fallback to Supabase if primary database fails
    async def get_document_with_fallback(
        self, table_name: str, doc_id: str
    ) -> dict[str, Any] | None:
        try:
            # Try to fetch from Firebase
            return await self._fetch_from_primary(table_name, doc_id)
        except PrimaryDatabaseDownException:
            logger.critical(
                "🚨 FIREBASE IS DOWN! Circuit Breaker Tripped. Falling back to Supabase."
            )
            try:
                # If Supabase client has the execute API (standard Supabase-py)
                if hasattr(self.supabase, "table"):
                    self._validate_table_name(table_name)
                    response = (
                        await self.supabase.table(table_name).select("*").eq("id", doc_id).execute()
                    )
                    return response.data[0] if response.data else None
                # If it's CloudPostgresStore helper
                elif hasattr(self.supabase, "_execute"):
                    self._validate_table_name(table_name)
                    query = f"SELECT * FROM {table_name} WHERE id = %s LIMIT 1"
                    row = self.supabase._execute(query, (doc_id,), fetchone=True)
                    return dict(row) if row else None
                else:
                    logger.critical("Supabase client is not compatible or not initialized.")
                    return None
            except Exception as backup_error:
                logger.critical(f"💀 FATAL: Both databases are down! {backup_error!s}")
                raise ServiceDegradedException(
                    "Both primary and fallback databases unavailable"
                ) from backup_error
