# backend/skills/core_knowledge_qa.py
import os
from typing import Any

from core.config_cache import config_cache
from core.logging_config import logger

# বাংলা মন্তব্য: google-genai প্যাকেজ CI-তে ঠিকমতো install না থাকলে graceful fallback
try:
    from google import genai
    from google.genai import types

    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]

from core.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

# বাংলা মন্তব্য: গ্লোবাল Gemini Circuit Breaker — ৫ বার ফেইল হলে OPEN, 60স পর HALF_OPEN
_gemini_qa_breaker: CircuitBreaker = CircuitBreaker(
    name="gemini_knowledge_qa",
    failure_threshold=5,
    recovery_timeout=60,
)


def _generate_embedding(text: str) -> list[float] | None:
    """লোকাল sentence-transformers (ফ্রি, অফলাইন) প্রাইমারি — LiteLLM OpenAI ফলব্যাক।
    memory/supabase_store.py-র একই প্যাটার্ন (core.embeddings.embed_for_pgvector)।"""
    try:
        from core.embeddings import embed_for_pgvector

        # ai_memory/pgvector contract is vector(384); requesting 1536 only
        # spams the normalization warning on every call (issue #443 cleanup).
        return embed_for_pgvector(text)
    except Exception as exc:
        logger.warning(f"Embedding generation failed: {exc}")
        return None


def _vector_search(query: str, namespace: str) -> list[dict[str, Any]]:
    """
    গ্যাপ ফিক্স (Database-Driven Logic নীতি): আগে এখানে `_mock_vector_search()` ছিল যা query
    যাই হোক না কেন সবসময় একই ২টা hardcoded fake ডকুমেন্ট রিটার্ন করত — ফলে "permission-aware
    RAG" স্কিলটি আসলে ইউজারের প্রশ্নকে সম্পূর্ণ উপেক্ষা করত। এখন real Supabase pgvector RPC
    (`match_knowledge_base`) দিয়ে সেম্যান্টিক সার্চ চেষ্টা করা হয়, ব্যর্থ হলে namespace-স্কোপড
    ilike সাবস্ট্রিং সার্চে ফলব্যাক করে (memory/supabase_store.py-এর search_facts()-এর একই
    resilience প্যাটার্ন)। Supabase কনফিগার করা না থাকলে fabricate না করে খালি লিস্ট রিটার্ন করে।
    """
    try:
        from database.supabase_client import db as supabase_db
    except Exception as exc:
        logger.warning(f"Supabase client unavailable for knowledge_qa vector search: {exc}")
        return []

    client = getattr(supabase_db, "client", None)
    if client is None:
        logger.warning(
            "Supabase client not configured — knowledge_qa returning no results instead of fabricated data."
        )
        return []

    query_embedding = _generate_embedding(query)
    if query_embedding:
        try:
            response = client.rpc(
                "match_knowledge_base",
                {
                    "query_embedding": query_embedding,
                    "match_namespace": namespace,
                    "match_threshold": 0.3,
                    "match_count": 5,
                },
            ).execute()
            if response.data:
                return [
                    {
                        "id": row["id"],
                        "content": row["content"],
                        "source": row["source"],
                    }
                    for row in response.data
                ]
        except Exception as exc:
            logger.warning(
                f"pgvector RPC 'match_knowledge_base' failed, falling back to ilike: {exc}"
            )

    try:
        result = (
            client.table("knowledge_base")
            .select("id, content, source")
            .eq("namespace", namespace)
            .ilike("content", f"%{query}%")
            .limit(5)
            .execute()
        )
        return result.data or []
    except Exception as exc:
        logger.error(f"Fallback ilike search on knowledge_base failed: {exc}")
        return []


def execute_tool(payload: dict) -> dict:
    """Strict Supreme Tool Contract for Permission-aware RAG with Citations"""
    try:
        user_role = payload.get("user_role", "Standard_User")
        query = payload.get("query", "").strip()

        if not query:
            return {"success": False, "error": "Query content cannot be empty."}

        role_permissions = {
            "Admin": ["company_financials", "public_sops"],
            "Manager": ["public_sops"],
            "Standard_User": ["public_sops"],
        }

        allowed_namespaces = role_permissions.get(user_role, ["public_sops"])

        retrieved_chunks = []
        for namespace in allowed_namespaces:
            chunks = _vector_search(query, namespace)
            retrieved_chunks.extend(chunks)

        if not retrieved_chunks:
            return {
                "success": True,
                "result": {
                    "answer": "I could not find any relevant documents you have permission to access.",
                    "citations": [],
                },
            }

        context_str = ""
        citations = []
        for idx, chunk in enumerate(retrieved_chunks, 1):
            context_str += f"[{idx}] Source: {chunk['source']}\nContent: {chunk['content']}\n\n"
            citations.append({"citation_id": idx, "source": chunk["source"], "doc_id": chunk["id"]})

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return {
                "success": False,
                "error": "Gemini API key is missing from environment.",
            }

        client = genai.Client(api_key=api_key)

        system_instruction = """
        You are an enterprise knowledge-base assistant. Your task is to answer the user's question using ONLY the provided context.
        For every claim or factual statement you make, you MUST cite the source number using brackets like [1] or [2].
        If the answer cannot be found in the context, state that you do not know. Do not hallucinate.
        """

        user_prompt = f"""
        [Context Data]
        {context_str}

        [User Question]
        {query}
        """

        # বাংলা মন্তব্য: সার্কিট ব্রেকার দিয়ে Gemini API কল র্যাপ করা হতেছে
        # OPEN অবস্থায় CircuitBreakerOpenError থ্রো করে ফরোয়ার্ডিং ব্লক করে
        try:
            response = _gemini_qa_breaker.call(
                client.models.generate_content,
                model="gemini-2.5-flash",
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=config_cache.get("core_knowledge_qa_temperature", 0.2),
                ),
            )
        except CircuitBreakerOpenError as cb_exc:
            logger.warning(f"🚨 Gemini Circuit Breaker OPEN: {cb_exc}")
            return {
                "success": False,
                "error": "LLM infrastructure is temporarily unavailable. Circuit breaker active. Please retry in 60 seconds.",
            }

        return {
            "success": True,
            "result": {"answer": response.text.strip(), "citations": citations},
        }

    except Exception as e:
        logger.error(f"Failed inside core_knowledge_qa skill loop: {e!s}")
        return {"success": False, "error": f"Skill execution anomaly: {e!s}"}
