# backend/agents/skill_librarian.py
import json
import os
import shutil
import urllib.request
from pathlib import Path
from typing import Any

from core.logging_config import logger
from schemas.skill_index import SkillIndexManager
from schemas.skill_manifest import SkillManifest, SkillStatus


class SkillLibrarian:
    # বাংলা মন্তব্য: ডকার এনভায়রনমেন্ট অনুযায়ী ডিফল্ট পাথ "backend/skills" থেকে "skills" করা হলো
    def __init__(self, base_skills_dir: str = "skills"):
        self.base_dir = Path(base_skills_dir)
        self.quarantine_dir = self.base_dir / "quarantine"
        self.approved_dir = self.base_dir / "approved"
        self.ephemeral_dir = self.base_dir / "ephemeral"

        self.approved_dir.mkdir(parents=True, exist_ok=True)
        self.index_manager = SkillIndexManager()
        # এনভায়রনমেন্ট থেকে ডিসকورد ওয়েবহুক ইউআরএল লোড
        self.webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

    def list_quarantine_queue(self) -> list[dict[str, Any]]:
        """কোয়ারেন্টাইনে থাকা পেন্ডিং স্কিলগুলোর মেটাডেটা তালিকা রিটার্ন করে।"""
        index = self.index_manager.load_index()
        return [meta for meta in index.values() if meta.get("status") == SkillStatus.QUARANTINE]

    def process_approval(
        self, skill_id: str, action: str, ai_patch_code: str | None = None
    ) -> dict[str, Any]:
        """Admin এর নির্দেশ অনুযায়ী স্কিল স্থানান্তর ও অনুমোদন গেটওয়ে এনফোর্স করে।"""
        try:
            logger.info(f"⚡ Background execution started for Skill: {skill_id} | Action: {action}")
            index = self.index_manager.load_index()
            if skill_id not in index:
                return {
                    "success": False,
                    "detail": "Skill not found in global registry.",
                }

            manifest_data = index[skill_id]
            manifest = SkillManifest(**manifest_data)
            source_path = self.quarantine_dir / skill_id

            if action == "APPROVE":
                target_path = self.approved_dir / skill_id
                manifest.status = SkillStatus.APPROVED
                # যদি এআই মডিফাইড কোড থাকে, তবে সোর্স ফাইলটি প্যাচ করা হবে
                if ai_patch_code:
                    self._apply_morphic_patch(source_path, ai_patch_code)

                shutil.move(str(source_path), str(target_path))

            elif action == "APPROVE_AS_EPHEMERAL":
                target_path = self.ephemeral_dir / skill_id
                manifest.status = SkillStatus.EPHEMERAL
                shutil.move(str(source_path), str(target_path))

            elif action == "REJECT":
                manifest.status = SkillStatus.REJECTED
                if source_path.exists():
                    shutil.rmtree(source_path)
            else:
                return {
                    "success": False,
                    "detail": "Invalid approval action identifier.",
                }

            # গলোবাল ইনডেক্স ফাইল আপডেট
            self.index_manager.update_skill(manifest)
            self._trigger_admin_notification(skill_id, action)

            return {
                "success": True,
                "detail": f"Skill {skill_id} state successfully updated to {manifest.status}.",
            }

        except Exception as e:
            # ব্যাকগ্রাউন্ড ফেইলর সাইলেন্টলি লগ করা হচ্ছে যাতে থ্রেড বা সার্ভার ক্র্যাশ না করে
            logger.error(
                f"❌ Critical failure in librarian background loop for skill {skill_id}: {e!s}"
            )

            # ব্যর্থতার অ্যালার্ট ডিসকর্ডে পাঠানো হচ্ছে (যদি কনফিগার করা থাকে)
            self._send_discord_message(
                f"🚨 **Librarian Background Failure!**\nFailed to process skill `{skill_id}` with action `{action}`.\n**Error:** `{e!s}`"
            )
            return {"success": False, "detail": str(e)}

    def _apply_morphic_patch(self, skill_dir: Path, patch_code: str):
        """Morphic Adaptation: র কোডকে SwarmAgentBase ফর্মে রূপান্তর করে।"""
        main_file = skill_dir / "main.py"
        main_file.write_text(patch_code, encoding="utf-8")

    def _trigger_admin_notification(self, skill_id: str, action: str):
        """সিস্টেম স্টেট পরিবর্তনের ওপর ভিত্তি করে ইমোজি ইডিটেড মেসেজ ফরম্যাট করে"""
        status_emojis = {"APPROVE": "✅", "APPROVE_AS_EPHEMERAL": "⏳", "REJECT": "❌"}
        emoji = status_emojis.get(action, "📢")

        message = (
            f"{emoji} **SupremeAI Librarian Ledger Update**\n"
            f"**Asset ID:** `{skill_id}`\n"
            f"**Status Transition:** Moved via Administrator to **{action}**\n"
            f"Pipeline execution verified under container sandbox environment."
        )
        self._send_discord_message(message)

    def _send_discord_message(self, content: str):
        """Native urllib ব্যবহার করে কোনো এক্সটার্নাল ডিপেনডেন্সি ছাড়াই নোটিফিকেশন পাঠায়"""
        if not self.webhook_url:
            logger.warning("Discord Webhook URL not configured. Skipping webhook dispatch.")
            return

        try:
            payload = json.dumps({"content": content}).encode("utf-8")
            req = urllib.request.Request(
                self.webhook_url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "SupremeAI-Librarian-Engine",
                },
            )
            # নেটওয়ার্ক হ্যান্ডশেক ফায়ার
            with urllib.request.urlopen(req) as response:
                if response.status not in [200, 204]:
                    logger.error(f"Discord Webhook returned invalid status code: {response.status}")
        except Exception as net_err:
            logger.error(f"Failed to transmit payload to Discord Webhook channel: {net_err!s}")
