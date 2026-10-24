"""MESH-4 Telegram command + callback handlers — issue #942 (P2-medium).

বাংলা সারসংক্ষেপ:
------------------
মেশ-বটের সব কমান্ড ও inline-button callback হ্যান্ডলার — pure logic স্তর,
Telegram HTTP আর Tower HTTP দুটোই injected ক্লায়েন্ট (টেস্টে mock করা যায়)।

কমান্ড (spec §Commands):
- /task <description>  — নতুন task → POST /api/v1/mesh/tasks (task_type="custom")
- /status              — সব active task + queue stats → GET /api/v1/mesh/tasks
- /nodes               — সংযুক্ত mesh agents + roles → GET /api/v1/nodes
- /cancel <task_id>    — চলমান task বাতিল → POST /api/v1/mesh/tasks/{id}/cancel
- /help, /start        — ব্যবহার-নির্দেশ

HITL callback (spec §Inline buttons):
- hitl:a:<n> → POST /api/v1/hitl/approve/{record_id}
- hitl:r:<n> → POST /api/v1/hitl/reject/{record_id}
- hitl:d:<n> → defer — পরে আবার জিজ্ঞেস হবে (৫ মিনিট), defer_limit পার হলে auto-reject

নিরাপত্তা: প্রতিটি কমান্ড/কলব্যাক আগে `config.is_admin_chat()` দিয়ে যাচাই —
fail-closed, অজানা chat-এ কোনো Tower কলই হবে না।

সম্পর্কিত: Master plan §৬ MESH-4 · Issue #942
"""

from __future__ import annotations

import time
from typing import Any

from core.logging_config import logger
from integrations.telegram_config import MeshTelegramConfig

# callback_data prefix — 64-byte Telegram সীমার জন্য record_id এর বদলে
# স্বল্প-সংখ্যক কী ব্যবহার হয় (registry: n → record_id)।
CB_APPROVE = "hitl:a:"
CB_REJECT = "hitl:r:"
CB_DEFER = "hitl:d:"

# status → (progress%, emoji) — /status ফরম্যাটিং টেবিল
_STATUS_PROGRESS: dict[str, tuple[int, str]] = {
    "pending": (0, "⏳"),
    "leased": (50, "🔧"),
    "done": (100, "✅"),
    "failed": (0, "❌"),
    "cancelled": (0, "🚫"),
}


class DeferStore:
    """HITL record প্রতি defer-state — in-memory (বট restart মানে তাজা শুরু, গ্রহণযোগ্য)।

    defers  = কতবার re-ask হয়েছে
    next_ask_epoch = পরের বার কখন জিজ্ঞেস করা হবে (monotonic wall-clock)
    """

    def __init__(self) -> None:
        self._state: dict[str, dict[str, int]] = {}

    def ensure(self, record_id: str, now_epoch: int) -> dict[str, int]:
        """না থাকলে তাজা state তৈরি করে দাও (defers=0, next_ask=এখনই)।"""
        return self._state.setdefault(record_id, {"defers": 0, "next_ask": now_epoch})

    def get(self, record_id: str) -> dict[str, int] | None:
        return self._state.get(record_id)

    def mark_asked(self, record_id: str, now_epoch: int, ask_timeout: int) -> int:
        """একটি ask সম্পন্ন — defers বাড়াও ও পরের ask সময় ঠিক করো; নতুন defers রিটার্ন।"""
        st = self.ensure(record_id, now_epoch)
        st["defers"] += 1
        st["next_ask"] = now_epoch + ask_timeout
        return st["defers"]

    def forget(self, record_id: str) -> None:
        """record terminal হলে (approve/reject/expired) state মুছে দাও।"""
        self._state.pop(record_id, None)

    def registered_ids(self) -> list[str]:
        return list(self._state.keys())


class KeyRegistry:
    """callback-স্বল্পকী (১,২,৩…) → HITL record_id ম্যাপ — Telegram 64-byte সীমা রক্ষার্থে।"""

    def __init__(self) -> None:
        self._next = 1
        self._map: dict[str, str] = {}

    def key_for(self, record_id: str) -> str:
        """record_id → স্থায়ী স্বল্পকী (একই record সবসময় একই কী পাবে)।"""
        for k, rid in self._map.items():
            if rid == record_id:
                return k
        key = str(self._next)
        self._next += 1
        self._map[key] = record_id
        return key

    def record_for(self, key: str) -> str | None:
        return self._map.get(key)


