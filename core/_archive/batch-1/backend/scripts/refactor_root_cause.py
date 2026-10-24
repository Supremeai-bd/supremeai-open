import ast
import os
import sys
from pathlib import Path

from core.errors.error_bus import with_error_bus
from core.logging_config import logger


@with_error_bus("process_file")
def process_file(filepath: Path, dry_run: bool = False):
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.debug(f"Skipping {filepath} due to read error: {e}")
        return

    try:
        ast.parse(content)  # শুধু syntax validity যাচাই — ফলাফল (tree) ব্যবহৃত হয় না
    except Exception as e:
        logger.debug(f"Skipping {filepath} due to syntax error: {e}")
        return

    # In a real implementation we would use libcst or a robust regex strategy to replace in place,
    # because AST unparsing removes comments and exact formatting.
    # For this AST agent script we will use a regex-based robust replacement for the two exact patterns.

    import re

    original_content = content
    modified = False

    # 1. Anti-Silent Error Pattern Replacement:
    # Match: except Exception as e: (or except Exception:)
    # Followed by: logger.error(..., e) and return or pass
    # We will inject the error_event_bus.emit() call.
    # This is a complex multiline replacement, for now we will inject an import at the top
    # and use regex to replace basic `except Exception:` that just has `pass`.

    pass_pattern = re.compile(r"(except\s+Exception(\s+as\s+\w+)?:\s*\n\s*)pass", re.MULTILINE)

    @with_error_bus("replacer")
    def replacer(match):
        prefix = match.group(1)
        # Use a safe fallback for the exception variable name
        var_name = match.group(2).strip().split()[-1] if match.group(2) else "e"
        if not match.group(2):
            # If no variable was captured, we need to modify the except statement
            prefix = prefix.replace("except Exception:", "except Exception as e:")
            var_name = "e"

        replacement = f"{prefix}from core.logging_config import logger\n"
        indent = prefix.split("\n")[-1]
        replacement += f"{indent}logger.error(f'Caught exception: {{{var_name}}}')\n"
        replacement += f"{indent}from core.messaging.event_bus import error_event_bus, ErrorEvent\n"
        replacement += f"{indent}error_event_bus.emit(ErrorEvent(module='auto_refactor', error_type='GENERIC_EXCEPTION', message=str({var_name})[:200], severity='ERROR', structured_context=ErrorContext(module='auto_fixed')))"
        return replacement

    new_content, count = pass_pattern.subn(replacer, original_content)
    if count > 0:
        modified = True
        original_content = new_content

    # 2. Anti-Hardcode os.getenv:
    # Replace os.getenv("FOO", "bar") with getattr(settings, "foo", "bar")
    # This requires adding from core.config import settings
    getenv_pattern = re.compile(r'os\.getenv\((["\'])(.*?)\1(?:,\s*(.*?))?\)')

    def getenv_replacer(match):
        env_var = match.group(2)
        default_val = match.group(3)
        setting_attr = env_var.lower()
        if default_val:
            return f'getattr(settings, "{setting_attr}", {default_val})'
        else:
            return f'getattr(settings, "{setting_attr}", None)'

    new_content, count = getenv_pattern.subn(getenv_replacer, original_content)
    if count > 0:
        if "from core.config import settings" not in new_content:
            # Inject at top
            lines = new_content.split("\n")
            for i, line in enumerate(lines):
                if line.startswith("import ") or line.startswith("from "):
                    lines.insert(i, "from core.config import settings")
                    break
            new_content = "\n".join(lines)
        modified = True

    if modified:
        if not dry_run:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)
            logger.debug(f"Refactored: {filepath}")
        else:
            logger.debug(f"[DRY RUN] Would refactor: {filepath}")


def main():
    root_dir = Path(r"c:\Users\n\supremeai\supremeai_2.0\backend")
    target_dirs = ["api", "brain", "tools"]
    dry_run = "--dry-run" in sys.argv

    for t_dir in target_dirs:
        dir_path = root_dir / t_dir
        if not dir_path.exists():
            continue
        for root, _, files in os.walk(dir_path):
            for file in files:
                if file.endswith(".py"):
                    process_file(Path(root) / file, dry_run=dry_run)


if __name__ == "__main__":
    main()
