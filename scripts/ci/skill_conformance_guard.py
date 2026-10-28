#!/usr/bin/env python3
"""skill_conformance_guard.py — Agent Skills (SKILL.md) structural conformance gate (#1672).

Mission (issue #1672, scout radar R17 / SCOUT_RADAR_2026-10-28-III, verdict ADOPT_IMMEDIATELY):
    The federation carried three coexisting skill-metadata conventions with zero
    cross-validation: (1) `.agents/skills/*/SKILL.md` YAML frontmatter per the
    Agent Skills open standard (https://agentskills.io/specification — originally
    developed by Anthropic, released as an open standard, Apache-2.0 code +
    CC-BY-4.0 docs), (2) the pydantic `SkillMetadata` model powering the dynamic
    registry (`skills/schema.py`), and (3) the standard itself, unused. This
    guard closes the structural-drift half of that gap for convention 1 with a
    stdlib-only, zero-dependency, fully offline validator. It does NOT touch
    runtime behavior: skills load exactly as before; the guard only makes
    discovery-breaking structure loud at push/CI time.

What it checks (per skill folder under `.agents/skills/`):
    E1  SKILL.md missing            — the folder advertises a skill the standard
                                      cannot discover (seed instance:
                                      developing-genkit-python ships references/
                                      only; its entry file is absent, so the
                                      skill is invisible to any client).
    E2  frontmatter delimiters      — file must open with `---` on line 1 and
                                      close with a second `---` before body text.
    E3  `name` missing              — minimum frontmatter per the standard.
    E4  name != directory           — the field-report pattern: name/directory
                                      drift is the most common silent failure
                                      because it breaks discovery without
                                      breaking load.
    E5  `description` missing/empty — minimum frontmatter per the standard.
    E6  description length > 1024   — the standard's cap; unbounded
                                      descriptions were unchecked before.
Warnings (informational, report-only, never fail the run):
    W1  extra top-level fields      — inventory of extension fields beyond
                                      {name, description, license} (risk,
                                      source, date_added, category, metadata,
                                      author, source_repo, source_type ...).
    W2  no `license` field          — no in-repo skill carries one (the R17
                                      field report's observation).
    W3  nested `metadata:` map      — convention-2 (registry) leakage into the
                                      file plane (e.g. developing-genkit-js).

Ratchet (house style: #1809 bandit, #1969/#1975/#2059 dep-CVE siblings):
    Errors are pinned shrink-only via scripts/ci/skill_conformance_baseline.json.
    A dated seed records the floors that are real at seed time (never assumed
    empty — the #2081 lesson). NEW folders with errors, or GROWN error codes on
    a pinned folder, fail closed. Resolved pins print a shrink note and stay
    green (shrinking the floor is an owner decision via `--baseline`; the
    baseline may never grow except through that explicit regeneration).
    Warnings are never floorable — they are inventory, not debt.

The other half of the ticket — the `SkillMetadata` <-> SKILL.md mapping that
stops the two planes drifting — lives in docs/AGENT_SKILLS_CONFORMANCE.md,
next to the validator usage contract.

Usage:
    python scripts/ci/skill_conformance_guard.py            # scan + ratchet
    python scripts/ci/skill_conformance_guard.py --check    # alias, explicit
    python scripts/ci/skill_conformance_guard.py --root DIR # scan a custom root
    python scripts/ci/skill_conformance_guard.py --baseline # regenerate the seed
    python scripts/ci/skill_conformance_guard.py --self-test

Exit codes: 0 = clean or fully covered by the shrink-only baseline;
            1 = new/grown structural violations (or self-test failure).
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = REPO_ROOT / ".agents" / "skills"
DEFAULT_BASELINE = Path(__file__).resolve().parent / "skill_conformance_baseline.json"

DESC_MAX = 1024  # standard cap (issue #1672 adoption path: description 1-1024 chars)
KNOWN_FIELDS = {"name", "description", "license"}
ERROR_CODES = ("E1", "E2", "E3", "E4", "E5", "E6")

_TAGGED_SCALAR = re.compile(r"^(?:[|>][+-]?\d*\s*(?:#.*)?)$")


def parse_frontmatter(lines: list[str]) -> tuple[dict[str, str], list[str], str | None]:
    """Minimal stdlib frontmatter parser for the shapes this repo actually ships.

    Returns (top_level_scalars, extra_inventory_notes, error) where error is a
    short E2-class message or None. Handles: `---` delimiters, top-level
    `key: value` plain scalars, single/double-quoted scalars, plain-scalar
    continuation lines (folded with single spaces), nested maps (children
    skipped, presence reported), block scalars (| and >), and full-line
    comments. It deliberately does NOT implement full YAML — the guard only
    needs the two required scalars plus an honest inventory of everything else,
    and a parser that silently guessed would violate the repo's evidence rules.
    """
    scalars: dict[str, str] = {}
    notes: list[str] = []
    if not lines or lines[0].strip() != "---":
        return scalars, notes, "E2: missing opening '---' delimiter on line 1"
    close = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close = i
            break
    if close is None:
        return scalars, notes, "E2: missing closing '---' delimiter"
    block_tag: str | None = None
    block_indent: int | None = None
    last_key: str | None = None
    for raw in lines[1:close]:
        stripped = raw.strip()
        if not stripped:
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if stripped.startswith("#"):
            continue  # full-line comment
        if block_tag is not None:
            if indent > (block_indent or 0):
                continue  # block-scalar body line: folded below
            block_tag = None
            block_indent = None
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s(.*))?$", stripped)
        if m and indent == 0:
            key, val = m.group(1), (m.group(2) or "").strip()
            if val == "":
                # either a nested map follows or a block scalar; both recorded
                last_key = key
                scalars.setdefault(key, "")
                continue
            if _TAGGED_SCALAR.match(val):
                block_tag = key
                block_indent = indent
                scalars.setdefault(key, "")
                last_key = key
                continue
            scalars[key] = _unquote(val)
            last_key = key
            continue
        if indent > 0:
            if last_key is not None and scalars.get(last_key) == "":
                if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*:", stripped):
                    note = f"nested map under '{last_key}'"
                    if note not in notes:
                        notes.append(note)
                    continue
            if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*:", stripped):
                continue  # nested child key: out of scope for top-level checks
            if last_key is not None:
                # plain-scalar continuation of the previous top-level value
                scalars[last_key] = (scalars[last_key] + " " + _unquote(stripped)).strip()
    return scalars, notes, None


def _unquote(val: str) -> str:
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
        return val[1:-1]
    # strip trailing comment on unquoted plain scalars (space before #)
    m = re.match(r"^(.*?)\s+#.*$", val)
    return m.group(1).strip() if m and re.match(r"^[^'\"[]", val) else val


def check_skill_file(folder: Path) -> tuple[list[str], list[str]]:
    """Structurally validate one SKILL.md. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []
    f = folder / "SKILL.md"
    try:
        text = f.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"E2: SKILL.md unreadable ({exc.__class__.__name__})"], warnings
    lines = text.splitlines()
    scalars, notes, parse_err = parse_frontmatter(lines)
    if parse_err:
        return [parse_err], warnings
    name = scalars.get("name")
    desc = scalars.get("description")
    if not name:
        errors.append("E3: required frontmatter field 'name' missing or empty")
    elif name != folder.name:
        errors.append(f"E4: frontmatter name {name!r} != directory name {folder.name!r} "
                      f"(breaks discovery without breaking load)")
    if not desc or not desc.strip():
        errors.append("E5: required frontmatter field 'description' missing or empty")
    elif len(desc) > DESC_MAX:
        errors.append(f"E6: description length {len(desc)} > standard cap {DESC_MAX}")
    extra = sorted(k for k in scalars if k not in KNOWN_FIELDS and scalars.get(k) != "")
    if extra:
        warnings.append(f"W1: extra top-level fields (informational): {', '.join(extra)}")
    if "license" not in scalars:
        warnings.append("W2: no 'license' field (recommended attribution metadata)")
    if any(n.startswith("nested map") for n in notes):
        warnings.append("W3: nested 'metadata:' map present (registry-plane leakage)")
    return errors, warnings


