import hashlib
import importlib.util
import os
from pathlib import Path
import sqlite3
import sys

# Ensure backend root is in sys.path
backend_dir = Path(__file__).resolve().parent.parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from core.logging_config import logger

try:
    import chromadb
except ImportError:
    chromadb = None

from tools.knowledge.local_search_rag import LocalSearchRAG

DB_PATH = os.path.join(str(backend_dir), "knowledge_store.db")


def _init_fts_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(title, content, source, tokenize='unicode61')"
    )
    conn.commit()


def _upsert_fts(
    conn: sqlite3.Connection, doc_id: str, title: str, content: str, source: str
) -> None:
    # SQLite FTS5 ভার্চুয়াল টেবিলে সরাসরি UPSERT (ON CONFLICT) সাপোর্ট করে না।
    # তাই প্রথমে ডুপ্লিকেট rowid থাকলে তা ডিলেট করে নতুন করে ইনসার্ট করা হচ্ছে।
    conn.execute("DELETE FROM knowledge_fts WHERE rowid = ?", [doc_id])
    conn.execute(
        "INSERT INTO knowledge_fts(rowid, title, content, source) VALUES (?, ?, ?, ?)",
        [doc_id, title, content, source],
    )


def seed_all():
    logger.info("Initializing LocalSearchRAG...")
    rag = LocalSearchRAG()

    seed_data_dir = os.path.join(str(backend_dir), "tools", "seed_data")
    if not os.path.exists(seed_data_dir):
        logger.info(f"Error: seed_data directory not found at {seed_data_dir}")
        return

    logger.info("Scanning seed modules...")
    ids = []
    documents = []
    metadatas = []

    for filename in os.listdir(seed_data_dir):
        if filename.endswith(".py") and filename not in ["__init__.py", "helpers.py"]:
            module_name = filename[:-3]
            module_path = os.path.join(seed_data_dir, filename)

            spec = importlib.util.spec_from_file_location(
                f"tools.seed_data.{module_name}", module_path
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.path.insert(0, seed_data_dir)
                try:
                    spec.loader.exec_module(module)
                except Exception as e:
                    logger.info(f"Failed to load {module_name}: {e}")
                    continue
                finally:
                    sys.path.pop(0)

                for attr_name in dir(module):
                    if attr_name.isupper():
                        attr_val = getattr(module, attr_name)
                        if isinstance(attr_val, dict):
                            logger.info(f"Processing dict '{attr_name}' in {module_name}...")
                            for key, item in attr_val.items():
                                if not isinstance(item, dict):
                                    continue

                                doc_title = item.get(
                                    "title",
                                    item.get("name", item.get("error_message", key)),
                                )
                                doc_content = f"Title: {doc_title}\n"
                                if "cause" in item:
                                    doc_content += f"Cause: {item['cause']}\n"
                                if "fix" in item:
                                    doc_content += f"Solution/Fix: {item['fix']}\n"
                                if "description" in item:
                                    doc_content += f"Description: {item['description']}\n"
                                if "when_to_use" in item:
                                    doc_content += f"When to use: {item['when_to_use']}\n"
                                if "code_example" in item:
                                    doc_content += f"Code Example:\n{item['code_example']}\n"
                                if "do" in item:
                                    doc_content += f"DO: {', '.join(item['do']) if isinstance(item['do'], list) else item['do']}\n"
                                if "dont" in item:
                                    doc_content += f"DONT: {', '.join(item['dont']) if isinstance(item['dont'], list) else item['dont']}\n"
                                if "content" in item:
                                    doc_content += f"Content: {item['content']}\n"
                                if "solutions" in item:
                                    doc_content += f"Solutions: {', '.join(item['solutions']) if isinstance(item['solutions'], list) else item['solutions']}\n"

                                doc_id = hashlib.md5(
                                    f"{module_name}_{key}".encode(),
                                    usedforsecurity=False,
                                ).hexdigest()
                                ids.append(doc_id)
                                documents.append(doc_content)
                                metadatas.append(
                                    {
                                        "source": "supremeai_1.0_seed",
                                        "module": module_name,
                                        "key": key,
                                        "title": doc_title[:100],
                                        "language": item.get("language", "generic"),
                                        "framework": item.get("framework", "generic"),
                                    }
                                )

    if ids:
        logger.info(f"Upserting {len(ids)} expert knowledge patterns to ChromaDB...")
        try:
            rag.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            logger.info("Successfully seeded all SupremeAI 1.0 expert knowledge!")
        except Exception as e:
            logger.info(f"ChromaDB Upsert failed: {e}. Writing to fallback index.")
            for idx, doc_id in enumerate(ids):
                rag._index[doc_id] = [metadatas[idx]["title"], documents[idx]]
            rag._store_search("expert_seed", {})
            logger.info("Successfully seeded to fallback index file.")

        logger.info(f"Writing {len(ids)} entries to SQLite FTS5...")
        try:
            conn = sqlite3.connect(DB_PATH)
            _init_fts_db(conn)
            for idx, doc_id in enumerate(ids):
                _upsert_fts(
                    conn,
                    doc_id,
                    metadatas[idx]["title"],
                    documents[idx],
                    metadatas[idx]["source"],
                )
            conn.commit()
            conn.close()
            logger.info("Successfully seeded SQLite FTS5 knowledge base.")
        except Exception as e:
            logger.info(f"SQLite FTS seeding failed: {e}")
    else:
        logger.info("No seed data found to import.")


if __name__ == "__main__":
    seed_all()
