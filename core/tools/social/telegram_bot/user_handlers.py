"""User-facing info panels for :class:`TelegramBotHandler`
(verbatim split artifact of the former single-module telegram_bot.py)."""

from __future__ import annotations

from core.config import settings


class UserHandlersMixin:
    """User-panel mixin for :class:`TelegramBotHandler`."""

    async def _handle_user_studio_info(self, chat_id: int | str) -> None:
        text = (
            "💬 <b>SupremeAI AI Chat & Coding Studio</b>\n\n"
            "• 🧠 <b>Smart AI Models:</b> Gemini 2.5 Flash + Groq Qwen/Llama\n"
            f"• 🌐 <b>Web Studio:</b> <a href='{settings.frontend_url}'>SupremeAI Dashboard</a>\n"
            "• ⚡ <b>Capabilities:</b> কোডিং, বাগ ফিক্স, ট্রান্সলেশন, ডাটাবেস ডিজাইন, ডকুমেন্ট সামারি\n\n"
            "💡 <i>যেকোনো প্রশ্ন সরাসরি এই চ্যাটে লিখুন — এআই তাৎক্ষণিক উত্তর দেবে!</i>"
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "🌐 Launch Web Studio",
                        "url": settings.frontend_url,
                    }
                ],
                [
                    {"text": "💡 Prompt Library", "callback_data": "user_skills_info"},
                    {"text": "🔙 User Dashboard", "callback_data": "user_main_menu"},
                ],
            ]
        }
        await self.send_message(chat_id, text, reply_markup=keyboard)

    async def _handle_user_desktop_info(self, chat_id: int | str) -> None:
        text = (
            "📦 <b>SupremeAI Desktop App (.exe)</b>\n\n"
            "• <b>Platform:</b> Windows 10/11 (64-bit)\n"
            "• <b>Architecture:</b> 100% Thin Client (Zero Local RAM overhead)\n"
            "• <b>Features:</b> Native Chat Studio, File Workspace, Real-time Sync\n\n"
            "👇 <i>সরাসরি ইন্সটলার ডাউনলোড করতে নিচের লিংকে ক্লিক করুন:</i>"
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "⬇️ Download Desktop (.exe)",
                        "url": "https://github.com/SaifulHaqueNiloy/supremeai/releases",
                    }
                ],
                [{"text": "🔙 User Dashboard", "callback_data": "user_main_menu"}],
            ]
        }
        await self.send_message(chat_id, text, reply_markup=keyboard)

    async def _handle_user_vscode_info(self, chat_id: int | str) -> None:
        text = (
            "🧩 <b>SupremeAI VS Code Extension (.vsix)</b>\n\n"
            "• <b>Features:</b> Inline Copilot, Code Refactor, Multi-Agent Sidecar\n"
            "• <b>Installation:</b> Download <code>.vsix</code> and run in VS Code:\n"
            "  <code>code --install-extension supremeai.vsix</code>\n\n"
            "👇 <i>লেটেস্ট VSIX প্যাকেজ ডাউনলোড করুন:</i>"
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "⬇️ Download Extension (.vsix)",
                        "url": "https://github.com/SaifulHaqueNiloy/supremeai/releases",
                    }
                ],
                [{"text": "🔙 User Dashboard", "callback_data": "user_main_menu"}],
            ]
        }
        await self.send_message(chat_id, text, reply_markup=keyboard)

    async def _handle_user_skills_info(self, chat_id: int | str) -> None:
        text = (
            "💡 <b>SupremeAI Prompt Library & Skills</b>\n\n"
            "আপনি নিচের মতো প্রম্পটগুলো দিয়ে যেকোনো কাজ করাতে পারেন:\n\n"
            "• 🐍 <b>Python & Backend:</b> <i>'FastAPI তে JWT authentication তৈরি করে দাও'</i>\n"
            "• 🌐 <b>Frontend & React:</b> <i>'একটি প্রিমিয়াম ডার্ক-মোড ল্যান্ডিং পেজ ডিজাইন কোড লেখো'</i>\n"
            "• 🗄️ <b>Database & SQL:</b> <i>'ই-কমার্সের জন্য অপ্টিমাইজড PostgreSQL স্কিমা ডিজাইন করো'</i>\n"
            "• 📝 <b>Content & Bangla:</b> <i>'এই টেক্সটের সহজ বাংলা অনুবাদ ও বুলেট পয়েন্ট সামারি তৈরি করো'</i>"
        )
        keyboard = {
            "inline_keyboard": [
                [{"text": "💬 AI Chat Studio", "callback_data": "user_studio_info"}],
                [{"text": "🔙 User Dashboard", "callback_data": "user_main_menu"}],
            ]
        }
        await self.send_message(chat_id, text, reply_markup=keyboard)

    async def _handle_user_guide_info(self, chat_id: int | str) -> None:
        text = (
            "❓ <b>SupremeAI 2.0 ইউজার গাইড ও ফিচারসমূহ</b>\n\n"
            "1. <b>Omnichannel Experience:</b> টেলিগ্রামের চ্যাট এবং ওয়েব স্টুডিও একই কেন্দ্রীয় এআই ব্রেইনে সিঙ্কড।\n"
            "2. <b>Zero-Lag Response:</b> Gemini 2.5 Flash ও Groq-এর মাধ্যমে মিলিসেকেন্ডে উত্তর পাবেন।\n"
            "3. <b>Multi-Language:</b> বাংলা ও ইংরেজি উভয় ভাষায় সাবলীল যোগাযোগ।\n"
            "4. <b>Download Options:</b> ডেস্কটপ (.exe), VS Code (.vsix) এবং ব্রাউজার ক্লায়েন্ট।"
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "🌐 Launch Web Studio",
                        "url": settings.frontend_url,
                    }
                ],
                [{"text": "🔙 User Dashboard", "callback_data": "user_main_menu"}],
            ]
        }
        await self.send_message(chat_id, text, reply_markup=keyboard)

    async def _handle_latest_build(self, chat_id: int | str) -> None:
        text = (
            "🚀 <b>SupremeAI 2.0 Build Artifacts</b>\n\n"
            "📦 <b>Desktop App (.exe):</b> <a href='https://github.com/SaifulHaqueNiloy/supremeai/releases'>Download Installer</a>\n"
            "🧩 <b>VS Code Extension (.vsix):</b> <a href='https://github.com/SaifulHaqueNiloy/supremeai/releases'>Download Extension</a>\n"
            "📱 <b>Mobile Client (.apk):</b> In CI Pipeline\n\n"
            "⚡ <i>Built with Zero Infrastructure Cost & 100% Thin Client Architecture.</i>"
        )
        await self.send_message(chat_id, text)