def scan(root: Path) -> tuple[list[tuple[str, list[str]]], list[tuple[str, list[str]]], list[str]]:
    """Scan every subdirectory of root. Returns (per-folder errors, warnings, skips)."""
    err_rows: list[tuple[str, list[str]]] = []
    warn_rows: list[tuple[str, list[str]]] = []
    skips: list[str] = []
    if not root.is_dir():
        return err_rows, warn_rows, [f"surface absent: {root} (nothing to guard — honest skip)"]
    folders = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
    if not folders:
        skips.append(f"no skill folders under {root} (honest zero)")
    for folder in folders:
        if not (folder / "SKILL.md").exists():
            err_rows.append((folder.name, ["E1: SKILL.md missing — skill is undiscoverable"]))
            continue
        errs, warns = check_skill_file(folder)
        if errs:
            err_rows.append((folder.name, errs))
        if warns:
            warn_rows.append((folder.name, warns))
    return err_rows, warn_rows, skips


def load_baseline(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"[skill-conformance-guard] baseline unreadable ({exc.__class__.__name__}) — "
              "failing closed; fix or regenerate with --baseline", file=sys.stderr)
        raise SystemExit(1)
    return data.get("errors", {}) if isinstance(data, dict) else {}


def ratchet(err_rows: list[tuple[str, list[str]]], baseline: dict) -> tuple[list[str], list[str]]:
    """Compare live errors against the shrink-only floor. Returns (violations, shrink_notes)."""
    violations: list[str] = []
    shrink_notes: list[str] = []
    live = {name: [e.split(":")[0] for e in errs] for name, errs in err_rows}
    for name, codes in live.items():
        pinned = baseline.get(name)
        if pinned is None:
            violations.append(f"{name}: NEW error class not in baseline -> "
                              + "; ".join(live_err_text(err_rows, name)))
            continue
        grown = [c for c in codes if c not in pinned]
        if grown:
            violations.append(f"{name}: GROWN error codes {grown} beyond pinned {pinned}")
    for name, pinned in baseline.items():
        live_codes = live.get(name, [])
        resolved = [c for c in pinned if c not in live_codes]
        if resolved and not live_codes:
            shrink_notes.append(f"{name}: pinned {pinned} fully resolved — shrink the floor via --baseline")
        elif resolved:
            shrink_notes.append(f"{name}: codes {resolved} resolved (pin {pinned} -> {live_codes})")
    return violations, shrink_notes


