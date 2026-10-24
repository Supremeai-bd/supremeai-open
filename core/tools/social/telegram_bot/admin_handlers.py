"""Admin command panels for :class:`TelegramBotHandler`
(verbatim split artifact of the former single-module telegram_bot.py).

Cluster status/telemetry, TelDrive vault & on-demand backup, AI brain,
DevOps, security and constitutional-rules panels.
"""

from __future__ import annotations

from core.config import settings
from core.logging_config import logger


class AdminHandlersMixin:
    """Admin-panel mixin for :class:`TelegramBotHandler`."""

    async def _handle_status(self, chat_id: int | str) -> None:
        import time as _time

        import httpx as _httpx

        status_lines = [
            "⚡ <b>SupremeAI 2.0 Telemetry & Cluster Monitor</b>",
            f"🕒 <i>Timestamp:</i> {_time.strftime('%Y-%m-%d %H:%M:%S UTC', _time.gmtime())}",
            "",
        ]

        # Backend Health
        backend_url = getattr(settings, "supremeai_api_url", "") or settings.backend_url
        try:
            async with _httpx.AsyncClient(timeout=5) as c:
                r = await c.get(f"{backend_url}/health")
                icon = "🟢" if r.status_code == 200 else "🟡"
                status_lines.append(
                    f"{icon} <b>Render Backend:</b> <code>{r.status_code} OK (Port 8000)</code>"
                )
        except Exception:
            status_lines.append("🔴 <b>Render Backend:</b> <code>Degraded/Unreachable</code>")

        # Database Health
        try:
            from core.health_check import ComprehensiveHealthChecker

            checker = ComprehensiveHealthChecker()
            db_res = await checker.check_database()
            db_icon = "🟢" if db_res.status.value == "healthy" else "🔴"
            status_lines.append(
                f"{db_icon} <b>Supabase Postgres:</b> <code>{db_res.message}</code>"
            )
        except Exception as e:
            status_lines.append(f"⚪ <b>Database:</b> <code>{e}</code>")

        # AI Engine & Free Tier status
        status_lines.extend(
            [
                "🟢 <b>AI Reasoning:</b> <code>Gemini 2.5 Flash + Groq ($0 Cost)</code>",
                "🟢 <b>TelDrive Storage:</b> <code>Operational (Unlimited Cloud)</code>",
                "🟢 <b>Vector Fabric:</b> <code>pgvector / Continuous Learning</code>",
                "",
                "💡 <i>সব সার্ভিস স্বাভাবিকভাবে চলমান রয়েছে।</i>",
            ]
        )

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "💾 Backup Vault", "callback_data": "admin_vault_now"},
                    {"text": "🤖 AI Brain Info", "callback_data": "admin_brain"},
                ],
                [
                    {"text": "🔙 Admin Dashboard", "callback_data": "admin_main_menu"},
                ],
            ]
        }
        await self.send_message(chat_id, "\n".join(status_lines), reply_markup=keyboard)

    async def _handle_admin_vault_menu(self, chat_id: int | str) -> None:
        text = (
            "💾 <b>SupremeAI TelDrive Vault & Backup Center</b>\n\n"
            "• <b>Storage Engine:</b> Telegram Cloud + AES-256 (Fernet) + Gzip\n"
            "• <b>Cost:</b> $0 / Month (Unlimited Zero-Cost Archive)\n"
            "• <b>Coverage:</b> Supabase Core Tables + Codebase Snapshot\n"
            "• <b>CI Cron:</b> Daily automated at 02:00 UTC\n\n"
            "👇 <i>তাত্ক্ষণিক ব্যাকআপ নিতে নিচের বাটনে চাপুন:</i>"
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🚀 Run Instant Backup Now", "callback_data": "admin_vault_now"},
                ],
                [
                    {"text": "⚡ Cluster Health", "callback_data": "admin_cluster"},
                    {"text": "���� Admin Dashboard", "callback_data": "admin_main_menu"},
                ],
            ]
        }
        await self.send_message(chat_id, text, reply_markup=keyboard)

    async def _handle_admin_brain(self, chat_id: int | str) -> None:
        text = (
            "🤖 <b>SupremeAI 2.0 AI Brain & Multi-Agent Matrix</b>\n\n"
            "• 🧠 <b>Primary Model:</b> Google Gemini 2.5 Flash (Ultra-fast)\n"
            "• ⚡ <b>Fallback Engine:</b> Groq (Qwen 2.5 / GPT-OSS 120B)\n"
            "• 🔄 <b>Orchestrator:</b> Native StateGraph + SupremeOrchestrator\n"
            "• 📚 <b>Long-Term Memory:</b> PostgreSQL pgvector (`ai_memory`)\n"
            "• 💰 <b>Operational Cost:</b> 100% Free-Tier ($0 Budget Optimization)\n\n"
            "<i>সিস্টেম সম্পূর্ণ অটোনোমাস এবং চ্যাটের সাথে রিয়েল-টাইমে কানেক্টেড।</i>"
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "⚡ Cluster Health", "callback_data": "admin_cluster"},
                    {"text": "🛡️ Security Status", "callback_data": "admin_security"},
                ],
                [
                    {"text": "🔙 Admin Dashboard", "callback_data": "admin_main_menu"},
                ],
            ]
        }
        await self.send_message(chat_id, text, reply_markup=keyboard)

    async def _handle_admin_devops(self, chat_id: int | str) -> None:
        text = (
            "🚀 <b>DevOps, CI/CD & Cloud Infrastructure</b>\n\n"
            "• 🐙 <b>GitHub Repository:</b> <a href='https://github.com/SaifulHaqueNiloy/supremeai'>SaifulHaqueNiloy/supremeai</a>\n"
            "• 🐳 <b>Container Host:</b> Render Cloud Docker\n"
            "• 🌐 <b>Frontend CDN:</b> Vercel Edge Network\n"
            "• 🗄️ <b>Database Engine:</b> Supabase Cloud Postgres (Singapore)\n"
            "• 🔄 <b>CI Pipeline:</b> GitHub Actions (Lint, Pytest, Auto-Deploy)\n\n"
            "<i>সকল ক্লাউড কম্পোনেন্ট সিঙ্কড ও সচল রয়েছে।</i>"
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "📦 Download Releases", "callback_data": "cmd_build"},
                    {
                        "text": "📚 Swagger API Docs",
                        "url": settings.backend_url + "/docs",
                    },
                ],
                [
                    {"text": "🔙 Admin Dashboard", "callback_data": "admin_main_menu"},
                ],
            ]
        }
        await self.send_message(chat_id, text, reply_markup=keyboard)

    async def _handle_admin_security(self, chat_id: int | str) -> None:
        # বাংলা মন্তব্য (P-B admin-identity truth): আগে এখানে হার্ডকোড করা admin
        # chat_id মুদ্রিত হতো (information disclosure + ভুয়া "Verified" দাবি)।
        # এখন শুধু সৎ configured/not-configured অবস্থা — কোনো আইডি প্রকাশ নয়।
        admin_ids = self._configured_admin_ids()
        admin_identity_state = (
            f"{len(admin_ids)} configured (vault/env, fail-closed gate)"
            if admin_ids
            else "NOT CONFIGURED — admin gate is fail-closed"
        )
        text = (
            "🛡️ <b>SupremeAI Security & AutonoGuard Center</b>\n\n"
            "• 🔐 <b>2FA Engine:</b> RFC 6238 TOTP (Google Authenticator)\n"
            "• 🚫 <b>Anti-Tampering:</b> Prompt Injection & Jailbreak Blocker Active\n"
            "• 🛑 <b>Critical Interceptor:</b> Destructive DB/Key actions locked behind 2FA\n"
            f"• 👤 <b>Admin Identity:</b> <code>{admin_identity_state}</code>\n\n"
            "<i>আপনার সিস্টেম সম্পূর্ণ সুরক্ষিত ও ফল্ট-টলারেন্ট।</i>"
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "🔐 Admin Web Console",
                        "url": settings.admin_url,
                    },
                    {"text": "📜 Constitutional Rules", "callback_data": "admin_rules"},
                ],
                [
                    {"text": "🔙 Admin Dashboard", "callback_data": "admin_main_menu"},
                ],
            ]
        }
        await self.send_message(chat_id, text, reply_markup=keyboard)

    async def _handle_admin_rules(self, chat_id: int | str) -> None:
        text = (
            "📜 <b>SupremeAI Constitutional Matrix (5 Cardinal Directions)</b>\n\n"
            "🧭 <b>North (Zero Cost):</b> প্রতিটি অপারেশন $0 খরচে ফ্রি-টিয়ারে পরিচালিত হবে।\n"
            "🧬 <b>South (Self-Evolution):</b> নিজের কোড নিজে রিরাইট ও অপ্টিমাইজ করবে।\n"
            "🏷️ <b>East (Brand Exclusivity):</b> থার্ড-পার্টি নাম বা কি ইউজারের সামনে অপ্রকাশ্য।\n"
            "⚡ <b>West (Thin Client):</b> সব ক্লায়েন্ট থিন ক্লায়েন্ট হিসেবে কাজ করবে।\n"
            "🧠 <b>Center (Continuous Learning):</b> মেমোরি ও ভেক্টর ম্যাট্রিক্স চিরস্থায়ী।"
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🔙 Admin Dashboard", "callback_data": "admin_main_menu"},
                ],
            ]
        }
        await self.send_message(chat_id, text, reply_markup=keyboard)

    async def _handle_backup_now(self, chat_id: int | str) -> None:
        await self.send_message(
            chat_id, "⏳ <i>Initiating on-demand encrypted database & AI memory backup...</i>"
        )
        try:
            from tools.social.teldrive_storage import teldrive_storage

            res = await teldrive_storage.create_and_upload_backup(chat_id=chat_id)
            if res:
                await self.send_message(
                    chat_id, "✅ <b>Backup Complete!</b> File securely archived in Telegram Cloud."
                )
            else:
                await self.send_message(
                    chat_id, "⚠️ Backup creation encountered an issue. Check server logs."
                )
        except Exception as exc:
            logger.exception("On-demand backup error")
            await self.send_message(chat_id, f"❌ Backup failed: <code>{exc}</code>")

    async def _handle_abort(self, chat_id: int | str, run_id: str) -> None:
        """``/abort <run_id>`` — বাস্তব রান-ক্যান্সেলেশন (M18 P-I, issue #453 Wave-1)।

        বাংলা মন্তব্য: এটি runs state machine-এর প্রকৃত ``run_service.cancel`` পথে
        যায় — ভুয়া সাফল্য-বার্তা নেই। Fail-closed: কমান্ড admin-only (updates.py
        গেট), অজানা run_id বা state-machine বাধায় সৎ ব্যর্থতা-বার্তা যায়।
        সীমা-সত্য: Run Fabric-এর গভীর CancellationToken প্রপাগেশন M02-এর মালিকানা —
        এখানে রান-স্তরের ক্যান্সেলেশন ট্রিগার হয়, ইন-ফ্লাইট এজেন্ট-টাস্ক মৃত্যু M02
        P-B সম্পন্ন হলেই পূর্ণ হবে (প্রগতি লগে নথি)।
        """
        run_id = (run_id or "").strip()
        if not run_id:
            await self.send_message(
                chat_id,
                "🛑 <b>ব্যবহার:</b> <code>/abort &lt;run_id&gt;</code>\n"
                "<i>run_id সহ কমান্ড পাঠান — যেমন /abort 9b7f…</i>",
            )
            return

        try:
            from database.session import get_db_session_context
            from runs.api import run_service  # বাংলা: singleton এখানেই সংজ্ঞায়িত
            from runs.service import RunNotFound
            from runs.state_machine import IllegalTransition

            async with get_db_session_context() as session:
                updated = await run_service.cancel(
                    session,
                    run_id,
                    actor=f"telegram:admin:{chat_id}",
                    reason="telegram /abort command",
                )
                await session.commit()
            # বাংলা: cancel idempotent — ইতোমধ্যে terminal হলে প্রথম ফলাফলই থাকে;
            # আমরা বাস্তব অবস্থাই জানাই, ফেক 'বাতিল সফল' দাবি নয়।
            await self.send_message(
                chat_id,
                f"🛑 Run <code>{run_id}</code> — বর্তমান অবস্থা: <code>{updated.status}</code>",
            )
        except RunNotFound:
            # বাংলা: অজানা run_id — সৎ ব্যর্থতা; কোনো ফেক কনফার্মেশন নয়।
            await self.send_message(chat_id, f"❌ Run <code>{run_id}</code> খুঁজে পাওয়া যায়নি।")
        except IllegalTransition as exc:
            await self.send_message(
                chat_id,
                f"⚠️ Run <code>{run_id}</code> ক্যান্সেলযোগ্য অবস্থায় নেই: <code>{exc}</code>",
            )
        except Exception as exc:
            # বাংলা: অপ্রত্যাশিত ব্যর্থতা (DB/সেশন) — লাউড-লগ + সৎ ব্যর্থতা-বার্তা;
            # নীরব পাস মানে ব্যবহারকারী ভুয়া 'সফল' ধরে নেবে।
            logger.error(f"Telegram /abort failed for run {run_id}: {exc}")
            await self.send_message(chat_id, f"❌ Abort ব্যর্থ হয়েছে: <code>{str(exc)[:200]}</code>")
