"""
Provides the `KnowledgeBaseIndexer` for managing a vector-based knowledge base.

This module handles the extraction and indexing of structured and unstructured
knowledge from Python `seed_data` modules (

"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import os
from typing import Any, ClassVar

from core.logging_config import logger
from memory.chromadb_store import ChromaDBStore


class KnowledgeBaseIndexer:
    """
    Indexes tools/seed_data/ Python modules into a ChromaDB-backed vector store
    and exposes search + real-time feedback recording.
    """

    def __init__(self, vector_store: ChromaDBStore | None = None) -> None:
        self.vector_store = vector_store or ChromaDBStore()
        self.seed_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "tools",
            "seed_data",
        )
        self._indexed_hashes: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------
    def _extract_documents_from_file(self, path: str) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        filename = os.path.basename(path)
        category = os.path.splitext(filename)[0].upper()
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                source = f.read()
        except Exception as e:
            try:
                import loguru

                loguru.logger.error(f"Tool execution error: {e}")
            except Exception as e:
                logger.warning(f"Exception suppressed: {e}")
            return docs

        module_hash = hashlib.md5(source.encode("utf-8"), usedforsecurity=False).hexdigest()
        self._indexed_hashes[path] = module_hash

        docs.append(
            {
                "id": f"{filename}::module",
                "text": source,
                "metadata": {
                    "source": path,
                    "filename": filename,
                    "category": category,
                    "type": "module_source",
                    "module_hash": module_hash,
                },
            }
        )

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return docs

        # 1) Extract classes + methods + top-level functions
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_doc = ast.get_docstring(node) or ""
                methods = [
                    m.name
                    for m in node.body
                    if isinstance(m, ast.FunctionDef | ast.AsyncFunctionDef)
                ]
                docs.append(
                    {
                        "id": f"{filename}::{node.name}",
                        "text": f"Class {node.name}\nDocstring: {class_doc}\nMethods: {', '.join(methods)}",
                        "metadata": {
                            "source": path,
                            "filename": filename,
                            "category": category,
                            "type": "class",
                            "class_name": node.name,
                        },
                    }
                )
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and (
                        item_doc := ast.get_docstring(item) or ""
                    ):
                        docs.append(
                            {
                                "id": f"{filename}::{node.name}.{item.name}",
                                "text": f"Method {node.name}.{item.name}\n{item_doc}",
                                "metadata": {
                                    "source": path,
                                    "filename": filename,
                                    "category": category,
                                    "type": "method",
                                    "class_name": node.name,
                                    "method_name": item.name,
                                },
                            }
                        )
            elif isinstance(node, ast.FunctionDef):
                func_doc = ast.get_docstring(node) or ""
                docs.append(
                    {
                        "id": f"{filename}::{node.name}",
                        "text": f"Function {node.name}\n{func_doc}",
                        "metadata": {
                            "source": path,
                            "filename": filename,
                            "category": category,
                            "type": "function",
                            "function_name": node.name,
                        },
                    }
                )

        # 2) Extract module-level pattern/learning/template dicts (seed_data style)
        docs.extend(self._extract_seed_data_calls(tree, filename, path, category))
        return docs

    _CALL_FACTORIES: ClassVar[Any] = {
        "_learning",
        "_pattern",
        "_error_fix",
        "_code_template",
        "_best_practice",
    }

    def _extract_seed_data_calls(
        self, tree: Any, filename: str, path: str, category: str
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen_ids: set = set()
        self._walk_for_factory_calls(
            tree, filename, path, category, results, seen_ids, parent_key=None
        )
        return results

    def _walk_for_factory_calls(
        self,
        node: Any,
        filename: str,
        path: str,
        category: str,
        out: list[dict[str, Any]],
        seen: set,
        parent_key: str | None,
    ) -> None:
        if isinstance(node, ast.Call):
            func_name = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else (node.func.id if isinstance(node.func, ast.Name) else None)
            )
            if func_name in self._CALL_FACTORIES:
                entry_id, doc = self._build_doc_from_call(
                    node, filename, path, category, func_name, parent_key
                )
                if entry_id and doc and entry_id not in seen:
                    seen.add(entry_id)
                    out.append(doc)
        for child in ast.iter_child_nodes(node):
            child_parent_key = parent_key
            if isinstance(child, ast.Dict):
                for k in child.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        child_parent_key = k.value
                        break
            self._walk_for_factory_calls(
                child, filename, path, category, out, seen, child_parent_key
            )

    def _build_doc_from_call(
        self,
        call_node: Any,
        filename: str,
        path: str,
        category: str,
        func_name: str,
        doc_name: str | None,
    ) -> tuple:
        text_parts, meta_parts, name_key, tags, confidence = [], [], None, [], 0.0
        args = call_node.args
        if not args:
            return None, None
        try:
            if (
                len(args) > 0
                and isinstance(args[0], ast.Constant)
                and isinstance(args[0].value, str)
            ):
                name_key = doc_name or args[0].value
            if (
                len(args) > 2
                and isinstance(args[2], ast.Constant)
                and isinstance(args[2].value, str)
            ):
                text_parts.append(args[2].value)
            if (
                len(args) > 1
                and isinstance(args[1], ast.Constant)
                and isinstance(args[1].value, str)
            ):
                meta_parts.append(f"category={args[1].value}")
            if len(args) > 3 and isinstance(args[3], ast.List):
                for elt in args[3].elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        tags.append(elt.value)
                        text_parts.append(elt.value)
            if len(args) > 6:
                with contextlib.suppress(Exception):
                    confidence = float(args[6].value)
        except Exception as e:
            try:
                import loguru

                loguru.logger.error(f"Tool execution error: {e}")
            except Exception as e:
                logger.warning(f"Exception suppressed: {e}")
            return None, None

        text = "\n".join(text_parts) if text_parts else (doc_name or "")
        if not name_key:
            return None, None
        entry_id = f"{filename}::{name_key}"
        metadata: dict[str, Any] = {
            "source": path,
            "filename": filename,
            "category": category,
            "type": func_name.replace("_", ""),
            "name": name_key,
            "confidence": confidence,
            "tags": tags,
        }
        return entry_id, {"id": entry_id, "text": text, "metadata": metadata}

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------
    def index_seed_data(self, seed_dir: str | None = None) -> dict[str, Any]:
        seed_dir = seed_dir or self.seed_dir
        if not os.path.isdir(seed_dir):
            return {"indexed": False, "reason": f"seed directory not found: {seed_dir}"}
        total_docs = 0
        errors: list[str] = []
        for root, _dirs, files in os.walk(seed_dir):
            for name in sorted(files):
                if not name.endswith(".py"):
                    continue
                path = os.path.join(root, name)
                docs = self._extract_documents_from_file(path)
                if docs:
                    try:
                        self.vector_store.add_documents(docs)
                        total_docs += len(docs)
                    except Exception as exc:
                        errors.append(f"{name}: {exc}")
        return {
            "indexed": total_docs,
            "seed_dir": seed_dir,
            "errors": errors[:10],
        }

    def index_scraped_data(self, data: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Indexes data scraped from external sources (OSSInsight, awesome-lists, etc.)
        Expects a list of dicts with at least 'text' and 'metadata'.
        """
        if not data:
            return {"indexed": 0, "reason": "No data provided"}

        docs: list[dict[str, Any]] = []
        for _i, item in enumerate(data):
            text = item.get("text", "")
            if not text:
                continue

            metadata = item.get("metadata", {})
            metadata["type"] = "scraped_data"
            metadata["source_type"] = metadata.get("source_type", "external")

            # Generate a unique ID based on the content or provided ID
            item_id = (
                item.get("id")
                or hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()
            )

            docs.append(
                {
                    "id": f"scraped::{item_id}",
                    "text": text,
                    "metadata": metadata,
                }
            )

        total_docs = 0
        errors = []
        if docs:
            try:
                self.vector_store.add_documents(docs)
                total_docs = len(docs)
            except Exception as exc:
                errors.append(str(exc))

        return {
            "indexed": total_docs,
            "errors": errors[:10],
        }

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def search_knowledge(self, query: str, n_results: int = 5) -> list[dict[str, Any]]:
        try:
            raw = self.vector_store.query(query, n_results=n_results)
            return [
                {
                    "doc_id": doc_id,
                    "score": score,
                    "text": doc_data.get("text", ""),
                    "metadata": doc_data.get("metadata", {}),
                }
                for doc_id, score, doc_data in raw
            ]
        except Exception as e:
            try:
                import loguru

                loguru.logger.error(f"Tool execution error: {e}")
            except Exception as e:
                logger.warning(f"Exception suppressed: {e}")
            return []

    # ------------------------------------------------------------------
    # Real-time feedback
    # ------------------------------------------------------------------
    def record_search_feedback(
        self, session_id: str, query: str, top_k: int = 5, rating: float | None = None
    ) -> dict[str, Any]:
        results = self.search_knowledge(query, n_results=top_k)
        retrieved_texts = "\n---\n".join(r["text"] for r in results)
        feedback: dict[str, Any] = {
            "session_id": session_id,
            "query": query,
            "retrieved_count": len(results),
            "top_doc_ids": [r["doc_id"] for r in results],
        }
        if rating is not None:
            feedback["user_rating"] = rating
        feedback["retrieved_chunks"] = retrieved_texts
        return feedback

    def record_thumbs(
        self, session_id: str, query: str, doc_id: str, helpful: bool
    ) -> dict[str, Any]:
        rating = 1.0 if helpful else 0.0
        doc = self.vector_store.get_document(doc_id)
        if doc and doc.get("metadata"):
            metadata = dict(doc["metadata"])
            metadata["helpful_votes"] = metadata.get("helpful_votes", 0) + (1 if helpful else 0)
            metadata["negative_votes"] = metadata.get("negative_votes", 0) + (0 if helpful else 1)
            self.vector_store.add_document(doc_id, doc["text"], metadata)
        return {
            "recorded": True,
            "doc_id": doc_id,
            "helpful": helpful,
            "rating": rating,
        }

    def prune_low_quality(
        self, min_helpful_ratio: float = 0.3, min_votes: int = 5
    ) -> dict[str, Any]:
        if hasattr(self.vector_store, "_collection") and self.vector_store._collection is not None:
            return {
                "pruned": 0,
                "note": "prune not implemented for live ChromaDB collections in this pass",
            }
        to_remove = []
        for doc_id, doc_data in self.vector_store._fallback_docs.items():
            meta = doc_data.get("metadata", {})
            helpful = meta.get("helpful_votes", 0)
            negative = meta.get("negative_votes", 0)
            total = helpful + negative
            if total >= min_votes and (helpful / total) < min_helpful_ratio:
                to_remove.append(doc_id)
        for doc_id in to_remove:
            self.vector_store.delete(doc_id)
        return {"pruned": len(to_remove)}

    def rebuild_index(self, seed_dir: str | None = None) -> dict[str, Any]:
        if hasattr(self.vector_store, "_collection") and self.vector_store._collection is not None:
            with contextlib.suppress(Exception):
                self.vector_store._client.delete_collection(self.vector_store.collection_name)
            self.vector_store._init_chroma()
        else:
            self.vector_store._fallback_docs.clear()
            self.vector_store._save_fallback()
        self._indexed_hashes.clear()
        return self.index_seed_data(seed_dir)

    def index_single_file_ast(self, file_path: str) -> dict[str, Any]:
        """Extracts AST nodes from a single source file and indexes them into the vector store.

        বাংলা মন্তব্য: ফাইল সেভ হওয়া মাত্রই AST নোডসমূহ পড়ে ভেক্টর ডাটাবেসে আপডেট করে।
        """
        docs = self._extract_documents_from_file(file_path)
        if not docs:
            return {"indexed": 0, "file": file_path, "status": "skipped_or_empty"}

        self.vector_store.add_documents(docs)
        return {"indexed": len(docs), "file": file_path, "status": "success"}
