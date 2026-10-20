#!/usr/bin/env python3
"""S10 — Ecosystem Scout Agent reference implementation (issue #497).

Institutionalizes the **Ecosystem Scout (`agent:scout` / `ecosystem-scout`)**:
external intelligence, comparative dissection and tech-adoption engineering
across the SupremeAI federation, governed by the

    Surgical Need-Driven Extraction Doctrine
    ("কতটুকু দরকার, কীভাবে দরকার — পুরো কপি নয়, সেরা কোডটুকু নেওয়া")

Deterministic contract enforced here (fail-closed everywhere):

  * `EcosystemDossier` mirrors the issue's TypeScript schema field-for-field;
  * the 4-phase dissection methodology (EXTRACTION → DISSECTION → AUDIT →
    RFC) is a typed pipeline with a validator per phase;
  * the **Surgical Extraction Guard** rejects wholesale vendoring:
    `full_repo_vending_prohibited` must be `True`, a Gold Pearl component
    list must be present (20–100 line budget per component), the adaptation
    blueprint must name a native zero-dependency target (Python for
    `scripts/agents/`, `scripts/ci/`; TypeScript for control-plane/studio/
    sdk), and vendor markers are forbidden;
  * attribution hygiene: adoption verdicts require a known license and the
    provenance header template (`Adapted from <repo> under <license>`);
  * `render_dossier_markdown()` exports the standard SupremeAI artifact
    with the কতটুকু দরকার / কীভাবে দরকার breakdown;
  * `scout_analyze_repository()` is the pure-core reference for the MCP
    tool of the same name (network I/O stays in the tower adapter — this
    module is offline and deterministic).

Pure stdlib. Run: python3 scripts/agents/ecosystem_scout_reference.py --self-test
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any, Final

# ---------------------------------------------------------------------------
# Doctrine constants
# ---------------------------------------------------------------------------

#: Gold Pearl budget — the exact high-value slice the Scout may extract.
GOLD_PEARL_MIN_LINES: Final = 20
GOLD_PEARL_MAX_LINES: Final = 100

VERDICTS: Final = (
    "ADOPT_IMMEDIATELY",
    "EXTRACT_PATTERNS_ONLY",
    "MONITOR",
    "REJECT",
)

ACTION_TYPES: Final = (
    "adopt_library",
    "replicate_pattern",
    "integrate_mcp",
)

PHASE_1_EXTRACTION: Final = "PHASE_1_EXTRACTION"
PHASE_2_DISSECTION: Final = "PHASE_2_DISSECTION"
PHASE_3_AUDIT: Final = "PHASE_3_AUDIT"
PHASE_4_RFC: Final = "PHASE_4_RFC"
PHASES: Final = (PHASE_1_EXTRACTION, PHASE_2_DISSECTION, PHASE_3_AUDIT, PHASE_4_RFC)

#: Canonical federation satellites (issue #497 routing targets; extensible —
#: an unknown satellite name is allowed by the schema, an EMPTY routing list
#: is not).
CANONICAL_SATELLITES: Final = (
    "supremeai-open",
    "supremeai-browser",
    "supremeai-agents",
    "supremeai-mcp-control-plane",
    "supremeai-studio",
    "supremeai-sdk",
    "supremeai-infra",
)

#: Native zero-dependency targets for adaptation blueprints.
NATIVE_TARGETS: Final = ("python", "typescript")

#: Markers that indicate wholesale vendoring instead of surgical extraction.
VENDOR_MARKERS: Final = (
    "git clone",
    "git submodule",
    "npm install",
    "pip install git+",
    "vendor the entire",
    "copy the whole repository",
    "vendored tree",
)

PROVENANCE_HEADER_TEMPLATE: Final = (
    "Concept / algorithm adapted from: github.com/{repository}\n"
    "Upstream License: {license}\n"
    "Adapted for SupremeAI Federation lightweight satellite runtime."
)


class DossierError(ValueError):
    """Raised when a dossier violates the Scout contract (fail-closed)."""


class PhaseError(ValueError):
    """Raised when a methodology phase produces invalid evidence."""


# ---------------------------------------------------------------------------
# Schema — field-for-field mirror of the issue's TypeScript EcosystemDossier
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Target:
    repository: str
    license: str
    tech_stack: tuple[str, ...]
    core_purpose: str


@dataclass(frozen=True)
class ComparativeAnalysis:
    superior_capabilities: tuple[str, ...]
    supremeai_advantages: tuple[str, ...]
    token_and_resource_impact: str


@dataclass(frozen=True)
class SurgicalExtraction:
    exact_components_needed: tuple[str, ...]
    adaptation_blueprint: str
    full_repo_vending_prohibited: bool


@dataclass(frozen=True)
class SatelliteAction:
    satellite: str
    action_type: str
    rationale: str


@dataclass(frozen=True)
class ActionableTakeaways:
    architectural_patterns: tuple[str, ...]
    reusable_components: tuple[str, ...]
    target_satellites: tuple[SatelliteAction, ...]


@dataclass(frozen=True)
class WatchoutsAndRisks:
    anti_patterns: tuple[str, ...]
    security_or_compliance_concerns: tuple[str, ...]
    prohibited_practices: tuple[str, ...]


@dataclass(frozen=True)
class EcosystemDossier:
    target: Target
    comparative_analysis: ComparativeAnalysis
    surgical_extraction: SurgicalExtraction
    actionable_takeaways: ActionableTakeaways
    watchouts_and_risks: WatchoutsAndRisks
    verdict: str


# ---------------------------------------------------------------------------
# Surgical Extraction Guard
# ---------------------------------------------------------------------------


def validate_surgical_extraction(extraction: SurgicalExtraction) -> None:
    """Anti-Vending Invariant + Gold Pearl budget + native-fitting check."""
    if extraction.full_repo_vending_prohibited is not True:
        raise DossierError(
            "Anti-Vending Invariant violated: full_repo_vending_prohibited "
            "must be True — wholesale repository copying is prohibited"
        )
    if not extraction.exact_components_needed:
        raise DossierError(
            "Surgical extraction requires the exact Gold Pearl components "
            "('কতটুকু দরকার') — got an empty list"
        )
    blueprint = extraction.adaptation_blueprint.strip()
    if not blueprint:
        raise DossierError("adaptation_blueprint ('কীভাবে দরকার') is empty")
    if not any(target in blueprint.lower() for target in NATIVE_TARGETS):
        raise DossierError(
            "adaptation_blueprint must fit SupremeAI natively — name python "
            "or typescript as the zero-dependency target"
        )
    lowered = blueprint.lower()
    for marker in VENDOR_MARKERS:
        if marker in lowered:
            raise DossierError(
                f"vendor marker {marker!r} found in adaptation blueprint — "
                "extract the Gold Pearl, never vendor trees"
            )


def validate_gold_pearl_budget(component_lines: int) -> None:
    """A Gold Pearl slice must stay inside the 20-100 line budget."""
    if not (GOLD_PEARL_MIN_LINES <= component_lines <= GOLD_PEARL_MAX_LINES):
        raise DossierError(
            f"Gold Pearl budget is {GOLD_PEARL_MIN_LINES}-"
            f"{GOLD_PEARL_MAX_LINES} lines, got {component_lines}"
        )


def provenance_header(repository: str, license_name: str) -> str:
    """Attribution hygiene: the provenance header every adaptation carries."""
    if not repository or not license_name:
        raise DossierError("provenance header requires repository and license")
    return PROVENANCE_HEADER_TEMPLATE.format(
        repository=repository, license=license_name
    )


# ---------------------------------------------------------------------------
# Verdict & routing
# ---------------------------------------------------------------------------


def validate_dossier(dossier: EcosystemDossier) -> None:
    """Full fail-closed dossier validation (all four phases consolidated)."""
    if dossier.verdict not in VERDICTS:
        raise DossierError(
            f"verdict must be one of {VERDICTS}, got {dossier.verdict!r}"
        )

    t = dossier.target
    if not t.repository or not t.core_purpose:
        raise DossierError("target.repository and target.core_purpose are mandatory")
    if not t.tech_stack:
        raise DossierError(
            "target.tech_stack is mandatory (runtime truth, never marketing pages)"
        )

    c = dossier.comparative_analysis
    if not c.superior_capabilities:
        raise DossierError(
            "comparative_analysis.superior_capabilities is empty — "
            "'ওরা কোথায় বেটার' must be answered"
        )
    if not c.supremeai_advantages:
        raise DossierError(
            "comparative_analysis.supremeai_advantages is empty — "
            "SupremeAI's own strengths must be stated"
        )
    if not c.token_and_resource_impact:
        raise DossierError("comparative_analysis.token_and_resource_impact is empty")

    validate_surgical_extraction(dossier.surgical_extraction)

    a = dossier.actionable_takeaways
    if not a.architectural_patterns or not a.reusable_components:
        raise DossierError(
            "actionable_takeaways requires architectural_patterns "
            "and reusable_components"
        )
    if not a.target_satellites:
        raise DossierError(
            "actionable_takeaways.target_satellites is empty — "
            "route the RFC to the 11-satellite federation"
        )
    for action in a.target_satellites:
        if action.action_type not in ACTION_TYPES:
            raise DossierError(
                f"action_type must be one of {ACTION_TYPES}, got {action.action_type!r}"
            )
        if not action.rationale:
            raise DossierError(
                f"satellite action for {action.satellite!r} needs a rationale"
            )

    w = dossier.watchouts_and_risks
    if not w.anti_patterns:
        raise DossierError(
            "watchouts_and_risks.anti_patterns is empty — "
            "'কী করা যাবে না' must be answered"
        )
    if not w.security_or_compliance_concerns:
        raise DossierError(
            "watchouts_and_risks.security_or_compliance_concerns "
            "is empty — fingerprint/bloat/boundary risks mandatory"
        )
    if not w.prohibited_practices:
        raise DossierError("watchouts_and_risks.prohibited_practices is empty")

    # Verdict-specific deterministic gates.
    if dossier.verdict == "ADOPT_IMMEDIATELY":
        if t.license in ("", "unknown", "UNKNOWN", "none"):
            raise DossierError(
                "ADOPT_IMMEDIATELY requires a known upstream license "
                "(attribution hygiene)"
            )
        if dossier.surgical_extraction.full_repo_vending_prohibited is not True:
            raise DossierError("adoption still requires surgical extraction")
    if dossier.verdict == "REJECT" and not w.prohibited_practices:
        raise DossierError("a REJECT verdict must document the prohibited practices")
    if dossier.verdict == "EXTRACT_PATTERNS_ONLY" and not a.reusable_components:
        raise DossierError("EXTRACT_PATTERNS_ONLY must list reusable components")


# ---------------------------------------------------------------------------
# 4-Phase methodology — typed pipeline with per-phase validators
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PhaseEvidence:
    """Structured evidence produced by one methodology phase."""

    phase: str
    findings: tuple[str, ...]
    artifact: str = ""


def validate_phase_evidence(evidence: PhaseEvidence) -> None:
    """Per-phase fail-closed gates (zero-hype truth)."""
    if evidence.phase not in PHASES:
        raise PhaseError(f"unknown phase {evidence.phase!r}")
    if not evidence.findings:
        raise PhaseError(f"{evidence.phase} produced no findings")
    if evidence.phase == PHASE_1_EXTRACTION:
        joined = " ".join(evidence.findings).lower()
        if any(m in joined for m in ("marketing", "landing page only")):
            raise PhaseError(
                "Phase 1 must extract manifests/contracts/runtime truth — "
                "marketing-only evidence is rejected (zero-hype)"
            )
    if evidence.phase == PHASE_4_RFC and not evidence.artifact:
        raise PhaseError("Phase 4 (RFC) must emit the standardized dossier artifact")


def run_methodology(evidence: tuple[PhaseEvidence, ...]) -> str:
    """Validate the full 4-phase chain in order; return the RFC artifact."""
    if tuple(e.phase for e in evidence) != PHASES:
        raise PhaseError(f"phases must run in order {PHASES}")
    for step in evidence:
        validate_phase_evidence(step)
    return evidence[-1].artifact


# ---------------------------------------------------------------------------
# MCP tool reference core — scout_analyze_repository (offline, deterministic)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoutInputs:
    """Structured inputs for the scout_analyze_repository core.

    The tower adapter fills these from live fetches; the core itself never
    touches the network.
    """

    repository: str
    license: str = "unknown"
    manifest_yaml: str = ""
    manifest_json: str = ""
    file_tree: tuple[str, ...] = ()
    readme_headline: str = ""


def scout_analyze_repository(inputs: ScoutInputs) -> EcosystemDossier:
    """Build a fail-closed dossier skeleton from structured evidence.

    Extraction (Phase 1) truth comes from manifests and the file tree —
    never from the marketing headline. Raises DossierError when mandatory
    runtime facts are missing.
    """
    if not inputs.repository:
        raise DossierError("scout_analyze_repository requires a repository")
    if not inputs.manifest_yaml and not inputs.manifest_json:
        raise DossierError(
            "Phase 1 requires a package manifest (manifest_yaml or "
            "manifest_json) — zero-hype truth, not landing pages"
        )
    if not inputs.file_tree:
        raise DossierError("Phase 1 requires the file tree for runtime graph")

    tech_stack: list[str] = []
    runtime_notes: list[str] = []
    if inputs.manifest_json:
        try:
            manifest = json.loads(inputs.manifest_json)
        except json.JSONDecodeError as exc:
            raise DossierError(f"manifest_json is not valid JSON: {exc}") from exc
        deps = manifest.get("dependencies") or {}
        dev_deps = manifest.get("devDependencies") or {}
        tech_stack.append(f"node:{manifest.get('engines', {}).get('node', 'unpinned')}")
        tech_stack.extend(f"dep:{name}" for name in sorted(deps)[:20])
        if dev_deps:
            runtime_notes.append(f"{len(dev_deps)} devDependencies (build-only)")
    if inputs.manifest_yaml:
        for line in inputs.manifest_yaml.splitlines():
            stripped = line.strip()
            if stripped.startswith("- ") and stripped[2:]:
                tech_stack.append(f"py:{stripped[2:].split('==')[0]}")

    if not tech_stack:
        raise DossierError("manifest parsed to an empty tech stack — refuse to guess")

    heavy = [
        d
        for d in tech_stack
        if any(marker in d for marker in ("java", "jvm", "cargo", "rustc", "ghidra"))
    ]

    return EcosystemDossier(
        target=Target(
            repository=inputs.repository,
            license=inputs.license,
            tech_stack=tuple(tech_stack),
            core_purpose=inputs.readme_headline or "core purpose extracted upstream",
        ),
        comparative_analysis=ComparativeAnalysis(
            superior_capabilities=(
                "external runtime strengths recorded during Phase 2 dissection",
            ),
            supremeai_advantages=(
                "zero-bloat satellite doctrine; zero-admin self-healing loop",
            ),
            token_and_resource_impact=(
                f"file tree shows {len(inputs.file_tree)} entries; "
                + (
                    f"heavy runtime deps detected: {heavy}"
                    if heavy
                    else "no heavy runtime deps detected"
                )
            ),
        ),
        surgical_extraction=SurgicalExtraction(
            exact_components_needed=(
                "Gold Pearl component identified in Phase 2 — 20-100 line slice",
            ),
            adaptation_blueprint=(
                "Transcribe the Gold Pearl natively in python with "
                "fail-closed error handling; zero new dependencies."
            ),
            full_repo_vending_prohibited=True,
        ),
        actionable_takeaways=ActionableTakeaways(
            architectural_patterns=("pattern recorded in Phase 2",),
            reusable_components=("component recorded in Phase 2",),
            target_satellites=(
                SatelliteAction(
                    satellite=CANONICAL_SATELLITES[0],
                    action_type="replicate_pattern",
                    rationale="skeleton dossier — route after human review",
                ),
            ),
        ),
        watchouts_and_risks=WatchoutsAndRisks(
            anti_patterns=("wholesale vendoring",),
            security_or_compliance_concerns=(
                "license verification pending — do not adopt before review",
            ),
            prohibited_practices=("blind adoption of hype",),
        ),
        verdict="MONITOR",
    )


# ---------------------------------------------------------------------------
# Markdown artifact export
# ---------------------------------------------------------------------------


def _bullets(items: tuple[str, ...]) -> str:
    return "\n".join(f"- {item}" for item in items)


def render_dossier_markdown(dossier: EcosystemDossier) -> str:
    """Standard SupremeAI artifact format (issue #497 criterion 5)."""
    validate_dossier(dossier)
    a = dossier.actionable_takeaways
    routing = "\n".join(
        f"- **{s.satellite}** — `{s.action_type}`: {s.rationale}"
        for s in a.target_satellites
    )
    return (
        f"# Ecosystem Dossier — {dossier.target.repository}\n\n"
        f"**Verdict:** `{dossier.verdict}` · **License:** {dossier.target.license}\n\n"
        f"## Target\n- Core purpose: {dossier.target.core_purpose}\n"
        f"- Tech stack:\n{_bullets(dossier.target.tech_stack)}\n\n"
        f"## Comparative Analysis\n"
        f"### They are better at (ওরা আমাদের থেকে কোথায় বেটার)\n"
        f"{_bullets(dossier.comparative_analysis.superior_capabilities)}\n\n"
        f"### SupremeAI advantages\n"
        f"{_bullets(dossier.comparative_analysis.supremeai_advantages)}\n\n"
        f"- Token & resource impact: "
        f"{dossier.comparative_analysis.token_and_resource_impact}\n\n"
        f"## Surgical Extraction (কতটুকু দরকার / কীভাবে দরকার)\n"
        f"{_bullets(dossier.surgical_extraction.exact_components_needed)}\n\n"
        f"**Blueprint:** {dossier.surgical_extraction.adaptation_blueprint}\n\n"
        f"**Full-repo vending prohibited:** "
        f"{dossier.surgical_extraction.full_repo_vending_prohibited}\n\n"
        f"```\n{provenance_header(dossier.target.repository, dossier.target.license)}\n"
        f"```\n\n"
        f"## Actionable Takeaways\n"
        f"- Architectural patterns:\n{_bullets(a.architectural_patterns)}\n"
        f"- Reusable components:\n{_bullets(a.reusable_components)}\n"
        f"- Satellite routing:\n{routing}\n\n"
        f"## Watchouts & Risks (কী করা যাবে না / ঝুঁকি)\n"
        f"- Anti-patterns:\n{_bullets(dossier.watchouts_and_risks.anti_patterns)}\n"
        f"- Security/compliance:\n"
        f"{_bullets(dossier.watchouts_and_risks.security_or_compliance_concerns)}\n"
        f"- Prohibited practices:\n"
        f"{_bullets(dossier.watchouts_and_risks.prohibited_practices)}\n"
    )


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _valid_dossier(**overrides: Any) -> EcosystemDossier:
    parts: dict[str, Any] = {
        "target": Target(
            repository="example/org-repo",
            license="MIT",
            tech_stack=("node:24", "dep:zod"),
            core_purpose="reverse-engineering evidence ledger",
        ),
        "comparative_analysis": ComparativeAnalysis(
            superior_capabilities=("streaming pagination under 10 MiB frames",),
            supremeai_advantages=("zero-dep python runtime",),
            token_and_resource_impact="30% token reduction on ledger dumps",
        ),
        "surgical_extraction": SurgicalExtraction(
            exact_components_needed=("EvidenceRecord interface + sha256 fingerprint",),
            adaptation_blueprint=(
                "Transcribe natively in python with "
                "fail-closed errors; zero dependencies."
            ),
            full_repo_vending_prohibited=True,
        ),
        "actionable_takeaways": ActionableTakeaways(
            architectural_patterns=("evidence ledger",),
            reusable_components=("EvidenceRecord record type",),
            target_satellites=(
                SatelliteAction(
                    satellite="supremeai-mcp-control-plane",
                    action_type="replicate_pattern",
                    rationale="ledger parity with tower tooling",
                ),
            ),
        ),
        "watchouts_and_risks": WatchoutsAndRisks(
            anti_patterns=("wholesale vendoring",),
            security_or_compliance_concerns=("MIT attribution mandatory",),
            prohibited_practices=("blind hype adoption",),
        ),
        "verdict": "EXTRACT_PATTERNS_ONLY",
    }
    parts.update(overrides)
    return EcosystemDossier(**parts)


def self_test() -> bool:
    # Happy path.
    d = _valid_dossier()
    validate_dossier(d)
    md = render_dossier_markdown(d)
    assert "কতটুকু দরকার" in md and "কীভাবে দরকার" in md
    assert "adapted from: github.com/example/org-repo" in md and "MIT" in md
    assert d.verdict == "EXTRACT_PATTERNS_ONLY"

    # Fail-closed matrix.
    bad_cases = (
        _valid_dossier(verdict="SHIP_IT"),
        _valid_dossier(target=replace_target(repository="")),
        _valid_dossier(
            comparative_analysis=replace_comparative(superior_capabilities=())
        ),
        _valid_dossier(
            comparative_analysis=replace_comparative(supremeai_advantages=())
        ),
        _valid_dossier(
            surgical_extraction=replace_surgical(full_repo_vending_prohibited=False)
        ),
        _valid_dossier(
            surgical_extraction=replace_surgical(exact_components_needed=())
        ),
        _valid_dossier(surgical_extraction=replace_surgical(adaptation_blueprint="")),
        _valid_dossier(
            surgical_extraction=replace_surgical(
                adaptation_blueprint="git clone the whole repository"
            )
        ),
        _valid_dossier(actionable_takeaways=replace_takeaways(target_satellites=())),
        _valid_dossier(
            actionable_takeaways=replace_takeaways(
                target_satellites=(SatelliteAction("sat", "fork_it", "why"),)
            )
        ),
        _valid_dossier(watchouts_and_risks=replace_watchouts(anti_patterns=())),
        _valid_dossier(
            watchouts_and_risks=replace_watchouts(security_or_compliance_concerns=())
        ),
        _valid_dossier(watchouts_and_risks=replace_watchouts(prohibited_practices=())),
        _valid_dossier(
            verdict="ADOPT_IMMEDIATELY", target=replace_target(license="unknown")
        ),
        _valid_dossier(
            verdict="REJECT",
            watchouts_and_risks=replace_watchouts(prohibited_practices=()),
        ),
    )
    for bad in bad_cases:
        try:
            validate_dossier(bad)
            raise SystemExit(f"dossier gate failed open: {bad!r}")
        except DossierError:
            pass

    # Gold Pearl budget.
    validate_gold_pearl_budget(GOLD_PEARL_MIN_LINES)
    validate_gold_pearl_budget(GOLD_PEARL_MAX_LINES)
    for off in (GOLD_PEARL_MIN_LINES - 1, GOLD_PEARL_MAX_LINES + 1):
        try:
            validate_gold_pearl_budget(off)
            raise SystemExit("gold pearl budget failed open")
        except DossierError:
            pass

    # Provenance hygiene.
    assert "github.com/example/org-repo" in provenance_header("example/org-repo", "MIT")
    try:
        provenance_header("", "MIT")
        raise SystemExit("provenance failed open")
    except DossierError:
        pass

    # Methodology pipeline.
    chain = tuple(
        PhaseEvidence(
            p, ("finding",), artifact="dossier.md" if p == PHASE_4_RFC else ""
        )
        for p in PHASES
    )
    assert run_methodology(chain) == "dossier.md"
    for broken in (
        tuple(PhaseEvidence(p, ("f",)) for p in PHASES[1:]),
        tuple(PhaseEvidence(p, ("f",)) for p in reversed(PHASES)),
        (
            PhaseEvidence(PHASE_1_EXTRACTION, ("marketing landing page only",)),
            PhaseEvidence(PHASE_2_DISSECTION, ("f",)),
            PhaseEvidence(PHASE_3_AUDIT, ("f",)),
            PhaseEvidence(PHASE_4_RFC, ("f",), artifact="d.md"),
        ),
        (
            PhaseEvidence(PHASE_1_EXTRACTION, ("f",)),
            PhaseEvidence(PHASE_2_DISSECTION, ("f",)),
            PhaseEvidence(PHASE_3_AUDIT, ("f",)),
            PhaseEvidence(PHASE_4_RFC, ("f",)),
        ),
    ):
        try:
            run_methodology(broken)  # type: ignore[arg-type]
            raise SystemExit(f"methodology gate failed open: {broken!r}")
        except PhaseError:
            pass

    # MCP core: manifest-driven, fail-closed.
    d2 = scout_analyze_repository(
        ScoutInputs(
            repository="example/org-repo",
            license="MIT",
            manifest_json='{"dependencies": {"zod": "^3"}, "engines": {"node": "24"}}',
            file_tree=("src/index.ts", "src/ledger.ts"),
            readme_headline="evidence ledger",
        )
    )
    assert d2.target.tech_stack[0] == "node:24"
    assert any(dep == "dep:zod" for dep in d2.target.tech_stack)
    assert d2.verdict == "MONITOR"
    validate_dossier(d2)
    for broken_inputs in (
        ScoutInputs(repository=""),
        ScoutInputs(repository="x"),
        ScoutInputs(repository="x", manifest_yaml="a: 1"),
        ScoutInputs(repository="x", manifest_yaml="- fastapi", file_tree=()),
        ScoutInputs(repository="x", manifest_json="{bad json", file_tree=("a",)),
        ScoutInputs(repository="x", manifest_yaml="a: 1", file_tree=("a",)),
    ):
        try:
            scout_analyze_repository(broken_inputs)
            raise SystemExit(f"scout core failed open: {broken_inputs!r}")
        except DossierError:
            pass

    return True


def replace_target(**kw: Any) -> Target:
    base = Target(
        repository="example/org-repo",
        license="MIT",
        tech_stack=("node:24",),
        core_purpose="p",
    )
    return Target(**{**base.__dict__, **kw})


def replace_comparative(**kw: Any) -> ComparativeAnalysis:
    base = ComparativeAnalysis(("s",), ("a",), "t")
    return ComparativeAnalysis(**{**base.__dict__, **kw})


def replace_surgical(**kw: Any) -> SurgicalExtraction:
    base = SurgicalExtraction(("c",), "native python blueprint", True)
    return SurgicalExtraction(**{**base.__dict__, **kw})


def replace_takeaways(**kw: Any) -> ActionableTakeaways:
    base = ActionableTakeaways(
        ("p",), ("r",), (SatelliteAction("supremeai-open", "replicate_pattern", "why"),)
    )
    return ActionableTakeaways(**{**base.__dict__, **kw})


def replace_watchouts(**kw: Any) -> WatchoutsAndRisks:
    base = WatchoutsAndRisks(("a",), ("s",), ("p",))
    return WatchoutsAndRisks(**{**base.__dict__, **kw})


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("SELF-TEST OK: ecosystem_scout_reference")
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
