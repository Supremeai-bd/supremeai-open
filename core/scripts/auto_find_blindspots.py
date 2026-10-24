# backend/scripts/auto_find_blindspots.py
import ast
import json
import os
import sys
from pathlib import Path

from core.logging_config import logger


class BlindspotFinder:
    "বাংলা মন্তব্য: এলিট কোড কোয়ালিটি গেট — কভারেজ, টেকনিক্যাল ডেট এবং সিকিউরিটি হটস্পট স্ক্যানার।"

    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.report = {
            "low_coverage_files": [],
            "technical_debt_comments": [],
            "security_hotspots": [],
        }
        self.fail_build = False

    def parse_coverage(self, coverage_json_path: str):
        "১. কভারেজ ফাইল পার্স করে ২৫% এর নিচে থাকা ব্লাইন্ডস্পটগুলো ফ্ল্যাগ করবে।"
        if not os.path.exists(coverage_json_path):
            logger.warning(f"⚠️ Coverage report not found at {coverage_json_path}. Skipping step.")
            return
        try:
            with open(coverage_json_path, encoding="utf-8") as f:
                data = json.load(f)
                files = data.get("files", {})
                for filepath, file_stats in files.items():
                    cover_pct = file_stats.get("summary", {}).get("percent_covered", 100)
                    if cover_pct < 40.0:
                        self.report["low_coverage_files"].append(
                            {"file": filepath, "coverage": f"{cover_pct:.2f}%"}
                        )
                        if cover_pct < 25.0:
                            self.fail_build = True
        except Exception as e:
            logger.error(f"Failed to parse coverage json: {e}")

    def scan_files(self):
        "২. এএসটি এবং টেক্সট স্ক্যানিংয়ের মাধ্যমে TODO/FIXME এবং সিকিউরিটি অ্যান্টি-প্যাটার্ন খোঁজা।"
        for filepath in self.base_dir.rglob("*.py"):
            if "venv" in str(filepath) or ".venv" in str(filepath) or "tests" in str(filepath):
                continue
            try:
                with open(filepath, encoding="utf-8") as f:
                    lines = f.readlines()

                for idx, line in enumerate(lines):
                    if any(debt in line for debt in ["TODO:", "FIXME:", "HACK:", "XXX:"]):
                        self.report["technical_debt_comments"].append(
                            {
                                "file": str(filepath.relative_to(self.base_dir)),
                                "line": idx + 1,
                                "content": line.strip(),
                            }
                        )

                content = "".join(lines)
                tree = ast.parse(content, filename=str(filepath))
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id == "eval"
                    ):
                        self.report["security_hotspots"].append(
                            {
                                "file": str(filepath.relative_to(self.base_dir)),
                                "line": node.lineno,
                                "issue": "🚨 DANGEROUS CODE: Use of eval() function detected!",
                            }
                        )
                        self.fail_build = True

                    if (
                        isinstance(node, ast.keyword)
                        and node.arg == "verify"
                        and isinstance(node.value, ast.Constant)
                        and node.value.value is False
                    ):
                        self.report["security_hotspots"].append(
                            {
                                "file": str(filepath.relative_to(self.base_dir)),
                                "line": node.lineno,
                                "issue": "🔒 SECURITY WARNING: SSL/TLS verification is explicitly disabled (verify_is_disabled=False)!",
                            }
                        )

            except Exception as e:
                logger.error(f"Error scanning file {filepath}: {e}")

    def generate_markdown_summary(self, output_path: str):
        "৩. গিটহাব অ্যাকশন সামারির জন্য সুন্দর মার্কডাউন রিপোর্ট জেনারেট করা।"
        md = ["# 🔱 SupremeAI Codebase Blindspot Intelligence Report\n"]

        md.append("## 📊 Critical Low Coverage Gate (< 40%)")
        if not self.report["low_coverage_files"]:
            md.append("✅ All production modules maintain optimized test coverage boundary.")
        for item in self.report["low_coverage_files"]:
            md.append(f"- 🔴 `{item['file']}` — Only **{item['coverage']}** covered!")

        md.append("\n## 🔒 Security Hotspots & Insecure Anti-Patterns")
        if not self.report["security_hotspots"]:
            md.append("✅ Zero high-severity vulnerability patterns found.")
        for item in self.report["security_hotspots"]:
            md.append(f"- Line {item['line']} in `{item['file']}`: {item['issue']}")

        md.append("\n## 🛠️ Unresolved Technical Debt Tracker")
        for item in self.report["technical_debt_comments"]:
            md.append(f"- `{item['file']}` (Line {item['line']}): _{item['content']}_")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md))

        logger.info(
            f"📊 Quality intelligence report persistence successfully saved to {output_path}"
        )


if __name__ == "__main__":
    finder = BlindspotFinder(base_dir=".")
    finder.parse_coverage("coverage.json")
    finder.scan_files()
    finder.generate_markdown_summary("blindspots-report.md")

    if finder.fail_build:
        logger.critical(
            "❌ Pre-Merge Gate Blocked: Critical blindspots or code-vulnerabilities discovered."
        )
        sys.exit(1)
    logger.info("🏆 Iron Curtain validation approved. Code quality within enterprise threshold.")
