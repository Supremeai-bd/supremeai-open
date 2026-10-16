#!/usr/bin/env python3
"""tests/test_gateway_live_smoke.py — E2E smoke contract for the SupremeAI Gateway (issue #403).

Verifies the canonical 10-call E2E matrix (5 non-stream + 5 SSE streaming)
and the SSE streaming contract (valid ``data:`` frames, terminal frame EXACT
``data: [DONE]``, TTFT measurement, honest mid-stream failure) mandated by
issue #403. The bash harness ``examples/curl-tests/run_e2e_smoke.sh`` is
executed for real against an embedded mock gateway, so the suite proves the
shipped artifact — not a copy of it.

Dual mode (zero-dependency doctrine, AGENT_RULES.md §13):
  - pytest:  pytest tests/test_gateway_live_smoke.py
  - stdlib:  python3 tests/test_gateway_live_smoke.py   (plain runner, no pytest)

Honest sequencing: the live gateway routes are currently down (independently
probed: /healthz /health /v1/models → 404; repair is Seq 0.1 = issue #401),
so without ``SUPREMEAI_API_KEY`` the live test SKIPS — mock evidence here is
complete (10/10), and the suite flips to live mode the moment the key env is
present and Seq 0.1/0.2 land.

বাংলা নোট: মক গেটওয়ে-ও আসল চুক্তি মেনে চলে — `X-SupremeAI-Key` হেডার ছাড়া
৪০১, `usage` অবজেক্ট বাধ্যতামূলক (Honest Ledger), স্ট্রিম মাঝপথে কেটে গেলে
সৎ ব্যর্থতা, কখনো নীরব দুর্নীতি নয়।
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SH_HARNESS = REPO_ROOT / "examples" / "curl-tests" / "run_e2e_smoke.sh"
PS1_HARNESS = REPO_ROOT / "examples" / "curl-tests" / "run_e2e_smoke.ps1"

DEFAULT_BASE = os.getenv("SUPREMEAI_GATEWAY_URL", "https://supremeai-api.onrender.com")
AUTH_HEADER = "X-SupremeAI-Key"  # canonical per docs/CONSUMERS.md §১২
MOCK_MODELS = ["auto", "mock-fast", "mock-mini"]
DROP_MODEL = "mock-midstream-drop"  # mock scenario: stream dies without [DONE]


class _Skip(Exception):
    """Stdlib-mode skip signal (pytest path uses pytest.skip instead)."""


def _skip(reason: str) -> None:
    if "PYTEST_CURRENT_TEST" in os.environ:
        import pytest  # noqa: PLC0415 — dual-mode: pytest optional by design

        pytest.skip(reason)
    raise _Skip(reason)


# --------------------------------------------------------------------------- #
# Embedded mock gateway — OpenAI-compatible subset of the repo contract       #
# --------------------------------------------------------------------------- #

class _MockGatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"  # connection-per-request: SSE EOF == honest drop

    def log_message(self, *args):  # keep test output clean
        pass

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 — stdlib naming
        if self.path == "/v1/models":
            self._json(200, {"object": "list",
                             "data": [{"id": m, "object": "model"} for m in MOCK_MODELS]})
        else:
            self._json(404, {"error": {"message": f"no route: {self.path}"}})

    def do_POST(self) -> None:  # noqa: N802 — stdlib naming
        if self.path != "/v1/chat/completions":
            self._json(404, {"error": {"message": f"no route: {self.path}"}})
            return
        if not self.headers.get(AUTH_HEADER):
            self._json(401, {"error": {"message": f"missing {AUTH_HEADER} (docs/CONSUMERS.md)"}})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": {"message": "invalid JSON body"}})
            return
        model = str(payload.get("model", "auto"))
        prompt = (payload.get("messages") or [{}])[-1].get("content", "")

        if model == "mock-502":
            self._json(502, {"error": {"message": "all providers failed — sanitized ledger",
                                       "providers_tried": ["groq", "gemini"]}})
            return

        if not payload.get("stream"):
            self._json(200, {
                "id": "chatcmpl-mock", "object": "chat.completion", "model": model,
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": f"echo:{prompt}"}}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 6, "total_tokens": 15},
            })
            return

        # ---- SSE streaming ----
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def frame(delta: str) -> bytes:
            chunk = {"id": "chatcmpl-mock", "object": "chat.completion.chunk", "model": model,
                     "choices": [{"index": 0, "finish_reason": None,
                                  "delta": {"role": "assistant", "content": delta}}]}
            return f"data: {json.dumps(chunk)}\n\n".encode()

        if model == DROP_MODEL:
            # mid-stream provider failure: two honest frames, then a silent drop —
            # the CLIENT must detect the missing terminal frame and fail honestly.
            self.wfile.write(frame("par"))
            self.wfile.write(frame("tial"))
            self.wfile.flush()
            self.close_connection = True
            return

        for tok in ("SUP", "REME", "-E2E", "-OK"):
            self.wfile.write(frame(tok))
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def _start_mock() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockGatewayHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


# --------------------------------------------------------------------------- #
# Contract helpers — the 10-call matrix against any OpenAI-compatible base    #
# --------------------------------------------------------------------------- #

def _headers(key: str) -> dict:
    return {AUTH_HEADER: key, "Content-Type": "application/json"}


def nonstream_call(base: str, key: str, model: str, timeout: float = 20.0) -> dict:
    """One stream:false call → {'ok', 'status', 'content', 'usage', 'latency'}."""
    payload = json.dumps({"model": model, "stream": False, "max_tokens": 32,
                          "messages": [{"role": "user", "content": "Reply with exactly: SUPREME-E2E-OK"}]}).encode()
    t0 = time.monotonic()
    try:
        req = urllib.request.Request(f"{base}/v1/chat/completions", data=payload,
                                     headers=_headers(key), method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            obj = json.load(resp)
        latency = time.monotonic() - t0
        content = (obj.get("choices") or [{}])[0].get("message", {}).get("content", "")
        ok = bool(content) and "usage" in obj
        return {"ok": ok, "status": 200, "content": content,
                "usage": obj.get("usage"), "latency": latency}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:200]
        return {"ok": False, "status": exc.code, "content": "", "usage": None,
                "latency": time.monotonic() - t0, "error": body}


def stream_call(base: str, key: str, model: str, timeout: float = 20.0) -> dict:
    """One stream:true call → SSE contract check.

    Returns {'ok', 'status', 'ttft', 'terminal', 'frames', 'deltas'}; ok=False
    carries an honest 'error' reason (mid-stream drop, bad frame, HTTP error).
    """
    payload = json.dumps({"model": model, "stream": True, "max_tokens": 32,
                          "messages": [{"role": "user", "content": "Reply with exactly: SUPREME-E2E-OK"}]}).encode()
    t0 = time.monotonic()
    try:
        req = urllib.request.Request(f"{base}/v1/chat/completions", data=payload,
                                     headers=_headers(key), method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ttft = None
            frames: list[str] = []
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                if ttft is None:
                    ttft = time.monotonic() - t0
                frames.append(line[len("data:"):].strip())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:200]
        return {"ok": False, "status": exc.code, "ttft": None, "terminal": None,
                "frames": [], "deltas": "", "error": body}
    terminal = frames[-1] if frames else None
    if not frames:
        return {"ok": False, "status": 200, "ttft": None, "terminal": None,
                "frames": [], "deltas": "", "error": "no SSE data: frames"}
    if terminal != "[DONE]":
        return {"ok": False, "status": 200, "ttft": ttft, "terminal": terminal,
                "frames": frames, "deltas": "",
                "error": f"stream ended without exact 'data: [DONE]' terminal frame (last={terminal!r}) — mid-stream drop"}
    deltas = ""
    for f in frames[:-1]:
        try:
            obj = json.loads(f)
            delta = (obj.get("choices") or [{}])[0].get("delta", {}).get("content")
        except json.JSONDecodeError:
            return {"ok": False, "status": 200, "ttft": ttft, "terminal": terminal,
                    "frames": frames, "deltas": deltas,
                    "error": f"unparseable SSE frame: {f[:80]!r}"}
        if delta is None:
            return {"ok": False, "status": 200, "ttft": ttft, "terminal": terminal,
                    "frames": frames, "deltas": deltas,
                    "error": f"SSE frame missing choices[0].delta: {f[:80]!r}"}
        deltas += delta
    return {"ok": True, "status": 200, "ttft": ttft, "terminal": terminal,
            "frames": frames, "deltas": deltas}


# --------------------------------------------------------------------------- #
# Tests (pytest discovers directly; stdlib runner at the bottom)              #
# --------------------------------------------------------------------------- #

def test_bash_harness_syntax():
    assert SH_HARNESS.is_file(), f"missing harness {SH_HARNESS}"
    r = subprocess.run(["bash", "-n", str(SH_HARNESS)], capture_output=True, text=True)
    assert r.returncode == 0, f"bash -n failed: {r.stderr[:300]}"


def test_powershell_harness_syntax():
    if not PS1_HARNESS.is_file():
        raise AssertionError(f"missing harness {PS1_HARNESS}")
    from shutil import which

    if which("pwsh") is None:
        _skip("pwsh not installed on this runner — .ps1 mirror syntax unchecked here (CI Windows lane)")
    script = (
        "$t=$null;$e=$null;"
        "[System.Management.Automation.Language.Parser]::ParseFile("
        f"'{PS1_HARNESS}',[ref]$t,[ref]$e)|Out-Null;"
        "if($e.Count -gt 0){$e|ForEach-Object{$_.Message};exit 1}else{exit 0}"
    )
    r = subprocess.run(["pwsh", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"PowerShell parse errors: {r.stdout[:300]}"


def test_mock_models_endpoint():
    server, base = _start_mock()
    try:
        with urllib.request.urlopen(f"{base}/v1/models", timeout=10) as resp:
            obj = json.load(resp)
        ids = [m["id"] for m in obj["data"]]
        assert "auto" in ids and "mock-fast" in ids
    finally:
        server.shutdown()


def test_mock_nonstream_matrix_5():
    server, base = _start_mock()
    try:
        results = [nonstream_call(base, "test-key-e2e", MOCK_MODELS[i % len(MOCK_MODELS)])
                   for i in range(5)]
        assert all(r["ok"] for r in results), f"honest failures: {results}"
        assert all(r["usage"] for r in results), "Honest Ledger: usage required on every call"
        assert all(r["content"].startswith("echo:") for r in results)
    finally:
        server.shutdown()


def test_mock_stream_matrix_5_sse_contract():
    server, base = _start_mock()
    try:
        results = [stream_call(base, "test-key-e2e", MOCK_MODELS[i % len(MOCK_MODELS)])
                   for i in range(5)]
        for r in results:
            assert r["ok"], f"SSE contract violation: {r.get('error')}"
            assert r["terminal"] == "[DONE]", "terminal frame must be EXACT data: [DONE]"
            assert r["ttft"] is not None and r["ttft"] > 0, "TTFT must be measured"
            assert r["deltas"] == "SUPREME-E2E-OK", f"delta reassembly broken: {r['deltas']!r}"
    finally:
        server.shutdown()


def test_mock_sse_terminal_frame_exact():
    server, base = _start_mock()
    try:
        r = stream_call(base, "test-key-e2e", "auto")
        assert r["ok"] and r["frames"][-1] == "[DONE]"
        assert all(f != "[DONE]" for f in r["frames"][:-1]), "[DONE] must appear exactly once, last"
    finally:
        server.shutdown()


def test_mock_midstream_drop_fails_honestly():
    server, base = _start_mock()
    try:
        r = stream_call(base, "test-key-e2e", DROP_MODEL)
        assert not r["ok"], "silent drop must NOT pass — honesty contract"
        assert "[DONE]" in r["error"], "honest error must name the missing terminal frame"
        assert r["terminal"] != "[DONE]"
    finally:
        server.shutdown()


def test_mock_502_honest_failure():
    server, base = _start_mock()
    try:
        r = nonstream_call(base, "test-key-e2e", "mock-502")
        assert not r["ok"] and r["status"] == 502
        assert "providers_tried" in r["error"], "sanitized provider ledger required"
    finally:
        server.shutdown()


def test_mock_auth_401_without_key():
    server, base = _start_mock()
    try:
        payload = json.dumps({"model": "auto", "stream": False, "messages": []}).encode()
        req = urllib.request.Request(f"{base}/v1/chat/completions", data=payload,
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=10)
            raise AssertionError("missing key must be rejected 401")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
            assert AUTH_HEADER in exc.read().decode()
    finally:
        server.shutdown()


def test_bash_harness_full_10_over_mock():
    # THE functional proof: the shipped .sh runs the real matrix over the mock.
    server, base = _start_mock()
    try:
        env = dict(os.environ,
                   GATEWAY_URL=base, SUPREMEAI_API_KEY="test-key-e2e",
                   MODELS=" ".join(MOCK_MODELS), CURL_TIMEOUT="20")
        r = subprocess.run(["sh", str(SH_HARNESS), "all"],
                           capture_output=True, text=True, env=env, timeout=180)
        assert r.returncode == 0, f"harness failed honestly:\n{r.stdout[-1200:]}"
        assert "10/10 calls passed" in r.stdout, f"expected 10/10 ledger:\n{r.stdout[-800:]}"
        assert r.stdout.count("PASS ns") == 5 and r.stdout.count("PASS st") == 5
        assert "TTFT=" in r.stdout, "TTFT must be recorded per stream call"
    finally:
        server.shutdown()


def test_bash_harness_midstream_drop_honest():
    server, base = _start_mock()
    try:
        env = dict(os.environ,
                   GATEWAY_URL=base, SUPREMEAI_API_KEY="test-key-e2e",
                   MODELS=f"auto {DROP_MODEL}", CURL_TIMEOUT="20")
        r = subprocess.run(["sh", str(SH_HARNESS), "stream"],
                           capture_output=True, text=True, env=env, timeout=180)
        assert r.returncode == 1, "mid-stream drop must fail the harness (fail-closed)"
        assert "without exact 'data: [DONE]'" in r.stdout, "honest drop diagnosis required"
        # rotation fixed: st1/st3/st5=auto pass, st2/st4=drop fail → 3/5 honest ledger
        assert "3/5 calls passed" in r.stdout, f"ledger must be honest:\n{r.stdout[-600:]}"
        assert f"model={DROP_MODEL}" in r.stdout, "drop model must actually be exercised (rotation proof)"
    finally:
        server.shutdown()


def test_live_gateway_e2e_or_honest_skip():
    key = os.getenv("SUPREMEAI_API_KEY")
    if not key:
        _skip("SUPREMEAI_API_KEY not provisioned — live lane pending Seq 0.1/0.2 (#401/#402); "
              "mock evidence above is complete (10/10)")
    base = DEFAULT_BASE
    try:
        with urllib.request.urlopen(f"{base}/v1/models", timeout=15) as resp:
            models = [m["id"] for m in json.load(resp)["data"]]
    except Exception as exc:  # noqa: BLE001 — gateway routes down = #401's domain, not ours
        _skip(f"live gateway routes not serving yet ({exc.__class__.__name__}) — Seq 0.1 pending")
        return
    r1 = nonstream_call(base, key, models[0])
    r2 = stream_call(base, key, models[0])
    assert r1["ok"], f"live non-stream honest failure: {r1}"
    assert r2["ok"], f"live SSE honest failure: {r2.get('error')}"
    assert r2["terminal"] == "[DONE]"


# --------------------------------------------------------------------------- #
# Dual-mode runner (stdlib path)                                              #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = skipped = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS | {fn.__name__}")
        except _Skip as exc:
            skipped += 1
            print(f"  SKIP | {fn.__name__}: {exc}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL | {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 — honest failure reporting
            failed += 1
            print(f"  ERROR | {fn.__name__}: {type(exc).__name__}: {exc}")
    passed = len(fns) - failed - skipped
    if skipped:
        print(f"{passed}/{len(fns)} tests passed ({skipped} skipped — honest sequencing)")
    else:
        print(f"{passed}/{len(fns)} tests passed")
    sys.exit(1 if failed else 0)
