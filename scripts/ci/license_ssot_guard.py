#!/usr/bin/env python3
"""license_ssot_guard.py — machine declared-vs-actual license gate for ECOSYSTEM_MAP §2.3 (#1773).

Mission (issue #1773, scout radar lane R34):
    `ECOSYSTEM_MAP.md` §2.3 "Licensing & Intellectual Property Policy (SSOT)" is the
    legal boundary of the open-core Embassy Model. Until this guard it was enforced
    by prose and memory only: six open license work orders in one week (#1640,
    #1621<->#1678, #1690, #1691, #1725) plus one landed hand-fix (#1731, SPDX
    Apache-2.0 -> MIT) prove the drift class recurs, and zero mechanical enforcer
    ever went red. Mirror sync is automated, so a license mistake propagates
    mechanically while compliance stayed manual — this guard closes that asymmetry.

Behavior contract (report-only ratchet first, fail-closed on NEW drift):
    1. Parses the two §2.3 bullets into (repo -> declared model) pairs. An
       unparseable SSOT is fail-closed — the legal boundary must never silently
       pass unverified.
    2. Verifies declared-MIT surfaces: LICENSE file present, and every tracked
       package.json carries a `license` field whose value is a valid SPDX
       expression from the pinned in-file allowlist (no network at guard time).
    3. Verifies declared-Proprietary mirror surfaces: LICENSE or NOTICE file
       present — compared against the mirror-surface table below (§2.2 + the
       #1720 sentinel mapping), never guessing private repo state.
    4. Flags model contradictions in BOTH directions: an open-source SPDX token
       on a Proprietary-declared surface (the filed #1690 class), or a
       LicenseRef-Proprietary token on an MIT-declared surface.
    5. Ratchet (the dead-import #1598 pattern): findings in the dated KNOWN_DRIFTS
       baseline are reported (exit 0, report-only first cycle — the 9 missing
       package.json fields + 3 LICENSE-absent mirrors + 2 model contradictions
       stay visible without reddening CI). Any finding OUTSIDE the baseline is
       new drift -> exit 1. The baseline can only shrink; the test suite pins
       its exact contents.
    6. `--strict` flips to fail-closed-on-any-finding for the admin to enable
       once the known drifts are fixed. `--json` emits a machine report for the
       auditor lane. Surfaces with no manifest are skipped with evidence.

Never-do (issue #1773): stdlib-only, zero new dependencies, no network at guard
time, never rewrites ECOSYSTEM_MAP.md, never guesses private repo state, and
this guard never edits a license itself — it only measures and reports.

Usage:
    python scripts/ci/license_ssot_guard.py --check        # roster mode (ratchet)
    python scripts/ci/license_ssot_guard.py --strict       # fail-closed on any finding
    python scripts/ci/license_ssot_guard.py --json         # machine-readable report
    python scripts/ci/license_ssot_guard.py --self-test    # hermetic (offline)

Exit codes: 0 = pass / known-drift report-only · 1 = new (or strict) drift · 2 = usage error.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]
ECOSYSTEM_MAP = "ECOSYSTEM_MAP.md"
GUARD_TAG = "[license-ssot-guard]"

EXIT_PASS = 0
EXIT_DRIFT = 1
EXIT_USAGE = 2

# SPDX allowlist — pinned, dated copy of common SPDX license-list identifiers
# (SPDX is ISO/IEC 5962:2021). Compound expressions split on AND/OR. The
# LicenseRef- prefix is the SPDX-vocabulary way to declare a non-OSS license.
SPDX_ALLOWLIST = frozenset(
    {
        "MIT",
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "ISC",
        "0BSD",
        "Unlicense",
        "LicenseRef-Proprietary",
    }
)
OSS_TOKENS = frozenset(SPX for SPX in SPDX_ALLOWLIST if SPX != "LicenseRef-Proprietary")

# Mirror-surface table (dated 2026-10-28, main 203a562): open-repo surface path
# -> declared §2.3 repo -> declared model. Sources: ECOSYSTEM_MAP §2.2 mirror
# columns (command/skills/agents/sdk/infrastructure consolidations) and the
# #1720 satellite-sentinel manifest (gateway/ maps to the supremeai-api root).
# "" = the open repo root itself. The most specific surface prefix wins when
# assigning a package.json to a surface.
MIRROR_SURFACE_TABLE: list[tuple[str, str, str]] = [
    ("", "supremeai-open", "MIT"),
    ("studio", "supremeai-studio", "MIT"),
    ("vscode", "supremeai-vscode", "MIT"),
    ("core", "supremeai-core", "PROPRIETARY"),
    ("browser", "supremeai-browser", "PROPRIETARY"),
    ("gateway", "supremeai-api", "PROPRIETARY"),
    ("infrastructure", "supremeai-infrastructure", "PROPRIETARY"),
    ("infrastructure/mcp-control-plane", "supremeai-mcp-control-plane", "PROPRIETARY"),
]

# §2.3-declared repos with NO public mirror surface in supremeai-open — the
# guard honestly skips these (it never guesses private repo state, per #1773).
NO_MIRROR_REPOS = frozenset({"supremeai", "supremeai-agents", "supremeai-archive"})

MIN_MIT_REPOS = 3  # open, studio, vscode — fewer means the SSOT parse broke
MIN_PROPRIETARY_REPOS = 5

LICENSE_CANDIDATES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "NOTICE", "NOTICE.md")

# ---------------------------------------------------------------------------
# Known-drift baseline (shrink-only ratchet, dead-import #1598 pattern).
# Dated 2026-10-29 on main a996d30. (code, normalized path) pairs. When one of
# these is FIXED, delete the line and lower the test pin — never add entries
# for new drift; new drift must be fixed, not baselined.
# History: baseline entered at 15 entries (#1773); the 9 PACKAGE_LICENSE_MISSING
# entries were fixed and shrunk out in the same change (issue #1621, the
# #1621<->#1678 class), landing the field-level license floor repo-wide;
# the 4 LICENSE-absent proprietary mirrors and infrastructure/mcp-control-plane
# package.json contradiction were fixed in #1640/#1691 (shrink 6 -> 1).
# ---------------------------------------------------------------------------
KNOWN_DRIFTS: frozenset[tuple[str, str]] = frozenset(
    {
        # r1 heal (#3665, shrink-only): the gateway/LICENSE model contradiction
        # was fixed on main (gateway now ships no contradictory LICENSE text),
        # so the dated baseline entry shrinks to zero. The ratchet only shrinks;
        # new drift must be fixed, never baselined.
    }
)


def _evidence(msg: str) -> None:
    print(f"{GUARD_TAG} {msg}")


# --------------------------------------------------------------------------- #
# §2.3 SSOT parsing (fail-closed when unparseable)                             #
# --------------------------------------------------------------------------- #

MIT_BULLET_PREFIX = "- **Permissive Open-Source"
PROP_BULLET_PREFIX = "- **Proprietary"


def parse_ssot(map_text: str) -> tuple[dict[str, str] | None, str]:
    """Extract (repo -> declared model) from the two §2.3 bullets.

    Returns (mapping_or_None, reason). None mapping = unparseable SSOT, which
    the caller must treat as fail-closed (never a silent pass).
    """
    mit_line = prop_line = None
    for line in map_text.splitlines():
        stripped = line.strip()
        if stripped.startswith(MIT_BULLET_PREFIX) and "MIT" in stripped:
            mit_line = stripped
        elif stripped.startswith(PROP_BULLET_PREFIX) and "All Rights Reserved" in stripped:
            prop_line = stripped
    if mit_line is None or prop_line is None:
        return None, "§2.3 MIT/Proprietary bullets not found in ECOSYSTEM_MAP.md"
    mapping: dict[str, str] = {}
    for repo in re.findall(r"`([^`]+)`", mit_line):
        mapping[repo] = "MIT"
    for repo in re.findall(r"`([^`]+)`", prop_line):
        if repo in mapping and mapping[repo] != "PROPRIETARY":
            return None, f"repo {repo} declared in both MIT and Proprietary bullets"
        mapping[repo] = "PROPRIETARY"
    mit_count = sum(1 for m in mapping.values() if m == "MIT")
    prop_count = sum(1 for m in mapping.values() if m == "PROPRIETARY")
    if mit_count < MIN_MIT_REPOS or prop_count < MIN_PROPRIETARY_REPOS:
        return None, (
            f"§2.3 parse sanity failed: {mit_count} MIT (<{MIN_MIT_REPOS}) / "
            f"{prop_count} PROPRIETARY (<{MIN_PROPRIETARY_REPOS})"
        )
    return mapping, "ok"


# --------------------------------------------------------------------------- #
# License-expression validation (pinned allowlist, no network)                 #
# --------------------------------------------------------------------------- #

def license_tokens(value: str) -> list[str] | None:
    """Split an SPDX expression on AND/OR and validate every token.

    Returns the token list, or None when the value is unusable (empty,
    unquoted-with-unknown-parentheses, or a token outside the allowlist).
    """
    value = (value or "").strip()
    if not value:
        return None
    if "(" in value or ")" in value:
        return None  # parenthesized sub-expressions: out of pinned scope, flagged
    tokens = [tok.strip() for tok in re.split(r"\s+(?:AND|OR)\s+", value) if tok.strip()]
    if not tokens:
        return None
    for tok in tokens:
        if tok not in SPDX_ALLOWLIST:
            return None
    return tokens


# --------------------------------------------------------------------------- #
# Findings + surface scanning                                                  #
# --------------------------------------------------------------------------- #

def classify_findings(
    repo_root: Path, mapping: dict[str, str]
) -> tuple[list[dict], list[str]]:
    """Scan the open repo tree against the declared SSOT.

    Returns (findings, notes). Each finding is a dict with code/path/detail.
    Notes are skip-with-evidence lines (honest degradation, never findings).
    """
    findings: list[dict] = []
    notes: list[str] = []

    def add(code: str, path: str, detail: str) -> None:
        findings.append({"code": code, "path": path, "detail": detail})

    # -- Mapping cross-check: every declared repo must be either surfaced here
    #    or explicitly listed as having no public mirror. New §2.3 rows force a
    #    conscious table update (fail-closed ratchet against silent drift).
    table_repos = {repo: model for _, repo, model in MIRROR_SURFACE_TABLE}
    for repo, model in sorted(mapping.items()):
        if repo in NO_MIRROR_REPOS:
            continue
        if repo not in table_repos:
            add(
                "MAPPING_DRIFT",
                repo,
                f"§2.3 declares {repo} ({model}) but the mirror-surface table has no row — update MIRROR_SURFACE_TABLE",
            )
        elif table_repos[repo] != model:
            add(
                "MAPPING_DRIFT",
                repo,
                f"§2.3 declares {repo} ({model}) but table row says {table_repos[repo]}",
            )
    for repo in sorted(table_repos):
        if repo not in mapping:
            add("MAPPING_DRIFT", repo, "table row not present in parsed §2.3 SSOT")

    surfaces = sorted(MIRROR_SURFACE_TABLE, key=lambda row: -len(row[0]))

    def surface_for(rel_path: str) -> tuple[str, str, str]:
        for surface, repo, model in surfaces:
            if surface == "":
                return surface, repo, model
            if rel_path == surface or rel_path.startswith(surface + "/"):
                return surface, repo, model
        return "", "supremeai-open", "MIT"

    # -- LICENSE/NOTICE presence + content-model marker per surface
    for surface, repo, model in MIRROR_SURFACE_TABLE:
        base = repo_root if surface == "" else repo_root / surface
        if not base.is_dir():
            notes.append(f"surface {surface or '<root>'} ({repo}) absent on disk — skipped with evidence")
            continue
        license_file = next((base / name for name in LICENSE_CANDIDATES if (base / name).is_file()), None)
        if license_file is None:
            add(
                "LICENSE_FILE_ABSENT",
                surface,
                f"{repo} is declared {model} in §2.3 but ships no LICENSE/NOTICE at its mirror root",
            )
        elif model == "PROPRIETARY":
            head = (license_file.read_text(encoding="utf-8", errors="replace")[:400]).lower()
            if "mit license" in head:
                add(
                    "MODEL_CONTRADICTION",
                    license_file.relative_to(repo_root).as_posix(),
                    f"{repo} is declared PROPRIETARY in §2.3 but its mirror LICENSE is the MIT text (the #1690 class)",
                )

    # -- package.json license-field scan across every tracked manifest
    seen: set[Path] = set()
    for pkg in sorted(repo_root.rglob("package.json")):
        rel = pkg.relative_to(repo_root).as_posix()
        if "node_modules" in pkg.parts:
            continue
        if rel in seen:
            continue
        seen.add(pkg)
        surface, repo, model = surface_for(rel)
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001 — unparseable manifest is honest evidence
            notes.append(f"{rel}: unparseable package.json ({exc}) — skipped with evidence")
            continue
        if not isinstance(data, dict):
            notes.append(f"{rel}: package.json root is not an object — skipped with evidence")
            continue
        value = data.get("license")
        if not value or not str(value).strip():
            add(
                "PACKAGE_LICENSE_MISSING",
                rel,
                f"no license field (surface {surface or '<root>'} declared {model} via {repo})",
            )
            continue
        tokens = license_tokens(str(value))
        if tokens is None:
            add(
                "PACKAGE_LICENSE_INVALID",
                rel,
                f"license value {str(value)!r} is not a valid expression over the pinned SPDX allowlist",
            )
            continue
        if model == "PROPRIETARY" and any(tok in OSS_TOKENS for tok in tokens):
            add(
                "MODEL_CONTRADICTION",
                rel,
                f"{repo} is declared PROPRIETARY in §2.3 but package.json declares open-source {value!r}",
            )
        elif model == "MIT" and "LicenseRef-Proprietary" in tokens:
            add(
                "MODEL_CONTRADICTION",
                rel,
                f"{repo} is declared MIT in §2.3 but package.json declares LicenseRef-Proprietary",
            )

    return findings, notes


def evaluate(repo_root: Path, strict: bool = False) -> tuple[int, list[dict], list[str]]:
    """Single decision tree. Returns (exit_code, findings, notes). Never raises."""
    map_path = repo_root / ECOSYSTEM_MAP
    if not map_path.is_file():
        return EXIT_DRIFT, [{"code": "SSOT_UNPARSEABLE", "path": ECOSYSTEM_MAP, "detail": "file absent"}], []
    mapping, why = parse_ssot(map_path.read_text(encoding="utf-8", errors="replace"))
    if mapping is None:
        return (
            EXIT_DRIFT,
            [{"code": "SSOT_UNPARSEABLE", "path": ECOSYSTEM_MAP, "detail": why}],
            [],
        )
    findings, notes = classify_findings(repo_root, mapping)
    known = [f for f in findings if (f["code"], f["path"]) in KNOWN_DRIFTS]
    new = [f for f in findings if (f["code"], f["path"]) not in KNOWN_DRIFTS]
    if strict and findings:
        return EXIT_DRIFT, findings, notes
    if new:
        return EXIT_DRIFT, new + known, notes  # new drift leads the report
    return EXIT_PASS, findings, notes


def render_report(findings: list[dict], notes: list[str], exit_code: int) -> None:
    if not findings and not notes:
        _evidence("license SSOT verified: all declared surfaces clean")
        return
    for note in notes:
        _evidence(f"note | {note}")
    for f in findings:
        marker = "KNOWN-DRIFT (report-only)" if (f["code"], f["path"]) in KNOWN_DRIFTS else "NEW-DRIFT"
        _evidence(f"{marker} | {f['code']} | {f['path']} | {f['detail']}")
    known_n = sum(1 for f in findings if (f["code"], f["path"]) in KNOWN_DRIFTS)
    new_n = len(findings) - known_n
    _evidence(
        f"summary: {len(findings)} finding(s) = {known_n} known (report-only ratchet) + {new_n} new "
        f"· exit {exit_code} · baseline entries: {len(KNOWN_DRIFTS)} (shrink-only)"
    )


# --------------------------------------------------------------------------- #
# Hermetic self-test (offline; sandbox trees, live wiring asserts)             #
# --------------------------------------------------------------------------- #

SSOT_FIXTURE = (
    "### 2.3 Licensing & Intellectual Property Policy (SSOT)\n"
    "- **Permissive Open-Source (MIT License):** Applied to (`supremeai-open`, "
    "`supremeai-studio`, `supremeai-vscode`).\n"
    "- **Proprietary / All Rights Reserved:** Applied to (`supremeai`, `supremeai-core`, "
    "`supremeai-api`, `supremeai-browser`, `supremeai-infrastructure`, "
    "`supremeai-mcp-control-plane`, `supremeai-agents`, `supremeai-archive`).\n"
)


def self_test() -> bool:
    print("[self-test] Running license SSOT guard tests...")
    # 1. SSOT parse: happy path + sanity floors.
    mapping, why = parse_ssot(SSOT_FIXTURE)
    assert mapping is not None, why
    assert mapping["supremeai-open"] == "MIT" and mapping["supremeai-core"] == "PROPRIETARY"
    assert len(mapping) == 11, f"expected 11 declared repos, got {len(mapping)}"
    print("  PASS | §2.3 parse: 3 MIT + 8 PROPRIETARY")
    # 2. Unparseable SSOT must be fail-closed, never a silent pass.
    assert parse_ssot("no bullets here")[0] is None
    ambiguous = SSOT_FIXTURE.replace("`supremeai-core`, ", "").replace(
        "`supremeai-core`", "`supremeai-core`"
    )
    broken = SSOT_FIXTURE.replace("- **Proprietary", "- **SomethingElse")
    assert parse_ssot(broken)[0] is None
    both = SSOT_FIXTURE.replace("`supremeai-archive`", "`supremeai-open`")
    assert parse_ssot(both)[0] is None, "a repo in both bullets must fail the parse"
    del ambiguous
    print("  PASS | unparseable/dual-declared SSOT -> fail-closed")
    # 3. License expression validation.
    assert license_tokens("MIT") == ["MIT"]
    assert license_tokens("MIT OR Apache-2.0") == ["MIT", "Apache-2.0"]
    assert license_tokens("(MIT OR Apache-2.0)") is None
    assert license_tokens("WTFPL") is None
    assert license_tokens("") is None
    assert license_tokens("LicenseRef-Proprietary") == ["LicenseRef-Proprietary"]
    print("  PASS | SPDX allowlist: valid/compound/parenthesized/unknown/LicenseRef")
    # 4. Sandbox repo: detection of every finding class + honest skips.
    with tempfile.TemporaryDirectory(prefix="license-ssot-guard-") as td:
        root = Path(td)
        (root / ECOSYSTEM_MAP).write_text(SSOT_FIXTURE, encoding="utf-8")
        # MIT surface with a LICENSE and a good manifest.
        (root / "studio").mkdir()
        (root / "studio" / "LICENSE").write_text("MIT License\n", encoding="utf-8")
        (root / "studio" / "package.json").write_text('{"name":"s","license":"MIT"}', encoding="utf-8")
        # MIT surface missing LICENSE + manifest field -> 2 findings.
        (root / "vscode").mkdir()
        (root / "vscode" / "package.json").write_text('{"name":"v"}', encoding="utf-8")
        # Proprietary surface, LICENSE-absent -> finding.
        (root / "core").mkdir()
        # Proprietary surface with an MIT LICENSE text -> model contradiction.
        (root / "gateway").mkdir()
        (root / "gateway" / "LICENSE").write_text("MIT License\n", encoding="utf-8")
        # Root-surface manifest without a license field -> finding (the root
        # itself is the supremeai-open MIT surface; valid manifests under
        # studio/ already cover the passing side).
        (root / "package.json").write_text('{"name":"root"}', encoding="utf-8")
        findings, notes = classify_findings(root, mapping)
        by_key = {(f["code"], f["path"]) for f in findings}
        assert ("PACKAGE_LICENSE_MISSING", "vscode/package.json") in by_key, by_key
        assert ("LICENSE_FILE_ABSENT", "vscode") in by_key, by_key
        assert ("LICENSE_FILE_ABSENT", "core") in by_key, by_key
        assert ("MODEL_CONTRADICTION", "gateway/LICENSE") in by_key, by_key
        assert ("PACKAGE_LICENSE_MISSING", "package.json") in by_key, by_key
        assert not any(f["code"] == "MAPPING_DRIFT" for f in findings), findings
        assert any("absent on disk" in n for n in notes), notes  # browser/infra honest skips
        print("  PASS | sandbox scan: missing/absent/contradiction + honest skips")
        # 5. Decision tree: all findings inside baseline -> exit 0 (report-only).
        import license_ssot_guard as guard_mod  # noqa: PLC0415 — self-test only

        # NOTE: mutate + call through the imported module object so the
        # baseline swap is actually visible to evaluate() (when run as a
        # script, __main__ and the re-import are distinct module objects).
        baseline_sandbox = frozenset(by_key)
        saved = guard_mod.KNOWN_DRIFTS
        try:
            guard_mod.KNOWN_DRIFTS = baseline_sandbox
            code, f2, _ = guard_mod.evaluate(root)
            assert code == EXIT_PASS and len(f2) == len(by_key), (code, f2)
            # A NEW finding (not baselined) -> exit 1 even in report-only mode.
            (root / "examples").mkdir()
            (root / "examples" / "package.json").write_text('{"name":"e"}', encoding="utf-8")
            code3, f3, _ = guard_mod.evaluate(root)
            assert code3 == EXIT_DRIFT, (code3, f3)
            assert any(f["path"] == "examples/package.json" for f in f3), f3
            # --strict flips known drifts to fail-closed too.
            (root / "examples" / "package.json").unlink()
            code4, f4, _ = guard_mod.evaluate(root, strict=True)
            assert code4 == EXIT_DRIFT and len(f4) == len(by_key), (code4, len(f4))
        finally:
            guard_mod.KNOWN_DRIFTS = saved
        print("  PASS | ratchet: baseline report-only, new drift exit 1, strict exit 1")
    # 6. Live wiring: roster + pre-push carry the guard (SSOT-extraction style).
    roster = REPO_ROOT / "scripts" / "ci" / "run_all_guards.py"
    if roster.is_file():
        assert "scripts/ci/license_ssot_guard.py" in roster.read_text(encoding="utf-8"), (
            "guard missing from run_all_guards roster"
        )
    hook = REPO_ROOT / ".githooks" / "pre-push"
    if hook.is_file():
        assert "license_ssot_guard.py" in hook.read_text(encoding="utf-8"), (
            "guard missing from pre-push hook"
        )
    print("  PASS | roster + pre-push wiring present (when run inside the repo)")
    print("[self-test] license SSOT guard self-tests PASSED (6 test cases)!")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Machine declared-vs-actual license gate for ECOSYSTEM_MAP §2.3 (#1773)"
    )
    parser.add_argument("--check", action="store_true", help="roster mode: ratchet report (known drift exit 0, new drift exit 1)")
    parser.add_argument("--strict", action="store_true", help="fail-closed on ANY finding (admin mode, post-fix)")
    parser.add_argument("--json", action="store_true", help="machine-readable report on stdout")
    parser.add_argument("--self-test", action="store_true", help="hermetic self-test suite (offline)")
    args = parser.parse_args()

    if args.self_test:
        return EXIT_PASS if self_test() else EXIT_DRIFT

    code, findings, notes = evaluate(REPO_ROOT, strict=args.strict)
    if args.json:
        print(
            json.dumps(
                {
                    "guard": "license_ssot_guard",
                    "map": ECOSYSTEM_MAP,
                    "mode": "strict" if args.strict else "ratchet",
                    "exit": code,
                    "baseline_entries": len(KNOWN_DRIFTS),
                    "findings": findings,
                    "notes": notes,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        for note in notes:
            _evidence(f"note | {note}")
        render_report(findings, notes, code)
    if code == EXIT_DRIFT:
        print(
            f"{GUARD_TAG} ❌ license SSOT drift: fix the findings above, or (admin, post-fix) "
            f"shrink KNOWN_DRIFTS / use --strict semantics deliberately.",
            file=sys.stderr,
        )
    return code


if __name__ == "__main__":
    sys.exit(main())
