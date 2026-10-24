"""core/self_evolution/red_team_gate.py — Adversarial red-team gate for agent breeding (Way 30).

বাংলা: agent-breeding পাইপলাইনের গেট — বংশোদ্ভূত agent কনফিগ/প্ল্যান রুব্রিকের
অ্যাডভারসারিয়াল চেক পাস না করলে এগোবে না (fail-closed, 100% specificity লক্ষ্য)।

Plan contract (Way 30, Infinity adversarial_redteam):
- red-team rubric over breeding candidates:
    * vague quantifiers ("some", "lots", "basically", "a lot of") in plans
    * missing rollback / no revert contract
    * retired or unknown model references
    * scope creep beyond the declared slice
- Gate verdict is deterministic and auditable (findings carry rule ids).
- Importable WITHOUT the breeding pipeline so CI and evaluators can run it standalone.

Integration (documented, P3-safe — no forced edit of agent_breeder.py):
    from core.self_evolution.red_team_gate import RedTeamGate
    verdict = RedTeamGate().evaluate(candidate=plan_text, model=model_id)
    if not verdict.passed:
        quarantine(candidate_id, verdict.findings)

Local test:
    pytest tests/test_red_team_gate.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Known-retired / hallucination-prone model references (extend via PR with citation).
RETIRED_MODELS: tuple[str, ...] = (
    "gpt-3.5-turbo-0301",
    "gpt-4-0314",
    "gpt-4-32k",
    "claude-1",
    "claude-2.0",
    "claude-instant",
    "text-davinci-003",
)

# Vague quantifiers that make a breeding plan unauditable (plan Way 30 rubric).
_VAGUE_QUANTIFIERS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(some|lots? of|a lot of|basically|stuff|things|various|several)\b", re.I),
    re.compile(r"\b(maybe|probably|should work|i think|hopefully)\b", re.I),
)

_ROLLBACK_HINTS = ("rollback", "revert", "roll back", "restore", "undo", "previous version")
_SCOPE_HINTS = ("scope:", "single file", "one file", "atomic slice", "in scope", "within scope")

_MAX_FINDINGS = 50  # bound the report


@dataclass(frozen=True, slots=True)
class Finding:
    rule: str
    severity: str  # "blocker" | "warning"
    detail: str


@dataclass(frozen=True, slots=True)
class RedTeamVerdict:
    passed: bool
    findings: tuple[Finding, ...] = field(default=())
    checked_rules: tuple[str, ...] = field(default=())

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "findings": [
                {"rule": f.rule, "severity": f.severity, "detail": f.detail}
                for f in self.findings
            ],
            "checked_rules": list(self.checked_rules),
        }


class RedTeamGate:
    """Deterministic adversarial rubric over a breeding candidate's plan/config.

    বাংলা: vague quantifier / rollback-হীনতা / retired model / scope-creep —
    চার নিয়মের গেট; একটি blocker থাকলেই fail।
    """

    RULES = ("RT-01 vague-quantifiers", "RT-02 missing-rollback", "RT-03 retired-model", "RT-04 scope-creep")

    def evaluate(
        self,
        candidate: str,
        *,
        model: str | None = None,
        allow_retired: bool = False,
    ) -> RedTeamVerdict:
        findings: list[Finding] = []
        text = (candidate or "").strip()
        if not text:
            findings.append(
                Finding("RT-00 empty-plan", "blocker", "Candidate plan is empty — cannot audit.")
            )
            return RedTeamVerdict(False, tuple(findings), self.RULES)

        # RT-01: vague quantifiers make fitness claims unauditable.
        for pattern in _VAGUE_QUANTIFIERS:
            m = pattern.search(text)
            if m:
                findings.append(
                    Finding(
                        "RT-01 vague-quantifiers",
                        "warning",
                        f"Vague quantifier {m.group(0)!r} — replace with measurable terms.",
                    )
                )

        # RT-02: no rollback contract → regression cannot be reverted (P3 violation).
        if not any(h in text.lower() for h in _ROLLBACK_HINTS):
            findings.append(
                Finding(
                    "RT-02 missing-rollback",
                    "blocker",
                    "No rollback/revert contract found in the plan.",
                )
            )

        # RT-03: retired / unknown model references (optionally tolerated).
        if model and not allow_retired:
            mlow = model.lower()
            for retired in RETIRED_MODELS:
                if retired in mlow or retired in text.lower():
                    findings.append(
                        Finding(
                            "RT-03 retired-model",
                            "blocker",
                            f"References retired model {retired!r}.",
                        )
                    )
                    break

        # RT-04: scope creep signals — multi-domain rewrites without a slice claim.
        if not any(h in text.lower() for h in _SCOPE_HINTS):
            domain_words = len(re.findall(r"\b(refactor|rewrite|redesign|migrate all|entire system|whole codebase)\b", text, re.I))
            if domain_words >= 2:
                findings.append(
                    Finding(
                        "RT-04 scope-creep",
                        "blocker",
                        "Plan proposes broad multi-domain rewrites without an atomic-slice claim (P7).",
                    )
                )

        blockers = [f for f in findings if f.severity == "blocker"]
        return RedTeamVerdict(
            passed=not blockers,
            findings=tuple(findings[:_MAX_FINDINGS]),
            checked_rules=self.RULES,
        )
