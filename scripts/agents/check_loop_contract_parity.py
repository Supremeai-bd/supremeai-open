#!/usr/bin/env python3
"""Loop-Contract Parity Guard (#118) — docs/code SSOT sync, fail-closed.

The loop's contract surface (evidence tiers, guards, flag semantics) drifted
repeatedly because it was hand-duplicated across five surfaces. This guard
makes the drift machine-visible:

  1. Evidence tier count: the tiers emitted by ``continuous_agent_loop.py``
     (``{"tier": N, ...}`` appends) must match the tier range declared by the
     SSOT row in ``docs/AGENT_LOOP_SPEC.md`` §4 ("tiers 1–N"), with no gaps.
  2. No hardcoded "<N>-tier checks passed" / "All <N>-tier checks" literal in
     the loop code — the count must be derived from the evidence list.
  3. SPEC §5 must name every guard job that ``pipeline.yml`` actually runs.
  4. CONTRIBUTING.md must carry no flag-table copy (SSOT is SPEC §4).
  5. The SSOT pointers must exist (SPEC §4b → §4; CONTRIBUTING → this guard).
  6. Every ``.github/workflows/*.yml`` reference in the loop code or the SPEC
     must resolve to an existing workflow file on disk (the deleted
     ``open-guards.yml`` drift class — #214).

Exit codes: 0 = parity held · 1 = drift detected · 2 = guard environment error.
"""

import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is the loop's only dependency
    print("GUARD-ENV-ERROR: PyYAML required (pip install pyyaml)")
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[2]
LOOP = ROOT / "scripts" / "agents" / "continuous_agent_loop.py"
SPEC = ROOT / "docs" / "AGENT_LOOP_SPEC.md"
CONTRIB = ROOT / "docs" / "CONTRIBUTING.md"
GUARDS_WF = ROOT / ".github" / "workflows" / "pipeline.yml"
# The open-guards.yml fallback was removed with the #155 workflow diet: a
# missing guard workflow is now a fail-closed guard-environment error, not a
# silent fallback to a deleted file.


def main() -> int:
    for path in (LOOP, SPEC, CONTRIB, GUARDS_WF):
        if not path.is_file():
            print(f"GUARD-ENV-ERROR: missing required file: {path.relative_to(ROOT)}")
            return 2

    failures: list[str] = []
    code = LOOP.read_text(encoding="utf-8")
    spec = SPEC.read_text(encoding="utf-8")
    contrib = CONTRIB.read_text(encoding="utf-8")

    # 1. Evidence tier count: code emission vs SPEC §4 SSOT row.
    emitted = sorted({int(n) for n in re.findall(r'\{"tier": (\d+),', code)})
    declared = None
    if not emitted:
        failures.append("no evidence tier emissions found in the loop code")
    else:
        gaps = [t for t in range(1, max(emitted) + 1) if t not in emitted]
        if gaps:
            failures.append(f"evidence tier sequence has gaps in code: {gaps}")
        m = re.search(r"tiers 1[–-](\d+)", spec)
        if not m:
            failures.append('SPEC §4 SSOT row does not declare "tiers 1–N"')
        else:
            declared = int(m.group(1))
            if declared != max(emitted):
                failures.append(
                    f"tier-count drift: code emits tiers 1..{max(emitted)}, "
                    f"SPEC §4 declares tiers 1..{declared}"
                )

    # 2. No hardcoded tier-count success literal (count must be derived).
    if re.search(r'"[0-9]+-tier checks passed', code) or re.search(
        r"All [0-9]+-tier checks", code
    ):
        failures.append(
            "hardcoded tier-count success string found in the loop code — "
            "derive the count from the evidence list instead"
        )

    # 3. SPEC §5 guard list vs pipeline.yml guard job set (name-level parity).
    def norm(name: str) -> str:
        name = re.sub(r"\(#[0-9]+\)", "", name)
        name = re.sub(r"[^A-Za-z ]+", " ", name)
        return re.sub(r"\s+", " ", name).strip()

    wf = yaml.safe_load(GUARDS_WF.read_text(encoding="utf-8"))
    job_names = {
        norm(j.get("name") or jid)
        for jid, j in wf["jobs"].items()
        if "guard" in jid.lower() or "guard" in (j.get("name") or "").lower()
    }
    sec5 = norm(spec.split("## 5.")[1].split("## 6.")[0])
    for job in sorted(job_names):
        if job and job not in sec5:
            failures.append(f"SPEC §5 does not document pipeline guard job: '{job}'")

    # 4. No flag-table copy in CONTRIBUTING (SSOT is SPEC §4).
    if re.search(r"^\|\s*`--", contrib, flags=re.MULTILINE):
        failures.append(
            "CONTRIBUTING.md still contains a flag-table copy (SSOT is SPEC §4)"
        )

    # 5. SSOT pointers present.
    if "count SSOT: §4" not in spec:
        failures.append("SPEC §4b row lost the tier-count SSOT pointer")
    if "check_loop_contract_parity" not in contrib:
        failures.append("CONTRIBUTING lost the parity-guard pointer")

    # 6. Every .github/workflows/*.yml reference in the loop-contract surfaces
    #    must resolve to an existing workflow file (#214: the envelope pointed
    #    agents at open-guards.yml, deleted in the #155 workflow diet).
    wf_ref_re = re.compile(r"\.github/workflows/([A-Za-z0-9_.-]+\.ya?ml)")
    for surface in (LOOP, SPEC):
        surface_text = surface.read_text(encoding="utf-8")
        for wf_name in sorted(set(wf_ref_re.findall(surface_text))):
            if not (ROOT / ".github" / "workflows" / wf_name).is_file():
                failures.append(
                    f"{surface.relative_to(ROOT)} references a deleted workflow: "
                    f".github/workflows/{wf_name}"
                )

    if failures:
        print("❌ Loop-contract parity FAILED:")
        for failure in failures:
            print(f"   - {failure}")
        return 1

    print(
        f"✅ Loop-contract parity OK: tiers 1..{max(emitted)} "
        f"(code == SPEC §4 declared 1..{declared}), "
        f"{len(job_names)} guards (workflow == SPEC §5), "
        "no flag-table copy, SSOT pointers present, "
        "all workflow references resolve."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
