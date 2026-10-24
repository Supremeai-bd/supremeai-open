"""Lazy Loader Utility — Dynamically load heavy Python packages on-demand.

বাংলা: লেজি লোডার ইউটিলিটি — ভারী পাইথন প্যাকেজসমূহ (যেমন PyTorch, ChromaDB, Sentence-Transformers)
প্রারম্ভে লোড না করে অন-ডিমান্ড প্রয়োজনকালে লোড করে মেমরি ও স্টার্টআপ টাইম বাঁচায়।
"""

import importlib
from typing import Any

from core.logging_config import logger


def lazy_import(module_name: str, package_hint: str | None = None) -> Any:
    """Dynamically import a module when required.

    Args:
        module_name: The module dot-path to import (e.g. 'chromadb', 'sentence_transformers').
        package_hint: Optional poetry group hint if module is missing.

    Returns:
        The imported module object.

    Raises:
        RuntimeError: If the module cannot be imported.
    """
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        hint = (
            f" Please install it via 'poetry install --with {package_hint}'."
            if package_hint
            else ""
        )
        logger.warning(
            f"⚠️ [LazyLoader] Optional package '{module_name}' is not available in light mode.{hint}"
        )
        raise RuntimeError(
            f"Package '{module_name}' is required for this feature but not installed.{hint}"
        ) from exc
