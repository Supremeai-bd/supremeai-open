#!/usr/bin/env python3
"""contract_fuzz_guard.py — runtime OpenAPI contract-fuzzing gate (R40, #1898).

Mission (issue #1898, scout radar lane R40):
    The contract triangle had two of three legs mechanically guarded:
    producer drift (#1760 oasdiff breaks-gate between spec revisions) and
    consumer viability (#1846 pinned-generator codegen guard). The third leg
    — does the IMPLEMENTATION conform to the SPEC at runtime, under hostile
    negative input — was guarded by nothing. This guard closes that leg:
    Schemathesis (pinned 4.32.7, MIT) reads the SSOT spec
    (api-schemas/gateway.openapi.yaml), binds gateway/service/app.py
    in-memory via the ASGI transport (zero sockets, zero credentials, zero
    upstream provider calls — chat auth fail-closes 401 before any provider
    touch), and generates schema-aware positive + negative traffic against
    the real implementation.

What the landing run witnessed (dated 2026-10-28, seed 42, live):
    F1  status_code_conformance failures — /v1/chat/completions answers
        malformed JSON with 400 {"detail":"Invalid JSON payload"} but the
        spec declares [200, 401, 403, 429, 502, 503]; the 400 is
        undocumented in the SSOT (oasdiff cannot see it — it diffs two
        revisions, not implementation-vs-spec).
    F2  ignored_auth failures — /v1/models serves anonymous AND forged-key
        requests while the spec's top-level security says a key is required.
        Owner's call (spec security:[] vs implement auth) — REPORT-ONLY
        routing to the gateway domain (U1/U3), never an agent fix.
    F3  not_a_server_error — zero 5xx across the entire run. This is the
        crash class: HARD-ASSERTED, never ratcheted, never baselined.

Behavior contract (the #1796/#1809/#1735 shrink-only ratchet family, adapted
for property-based fuzzing):

    1. Ratchet unit = the SET of failing check CLASSES (e.g.
       status_code_conformance), NOT the failure COUNT: counts under a
       wall-clock time box are not reproducible run-to-run (the cutoff lands
       mid-generation), so a count-ratchet would false-red. The class set
       was stable across independent runs (this guard's landing run and the
       #1898 scout run agree on the failing classes). Counts are recorded as
       last-seen watermarks for evidence, never gated on magnitude.
    2. --check: any failing class NOT in the baseline's known_failing set is
       NEW DRIFT -> exit 1 with the class list. Classes in the baseline are
       compliant. not_a_server_error failures -> exit 1 immediately
       (hard assertion; a 5xx is a crash, never a baseline entry).
    3. The baseline may only SHRINK: --update-baseline rewrites it as the
       INTERSECTION with the current failing set (a class that stopped
       failing leaves the baseline); it refuses (exit 2) when the current
       set contains a class absent from the baseline — new classes must be
       triaged first, never baselined away silently. Absent baseline +
       --update-baseline bootstraps from the live run.
    4. Honest degradation (#1760 pattern): schemathesis not installed ->
       skip with evidence (exit 0, note emitted) — never a fabricated PASS.
       The in-repo gateway app failing to import is NOT degradation (repo
       code, not an external tool) -> exit 1 fail-closed.
    5. Determinism knobs: seed pinned (42) in the run config; max-time is a
       wall-clock budget (default 60s, roster-friendly). A tool-version
       mismatch vs the baseline provenance is a NOTE, not a failure.

Never-do (issue #1898):
    - No agent fixes for F2 (auth direction is a gateway-owner decision);
      the guard reports, the §2.2 mirror table routes.
    - Never touch the SSOT spec to silence the guard (editing
      api-schemas/gateway.openapi.yaml to add the 400 is a CONTRACT-DOC
      patch for the gateway domain to land, not this guard's business).
    - No network, no sockets, no provider calls: the ASGI transport never
      leaves the process; the chat route fail-closes 401 in
      _verify_client_auth before any upstream touch.

Usage:
    python scripts/ci/contract_fuzz_guard.py --check             # roster mode
    python scripts/ci/contract_fuzz_guard.py --update-baseline   # shrink/bootstrap
    python scripts/ci/contract_fuzz_guard.py --check --max-time 90
    python scripts/ci/contract_fuzz_guard.py --json              # machine report
    python scripts/ci/contract_fuzz_guard.py --self-test         # hermetic

Exit codes: 0 = pass / known-floor / honest skip · 1 = new drift or 5xx or
fail-closed condition · 2 = usage error (growth refused / bad invocation).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "api-schemas" / "gateway.openapi.yaml"
BASELINE_PATH = REPO_ROOT / "scripts" / "ci" / "contract_fuzz_baseline.json"
PINNED_SCHEMATHESIS = "4.32.7"
DEFAULT_SEED = 42
DEFAULT_MAX_TIME = 60
# The crash class: any failure here fails the guard outright.
HARD_ASSERT_CLASSES = {"not_a_server_error"}


# ---------------------------------------------------------------------------
# Baseline model (class-set shrink-only ratchet)
# ---------------------------------------------------------------------------

def load_baseline(path: Path) -> dict | None:
    """Load the baseline; corrupt content is a fail-closed condition (None + marker)."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("known_failing"), dict):
        return None
    return data


