"""Skill Provisioner Engine for SupremeAI 2.0.

বাংলা: ইউজারের এনভায়রনমেন্টে ব্যাকগ্রাউন্ড সিস্টেম ও পাইথন ডিপেনডেন্সি অটো-ইনস্টলেশন ইঞ্জিন।
"""

import asyncio
import shutil
import sys
from typing import Any

from core.logging_config import logger

from .skill_registry import skill_registry


class SkillProvisioner:
    """Provisions required system and Python dependencies for skills."""

    def __init__(self):
        self.installed_packages: set = set()

    def check_system_dependency(self, command_name: str) -> bool:
        """Check if a system CLI command is available."""
        return shutil.which(command_name) is not None

    async def provision_skill(self, skill_id: str) -> dict[str, Any]:
        """Check and provision dependencies for a given skill ID.

        বাংলা: প্রদত্ত স্কিলের প্রয়োজনীয় ডিপেনডেন্সি চেক ও ইনস্টল নিশ্চিত করে।
        """
        skill_meta = skill_registry.get_skill(skill_id)
        if not skill_meta:
            return {
                "status": "error",
                "message": f"Skill '{skill_id}' not found in registry",
            }

        missing_system = []
        for pkg in skill_meta.get("system_packages", []):
            if not self.check_system_dependency(pkg):
                missing_system.append(pkg)

        missing_python = []
        for py_pkg in skill_meta.get("dependencies", []):
            try:
                __import__(py_pkg.split("==")[0].split(">=")[0].strip())
            except ImportError:
                missing_python.append(py_pkg)

        if missing_python:
            logger.info(f"Installing Python packages for skill {skill_id}: {missing_python}")
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pip",
                "install",
                *missing_python,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error(f"Failed to install Python packages for {skill_id}: {stderr.decode()}")
                return {
                    "status": "failed",
                    "reason": "pip_install_failure",
                    "details": stderr.decode(),
                }

        return {
            "status": "success",
            "skill_id": skill_id,
            "missing_system_warnings": missing_system,
            "provisioned_python": missing_python,
        }


skill_provisioner = SkillProvisioner()
