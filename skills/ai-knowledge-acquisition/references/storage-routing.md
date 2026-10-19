# Storage routing (verify before use)

Never assume a tool works. Probe with a read-only call first and report the real result. A tool that is listed but returns an error is **unavailable**.

## Capability probe (read-only)
| Capability | Probe |
|---|---|
| Memory sidecar (facts, entities, document store, RAG) | `memory_status` → proceed only if `ready: true` |
| Vector index | `qdrant_collections` → lists collections if reachable |
| Anything else | one harmless read; record the outcome |

State of the SupremeAI deployment on the date this skill was built (2026-10-18): the Qdrant API answered and listed `error_patterns`, `supremeai_documents`, `supremeai_memory`; the memory sidecar reported `ready: false` because its backend directory was missing. Re-probe every session; this snapshot will go stale.

## Role of each store (use the minimum needed)
| Knowledge | Preferred store | Note |
|---|---|---|
| Short verified fact or principle | `memory_remember_fact` | `auto_store_ok` only |
| Entities and relationships (agent, tool, concept → relation) | `memory_create_entities`, `memory_create_relations` | when relations matter for retrieval |
| Long record or documentation | `memory_store_document` / `memory_ingest_document_rag` | keep the JSON record as the document body |
| Semantic retrieval | Qdrant `qdrant_upsert` (needs an embedding vector) | store the record id in the payload; do not fabricate vectors |
| Pending / unverified | staging: Qdrant payload `status: "staging"` or a local JSON file | never mix with authoritative memory |

Qdrant requires a real embedding vector. If no embedding tool is available, do not invent vectors; write the validated JSON to a file and report that indexing is pending.

## Fallback when no store works
Write validated records to `knowledge-records/<id>.json` (JSONL for batches) and tell the user plainly: "not saved to memory, saved as files for an authorized workflow." This is a correct outcome, not a failure.

## Write discipline
- Validate with `scripts/validate_record.py` first; write only what the tier allows.
- Include tenant/session context only if the tool injects it; do not guess tenant IDs.
- Do not store credentials, tokens or personal data in records. Redact them.
- Never delete or overwrite existing records; supersede them.
- Retrieve before writing: search for a duplicate or conflicting record so you can link it.
