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
  7. The ``pipeline.yml`` board pre-check's CLAIMABLE exclusion label array
     must not hide claimable work from the dispatcher: any label it excludes
     that the loop's ``EXCLUDED_LABELS`` frozenset (SSOT) does not, fails the
     guard (starvation direction). The opposite lag (the pre-check missing
     SSOT labels, dispatcher burning a job the loop then refuses) is reported
     as a warning line — the workflow file is admin-lane (``.github/`` is
     bridge-protected), so waste-direction drift cannot be fixed agent-side.
  8. The integration contract doc (``docs/AUTONOMY_LOOP_CONTRACT.md``) must
     keep its claim-exclusion story SSOT-first: it must point at the loop's
     ``EXCLUDED_LABELS`` frozenset instead of hand-copying the label list
     (the copy had drifted to 5 of 12 labels), and any label it still names
     must be a real loop exclusion — a doc-only label tells integrators to
     skip claimable work (starvation, fail-closed); an enumeration lagging
     the SSOT merely wastes integrator claims (waste, warn — the doc is
     bridge-editable, so agents can sync it, unlike ``pipeline.yml``).

Exit codes: 0 = parity held · 1 = drift detected · 2 = guard environment error.
"""

import contextlib
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is the loop's only dependency
    print("GUARD-ENV-ERROR: PyYAML required (pip install pyyaml)")
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[2]
LOOP = ROOT / "scripts" / "agents" / "continuous_agent_loop.py"
SPEC = ROOT / "docs" / "AGENT_LOOP_SPEC.md"
CONTRIB = ROOT / "CONTRIBUTING.md"  # moved to repo root by #3524 (founder doc migration)
CONTRACT_DOC = ROOT / "docs" / "AUTONOMY_LOOP_CONTRACT.md"
GUARDS_WF = ROOT / ".github" / "workflows" / "pipeline.yml"
# The open-guards.yml fallback was removed with the #155 workflow diet: a
# missing guard workflow is now a fail-closed guard-environment error, not a
# silent fallback to a deleted file.


def main() -> int:
    for path in (LOOP, SPEC, CONTRIB, GUARDS_WF, CONTRACT_DOC):
        if not path.is_file():
            print(f"GUARD-ENV-ERROR: missing required file: {path.relative_to(ROOT)}")
            return 2

    failures: list[str] = []
    code = LOOP.read_text(encoding="utf-8")
    spec = SPEC.read_text(encoding="utf-8")
    contrib = CONTRIB.read_text(encoding="utf-8")

    # 1. Evidence tier count: code emission vs SPEC §4 SSOT row.
    emitted = sorted(
        {int(n) for n in re.findall(r'\{\s*["\']tier["\']:\s*(\d+),', code)}
    )
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

    # 7. Board pre-check claim-exclusion set vs the loop EXCLUDED_LABELS SSOT.
    #    The pre-check hand-copies pick_next_issue()'s exclusion set inside a
    #    jq filter (#88/#222). Asymmetric severity: a label the pipeline
    #    excludes but the loop doesn't means real claimable work is hidden
    #    from the dispatcher (starvation — fail-closed). The opposite lag only
    #    burns a dispatcher job on a board the loop refuses (waste — warn:
    #    pipeline.yml is admin-lane, agents cannot sync it).
    warnings: list[str] = []
    loop_labels_m = re.search(
        r"EXCLUDED_LABELS\s*=\s*frozenset\(\{(.*?)\}\)", code, re.S
    )
    pipe_lines = [
        ln
        for ln in GUARDS_WF.read_text(encoding="utf-8").splitlines()
        if "CLAIMABLE=" in ln and "select((" in ln
    ]
    if loop_labels_m is None:
        failures.append(
            "loop code lost the EXCLUDED_LABELS frozenset "
            "(claim-exclusion SSOT, guard 7)"
        )
    elif len(pipe_lines) != 1:
        failures.append(
            "pipeline.yml must contain exactly one CLAIMABLE claim-exclusion "
            f"jq filter for guard 7, found {len(pipe_lines)}"
        )
    else:
        loop_labels = {
            s.lower() for s in re.findall(r'"([^"]+)"', loop_labels_m.group(1))
        }
        labels_m = re.search(r"select\(\(\[([^\]]*)\]", pipe_lines[0])
        if labels_m is None:
            failures.append(
                "pipeline.yml CLAIMABLE filter lost the exclusion label array "
                "(select(([...]) shape, guard 7)"
            )
        else:
            pipe_labels = {
                s.strip().strip('"\'').lower()
                for s in labels_m.group(1).split(",")
                if s.strip()
            }
            starvation = pipe_labels - loop_labels
            waste = loop_labels - pipe_labels
            if starvation:
                failures.append(
                    "claim-exclusion drift (guard 7, starvation): "
                    "pipeline.yml board pre-check excludes label(s) the loop "
                    f"EXCLUDED_LABELS SSOT does not: {sorted(starvation)} — "
                    "claimable work is hidden from the dispatcher; remove them "
                    "from the CLAIMABLE jq array or add them to the loop SSOT "
                    "deliberately"
                )
            elif waste:
                warnings.append(
                    "claim-exclusion lag (guard 7, waste direction): "
                    "pipeline.yml board pre-check is missing loop "
                    f"EXCLUDED_LABELS SSOT label(s) {sorted(waste)} — the "
                    "dispatcher burns a job on a board the loop then refuses; "
                    "admin-lane fix: extend the CLAIMABLE jq array with the "
                    "loop SSOT set (workflow is .github/, bridge-protected)"
                )

    # 8. Contract-doc claim-exclusion parity. AUTONOMY_LOOP_CONTRACT.md §1 is
    #    the surface integrators read INSTEAD of the loop source, so its
    #    exclusion-label enumeration is a third hand-copy of the
    #    EXCLUDED_LABELS SSOT (it drifted to 5 of 12 labels while the doc's
    #    own anti-drift scope note forbids duplication). The doc must point
    #    at the SSOT frozenset; any label it still names must be a real loop
    #    exclusion. Asymmetric severity, same doctrine as guard 7: a
    #    doc-only label hides claimable work from integrators (starvation —
    #    fail-closed); an enumeration lagging the SSOT only wastes
    #    integrator claims the loop refuses (waste — warn; docs/ is
    #    bridge-editable, so agents can sync it).
    doc_labels: set = set()
    doc_text = CONTRACT_DOC.read_text(encoding="utf-8")
    if "EXCLUDED_LABELS" not in doc_text:
        failures.append(
            "AUTONOMY_LOOP_CONTRACT.md lost the EXCLUDED_LABELS SSOT pointer "
            "(integrators read this doc instead of the loop source, guard 8)"
        )
    else:
        ssot_m8 = re.search(
            r"EXCLUDED_LABELS\s*=\s*frozenset\(\{(.*?)\}\)", code, re.S
        )
        if ssot_m8 is None:
            failures.append(
                "loop code lost the EXCLUDED_LABELS frozenset "
                "(claim-exclusion SSOT, guard 8 cannot verify the contract doc)"
            )
        else:
            loop_labels_8 = {
                s.lower() for s in re.findall(r'"([^"]+)"', ssot_m8.group(1))
            }
            # Namespaced label shape covers 10 of the 12 SSOT labels;
            # non-colon SSOT labels (admin-only, anchor-hub,
            # blocked-by-upstream) count only when the loop really has
            # them, so doc tokens like task-envelope-v1 never false-positive.
            for tok in re.findall(r"`([^`]+)`", doc_text):
                tok = tok.strip().lower()
                if re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*:[a-z0-9-]+", tok):
                    doc_labels.add(tok)
                elif tok in loop_labels_8:
                    doc_labels.add(tok)
            starve8 = doc_labels - loop_labels_8
            waste8 = loop_labels_8 - doc_labels if doc_labels else set()
            if starve8:
                failures.append(
                    "contract-doc exclusion drift (guard 8, starvation): "
                    "AUTONOMY_LOOP_CONTRACT.md names exclusion label(s) the "
                    f"loop EXCLUDED_LABELS SSOT does not have: {sorted(starve8)} "
                    "— integrators will skip claimable work; point the doc at "
                    "the SSOT frozenset instead of enumerating labels"
                )
            elif waste8:
                warnings.append(
                    "contract-doc exclusion lag (guard 8, waste direction): "
                    "AUTONOMY_LOOP_CONTRACT.md enumerates only "
                    f"{sorted(doc_labels)} of the loop EXCLUDED_LABELS SSOT "
                    f"({sorted(waste8)} missing) — integrators attempt claims "
                    "the loop refuses; fix: replace the enumeration with the "
                    "EXCLUDED_LABELS SSOT pointer (doc is bridge-editable)"
                )

    if warnings:
        for warning in warnings:
            print(f"⚠ {warning}")

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
        "all workflow references resolve, "
        f"claim-exclusion parity ({len(loop_labels)} labels pipeline, "
        f"{len(doc_labels) if doc_labels else 'SSOT-pointer'} doc)"
        + ("" if not warnings else ", waste-direction lag warned above")
        + ")."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
