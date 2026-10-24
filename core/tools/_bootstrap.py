import sys
from pathlib import Path


def ensure_project_paths() -> None:
    _file_path = Path(__file__).resolve()
    _backend_dir = _file_path.parents[1]
    _project_root = _file_path.parents[2]
    for p in (_backend_dir, _project_root):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))


def bootstrap() -> None:
    """Ensure project paths are available for direct script execution."""
    ensure_project_paths()
