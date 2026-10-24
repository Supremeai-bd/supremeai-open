"""Agent Registry — multi-AI agent governance Phase 1 (issue #1150).

বাংলা সারসংক্ষেপ:
------------------
ছোট, স্পষ্ট agent রেজিস্ট্রি — Admin প্রতিটি agent-এর জন্য সংজ্ঞা দেয়:
- id (slug), role/responsibility (মুক্ত-ফর্ম), assigned AI/provider (যে-কোনো
  ভেন্ডর — কোনো ভেন্ডর hardcode নেই), workspace branch, active flag।

Task ownership চুক্তি (#1150 Phase-1 §2): প্রতিটি task-এ —
task_id, assigned agent, expected scope, status, branch/workspace —
:meth:`AgentRegistry.ownership_record` এই রেকর্ড তৈরি করে।

নকশা-নীতি (issue-এর guiding rule): **"Working first, hardening second"** —
ফাইল-ব্যাকড YAML + ইন-মেমরি upsert, কোনো বড় orchestration ইঞ্জিন নয়।
Safety boundary হলো PR + CI (branch protection), MCP নয় — MCP মরলেও
workflow অক্ষত থাকে।

Env override: ``AGENT_ROLES_FILE`` (default backend/config/agent_roles.yaml)।
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any

import yaml  # type: ignore  # house pattern (cf. agents/syncguard)
from pydantic import BaseModel, Field

from core.logging_config import logger

DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "config" / "agent_roles.yaml"

# slug: অক্ষর/সংখ্যা/হাইফেন/আন্ডারস্কোর, ১-৬৪ অক্ষর — branch নামের সাথে বাসবে।
_AGENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
# branch: path-safe, '..' ও শুরুতে '-' নিষিদ্ধ (git ref injection বন্ধ)।
_BRANCH_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]{0,127}$")


class AgentRecord(BaseModel):
    """একটি agent-এর admin-সংজ্ঞায়িত পরিচয় (#1150 Phase-1 §1)।"""

    id: str = Field(..., description="slug — যেমন agent-1")
    role: str = Field(..., min_length=1, max_length=64, description="role/responsibility")
    provider: str = Field(
        ..., min_length=1, max_length=64, description="assigned AI/provider — যে-কোনো ভেন্ডর"
    )
    workspace_branch: str = Field(..., description="agent নিজস্ব branch — কখনো সরাসরি main নয়")
    active: bool = True
    notes: str = Field(default="", max_length=500)


class AgentRegistry:
    """YAML-ব্যাকড রেজিস্ট্রি — thread-safe, fail-closed validation।"""

    def __init__(self, path: Path | str | None = None) -> None:
        env_path = os.getenv("AGENT_ROLES_FILE", "").strip()
        self.path = Path(path or env_path or DEFAULT_REGISTRY_PATH)
        self._lock = threading.Lock()
        self._agents: dict[str, AgentRecord] = {}
        self._load()

    # ── Load / persist ───────────────────────────────────────────────────────
    def _load(self) -> None:
        if not self.path.exists():
            logger.warning(f"[AgentRegistry] file missing: {self.path} — empty registry")
            return
        try:
            raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise RuntimeError(f"[AgentRegistry] invalid YAML in {self.path}: {exc}") from exc
        agents = raw.get("agents") or []
        with self._lock:
            self._agents = {}
            for item in agents:
                record = AgentRecord.model_validate(item)
                self._agents[record.id] = record
        logger.info(f"[AgentRegistry] loaded {len(self._agents)} agent(s) from {self.path}")

    def _persist(self) -> None:
        """বর্তমান state ফাইলে লেখো (atomic-ish: আগে tmp, পরে rename)।"""
        data = {
            "version": "1",
            "agents": [a.model_dump() for a in sorted(self._agents.values(), key=lambda r: r.id)],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".yaml.tmp")
        tmp.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        tmp.replace(self.path)

    # ── Query ────────────────────────────────────────────────────────────────
    def list_agents(self, active_only: bool = False) -> list[AgentRecord]:
        with self._lock:
            agents = list(self._agents.values())
        if active_only:
            agents = [a for a in agents if a.active]
        return sorted(agents, key=lambda r: r.id)

    def get(self, agent_id: str) -> AgentRecord | None:
        with self._lock:
            return self._agents.get(agent_id)

    # ── Admin mutations ──────────────────────────────────────────────────────
    @staticmethod
    def validate_identity(agent_id: str, branch: str) -> None:
        """id ও branch-এর গঠনগত যাচাই — খারাপ ইনপুটে বানাই ValueError।"""
        if not _AGENT_ID_RE.match(agent_id or ""):
            raise ValueError(f"invalid agent id: {agent_id!r}")
        if branch in ("main", "master") or not _BRANCH_RE.match(branch or ""):
            raise ValueError(
                f"invalid workspace branch: {branch!r} (main/master forbidden for agents)"
            )

    def upsert(self, record: AgentRecord) -> AgentRecord:
        """Admin দ্বারা সংজ্ঞা যোগ/আপডেট (#1150: 'Admin can define Agent 1/2/3 roles')।"""
        self.validate_identity(record.id, record.workspace_branch)
        with self._lock:
            self._agents[record.id] = record
            self._persist()
        logger.info(
            f"[AgentRegistry] upserted agent {record.id} (role={record.role}, provider={record.provider})"
        )
        return record

    def remove(self, agent_id: str) -> bool:
        with self._lock:
            existed = self._agents.pop(agent_id, None) is not None
            if existed:
                self._persist()
        return existed

    # ── Task ownership (#1150 Phase-1 §2) ────────────────────────────────────
    def ownership_record(
        self,
        agent_id: str,
        task_id: str,
        expected_scope: str,
        status: str = "assigned",
        branch: str | None = None,
    ) -> dict[str, Any]:
        """একটি task-এর মালিকানা রেকর্ড — দুই agent নীরবে একই task ধরবে না।

        চুক্তি: task_id + assigned agent + expected scope + status + branch/workspace।
        ভুল agent/status হলে ValueError (fail-closed)।
        """
        agent = self.get(agent_id)
        if agent is None:
            raise ValueError(f"unknown agent: {agent_id!r}")
        if not task_id or not expected_scope:
            raise ValueError("task_id and expected_scope are required")
        valid_statuses = {"assigned", "in_progress", "in_review", "done", "cancelled"}
        if status not in valid_statuses:
            raise ValueError(f"status must be one of {sorted(valid_statuses)}")
        return {
            "task_id": task_id,
            "agent_id": agent.id,
            "expected_scope": expected_scope,
            "status": status,
            "branch": branch or agent.workspace_branch,
            "provider": agent.provider,
            "role": agent.role,
        }


_REGISTRY: AgentRegistry | None = None


def get_agent_registry() -> AgentRegistry:
    """প্রসেস-ব্যাপী singleton (টেস্ট নিজস্ব ইনস্ট্যান্স বানায়)।"""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = AgentRegistry()
    return _REGISTRY


__all__ = ["AgentRecord", "AgentRegistry", "get_agent_registry"]
