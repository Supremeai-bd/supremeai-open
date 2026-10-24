import os
import re


def refactor_logging(root_dir):
    for root, dirs, files in os.walk(root_dir):
        if "venv" in root or ".venv" in root or "__pycache__" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                with open(path, encoding="utf-8") as f:
                    content = f.read()

                # Check if file has logging import
                if (
                    "import logging" not in content
                    and "from logging" not in content
                    and "logging." not in content
                ):
                    continue

                # Replace from core.logging_config import logger
                new_content = re.sub(
                    r"import logging(\r?\n)", r"from core.logging_config import logger\1", content
                )

                # Replace  with nothing (loguru logger is already imported)
                new_content = re.sub(
                    r"[_a-zA-Z0-9]*logger\s*=\s*logging\.getLogger\([^\)]+\)(\r?\n)?",
                    "",
                    new_content,
                )
                new_content = re.sub(r"logging\.getLogger\([^\)]+\)", "logger", new_content)

                # Replace logging.info, logging.error etc with logger.info, logger.error
                new_content = re.sub(
                    r"logging\.(debug|info|warning|error|critical|exception|warn)\(",
                    r"logger.\1(",
                    new_content,
                )

                # Fix up any leftover logger issues
                new_content = new_content.replace("logger", "logger")

                if new_content != content:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    print(f"Refactored: {path}")


if __name__ == "__main__":
    refactor_logging("F:/supremeai/backend")
