"""Guard: mirrored satellite workflow trigger filters must be well-formed.

Root cause class this pins (P0 #3538, browser Run 41089438563): the #3467
tower read artifact nondeterministically strips `[m`-shaped spans from file
payloads, turning `branches: [main]` into `branches: ain]` on the READ
plane. A full_file bridge submission built from such a read lands the
corruption into the mirrored satellite workflows (browser/core/gateway/
studio/vscode `.github/workflows/`), where GitHub's trigger evaluation
fail-opens on the malformed filter — the workflow then fires on pushes to
ANY branch while the corruption stays invisible to every YAML-eye review
(the file still parses: a bare scalar is valid YAML). Landed triage #3561
itself reported the corruption as "mechanically verified" while the actual
blob (324471d6, byte-verified via `od` against the in-parity mirror on
2026-10-31) is intact — the artifact is that convincing.

This guard fail-closes the mirror plane on REAL bytes (pytest reads the
working tree directly — no tower, no display path):

1. every `on.push.branches` / `on.pull_request.branches` filter must be a
   YAML list (a bare scalar — the truncation shape — fails here);
2. every branch filter entry must be bracket-free and glob-safe;
3. the six satellite CI lanes whose 19-run history proves main-triggering
   must keep `main` among their push branches.

বাংলা: #3467 আর্টিফ্যাক্ট ক্লাস প্রমাণিতভাবেই এজেন্ট রিড-প্লেনে সক্রিয়
(landed #3561 নিজেই ভুক্তভোগী)। এই টেস্ট আসল বাইটে চলে — tower/ডিসপ্লে
পথ এভারেজ করে না — তাই দূষণ কখনো মিরর প্লেনে ল্যান্ড করতে পারলে এখানেই
ধরা পড়বে, sync স্যাটেলাইটে ছড়ানোর আগেই।
"""

from __future__ import annotations

import pathlib
import re

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# Satellite mirror domains that carry their own .github/workflows (the
# open->satellite sync plane, federation_satellite_sync.py sync_workflows).
MIRROR_DOMAINS = ("browser", "core", "gateway", "studio", "vscode")

# The six satellite CI lanes that demonstrably trigger on push-to-main
# (19-run browser history + sibling satellite run histories, #3538).
MAIN_TRIGGER_LANES = frozenset(
    {
        "browser/.github/workflows/ci.yml",
        "core/.github/workflows/ci.yml",
        "gateway/.github/workflows/ci.yml",
        "studio/.github/workflows/pipeline.yml",
        "studio/.github/workflows/upstream-sync.yml",
        "vscode/.github/workflows/release.yml",
    }
)

# Safe branch-name/glob characters. Anything else (notably `[`, `]`, `{`,
# `}`, whitespace fragments) is the truncation/corruption signature.
SAFE_BRANCH = re.compile(r"^[A-Za-z0-9._/\-]+$")


def _mirror_workflows() -> list[pathlib.Path]:
    paths: list[pathlib.Path] = []
    for domain in MIRROR_DOMAINS:
        wf_dir = REPO_ROOT / domain / ".github" / "workflows"
        if wf_dir.is_dir():
            paths.extend(sorted(wf_dir.glob("*.y*ml")))
    for lane in sorted(MAIN_TRIGGER_LANES):
        assert (REPO_ROOT / lane).is_file(), f"main-trigger lane missing: {lane}"
    return paths


def _trigger_block(doc: object, path: pathlib.Path) -> dict:
    assert isinstance(doc, dict), f"{path}: workflow is not a YAML mapping"
    # YAML 1.1 parses a bare `on:` key as boolean True; accept both shapes.
    trigger = doc.get(True, doc.get("on"))
    assert isinstance(trigger, dict), (
        f"{path}: 'on:' trigger block missing or not a mapping — "
        "a workflow whose trigger cannot be parsed is the corruption class (#3538)"
    )
    return trigger


def _validated_branches(
    doc: object, path: pathlib.Path, event: str
) -> list[str] | None:
    trigger = _trigger_block(doc, path)
    event_body = trigger.get(event)
    if event_body is None:
        return None
    if not isinstance(event_body, dict):
        # `pull_request:` with no body is a legitimate open filter.
        return None
    branches = event_body.get("branches")
    if branches is None:
        return None
    assert isinstance(branches, list), (
        f"{path}: {event}.branches must be a YAML flow sequence (list); "
        f"got bare scalar {branches!r} — the #3467 read-artifact truncation "
        "shape ([main] -> ain]) that GitHub trigger-evaluation fail-opens on (#3538)"
    )
    for entry in branches:
        assert isinstance(entry, str), f"{path}: {event}.branches entry not a string: {entry!r}"
        assert SAFE_BRANCH.match(entry), (
            f"{path}: {event}.branches entry {entry!r} carries characters outside "
            "the safe branch/glob set — bracket/brace fragments are the "
            "truncation-corruption signature (#3467/#3538)"
        )
    return branches


@pytest.mark.parametrize(
    "path", _mirror_workflows(), ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_workflow_trigger_filters_are_well_formed(path: pathlib.Path) -> None:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    rel = str(path.relative_to(REPO_ROOT))
    push_branches = _validated_branches(doc, path, "push")
    _validated_branches(doc, path, "pull_request")
    if rel in MAIN_TRIGGER_LANES:
        assert push_branches is not None, f"{rel}: push trigger lost its branch filter"
        assert "main" in push_branches, (
            f"{rel}: push branches {push_branches!r} no longer include 'main' — "
            "the lane's 19-run main-trigger history contradicts this (#3538)"
        )
