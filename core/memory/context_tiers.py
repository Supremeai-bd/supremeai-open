"""Hierarchical context tiers (#4051 — Roadmap v2 §3.1, OpenViking-inspired).

বাংলা নোট: L0 শুধু memory নয় — এটা *governance context*। AGENTS.md +
AGENT_RULES.md + SECURITY.md সবসময় loaded থাকবে এবং সব আচরণকে নিয়ন্ত্রিত
রাখবে। L0-তে যেকোনো পরিবর্তন = Tier-3 constitutional change → ADMIN_DECISION
ছাড়া করা যাবে না (AGENT_RULES §6)।

Tier মডেল:
  L0 (Immutable / Constitutional) — সবসময় loaded, parsed (raw dump নয়)
  L1 (Active Task Context)        — claim/assign হলে loaded (task contract)
  L2 (Retrieved Experience)       — on-demand, similarity-ranked, tenant-scoped

Budget নীতি (acceptance): total window budget-এ allocation ক্রম L0 > L1 > L2 —
L0 আগে reserved, তারপর L1, বাকিটা L2 পায়। কোনো tier বাজেট ছাড়িয়ে গেলে
sentence-boundary truncation (core.llm.token_budget-এর single owner) হয়।

Design guardrails (AGENT_RULES P1/P2):
  * নতুন vector store / retrieval system তৈরি হয়নি — L2 বিদ্যমান
    ExperienceDatabase.find_similar() + MemoryRepository.search_similar() ব্যবহার
    করে (SSOT reuse; second retrieval stack নিষিদ্ধ)।
  * Token estimation বিদ্যমান core.llm.token_budget মডিউলের — duplicate estimator নেই।
  * Composition log-এ কনটেন্ট লগ হয় না — শুধু per-tier token count (PII-safe)।
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from core.llm.token_budget import estimate_tokens, truncate_to_token_limit
from core.logging_config import logger
from learning.skill_template_writer import read_regression_guards, read_skill_templates

__all__ = [
    "TierLevel",
    "TierSection",
    "ConstitutionDrift",
    "L0Context",
    "L1Context",
    "L2Context",
    "RetrievalSourceTrace",
    "RetrievalTrace",
    "ComposedContext",
    "compose_agent_context",
]

# বাংলা (#4051): repo root — backend/memory/context_tiers.py থেকে দুই ধাপ উপরে।
REPO_ROOT = Path(__file__).resolve().parents[2]

# L0 constitutional sources — parsed, raw dump নয় (acceptance #2)।
CONSTITUTION_FILES: tuple[str, ...] = ("AGENTS.md", "AGENT_RULES.md", "SECURITY.md")

# বাংলা (#4051): L0-ই constitutional context — এর পরিবর্তন সবসময় Tier-3
# admin approval দাবী করবে। এটা hard policy constant, caller override করতে পারবে না।
L0_CHANGE_REQUIRES_ADMIN_APPROVAL = True


class TierLevel(StrEnum):
    """Context tier শনাক্তকারী — L0 governance / L1 task / L2 experience।"""

    L0 = "L0"
    L1 = "L1"
    L2 = "L2"


@dataclass(frozen=True)
class TierSection:
    """একটি parsed অংশ — heading + body (L0-তে markdown `##` section)।"""

    heading: str
    body: str


def _parse_markdown_sections(text: str) -> list[TierSection]:
    """Markdown-কে `##` heading ধরে section-এ ভাগ করে (parsed, not raw)।

    বাংলা: front-matter/title block (# single-hash) preamble হিসেবে থাকে;
    `##` heading না পেলে পুরো ফাইল একটি single "preamble" section হয়।
    """
    sections: list[TierSection] = []
    current_heading = "preamble"
    current_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections.append(
                    TierSection(
                        heading=current_heading,
                        body="\n".join(current_lines).strip(),
                    )
                )
            current_heading = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        body = "\n".join(current_lines).strip()
        if body or current_heading != "preamble":
            sections.append(TierSection(heading=current_heading, body=body))

    return sections


@dataclass
class ConstitutionDrift:
    """L0 constitutional hash পরিবর্তনের সনাক্তকরণ ফল।

    changed=True মানে L0 content বদলেছে — Tier-3 ADMIN_DECISION ছাড়া
    এই পরিবর্তন গ্রহণযোগ্য নয় (AGENT_RULES §6)। requires_admin_approval
    সবসময় True — এটা policy, এটা কেউ কনফিগার করে False করতে পারবে না।
    """

    changed: bool
    previous_hash: str | None
    current_hash: str
    requires_admin_approval: bool = L0_CHANGE_REQUIRES_ADMIN_APPROVAL

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "previous_hash": self.previous_hash,
            "current_hash": self.current_hash,
            "requires_admin_approval": self.requires_admin_approval,
        }


@dataclass
class L0Context:
    """Constitutional tier — সবসময় loaded (acceptance: "L0 always loaded")।"""

    sections: list[TierSection] = field(default_factory=list)
    token_count: int = 0
    constitution_hash: str = ""
    source_files: tuple[str, ...] = ()
    missing_files: tuple[str, ...] = ()

    @classmethod
    def load(cls, repo_root: Path | None = None) -> L0Context:
        """AGENTS.md + AGENT_RULES.md + SECURITY.md parse করে L0 গঠন করে।

        বাংলা: fail-honest — কোনো constitutional ফাইল পাওয়া না গেলে সেটা
        missing_files-এ ঘোষণা হয়, চুপচাপ ঢাকা হয় না (U2 Truth & Evidence)।
        প্রতিটি ফাইলের প্রতিটি section-এর heading এ "file::heading" আকারে
        রাখা হয় যাতে source ট্রেসযোগ্য থাকে।
        """
        root = repo_root or REPO_ROOT
        sections: list[TierSection] = []
        used: list[str] = []
        missing: list[str] = []

        for name in CONSTITUTION_FILES:
            path = root / name
            if not path.exists():
                missing.append(name)
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                # বাংলা: পড়া গেল না — fail-honest missing হিসেবে ঘোষণা।
                logger.warning(f"[context_tiers] L0 source unreadable: {name}: {exc}")
                missing.append(name)
                continue
            used.append(name)
            for sec in _parse_markdown_sections(text):
                sections.append(TierSection(heading=f"{name}::{sec.heading}", body=sec.body))

        hash_src = "\n".join(f"{s.heading}\n{s.body}" for s in sections)
        constitution_hash = hashlib.sha256(hash_src.encode("utf-8")).hexdigest()

        ctx = cls(
            sections=sections,
            token_count=sum(estimate_tokens(s.body) for s in sections),
            constitution_hash=constitution_hash,
            source_files=tuple(used),
            missing_files=tuple(missing),
        )
        if missing:
            logger.warning(f"[context_tiers] L0 missing constitutional files: {sorted(missing)}")
        return ctx

    def drift_check(self, previous_hash: str | None) -> ConstitutionDrift:
        """পূর্ববর্তী constitution hash-এর সাথে তুলনা — Tier-3 gate ইনপুট।"""
        return ConstitutionDrift(
            changed=previous_hash is not None and previous_hash != self.constitution_hash,
            previous_hash=previous_hash,
            current_hash=self.constitution_hash,
        )

    def render(self, max_tokens: int | None = None) -> str:
        """Section-গুলো heading-সহ রেন্ডার করে; বাজেট দিলে truncate করে।"""
        text = "\n\n".join(f"## {s.heading}\n{s.body}" for s in self.sections)
        if max_tokens is not None:
            text = truncate_to_token_limit(text, max_tokens)
        return text


@dataclass
class L1Context:
    """Active task tier — claim/assign হলেই গঠিত হয় (acceptance #4)।"""

    task_id: str = ""
    issue: int | None = None
    objective: str = ""
    role_policy: str = ""
    touching_files: tuple[str, ...] = ()
    acceptance: tuple[str, ...] = ()
    token_count: int = 0
    truncated: bool = False

    @classmethod
    def from_task_contract(cls, contract: dict[str, Any]) -> L1Context:
        """Standard Task Contract (AGENT_RULES §7) থেকে L1 গঠন করে।

        বাংলা: contract খালি/None হলে খালি L1 — চুপচাপ placeholder বানানো হয় না।
        """
        if not isinstance(contract, dict):
            contract = {}
        scope = contract.get("scope") or {}
        touching = scope.get("touching_files") or []
        acceptance = contract.get("acceptance") or []

        ctx = cls(
            task_id=str(contract.get("task_id", "") or ""),
            issue=contract.get("issue"),
            objective=str(contract.get("objective", "") or ""),
            role_policy=str(contract.get("role_policy", "") or ""),
            touching_files=tuple(str(f) for f in touching),
            acceptance=tuple(str(a) for a in acceptance),
        )
        ctx.token_count = estimate_tokens(ctx.render())
        return ctx

    def render(self, max_tokens: int | None = None) -> str:
        parts: list[str] = [f"# Active Task: {self.task_id or 'unnamed'}"]
        if self.issue is not None:
            parts.append(f"Issue: #{self.issue}")
        if self.objective:
            parts.append(f"Objective: {self.objective}")
        if self.role_policy:
            parts.append(f"Role policy: {self.role_policy}")
        if self.touching_files:
            parts.append("Touching files:\n" + "\n".join(f"- {f}" for f in self.touching_files))
        if self.acceptance:
            parts.append("Acceptance criteria:\n" + "\n".join(f"- {a}" for a in self.acceptance))
        text = "\n\n".join(parts)
        if max_tokens is not None:
            text = truncate_to_token_limit(text, max_tokens)
        return text


@dataclass
class RetrievalSourceTrace:
    """একটি store-এর retrieval trajectory — কনটেন্ট-মুক্ত (#4080)।

    বাংলা: error_class শুধু ক্লাস-শনাক্তকারী (timeout/connect/unknown ইত্যাদি
    exception TYPE-এর নাম), বার্তা নয় — exception-এর ভেতরের কনটেন্ট কখনো
    trace-এ যায় না (privacy contract, verification #4)।
    """

    origin: str
    available: bool = True
    candidate_count: int = 0
    error_class: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "origin": self.origin,
            "available": self.available,
            "candidate_count": self.candidate_count,
            "error_class": self.error_class,
        }


@dataclass
class RetrievalTrace:
    """L2 retrieval provenance — কেন এই entries এই agent পেল (#4080)।

    বাংলা: OpenViking-এর retrieval-trajectory নীতি — ভুল memory এলে অপারেটর
    বলতে পারবেন সমস্যাটা retrieval-quality-র নাকি merge/dedup-এর নাকি budget-এর।

    Privacy contract (issue §Governance):
      * raw query নয় — শুধু sha256 prefix;
      * raw memory body/prompt/secret কখনো নয় — শুধু rank/score/counts;
      * tenant_id নয় — শুধু scope decision (allowed / fail_closed);
      * degraded/error অবস্থা দৃশ্যমান, কিন্তু exception বার্তা নয়।
    """

    query_hash: str = ""  # sha256(query)[:16]
    tenant_scope: str = "unknown"  # allowed | fail_closed_no_tenant | skipped_empty_query
    sources: list[RetrievalSourceTrace] = field(default_factory=list)
    candidates_before_merge: int = 0
    dedup_removed: int = 0
    selected: list[dict[str, Any]] = field(default_factory=list)  # {rank, origin, similarity}
    pre_budget_tokens: int = 0
    post_budget_tokens: int = 0
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_hash": self.query_hash,
            "tenant_scope": self.tenant_scope,
            "sources": [s.to_dict() for s in self.sources],
            "candidates_before_merge": self.candidates_before_merge,
            "dedup_removed": self.dedup_removed,
            "selected": list(self.selected),
            "pre_budget_tokens": self.pre_budget_tokens,
            "post_budget_tokens": self.post_budget_tokens,
            "truncated": self.truncated,
        }


