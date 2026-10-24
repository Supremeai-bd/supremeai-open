"""Provides a deep indexing tool for code repositories, extracting structural information and code snippets for storage and semantic search."""

import ast
import os
from typing import Any

from core.logging_config import logger


class RepoDeepIndexer:
    def __init__(self, vector_db_client=None):
        self.vector_db_client = vector_db_client
        logger.info("Initialized RepoDeepIndexer")

    def _parse_ast(self, file_path: str) -> dict[str, Any]:
        if file_path.endswith(".py"):
            try:
                with open(file_path, encoding="utf-8") as f:
                    source = f.read()
                tree = ast.parse(source)
                classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
                functions = [
                    node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                ]
                imports = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imports.extend(alias.name for alias in node.names)
                    elif isinstance(node, ast.ImportFrom):
                        imports.append(node.module)
                return {"classes": classes, "functions": functions, "imports": imports}
            except Exception as e:
                logger.debug(f"AST parse failed for {file_path}: {e}")
        return {"classes": [], "functions": [], "imports": []}

    async def index_repository(self, repo_path: str) -> dict[str, Any]:
        if not os.path.exists(repo_path):
            raise FileNotFoundError(f"Repository path not found: {repo_path}")

        logger.info(f"Starting deep index of repository: {repo_path}")

        indexed_files = 0
        nodes = []

        for root, _, files in os.walk(repo_path):
            for file in files:
                if file.endswith((".py", ".ts", ".tsx", ".js", ".go")):
                    file_path = os.path.join(root, file)
                    ast_data = self._parse_ast(file_path)
                    try:
                        with open(file_path, encoding="utf-8") as f:
                            snippet = f.read()[:200]
                    except Exception as e:
                        try:
                            import loguru

                            loguru.logger.error(f"Tool execution error: {e}")
                        except Exception as e:
                            logger.warning(f"Exception suppressed: {e}")
                        snippet = ""
                    node = {
                        "path": file_path,
                        "ast": ast_data,
                        "snippet": snippet,
                    }
                    nodes.append(node)
                    indexed_files += 1

        if self.vector_db_client:
            try:
                await self.vector_db_client.upsert(nodes)
            except Exception as e:
                logger.debug(f"Vector DB upsert skipped: {e}")

        logger.info(f"Successfully indexed {indexed_files} files.")
        return {
            "status": "success",
            "files_indexed": indexed_files,
            "nodes_extracted": len(nodes),
        }

    async def search_context(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        logger.info(f"Searching index for: {query}")
        try:
            if self.vector_db_client:
                return await self.vector_db_client.query(query, limit)
        except Exception as e:
            try:
                import loguru

                loguru.logger.error(f"Tool execution error: {e}")
            except Exception as e:
                logger.warning(f"Exception suppressed: {e}")
            pass
        return []
