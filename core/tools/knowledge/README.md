# backend/tools/knowledge

This directory houses a comprehensive suite of modules dedicated to the extraction, indexing, and management of diverse forms of knowledge for the SupremeAI project. These tools are designed to empower AI agents by transforming raw data from various sources—including code repositories, git history, PDF documents, and web content—into structured, searchable, and actionable insights. The collective aim is to build a robust and accessible knowledge base that significantly enhances the contextual understanding, learning capabilities, and operational effectiveness of the AI system.

## Core Components

*   **`codebase_exporter.py`**: Exports structured information from a codebase for analysis or indexing.
*   **`git_knowledge_extractor.py`**: Analyzes git history to extract error-fix patterns and architecture learnings.
*   **`knowledge_base_indexer.py`**: Provides the `KnowledgeBaseIndexer` for managing a vector-based knowledge base, handling the extraction and indexing of structured and unstructured knowledge.
*   **`local_search_rag.py`**: Provides a local Retrieval Augmented Generation (RAG) system for AI agents, integrating web browsing with local persistent storage and retrieval mechanisms.
*   **`pdf_to_sdk.py`**: Provides tools to extract API specifications from PDF documents and generate client SDKs.
*   **`repo_deep_indexer.py`**: Provides a deep indexing tool
