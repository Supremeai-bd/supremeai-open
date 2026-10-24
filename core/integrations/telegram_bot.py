"""MESH-4 Telegram command handler — main bot — issue #942 (P2-medium).

বাংলা সারসংক্ষেপ:
------------------
Tower-এর সাথে মেশ বটের মূল রানটাইম — দুটি httpx ক্লায়েন্ট (Telegram API +
Tower REST) এবং দুটি লুপ:
1. long-polling (getUpdates) — কমান্ড (/task, /status, /nodes, /cancel) ও
   inline-button callback (HITL Approve/Reject/Defer)
2. HITL watcher — GET /api/v1/hitl/pending পোল করে নতুন বিপজ্জনক কাজের
   অনুমোদন-কার্ড admin chat-এ পাঠায়; ৫ মিনিট উত্তর না পেলে re-ask (auto-defer),
   defer_limit (৩) পার হলে auto-reject (fail-closed)।

নিরাপত্তা-চুক্তি:
- `configured` মিথ্যা হলে polling শুরুই হয় না (নীরব ভান নেই — social বটের মতোই)।
- কমান্ড/কলব্যাক শুধু ADMIN_TELEGRAM_CHAT_ID গ্রহণ করে; অজানা chat-এ Tower কল নেই।
- HITL লেখা (approve/reject) TOWER_ADMIN_TOKEN ছাড়া সম্ভব নয় — স্পষ্ট ত্রুটি জানানো হয়।

ফ্রেমওয়ার্ক নোট: issue-তে python-telegram-bot v21+ উল্লেখ ছিল, কিন্তু repo-র
প্রতিষ্ঠিত রীতি (backend/tools/social/telegram_bot/*) raw Bot API + httpx —
নতুন dependency যোগ না করে একই কার্যকারিতা, CI-নিরাপদ। Zero-dependency।

সম্পর্কিত: Master plan §৬ MESH-4 · HITL contract docs/security/HITL_APPROVAL_CONTRACT.md
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

from core.logging_config import logger
from integrations.telegram_config import MeshTelegramConfig, load_mesh_telegram_config
from integrations.telegram_handlers import (
    CB_APPROVE,
    CB_DEFER,
    CB_REJECT,
    DeferStore,
    KeyRegistry,
    MeshCallbackHandlers,
    MeshCommandHandlers,
)


# ── HTTP clients ─────────────────────────────────────────────────────────────
class TowerClient:
    """Tower REST ক্লায়েন্ট — (status_code, parsed_json) টুপল রিটার্ন; কখনো raise করে না।"""

    def __init__(self, base_url: str, admin_token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.admin_token = admin_token

    async def request(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        headers: dict[str, str] = {}
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.request(
                    method, f"{self.base_url}{path}", json=json_body, headers=headers
                )
            try:
                data: Any = resp.json()
            except (json.JSONDecodeError, ValueError):
                data = {"detail": resp.text[:200]}
            return resp.status_code, data
        except httpx.HTTPError as exc:
            logger.warning(f"[MESH-TG] Tower {method} {path} failed: {exc}")
            return 0, {"detail": f"tower unreachable: {exc}"}


class TelegramClient:
    """Telegram Bot API ক্লায়েন্ট — ন্যূনতম প্রয়োজনীয় মেথড (raw API, house-style)।"""

    def __init__(self, api_base: str) -> None:
        self.api_base = api_base

    async def get_updates(self, offset: int, poll_timeout: int) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=poll_timeout + 10) as client:
                resp = await client.get(
                    f"{self.api_base}/getUpdates",
                    params={
                        "offset": offset,
                        "timeout": poll_timeout,
                        "allowed_updates": ["message", "callback_query"],
                    },
                )
            if resp.status_code == 200:
                return list(resp.json().get("result", []))
            logger.warning(f"[MESH-TG] getUpdates HTTP {resp.status_code}")
        except httpx.HTTPError as exc:
            logger.warning(f"[MESH-TG] getUpdates failed: {exc}")
        return []

    async def send_message(
        self, chat_id: str, text: str, reply_markup: dict[str, Any] | None = None
    ) -> int | None:
        """মেসেজ পাঠাও — সফল হলে message_id (card edit-এর জন্য), ব্যর্থে None।"""
        body: dict[str, Any] = {"chat_id": chat_id, "text": text[:4000]}
        if reply_markup:
            body["reply_markup"] = reply_markup
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(f"{self.api_base}/sendMessage", json=body)
            if resp.status_code == 200:
                result = resp.json().get("result", {})
                return result.get("message_id")
            logger.warning(f"[MESH-TG] sendMessage HTTP {resp.status_code}: {resp.text[:150]}")
        except httpx.HTTPError as exc:
            logger.warning(f"[MESH-TG] sendMessage failed: {exc}")
        return None

    async def answer_callback(self, callback_query_id: str, text: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"{self.api_base}/answerCallbackQuery",
                    json={"callback_query_id": callback_query_id, "text": text[:190]},
                )
        except httpx.HTTPError as exc:
            logger.warning(f"[MESH-TG] answerCallbackQuery failed: {exc}")

    async def edit_message(self, chat_id: str, message_id: int, text: str) -> None:
        """কার্ড মেসেজ আপডেট (সিদ্ধান্তের পরে বাটন-শূন্য করা) — best-effort।"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"{self.api_base}/editMessageText",
                    json={"chat_id": chat_id, "message_id": message_id, "text": text[:4000]},
                )
        except httpx.HTTPError as exc:
            logger.warning(f"[MESH-TG] editMessageText failed: {exc}")


