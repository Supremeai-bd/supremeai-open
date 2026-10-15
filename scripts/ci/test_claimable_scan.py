#!/usr/bin/env python3
"""Offline claimable-scan contract test (#122) — mirrors the #88 stub pattern.

Verifies the ``--pick-next`` claim filter's #122 mirror gate:

  1. Mirror issues (body DECLARES a non-public ``### Target Repository``)
     are excluded from dispatch even when they are the oldest claimable P0.
  2. Marker-carrying mirrors (``<!-- MIRROR_SOURCE: ... -->`` + private
     target field, the exact #78-#81 shape) are excluded.
  3. Normal unclaimed issues are still selected — priority label order and
     oldest-first tie-break are preserved.
  4. Legacy stubs/issues without a ``body`` key keep working (#88
     backward compatibility — absence of the field never excludes).
  5. Prose MENTIONS of the private repo (triage issues quoting the mirror
     marker) do NOT trigger exclusion — detection is field-anchored.
  6. An all-mirror claimable board dispatches nothing (fail-closed: no
     dispatch is better than a blocked handoff).

Run: ``python scripts/ci/test_claimable_scan.py`` — exit 0 = all green.
No network, no gh CLI, no pytest dependency required.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.agents.continuous_agent_loop as loop  # noqa: E402

# --- Realistic issue bodies -------------------------------------------------
MIRROR_BODY = (
    "<!-- MIRROR_SOURCE: Supremeai-bd/supremeai#142 -->\n\n"
    "### Target Repository\n"
    "Supremeai-bd/supremeai\n\n"
    "### Priority Tier\n"
    "P2-medium\n"
)
MIRROR_BODY_BACKTICKED = (
    "### Target Repository\n"
    "`Supremeai-bd/supremeai`\n"
)
PUBLIC_BODY = (
    "### Target Repository\n"
    "Supremeai-bd/supremeai-open\n\n"
    "### Priority Tier\n"
    "P2-medium\n"
)
PROSE_BODY = (
    "Audit issue quoting the mirror marker for evidence: "
    "`<!-- MIRROR_SOURCE: Supremeai-bd/supremeai#100 -->`.\n\n"
    "### Target Repository\n"
    "Supremeai-bd/supremeai-open\n"
)


def check(name: str, cond: bool) -> None:
    if not cond:
        print(f"FAIL: {name}")
        raise SystemExit(1)
    print(f"ok: {name}")


# --- 1. Unit level: the field parser and the predicate ----------------------
check("parser: next-line private target",
      loop._declared_target_repository(MIRROR_BODY) == "supremeai-bd/supremeai")
check("parser: backticked target unwrapped",
      loop._declared_target_repository(MIRROR_BODY_BACKTICKED) == "supremeai-bd/supremeai")
check("parser: next-line public target",
      loop._declared_target_repository(PUBLIC_BODY) == "supremeai-bd/supremeai-open")
check("parser: same-line colon layout",
      loop._declared_target_repository("### Target Repository: Supremeai-bd/supremeai\n")
      == "supremeai-bd/supremeai")
check("parser: missing field -> None",
      loop._declared_target_repository("no field here") is None)
check("parser: header only (next line is another header) -> None",
      loop._declared_target_repository("### Target Repository\n### Priority Tier\n") is None)
check("parser: non-string/empty body -> None",
      loop._declared_target_repository(None) is None and
      loop._declared_target_repository("") is None)

check("gate: private target excluded", loop.declares_non_public_target({"body": MIRROR_BODY}))
check("gate: public target kept",
      not loop.declares_non_public_target({"body": PUBLIC_BODY}))
check("gate: prose quote of marker kept (no false positive)",
      not loop.declares_non_public_target({"body": PROSE_BODY}))
check("gate: absent body kept (legacy issues)",
      not loop.declares_non_public_target({}) and
      not loop.declares_non_public_target({"body": None}))

# --- 2. Selection level: monkeypatched run_cmd (the #88 stub pattern) -------
def with_stub(stub: list[dict]) -> str | None:
    loop.run_cmd = lambda cmd: (0, json.dumps(stub), "")  # type: ignore[method-assign]
    return loop.pick_next_issue()


# Mirror is the oldest claimable P0 — it must NOT win; public sibling does.
stub = [
    {"number": 201, "title": "private mirror, oldest P0",
     "labels": [{"name": "status:unclaimed"}, {"name": "P0-critical"}],
     "body": MIRROR_BODY},
    {"number": 202, "title": "normal unclaimed P2",
     "labels": [{"name": "status:unclaimed"}, {"name": "P2-medium"}],
     "body": PUBLIC_BODY},
]
check("dispatch: mirror skipped, public sibling picked",
      with_stub(stub) == "202")

# Priority + tie-break still work among public issues (#88 contract).
stub2 = [
    {"number": 55, "title": "prose p0 critical words",
     "labels": [{"name": "status:unclaimed"}], "body": PUBLIC_BODY},
    {"number": 66, "title": "nothing special",
     "labels": [{"name": "status:unclaimed"}, {"name": "P0-critical"}],
     "body": PUBLIC_BODY},
]
check("dispatch: real P0 label outranks prose titles (#88)",
      with_stub(stub2) == "66")

# Legacy #88 stub shape (no body key at all) keeps passing unchanged.
stub3 = [
    {"number": 101, "title": "old unclaimed P1",
     "labels": [{"name": "status:unclaimed"}, {"name": "P1-high"}]},
    {"number": 102, "title": "claimed p0 critical words",
     "labels": [{"name": "status:in-progress"}, {"name": "P0-critical"}]},
    {"number": 103, "title": "held work",
     "labels": [{"name": "status:unclaimed"}, {"name": "state:seq-hold"}]},
    {"number": 104, "title": "unlabeled tail",
     "labels": [{"name": "status:unclaimed"}]},
]
check("dispatch: legacy no-body stubs unchanged (#88 compat)",
      with_stub(stub3) == "101")

# Board full of mirrors -> nothing dispatchable (fail-closed, no wasted run).
stub4 = [
    {"number": 301, "title": "mirror A",
     "labels": [{"name": "status:unclaimed"}, {"name": "P0-critical"}],
     "body": MIRROR_BODY},
    {"number": 302, "title": "mirror B",
     "labels": [{"name": "status:unclaimed"}, {"name": "P1-high"}],
     "body": MIRROR_BODY_BACKTICKED},
]
check("dispatch: all-mirror board yields no pick (fail-closed)",
      with_stub(stub4) is None)

# gh failure paths unchanged.
loop.run_cmd = lambda cmd: (1, "", "boom")  # type: ignore[method-assign]
check("dispatch: gh failure still returns None", loop.pick_next_issue() is None)

print("claimable-scan mirror-gate contract: OK (#122)")