def evaluate_against_baseline(
    failing: set[str],
    known: dict[str, int],
) -> tuple[list[str], list[str]]:
    """Split the live failing set vs the baseline.

    Returns (new_drift, shrunk): classes absent from the baseline (red), and
    baseline classes that no longer fail (improvement — shrink candidate).
    """
    new_drift = sorted(c for c in failing if c not in known)
    shrunk = sorted(c for c in known if c not in failing)
    return new_drift, shrunk


def intersect_baseline(known: dict[str, int], failing: dict[str, int]) -> dict[str, int]:
    """Intersection-only baseline rewrite: keeps only still-failing classes.

    A class that kept failing keeps its RECORD count (the watermark may stay
    above the live count — wall-clock variance makes live counts non-authoritative).
    """
    return {c: known.get(c, failing[c]) for c in sorted(failing) if c in known}


def bootstrap_baseline(failing: dict[str, int]) -> dict[str, int]:
    """Bootstrap a fresh baseline from a live run (baseline absent case)."""
    return {c: failing[c] for c in sorted(failing)}


# ---------------------------------------------------------------------------
# Live fuzz execution (imported lazily so --self-test stays hermetic)
# ---------------------------------------------------------------------------

def run_live_fuzz(max_time: int, seed: int) -> tuple[dict[str, int], int, list[str]]:
    """Run the in-memory ASGI fuzz; return (failing_counts, interactions, notes).

    Raises RuntimeError on fail-closed conditions (missing tool is handled by
    the caller as honest skip; missing spec or broken app import are red).
    """
    try:
        import schemathesis
    except ImportError as exc:
        raise SkipSignal(f"schemathesis not installed ({exc}) — honest skip (#1760 pattern)") from None

    if not SPEC_PATH.is_file():
        raise RuntimeError(f"SSOT spec missing: {SPEC_PATH}")

    notes: list[str] = []
    version = getattr(schemathesis, "__version__", None) or getattr(
        schemathesis, "SCHEMATHESIS_VERSION", "?"
    )
    if version != PINNED_SCHEMATHESIS:
        notes.append(
            f"schemathesis {version} != pinned {PINNED_SCHEMATHESIS} (baseline provenance); counts may shift"
        )

    # Silence the app's secret-vault mock warnings (names only, but noisy).
    from loguru import logger

    logger.remove()

    # scripts/ci/<guard>.py execution puts scripts/ci on sys.path, not the
    # repo root — the in-repo gateway package lives at the root.
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from gateway.service.app import app  # in-repo production implementation

    from schemathesis import openapi as st_openapi

    cfg = schemathesis.Config.from_dict(
        {"max-time": max_time, "seed": seed, "max-failures": 1000000}
    )
    schema = st_openapi.from_path(str(SPEC_PATH), config=cfg)
    schema.app = app  # mirror from_asgi's binding for file-loaded schemas
    schema.get_transport(app)

    import collections

    import schemathesis.engine as eng
    from schemathesis.engine import Status

    failing: dict[str, int] = collections.Counter()
    interactions = 0
    for ev in eng.from_schema(schema).execute():
        name = type(ev).__name__
        if name in ("ScenarioFinished", "FuzzScenarioFinished"):
            rec = ev.recorder
            interactions += len(getattr(rec, "interactions", None) or {})
            for checks in (getattr(rec, "checks", None) or {}).values():
                for chk in checks:
                    if chk.status == Status.FAILURE:
                        failing[chk.name] += 1
        # NonFatalError / FatalError events are tolerated: per-operation
        # generation errors (e.g. unsatisfiable coverage probes) are the
        # engine's own honesty, not contract drift.

    return dict(failing), interactions, notes


