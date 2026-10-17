"""Shared pytest bootstrap: put the repo root on sys.path.

Without this, suites importing the ``scripts.*`` namespace package (e.g.
``from scripts.ci.federation_ci_watchdog import ...``) fail on clean CI
harnesses that invoke pytest directly, because pytest prepends the test
directory — not the repo root — to sys.path.
"""

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
