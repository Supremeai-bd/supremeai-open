"""Webhook/polling update dispatcher for :class:`TelegramBotHandler`
(verbatim split artifact of the former single-module telegram_bot.py).

``handle_update`` routes inline callback queries and messages, including
the AutonoGuard prompt-injection guard, the TOTP 2FA verification flow
and the critical/destructive instruction interceptor
(``tools.social.telegram_security``).
"""

from __future__ import annotations

from typing import Any

from core.config import settings
from core.logging_config import logger


class UpdatesMixin:
    """Update-dispatch mixin for :class:`TelegramBotHandler`."""

    async def handle_update(self, update: dict[str, Any]) -> None:
        """Process a Telegram update payload (from webhook or polling)."""
        # 1. Handle Inline Callback Queries
        callback_query = update.get("callback_query")
        if callback_query:
            callback_id = callback_query["id"]
            data = callback_query.get("data", "")
            chat_id = callback_query.get("message", {}).get("chat", {}).get("id")
            # বাংলা মন্তব্য (P-B): admin গেটে chat_id নয় — পাঠকের from.id authoritative
            sender_id = callback_query.get("from", {}).get("id")
            await self.answer_callback_query(callback_id)

            if chat_id and data:
                # ── User & Common Callbacks ───────────────────────────
                if data == "cmd_build":
                    await self._handle_latest_build(chat_id)
                elif data == "quick_actions_menu":
                    await self._handle_quick_actions(chat_id)
                elif data == "quick_telemetry":
                    await self._handle_telemetry(chat_id)
                elif data == "quick_self_healer":
                    await self._handle_quick_self_healer(chat_id)
                elif data == "quick_evolve":
                    await self._handle_quick_evolve(chat_id)
                elif data == "quick_audit":
                    await self._handle_quick_audit(chat_id)
                elif data == "quick_kb":
                    await self._handle_quick_kb(chat_id)
                elif data == "session_menu":
                    await self._handle_session_menu(chat_id)
                elif data.startswith("session_switch_"):
                    sid = data.replace("session_switch_", "")
                    await self.send_message(
                        chat_id,
                        f"🔄 <b>Session Switched:</b> Context active on <code>{sid}</code>.",
                    )
                elif data == "session_new":
                    await self.send_message(
                        chat_id,
                        "✨ <b>New Conversation Session Created!</b>\nSend any message to start a fresh thread.",
                    )
                elif data == "user_studio_info":
                    await self._handle_user_studio_info(chat_id)
                elif data == "user_desktop_info":
                    await self._handle_user_desktop_info(chat_id)
                elif data == "user_vscode_info":
                    await self._handle_user_vscode_info(chat_id)
                elif data == "user_skills_info":
                    await self._handle_user_skills_info(chat_id)
                elif data in ("user_guide_info", "user_chat_guide"):
                    await self._handle_user_guide_info(chat_id)
                elif data == "user_main_menu":
                    await self.send_message(
                        chat_id,
                        "🤖 <b>SupremeAI 2.0 | User Studio & Dashboard</b>\n\nনিচের অপশনগুলো থেকে আপনার প্রয়োজনীয় সার্ভিস বেছে নিন:",
                        reply_markup=self._user_keyboard(),
                    )
                elif data == "user_apk_info":
                    apk_text = (
                        "📱 <b>SupremeAI Mobile Client (.apk)</b>\n\n"
                        "Android APK ফাইলটি আমাদের স্বয়ংক্রিয় ক্লাউড বিল্ড পাইপলাইনে রয়েছে।\n"
                        "রিলিজ প্রস্তুত হওয়া মাত্রই গিটহাব এবং এই বটে ডাউনলোড লিংক উপলব্ধ হবে!\n\n"
                        "🌐 <i>বর্তমানে মোবাইল ব্রাউজারে ব্যবহার করুন:</i> <a href='{settings.frontend_url}'>SupremeAI Web Studio</a>"
                    )
                    keyboard = {
                        "inline_keyboard": [
                            [
                                {
                                    "text": "✨ Open Studio (Mini App)",
                                    "web_app": {"url": settings.frontend_url},
                                }
                            ],
                            [{"text": "🔙 User Dashboard", "callback_data": "user_main_menu"}],
                        ]
                    }
                    await self.send_message(chat_id, apk_text, reply_markup=keyboard)
                elif data == "cmd_help":
                    await self.send_message(
                        chat_id,
                        self.COMMANDS["/help"],
                        reply_markup=self._quick_actions_keyboard(chat_id, sender_id),
                    )

                # ── Admin Dashboard Callbacks ─────────────────────────
                elif data.startswith("admin_") or data in ("cmd_status", "cmd_backup", "cmd_rules"):
                    if not self.is_admin(chat_id, sender_id):
                        await self.send_message(
                            chat_id,
                            "🔒 <i>This operation is restricted to SupremeAI Administrators.</i>",
                        )
                    else:
                        if data in ("admin_cluster", "cmd_status"):
                            await self._handle_status(chat_id)
                        elif data in ("admin_vault", "cmd_backup"):
                            await self._handle_admin_vault_menu(chat_id)
                        elif data == "admin_vault_now":
                            await self._handle_backup_now(chat_id)
                        elif data == "admin_brain":
                            await self._handle_admin_brain(chat_id)
                        elif data == "admin_devops":
                            await self._handle_admin_devops(chat_id)
                        elif data == "admin_security":
                            await self._handle_admin_security(chat_id)
                        elif data == "admin_mcp_clients":
                            await self._handle_mcp_clients(chat_id, sender_id)
                        elif data in ("admin_rules", "cmd_rules"):
                            await self._handle_admin_rules(chat_id)
                        elif data.startswith("mcp_approve_"):
                            await self._handle_mcp_action(chat_id, data, "approve", sender_id)
                        elif data.startswith("mcp_role_"):
                            await self._handle_mcp_action(chat_id, data, "role", sender_id)
                        elif data == "admin_main_menu":
                            await self.send_message(
                                chat_id,
                                "🔱 <b>SupremeAI 2.0 | Admin Command Center</b>\n\nপ্রধান অ্যাডমিন মেনু থেকে একটি অপশন বেছে নিন:",
                                reply_markup=self._admin_keyboard(),
                            )
            return

        # 2. Handle Direct Messages
        message = update.get("message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        text: str = message.get("text", "").strip()
        user_id: str = str(message["from"]["id"])
        username: str = message["from"].get("username", user_id)

        logger.info(f"Telegram message from @{username} ({user_id}): '{text}'")

        from tools.social.telegram_security import security_guard

        # ── Step A: Anti-Hacking & Prompt Injection Guardrail ─────────
        injected, _inj_reason = security_guard.detect_prompt_injection(text)
        if injected:
            logger.warning(
                f"🚨 Security Alert: Prompt injection attempt from @{username} ({user_id}): '{text}'"
            )
            await self.send_message(
                chat_id,
                "🛡️ <b>Security Alert: AutonoGuard Triggered</b>\n\n"
                "আপনার বার্তায় প্রম্পট ইঞ্জেকশন বা সিকিউরিটি বাইপাস প্যাটার্ন শনাক্ত হয়েছে।\n"
                "সুপ্রিমএআই-এর সাংবিধানিক নিরাপত্তা নীতি অনুসারে এই রিকোয়েস্টটি বাতিল করা হলো।",
            )
            return

        # ── Step B: TOTP 2FA Verification Flow ────────────────────────
        command = text.split(maxsplit=1)[0].lower() if text.startswith("/") else None
        is_verify_cmd = command in ("/verify", "/auth", "/totp", "/otp")
        raw_digits = text.strip()

        if is_verify_cmd or (
            security_guard.has_pending_challenge(chat_id)
            and raw_digits.isdigit()
            and len(raw_digits) == 6
        ):
            otp_code = text.split()[1] if is_verify_cmd and len(text.split()) > 1 else raw_digits
            ok, msg, challenge = security_guard.verify_challenge(chat_id, otp_code)
            await self.send_message(chat_id, msg)
            if ok and challenge:
                await self._execute_authorized_critical_action(chat_id, challenge)
            return

        # ── Step C: Critical / Destructive Instruction Interceptor ────
        is_crit, action_type, action_desc = security_guard.detect_critical_action(text)
        if is_crit:
            if not self.is_admin(chat_id, user_id):
                await self.send_message(
                    chat_id,
                    "🔒 <b>Access Denied:</b> This destructive/privileged system instruction is restricted to System Administrators.",
                )
                return

            chal_id = security_guard.create_challenge(chat_id, action_type, action_desc, text)
            crit_msg = (
                "🛡️ <b>CRITICAL SYSTEM INSTRUCTION INTERCEPTED</b>\n\n"
                f"🎯 <b>Target Action:</b> <code>{action_desc}</code>\n"
                f"⚠️ <b>Risk Level:</b> <code>HIGH / PRIVILEGED</code>\n"
                f"🆔 <b>Challenge ID:</b> <code>{chal_id}</code>\n"
                f"⏳ <b>Validity:</b> 5 Minutes\n\n"
                "🔐 <b>TOTP 2FA Verification Required:</b>\n"
                "এই স্পর্শকাতর অ্যাকশনটি অনুমোদন করতে Authenticator অ্যাপের ৬ ডিজিটের OTP কোডটি পাঠান:\n"
                "👉 <code>/verify 123456</code> অথবা সরাসরি ৬ ডিজিট রিপ্লাই করুন।"
            )
            await self.send_message(chat_id, crit_msg)
            return

        # ── Step D: Standard Command Handling ─────────────────────────
        if command:
            if command in ("/start", "/help"):
                if self.is_admin(chat_id, user_id):
                    welcome_text = (
                        "🔱 <b>SupremeAI 2.0 | Admin Command Center</b>\n\n"
                        "স্বাগতম অ্যাডমিন! আপনি সম্পূর্ণ ক্লাউড আর্কিটেকচার, ব্যাকআপ ও মেমোরি কন্ট্রোল করতে পারেন।\n\n"
                        "• ⚡ <b>Cluster Telemetry:</b> /sys_status\n"
                        "• 💾 <b>Instant Vault Backup:</b> /backup_now\n"
                        "• 🚀 <b>Build Releases:</b> /latest_build\n"
                        f"• 🌐 <b>Dashboard:</b> <a href='{settings.frontend_url}'>SupremeAI Dashboard</a>\n\n"
                        "<i>যেকোনো প্রশ্ন বা কমান্ড পাঠিয়ে এআই অ্যাসিস্ট্যান্স শুরু করুন।</i>"
                    )
                    await self.send_message(
                        chat_id, welcome_text, reply_markup=self._admin_keyboard()
                    )
                else:
                    user_welcome = (
                        "🤖 <b>Welcome to SupremeAI 2.0</b>\n\n"
                        "আপনার স্ব-বিবর্তনশীল কৃত্রিম বুদ্ধিমত্তা সহকারী।\n\n"
                        "✨ <b>আপনার জন্য সহজ সুবিধাগুলো:</b>\n"
                        "• যেকোনো প্রশ্ন বা কোডিং সহায়তা সরাসরি এই চ্যাটে বাংলায় বা ইংরেজিতে লিখুন।\n"
                        "• ব্রাউজার থেকে আমাদের Web Dashboard ব্যবহার করুন।\n"
                        "• Desktop Installer (.exe), VS Code Extension (.vsix) ও Mobile (.apk) ডাউনলোড করুন।\n\n"
                        "🚀 <i>শুরু করতে নিচে যেকোনো অপশন সিলেক্ট করুন বা সরাসরি বার্তা পাঠান!</i>"
                    )
                    await self.send_message(
                        chat_id, user_welcome, reply_markup=self._user_keyboard()
                    )
                return

            if command in ("/app", "/studio"):
                await self.send_message(
                    chat_id,
                    self.COMMANDS["/app"],
                    reply_markup={
                        "inline_keyboard": [
                            [
                                {
                                    "text": "✨ Open Studio (Telegram Mini App)",
                                    "web_app": {"url": settings.frontend_url},
                                }
                            ]
                        ]
                    },
                )
                return

        if command == "/mcp_clients":
            if not self.is_admin(chat_id, user_id):
                await self.send_message(chat_id, "🔒 <i>Admin operation restricted.</i>")
            else:
                await self._handle_mcp_clients(chat_id, user_id)
        if command == "/telemetry":
            await self._handle_telemetry(chat_id)
            return

        if command == "/abort":
            # বাংলা (M18 P-I): রান-ক্যান্সেলেশন বিপজ্জনক অপারেশন — admin-only
            # fail-closed গেট; অন্য কেউ run বাতিল করতে পারবে না।
            if not self.is_admin(chat_id, user_id):
                await self.send_message(chat_id, "🔒 <i>Admin operation restricted.</i>")
            else:
                await self._handle_abort(chat_id, text[len("/abort") :].strip())
            return

        if command == "/quick":
            await self._handle_quick_actions(chat_id)
            return

        if command in ("/kb", "/docs"):
            query = text[len(command) :].strip()
            await self._handle_kb_search(chat_id, query)
            return

        if command == "/session":
            await self._handle_session_menu(chat_id)
            return

        if command in ("/status", "/sys_status"):
            if not self.is_admin(chat_id, user_id):
                await self.send_message(chat_id, "🔒 <i>Admin operation restricted.</i>")
            else:
                await self._handle_status(chat_id)
            return

        if command == "/ai_list":
            await self._handle_ai_list(chat_id)
            return

        if command == "/ai_surfaces":
            await self._handle_ai_surfaces(chat_id)
            return

        if command == "/ai_assign":
            args = text.split()[1:] if text.split()[1:] else []
            await self._handle_ai_assign(chat_id, args, user_id)
            return

        if command == "/backup_now":
            if not self.is_admin(chat_id, user_id):
                await self.send_message(chat_id, "🔒 <i>Admin operation restricted.</i>")
            else:
                await self._handle_backup_now(chat_id)
            return

        if command == "/latest_build":
            await self._handle_latest_build(chat_id)
            return

        reply = self.COMMANDS.get(command)
        if reply:
            if command in ("/admin", "/rules") and not self.is_admin(chat_id, user_id):
                await self.send_message(chat_id, "🔒 <i>Admin operation restricted.</i>")
            else:
                await self.send_message(chat_id, reply)
            return

        # ── Step E: AI Conversational Engine ──────────────────────────
        await self.send_typing(chat_id)
        ai_response = await self._ai_response(text, user_id)
        await self.send_message(chat_id, ai_response)
