# backend/agents/skill_gc.py
import shutil
import tarfile

# datetime class এবং timedelta উভয়ই import করা হচ্ছে — utcnow() ব্যবহারের জন্য
from datetime import datetime, timedelta
from pathlib import Path

from core.logging_config import logger
from core.utils.time_utils import utc_now
from schemas.skill_index import SkillIndexManager
from schemas.skill_manifest import SkillManifest, SkillStatus


class SkillGarbageCollector:
    # বাংলা মন্তব্য: ডকার এনভায়রনমেন্ট অনুযায়ী ডিফল্ট পাথ "backend/skills" থেকে "skills" করা হলো
    def __init__(self, base_skills_dir: str = "skills"):
        self.base_dir = Path(base_skills_dir)
        self.approved_dir = self.base_dir / "approved"
        self.archive_dir = self.base_dir / "archive"
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        self.index_manager = SkillIndexManager()
        # কোর সিস্টেম স্কিল যা কোনো অবস্থাতেই ছাঁটাই করা যাবে না
        self.SYSTEM_CRITICAL_SKILLS = [
            "browser_agent",
            "code_smell_detector",
            "mcp_router",
        ]

    def run_daily_cleanup(self, usage_threshold: int = 5, days_threshold: int = 30) -> list[str]:
        """কম ব্যবহৃত স্কিলগুলো আইডেন্টিফাই করে এবং গ্রেস পিরিয়ড ও আর্কাইভ এনফোর্স করে।"""
        index = self.index_manager.load_index()
        now = datetime.utcnow()
        cutoff_date = now - timedelta(days=days_threshold)
        purged_skills = []

        for skill_id, meta in list(index.items()):
            # সিস্টেম রিকোয়ার্ড বা পিনড স্কিল স্কিপ করা হচ্ছে
            if skill_id in self.SYSTEM_CRITICAL_SKILLS or meta.get("is_pinned", False):
                continue

            manifest = SkillManifest(**meta)

            # শেষ ব্যবহারের সময় বা তৈরির সময় নির্ধারণ
            last_used_raw = manifest.last_used_at or manifest.created_at

            # ISO string → datetime parse (string হলে convert করতে হবে)
            if isinstance(last_used_raw, str):
                try:
                    # বাংলা: আগের কোডে .rstrip("+00:00") ভুলভাবে ব্যবহার হয়েছিল — rstrip
                    # একটা character SET হিসেবে কাজ করে, পুরো substring হিসেবে না, তাই এটা
                    # timestamp-এর শেষের আসল সংখ্যাও মুছে দিতে পারত (যেমন ...T00:00:00+00:00)।
                    # সঠিক ফিক্স: শুধু "Z" suffix-টা "+00:00" দিয়ে replace করা, বাড়তি strip না করে।
                    last_used = datetime.fromisoformat(
                        last_used_raw[:-1] + "+00:00"
                        if last_used_raw.endswith("Z")
                        else last_used_raw
                    )
                except ValueError:
                    # Parse করতে না পারলে খুব পুরনো ধরে নাও
                    last_used = datetime.min
            else:
                last_used = last_used_raw

            # ক্যান্ডিডেট সিলেকশন: নির্দিষ্ট দিনে ব্যবহার threshold-এর কম হলে
            if manifest.usage_count < usage_threshold and last_used < cutoff_date:
                if manifest.status == SkillStatus.APPROVED:
                    # ⚠️ ধাপ ১: সরাসরি ডিলেট না করে Deprecated Pending করা ও নোটিফিকেশন
                    manifest.status = SkillStatus.DEPRECATED_PENDING
                    self.index_manager.update_skill(manifest)
                    logger.info(
                        f"⚠️ [GC WARNING] Skill '{skill_id}' marked as DEPRECATED_PENDING. Grace period started."
                    )

                elif manifest.status == SkillStatus.DEPRECATED_PENDING:
                    # 📦 ধাপ ২: গ্রেস পিরিয়ড পার হলে নিরাপদ রিকভারেবল আর্কাইভ তৈরি
                    self._create_recoverable_archive(skill_id)

                    # 🧹 ফাইল সিস্টেম এবং ইনডেক্স থেকে ক্লিনআপ
                    skill_path = self.approved_dir / skill_id
                    if skill_path.exists():
                        shutil.rmtree(skill_path)

                    # ইনডেক্স থেকে রিমুভ
                    global_index = self.index_manager.load_index()
                    if skill_id in global_index:
                        del global_index[skill_id]
                        with open(self.index_manager.path, "w") as f:
                            import json

                            json.dump(global_index, f, indent=4)

                    purged_skills.append(skill_id)
                    logger.info(
                        f"✨ [GC PURGE] Stale asset '{skill_id}' successfully archived and cleared."
                    )

        return purged_skills

    def _create_recoverable_archive(self, skill_id: str):
        """ডিলেট করার আগে অডিট স্ন্যাপশট ও টারবল ব্যাকআপ তৈরি করে।"""
        target_path = self.approved_dir / skill_id
        if not target_path.exists():
            return

        archive_file = self.archive_dir / f"{skill_id}_{utc_now().strftime('%Y%m%d')}.tar.gz"
        with tarfile.open(archive_file, "w:gz") as tar:
            tar.add(target_path, arcname=skill_id)
