"""Telegram bot handler for AI surface assignment commands.

Commands:
  /ai_list     — show all AI providers + key status
  /ai_surfaces — show all surfaces + assigned AI
  /ai_assign   — assign AI to a surface (admin only)
"""

from __future__ import annotations

import os

from core.logging_config import logger


class AIAssignmentHandlerMixin:
    """AI assignment commands mixin for TelegramBotHandler."""

    async def _handle_ai_list(self, chat_id: int | str) -> None:
        """Show all AI providers + API key status."""
        providers = [
            ("Groq", "GROQ_API_KEY", "Tier 1", "fastest", "free"),
            ("Gemini Flash", "GEMINI_API_KEY", "Tier 1", "fast", "free"),
            ("OpenRouter", "OPENROUTER_API_KEY", "Tier 2", "medium", "free"),
            ("Mistral", "MISTRAL_API_KEY", "Tier 2", "fast", "free"),
            ("Bynara", "BYNARA_API_KEY", "Tier 2", "medium", "free"),
            ("BAI", "BAI_API_KEY", "Tier 2", "medium", "free"),
            ("DeepSeek", "DEEPSEEK_API_KEY", "Tier 2", "fast", "free"),
            ("Cerebras", "CEREBRAS_API_KEY", "Tier 1", "fastest", "free"),
            ("OpenAI", "OPENAI_API_KEY", "Tier 3", "medium", "paid"),
            ("Anthropic", "ANTHROPIC_API_KEY", "Tier 3", "medium", "paid"),
            ("Modal", "MODAL_TOKEN_ID", "Tier 3", "variable", "free-tier"),
        ]

        lines = ["🤖 <b>AI Provider List</b>\n"]
        working = 0
        missing = 0

        for name, env_key, tier, speed, cost in providers:
            key = os.environ.get(env_key, "")
            # Also check LLM_PROVIDER_KEYS JSON
            lpk = os.environ.get("LLM_PROVIDER_KEYS", "")
            has_key = bool(key) or (lpk and name.lower().split()[0] in lpk.lower())

            if has_key:
                icon = "✅"
                working += 1
            else:
                icon = "❌"
                missing += 1

            lines.append(f"{icon} <b>{name}</b> ({tier}, {speed}, {cost})")
            lines.append(
                f"   Key: <code>{env_key}</code> — {'✅ set' if has_key else '❌ missing'}"
            )

        lines.append(f"\n📊 <b>Summary:</b> {working} working, {missing} missing")
        lines.append("\n💡 <i>/ai_surfaces — দেখো কোন AI কোথায় ব্যস্ত</i>")
        lines.append("💡 <i>/ai_assign [surface] [provider] — assign করো (admin)</i>")

        await self.bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML")

    async def _handle_ai_surfaces(self, chat_id: int | str) -> None:
        """Show all surfaces + assigned AI."""
        surfaces = [
            ("💬 Web Chat", "web_chat", "Dashboard chat"),
            ("💻 IDE (Trio)", "ide", "Code assistant"),
            ("📱 Telegram", "telegram", "Bot AI response"),
            ("🔌 API", "api", "Direct API"),
            ("🔍 Research", "research", "Deep research"),
            ("🤖 Automation", "automation", "Browser agent"),
        ]

        # Get current assignment (from in-memory store or API)
        try:
            import httpx

            backend_url = os.environ.get("BACKEND_URL", "")
            if backend_url:
                async with httpx.AsyncClient(timeout=5) as client:
                    resp = await client.get(f"{backend_url}/api/admin/ai/assignment")
                    assignment = resp.json() if resp.status_code == 200 else {}
            else:
                assignment = {}
        except Exception:
            assignment = {}

        lines = ["🎯 <b>AI Surface Assignment</b>\n"]
        for icon_name, surface_id, desc in surfaces:
            assigned = assignment.get(surface_id, "auto")
            lines.append(f"{icon_name} — <b>{desc}</b>")
            lines.append(f"   → AI: <code>{assigned}</code>\n")

        lines.append("💡 <i>/ai_assign [surface] [provider] — change করো (admin)</i>")
        lines.append("Example: /ai_assign telegram groq")

        await self.bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML")

    async def _handle_ai_assign(
        self, chat_id: int | str, args: list[str], user_id: int | str | None = None
    ) -> None:
        """Assign AI to a surface. Admin only."""
        # Check admin
        if not self.is_admin(chat_id, user_id):
            await self.bot.send_message(chat_id, "❌ শুধু admin এটা করতে পারবেন।")
            return

        if len(args) < 2:
            await self.bot.send_message(
                chat_id,
                "📋 <b>Usage:</b> <code>/ai_assign [surface] [provider]</code>\n\n"
                "<b>Surfaces:</b> web_chat, ide, telegram, api, research, automation\n"
                "<b>Providers:</b> groq, gemini, openrouter, mistral, deepseek, cerebras, openai, anthropic, auto\n\n"
                "Example: <code>/ai_assign telegram groq</code>",
                parse_mode="HTML",
            )
            return

        surface = args[0].lower()
        provider = args[1].lower()

        valid_surfaces = ["web_chat", "ide", "telegram", "api", "research", "automation"]
        valid_providers = [
            "groq",
            "gemini",
            "openrouter",
            "mistral",
            "deepseek",
            "cerebras",
            "openai",
            "anthropic",
            "byna",
            "bai",
            "modal",
            "auto",
        ]

        if surface not in valid_surfaces:
            await self.bot.send_message(
                chat_id,
                f"❌ Invalid surface: <code>{surface}</code>\nValid: {', '.join(valid_surfaces)}",
                parse_mode="HTML",
            )
            return

        if provider not in valid_providers:
            await self.bot.send_message(
                chat_id,
                f"❌ Invalid provider: <code>{provider}</code>\nValid: {', '.join(valid_providers)}",
                parse_mode="HTML",
            )
            return

        # Call backend API to assign (BACKEND_URL must point at the running
        # backend; no localhost fallback — constitution ARCH-001).
        if not os.environ.get("BACKEND_URL"):
            await self.bot.send_message(
                chat_id,
                "❌ BACKEND_URL কনফিগার করা নেই — /ai_assign ব্যবহার করা যাবে না।",
            )
            return
        try:
            import httpx

            backend_url = os.environ["BACKEND_URL"]
            admin_token = os.environ.get("SUPREMEAI_ADMIN_SECRET", "")
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{backend_url}/api/admin/ai/assign",
                    json={"surface": surface, "provider": provider},
                    headers={"Authorization": f"Bearer {admin_token}"},
                )

            if resp.status_code == 200:
                await self.bot.send_message(
                    chat_id,
                    f"✅ <b>Assignment updated!</b>\n"
                    f"📱 Surface: <code>{surface}</code>\n"
                    f"🤖 Provider: <code>{provider}</code>\n\n"
                    f"<i>{surface} এখন {provider} ব্যবহার করবে</i>",
                    parse_mode="HTML",
                )
            else:
                await self.bot.send_message(
                    chat_id,
                    f"❌ Assignment failed: HTTP {resp.status_code}",
                )
        except Exception as e:
            await self.bot.send_message(
                chat_id,
                f"❌ Error: {str(e)[:60]}",
            )