def _error_class(exc: Exception) -> str:
    """Exception TYPE নাম — বার্তা নয় (PII-safe provenance, #4080)।"""
    return type(exc).__name__


@dataclass
class L2Context:
    """Retrieved experience tier — on-demand, similarity-ranked, tenant-scoped।

    বাংলা (#4051): retrieval বিদ্যমান দুই স্টোরের উপর দিয়ে যায় —
      * adaptive_engine.experience_db.ExperienceDatabase.find_similar()
      * core.ai_memory.repository.MemoryRepository.search_similar()
    ফল merge + similarity-desc sort + dedup করা হয়। Policy Engine scope:
    tenant_id (user_id) বাধ্যতামূলক — না থাকলে খালি L2 (fail-closed)।
    """

    entries: list[dict[str, Any]] = field(default_factory=list)
    token_count: int = 0
    truncated: bool = False
    tenant_id: str | None = None
    degraded: bool = False
    skip_reason: str = ""
    # বাংলা (#4080): provenance — কোন store থেকে কী এল, কে বাদ/নির্বাচিত।
    trace: RetrievalTrace = field(default_factory=RetrievalTrace)

    @classmethod
    async def retrieve(
        cls,
        query: str,
        tenant_id: str | None,
        top_k: int = 5,
        threshold: float = 0.7,
        experience_db: Any | None = None,
        memory_repo: Any | None = None,
    ) -> L2Context:
        """Query দিয়ে top-K experience retrieve করে (tenant scope fail-closed)।

        বাংলা: experience_db.find_similar sync, memory_repo.search_similar async —
        দুটোই optional inject করা যায় (টেস্টে mock)। কোনো store ব্যর্থ হলে
        degraded=True + সৎ লগ; কখনো কলার ক্র্যাশ করানো হয় না (graceful
        degradation — AGENT_RULES §13)।
        """
        # Policy Engine scope (acceptance #7): tenant ছাড়া L2 নেই।
        if not tenant_id:
            trace = RetrievalTrace(
                query_hash=hashlib.sha256(query.encode("utf-8")).hexdigest()[:16] if query else "",
                tenant_scope="fail_closed_no_tenant",
            )
            return cls(tenant_id=None, skip_reason="no_tenant_scope", trace=trace)

        if not query or not query.strip():
            return cls(
                tenant_id=tenant_id,
                skip_reason="empty_query",
                trace=RetrievalTrace(query_hash="", tenant_scope="skipped_empty_query"),
            )

        # বাংলা (#4080): provenance trace — কনটেন্ট-মুক্ত, শুধু সিদ্ধান্ত-মেটাডেটা।
        trace = RetrievalTrace(
            query_hash=hashlib.sha256(query.encode("utf-8")).hexdigest()[:16],
            tenant_scope="allowed",
        )

        merged: list[dict[str, Any]] = []
        degraded = False

        # ── Experience DB (adaptive_engine) ─────────────────────────────
        exp_source = RetrievalSourceTrace(origin="experience_db")
        if experience_db is None:
            try:
                from adaptive_engine.experience_db import ExperienceDatabase

                experience_db = ExperienceDatabase()
            except Exception as exc:  # pragma: no cover - store init failure path
                logger.warning(f"[context_tiers] L2 experience_db unavailable: {exc}")
                experience_db = None
                degraded = True
                exp_source.available = False
                exp_source.error_class = _error_class(exc)

        if experience_db is not None:
            try:
                hits = experience_db.find_similar(
                    query, limit=top_k, threshold=threshold, user_id=tenant_id
                )
                for h in hits or []:
                    entry = dict(h)
                    entry.setdefault("similarity", float(h.get("similarity", 0.0) or 0.0))
                    entry["origin"] = "experience_db"
                    merged.append(entry)
                exp_source.candidate_count = len(hits or [])
            except Exception as exc:
                degraded = True
                exp_source.available = False
                exp_source.error_class = _error_class(exc)
                logger.warning(
                    f"[context_tiers] L2 experience_db query failed: {_error_class(exc)}"
                )
        trace.sources.append(exp_source)

        # ── AI memory repository (core.ai_memory) ───────────────────────
        mem_source = RetrievalSourceTrace(origin="ai_memory")
        if memory_repo is None:
            try:
                from core.ai_memory.repository import get_memory_repository

                memory_repo = get_memory_repository()
            except Exception as exc:  # pragma: no cover - store init failure path
                logger.warning(f"[context_tiers] L2 memory_repo unavailable: {exc}")
                memory_repo = None
                degraded = True
                mem_source.available = False
                mem_source.error_class = _error_class(exc)

        if memory_repo is not None:
            try:
                mem_hits = await memory_repo.search_similar(
                    query_text=query,
                    user_id=tenant_id,
                    limit=top_k,
                )
                for h in mem_hits or []:
                    entry = dict(h)
                    entry.setdefault("similarity", float(h.get("similarity", 0.0) or 0.0))
                    entry["origin"] = "ai_memory"
                    merged.append(entry)
                mem_source.candidate_count = len(mem_hits or [])
            except Exception as exc:
                degraded = True
                mem_source.available = False
                mem_source.error_class = _error_class(exc)
                logger.warning(f"[context_tiers] L2 memory_repo query failed: {_error_class(exc)}")
        trace.sources.append(mem_source)
        trace.candidates_before_merge = len(merged)

        # similarity-desc rank + dedup (content fingerprint)
        merged.sort(key=lambda e: e.get("similarity", 0.0), reverse=True)
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for e in merged:
            key = str(e.get("id") or e.get("memory_id") or e.get("content", "")[:128])
            if key in seen:
                trace.dedup_removed += 1
                continue
            seen.add(key)
            deduped.append(e)
        deduped = deduped[:top_k]

        # বাংলা (#4080): selection provenance — rank/origin/similarity, কনটেন্ট নয়।
        for rank, e in enumerate(deduped, start=1):
            trace.selected.append(
                {
                    "rank": rank,
                    "origin": e.get("origin", "experience"),
                    "similarity": round(float(e.get("similarity", 0.0) or 0.0), 4),
                }
            )

        return cls(
            entries=deduped,
            token_count=cls._entries_tokens(deduped),
            tenant_id=tenant_id,
            degraded=degraded,
            trace=trace,
        )

    @staticmethod
    def _entries_tokens(entries: list[dict[str, Any]]) -> int:
        total = 0
        for e in entries:
            content = str(e.get("content") or e.get("action_taken") or "")
            total += estimate_tokens(content)
        return total

    def render(self, max_tokens: int | None = None) -> str:
        if not self.entries:
            return ""
        lines = []
        for e in self.entries:
            content = str(e.get("content") or e.get("action_taken") or "").strip()
            if not content:
                continue
            sim = e.get("similarity")
            lines.append(f"- ({e.get('origin', 'experience')}, sim={sim:.2f}) {content}")
        text = "\n".join(lines)
        if max_tokens is not None:
            self.truncated = True
            text = truncate_to_token_limit(text, max_tokens)
        return text


