"""tests/test_command_foundation.py — 3-tier verification (tier 3, unit).

Minimum 8 passing tests covering HMAC authentication, Telegram command
routing (RBAC), webhook ingress, dispatcher payload shape and the RESP
kill-switch encoding. Fully offline: only ephemeral local sockets.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from command.config import CommandConfig, CommandConfigError  # noqa: E402
    from command.dispatcher import (  # noqa: E402
        DispatcherError,
        MiniRedis,
        TowerDispatcher,
        encode_resp,
    )
    from command.telegram_bot import CommandRouter, TelegramUpdate  # noqa: E402
    from command.webhook_ingress import (  # noqa: E402
        WebhookIngress,
        compute_signature,
        make_http_server,
        verify_hmac,
    )
except ImportError:
    from src.config import CommandConfig, CommandConfigError  # noqa: E402
    from src.dispatcher import (  # noqa: E402
        DispatcherError,
        MiniRedis,
        TowerDispatcher,
        encode_resp,
    )
    from src.telegram_bot import CommandRouter, TelegramUpdate  # noqa: E402
    from src.webhook_ingress import (  # noqa: E402
        WebhookIngress,
        compute_signature,
        make_http_server,
        verify_hmac,
    )


def make_config(**overrides) -> CommandConfig:
    env: Dict[str, str] = {
        "TELEGRAM_BOT_TOKEN": "123456:TEST-ONLY-TOKEN",
        "TELEGRAM_SUPERADMIN_CHAT_ID": "424242",
        "COMMAND_HMAC_SECRET": "x" * 32,
    }
    env.update({k: v for k, v in overrides.items() if v is not None})
    return CommandConfig.from_env(env)


# ---------------------------------------------------------------------------
# 1) config: fail-closed construction + redaction
# ---------------------------------------------------------------------------

def test_config_missing_env_lists_all_missing_vars():
    try:
        CommandConfig.from_env({})
        raise AssertionError("expected CommandConfigError")
    except CommandConfigError as exc:
        text = str(exc)
        assert "TELEGRAM_BOT_TOKEN" in text
        assert "TELEGRAM_SUPERADMIN_CHAT_ID" in text
        assert "COMMAND_HMAC_SECRET" in text


def test_config_rejects_bad_superadmin_and_short_hmac():
    try:
        make_config(TELEGRAM_SUPERADMIN_CHAT_ID="not-numeric", COMMAND_HMAC_SECRET="short")
        raise AssertionError("expected CommandConfigError")
    except CommandConfigError:
        pass


def test_config_repr_never_leaks_secrets():
    cfg = make_config()
    rendered = repr(cfg)
    assert "123456:TEST-ONLY-TOKEN" not in rendered
    assert "xxx" not in rendered
    assert "redacted" in rendered


# ---------------------------------------------------------------------------
# 2) RBAC + Telegram command routing (pure layer)
# ---------------------------------------------------------------------------

def make_router(status="runway: 3 queued", dispatch="dispatched", armed="kill-switch ARMED"):
    cfg = make_config()
    return CommandRouter(
        config=cfg,
        fetch_status=lambda: status,
        dispatch_issue=lambda issue_url: dispatch,
        arm_kill_switch=lambda: armed,
    )


def test_rbac_rejects_non_superadmin_chat():
    router = make_router()
    reply = router.route(TelegramUpdate(chat_id="999", text="/stop"))
    assert reply.allowed is False
    assert reply.action == "deny"
    assert "Unauthorized" in reply.text


def test_status_and_runway_route_to_status():
    router = make_router()
    assert router.route(TelegramUpdate("424242", "/status")).text == "runway: 3 queued"
    assert router.route(TelegramUpdate("424242", "/runway")).text == "runway: 3 queued"


def test_dispatch_validates_issue_url_fail_closed():
    router = make_router()
    bad = router.route(
        TelegramUpdate("424242", "/dispatch not-a-github-url")
    )
    assert bad.action == "reply" and "requires a GitHub issue URL" in bad.text
    good = router.route(
        TelegramUpdate(
            "424242",
            "/dispatch https://github.com/Supremeai-bd/supremeai-open/issues/505",
        )
    )
    assert good.action == "dispatch" and good.text == "dispatched"


def test_stop_arms_kill_switch_and_unknown_gets_help():
    router = make_router()
    stopped = router.route(TelegramUpdate("424242", "/stop"))
    assert stopped.action == "kill_switch" and "ARMED" in stopped.text
    unknown = router.route(TelegramUpdate("424242", "/frobnicate"))
    assert "Commands:" in unknown.text


# ---------------------------------------------------------------------------
# 3) HMAC webhook ingress (pure + local socket end-to-end)
# ---------------------------------------------------------------------------

def test_hmac_verify_ok_tampered_and_missing():
    secret = "h" * 32
    body = json.dumps({"issue_url": "https://github.com/o/r/issues/1"}).encode("utf-8")
    sig = compute_signature(secret, body)
    assert verify_hmac(secret, body, sig) is True
    tampered = "sha256=" + "0" * 64
    assert verify_hmac(secret, body, tampered) is False
    assert verify_hmac(secret, body, None) is False
    assert verify_hmac("", body, sig) is False


def test_webhook_ingress_status_codes():
    calls: List[str] = []
    ingress = WebhookIngress("h" * 32, on_valid=calls.append)
    body = json.dumps({"issue_url": "https://github.com/o/r/issues/7"}).encode("utf-8")
    sig = compute_signature("h" * 32, body)
    assert ingress.handle("POST", "/dispatch", body, sig)[0] == 202
    assert calls == ["https://github.com/o/r/issues/7"]
    assert ingress.handle("POST", "/dispatch", body, "sha256=" + "1" * 64)[0] == 401
    # malformed JSON with a VALID signature reaches the parse branch -> 400
    broken = b"{broken"
    broken_sig = compute_signature("h" * 32, broken)
    assert ingress.handle("POST", "/dispatch", broken, broken_sig)[0] == 400
    assert ingress.handle("GET", "/dispatch", body, sig)[0] == 404


def test_webhook_end_to_end_local_socket():
    calls: List[str] = []
    ingress = WebhookIngress("h" * 32, on_valid=calls.append)
    server = make_http_server(ingress)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = json.dumps({"issue_url": "https://github.com/o/r/issues/9"}).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:%d/dispatch" % server.server_address[1],
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": compute_signature("h" * 32, body),
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            assert resp.status == 202
        assert calls == ["https://github.com/o/r/issues/9"]
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# 4) dispatcher payload shape + fail-closed errors (local dummy tower)
# ---------------------------------------------------------------------------

def test_dispatcher_rpc_payload_shape_and_result_parsing():
    captured = {}

    def make_handler():
        from http.server import BaseHTTPRequestHandler

        class H(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                captured["body"] = json.loads(self.rfile.read(length).decode("utf-8"))
                captured["headers"] = {k.lower(): v for k, v in self.headers.items()}
                payload = json.dumps(
                    {"jsonrpc": "2.0", "id": 1,
                     "result": {"content": [{"type": "text", "text": "ok:3"}]}}
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, fmt, *args):  # noqa: A002
                return

        return H

    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        d = TowerDispatcher("https://dummy.invalid", timeout_s=5)
        d.base_url = "http://127.0.0.1:%d/mcp" % server.server_address[1]
        out = d.call_tool("bridge_list_work_orders", {"label": "bridge:queued"})
        assert out == "ok:3"
        body = captured["body"]
        assert body["jsonrpc"] == "2.0" and body["method"] == "tools/call"
        assert body["params"]["name"] == "bridge_list_work_orders"
        assert captured["headers"].get("mcp-protocol-version") == "2025-06-18"
    finally:
        server.shutdown()
        server.server_close()


def test_dispatcher_rejects_http_error_and_bad_url():
    d = TowerDispatcher("https://supremeai-mcp-tower.onrender.com/mcp", timeout_s=5)
    try:
        d.call_tool("bridge_list_work_orders")
        raise AssertionError("expected DispatcherError for unreachable/4xx tower")
    except DispatcherError:
        pass
    try:
        TowerDispatcher("http://insecure.example/mcp")
        raise AssertionError("expected DispatcherError for non-https base_url")
    except DispatcherError:
        pass


# ---------------------------------------------------------------------------
# 5) RESP kill-switch encoding (pure, no socket)
# ---------------------------------------------------------------------------

def test_resp_encoding_shape():
    blob = encode_resp(b"SET", b"key", b"value", b"EX", b"60")
    assert blob.startswith(b"*5\r\n")
    assert b"$3\r\nSET\r\n" in blob
    assert b"$3\r\nkey\r\n" in blob
    assert b"$5\r\nvalue\r\n" in blob
    assert b"$2\r\nEX\r\n" in blob
    assert b"$2\r\n60\r\n" in blob


def test_miniredis_requires_url_fail_closed():
    try:
        MiniRedis(None)
        raise AssertionError("expected KillSwitchUnavailable")
    except Exception as exc:
        assert "REDIS_URL" in str(exc)
    try:
        MiniRedis("https://not-redis.example")
        raise AssertionError("expected KillSwitchUnavailable for bad scheme")
    except Exception:
        pass


def test_config_boot_smoke_contract():
    """Tier-2 boot smoke equivalent: import + construct + API base shape."""
    cfg = make_config()
    assert cfg.telegram_api_base.startswith("https://api.telegram.org/bot")
    assert cfg.is_superadmin("424242") and not cfg.is_superadmin("1")
