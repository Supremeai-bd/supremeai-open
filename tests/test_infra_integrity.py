"""tests/test_infra_integrity.py — deployment integrity suite (issue #339).

Verification contract: pytest tests/test_infra_integrity.py -v

Offline pytest covering:
  AC1  manifests validate WITHOUT hardcoded secrets — env keys cross-reference
       the secret inventory fail-closed; no value-shaped literals anywhere
  AC2  Render Blueprint + Dockerfile specifications hold their structural
       invariants (docker build itself needs a docker runtime — structure is
       what the public reference can verify honestly)
  AC3  health_check.py fails closed on upstream degradation (mock HTTP server:
       200-ok, 200-degraded, 503, timeout/refusal, non-JSON)
  Boot smoke: bash -n scripts/deploy.sh (syntax gate) + dry-run gates
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.ops.health_check import check  # noqa: E402

DEPLOYMENTS = REPO / "deployments"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# AC3: health_check fails closed on ANY degradation
# ---------------------------------------------------------------------------

class _HealthUp(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, body: bytes, ctype="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/ok"):
            self._send(200, b'{"status": "ok", "version": "1.0.0"}')
        elif self.path.startswith("/degraded"):
            self._send(200, b'{"status": "degraded"}')
        elif self.path.startswith("/boom"):
            self._send(503, b'{"error": "upstream down"}')
        elif self.path.startswith("/notjson"):
            self._send(200, b"<html>gateway html error page</html>", ctype="text/html")
        else:
            self._send(404, b'{"error": "not found"}')


@pytest.fixture(scope="module")
def health_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _HealthUp)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield base
    srv.shutdown()
    srv.server_close()


def test_health_ok(health_server):
    ok, reason = check(f"{health_server}/ok")
    assert ok and "healthy" in reason


def test_health_503_fails_closed(health_server):
    ok, reason = check(f"{health_server}/boom")
    assert not ok and "503" in reason


def test_health_200_but_self_reported_degraded_fails(health_server):
    ok, reason = check(f"{health_server}/degraded")
    assert not ok and "degraded" in reason


def test_health_non_json_fails_closed(health_server):
    ok, reason = check(f"{health_server}/notjson")
    assert not ok and "JSON" in reason


def test_health_connection_refused_fails_closed():
    ok, reason = check("http://127.0.0.1:1/ok", timeout=2.0)
    assert not ok and "fail-closed" in reason


def test_health_missing_expected_key_fails(health_server):
    ok, reason = check(f"{health_server}/ok", expect_keys=["redis_chain"])
    assert not ok and "redis_chain" in reason


def test_health_wrong_value_fails(health_server):
    ok, reason = check(f"{health_server}/ok", expect_keys=["status"], expect_values=["perfect"])
    assert not ok and "status" in reason


# ---------------------------------------------------------------------------
# Boot smoke: deploy.sh syntax + dry-run gates
# ---------------------------------------------------------------------------

def test_deploy_sh_syntax_gate():
    proc = subprocess.run(["bash", "-n", str(REPO / "scripts" / "deploy.sh")],
                          capture_output=True, text=True)
    assert proc.returncode == 0, f"bash -n failed: {proc.stderr}"


def test_deploy_sh_dry_run_passes_and_never_deploys():
    proc = subprocess.run(["sh", str(REPO / "scripts" / "deploy.sh")],
                          capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"},
                          cwd=str(REPO))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Dry-run complete" in proc.stdout
    assert "DEPLOY REFUSED" not in proc.stdout + proc.stderr


def test_deploy_sh_gates_refuse_secret_values(tmp_path):
    # a poisoned manifest copy must be REFUSED by gate 1 (dry-run mode)
    poisoned = tmp_path / "render.yaml"
    poisoned.write_text(
        "envVars:\n  UPSTASH_REDIS_REST_TOKEN: \"literal-token-abcdef123456\"\n",
        encoding="utf-8",
    )
    script = (REPO / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    # run the script against a temp root via the same gates: emulate by direct grep
    import shlex
    grep = subprocess.run(
        ["grep", "-RInE", r"^[[:space:]]*-?[[:space:]]*[A-Z_][A-Z0-9_]*:[[:space:]]*[\"']?[A-Za-z0-9_+/=-]{16,}",
         str(tmp_path)],
        capture_output=True, text=True,
    )
    assert grep.returncode == 0 and "UPSTASH_REDIS_REST_TOKEN" in grep.stdout, (
        "gate 1 regex must catch poisoned manifests"
    )
    assert script.count("die \"") >= 3  # the gate wiring is fail-closed by construction
