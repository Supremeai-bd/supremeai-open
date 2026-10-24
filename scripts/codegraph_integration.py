#!/usr/bin/env python3
# 🔗 কোডগ্রাফ ইন্টিগ্রেশন — স্মার্ট নলেজ গ্রাফ জেনারেশন
# বাংলা মন্তব্য: প্রতিটি পুশে কোডবেসের একটি নলেজ গ্রাফ জেনারেট করে এআই এজেন্টদের বুঝতে সাহায্য করে

import json
import subprocess
from pathlib import Path
from typing import Any

try:
    from loguru import logger
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger("codegraph_integration")


class CodeGraphGenerator:
    """
    কোডবেসের নলেজ গ্রাফ জেনারেট করুন

    জেনারেট করে:
    - মডিউল ডিপেন্ডেন্সি গ্রাফ
    - ফাংশন/ক্লাস রিলেশনশিপ
    - ডেটা ফ্লো ম্যাপিং
    - ইমপ্যাক্ট এনালাইসিস
    """

    def __init__(self, repo_root: str = "."):
        self.repo_root = repo_root
        self.output_dir = Path(repo_root) / "docs" / "codebase" / "knowledge_graph"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_module_graph(self) -> dict[str, Any]:
        """পাইথন মডিউলের ডিপেন্ডেন্সি গ্রাফ তৈরি করুন"""
        logger.info("📊 Generating Python module dependency graph...")

        try:
            # pydeps ব্যবহার করে ডিপেন্ডেন্সি ম্যাপ তৈরি করুন
            subprocess.run(
                ["pip", "install", "pydeps", "-q"],
                timeout=30,
                capture_output=True
            )

            subprocess.run(
                [
                    "pydeps",
                    "backend/core",
                    "--dot",
                    "--show",
                    f"--output={self.output_dir}/module_graph.dot"
                ],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=30
            )

            logger.info("✅ Module dependency graph generated")

            return {
                "type": "module_dependency",
                "output_file": str(self.output_dir / "module_graph.dot"),
                "status": "success"
            }

        except Exception as e:
            logger.error(f"Failed to generate module graph: {e}")
            return {"status": "error", "error": str(e)}

    def analyze_code_relationships(self) -> dict[str, Any]:
        """কোডের সম্পর্ক এবং ডেটা ফ্লো এনালাইজ করুন"""
        logger.info("🔍 Analyzing code relationships...")

        relationships = {
            "imports": {},
            "class_hierarchy": {},
            "function_calls": {},
            "data_flow": {}
        }

        try:
            # রেকার্সিভভাবে সব পাইথন ফাইল খুঁজুন
            for py_file in Path(self.repo_root).rglob("backend/core/**/*.py"):
                if "__pycache__" in str(py_file):
                    continue

                self._extract_relationships(py_file, relationships)

            # রিলেশনশিপ সেভ করুন
            output_file = self.output_dir / "code_relationships.json"
            with open(output_file, "w") as f:
                json.dump(relationships, f, indent=2, ensure_ascii=False, default=str)

            logger.info(f"✅ Code relationships saved to {output_file}")

            return {
                "type": "code_relationships",
                "output_file": str(output_file),
                "relationships_count": sum(len(v) for v in relationships.values()),
                "status": "success"
            }

        except Exception as e:
            logger.error(f"Failed to analyze relationships: {e}")
            return {"status": "error", "error": str(e)}

    def _extract_relationships(self, file_path: Path, relationships: dict):
        """একটি ফাইল থেকে রিলেশনশিপ এক্সট্র্যাক্ট করুন"""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # ইমপোর্ট স্টেটমেন্ট খুঁজুন
            import re
            imports = re.findall(r"^(?:from|import)\s+(.+?)(?:\s+import|\s*$)", content, re.MULTILINE)

            rel_path = file_path.relative_to(self.repo_root)
            if imports:
                relationships["imports"][str(rel_path)] = imports

        except Exception as e:
            logger.debug(f"Error extracting relationships from {file_path}: {e}")

    def generate_impact_analysis(self, changed_files: list[str]) -> dict[str, Any]:
        """চেঞ্জড ফাইল থেকে কী প্রভাবিত হতে পারে তা বিশ্লেষণ করুন"""
        logger.info(f"📈 Analyzing impact of {len(changed_files)} changed files...")

        impact = {
            "changed_files": changed_files,
            "potentially_affected": [],
            "risk_level": "LOW",
            "recommendations": []
        }

        try:
            # প্রতিটি চেঞ্জড ফাইলের জন্য ইমপ্যাক্ট অ্যানালাইজ করুন
            for changed_file in changed_files:
                dependent_files = self._find_dependents(changed_file)
                impact["potentially_affected"].extend(dependent_files)

            # ডুপ্লিকেট রিমুভ করুন
            impact["potentially_affected"] = list(set(impact["potentially_affected"]))

            # রিস্ক লেভেল নির্ধারণ করুন
            if any("auth" in f or "security" in f for f in impact["potentially_affected"]):
                impact["risk_level"] = "HIGH"
                impact["recommendations"].append("Run security validation")

            if len(impact["potentially_affected"]) > 10:
                impact["risk_level"] = "HIGH"
                impact["recommendations"].append("Wide-spread changes - increase test coverage")

            return impact

        except Exception as e:
            logger.error(f"Impact analysis failed: {e}")
            return {"status": "error", "error": str(e)}

    def _find_dependents(self, file_path: str) -> list[str]:
        """যে ফাইলগুলো এই ফাইলের উপর নির্ভর করে তা খুঁজুন"""
        dependents = []

        try:
            module_name = Path(file_path).stem

            # সব পাইথন ফাইলে অনুসন্ধান করুন
            for py_file in Path(self.repo_root).rglob("**/*.py"):
                if str(py_file) == file_path or "__pycache__" in str(py_file):
                    continue

                try:
                    with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
                        if module_name in f.read():
                            dependents.append(str(py_file.relative_to(self.repo_root)))
                except (OSError, UnicodeDecodeError) as file_err:
                    logger.warning(f"Could not read file {py_file} to scan dependencies: {file_err}")
                except Exception as file_err:
                    logger.error(f"Unexpected error reading file {py_file}: {file_err}")

        except Exception as scan_err:
            logger.error(f"Dependency scan traversal failed: {scan_err}")

        return dependents[:10]  # লিমিট করুন

    def generate_knowledge_index(self) -> dict[str, Any]:
        """এআই এজেন্টদের জন্য ইন্ডেক্স জেনারেট করুন"""
        logger.info("📚 Generating knowledge index...")

        index = {
            "generated_at": str(Path(self.repo_root) / "docs" / "codebase"),
            "modules": {},
            "key_files": [],
            "api_endpoints": [],
            "database_models": [],
            "configuration": []
        }

        try:
            # কী ফাইল সংগ্রহ করুন
            key_patterns = [
                "backend/core/app.py",
                "backend/core/config.py",
                "backend/api/**/*.py",
                "backend/models/**/*.py"
            ]

            for pattern in key_patterns:
                for file in Path(self.repo_root).glob(pattern):
                    index["key_files"].append(str(file.relative_to(self.repo_root)))

            # সব মডিউল ডকুমেন্ট করুন
            for dir_path in Path(self.repo_root / "backend" / "core").iterdir():
                if dir_path.is_dir() and not dir_path.name.startswith("_"):
                    index["modules"][dir_path.name] = str(dir_path)

            # সেভ করুন
            output_file = self.output_dir / "knowledge_index.json"
            with open(output_file, "w") as f:
                json.dump(index, f, indent=2, ensure_ascii=False)

            logger.info("✅ Knowledge index saved")
            return {"status": "success", "output_file": str(output_file)}

        except Exception as e:
            logger.error(f"Knowledge index generation failed: {e}")
            return {"status": "error", "error": str(e)}

    def generate_full_graph(self) -> dict[str, Any]:
        """সম্পূর্ণ কোড গ্রাফ জেনারেট করুন"""
        logger.info("🔗 Generating complete code knowledge graph...")

        results = {
            "timestamp": str(Path(self.repo_root).stat().st_mtime),
            "components": {}
        }

        # সব জেনারেশন রান করুন
        results["components"]["module_graph"] = self.generate_module_graph()
        results["components"]["relationships"] = self.analyze_code_relationships()
        results["components"]["knowledge_index"] = self.generate_knowledge_index()

        logger.info("✅ Code knowledge graph generation complete")

        return results


def integrate_into_ci():
    """CI পাইপলাইনে ইন্টিগ্রেট করার জন্য ইন্সট্রাকশন"""

    instruction = """
    # CI পাইপলাইনে যোগ করুন (.github/workflows/supreme-core-ci.yml):

    - name: 📊 Generate Code Knowledge Graph
      run: |
        pip install pydeps networkx -q
        python scripts/codegraph_integration.py
      if: github.event_name == 'push'

    - name: 📚 Update AI Knowledge Base
      run: |
        python scripts/generate_smart_docs.py
        python scripts/codegraph_integration.py --update-agents
    """

    return instruction


if __name__ == "__main__":
    import sys

    generator = CodeGraphGenerator(".")

    if len(sys.argv) > 1 and sys.argv[1] == "--full":
        result = generator.generate_full_graph()
    else:
        result = generator.generate_knowledge_index()

    print(json.dumps(result, indent=2, ensure_ascii=False))