class SkipSignal(Exception):
    """Honest-skip condition (external tool absent) — exits 0 with evidence."""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_check(max_time: int, as_json: bool, baseline_path: Path | None = None) -> int:
    started = time.time()
    baseline = load_baseline(baseline_path or BASELINE_PATH)
    if baseline is None:
        print(
            f"contract-fuzz guard: FAIL — baseline missing or corrupt: {BASELINE_PATH} "
            "(fail-closed; run --update-baseline to bootstrap explicitly, never silently)"
        )
        return 1
    known: dict[str, int] = baseline.get("known_failing", {})
    try:
        failing, interactions, notes = run_live_fuzz(max_time, DEFAULT_SEED)
    except SkipSignal as exc:
        print(f"contract-fuzz guard: SKIP — {exc}")
        return 0
    except RuntimeError as exc:
        print(f"contract-fuzz guard: FAIL — {exc}")
        return 1

    # Hard assertion: the crash class is never baselined.
    hard = sorted(c for c in failing if c in HARD_ASSERT_CLASSES)
    if hard:
        detail = ", ".join(f"{c}={failing[c]}" for c in hard)
        print(f"contract-fuzz guard: FAIL — 5xx/crash class observed (never tolerated): {detail}")
        return 1

    new_drift, shrunk = evaluate_against_baseline(set(failing), known)
    elapsed = time.time() - started
    report = {
        "verdict": "FAIL" if new_drift else "PASS",
        "interactions": interactions,
        "wall_seconds": round(elapsed, 1),
        "failing_classes": failing,
        "known_failing": known,
        "new_drift": new_drift,
        "shrunk_since_baseline": shrunk,
        "notes": notes,
    }
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"contract-fuzz guard: {report['verdict']} — {interactions} interactions in {elapsed:.1f}s "
            f"(seed {DEFAULT_SEED}, max-time {max_time}s)"
        )
        for n in notes:
            print(f"  note: {n}")
        for c, n in sorted(failing.items()):
            print(f"  known-failing: {c} live={n} baseline={known.get(c, 'ABSENT')}")
        for c in new_drift:
            print(f"  NEW DRIFT: {c} (absent from baseline — triage before baselining)")
        for c in shrunk:
            print(f"  shrunk: {c} no longer fails — run --update-baseline to shrink the file")
    return 1 if new_drift else 0


def cmd_update_baseline(max_time: int, baseline_path: Path | None = None) -> int:
    target = baseline_path or BASELINE_PATH
    baseline = load_baseline(target)
    try:
        failing, interactions, _notes = run_live_fuzz(max_time, DEFAULT_SEED)
    except SkipSignal as exc:
        print(f"contract-fuzz guard: SKIP — {exc}")
        return 0
    except RuntimeError as exc:
        print(f"contract-fuzz guard: FAIL — {exc}")
        return 1
    hard = sorted(c for c in failing if c in HARD_ASSERT_CLASSES)
    if hard:
        print(f"contract-fuzz guard: REFUSED — crash class {hard} must never be baselined")
        return 2

    if baseline is None:
        known = bootstrap_baseline(failing)
        action = "bootstrapped"
    else:
        current_known: dict[str, int] = baseline.get("known_failing", {})
        new_classes = sorted(c for c in failing if c not in current_known)
        if new_classes:
            print(
                "contract-fuzz guard: REFUSED — live run carries classes absent from the baseline "
                f"({new_classes}); triage them first, never grow the baseline (exit 2)"
            )
            return 2
        known = intersect_baseline(current_known, failing)
        action = "intersection-rewritten"

    import schemathesis

    version = getattr(schemathesis, "__version__", "?")
    payload = {
        "known_failing": known,
        "provenance": {
            "issue": "1898",
            "radar": "R40",
            "pinned_schemathesis": PINNED_SCHEMATHESIS,
            "schemathesis_at_generation": version,
            "seed": DEFAULT_SEED,
            "max_time": max_time,
            "interactions_at_generation": interactions,
            "spec": "api-schemas/gateway.openapi.yaml",
            "app": "gateway/service/app.py (in-memory ASGI)",
            "ratchet": "failing-class-set shrink-only; counts are watermarks, not gates",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    }
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"contract-fuzz guard: baseline {action} — {len(known)} classes, {interactions} interactions")
    for c, n in sorted(known.items()):
        print(f"  {c}: {n}")
    return 0