class MeshCommandHandlers:
    """কমান্ড হ্যান্ডলার — প্রতিটি মেথড Telegram-পাঠযোগ্য টেক্সট রিটার্ন করে।"""

    def __init__(
        self,
        config: MeshTelegramConfig,
        tower: Any,
    ) -> None:
        # tower: integrations.telegram_bot.TowerClient (circular import এড়াতে duck-typed)
        self.config = config
        self.tower = tower

    # ── /task ────────────────────────────────────────────────────────────────
    async def handle_task(self, description: str) -> str:
        """/task <description> — Tower queue-তে নতুন task জমা।"""
        description = (description or "").strip()
        if not description:
            return "⚠️ ব্যবহার: /task <বর্ণনা>\nউদাহরণ: /task add rate limiting to public API"
        body = {
            "task_type": "custom",
            "title": description[:200],
            "payload": {"source": "telegram"},
            "priority": 5,
        }
        code, data = await self.tower.request("POST", "/api/v1/mesh/tasks", json_body=body)
        if code != 201:
            return f"❌ Task তৈরি ব্যর্থ (HTTP {code}): {self._safe_detail(data)}"
        task_id = data.get("task_id", "?")
        return f"✅ Task তৈরি হয়েছে\n🆔 {task_id}\n📋 {description[:120]}\n🎯 status: pending"

    # ── /status ──────────────────────────────────────────────────────────────
    async def handle_status(self) -> str:
        """/status — queue snapshot + active task তালিকা (progress% সহ)।"""
        code, data = await self.tower.request("GET", "/api/v1/mesh/tasks")
        if code != 200:
            return f"❌ Queue পড়া ব্যর্থ (HTTP {code}): {self._safe_detail(data)}"
        tasks = data.get("tasks", [])
        stats = data.get("stats", {})
        lines = ["📊 Mesh Queue Status", f"মোট: {data.get('count', len(tasks))}"]
        if stats:
            lines.append("খুঁটিনাটি: " + ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))
        active = [t for t in tasks if t.get("status") in ("pending", "leased")]
        if not active:
            lines.append("\n😴 কোনো active task নেই।")
        else:
            lines.append("")
            for t in active[:10]:  # Telegram মেসেজ 4096-char সীমা — শীর্ষ ১০ যথেষ্ট
                pct, emoji = _STATUS_PROGRESS.get(t.get("status", ""), (0, "•"))
                node = t.get("lease_node_id") or "—"
                lines.append(
                    f"{emoji} {t.get('task_id', '?')} [{t.get('status', '?')} {pct}%] "
                    f"agent:{node} — {t.get('title', '')[:60]}"
                )
            if len(active) > 10:
                lines.append(f"… আরও {len(active) - 10} টি")
        return "\n".join(lines)

    # ── /nodes ───────────────────────────────────────────────────────────────
    async def handle_nodes(self) -> str:
        """/nodes — সংযুক্ত mesh agents + roles (MESH-1 presence ডেটা)।"""
        code, data = await self.tower.request("GET", "/api/v1/nodes")
        if code != 200:
            return f"❌ Node list পড়া ব্যর্থ (HTTP {code}): {self._safe_detail(data)}"
        nodes = data.get("nodes", data if isinstance(data, list) else [])
        if not nodes:
            return "🕸️ কোনো সংযুক্ত node নেই।"
        lines = ["🕸️ Connected Mesh Agents", ""]
        for n in nodes[:15]:
            role = n.get("role") or "unassigned"
            status = n.get("status") or "unknown"
            icon = "🟢" if status in ("online", "active", "healthy") else "⚪"
            lines.append(f"{icon} {n.get('node_id', '?')} — role: {role}, status: {status}")
        return "\n".join(lines)

    # ── /cancel ──────────────────────────────────────────────────────────────
    async def handle_cancel(self, task_id: str) -> str:
        """/cancel <task_id> — pending/leased task বাতিল (operator action)।"""
        task_id = (task_id or "").strip()
        if not task_id:
            return "⚠️ ব্যবহার: /cancel <task_id>"
        code, data = await self.tower.request("POST", f"/api/v1/mesh/tasks/{task_id}/cancel")
        if code == 200:
            return f"🚫 Task বাতিল হয়েছে: {task_id}"
        if code == 404:
            return f"❓ Task পাওয়া যায়নি: {task_id}"
        if code == 422:
            return f"⚠️ বাতিল করা যায়নি (terminal state): {self._safe_detail(data)}"
        return f"❌ Cancel ব্যর্থ (HTTP {code}): {self._safe_detail(data)}"

    # ── /help ────────────────────────────────────────────────────────────────
    def handle_help(self) -> str:
        return (
            "🤖 SupremeAI Mesh Bot — কমান্ড\n"
            "/task <বর্ণনা> — নতুন task জমা দাও\n"
            "/status — active task + queue stats\n"
            "/nodes — সংযুক্ত agents + roles\n"
            "/cancel <task_id> — task বাতিল\n"
            "HITL অনুমোদন: কার্ডের ✅/❌/⏸ বাটন ব্যবহার করো\n"
            f"(⏸ defer সীমা: {self.config.defer_limit}, re-ask: {self.config.hitl_ask_timeout_sec}s)"
        )

    @staticmethod
    def _safe_detail(data: Any) -> str:
        """Tower error body থেকে নিরাপদে detail বের করা (কখনো crash নয়)।"""
        if isinstance(data, dict):
            return str(data.get("detail", data))[:200]
        return str(data)[:200]


