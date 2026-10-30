#!/usr/bin/env python3
"""workflow_hardening_census_guard.py — closure-integrity tripwire for the CI
workflow-hardening surface (#1776 family, U4 false-close class).

Defect class this guard exists for (instances: #1776 closed 'completed' while
the hardening was verifiably absent from live main; #3093/#3070/#2225/#2738
same shape): a tracking row for byte-plane-verifiable hardening work is closed
with zero landing evidence, and no mechanical gate can falsify the closure.
The annotations-census gate (#3335/#3336) is the same-family tripwire for the
bridge census surface; this guard is its counterpart for the workflow surface.

What it measures (line-based, stdlib-only, offline, no YAML dependency):
  - uses_total      : every `uses:` occurrence across .github workflows+actions
  - sha_pinned      : external actions pinned to a 40-hex commit SHA
  - local_actions   : `uses: ./...` composite actions (no pin requirement)
  - tag_pinned      : external actions on a mutable tag (unpinned-uses class)
  - checkout_sites  : actions/checkout invocations (artipacked exposure set)
  - persist_false   : explicit `persist-credentials: false` occurrences
  - template_injection : untrusted PR attributes expanded inside run bodies
                       (github.head_ref / github.event.pull_request + ${{ }})
  - persist-credential sub-classes per checkout site (#3527 class): the checkout
    action's `persist-credentials` input DEFAULTS TO TRUE — a site with no
    explicit key persists the job GITHUB_TOKEN into the runner git config just
    as surely as an explicit true. Every checkout window (the lines between a
    checkout `uses:` line and the next line at <= its indentation) is
    classified into exactly one of:
      checkout_explicit_false : window carries `persist-credentials: false`
      persist_explicit_true   : window carries `persist-credentials: true`
      implicit_persist_true   : window carries no persist-credentials key
                                (the #3527 hygiene-debt class; 18 sites in the
                                monorepo's ops-maintenance.yml, 15 on this open
                                repo's surface at baseline)
    and the invariant checkout_sites == checkout_explicit_false +
    persist_explicit_true + implicit_persist_true holds per census (asserted
    in tests and self-test).

Verdicts (fail-closed, same discipline as annotations_census_guard):
  REMEDIATED            exit 0 — every countable class at target
  RESIDUAL              exit 2 — at least one class below target
  INSUFFICIENT_EVIDENCE exit 2 — empty surface, census cannot be taken
  SURFACE_DRIFT         exit 3 — profile differs from --frozen-baseline;
                               re-baseline required with dated evidence
                               (the 2026-10-30 #1776 restructure mode)

Frozen baseline (Zero-Recurrence tripwire, #3527 remedy 2):
  scripts/ci/workflow_hardening_baseline.json freezes this open repo's
  measured profile. Because the drift check compares EVERY profile key, an
  implicit_persist_true INCREASE fails closed (exit 3) and a decrease (a
  fixed site) requires a dated re-baseline — the same shrink-only discipline
  as the mypy/bandit floors. The monorepo lane runs the same guard against
  its own root with its own frozen file (its #3527-verified starting counts:
  23 checkout sites / 5 explicit-false / 18 implicit-true).

Usage:
  python workflow_hardening_census_guard.py --self-test
  python workflow_hardening_census_guard.py --check --root /path/to/repo
  python workflow_hardening_census_guard.py --check --root . --frozen-baseline baseline.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

USES_RE = re.compile(r"^\s*(?:-\s+)?uses:\s*(\S+)", re.MULTILINE)
SHA_RE = re.compile(r"@[0-9a-f]{40}(?:\s|$|#)")
INJECTION_TOKENS = ("github.head_ref", "github.event.pull_request")
EXPR_RE = re.compile(r"\$\{\{")
PERSIST_VALUE_RE = re.compile(r"persist-credentials:\s*(true|false)\b")

PROFILE_KEYS = (
    "uses_total",
    "sha_pinned",
    "local_actions",
    "tag_pinned",
    "checkout_sites",
    "persist_false",
    "template_injection",
    "checkout_explicit_false",
    "persist_explicit_true",
    "implicit_persist_true",
)

REMEDIATED = "REMEDIATED"
RESIDUAL = "RESIDUAL"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
SURFACE_DRIFT = "SURFACE_DRIFT"

WORKFLOW_GLOBS = (".github/workflows/*.yml", ".github/workflows/*.yaml")
ACTION_GLOBS = (".github/actions/*/action.yml", ".github/actions/*/*/action.yml")


def _is_checkout_use(ref: str) -> bool:
    """True for actions/checkout and any local action named *checkout*.

    Same predicate the original census used ("actions/checkout" in ref or
    "checkout" in the action's last path segment before @), kept verbatim so
    checkout_sites counts are unchanged from pre-#3527 runs."""
    return "actions/checkout" in ref or "checkout" in ref.split("@")[0].split("/")[-1]


def _classify_checkout_windows(text: str) -> tuple[int, int, int]:
    """Classify each checkout step window into explicit-false/true/implicit.

    A checkout window spans the checkout `uses:` line plus every following
    line with GREATER indentation, ending at the first non-empty, non-comment
    line with indent <= the uses line (the next step key or sibling step).
    Line-based and YAML-flow tolerant: `with: { persist-credentials: false }`
    on a single line inside the window counts, commented-out keys do not.
    """
    explicit_false = 0
    explicit_true = 0
    implicit_true = 0
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        m = USES_RE.match(line)
        if not m or not _is_checkout_use(m.group(1)):
            continue
        indent = len(line) - len(line.lstrip(" "))
        window = "\n".join(
            l
            for l in lines[idx + 1 :]
            if l.strip() and not l.strip().startswith("#") and (len(l) - len(l.lstrip(" "))) > indent
        )
        found = PERSIST_VALUE_RE.search(window)
        if found is None:
            implicit_true += 1
        elif found.group(1) == "false":
            explicit_false += 1
        else:
            explicit_true += 1
    return explicit_false, explicit_true, implicit_true


def census_text(text: str) -> dict:
    """Census one file's bytes into the countable hardening classes."""
    uses_total = 0
    sha_pinned = 0
    local_actions = 0
    checkout_sites = 0
    persist_false = len(re.findall(r"persist-credentials:\s*false\s*$", text, re.MULTILINE))
    template_injection = 0
    for m in USES_RE.finditer(text):
        ref = m.group(1)
        uses_total += 1
        if ref.startswith("./"):
            local_actions += 1
            continue
        if SHA_RE.search(ref):
            sha_pinned += 1
        if _is_checkout_use(ref):
            checkout_sites += 1
    for line in text.splitlines():
        if EXPR_RE.search(line) and any(tok in line for tok in INJECTION_TOKENS):
            template_injection += 1
    checkout_explicit_false, persist_explicit_true, implicit_persist_true = _classify_checkout_windows(text)
    return {
        "uses_total": uses_total,
        "sha_pinned": sha_pinned,
        "local_actions": local_actions,
        "tag_pinned": uses_total - sha_pinned - local_actions,
        "checkout_sites": checkout_sites,
        "persist_false": persist_false,
        "template_injection": template_injection,
        "checkout_explicit_false": checkout_explicit_false,
        "persist_explicit_true": persist_explicit_true,
        "implicit_persist_true": implicit_persist_true,
    }


def census_surface(root: Path) -> tuple[dict, list[str]]:
    """Census the whole .github workflow+action surface under root."""
    total = {key: 0 for key in PROFILE_KEYS}
    files: list[str] = []
    patterns = [p for glob in WORKFLOW_GLOBS + ACTION_GLOBS for p in [glob]]
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            files.append(str(path))
            per = census_text(text)
            for key in total:
                total[key] += per[key]
    return total, files


def baseline_drift(baseline: dict, profile: dict) -> dict:
    """Return {key: (baseline_value, live_value)} for every drifted key.

    Extracted pure helper (was inline in main) so the #3527 shrink-only
    tripwire is unit-testable: any profile key not present in the baseline
    drifts, and so does any value change in either direction — an
    implicit_persist_true increase fails closed, a decrease (a fixed site)
    requires a dated re-baseline."""
    return {k: (baseline.get(k), profile[k]) for k in profile if baseline.get(k) != profile[k]}


def classify(profile: dict, surface_files: int) -> tuple[str, int]:
    """Four-quadrant fail-closed verdict on a hardening census profile."""
    if surface_files == 0 or profile["uses_total"] == 0:
        return INSUFFICIENT_EVIDENCE, 2
    target_pin = profile["uses_total"] - profile["local_actions"]
    pins_ok = profile["sha_pinned"] >= target_pin
    persist_ok = profile["checkout_sites"] == 0 or profile["persist_false"] >= profile["checkout_sites"]
    inject_ok = profile["template_injection"] == 0
    if pins_ok and persist_ok and inject_ok:
        return REMEDIATED, 0
    return RESIDUAL, 2


def _self_test() -> int:
    cases = []

    # 1. Hardened surface: all external uses SHA-pinned, checkouts persisted-off, no injection.
    hardened = textwrap_dedent(
        """
        jobs:
          build:
            steps:
              - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v5
                with:
                  persist-credentials: false
              - uses: actions/setup-node@39370e3970a6aaaa5b8b0db1d59a6a5eeef664a4 # v5
        """
    )
    cases.append(("hardened", hardened, 1, REMEDIATED, 0))

    # 2. The #1776-era profile: tag-pinned uses, no persist-credentials, live head_ref injection.
    era1776 = textwrap_dedent(
        """
        jobs:
          guard:
            steps:
              - uses: actions/checkout@v5
              - run: BRANCH=$(echo "${{ github.head_ref }}" | grep -oE 'issue-?[0-9]+')
        """
    )
    cases.append(("1776-era", era1776, 1, RESIDUAL, 2))

    # 3. The 2026-10-30 restructured surface (synthetic): persist-credentials present,
    #    injection gone, but checkouts still tag-pinned -> unpinned-uses class persists.
    restructured = textwrap_dedent(
        """
        jobs:
          intake:
            steps:
              - uses: actions/checkout@v5
                with:
                  persist-credentials: false
        """
    )
    cases.append(("restructured", restructured, 1, RESIDUAL, 2))

    # 4. Empty surface -> fail-closed, never assume remediation.
    cases.append(("empty", "", 0, INSUFFICIENT_EVIDENCE, 2))

    # 5. Local composite actions only: no external pin requirement, no injection.
    local_only = textwrap_dedent(
        """
        runs:
          steps:
            - uses: ./.github/actions/setup-backend
        """
    )
    cases.append(("local-only", local_only, 1, REMEDIATED, 0))

    # 6 (#3527 class): implicit persist-true — checkout with no persist-credentials key.
    implicit = textwrap_dedent(
        """
        jobs:
          maintain:
            steps:
              - uses: actions/checkout@v5
                with:
                  fetch-depth: 0
        """
    )
    cases.append(("implicit-persist-true", implicit, 1, RESIDUAL, 2))

    # 7 (#3527 class): explicit persist-credentials: true — same exposure, spelled out.
    explicit_true = textwrap_dedent(
        """
        jobs:
          maintain:
            steps:
              - uses: actions/checkout@v5
                with:
                  persist-credentials: true
        """
    )
    cases.append(("explicit-persist-true", explicit_true, 1, RESIDUAL, 2))

    # 8 (#3527 class): window boundary — a sibling step at the SAME indent must not
    # leak its own text into the checkout's window (no phantom explicit_false).
    boundary = textwrap_dedent(
        """
        jobs:
          maintain:
            steps:
              - uses: actions/checkout@v5
              - run: echo 'persist-credentials: false'
        """
    )
    cases.append(("window-boundary", boundary, 1, RESIDUAL, 2))

    failures = 0
    for name, text, n_files, want_verdict, want_code in cases:
        profile = census_text(text)
        got_verdict, got_code = classify(profile, n_files)
        ok = (got_verdict, got_code) == (want_verdict, want_code)
        print(f"  self-test {name}: profile={profile} -> {got_verdict}/{got_code} {'PASS' if ok else 'FAIL'}")
        if not ok:
            failures += 1

    # 9 (#3527 invariant): every checkout window classifies exactly once.
    invariant_specs = (
        ("hardened", hardened, 1, 0, 0),
        ("1776-era", era1776, 0, 0, 1),
        ("restructured", restructured, 1, 0, 0),
        ("implicit-persist-true", implicit, 0, 0, 1),
        ("explicit-persist-true", explicit_true, 0, 1, 0),
        ("window-boundary", boundary, 0, 0, 1),
    )
    for name, text, want_false, want_true, want_implicit in invariant_specs:
        p = census_text(text)
        ok = p["checkout_sites"] == p["checkout_explicit_false"] + p["persist_explicit_true"] + p["implicit_persist_true"] and (
            p["checkout_explicit_false"],
            p["persist_explicit_true"],
            p["implicit_persist_true"],
        ) == (want_false, want_true, want_implicit)
        print(
            f"  self-test {name} persist-invariant: "
            f"sites={p['checkout_sites']} false={p['checkout_explicit_false']} "
            f"true={p['persist_explicit_true']} implicit={p['implicit_persist_true']} {'PASS' if ok else 'FAIL'}"
        )
        if not ok:
            failures += 1

    # 10. Drift detector: restructured profile vs hardened baseline must flag drift.
    baseline = census_text(hardened)
    drift_profile = census_text(restructured)
    drifted = any(drift_profile[k] != baseline[k] for k in baseline)
    print(f"  self-test drift-detection: {drift_profile} vs baseline {baseline} -> {'PASS' if drifted else 'FAIL'}")
    if not drifted:
        failures += 1

    # 11 (#3527 tripwire): baseline_drift helper — implicit-true increase drifts,
    # missing baseline key drifts, exact match does not.
    base = census_text(hardened)
    same = baseline_drift(base, census_text(hardened))
    increased = baseline_drift(base, {**census_text(hardened), "implicit_persist_true": 1})
    missing_key = baseline_drift({"uses_total": 2}, census_text(hardened))
    tripwire_ok = same == {} and "implicit_persist_true" in increased and len(missing_key) > 0
    print(
        f"  self-test baseline-tripwire: same={same == {}}, "
        f"increase-drifts={'implicit_persist_true' in increased}, "
        f"missing-key-drifts={len(missing_key) > 0} {'PASS' if tripwire_ok else 'FAIL'}"
    )
    if not tripwire_ok:
        failures += 1

    print(f"workflow_hardening_census_guard self-test: {'PASS' if failures == 0 else 'FAIL'} ({failures} failure(s))")
    return 0 if failures == 0 else 2


def textwrap_dedent(text: str) -> str:
    """Minimal dedent (stdlib textwrap import kept local to avoid shadowing)."""
    lines = text.split("\n")
    indents = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
    cut = min(indents) if indents else 0
    return "\n".join(l[cut:] if len(l) >= cut else l.lstrip() for l in lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true", help="run offline fixtures and exit")
    parser.add_argument("--check", action="store_true", help="census the surface and classify")
    parser.add_argument("--root", default=".", help="repository root holding .github/")
    parser.add_argument("--frozen-baseline", default=None, help="baseline JSON file; exit 3 on drift")
    parser.add_argument("--json", action="store_true", help="print the profile as JSON")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()
    if not args.check:
        parser.print_help()
        return 0

    root = Path(args.root)
    profile, files = census_surface(root)
    verdict, code = classify(profile, len(files))

    if args.frozen_baseline:
        try:
            baseline = json.loads(Path(args.frozen_baseline).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print(f"[workflow-hardening-census] unreadable baseline {args.frozen_baseline} -> INSUFFICIENT_EVIDENCE")
            return 2
        diff = baseline_drift(baseline, profile)
        if diff:
            print(f"[workflow-hardening-census] SURFACE_DRIFT (re-baseline with dated evidence): {diff}")
            if args.json:
                print(json.dumps({"profile": profile, "files": files}, indent=2))
            return 3

    print(f"[workflow-hardening-census] files={len(files)} profile={json.dumps(profile)}")
    print(f"[workflow-hardening-census] verdict={verdict} exit={code}")
    if verdict == RESIDUAL:
        print(
            "[workflow-hardening-census] residual classes present: "
            f"tag_pinned={profile['tag_pinned']} "
            f"unpersisted_checkouts={max(0, profile['checkout_sites'] - profile['persist_false'])} "
            f"(explicit_false={profile['checkout_explicit_false']} "
            f"explicit_true={profile['persist_explicit_true']} "
            f"implicit_true={profile['implicit_persist_true']}) "
            f"template_injection={profile['template_injection']} "
            "- closure-as-completed on this surface is falsifiable while these are non-zero"
        )
    if args.json:
        print(json.dumps({"profile": profile, "files": files, "verdict": verdict}, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