def live_err_text(err_rows: list[tuple[str, list[str]]], name: str) -> list[str]:
    for n, errs in err_rows:
        if n == name:
            return errs
    return []


def write_baseline(root: Path, path: Path) -> None:
    err_rows, _, _ = scan(root)
    seed = {
        "schema_version": 1,
        "seeded_at": "2026-10-29",
        "seed_commit": "961e2be (issue #1672 adoption landing)",
        "note": "Shrink-only floor: entries may be removed when fixed, never added by hand. "
                "Regenerate only via `--baseline` at a state you are willing to pin.",
        "errors": {name: sorted({e.split(":")[0] for e in errs}) for name, errs in err_rows},
    }
    path.write_text(json.dumps(seed, indent=2) + "\n", encoding="utf-8")
    print(f"[skill-conformance-guard] baseline written: {path} "
          f"({len(seed['errors'])} pinned folder(s))")


def self_test() -> int:
    """Hermetic battery — every check class exercised on tempdirs."""
    failures = 0

    def expect(cond: bool, label: str) -> None:
        nonlocal failures
        print(f"{'PASS' if cond else 'FAIL'} {label}")
        if not cond:
            failures += 1

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        def mk(name: str, frontmatter: str) -> Path:
            d = root / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(frontmatter, encoding="utf-8")
            return d

        clean = mk("clean-skill", "---\nname: clean-skill\ndescription: ok\n---\nbody\n")
        errs, _ = check_skill_file(clean)
        expect(errs == [], "clean skill passes with zero errors")

        errs, _ = check_skill_file(mk("other-name", "---\nname: clean-skill\ndescription: x\n---\n"))
        expect(errs and errs[0].startswith("E4"), "E4 name-directory drift fires")

        errs, _ = check_skill_file(mk("no-name", "---\ndescription: x\n---\n"))
        expect(errs and errs[0].startswith("E3"), "E3 missing name fires")

        errs, _ = check_skill_file(mk("no-desc", "---\nname: no-desc\n---\n"))
        expect(errs and errs[0].startswith("E5"), "E5 missing description fires")

        errs, _ = check_skill_file(mk("long-desc", "---\nname: long-desc\n"
                                      "description: " + "x" * (DESC_MAX + 1) + "\n---\n"))
        expect(errs and errs[0].startswith("E6"), "E6 over-cap description fires")

        errs, _ = check_skill_file(mk("no-delims", "name: no-delims\ndescription: x\n"))
        expect(errs and errs[0].startswith("E2"), "E2 missing delimiters fires")

        folded = ("---\nname: folded\ndescription: first line\n"
                  "  continued here\n  and here\n---\n")
        errs, _ = check_skill_file(mk("folded", folded))
        expect(errs == [], "plain-scalar continuation folds parse clean")

        quoted = "---\nname: quoted\ndescription: \"double quoted\"\n---\n"
        errs, _ = check_skill_file(mk("quoted", quoted))
        expect(errs == [], "double-quoted scalar parses clean")

        nested = ("---\nname: nested\ndescription: d\nmetadata:\n  version: \"1.0.0\"\n"
                  "  category: AiAndMachineLearning\n---\n")
        errs, warns = check_skill_file(mk("nested", nested))
        expect(errs == [] and any(w.startswith("W3") for w in warns),
               "nested metadata warns W3 without erroring")

        (root / "empty-folder").mkdir()
        err_rows, warn_rows, _ = scan(root)
        names = {n for n, _ in err_rows}
        expect("empty-folder" in names, "E1 missing SKILL.md fires at scan level")

        baseline = {"empty-folder": ["E1"], "other-name": ["E4"]}
        # isolated scenario: empty-folder still fires E1; other-name was fixed
        scenario = [("empty-folder", ["E1: SKILL.md missing — skill is undiscoverable"]),
                    ("other-name", ["E4: frontmatter name 'clean-skill' != directory name 'other-name'"])]
        fixed = [r for r in scenario if r[0] != "other-name"]
        violations, shrinks = ratchet(fixed, baseline)
        expect(not violations and any("other-name" in s for s in shrinks),
               "ratchet: resolved pin shrinks with note, never violates")

        grown_errs = err_rows + [("empty-folder", [])]
        violations, _ = ratchet(err_rows, {"clean-skill": ["E1"]})
        expect(any("NEW error" in v for v in violations),
               "ratchet: new unpinned folder fails closed")

    print(f"self-test: {'OK' if failures == 0 else f'{failures} FAILURE(S)'}")
    return 0 if failures == 0 else 1


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    root = Path(argv[argv.index("--root") + 1]) if "--root" in argv else DEFAULT_ROOT
    baseline_path = DEFAULT_BASELINE
    if "--baseline" in argv:
        write_baseline(root if "--root" in argv else DEFAULT_ROOT, baseline_path)
        return 0
    err_rows, warn_rows, skips = scan(root)
    for s in skips:
        print(f"[skill-conformance-guard] {s}")
    if not skips or not all("surface absent" in s or "honest zero" in s for s in skips):
        baseline = load_baseline(baseline_path)
        violations, shrink_notes = ratchet(err_rows, baseline)
        for name, errs in err_rows:
            for e in errs:
                code = e.split(":")[0]
                state = "PINNED (baseline)" if code in baseline.get(name, []) else "LIVE"
                print(f"[skill-conformance-guard] ERROR {state} {name}: {e}")
        for name, warns in warn_rows:
            for w in warns:
                print(f"[skill-conformance-guard] warn {name}: {w}")
        for n in shrink_notes:
            print(f"[skill-conformance-guard] shrink note: {n}")
        if violations:
            for v in violations:
                print(f"[skill-conformance-guard] RATCHET VIOLATION: {v}")
            print("skill-conformance-guard: FAIL — new/grown structural violations; "
                  "fix the skill files (or, only for genuinely pre-existing floors, "
                  "regenerate the dated baseline via --baseline at a state you pin).")
            return 1
    scanned = len([p for p in (root.iterdir() if root.is_dir() else []) if p.is_dir()])
    print(f"skill-conformance-guard: OK — {scanned} skill folder(s) checked, "
          f"{sum(len(w) for _, w in warn_rows)} warning(s) (report-only), "
          f"errors within shrink-only floor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
