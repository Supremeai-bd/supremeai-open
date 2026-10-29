"""R47 FROM-pin ratchet tests for check_dockerfile_security.py (#2084).

Covers: image classification (digest / full-version / float), FROM parsing
(comments, build flags, stage aliases), the non-prod allowlist, legacy USER
audit regression, the live FROM surface collector, and the shrink-only
baseline ratchet polarity — plus hermetic subprocess proofs against the real
repository state.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "ci" / "check_dockerfile_security.py"
BASELINE = REPO_ROOT / "scripts" / "ci" / "dockerfile_from_baseline.json"

_spec = importlib.util.spec_from_file_location("cds", GUARD)
cds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cds)


# --------------------------------------------------------------------------- #
# classification
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("python:3.11-slim@sha256:" + "a" * 64, "digest"),
        ("nginx:1.27.4-alpine@sha256:" + "B" * 64, "digest"),
        ("python:3.11.14-slim", "version"),
        ("node:24.22.1-alpine3.22", "version"),
        ("python:3.11-slim", "float"),
        ("node:24-alpine", "float"),
        ("nginx:1.27-alpine", "float"),
        ("node:latest", "float"),
        ("alpine", "float"),
        ("mcr.microsoft.com/devcontainers/python:3.11", "float"),
    ],
)
def test_classify_image(ref, expected):
    assert cds.classify_image(ref) == expected


# --------------------------------------------------------------------------- #
# FROM parsing
# --------------------------------------------------------------------------- #

def test_parse_froms_flags_aliases_comments():
    content = "\n".join([
        "# FROM python:3.9 (comment must be ignored)",
        "FROM --platform=linux/amd64 python:3.11-slim AS builder",
        "",
        "FROM python:3.11.14-slim",
        "from node:24-alpine as runtime",  # case-insensitive instruction
    ])
    froms = cds.parse_froms(content)
    assert [(ln, ref) for ln, ref in froms] == [
        (2, "python:3.11-slim"),
        (4, "python:3.11.14-slim"),
        (5, "node:24-alpine"),
    ]


def test_parse_froms_multi_stage_names_not_confused_with_image():
    content = "FROM golang:1.22 AS build\nFROM scratch\n"
    froms = cds.parse_froms(content)
    # 'AS' alias tokens are dropped; the image is always the first non-flag token
    assert [ref for _, ref in froms] == ["golang:1.22", "scratch"]


# --------------------------------------------------------------------------- #
# non-prod allowlist (#2084 never-do note)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("docs/devcontainer/Dockerfile", True),
        ("core/ecosystem/Dockerfile.test", True),
        ("gateway/Dockerfile", False),
        ("studio/Dockerfile", False),
        ("infrastructure/mcp-control-plane/Dockerfile", False),
    ],
)
def test_allowlist_routing(rel, expected):
    assert cds.is_allowlisted(rel) is expected


# --------------------------------------------------------------------------- #
# legacy USER audit regression (Trap #97 semantics unchanged)
# --------------------------------------------------------------------------- #

def _write(tmp_path: Path, rel: str, text: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture()
def _repoint_repo_root(tmp_path, monkeypatch):
    monkeypatch.setattr(cds, "REPO_ROOT", tmp_path)
    return tmp_path


def test_user_audit_non_root_passes(_repoint_repo_root):
    df = _write(_repoint_repo_root, "svc/Dockerfile", "FROM python:3.11.14-slim\nUSER app\n")
    assert cds.check_dockerfile(df) == []


def test_user_audit_root_fails(_repoint_repo_root):
    df = _write(_repoint_repo_root, "svc/Dockerfile", "FROM python:3.11.14-slim\nUSER root\n")
    issues = cds.check_dockerfile(df)
    assert len(issues) == 1 and "must run as non-root" in issues[0]


def test_user_audit_missing_fails(_repoint_repo_root):
    df = _write(_repoint_repo_root, "svc/Dockerfile", "FROM python:3.11.14-slim\n")
    issues = cds.check_dockerfile(df)
    assert len(issues) == 1 and "Missing USER directive" in issues[0]


# --------------------------------------------------------------------------- #
# live FROM surface collector
# --------------------------------------------------------------------------- #

def test_collect_from_surface_skips_allowlist_and_classifies(_repoint_repo_root):
    _write(_repoint_repo_root, "svc/Dockerfile", "FROM python:3.11-slim AS b\nFROM python:3.11.14-slim\n")
    _write(_repoint_repo_root, "docs/devcontainer/Dockerfile", "FROM python:3.11-slim\n")
    surface = cds.collect_from_surface(cds.find_dockerfiles(_repoint_repo_root))
    assert set(surface) == {"svc/Dockerfile"}
    info = surface["svc/Dockerfile"]
    assert info["unpinned"] == ["python:3.11-slim"]
    assert [(ref, cls) for _, ref, cls in info["froms"]] == [
        ("python:3.11-slim", "float"),
        ("python:3.11.14-slim", "version"),
    ]


# --------------------------------------------------------------------------- #
# shrink-only ratchet polarity
# --------------------------------------------------------------------------- #

def _ratchet(tmp_path: Path, dockerfiles_text: dict[str, str], baseline_doc: dict) -> tuple[int, str]:
    for rel, text in dockerfiles_text.items():
        _write(tmp_path, rel, text)
    bl = tmp_path / "baseline.json"
    bl.write_text(json.dumps(baseline_doc), encoding="utf-8")
    monkey_bl = str(bl)
    old = cds.BASELINE_PATH
    cds.BASELINE_PATH = Path(monkey_bl)
    try:
        code = cds.run_from_ratchet(cds.find_dockerfiles(tmp_path), json_out=False)
        return code, monkey_bl
    finally:
        cds.BASELINE_PATH = old


def test_ratchet_baselined_refs_compliant(_repoint_repo_root, capsys):
    code, _ = _ratchet(
        _repoint_repo_root,
        {"svc/Dockerfile": "FROM python:3.11-slim\nUSER app\n"},
        {"unpinned_froms": {"svc/Dockerfile": ["python:3.11-slim"]}},
    )
    assert code == 0
    assert "COMPLIANT" in capsys.readouterr().out


def test_ratchet_new_ref_is_drift_exit1(_repoint_repo_root, capsys):
    code, _ = _ratchet(
        _repoint_repo_root,
        {"svc/Dockerfile": "FROM python:3.12-slim\nUSER app\n"},
        {"unpinned_froms": {"svc/Dockerfile": ["python:3.11-slim"]}},
    )
    assert code == 1
    assert "DRIFT" in capsys.readouterr().out


def test_ratchet_new_file_is_drift_exit1(_repoint_repo_root):
    code, _ = _ratchet(
        _repoint_repo_root,
        {
            "svc/Dockerfile": "FROM python:3.11-slim\nUSER app\n",
            "svc2/Dockerfile": "FROM alpine\nUSER app\n",
        },
        {"unpinned_froms": {"svc/Dockerfile": ["python:3.11-slim"]}},
    )
    assert code == 1


def test_ratchet_pinned_from_never_drifts(_repoint_repo_root):
    code, _ = _ratchet(
        _repoint_repo_root,
        {
            "svc/Dockerfile": (
                "FROM python:3.11-slim@sha256:" + "a" * 64 + "\nUSER app\n"
            ),
        },
        {"unpinned_froms": {}},
    )
    assert code == 0


# --------------------------------------------------------------------------- #
# real-repo subprocess proofs (the landed floor is compliant; self-test green)
# --------------------------------------------------------------------------- #

def test_repo_strict_ratchet_compliant():
    """The landed baseline must cover the live production surface (shrink-only floor)."""
    r = subprocess.run(
        [sys.executable, str(GUARD), "--from-strict"],
        capture_output=True, text=True, timeout=120, cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "COMPLIANT" in r.stdout


def test_repo_baseline_matches_live_surface():
    """Regenerating the baseline in a scratch copy must produce the same refs
    (baseline == live floor at landing time; only real fixes shrink it)."""
    doc = json.loads(BASELINE.read_text(encoding="utf-8"))
    r = subprocess.run(
        [sys.executable, str(GUARD), "--json", "--from-strict"],
        capture_output=True, text=True, timeout=120, cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    report = json.loads(r.stdout)
    # The JSON report carries drift/shrinkable; at landing both must be empty.
    assert report["drift"] == {}, report["drift"]
    assert report["shrinkable"] == [], report["shrinkable"]
    # Baseline content sanity: 13 prod files, 14 refs, scout numbers (#2084).
    assert len(doc["unpinned_froms"]) == 13
    assert sum(len(v) for v in doc["unpinned_froms"].values()) == 14
    assert "docs/devcontainer" not in json.dumps(doc["unpinned_froms"])
    assert "core/ecosystem" not in json.dumps(doc["unpinned_froms"])


def test_self_test_hermetic_green():
    r = subprocess.run(
        [sys.executable, str(GUARD), "--self-test"],
        capture_output=True, text=True, timeout=120, cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "self-test: 14/14" in r.stdout
