"""deployments/tests/test_deployment_integrity.py — deployment artifact integrity (issue #339).

bridge v2 single-target routing: colocated at deployments/tests/ so the order
targets exactly one federation repo. Canonical root: deployments/ artifacts
(render.yaml, secrets-inventory.json, Dockerfile, README.md).

Offline pytest covering:
  AC1  manifests validate WITHOUT hardcoded secrets — env keys cross-reference
       the secret inventory fail-closed; no value-shaped literals anywhere
  AC2  Render Blueprint + Dockerfile structural invariants
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

DEPLOYMENTS = Path(__file__).resolve().parents[1]
if not DEPLOYMENTS.is_dir():
    raise ImportError("deployments/ artifacts not found near " + str(Path(__file__)))


def _simple_yaml(text: str) -> dict:
    """Minimal YAML subset parser for the blueprint (no external deps)."""
    result: dict = {}
    stack = [(-1, result)]
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip() if not raw.lstrip().startswith("#") else ""
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if stripped.startswith("- "):
            item: dict = {}
            if not isinstance(parent, list):
                parent = []
                stack[-1][1].update({list.__name__: parent}) if False else None
            parent.append(item)
            kv = stripped[2:]
            if ":" in kv:
                k, _, v = kv.partition(":")
                item[k.strip()] = v.strip()
            stack.append((indent, item))
            continue
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            key, value = key.strip(), value.strip()
            if value == "":
                child: dict = {}
                parent[key] = child
                stack.append((indent, child))
            else:
                parent[key] = value.strip('"')
    return result


@pytest.fixture(scope="module")
def manifest_text() -> str:
    return (DEPLOYMENTS / "render.yaml").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def inventory() -> dict:
    return json.loads((DEPLOYMENTS / "secrets-inventory.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# AC1: no hardcoded secrets; manifest/inventory cross-reference
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# AC1: no hardcoded secrets; manifest/inventory cross-reference
# ---------------------------------------------------------------------------

SECRETISH = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.I)


def test_render_blueprint_declares_every_env_key(manifest_text, inventory):
    declared = [
        ln.split("key:")[1].strip()
        for ln in manifest_text.splitlines()
        if "- key:" in ln
    ]
    inv_keys = {s["key"] for s in inventory["secrets"]}
    # infrastructure knobs (non-secret) are allowed un-inventoried
    allowed_free = {"PYTHON_VERSION", "SUPREMEAI_ROUTING_POLICY"}
    for key in declared:
        assert key in inv_keys or key in allowed_free, f"env key {key} missing from secret inventory (fail-closed)"


def test_render_blueprint_has_no_literal_secret_values(manifest_text):
    for i, line in enumerate(manifest_text.splitlines()):
        if "- key:" in line or line.strip().startswith("#"):
            continue
        if ":" in line and SECRETISH.search(line):
            key, _, value = line.partition(":")
            if value.strip().strip('"') not in ("", "sync: false") and value.strip() != "false":
                # value: false (sync) is fine; a literal string on a secretish key is not
                assert not value.strip(), f"line {i+1}: literal value on secretish key: {line!r}"


def test_every_secret_env_var_uses_sync_false_or_generate(manifest_text, inventory):
    lines = manifest_text.splitlines()
    for secret in inventory["secrets"]:
        key = secret["key"]
        idx = next((i for i, ln in enumerate(lines) if f"key: {key}" in ln), None)
        assert idx is not None, f"inventory secret {key} not declared in blueprint"
        context = "\n".join(lines[idx : idx + 2])
        assert "sync: false" in context or "generateValue" in context, (
            f"{key} must ride the dashboard (sync:false), never a committed value"
        )


def test_inventory_has_no_value_shaped_material(inventory):
    for secret in inventory["secrets"]:
        assert set(secret) == {"key", "owner", "purpose", "set_in"}
        for field_value in secret.values():
            # 32+ char base64/hex blobs have no business in an inventory
            assert not re.search(r"[A-Za-z0-9+/=]{32,}", str(field_value)), "value-shaped material in inventory"


def test_inventory_references_are_documented(inventory):
    assert inventory["inventory_version"] == "secrets-inventory/1"
    for secret in inventory["secrets"]:
        assert secret["set_in"] == "render-dashboard", "secret material must live in the dashboard"


# ---------------------------------------------------------------------------
# AC2: blueprint + Dockerfile structural invariants
# ---------------------------------------------------------------------------

def test_blueprint_services_have_health_checks(manifest_text):
    assert "healthCheckPath: /healthz" in manifest_text, "web service must expose the credential-free probe"


def test_dockerfile_invariants():
    df = (DEPLOYMENTS / "Dockerfile").read_text(encoding="utf-8")
    instructions = [ln for ln in df.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert not any(ln.strip() == "USER root" for ln in instructions), "must not run as root"
    assert any(ln.startswith("USER 10001") or ln.startswith("USER ") for ln in instructions), "explicit non-root USER required"
    assert any(ln.startswith("HEALTHCHECK") for ln in instructions), "HEALTHCHECK required"
    assert "/healthz" in df, "healthcheck must target the credential-free probe"
    assert not re.search(r"^(ADD|COPY)\s+.*\.env", df, re.M), "dot-env files must never enter the image"
    assert not re.search(r"^(ADD|COPY)\s+.*\.git", df, re.M), ".git must never enter the image"
    assert "python:3.12-slim" in df, "pinned base image"
    assert not re.search(r"^FROM\s+\S*(latest|:)$", df, re.M), "no floating tags in FROM"


def test_dockerfile_starts_from_the_gateway_package():
    df = (DEPLOYMENTS / "Dockerfile").read_text(encoding="utf-8")
    assert "gateway/requirements.txt" in df
    assert "gateway.serve:app" in df