class MeshCallbackHandlers:
    """Inline-button callback হ্যান্ডলার — Approve/Reject/Defer (HITL)।"""

    def __init__(
        self,
        config: MeshTelegramConfig,
        tower: Any,
        registry: KeyRegistry,
        defers: DeferStore,
    ) -> None:
        self.config = config
        self.tower = tower
        self.registry = registry
        self.defers = defers

    async def handle_callback(self, data: str) -> str:
        """callback_data রাউট — রিটার্ন মান admin-কে দেখানো answer টেক্সট।"""
        if data.startswith(CB_APPROVE):
            return await self._approve(data[len(CB_APPROVE) :])
        if data.startswith(CB_REJECT):
            return await self._reject(data[len(CB_REJECT) :])
        if data.startswith(CB_DEFER):
            return await self._defer(data[len(CB_DEFER) :])
        return "⚠️ অজানা callback"

    async def _approve(self, key: str) -> str:
        record_id = self.registry.record_for(key)
        if not record_id:
            return "⚠️ এই অনুমোদন-কার্ড আর বৈধ নয় (বট restart হয়েছে)।"
        if not self.config.tower_admin_token:
            return "🚫 TOWER_ADMIN_TOKEN কনফিগার নেই — দূর থেকে approve করা যাবে না (fail-closed)।"
        body = {"reason": "approved via Telegram mesh bot", "resolved_by": "telegram-admin"}
        code, data = await self.tower.request(
            "POST", f"/api/v1/hitl/approve/{record_id}", json_body=body
        )
        if code == 200:
            self.defers.forget(record_id)
            logger.info(f"[MESH-TG] HITL approved via Telegram: {record_id}")
            return f"✅ অনুমোদিত: {record_id}"
        if code == 409:
            return f"⚠️ আর অনুমোদনযোগ্য নয় (already decided/expired): {record_id}"
        if code == 410:
            return f"⌛ অনুমোদনের মেয়াদ শেষ: {record_id}"
        return f"❌ Approve ব্যর্থ (HTTP {code}): {MeshCommandHandlers._safe_detail(data)}"

    async def _reject(self, key: str) -> str:
        record_id = self.registry.record_for(key)
        if not record_id:
            return "⚠️ এই কার্ড আর বৈধ নয়।"
        if not self.config.tower_admin_token:
            return "🚫 TOWER_ADMIN_TOKEN কনফিগার নেই — দূর থেকে reject করা যাবে না (fail-closed)।"
        body = {"reason": "rejected via Telegram mesh bot", "resolved_by": "telegram-admin"}
        code, data = await self.tower.request(
            "POST", f"/api/v1/hitl/reject/{record_id}", json_body=body
        )
        if code == 200:
            self.defers.forget(record_id)
            logger.info(f"[MESH-TG] HITL rejected via Telegram: {record_id}")
            return f"❌ প্রত্যাখ্যাত: {record_id}"
        if code in (409, 410):
            return f"⚠️ আর সিদ্ধান্তযোগ্য নয়: {record_id}"
        return f"❌ Reject ব্যর্থ (HTTP {code}): {MeshCommandHandlers._safe_detail(data)}"

    async def _defer(self, key: str) -> str:
        record_id = self.registry.record_for(key)
        if not record_id:
            return "⚠️ এই কার্ড আর বৈধ নয়।"
        now = int(time.time())
        count = self.defers.mark_asked(record_id, now, self.config.hitl_ask_timeout_sec)
        if count >= self.config.defer_limit:
            # স্পেক: defer সীমা ছুঁয়ে গেলে পরের মেয়াদোত্তীর্ণে auto-reject —
            # এখানে সাথে সাথে reject করা হয় (উত্তর এসেছে শুধু বিলম্ব-চাওয়া),
            # নীতি: ৩ defer = সিদ্ধান্তহীনতা = auto-reject (fail-closed)।
            if self.config.tower_admin_token:
                body = {
                    "reason": f"auto-reject: defer limit ({self.config.defer_limit}) reached",
                    "resolved_by": "telegram-admin",
                }
                code, _data = await self.tower.request(
                    "POST", f"/api/v1/hitl/reject/{record_id}", json_body=body
                )
                if code == 200:
                    self.defers.forget(record_id)
                    return f"🚫 Auto-reject: {self.config.defer_limit} বার defer হয়েছে — {record_id}"
                return f"⚠️ Defer সীমা ছাড়িয়েছে, কিন্তু auto-reject ব্যর্থ (HTTP {code}) — আবার জিজ্ঞেস হবে।"
            return f"⏸ Deferred ({count}/{self.config.defer_limit}) — কিন্তু TOWER_ADMIN_TOKEN নেই, auto-reject করা যাবে না।"
        return f"⏸ Deferred ({count}/{self.config.defer_limit}) — {self.config.hitl_ask_timeout_sec}s পরে আবার জিজ্ঞেস হবে।"


__all__ = [
    "CB_APPROVE",
    "CB_DEFER",
    "CB_REJECT",
    "DeferStore",
    "KeyRegistry",
    "MeshCallbackHandlers",
    "MeshCommandHandlers",
]
