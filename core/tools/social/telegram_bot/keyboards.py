"""Inline keyboard builders for :class:`TelegramBotHandler`
(verbatim split artifact of the former single-module telegram_bot.py)."""

from __future__ import annotations

from typing import Any

from core.config import settings


class KeyboardsMixin:
    """Keyboard-builders mixin for :class:`TelegramBotHandler`."""

    @staticmethod
    def _user_keyboard() -> dict[str, Any]:
        """Comprehensive Pocket User Studio & Dashboard keyboard for regular users."""
        return {
            "inline_keyboard": [
                [
                    {
                        "text": "✨ Open Studio (Telegram Mini App)",
                        "web_app": {"url": settings.frontend_url},
                    },
                ],
                [
                    {"text": "⚡ Quick Actions", "callback_data": "quick_actions_menu"},
                    {"text": "📊 Live Telemetry", "callback_data": "quick_telemetry"},
                ],
                [
                    {"text": "💬 AI Chat & Coding", "callback_data": "user_studio_info"},
                    {"text": "📦 Desktop App (.exe)", "callback_data": "user_desktop_info"},
                ],
                [
                    {"text": "🧩 VS Code Ext (.vsix)", "callback_data": "user_vscode_info"},
                    {"text": "📱 Mobile Client (.apk)", "callback_data": "user_apk_info"},
                ],
                [
                    {"text": "📚 Knowledge Base & Docs", "callback_data": "quick_kb"},
                    {"text": "❓ Features & Guide", "callback_data": "user_guide_info"},
                ],
            ]
        }

    @staticmethod
    def _admin_keyboard() -> dict[str, Any]:
        """Comprehensive Pocket Command Center keyboard for system administrator."""
        return {
            "inline_keyboard": [
                [
                    {
                        "text": "✨ Open Admin Studio (Mini App)",
                        "web_app": {"url": settings.frontend_url},
                    },
                    {
                        "text": "🌐 Admin Web Console",
                        "url": settings.admin_url,
                    },
                ],
                [
                    {"text": "⚡ Cluster & Cost", "callback_data": "admin_cluster"},
                    {"text": "📊 Live Telemetry", "callback_data": "quick_telemetry"},
                ],
                [
                    {"text": "💾 TelDrive Vault", "callback_data": "admin_vault"},
                    {"text": "🤖 AI Brain & Memory", "callback_data": "admin_brain"},
                ],
                [
                    {"text": "🚀 DevOps & CI/CD", "callback_data": "admin_devops"},
                    {"text": "🛡️ Security & 2FA", "callback_data": "admin_security"},
                ],
                [
                    {"text": "📦 Download Builds", "callback_data": "cmd_build"},
                    {"text": "📜 AI Directives", "callback_data": "admin_rules"},
                ],
                [
                    {"text": "🔌 MCP Clients", "callback_data": "admin_mcp_clients"},
                ],
                [
                    {
                        "text": "📚 API Documentation",
                        "url": settings.backend_url + "/docs",
                    },
                    {"text": "⚡ Quick Actions", "callback_data": "quick_actions_menu"},
                ],
            ]
        }

    @staticmethod
    def _dashboard_quick_actions_keyboard() -> dict[str, Any]:
        """Interactive Quick Actions matching the Dashboard QuickActionsPanel."""
        return {
            "inline_keyboard": [
                [
                    {
                        "text": "✨ Open Studio (Mini App)",
                        "web_app": {"url": settings.frontend_url},
                    },
                ],
                [
                    {"text": "⚡ Trigger Self-Healer", "callback_data": "quick_self_healer"},
                    {"text": "🧬 Evolve New Skill", "callback_data": "quick_evolve"},
                ],
                [
                    {"text": "📊 Live Telemetry", "callback_data": "quick_telemetry"},
                    {"text": "🔍 Deep Codebase Audit", "callback_data": "quick_audit"},
                ],
                [
                    {"text": "📚 Knowledge Base Search", "callback_data": "quick_kb"},
                    {"text": "💬 Multi-Session Chat", "callback_data": "session_menu"},
                ],
            ]
        }

    def _quick_actions_keyboard(
        self, chat_id: int | str | None = None, user_id: int | str | None = None
    ) -> dict[str, Any]:
        """Dynamic keyboard based on user role (sender-aware admin gate)."""
        if chat_id and self.is_admin(chat_id, user_id):
            return self._admin_keyboard()
        return self._user_keyboard()
