#!/usr/bin/env python3
"""workflow_hardening_census_guard.py — closure-integrity tripwire for the CI
workflow-hardening surface (#1776 family, U4 false-close class).

Defect class this guard exists for (instances: #1776 closed 'completed' while
the hardening was verifiably absent from live main; #3093/#3070/#2225/#2738
same shape): a tracking row for byte-plane-verifiable hardening work is closed
with zero landing evidence, and no mechanical gate can falsify the closure.
The annotations-census gate (#3335/#3336) is the same-family tripwire for the
bridge census surface; this guard is its counterpart for the workflow surface.

r2 (2026-10-31, #3527 remedy: implicit_persist_true machine-tracking):
  r1 counted only explicit `persist-credentials: false` occurrences with a
  global regex, so implicitly-persisting checkout sites (the actions/checkout
  default persist-credentials: true — every later step can read the job
  GITHUB_TOKEN from runner git config) were invisible as a first-class count:
  ops-maintenance.yml carried 23 checkout sites with just 5 explicit `false`
  (18 implicit true, 11 of those jobs holding write permissions) and no gate
  could see the 18 as a tracked number. r2 resolves the credential posture
  per checkout site (with-block-aware line scan) and emits four countable
  classes; a frozen baseline turns any new implicitly-persisting checkout
  into a SURFACE_DRIFT (Zero-Recurrence tripwire).

What it measures (line-based, stdlib-only, offline, no YAML dependency):
  - uses_total      : every `uses:` occurrence across .github workflows+actions
  - sha_pinned      : external actions pinned to a 40-hex commit SHA
  - local_actions   : `uses: ./...` composite actions (no pin requirement)
  - tag_pinned      : external actions on a mutable tag (unpinned-uses class)
  - checkout_sites  : actions/checkout invocations (artipacked exposure set)
  - persist_false   : checkout sites explicitly `persist-credentials: false`
  - persist_true_explicit : checkout sites explicitly `persist-credentials: true`
  - persist_dynamic : checkout sites with a non-boolean/expression value
                      (fail-closed: counted as NOT persisted)
  - implicit_persist_true : checkout sites with NO persist-credentials key in
                      their step body (default-true exposure — the #3527 class)
  - template_injection : untrusted PR attributes expanded inside run bodies
                      (github.head_ref / github.event.pull_request + ${{ }})

Verdicts (fail-closed, same discipline as annotations_census_guard):
  REMEDIATED            exit 0 — every countable class at target
  RESIDUAL              exit 2 — at least one class below target
  INSUFFICIENT_EVIDENCE exit 2 — empty surface, census cannot be taken
  SURFACE_DRIFT         exit 3 — profile differs from --frozen-baseline;
                               re-baseline required with dated evidence
                               (the 2026-10-30 #1776 restructure mode; the
                               2026-10-31 #3527 r2 class-schema upgrade also
                               requires a one-time re-baseline)

Usage:
  python workflow_hardening_census_guard.py --self-test
  python workflow_hardening_census_guard.py --check --root /path/to/repo
  python workflow_hardening_census_guard.py --check --root . --frozen-baseline baseline.json
  python workflow_hardening_census_guard.py --check --root . --emit-baseline baseline.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

USES_RE = re.compile(r"^\s*(?:-\s+)?uses:\s*(\S+)", re.MULTILINE)
SHA_RE = re.compile(r"@[0-9a-f]{40}(?:\s|$|#)")
STEP_USES_RE = re.compile(r"^(\s*)(-\s+)?uses:\s*(\S+)")
PERSIST_RE = re.compile(r"^(\s*)persist-credentials:\s*(\S+)")
INJECTION_TOKENS = ("github.head_ref", "github.event.pull_request")
EXPR_RE = re.compile(r"\$\{\{")

REMEDIATED = "REMEDIATED"
RESIDUAL = "RESIDUAL"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
SURFACE_DRIFT = "SURFACE_DRIFT"

WORKFLOW_GLOBS = (".github/workflows/*.yml", ".github/workflows/*.yaml")
ACTION_GLOBS = (".github/actions/*/action.yml", ".github/actions/*/*/action.yml")


def is_checkout_ref(ref: str) -> bool:
    """Same checkout-site predicate as the uses-census (name-based)."""
    return "actions/checkout" in ref or "checkout" in ref.split("@")[0].split("/")[-1]


def resolve_checkouts(text: str) -> dict:
    """Per-checkout credential-posture census (the #3527 class).

    For each `uses:` step invoking actions/checkout, scan the step's own body
    (lines indented deeper than the step's base column, until the first
    non-comment line at or above the base column ends the step) for a
    persist-credentials key, and classify its value:
      false          -> persisted-off (hardened)
      true           -> explicitly persisted
      anything else  -> dynamic/expression (fail-closed: not persisted)
      no key found   -> implicit default (actions/checkout persists by default)
    """
    counts = {
        "persist_false": 0,
        "persist_true_explicit": 0,
        "persist_dynamic": 0,
        "implicit_persist_true": 0,
    }
    lines = text.split("\n")
    for idx, line in enumerate(lines):
        m = STEP_USES_RE.match(line)
        if not m:
            continue
        ref = m.group(3)
        if not is_checkout_ref(ref):
            continue
        # Step base column: the dash of the enclosing list item. When the
        # `uses:` key itself carries the dash, that is this line; otherwise
        # walk back to the nearest dash-led line at a shallower column
        # (the `- name:` / `- id:` step-opening key).
        if m.group(2):
            base = line.index("-")
        else:
            uses_indent = len(m.group(1))
            base = uses_indent
            for j in range(idx - 1, -1, -1):
                prev = lines[j]
                pstripped = prev.strip()
                if not pstripped or pstripped.startswith("#"):
                    continue
                pcol = len(prev) - len(prev.lstrip())
                if pcol >= uses_indent:
                    break
                dash = re.match(r"^(\s*)-\s", prev)
                if dash:
                    base = prev.index("-")
                    break
                break
        value = None
        for j in range(idx + 1, len(lines)):
            nxt = lines[j]
            stripped = nxt.strip()
            if not stripped or stripped.startswith("#"):
                continue
            col = len(nxt) - len(nxt.lstrip())
            if col <= base:
                break
            pm = PERSIST_RE.match(nxt)
            if pm:
                value = pm.group(2).strip().strip("\"'")
                break
        if value is None:
            counts["implicit_persist_true"] += 1
        elif value == "false":
            counts["persist_false"] += 1
        elif value == "true":
            counts["persist_true_explicit"] += 1
        else:
            # Expression values (${{ ... }}) or any non-boolean literal:
            # fail-closed as unknown (counted as NOT persisted).
            counts["persist_dynamic"] += 1
    return counts


def census_text(text: str) -> dict:
    """Census one file's bytes into the countable hardening classes."""
    uses_total = 0
    sha_pinned = 0
    local_actions = 0
    checkout_sites = 0
    template_injection = 0
    for m in USES_RE.finditer(text):
        ref = m.group(1)
        uses_total += 1
        if ref.startswith("./"):
            local_actions += 1
            continue
        if SHA_RE.search(ref):
            sha_pinned += 1
        if is_checkout_ref(ref):
            checkout_sites += 1
    for line in text.splitlines():
        if EXPR_RE.search(line) and any(tok in line for tok in INJECTION_TOKENS):
            template_injection += 1
    profile = {
        "uses_total": uses_total,
        "sha_pinned": sha_pinned,
        "local_actions": local_actions,
        "tag_pinned": uses_total - sha_pinned - local_actions,
        "checkout_sites": checkout_sites,
        "template_injection": template_injection,
    }
    profile.update(resolve_checkouts(text))
    return profile


def census_surface(root: Path) -> tuple[dict, list[str]]:
    """Census the whole .github workflow+action surface under root."""
    total = {
        "uses_total": 0,
        "sha_pinned": 0,
        "local_actions": 0,
        "tag_pinned": 0,
        "checkout_sites": 0,
        "persist_false": 0,
        "persist_true_explicit": 0,
        "persist_dynamic": 0,
        "implicit_persist_true": 0,
        "template_injection": 0,
    }
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

    failures = 0
    for name, text, n_files, want_verdict, want_code in cases:
        profile = census_text(text)
        got_verdict, got_code = classify(profile, n_files)
        ok = (got_verdict, got_code) == (want_verdict, want_code)
        print(f"  self-test {name}: profile={profile} -> {got_verdict}/{got_code} {'PASS' if ok else 'FAIL'}")
        if not ok:
            failures += 1

    # 6. Drift detector: restructured profile vs hardened baseline must flag drift.
    baseline = census_text(hardened)
    drift_profile = census_text(restructured)
    drifted = any(drift_profile[k] != baseline[k] for k in baseline)
    print(f"  self-test drift-detection: {drift_profile} vs baseline {baseline} -> {'PASS' if drifted else 'FAIL'}")
    if not drifted:
        failures += 1

    # 7. r2 (#3527): mixed checkout postures must resolve per-site, with the
    #    implicit default counted as a first-class number.
    mixed = textwrap_dedent(
        """
        jobs:
          a:
            steps:
              - name: Checkout repository
                uses: actions/checkout@v5 # v7.0.1
                with:
                  persist-credentials: false # comment suffix must not break the scan
              - uses: actions/checkout@v5
          b:
            steps:
              - uses: actions/checkout@v5
                with:
                  persist-credentials: true
              - uses: actions/checkout@v5
                with:
                  persist-credentials: ${{ matrix.persist }}
              - uses: actions/checkout@v5
                with:
                  fetch-depth: 0
        """
    )
    mixed_profile = census_text(mixed)
    want_mixed = {
        "checkout_sites": 5,
        "persist_false": 1,
        "persist_true_explicit": 1,
        "persist_dynamic": 1,
        "implicit_persist_true": 2,  # the bare -uses step and the fetch-depth-only step
    }
    got_mixed = {k: mixed_profile[k] for k in want_mixed}
    ok7 = got_mixed == want_mixed
    print(f"  self-test r2-mixed-postures: {got_mixed} -> {'PASS' if ok7 else 'FAIL'} (want {want_mixed})")
    if not ok7:
        failures += 1

    # 8. r2 (#3527): step-body scan must stop at the next same-indent step, not
    #    leak the following step's keys into the first checkout's posture.
    leaky = textwrap_dedent(
        """
        jobs:
          a:
            steps:
              - uses: actions/checkout@v5
              - uses: actions/setup-node@v5
                with:
                  persist-credentials: false
        """
    )
    leaky_profile = census_text(leaky)
    ok8 = (
        leaky_profile["checkout_sites"] == 1
        and leaky_profile["implicit_persist_true"] == 1
        and leaky_profile["persist_false"] == 0
    )
    print(
        f"  self-test r2-step-body-boundary: checkout={leaky_profile['checkout_sites']} "
        f"implicit={leaky_profile['implicit_persist_true']} false={leaky_profile['persist_false']} "
        f"-> {'PASS' if ok8 else 'FAIL'}"
    )
    if not ok8:
        failures += 1

    # 9. r2 (#3527): all-checkouts-persisted-off surface classifies REMEDIATED on
    #    the persist axis even when other classes are clean.
    all_off = textwrap_dedent(
        """
        jobs:
          a:
            steps:
              - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v5
                with:
                  persist-credentials: false
              - uses: actions/checkout@22bd71901bbe5b1630ceea73d27597364c9af683 # v5
                with:
                  persist-credentials: false
        """
    )
    all_off_profile = census_text(all_off)
    ok9 = (
        classify(all_off_profile, 1) == (REMEDIATED, 0)
        and all_off_profile["implicit_persist_true"] == 0
    )
    print(f"  self-test r2-all-off: profile={all_off_profile} -> {'PASS' if ok9 else 'FAIL'}")
    if not ok9:
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
    parser.add_argument(
        "--emit-baseline",
        default=None,
        metavar="PATH",
        help="write the current census as a frozen-baseline JSON (re-baseline mode; pair with dated evidence)",
    )
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

    if args.emit_baseline:
        Path(args.emit_baseline).write_text(
            json.dumps(profile, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"[workflow-hardening-census] frozen baseline written to {args.emit_baseline}")

    if args.frozen_baseline:
        try:
            baseline = json.loads(Path(args.frozen_baseline).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print(f"[workflow-hardening-census] unreadable baseline {args.frozen_baseline} -> INSUFFICIENT_EVIDENCE")
            return 2
        diff = {k: (baseline.get(k), profile[k]) for k in profile if baseline.get(k) != profile[k]}
        if diff:
            print(f"[workflow-hardening-census] SURFACE_DRIFT (re-baseline with dated evidence): {diff}")
            if args.json:
                print(json.dumps({"profile": profile, "files": files}, indent=2))
            return 3

    print(f"[workflow-hardening-census] files={len(files)} profile={json.dumps(profile)}")
    print(f"[workflow-hardening-census] verdict={verdict} exit={code}")
    if verdict == RESIDUAL:
        unpersisted = (
            profile["implicit_persist_true"]
            + profile["persist_true_explicit"]
            + profile["persist_dynamic"]
        )
        print(
            "[workflow-hardening-census] residual classes present: "
            f"tag_pinned={profile['tag_pinned']} "
            f"unpersisted_checkouts={max(0, unpersisted)} "
            f"(implicit={profile['implicit_persist_true']} "
            f"explicit_true={profile['persist_true_explicit']} "
            f"dynamic={profile['persist_dynamic']}) "
            f"template_injection={profile['template_injection']} "
            "- closure-as-completed on this surface is falsifiable while these are non-zero"
        )
    if args.json:
        print(json.dumps({"profile": profile, "files": files, "verdict": verdict}, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