# ── Bot ──────────────────────────────────────────────────────────────────────
class MeshTelegramBot:
    """মেশ-কমান্ড বট — Telegram (মানুষ) ↔ Tower (REST) সেতু + HITL অনুমোদন-কার্ড।"""

    def __init__(self, config: MeshTelegramConfig | None = None) -> None:
        self.config = config or load_mesh_telegram_config()
        self.tg = TelegramClient(self.config.api_base)
        self.tower = TowerClient(self.config.tower_base_url, self.config.tower_admin_token)
        self.commands = MeshCommandHandlers(self.config, self.tower)
        self.registry = KeyRegistry()
        self.defers = DeferStore()
        self.callbacks = MeshCallbackHandlers(self.config, self.tower, self.registry, self.defers)
        # announced HITL record → (chat_id, message_id) — watcher re-ask/card edit-এর জন্য
        self._cards: dict[str, tuple[str, int]] = {}
        self._offset = 0

    # ── Update dispatch ──────────────────────────────────────────────────────
    async def handle_update(self, update: dict[str, Any]) -> str | None:
        """একটি Telegram update রাউট — নিরাপত্তা-যাচাই সবার আগে (fail-closed)।

        রিটার্ন: পাঠানো reply/answer টেক্সট (টেস্টেবিলিটির জন্য); অজানা chat
        বা অপ্রাসঙ্গিক update হলে None।
        """
        msg = update.get("message")
        cb = update.get("callback_query")
        if msg:
            chat_id = str((msg.get("chat") or {}).get("id", ""))
            if not self.config.is_admin_chat(chat_id):
                logger.info("[MESH-TG] command from non-admin chat ignored")
                return None
            text = (msg.get("text") or "").strip()
            reply = await self._route_command(text)
            await self.tg.send_message(chat_id, reply)
            return reply
        if cb:
            chat_id = str(((cb.get("message") or {}).get("chat") or {}).get("id", ""))
            if not self.config.is_admin_chat(chat_id):
                logger.info("[MESH-TG] callback from non-admin chat ignored")
                return None
            data = cb.get("data") or ""
            answer = await self.callbacks.handle_callback(data)
            await self.tg.answer_callback(cb.get("id") or "", answer)
            record_key = self._record_of(data)
            card = self._cards.get(record_key) if record_key is not None else None
            if card:
                await self.tg.edit_message(card[0], card[1], f"{card[0]}\n\n➡️ সিদ্ধান্ত: {answer}")
            return answer
        return None

    def _record_of(self, data: str) -> str | None:
        """callback_data → কার্ড-কী (registry key) — card map lookup-এর জন্য।"""
        for prefix in (CB_APPROVE, CB_REJECT, CB_DEFER):
            if data.startswith(prefix):
                return data[len(prefix) :]
        return None

    async def _route_command(self, text: str) -> str:
        if not text.startswith("/"):
            return "⚠️ কমান্ড নয় — /help দেখো।"
        parts = text.split(maxsplit=1)
        cmd = parts[0].split("@")[0].lower()  # /task@SomeBot → /task
        arg = parts[1].strip() if len(parts) > 1 else ""
        if cmd == "/task":
            return await self.commands.handle_task(arg)
        if cmd == "/status":
            return await self.commands.handle_status()
        if cmd == "/nodes":
            return await self.commands.handle_nodes()
        if cmd == "/cancel":
            return await self.commands.handle_cancel(arg)
        if cmd in ("/help", "/start"):
            return self.commands.handle_help()
        return f"⚠️ অজানা কমান্ড {cmd} — /help দেখো।"

    # ── HITL watcher ─────────────────────────────────────────────────────────
    def _approval_card_markup(self, key: str) -> dict[str, Any]:
        """[✅ Approve] [❌ Reject] [⏸ Defer 5 min] — spec §Inline buttons।"""
        return {
            "inline_keyboard": [
                [
                    {"text": "✅ Approve", "callback_data": f"{CB_APPROVE}{key}"},
                    {"text": "❌ Reject", "callback_data": f"{CB_REJECT}{key}"},
                    {"text": "⏸ Defer 5 min", "callback_data": f"{CB_DEFER}{key}"},
                ]
            ]
        }

    def _card_text(self, record: dict[str, Any]) -> str:
        payload = record.get("payload") or {}
        payload_s = json.dumps(payload, ensure_ascii=False)[:200] if payload else "—"
        return (
            "🤖 HITL required\n"
            f"   Record: {record.get('id', record.get('target_resource', '?'))}\n"
            f"   Action: {record.get('target_resource', '?')}\n"
            f"   Payload: {payload_s}"
        )

    async def hitl_tick(self) -> None:
        """HITL pending queue একবার পোল — নতুন কার্ড, re-ask, auto-reject।"""
        code, data = await self.tower.request("GET", "/api/v1/hitl/pending")
        if code != 200:
            return  # Tower অনুপলব্ধ — নীরব পুনঃপ্রচেষ্টা (লগ TowerClient-এ হয়ে গেছে)
        records = data if isinstance(data, list) else data.get("tasks", data.get("pending", []))
        now = int(time.time())
        pending_ids: set[str] = set()
        for record in records:
            if not isinstance(record, dict):
                continue
            rid = str(record.get("id") or record.get("target_resource") or "")
            if not rid:
                continue
            pending_ids.add(rid)
            st = self.defers.ensure(rid, now)
            if now < st["next_ask"]:
                continue  # এখনো উত্তরের অপেক্ষায়
            if st["defers"] >= self.config.defer_limit and rid in self._cards:
                # স্পেক: ৩ defer → auto-reject (task cancelled)
                await self._auto_reject(rid)
                continue
            # নতুন রেকর্ড বা re-ask — কার্ড পাঠাও
            key = self.registry.key_for(rid)
            chat = self.config.admin_chat_id
            mid = await self.tg.send_message(
                chat, self._card_text(record), self._approval_card_markup(key)
            )
            if mid is not None:
                self._cards[rid] = (chat, mid)
            self.defers.mark_asked(rid, now, self.config.hitl_ask_timeout_sec)
        # আর pending নেই এমন রেকর্ডের defer-state মুছে দাও (resolve/expired)
        for rid in self.defers.registered_ids():
            if rid not in pending_ids:
                self.defers.forget(rid)

    async def _auto_reject(self, record_id: str) -> None:
        """defer_limit অতিক্রান্ত — Tower-এ reject (admin token না থাকলে স্পষ্ট লগ, ভান নেই)।"""
        if not self.config.tower_admin_token:
            logger.warning(f"[MESH-TG] auto-reject skipped (no TOWER_ADMIN_TOKEN): {record_id}")
            return
        body = {
            "reason": f"auto-reject: {self.config.defer_limit} defers without decision",
            "resolved_by": "telegram-admin",
        }
        code, _ = await self.tower.request(
            "POST", f"/api/v1/hitl/reject/{record_id}", json_body=body
        )
        if code == 200:
            self.defers.forget(record_id)
            card = self._cards.pop(record_id, None)
            if card:
                await self.tg.edit_message(
                    card[0], card[1], f"🚫 Auto-reject (defer limit): {record_id}"
                )
            logger.info(f"[MESH-TG] auto-rejected {record_id} after defer limit")
        else:
            logger.warning(f"[MESH-TG] auto-reject HTTP {code} for {record_id}")

    # ── Main loop ────────────────────────────────────────────────────────────
    async def run_polling(self) -> None:
        """লং-পোলিং মূল লুপ + HITL watcher — `configured` না হলে চলেই না।"""
        if not self.config.configured:
            logger.warning(
                "Mesh Telegram bot not configured (TELEGRAM_BOT_TOKEN / "
                "ADMIN_TELEGRAM_CHAT_ID missing) — skipping polling."
            )
            return
        logger.info("🤖 MESH-4 Telegram command bot active (long-polling)…")
        last_hitl_poll = 0.0
        while True:
            now = time.monotonic()
            if now - last_hitl_poll >= self.config.hitl_poll_interval_sec:
                last_hitl_poll = now
                try:
                    await self.hitl_tick()
                except Exception as exc:  # watcher কখনো মূল লুপ মারবে না
                    logger.warning(f"[MESH-TG] hitl_tick error: {exc}")
            try:
                updates = await self.tg.get_updates(self._offset, 25)
            except Exception as exc:
                logger.warning(f"[MESH-TG] polling error: {exc}")
                updates = []
            for update in updates:
                self._offset = max(self._offset, int(update.get("update_id", 0)) + 1)
                try:
                    await self.handle_update(update)
                except Exception as exc:
                    logger.warning(f"[MESH-TG] update handling error: {exc}")


async def main() -> None:
    """`python -m integrations.telegram_bot` entrypoint।"""
    await MeshTelegramBot().run_polling()


if __name__ == "__main__":
    asyncio.run(main())


__all__ = [
    "MeshTelegramBot",
    "TelegramClient",
    "TowerClient",
    "main",
]
