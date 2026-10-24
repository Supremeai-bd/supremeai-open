"""Validate the repository's baseline command registry without executing commands."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = Path(__file__).with_name("baseline_commands.json")
PACKAGE = ROOT / "package.json"


def load_registry() -> dict[str, Any]:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def package_scripts() -> set[str]:
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    return set(package.get("scripts", {}))


def referenced_script(command: str) -> str | None:
    parts = command.split()
    if len(parts) >= 3 and parts[0] == "pnpm" and parts[1] == "run":
        return parts[2]
    return None


def validate_registry() -> list[str]:
    registry = load_registry()
    scripts = package_scripts()
    errors: list[str] = []
    for category, commands in registry.get("commands", {}).items():
        if not commands:
            errors.append(f"{category}: command list is empty")
        for command in commands:
            script = referenced_script(command)
            if script and script not in scripts:
                errors.append(f"{category}: unknown package script '{script}'")
    for command in registry.get("policy", {}).get("never_execute_automatically", []):
        if command not in sum(registry.get("commands", {}).values(), []):
            errors.append(f"policy command is not registered: '{command}'")
    return errors


def main() -> int:
    errors = validate_registry()
    if errors:
        print("BASELINE_REGISTRY=FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("BASELINE_REGISTRY=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
