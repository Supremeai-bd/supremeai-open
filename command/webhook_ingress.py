"""src/webhook_ingress.py — HMAC-SHA256 authenticated webhook server.

Security contract (fail-closed):
- Requests must carry `X-Signature: sha256=<hex hmac-sha256(secret, raw body)>`.
- Signature comparison is constant-time (hmac.compare_digest).
- A missing/short server secret refuses to start the server at all.
- Bad signature -> 401, malformed payload -> 400, accepted -> 202.
- Endpoint: POST /dispatch with JSON body {"issue_url": "..."} (or raw text).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional, Tuple

MIN_SECRET_LEN = 16
MAX_BODY_BYTES = 64 * 1024


def compute_signature(secret: str, body: bytes) -> str:
    """Return the canonical `sha256=<hex>` signature for a request body."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return "sha256=%s" % digest


def verify_hmac(secret: str, body: bytes, signature_header: Optional[str]) -> bool:
    """Constant-time HMAC verification; anything unusual is a rejection."""
    if not secret or signature_header is None:
        return False
    expected = compute_signature(secret, body)
    provided = signature_header.strip()
    if len(provided) != len(expected):
        return False
    return hmac.compare_digest(expected, provided)


class WebhookIngress:
    """Auth + parse layer, fully unit-testable without opening a socket."""

    def __init__(self, hmac_secret: str, on_valid: Callable[[str], str]) -> None:
        if not hmac_secret or len(hmac_secret) < MIN_SECRET_LEN:
            raise ValueError(
                "webhook HMAC secret missing or shorter than %d chars" % MIN_SECRET_LEN
            )
        self.hmac_secret = hmac_secret
        self._on_valid = on_valid

    def handle(self, method: str, path: str, body: bytes, signature: Optional[str]) -> Tuple[int, str]:
        if method != "POST" or path.rstrip("/") != "/dispatch":
            return 404, "not found"
        if not verify_hmac(self.hmac_secret, body, signature):
            return 401, "invalid signature"
        if not body or len(body) > MAX_BODY_BYTES:
            return 400, "bad body size"
        try:
            payload = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return 400, "body must be JSON"
        issue_url = ""
        if isinstance(payload, dict):
            issue_url = str(payload.get("issue_url", ""))
        elif isinstance(payload, str):
            issue_url = payload
        if not issue_url:
            return 400, "missing issue_url"
        result = self._on_valid(issue_url)
        return 202, result


def make_http_server(ingress: WebhookIngress, bind_port: int = 0) -> ThreadingHTTPServer:
    """Build (not start) a ThreadingHTTPServer around the ingress logic."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib API
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = self.rfile.read(length) if length else b""
            status, message = ingress.handle(
                "POST", self.path, body, self.headers.get("X-Signature")
            )
            payload = json.dumps({"status": status, "detail": message}).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt: str, *args: object) -> None:  # silence access log
            return

    return ThreadingHTTPServer(("0.0.0.0", bind_port), Handler)


def serve(ingress: WebhookIngress, port: int) -> None:  # pragma: no cover - runtime
    """Blocking runtime entrypoint (used by the command runtime, not tests)."""
    server = make_http_server(ingress, bind_port=port)
    server.serve_forever()