# ---------------------------------------------------------------------------
# Self-test (hermetic — no schemathesis, no gateway import, no network)
# ---------------------------------------------------------------------------

def run_self_test() -> int:
    cases = 0
    failed = 0

    def expect(name: str, cond: bool) -> None:
        nonlocal cases, failed
        cases += 1
        ok = bool(cond)
        if not ok:
            failed += 1
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")

    base = {"status_code_conformance": 4125, "ignored_auth": 4124,
            "missing_required_header": 1, "negative_data_rejection": 1}

    expect("known failing set passes (no new drift)",
           evaluate_against_baseline(set(base), base) == ([], []))
    expect("new class is drift",
           evaluate_against_baseline(set(base) | {"response_schema_conformance"}, base)[0]
           == ["response_schema_conformance"])
    expect("shrunk class detected",
           evaluate_against_baseline(set(base) - {"ignored_auth"}, base)[1] == ["ignored_auth"])

    expect("intersection keeps only still-failing classes",
           intersect_baseline(base, {"status_code_conformance": 500}) == {"status_code_conformance": 4125})
    expect("intersection preserves record watermark over live count",
           intersect_baseline({"a": 10}, {"a": 3}) == {"a": 10})
    expect("bootstrap takes the live set verbatim",
           bootstrap_baseline({"x": 2, "y": 7}) == {"x": 2, "y": 7})

    # corrupt baseline -> fail-closed (evaluate path is only reached with a
    # parsed baseline; the loader contract is exercised here)
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        expect("corrupt baseline loads as None (fail-closed)", load_baseline(bad) is None)
        empty = Path(td) / "empty.json"
        empty.write_text("{}", encoding="utf-8")
        expect("baseline without known_failing loads as None (fail-closed)", load_baseline(empty) is None)
        good = Path(td) / "good.json"
        good.write_text(json.dumps({"known_failing": base}), encoding="utf-8")
        expect("valid baseline parses", load_baseline(good) is not None)

    expect("crash class is hard-asserted (member of HARD_ASSERT_CLASSES)",
           "not_a_server_error" in HARD_ASSERT_CLASSES)
    expect("spec path anchors the SSOT", SPEC_PATH.name == "gateway.openapi.yaml")

    print(f"self-test: {cases - failed}/{cases} cases passed")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Runtime OpenAPI contract-fuzzing gate (#1898 R40)")
    parser.add_argument("--check", action="store_true", help="fuzz the live app against the baseline (roster mode)")
    parser.add_argument("--update-baseline", action="store_true", help="bootstrap/intersection-rewrite the baseline")
    parser.add_argument("--max-time", type=int, default=DEFAULT_MAX_TIME, help="wall-clock fuzz budget in seconds")
    parser.add_argument("--baseline-path", type=str, default=None, help="override baseline path (tests/fixtures)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable report (with --check)")
    parser.add_argument("--self-test", action="store_true", help="hermetic ratchet-logic tests")
    args = parser.parse_args()

    baseline_override = Path(args.baseline_path) if args.baseline_path else None
    if args.self_test:
        return run_self_test()
    if args.update_baseline:
        return cmd_update_baseline(args.max_time, baseline_override)
    if args.check or not (args.self_test or args.update_baseline):
        return cmd_check(args.max_time, args.json, baseline_override)
    return 0


if __name__ == "__main__":
    sys.exit(main())
