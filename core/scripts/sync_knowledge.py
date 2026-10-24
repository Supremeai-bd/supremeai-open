import json
import sys
from pathlib import Path

# Add backend directory to sys.path so we can import services
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# FIX (import): 'core.logger' module does not exist; canonical logger lives in
# monitoring.logging (core.logging is only a deprecation shim re-exporting it).
from monitoring.logging import get_logger
from services.memory_service import CascadeMemoryService

logger = get_logger("knowledge_sync")


def sync_knowledge():
    logger.info("Starting knowledge base sync...")
    ms = CascadeMemoryService()

    knowledge_file = backend_dir.parent / "supremeai_coldstart_knowledge.json"
    if not knowledge_file.exists():
        logger.warning(f"Knowledge file {knowledge_file} not found. Skipping sync.")
        return

    with open(knowledge_file, encoding="utf-8") as f:
        knowledge_data = json.load(f)

    # Note: In a real incremental sync, we would check hashes or timestamps.
    # For now, we will assume store_memory handles upsert or we just insert.
    # The CascadeMemoryService doesn't have a native upsert by title out of the box unless we do custom SQL.
    # To keep it safe and idempotent, we might want to skip if already exists, but the user just said "inject it".

    count = 0
    for r in knowledge_data:
        count += 1
        rtype = r.get("type", "faq")
        metadata = {
            "tier": r.get("tier", "Unknown"),
            "priority": r.get("priority", "Unknown"),
            "tags": r.get("tags", []),
            "source": "coldstart_knowledge_seed.json",
            "injected_via": "sync_knowledge_pipeline",
        }

        # Build embedded summary and metadata content
        if rtype in ["doc", "domain"]:
            q_title = r.get("title", "")
            a_body = r.get("content", "")
            summary = f"{q_title}\n\n{a_body}"
            entry_content = a_body
        elif rtype == "faq":
            q_title = r.get("question", "")
            a_body = r.get("answer", "")
            summary = f"Q: {q_title}\nA: {a_body}"
            entry_content = a_body
        elif rtype == "error_pattern":
            q_title = f"{r.get('error_code', '')}: {r.get('title', '')}"
            a_body = f"Symptoms: {r.get('symptoms')}. Remediation: {r.get('remediation')}"
            summary = f"{q_title}\n{a_body}"
            entry_content = a_body
        elif rtype == "conversational_seed":
            q_title = r.get("intent", "")
            a_body = str(r.get("patterns", ""))
            summary = f"Intent: {q_title}\nPatterns: {a_body}"
            entry_content = a_body
        else:
            q_title = r.get("title") or r.get("question") or r.get("id", "")
            a_body = str(r)
            summary = f"{q_title}\n{a_body}"
            entry_content = a_body

        metadata["content"] = entry_content
        metadata["title"] = q_title

        try:
            ms.store_memory(
                file_path=r.get("id", f"import_ci_{count}"),
                content=entry_content,
                summary=summary,
                structure=rtype,
                session_id="ci_deployment_sync",
                agent_type="AntigravityCI",
                task_type="KnowledgeInjection",
                metadata=metadata,
            )
        except Exception as e:
            logger.error(f"Failed to inject memory {q_title}: {e}")

    logger.info(f"Knowledge sync complete. Processed {count} entries.")


if __name__ == "__main__":
    sync_knowledge()
