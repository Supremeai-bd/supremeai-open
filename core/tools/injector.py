from __future__ import annotations

import hashlib
import json
import time
from typing import Any

try:
    from tools.knowledge.cards import ToolKnowledgeCard
except ImportError:
    from .cards import ToolKnowledgeCard


class ToolKnowledgeInjector:
    def __init__(self) -> None:
        self._memory_svc = None
        self._loaded = False

    def _load_memory(self) -> bool:
        if self._loaded:
            return self._memory_svc is not None
        try:
            from services.memory_service import CascadeMemoryService
            self._memory_svc = CascadeMemoryService()
            self._loaded = True
            return True
        except Exception as exc:
            print(f"[WARN] Could not load CascadeMemoryService: {exc}")
            self._loaded = True
            return False

    def inject(
        self,
        cards: list[ToolKnowledgeCard],
        dry_run: bool = True,
        update_only: bool = False,
    ) -> dict[str, Any]:
        """Inject knowledge cards into ai_memory.

        Args:
            cards: List of ToolKnowledgeCard instances to inject.
            dry_run: If True, preview only — no DB writes.
            update_only: If True, skip cards whose content hash hasn't changed since last injection.
        """
        results: dict[str, Any] = {
            "total": len(cards),
            "injected": 0,
            "skipped": 0,
            "unchanged": 0,
            "failed": 0,
            "dry_run": dry_run,
            "update_only": update_only,
            "items": [],
        }

        has_memory = False if dry_run else self._load_memory()

        for card in cards:
            content = card.to_memory_content()
            summary = card.to_summary()

            # Content-hash versioning — auto-bumps version when card content changes
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
            version = f"{card.version}+{content_hash}"

            status = "DRY_RUN"

            if not dry_run:
                if has_memory and self._memory_svc:
                    try:
                        # Deduplication: skip unchanged cards in update_only mode
                        if update_only:
                            try:
                                hits = self._memory_svc.query_context(
                                    prompt=f"tool_id:{card.tool_id}", top_k=1
                                )
                                if hits:
                                    stored_meta = hits[0].get("metadata") or {}
                                    if isinstance(stored_meta, str):
                                        try:
                                            stored_meta = json.loads(stored_meta)
                                        except Exception:
                                            stored_meta = {}
                                    if stored_meta.get("content_hash") == content_hash:
                                        status = "UNCHANGED"
                                        results["unchanged"] += 1
                                        results["items"].append({
                                            "tool_id": card.tool_id,
                                            "category": card.category,
                                            "status": status,
                                            "summary": summary,
                                        })
                                        continue
                            except Exception:
                                print('Silenced error in except block')  # If dedup check fails, proceed with injection

                        self._memory_svc.store_memory(
                            file_path=card.file_path,
                            content=content,
                            summary=summary,
                            structure=json.dumps({
                                "tool_id": card.tool_id,
                                "category": card.category,
                                "cognitive_intents": card.cognitive_intents,
                                "chain_before": card.chain_before,
                                "chain_after": card.chain_after,
                                "confidence_weight": card.confidence_weight,
                                "requires_network": card.requires_network,
                                "cost_tokens": card.cost_tokens,
                                "version": version,
                                "tags": card.tags,
                            }),
                            session_id="tool_knowledge_injector_v2",
                            agent_type="knowledge_injector",
                            task_type="tool_registry",
                            metadata={
                                "tool_id": card.tool_id,
                                "category": card.category,
                                "content_hash": content_hash,
                                "injected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                "version": version,
                            },
                        )
                        status = "INJECTED"
                        results["injected"] += 1
                    except Exception as exc:
                        status = f"FAILED: {exc}"
                        results["failed"] += 1
                else:
                    status = "SKIPPED_NO_DB"
                    results["skipped"] += 1
            else:
                results["injected"] += 1

            results["items"].append({
                "tool_id": card.tool_id,
                "category": card.category,
                "status": status,
                "summary": summary,
            })

        return results

    def verify_recall(self, test_queries: list[str]) -> list[dict[str, Any]]:
        """Verify injected knowledge can be recalled semantically."""
        if not self._load_memory() or not self._memory_svc:
            return [{"query": q, "result": "NO_DB", "hits": 0} for q in test_queries]

        recall_results = []
        for query in test_queries:
            try:
                hits = self._memory_svc.query_context(prompt=query, top_k=3)
                recall_results.append({
                    "query": query,
                    "hits": len(hits),
                    "top_result": hits[0].get("summary", "N/A")[:100] if hits else "NONE",
                })
            except Exception as exc:
                recall_results.append({"query": query, "result": str(exc), "hits": 0})
        return recall_results

    @staticmethod
    def build_verification_queries() -> list[str]:
        """Returns a comprehensive query set covering all 24 knowledge card categories."""
        return [
            # RADAR / Audit
            "find gaps in codebase and missing tests",
            "detect documentation drift and stale README",
            "analyze project DNA and codebase fingerprint",
            "replay incident from error log to find root cause",
            "mine failure patterns from CI history",
            # SHIELD / Security
            "check if file is safe to modify governance policy",
            "verify artifact sha256 hash before install",
            "prevent knowledge memory poisoning attack",
            "pre-deploy safety gate validation",
            # ENGINE / Discovery + Synthesis
            "search github pypi npm for open source solution",
            "score source trustworthiness and evidence quality",
            "apply auto fix patch to repair code bug",
            "multi model adversarial knowledge distillation",
            "choose cheapest AI model for this task budget routing",
            "create new reusable skill from repeated workflow",
            # ORCHESTRATOR
            "run full autonomous cognitive repair pipeline",
            "which script to run when CI fails",
            "when to split pipeline into parallel branches",
            "compile dynamic tool chain pipeline recipe",
            # MEMORY / Knowledge OS
            "quarantine and verify new knowledge before admission",
            "resolve conflicting knowledge find canonical truth",
            "when to re-inject knowledge cards to ai memory",
            # LIFECYCLE
            "how often should I run gap finder audit",
            "continuous self healing background watchdog daemon",
        ]
