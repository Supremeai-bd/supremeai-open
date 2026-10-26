#!/usr/bin/env python3
"""
SupremeAI Universal Gap Finder wrapper script.
Delegates to `core.tools.gap_finder.cli`.
"""

import os
import sys

# Ensure repository root is on sys.path
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

if __name__ == "__main__":
    from core.tools.gap_finder.cli import main
    main()


