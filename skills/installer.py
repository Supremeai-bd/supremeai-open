import os
import re
import subprocess
import sys

from loguru import logger

from .registry import SkillRegistry

_SKILL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

# P0 (Task 9-c2): runtime `pip install` allowlist. Dynamic skills may only pull
# the dependencies actually used by the bundled skills/dynamic/* package
# (httpx + beautifulsoup4/bs4 by web_scraper.py, pandas declared by the
# marketplace seed for csv_exporter). Anything else is REJECTED — untrusted
# dependency names must never be piped into a shell/pip unchecked.
ALLOWED_SKILL_DEPENDENCIES = frozenset(
    {
        "httpx",
        "beautifulsoup4",
        "bs4",
        "pandas",
    }
)

# P0 (Task 9-c2): production requires an explicit operator opt-in for runtime
# dependency installation at all (supply-chain / arbitrary-package risk).
_SKILL_DEPS_ENABLED_ENV = "SUPREMEAI_SKILL_DEPS_ENABLED"


def _production_environment() -> bool:
    """Production detection that degrades gracefully when core.* is not importable
    (the root-level ``skills`` package can be imported without backend/ on sys.path)."""
    try:
        from core.degraded_mode import is_production

        return is_production()
    except Exception:
        return (os.getenv("ENV", "") or "").lower() in {"production", "prod"}


def _dependency_base_name(dep: str) -> str:
    """Normalize a pip requirement ('httpx>=0.24', 'bs4[extra]') to its base name."""
    name = str(dep).strip()
    for sep in ("==", ">=", "<=", "~=", "!=", ">", "<", "[", "!"):
        if sep in name:
            name = name.split(sep, 1)[0]
    return name.strip().lower()


class SecurityError(Exception):
    """Exception raised for security violations during skill installation."""



