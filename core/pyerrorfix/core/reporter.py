"""Reporters: console, JSON, SARIF, Markdown."""

from __future__ import annotations

import json
import sys

from pyerrorfix.core.issue import ScanResult, Severity


def to_json(result: ScanResult) -> str:
    return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)


def to_markdown(result: ScanResult) -> str:
    lines: list[str] = ["# pyerrorfix report", ""]
    s = result.summary
    lines.append(
        f"**Summary:** {s['total']} issue(s) — {s['errors']} error(s), "
        f"{s['warnings']} warning(s), {s['info']} info — {s['fixable']} auto-fixable."
    )
    lines.append("")
    if not result.issues:
        lines.append("✅ No issues found.")
        return "\n".join(lines)
    by_cat: dict[str, list] = {}
    for i in result.issues:
        by_cat.setdefault(i.category.value, []).append(i)
    for cat, issues in sorted(by_cat.items()):
        lines.append(f"## {cat} ({len(issues)})")
        lines.append("")
        for i in issues:
            sev_badge = {
                Severity.CRITICAL: "🔴",
                Severity.ERROR: "🟠",
                Severity.WARNING: "🟡",
                Severity.INFO: "🔵",
            }.get(i.severity, "⚪")
            fix_badge = "✅ fixable" if i.fixable else "—"
            lines.append(f"- {sev_badge} **{i.title}** `{i.code}` (line {i.line}) [{fix_badge}]")
            lines.append(f"  - {i.message}")
            if i.fix_description:
                lines.append(f"  - _Fix:_ {i.fix_description}")
        lines.append("")
    return "\n".join(lines)


def to_sarif(result: ScanResult) -> str:
    """Static Analysis Results Interchange Format v2.1.0 (GitHub native)."""
    rules: dict[str, dict] = {}
    results: list[dict] = []
    for i in result.issues:
        if i.rule_id not in rules:
            rules[i.rule_id] = {
                "id": i.rule_id,
                "name": i.title[:60],
                "shortDescription": {"text": i.title},
                "fullDescription": {"text": i.message},
                "helpUri": "https://github.com/SaifulHaqueNiloy/supremeai",
                "defaultConfiguration": {"level": _sarif_level(i.severity)},
                "properties": {
                    "category": i.category.value,
                    "error-code": i.code,
                    "fixable": i.fixable,
                },
            }
        loc_line = i.line if i.line > 0 else 1
        results.append(
            {
                "ruleId": i.rule_id,
                "level": _sarif_level(i.severity),
                "message": {"text": i.message},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": i.file},
                            "region": {
                                "startLine": loc_line,
                                "startColumn": max(i.col, 1),
                                "endLine": i.end_line or loc_line,
                                "endColumn": max(i.end_col, 1),
                            },
                        },
                    }
                ],
                "fixes": [
                    {
                        "description": {"text": i.fix_description or "see suggestion"},
                        "artifactChanges": [
                            {
                                "artifactLocation": {"uri": i.file},
                                "replacements": [
                                    {
                                        "deletedRegion": {
                                            "startLine": loc_line,
                                            "startColumn": max(i.col, 1),
                                            "endLine": i.end_line or loc_line,
                                            "endColumn": max(i.end_col, 1),
                                        },
                                        "insertedContent": {"text": i.suggestion or ""},
                                    }
                                ],
                            }
                        ],
                    }
                ]
                if i.fixable and i.suggestion
                else [],
            }
        )
    doc = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "pyerrorfix",
                        "version": "1.0.0",
                        "informationUri": "https://github.com/SaifulHaqueNiloy/supremeai",
                        "rules": list(rules.values()),
                    },
                },
                "results": results,
            }
        ],
    }
    return json.dumps(doc, indent=2, ensure_ascii=False)


def to_console(result: ScanResult, stream=None) -> None:
    stream = stream or sys.stdout
    s = result.summary
    if not result.issues:
        stream.write("✅ No issues found.\n")
        return
    for i in result.issues:
        sev = {
            Severity.CRITICAL: "CRIT",
            Severity.ERROR: "ERR ",
            Severity.WARNING: "WARN",
            Severity.INFO: "INFO",
        }.get(i.severity, "????")
        loc = f"{i.file}:{i.line}:{i.col}"
        fix = " [fixable]" if i.fixable else ""
        stream.write(f"{sev}  {loc:<40}  {i.code:<22}  {i.title}{fix}\n")
        stream.write(f"       {i.message}\n")
        if i.fix_description:
            stream.write(f"       → fix: {i.fix_description}\n")
    stream.write(
        f"\n{s['total']} issue(s): {s['errors']} error, {s['warnings']} warn, "
        f"{s['info']} info — {s['fixable']} fixable.\n"
    )


def _sarif_level(sev: Severity) -> str:
    return {
        Severity.CRITICAL: "error",
        Severity.ERROR: "error",
        Severity.WARNING: "warning",
        Severity.INFO: "note",
    }.get(sev, "warning")
