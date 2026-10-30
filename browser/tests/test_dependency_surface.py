"""Dependency-surface guard for the browser satellite (Zero-Recurrence U6).

বাংলা: এই গার্ড ঠিক সেই শ্রেণির পুনরাবৃত্তি ঠেকায় যা #3538-এ প্রথম দেখা গিয়েছিল
(run 41089438563): tests/test_webbotauth_probe.py-র ফিক্সচার importlib দিয়ে
scripts/webbotauth/probe.py লোড করে, probe.py মডিউল-লেভেলে cryptography
ইমপোর্ট করে, অথচ স্যাটেলাইট CI-র ইনস্টল-সারফেস (ci.yml-এর pip লাইন +
requirements.txt) সেটি বহন করত না → ModuleNotFoundError → ৯টি টেস্ট ERROR →
main লাল। স্ট্যাটিকভাবে শুধু tests/ স্ক্যান করলে ধরা যেত না — cryptography
ইমপোর্টটি dynamically-লোডেড probe.py-র ভেতরে লুকানো ছিল। তাই স্ক্যান-সারফেস
হলো tests/*.py + scripts/**/*.py (টেস্ট-প্লেন যা যা import/load করে তার
কভারেজ), allowed সেট = CI ইনস্টল-সারফেস ∪ stdlib ∪ first-party মডিউল।

Boundary (ইচ্ছাকৃত): root-লেভেল রানটাইম মডিউল (browser_agent, web_scraper,
runtime/*, ghost_tower/* ...) স্ক্যান করা হয় না — ওগুলো playwright/lxml-জাতীয়
রানটাইম-অপশনাল ডিপ বহন করে যা CI ইনস্টল করে না, এবং সেগুলোর ইমপোর্ট-সাইট
try/except ImportError দিয়ে graceful-degrade করে (main.py প্যাটার্ন)। টেস্ট-
প্লেনে graceful-degrade নিষিদ্ধ — ওখানে মিসিং ডিপ মানে সাইলেন্ট স্কিপ-মাস্কিং।

Fail-open: ci.yml বা requirements.txt পড়া না গেলে গার্ড skip করে (infra
অনুপস্থিতি কখনো লাল করে না); শুধু প্রমাণিত মিসিং ডিপেন্ডেন্সিতেই fail করে।
"""
from __future__ import annotations

import ast
import pathlib
import re
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# dist-name -> import-name pairs the pins commonly use the other spelling of
# (kept tiny, evidence-driven; extend only with a live CI failure in hand).
_DIST_TO_IMPORT_EXTRA = {
    "beautifulsoup4": "bs4",
    "pyyaml": "yaml",
    "pillow": "PIL",
    "scikit-learn": "sklearn",
    "opencv-python": "cv2",
}

SCAN_ROOTS = ("tests", "scripts")


def _ci_install_surface() -> set[str]:
    """Third-party dist names CI installs: ci.yml pip lines + requirements.txt."""
    dists: set[str] = set()
    ci = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    if ci.is_file():
        for line in ci.read_text(encoding="utf-8").splitlines():
            m = re.match(r"(?:python -m )?pip install\s+(.*)$", line.strip())
            if not m:
                continue
            for tok in m.group(1).split():
                if tok.startswith("-") or "=" in tok or ">" in tok or "<" in tok or "[" in tok:
                    continue  # flags / inline-pinned / extras tokens
                if tok in ("pip", "setuptools", "wheel"):
                    continue
                dists.add(tok.strip("'\","))
    req = REPO_ROOT / "requirements.txt"
    if req.is_file():
        for line in req.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            name = re.split(r"[<>=!\[]", line, maxsplit=1)[0].strip()
            if name:
                dists.add(name)
    return dists


def _norm(name: str) -> str:
    return name.lower().replace("-", "_").replace(".", "_")


def _allowed_imports() -> set[str]:
    allowed = set(sys.stdlib_module_names)
    for dist in _ci_install_surface():
        allowed.add(_norm(dist))
        extra = _DIST_TO_IMPORT_EXTRA.get(_norm(dist))
        if extra:
            allowed.add(_norm(extra))
    # first-party: root .py stems + root packages + the scan roots themselves
    for p in REPO_ROOT.iterdir():
        if p.is_file() and p.suffix == ".py":
            allowed.add(_norm(p.stem))
        elif p.is_dir() and (p / "__init__.py").is_file():
            allowed.add(_norm(p.name))
    allowed.update({"scripts", "tests", "conftest"})
    return allowed


def _top_level_third_party_imports(path: pathlib.Path) -> list[str]:
    """Top-level (module-body) import roots of one file (relative imports skipped)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []  # syntax errors are test_all_python_files_compile's lane
    roots: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            roots.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.append(node.module.split(".")[0])
    return roots


def test_ci_surface_covers_test_plane_imports() -> None:
    """Every import the test plane makes must exist in CI's install surface.

    বাংলা: টেস্ট-প্লেন (tests/ + scripts/, dynamically-লোড হোক বা সরাসরি) যে
    থার্ড-পার্টি মডিউল টপ-লেভেলে ইমপোর্ট করে, সেটি যেন CI আসলেই ইনস্টল করে —
    নইলে pytest-এর ভেতরে সাইলেন্ট ModuleNotFoundError-র বদলে এই গার্ডই
    merge-এর আগে স্পষ্ট বার্তা দিয়ে থামাবে।
    """
    if not _ci_install_surface():
        pytest.skip("CI install surface unreadable (no ci.yml/requirements.txt) — fail-open")
    allowed = _allowed_imports()
    offenders: list[str] = []
    for root_name in SCAN_ROOTS:
        root = REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for py in sorted(root.rglob("*.py")):
            for imp in _top_level_third_party_imports(py):
                if _norm(imp) not in allowed:
                    entry = f"{py.relative_to(REPO_ROOT)}: import {imp}"
                    if entry not in offenders:
                        offenders.append(entry)
    assert not offenders, (
        "test-plane imports outside CI's install surface (ci.yml pip lines + "
        "requirements.txt). Root cause of the #3538 red (run 41089438563): a "
        "test-plane module imported a dependency CI never installs and 9 "
        "tests died on ModuleNotFoundError. Remedy: add the missing pin to "
        "requirements.txt (the agent-writable surface CI installs), or make "
        "the import lazy/optional inside a guarded helper — never skip the "
        "test to hide it. Offenders:\n  " + "\n  ".join(offenders)
    )


def test_guard_self_surface_is_dependency_free() -> None:
    """The guard itself must respect the smoke doctrine (stdlib + pytest only)."""
    me = pathlib.Path(__file__)
    for imp in _top_level_third_party_imports(me):
        assert imp in sys.stdlib_module_names or imp == "pytest", (
            f"guard must stay dependency-free, found: {imp}"
        )