class SkillInstaller:
    """Installs dependencies and registers code packages as dynamic skills."""

    def __init__(self, registry: SkillRegistry = None, skills_dir: str | None = None):
        self.registry = registry or SkillRegistry()
        if skills_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.skills_dir = os.path.join(base_dir, "skills", "dynamic")
        else:
            self.skills_dir = skills_dir

    def _sanitize_skill_name(self, name: str) -> str:
        if not name or not isinstance(name, str):
            raise ValueError("Invalid skill name.")
        if not _SKILL_NAME_PATTERN.match(name):
            raise ValueError("Skill name contains invalid characters.")
        if ".." in name or name.startswith(("/", "\\")):
            raise ValueError("Path traversal detected in skill name.")
        return name

    def _pre_write_security_scan(self, code: str) -> None:
        try:
            import ast

            tree = ast.parse(code, filename="<skill>")
        except SyntaxError as e:
            raise ValueError(f"Syntax error in skill code: {e}") from e

        banned_modules = {
            "os",
            "sys",
            "subprocess",
            "shutil",
            "socket",
            "pty",
            "importlib",
            "code",
            "runpy",
            "pickle",
            "marshal",
            "tempfile",
            "urllib",
            "http",
            "requests",
            "ctypes",
            "__builtins__",
        }
        banned_names = {
            "eval",
            "exec",
            "compile",
            "__import__",
            "getattr",
            "setattr",
            "delattr",
            "globals",
            "locals",
            "open",
            "input",
            "breakpoint",
        }

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                modules = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module]
                )
                for mod_name in modules:
                    if mod_name and mod_name.split(".")[0] in banned_modules:
                        raise SecurityError(
                            f"Banned import '{mod_name}' blocked in skill install."
                        )
            elif isinstance(node, ast.Attribute) and (
                node.attr.startswith("__") or node.attr in banned_names
            ):
                raise SecurityError(
                    f"Malicious attribute access '{node.attr}' blocked in skill install."
                )
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in banned_names
            ):
                raise SecurityError(
                    f"Call to banned function '{node.func.id}' blocked in skill install."
                )

    def install_dependencies(self, dependencies: list[str]) -> bool:
        """Executes pip to install missing libraries dynamically.

        P0 (Task 9-c2): hardening —
        1. In production this is refused outright unless the operator explicitly
           sets ``SUPREMEAI_SKILL_DEPS_ENABLED=true``.
        2. Every dependency must be in ``ALLOWED_SKILL_DEPENDENCIES``; anything
           else raises SecurityError BEFORE the subprocess is ever spawned.
        The subprocess call itself is unchanged.
        """
        if not dependencies:
            return True

        if _production_environment():
            if (os.getenv(_SKILL_DEPS_ENABLED_ENV, "") or "").strip().lower() != "true":
                logger.critical(
                    "P0: dynamic skill dependency installation refused in production — "
                    f"set {_SKILL_DEPS_ENABLED_ENV}=true to opt in. Requested: {dependencies!r}"
                )
                raise SecurityError(
                    "Runtime dependency installation is disabled in production "
                    f"(set {_SKILL_DEPS_ENABLED_ENV}=true to opt in)."
                )

        rejected = [d for d in dependencies if _dependency_base_name(d) not in ALLOWED_SKILL_DEPENDENCIES]
        if rejected:
            logger.error(
                f"P0: rejected non-allowlisted skill dependency/ies {rejected!r} — "
                f"allowed: {sorted(ALLOWED_SKILL_DEPENDENCIES)!r}"
            )
            raise SecurityError(
                f"Dependency/ies {rejected!r} are not in ALLOWED_SKILL_DEPENDENCIES — "
                "installation refused."
            )

        logger.info(f"Dynamic Installer installing: {dependencies}")
        try:
            cmd = [sys.executable, "-m", "pip", "install"] + dependencies
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info("Installation completed successfully.")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install dependencies: {e.stderr}")
            return False

    def install_skill_from_source(
        self,
        name: str,
        code: str,
        version: str,
        description: str,
        dependencies: list[str] | None = None,
        uss: dict | None = None,
    ) -> bool:
        """Writes custom skill code into the local skills workspace and registers it.
        বাংলা মন্তব্য: মিউটেবল ডিফল্ট আর্গুমেন্ট (List[str] = []) পরিহার করে None সেন্টিনেল প্যাটার্ন ব্যবহার করা হলো।
        """
        import os
        actual_deps = list(dependencies) if dependencies is not None else []

        if uss:
            from skills.schema import UniversalSkillSchema

            try:
                UniversalSkillSchema(**uss)
            except Exception as e:
                logger.error(
                    f"USS validation failed before installing skill '{name}': {e}"
                )
                return False

        try:
            safe_name = self._sanitize_skill_name(name)
        except Exception as e:
            logger.error(f"Skill name validation failed: {e}")
            return False

        try:
            self._pre_write_security_scan(code)
        except Exception as e:
            logger.error(f"Security scan failed before writing skill '{name}': {e}")
            return False

        try:
            success = self.install_dependencies(actual_deps)
        except SecurityError as deps_err:
            # P0 (Task 9-c2): allowlist/production-gate rejection — no pip run.
            logger.error(f"Dependency installation refused for skill '{name}': {deps_err}")
            return False
        if not success:
            return False

        skill_dir = os.path.join(self.skills_dir, safe_name)
        os.makedirs(skill_dir, exist_ok=True)

        entry_file = os.path.join(skill_dir, "main.py")
        try:
            with open(entry_file, "w", encoding="utf-8") as f:
                f.write(code)

            if uss:
                import json

                schema_file = os.path.join(skill_dir, "schema.json")
                with open(schema_file, "w", encoding="utf-8") as sf:
                    json.dump(uss, sf, indent=4)
        except Exception as e:
            logger.error(f"Error saving skill source code: {e}")
            return False

        try:
            registered = bool(
                self.registry.register_skill(
                    safe_name, version, description, entry_file, actual_deps, uss=uss
                )
            )
            if not registered:
                # P0 (Task 9-c2): registry persistence failed — surface it.
                logger.error(
                    f"Skill '{safe_name}' written to disk but registry persistence "
                    "FAILED (register_skill returned False)."
                )
            return registered
        except Exception as e:
            logger.error(f"Skill registration failed for '{safe_name}': {e}")
            return False
