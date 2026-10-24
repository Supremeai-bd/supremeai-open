import asyncio
import logging
import os

from dotenv import load_dotenv

from core.config import settings
from core.logging_config import logger

if os.path.exists(".env"):
    load_dotenv(".env")
elif os.path.exists("../.env"):
    load_dotenv("../.env")

logging.basicConfig(level=logging.INFO)


async def migrate_embeddings():
    """Re-encode ai_memory using the canonical 384-dimensional pgvector contract."""
    try:
        from supabase import create_client

        from core.embeddings import embed_for_pgvector

        url = settings.supabase_url
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

        if not url or not key:
            logger.error(
                "Supabase credentials not found. Ensure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set."
            )
            return

        supabase = create_client(url, key)
        logger.info("Fetching existing records from ai_memory...")
        response = await supabase.table("ai_memory").select("id, summary, embedding").execute()
        records = response.data

        if not records:
            logger.info("No records found in ai_memory.")
            return

        logger.info(f"Found {len(records)} records. Re-encoding to 384 dimensions...")

        for i, record in enumerate(records):
            record_id = record.get("id")
            summary = record.get("summary")
            if not summary:
                logger.warning(f"Record {record_id} has no summary. Skipping.")
                continue

            try:
                new_embedding = embed_for_pgvector(summary, pg_dim=384)
                if len(new_embedding) != 384:
                    logger.error(
                        f"[{i + 1}/{len(records)}] Refusing record {record_id}: embedding is {len(new_embedding)} dims."
                    )
                    continue

                await (
                    supabase.table("ai_memory")
                    .update({"embedding": new_embedding})
                    .eq("id", record_id)
                    .execute()
                )
                logger.info(f"[{i + 1}/{len(records)}] Re-encoded record {record_id}.")
            except Exception as exc:
                logger.error(f"Error processing record {record_id}: {exc}")

        logger.info("Migration complete!")
    except Exception as exc:
        logger.error(f"Migration failed: {exc}")


if __name__ == "__main__":
    asyncio.run(migrate_embeddings())