@dataclass
class ComposedContext:
    """L0+L1+L2 composition ফল — per-tier token accounting সহ।"""

    l0: L0Context
    l1: L1Context | None = None
    l2: L2Context | None = None
    budget: int = 0
    total_tokens: int = 0
    l0_tokens: int = 0
    l1_tokens: int = 0
    l2_tokens: int = 0
    truncated: dict[str, bool] = field(default_factory=dict)
    # Roadmap v2.0 Phase 3 step-4 (#4145): learned knowledge injected from
    # knowledge/skills + regression_guards (#4054 templates — finally READ).
    learned_skills: list[dict[str, Any]] = field(default_factory=list)

    def to_log_dict(self) -> dict[str, Any]:
        """PII-safe composition summary — কনটেন্ট নয়, শুধু counts (acceptance #8)।"""
        out: dict[str, Any] = {
            "event": "context_composition",
            "budget": self.budget,
            "total_tokens": self.total_tokens,
            "l0_tokens": self.l0_tokens,
            "l1_tokens": self.l1_tokens,
            "l2_tokens": self.l2_tokens,
            "l0_sections": len(self.l0.sections),
            "l1_loaded": self.l1 is not None,
            "l2_entries": len(self.l2.entries) if self.l2 else 0,
            "l2_degraded": self.l2.degraded if self.l2 else False,
            "truncated": self.truncated,
        }
        # বাংলা (#4080): retrieval provenance-ও composition log-এ যায় —
        # একই PII-safe চুক্তি (hash/scope/counts, কোনো কনটেন্ট নয়)।
        if self.l2 is not None:
            out["l2_trace"] = self.l2.trace.to_dict()
        return out

    def render(self) -> str:
        """সম্পূর্ণ tiered context — L0 → L1 → L2 ক্রমে।"""
        parts = [
            "[L0 — Governance Context (always loaded)]",
            self.l0.render(),
        ]
        if self.l1 is not None:
            parts.append("[L1 — Active Task Context]")
            parts.append(self.l1.render())
        if self.l2 is not None and self.l2.entries:
            parts.append("[L2 — Retrieved Experience]")
            parts.append(self.l2.render())
        return "\n\n".join(p for p in parts if p and p.strip())


