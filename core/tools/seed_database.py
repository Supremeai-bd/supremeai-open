"""
Backward compatibility bridge: re-export all from scripts.db.seed_knowledge_fts.
Preserves legacy imports for 'tools.seed_database' and 'backend.tools.seed_database'.
"""

import sys
from pathlib import Path

# Add project root to sys.path so scripts can be imported cleanly
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scripts.db.seed_knowledge_fts import (  # noqa: F401
    DB_PATH,
    _init_fts_db,
    _upsert_fts,
    seed_all,
)

__all__ = [
    "DB_PATH",
    "_init_fts_db",
    "_upsert_fts",
    "seed_all",
]

if __name__ == "__main__":
    seed_all()
