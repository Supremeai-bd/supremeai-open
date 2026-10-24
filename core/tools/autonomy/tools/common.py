from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

IGNORE_DIRS = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', '.next', 'dist', 'build', '.turbo', 'coverage'}
TEXT_EXTS = {'.py','.ts','.tsx','.js','.jsx','.json','.yaml','.yml','.toml','.ini','.md','.txt','.sh','.ps1','.sql','.html','.css','.env'}
SECRET_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*["\']?[A-Za-z0-9_\-]{12,}'),
    re.compile(r'(?i)bearer\s+[A-Za-z0-9_\-\.]{20,}'),
    re.compile(r'AKIA[0-9A-Z]{16}'),
]

def walk_files(root: Path) -> Iterable[Path]:
    for p in root.rglob('*'):
        if p.is_file() and not any(part in IGNORE_DIRS for part in p.parts):
            yield p

def read_text(path: Path, limit: int = 300_000) -> str:
    try:
        return path.read_text(encoding='utf-8', errors='replace')[:limit]
    except OSError:
        return ''

def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()

def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8', errors='replace')).hexdigest()

def json_dump(data: Any, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')

def find_secret_hits(root: Path) -> list[dict[str, Any]]:
    hits = []
    for p in walk_files(root):
        if p.suffix.lower() not in TEXT_EXTS and p.name not in {'.env', '.env.example'}:
            continue
        text = read_text(p)
        for n, line in enumerate(text.splitlines(), 1):
            if any(rx.search(line) for rx in SECRET_PATTERNS):
                hits.append({'file': rel(root,p), 'line': n, 'kind': 'possible_secret'})
    return hits

def count_tokens_rough(text: str) -> int:
    return max(1, len(re.findall(r'\S+', text)))
