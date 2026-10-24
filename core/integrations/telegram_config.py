"""MESH-4 Telegram command-handler configuration — issue #942 (P2-medium).

বাংলা সারসংক্ষেপ:
------------------
মেশ-টেলিগ্রাম বটের কনফিগ স্তর। সব মান environment variable থেকে আসে —
কোনো secret কোডে বা yaml-এ hardcode করা যাবে না (hardcode scanner দেখবে)।
``backend/integrations/telegram_config.yaml`` শুধু ডকুমেন্ট-টেমপ্লেট —
রানটাইম সত্যিকারের সোর্স এই মডিউল + env।

Env vars:
- TELEGRAM_BOT_TOKEN      — বট টোকেন (BotFather-প্রাপ্ত) — এটা ছাড়া বট চলে না
- ADMIN_TELEGRAM_CHAT_ID  — অনুমোদিত admin chat (শুধু এই chat কমান্ড দিতে পারে)
- MESH_TOWER_BASE_URL     — Tower API base (default http://127.0.0.1:8000)
- TOWER_ADMIN_TOKEN       — HITL approve/reject এর জন্য admin Bearer token
- MESH_TG_HITL_ASK_TIMEOUT_SEC — অনুমোদন-কার্ড re-ask ব্যবধান (default 300s)
- MESH_TG_HITL_DEFER_LIMIT     — সর্বোচ্চ defer সংখ্যা, এরপর auto-reject (default 3)

সম্পর্কিত:
- Master plan: docs/plans/MULTI_AGENT_MESH_MASTER_PLAN.md (§৬ MESH-4)
- Issue: #942 · Depends on: /api/v1/mesh/tasks, /api/v1/nodes, /api/v1/hitl/*
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_int(name: str, default: int) -> int:
    """env var → int; অবৈধ/অনুপস্থিত হলে default (নীরব fallback নয় — ডকুমেন্টেড ডিফল্ট)।"""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class MeshTelegramConfig:
    """মেশ-টেলিগ্রাম বটের ফ্রোজেন কনফিগ — fail-closed: `configured` মিথ্যা হলে polling শুরুই হবে না।"""

    bot_token: str = ""
    admin_chat_id: str = ""
    # unguarded-localhost idiom: local-dev fallback only — production-এ Tower
    # URL অবশ্যই MESH_TOWER_BASE_URL থেকে আসবে; silent localhost default ভুল
    # হোস্টে connect করাত (regression-scanner HIGH finding)।
    tower_base_url: str = field(default_factory=lambda: _default_tower_base_url())
    tower_admin_token: str = ""
    hitl_ask_timeout_sec: int = 300  # স্পেক: ৫ মিনিট উত্তর না এলে auto-defer (আবার জিজ্ঞেস)
    defer_limit: int = 3  # স্পেক: ৩ defer এর পরে আর উত্তর না এলে auto-reject
    hitl_poll_interval_sec: int = 20  # Tower HITL pending queue পোলিং ব্যবধান

    @property
    def configured(self) -> bool:
        """বট চালু করার ন্যূনতম শর্ত: টোকেন + admin chat দুটোই থাকতে হবে।"""
        return bool(self.bot_token) and bool(self.admin_chat_id)

    @property
    def api_base(self) -> str:
        """Telegram Bot API base URL — টোকেন path এ থাকে (Telegram-এর স্ট্যান্ডার্ড)।"""
        return f"https://api.telegram.org/bot{self.bot_token}"

    def is_admin_chat(self, chat_id: str | int | None) -> bool:
        """কমান্ড/callback শুধুই admin chat থেকে গ্রহণযোগ্য — বাকি সব 403-ধর্মী প্রত্যাখ্যান।"""
        if chat_id is None or not self.admin_chat_id:
            return False
        return str(chat_id).strip() == self.admin_chat_id.strip()


def _default_tower_base_url() -> str:
    """Local-dev fallback only — production must set MESH_TOWER_BASE_URL."""
    from core.config import settings

    if settings.env == "local":
        return "http://127.0.0.1:8000"
    return ""


def load_mesh_telegram_config() -> MeshTelegramConfig:
    """env → :class:`MeshTelegramConfig` (প্রতিটি process শুরুতে একবার)।"""
    return MeshTelegramConfig(
        bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        admin_chat_id=os.getenv("ADMIN_TELEGRAM_CHAT_ID", "").strip(),
        tower_base_url=os.getenv("MESH_TOWER_BASE_URL", "").strip() or _default_tower_base_url(),
        tower_admin_token=os.getenv("TOWER_ADMIN_TOKEN", "").strip(),
        hitl_ask_timeout_sec=_env_int("MESH_TG_HITL_ASK_TIMEOUT_SEC", 300),
        defer_limit=_env_int("MESH_TG_HITL_DEFER_LIMIT", 3),
        hitl_poll_interval_sec=_env_int("MESH_TG_HITL_POLL_INTERVAL_SEC", 20),
    )


__all__ = ["MeshTelegramConfig", "load_mesh_telegram_config"]
