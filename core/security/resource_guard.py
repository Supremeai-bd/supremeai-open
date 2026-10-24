import os
from pathlib import Path

from core.logging_config import logger


class ResourceGuard:
    """
    Rox-Style ResourceGuard to protect against path traversal and restrict file access
    to whitelisted base directories (PROJECT_ROOT and PERSISTENT_DATA_DIR).
    """

    # In a real production setup, these would come from settings or env.
    PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", "/app/supremeai_2.0")).resolve()
    PERSISTENT_DATA_DIR = Path(os.getenv("PERSISTENT_DATA_DIR", "/mnt/data")).resolve()

    # Dynamically determine sandbox root similar to microvm_sandbox
    import platform

    _default_sandbox = "C:\\tmp\\sandboxes" if platform.system() == "Windows" else "/tmp/sandboxes"
    from core.config import settings

    SANDBOX_ROOT = Path(settings.sandbox_root or _default_sandbox).resolve()

    @classmethod
    def verify_path(cls, requested_path: str | Path) -> Path:
        """
        Normalizes the path, resolves symlinks, and enforces that the target
        is strictly within the whitelisted root directories.
        """
        path = Path(requested_path)

        # 1. Reject paths that explicitly try to use '..'
        # Even though resolve() cleans it, we proactively reject malicious intent.
        if ".." in str(path):
            logger.critical(f"[ResourceGuard] Path traversal attempt detected: {requested_path}")
            raise PermissionError("Path traversal ('..') is strictly prohibited.")

        # 2. Resolve the path to its absolute, canonical form (resolves symlinks)
        try:
            resolved_path = path.resolve(strict=False)
        except OSError as e:
            # বাংলা: Path resolve করতে OS-লেভেল error হলে (symlink loop ইত্যাদি) ValueError রেইজ করা হয়
            logger.error(f"[ResourceGuard] Error resolving path {requested_path}: {e}")
            raise ValueError(f"Invalid path: {requested_path}") from e

        # 3. Check if the resolved path starts with any of the allowed roots
        allowed = False
        github_workspace = Path(os.getenv("GITHUB_WORKSPACE", "/__w/supremeai/supremeai")).resolve()
        allowed_roots = [
            cls.PROJECT_ROOT,
            cls.PERSISTENT_DATA_DIR,
            cls.SANDBOX_ROOT,
            github_workspace,
        ]

        for root in allowed_roots:
            try:
                # relative_to will raise ValueError if resolved_path is not under root
                resolved_path.relative_to(root)
                allowed = True
                break
            except ValueError:
                continue

        if not allowed:
            logger.critical(
                f"[ResourceGuard] Unauthorized access attempt to external path: {resolved_path}"
            )
            raise PermissionError(
                f"Access to path '{resolved_path}' is denied. Outside of allowed scopes."
            )

        return resolved_path

    @classmethod
    def read_text(cls, requested_path: str | Path, encoding: str = "utf-8") -> str:
        """Securely read a text file."""
        safe_path = cls.verify_path(requested_path)
        return safe_path.read_text(encoding=encoding)

    @classmethod
    def write_text(cls, requested_path: str | Path, content: str, encoding: str = "utf-8") -> None:
        """Securely write a text file."""
        safe_path = cls.verify_path(requested_path)
        safe_path.write_text(content, encoding=encoding)
