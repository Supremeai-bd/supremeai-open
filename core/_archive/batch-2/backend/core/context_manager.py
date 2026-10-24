"""
SupremeAI 2.0 Context Management System
=======================================
Advanced context management with semantic search, session memory,
and long-term learning capabilities.
"""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta

from core.logging import get_logger
from qdrant_client import QdrantClient
from qdrant_client.http import models

from core.cache import get_redis_client
from core.config import settings


@dataclass
class ConversationContext:
    """Represents a conversation context with all relevant information."""

    session_id: str
    user_id: str
    conversation_history: list[dict]
    user_preferences: dict
    short_term_memory: dict
    long_term_memory: dict
    last_accessed: datetime
    context_embedding: list[float] | None = None
    relevance_score: float = 1.0  # How relevant this context is to current query


class ContextManager:
    """Manages conversation context with both short-term and long-term memory."""

    def __init__(self):
        self.logger = get_logger(__name__)

        # Initialize Qdrant client for vector storage.
        # Issue #443 fix: settings has NO QDRANT_URL/QDRANT_PORT fields (the old
        # direct attribute access raised AttributeError on every init, caught by
        # the except below, permanently degrading to Redis-only).  Read the
        # optional config the same way error_remediation.py does: safe getattr
        # with env-var fallback, so a provisioned QDRANT_URL actually activates
        # vector storage instead of silently never working.
        try:
            qdrant_url = getattr(settings, "qdrant_url", "") or os.getenv("QDRANT_URL", "")
            qdrant_port = int(
                getattr(settings, "qdrant_port", 0) or os.getenv("QDRANT_PORT", "6333") or 6333
            )
            if not qdrant_url:
                raise ValueError("QDRANT_URL not configured — vector storage disabled")
            self.vector_client = QdrantClient(url=qdrant_url, port=qdrant_port)
        except Exception as e:
            self.logger.warning(f"Qdrant client initialization failed: {e}")
            self.vector_client = None
            self.logger.warning(
                "Qdrant not available, falling back to Redis-only context management"
            )

        # Create collection for conversation contexts if Qdrant is available
        if self.vector_client:
            try:
                # FIX: Check if collection exists first, to prevent wiping out data on restart
                if not self.vector_client.collection_exists(
                    collection_name="conversation_contexts"
                ):
                    self.vector_client.create_collection(
                        collection_name="conversation_contexts",
                        vectors_config=models.VectorParams(
                            size=384, distance=models.Distance.COSINE
                        ),
                    )
                    self.logger.info("✅ Created Qdrant collection 'conversation_contexts'")
            except Exception as e:
                self.logger.error(f"Failed to create Qdrant collection: {e}")

        self.redis_client = get_redis_client()

    async def store_context(self, context: ConversationContext) -> bool:
        """Store conversation context with vector embedding."""
        try:
            # Store in Redis for quick access
            redis_key = f"context:{context.session_id}"
            self.redis_client.setex(
                redis_key,
                timedelta(hours=24),  # 24-hour expiry
                json.dumps(
                    {
                        "session_id": context.session_id,
                        "user_id": context.user_id,
                        "conversation_history": context.conversation_history,
                        "user_preferences": context.user_preferences,
                        "short_term_memory": context.short_term_memory,
                        "last_accessed": context.last_accessed.isoformat(),
                        "relevance_score": context.relevance_score,
                    }
                ),
            )

            # Store in vector database for semantic search if available
            if self.vector_client and context.context_embedding:
                try:
                    self.vector_client.upsert(
                        collection_name="conversation_contexts",
                        points=[
                            models.PointStruct(
                                id=hashlib.md5(
                                    context.session_id.encode(), usedforsecurity=False
                                ).hexdigest(),
                                vector=context.context_embedding,
                                payload={
                                    "user_id": context.user_id,
                                    "session_id": context.session_id,
                                    "timestamp": context.last_accessed.isoformat(),
                                    "conversation_summary": self.summarize_conversation(
                                        context.conversation_history
                                    ),
                                    "relevance_score": context.relevance_score,
                                },
                            )
                        ],
                    )
                except Exception as e:
                    self.logger.error(f"Failed to store context in vector database: {e}")

            return True
        except Exception as e:
            self.logger.error(f"Error storing context: {e}")
            return False

    async def retrieve_context(
        self, session_id: str, user_id: str | None = None
    ) -> ConversationContext | None:
        """Retrieve conversation context from Redis or vector database."""
        # First try Redis for quick access
        redis_key = f"context:{session_id}"
        context_data = self.redis_client.get(redis_key)

        if context_data:
            try:
                data = json.loads(context_data)
                # Update last accessed time
                self.redis_client.expire(redis_key, timedelta(hours=24))

                return ConversationContext(
                    session_id=data["session_id"],
                    user_id=data["user_id"],
                    conversation_history=data["conversation_history"],
                    user_preferences=data["user_preferences"],
                    short_term_memory=data.get("short_term_memory", {}),
                    long_term_memory={},  # Retrieve from separate long-term storage if needed
                    last_accessed=datetime.fromisoformat(data["last_accessed"]),
                    relevance_score=data.get("relevance_score", 1.0),
                )
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to decode context JSON: {e}")

        # If not in Redis, search vector database if available
        if self.vector_client and user_id:
            return await self.search_context_by_similarity(session_id, user_id)

        return None

    async def search_context_by_similarity(
        self, query: str, user_id: str | None = None
    ) -> ConversationContext | None:
        """Search for similar conversation contexts using semantic similarity."""
        if not self.vector_client:
            return None

        try:
            # Create embedding for the query (simplified - would use actual embedding model)
            # For now, we'll simulate this with a simple approach
            import hashlib

            hash_obj = hashlib.sha256(query.encode())
            hex_dig = hash_obj.hexdigest()
            # Convert hex to floats (simulated embedding)
            embedding = []
            for i in range(0, len(hex_dig), 2):
                byte_val = int(hex_dig[i : i + 2], 16)
                embedding.append(byte_val / 255.0)  # Normalize to 0-1
            # Pad or truncate to 384 dimensions
            while len(embedding) < 384:
                embedding.append(0.0)
            embedding = embedding[:384]

            # Search for similar contexts
            search_results = self.vector_client.search(
                collection_name="conversation_contexts",
                query_vector=embedding,
                limit=1,
                score_threshold=0.7,  # Minimum similarity threshold
                query_filter=(
                    models.Filter(
                        must=[
                            models.FieldCondition(
                                key="user_id", match=models.MatchValue(value=user_id)
                            )
                        ]
                    )
                    if user_id
                    else None
                ),
            )

            if search_results:
                payload = search_results[0].payload
                session_id = payload.get("session_id", "")

                # Retrieve from Redis using the found session ID
                return await self.retrieve_context(session_id, user_id)

        except Exception as e:
            self.logger.error(f"Error searching context by similarity: {e}")

        return None

    def summarize_conversation(self, history: list[dict]) -> str:
        """Create a summary of the conversation for vector storage."""
        summary_parts = []
        for msg in history[-5:]:  # Last 5 messages for brevity
            role = msg.get("role", "user")
            content = msg.get("content", "")[:100]  # Truncate for efficiency
            summary_parts.append(f"{role}: {content}")

        return " | ".join(summary_parts)

    async def update_context_with_new_interaction(
        self, session_id: str, user_id: str, user_input: str, ai_response: str
    ) -> bool:
        """Update context with a new interaction."""
        # Retrieve existing context
        context = await self.retrieve_context(session_id, user_id)

        if not context:
            # Create new context if none exists
            context = ConversationContext(
                session_id=session_id,
                user_id=user_id,
                conversation_history=[],
                user_preferences={},
                short_term_memory={},
                long_term_memory={},
                last_accessed=datetime.now(),
            )

        # Add new interaction to history
        context.conversation_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "user_input": user_input,
                "ai_response": ai_response,
            }
        )

        # Limit history to prevent excessive growth
        if len(context.conversation_history) > 50:  # Keep last 50 interactions
            context.conversation_history = context.conversation_history[-50:]

        # Update last accessed time
        context.last_accessed = datetime.now()

        # Store updated context
        return await self.store_context(context)


# Global context manager instance
context_manager = ContextManager()
