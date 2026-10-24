"""Configuration loading.

A config is simply a map of ``rule_id -> {enabled: bool, severity: str}``.
Default ruleset is builtin (see :func:`default_config`) so the tool works with
zero configuration. Users may override with ``.pyerrorfix.json`` (always
supported) or ``.pyerrorfix.yaml`` (requires PyYAML).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pyerrorfix.core.issue import Severity


def default_config() -> dict[str, dict[str, Any]]:
    """Builtin enabled-ruleset. Every rule on by default.

    Keys mirror the ``rule_id`` produced by detectors, so toggling a rule off
    here silences that exact detector finding everywhere.
    """
    return {
        # syntax
        "syntax-error": {"enabled": True, "severity": "error"},
        "indentation-error": {"enabled": True, "severity": "error"},
        "tab-error": {"enabled": True, "severity": "error"},
        # core python
        "undefined-name": {"enabled": True, "severity": "error"},
        "type-mismatch": {"enabled": True, "severity": "warning"},
        "possible-value-error": {"enabled": True, "severity": "warning"},
        "missing-attribute": {"enabled": True, "severity": "warning"},
        "index-out-of-range": {"enabled": True, "severity": "warning"},
        "missing-key": {"enabled": True, "severity": "warning"},
        "unbound-local": {"enabled": True, "severity": "error"},
        "zero-division": {"enabled": True, "severity": "error"},
        "not-implemented-stub": {"enabled": True, "severity": "warning"},
        "deep-recursion": {"enabled": True, "severity": "warning"},
        "assert-in-prod": {"enabled": True, "severity": "warning"},
        "overflow-risk": {"enabled": True, "severity": "warning"},
        "stop-iteration-explicit": {"enabled": True, "severity": "info"},
        "bare-raise": {"enabled": True, "severity": "warning"},
        # imports
        "missing-module": {"enabled": True, "severity": "error"},
        "missing-name-import": {"enabled": True, "severity": "error"},
        "circular-import-risk": {"enabled": True, "severity": "warning"},
        "wildcard-import": {"enabled": True, "severity": "warning"},
        "unused-import": {"enabled": True, "severity": "warning"},
        # files
        "hardcoded-path": {"enabled": True, "severity": "info"},
        "open-without-context": {"enabled": True, "severity": "warning"},
        "missing-path-exists-check": {"enabled": True, "severity": "warning"},
        "broad-except-io": {"enabled": True, "severity": "warning"},
        # asyncio
        "missing-await": {"enabled": True, "severity": "error"},
        "async-call-in-sync": {"enabled": True, "severity": "warning"},
        "blocking-call-in-async": {"enabled": True, "severity": "warning"},
        "unhandled-task-exception": {"enabled": True, "severity": "warning"},
        "event-loop-misuse": {"enabled": True, "severity": "warning"},
        # database
        "raw-sql-injection": {"enabled": True, "severity": "critical"},
        "missing-commit-rollback": {"enabled": True, "severity": "warning"},
        "n-plus-one-query": {"enabled": True, "severity": "info"},
        "missing-noresult-found": {"enabled": True, "severity": "warning"},
        # web/api
        "pydantic-validation-gap": {"enabled": True, "severity": "warning"},
        "broad-http-exception": {"enabled": True, "severity": "info"},
        "missing-response-model": {"enabled": True, "severity": "info"},
        "unhandled-route-exception": {"enabled": True, "severity": "warning"},
        # concurrency (NEW)
        "mutable-shared-state": {"enabled": True, "severity": "warning"},
        "lock-without-context": {"enabled": True, "severity": "warning"},
        "thread-unsafe-singleton": {"enabled": True, "severity": "warning"},
        # typing (NEW)
        "none-member-access": {"enabled": True, "severity": "warning"},
        "optional-without-check": {"enabled": True, "severity": "warning"},
        "missing-type-hint": {"enabled": True, "severity": "info"},
        # security (NEW)
        "hardcoded-secret": {"enabled": True, "severity": "critical"},
        "eval-exec": {"enabled": True, "severity": "critical"},
        "pickle-deserialize": {"enabled": True, "severity": "error"},
        "shell-injection": {"enabled": True, "severity": "critical"},
        "weak-hash": {"enabled": True, "severity": "warning"},
        # resources (NEW)
        "unclosed-resource": {"enabled": True, "severity": "warning"},
        "leaked-connection": {"enabled": True, "severity": "warning"},
        # deprecation (NEW)
        "deprecated-api": {"enabled": True, "severity": "warning"},
        "python2-construct": {"enabled": True, "severity": "warning"},
        # logging (NEW)
        "fstring-in-logging": {"enabled": True, "severity": "warning"},
        "broad-except": {"enabled": True, "severity": "warning"},
        "exception-not-logged": {"enabled": True, "severity": "info"},
        "print-in-production": {"enabled": True, "severity": "info"},
        # network & I/O (NEW — category 1 expanded)
        "missing-timeout": {"enabled": True, "severity": "warning"},
        "json-decode-uncaught": {"enabled": True, "severity": "warning"},
        "uncaught-connection-error": {"enabled": True, "severity": "warning"},
        # linter & code quality (NEW — category 2)
        "zip-without-strict": {"enabled": True, "severity": "warning"},
        "bool-compare-literal": {"enabled": True, "severity": "warning"},
        "nested-if-style": {"enabled": True, "severity": "info"},
        "ternary-style": {"enabled": True, "severity": "info"},
        "dead-mock": {"enabled": True, "severity": "warning"},
        "naming-convention-mismatch": {"enabled": True, "severity": "info"},
        # auth & security (NEW — category 7 expanded)
        "jwt-unverified": {"enabled": True, "severity": "critical"},
        "jwt-missing-algorithms": {"enabled": True, "severity": "warning"},
        "cors-wildcard-credentials": {"enabled": True, "severity": "critical"},
        "cors-wildcard": {"enabled": True, "severity": "warning"},
        "manual-auth-gate": {"enabled": True, "severity": "info"},
        # testing (NEW — category 10 expanded)
        "assert-without-message": {"enabled": True, "severity": "info"},
        "session-fixture-mutation": {"enabled": True, "severity": "warning"},
        "pytest.raises-without-match": {"enabled": True, "severity": "info"},
        # infrastructure & deployment (NEW — category 11)
        "docker-root-user": {"enabled": True, "severity": "warning"},
        "docker-missing-healthcheck": {"enabled": True, "severity": "info"},
        "docker-no-memory-limit": {"enabled": True, "severity": "warning"},
        "nginx-missing-proxy-timeout": {"enabled": True, "severity": "warning"},
        "nginx-wrong-backend-port": {"enabled": True, "severity": "warning"},
        "gunicorn-missing-workers": {"enabled": True, "severity": "warning"},
    }


def _coerce_severity(value: Any) -> str:
    if isinstance(value, str) and value.upper() in Severity.__members__:
        return Severity[value.upper()].value
    return str(value or "warning")


def load_config(path: str | os.PathLike[str] | None = None) -> dict[str, dict[str, Any]]:
    """Load config from ``path`` (json or yaml) falling back to defaults.

    If ``path`` is None, looks for ``.pyerrorfix.json`` / ``.pyerrorfix.yaml`` /
    ``.pyerrorfix.yml`` in CWD and parent dirs (up to 3 levels).
    """
    base = default_config()

    if path:
        p = Path(path)
        return _merge_file(base, p)

    # auto-discover
    cwd = Path.cwd()
    for d in [cwd, *cwd.parents[:3]]:
        for name in (".pyerrorfix.json", ".pyerrorfix.yaml", ".pyerrorfix.yml"):
            candidate = d / name
            if candidate.is_file():
                return _merge_file(base, candidate)
    return base


def _merge_file(base: dict, path: Path) -> dict[str, dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    data: Any
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError:
            # fall back: treat as json-ish; if that fails, ignore
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                return base
        else:
            data = yaml.safe_load(text)
    else:
        data = json.loads(text)

    if not isinstance(data, dict):
        return base

    rules = data.get("rules", data)
    if isinstance(rules, dict):
        for rule_id, cfg in rules.items():
            if not isinstance(cfg, dict):
                continue
            if rule_id not in base:
                base[rule_id] = {"enabled": True, "severity": "warning"}
            if "enabled" in cfg:
                base[rule_id]["enabled"] = bool(cfg["enabled"])
            if "severity" in cfg:
                base[rule_id]["severity"] = _coerce_severity(cfg["severity"])
    return base
