# backend/agents/skill_ingestor.py
import ast
import hashlib
import io
import os
import re
import shutil
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from core.logging_config import logger
from sandbox.docker_sandbox import DockerSandbox
from schemas.skill_index import SkillIndexManager
from schemas.skill_manifest import SkillManifest, SkillStatus

# রিলেটিভ ইম্পোর্ট ব্যবহার করে টাইপ চেকিং এবং পাথ রেজোলিউশন ঠিক করা হলো
from .morphic_adapter import MorphicAdapter  # Using relative import from same directory


class SkillIngestor:
    # বাংলা মন্তব্য: ডকার এনভায়রনমেন্ট অনুযায়ী ডিফল্ট পাথ "backend/skills" থেকে "skills" করা হলো
    def __init__(self, base_skills_dir: str = "skills"):
        self.base_dir = Path(base_skills_dir)
        self.staging_dir = self.base_dir / "staging"
        self.quarantine_dir = self.base_dir / "quarantine"
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)

        self.index_manager = SkillIndexManager()
        self.sandbox = DockerSandbox()
        self.morphic_adapter = MorphicAdapter()

    def static_ast_safety_check(self, code: str) -> tuple[bool, str]:
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in [
                            "os",
                            "subprocess",
                            "sys",
                            "requests",
                            "urllib",
                            "socket",
                        ]:
                            return False, f"Forbidden import found: {alias.name}"
                elif isinstance(node, ast.ImportFrom):
                    if node.module in [
                        "os",
                        "subprocess",
                        "sys",
                        "requests",
                        "urllib",
                        "socket",
                    ]:
                        return False, f"Forbidden from-import found: {node.module}"
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id in [
                        "eval",
                        "exec",
                    ]:
                        return False, "Dangerous code pattern found: exec/eval usage."
            return True, "AST verified."
        except SyntaxError:
            return False, "Invalid Python syntax."

    def ingest_mcp_skill(
        self, manifest: SkillManifest, zip_url: str, entry_file: str, test_payload: str
    ) -> dict[str, Any]:
        # 🛡️ ১. কঠোর Path Traversal এবং Injection ব্লকিং
        if not re.match(r"^[a-zA-Z0-9_]+$", manifest.skill_id):
            return {"success": False, "detail": "Malicious Skill ID pattern blocked."}

        if not self.index_manager.is_source_allowed(str(manifest.source_url)):
            manifest.status = SkillStatus.REJECTED
            self.index_manager.update_skill(manifest)
            return {"success": False, "detail": "Source domain unauthorized."}

        # 🛡️ SECURITY FIX: zip_url আলাদা প্যারামিটার, এটা manifest.source_url থেকে
        # ভিন্ন হতে পারে — শুধু source_url whitelist-চেক করলে zip_url দিয়ে SSRF
        # আক্রমণ সম্ভব ছিল (whitelisted source_url পাস করে যেকোনো zip_url দিয়ে
        # internal/cloud-metadata endpoint বা file:// URL ফেচ করা যেত)। zip_url-ও
        # একই whitelist-এর বিপরীতে যাচাই করা হলো।
        if not self.index_manager.is_source_allowed(zip_url):
            manifest.status = SkillStatus.REJECTED
            self.index_manager.update_skill(manifest)
            return {"success": False, "detail": "Zip download domain unauthorized."}

        try:
            with urllib.request.urlopen(zip_url) as response:
                zip_data = response.read()

            if hashlib.sha256(zip_data).hexdigest() != manifest.checksum:
                manifest.status = SkillStatus.REJECTED
                self.index_manager.update_skill(manifest)
                return {"success": False, "detail": "Checksum mismatch."}

            skill_staging_dir = self.staging_dir / manifest.skill_id
            if skill_staging_dir.exists():
                shutil.rmtree(skill_staging_dir)
            skill_staging_dir.mkdir(parents=True, exist_ok=True)

            # 🛡️ ২. Anti-Zip Slip Implementation
            with zipfile.ZipFile(io.BytesIO(zip_data)) as archive:
                for member in archive.namelist():
                    # টার্গেট ডিরেক্টরির বাইরে রিলেটিভ ট্রাভার্সাল (../) চেক করা
                    target_path = Path(os.path.abspath(skill_staging_dir / member))
                    base_path = Path(os.path.abspath(skill_staging_dir))

                    if not target_path.resolve().is_relative_to(base_path.resolve()):
                        raise PermissionError("🛑 Zip-Slip Malicious Payload Detected and Defused!")

                archive.extractall(path=skill_staging_dir)

            entry_path = skill_staging_dir / entry_file
            if not entry_path.exists():
                return {"success": False, "detail": "Entry point missing."}

            code_content = entry_path.read_text(encoding="utf-8")
            is_safe, static_msg = self.static_ast_safety_check(code_content)
            if not is_safe:
                manifest.status = SkillStatus.REJECTED
                self.index_manager.update_skill(manifest)
                return {"success": False, "detail": f"Static Failure: {static_msg}"}

            # ---- MORPHIC ADAPTATION LAYER START ----
            logger.info(
                f"🧬 [MORPHIC ENGINE] Triggering AI Refactoring for skill: {manifest.skill_id}"
            )
            morphic_res = self.morphic_adapter.adapt_code_to_contract(
                raw_code=code_content, skill_description=manifest.description
            )

            if not morphic_res["success"]:
                manifest.status = SkillStatus.REJECTED
                self.index_manager.update_skill(manifest)
                return {"success": False, "detail": morphic_res["detail"]}

            # এআই জেনারেট করা কোডটি স্টেজিং ফাইলে ওভাররাইট করা হচ্ছে পুনরায় টেস্টের জন্য
            entry_path.write_text(morphic_res["code"], encoding="utf-8")
            # ---- MORPHIC ADAPTATION LAYER END ----

            manifest.status = SkillStatus.QUARANTINE
            self.index_manager.update_skill(manifest)

            sandbox_res = self.sandbox.run_quarantine_test(
                skill_staging_dir, entry_file, test_payload
            )

            if sandbox_res["exit_code"] == 0:
                # 🔄 ৩. Staging to Quarantine Safe Move (ওভাররাইট পলিসি সহ)
                skill_quarantine_dir = self.quarantine_dir / manifest.skill_id
                if skill_quarantine_dir.exists():
                    shutil.rmtree(skill_quarantine_dir)

                shutil.move(str(skill_staging_dir), str(skill_quarantine_dir))

                return {
                    "success": True,
                    "status": "QUARANTINE_PASSED",
                    "detail": "Skill verified and safely moved to quarantine queue.",
                }
            else:
                manifest.status = SkillStatus.REJECTED
                self.index_manager.update_skill(manifest)
                return {
                    "success": False,
                    "status": "REJECTED",
                    "detail": "Sandbox test failed.",
                }

        except Exception as e:
            manifest.status = SkillStatus.REJECTED
            self.index_manager.update_skill(manifest)
            return {"success": False, "detail": f"Pipeline failure: {e!s}"}
