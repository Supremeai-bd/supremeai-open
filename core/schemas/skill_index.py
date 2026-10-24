# backend/schemas/skill_index.py
# বাংলা মন্তব্য: SkillIndexManager — .index.json ফাইলের atomic read/write manager।
# স্থায়ী ফিক্স: __file__ থেকে absolute path নির্ণয় করা হয়েছে
# যাতে CI/CD-তে working directory যেখানেই থাকুক, path সবসময় সঠিক থাকে।
import json
import os
from pathlib import Path

from .skill_manifest import SkillManifest

VERIFIED_MCP_SOURCES = [
    "https://github.com/modelcontextprotocol/servers",
    "https://github.com/paykaribazaronline/supreme-verified-skills",
]

# বাংলা মন্তব্য: __file__ থেকে absolute path — relative path CI-তে ভাঙে
_DEFAULT_INDEX_PATH = (
    Path(__file__).resolve().parent.parent / "skills" / "manifests" / ".index.json"
)


class SkillIndexManager:
    def __init__(self, index_path: Path | str | None = None):
        # বাংলা মন্তব্য: index_path না দিলে এই ফাইলের পজিশন থেকে absolute path ব্যবহার করা হয়
        # "backend/skills/manifests/.index.json" relative path CI-তে FileNotFoundError দেয়
        self.path = Path(index_path) if index_path is not None else _DEFAULT_INDEX_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._atomic_write({})

    def load_index(self) -> dict[str, dict]:
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def update_skill(self, manifest: SkillManifest):
        index = self.load_index()
        index[manifest.skill_id] = manifest.model_dump(mode="json")
        self._atomic_write(index)

    def _atomic_write(self, data: dict):
        """🔒 Temporary file swap এর মাধ্যমে race condition মুক্ত atomic write নিশ্চিত করে"""
        temp_path = self.path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        # কার্নেল স্তরে পারমাণবিক প্রতিস্থাপন (Atomic overwrite)
        os.replace(temp_path, self.path)

    def is_source_allowed(self, url: str) -> bool:
        return any(url.startswith(src) for src in VERIFIED_MCP_SOURCES)
