"""Compatibility shim for the issue-#338 verification contract.

The issue's Verification Contract pins the boot-smoke path::

    python -m py_compile sdk/python/client.py

The publishable layout keeps the implementation at
``sdk/python/supremeai_sdk/client.py`` (proper ``supremeai_sdk`` package,
PEP 561 ``py.typed``). This shim satisfies the literal contract path without
shipping a second copy of the code: it is NOT packaged (``pyproject.toml``
discovers only the ``supremeai_sdk`` package) and exists solely inside this
repository so the contracted command and
``python sdk/python/client.py --self-test`` keep working verbatim.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent / "supremeai_sdk"
if str(_PACKAGE_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT.parent))

from supremeai_sdk.client import DEFAULT_BASE_URL, DEFAULT_CLIENT_NAME, main  # noqa: E402,F401

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