async def compose_agent_context(
    task_contract: dict[str, Any] | None,
    retrieval_query: str | None = None,
    tenant_id: str | None = None,
    total_budget: int = 4096,
    experience_db: Any | None = None,
    memory_repo: Any | None = None,
    repo_root: Path | None = None,
) -> ComposedContext:
    """তিন tier একসাথে compose করে — budget L0 > L1 > L2 ক্রমে allocate হয়।

    বাংলা (acceptance #6): L0 আগে fully reserved হয় (constitutional context
    কখনো budget-এর বাইরে পড়ে না), তারপর L1, অবশিষ্ট বাজেট L2 পায়।
    Composition প্রতিটি ধাপে structured log ছাড়ে (debug সাপোর্ট, কনটেন্ট-হীন)।
    """
    if total_budget <= 0:
        raise ValueError(f"total_budget must be positive, got {total_budget}")

    # ── L0: সবসময় (acceptance #1) ──────────────────────────────────────
    l0 = L0Context.load(repo_root=repo_root)
    l0_tokens = l0.token_count
    l0_truncated = False
    remaining = total_budget
    if l0_tokens > remaining:
        # বাংলা: L0-ই বাজেট ছাপ্পান্নো হলে truncate — কিন্তু সৎ warning।
        l0_truncated = True
        logger.warning(
            f"[context_tiers] L0 ({l0_tokens} tok) exceeds budget ({total_budget}) "
            "— constitutional context truncated; consider raising total_budget"
        )
        l0_tokens = remaining
    remaining -= l0_tokens

    # ── L1: task assign হলে ─────────────────────────────────────────────
    l1: L1Context | None = None
    l1_tokens = 0
    l1_truncated = False
    if task_contract:
        l1 = L1Context.from_task_contract(task_contract)
        if l1.token_count > remaining:
            l1_truncated = True
            l1_tokens = remaining
        else:
            l1_tokens = l1.token_count
        remaining -= l1_tokens

    # ── Learned-knowledge injection (#4054 step-4 / Roadmap Phase 3, #4145) ──
    # task assign হলে similar skill templates + regression guards compose-এ
    # যোগ হয় — budget-aware (L0/L1 আগে; learned বরাদ্দ L2 retrieval-এর আগেই
    # কাটা হয় যেন retrieval বাজেট ছাপিয়ে না যায়)।
    learned: list[dict[str, Any]] = []
    learned_tokens = 0
    if task_contract:
        _tt = str(
            task_contract.get("task_type") or (task_contract.get("task") or {}).get("type") or ""
        )
        learned = read_skill_templates(_tt, repo_root=repo_root) + read_regression_guards(
            _tt, repo_root=repo_root
        )
        learned_tokens = sum(len(str(s)) // 4 for s in learned)
        if learned_tokens > remaining:
            logger.warning(
                f"[context_tiers] learned knowledge ({learned_tokens} tok) "
                f"exceeds remaining budget ({remaining}) — dropped (fail-honest)"
            )
            learned = []
            learned_tokens = 0
        else:
            remaining -= learned_tokens

    # ── L2: on-demand retrieval, অবশিষ্ট বাজেট পায় ─────────────────────
    l2: L2Context | None = None
    l2_tokens = 0
    l2_truncated = False
    if retrieval_query:
        l2 = await L2Context.retrieve(
            retrieval_query,
            tenant_id=tenant_id,
            experience_db=experience_db,
            memory_repo=memory_repo,
        )
        # বাংলা (#4080): budget-এর আগে/পরে token সংখ্যা trace-এ সংরক্ষিত —
        # "memory কাটা পড়ল" বনাম "retrieval-ই খারাপ" আলাদা করা যায়।
        l2.trace.pre_budget_tokens = l2.token_count
        l2_tokens = min(l2.token_count, remaining)
        if l2.token_count > remaining:
            l2_truncated = True
            l2.trace.truncated = True
        l2.trace.post_budget_tokens = l2_tokens

    composed = ComposedContext(
        l0=l0,
        l1=l1,
        l2=l2,
        budget=total_budget,
        total_tokens=l0_tokens + l1_tokens + l2_tokens + learned_tokens,
        l0_tokens=l0_tokens,
        l1_tokens=l1_tokens,
        l2_tokens=l2_tokens + learned_tokens,
        truncated={"L0": l0_truncated, "L1": l1_truncated, "L2": l2_truncated},
        learned_skills=learned,
    )

    # Acceptance #8: composition logged (which tiers loaded, token count per tier)।
    logger.info(f"[context_tiers] {composed.to_log_dict()}")

    return composed
