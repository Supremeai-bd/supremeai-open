#!/usr/bin/env python3
"""agent_heartbeat — Python pinger/library for the SupremeAI agent status
dashboard (issue #1402).

Implements the documented 6-state lifecycle transitions:

    startup  -> status "connected" (one-time)
    +3s      -> status "idle"
    loop     -> status "idle" every PING_INTERVAL seconds (keep-alive)
    task     -> status "working", task "<description>"
    done     -> status "idle"
    shutdown -> stop pinging; key expires after TTL -> slot shows "assigned"

Stdlib only (urllib) — no new dependencies. Observability is best-effort:
every failure is swallowed and logged to stderr; the host tool must never
crash because a heartbeat could not be delivered.

CLI:
    export HEARTBEAT_URL=https://<dashboard-host>/api/agents/heartbeat
    python3 heartbeat.py loop                      # background keep-alive
    python3 heartbeat.py once                      # single idle ping
    python3 heartbeat.py working "fixing CI lint"  # single working ping
    python3 heartbeat.py stop                      # final idle ping

Library:
    from heartbeat import HeartbeatClient
    hb = HeartbeatClient(url, slot="agent-2", agent_id="Claude Code")
    hb.connected(); hb.working("migrating shims"); hb.idle()
    hb.start()   # background thread (connected -> idle -> keep-alive)
    hb.stop()    # final idle ping + thread join
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

DEFAULT_SLOT = "agent-2"
DEFAULT_AGENT_ID = "Unknown Tool"
DEFAULT_INTERVAL = 45.0
DEFAULT_CONNECTED_HOLD = 3.0
REQUEST_TIMEOUT = 10.0

VALID_STATUSES = ("connected", "idle", "working")


def _log(msg: str) -> None:
    print(f"[agent_heartbeat] {msg}", file=sys.stderr, flush=True)


class HeartbeatClient:
    """Best-effort heartbeat client for one agent slot."""

    def __init__(
        self,
        url: str | None = None,
        slot: str | None = None,
        agent_id: str | None = None,
        interval: float | None = None,
        connected_hold: float = DEFAULT_CONNECTED_HOLD,
    ) -> None:
        # Explicit args win; otherwise env vars; otherwise defaults.
        # (Constructor defaults must NOT shadow env vars - caught by smoke test.)
        self.url = url or os.environ.get("HEARTBEAT_URL", "")
        self.slot = slot or os.environ.get("AGENT_SLOT", DEFAULT_SLOT)
        self.agent_id = agent_id or os.environ.get("AGENT_ID", DEFAULT_AGENT_ID)
        self.interval = float(
            os.environ.get("PING_INTERVAL", "") or interval or DEFAULT_INTERVAL
        )
        self.connected_hold = float(connected_hold)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # -- one-shot -------------------------------------------------------------
    def ping(self, status: str = "idle", task: str | None = None) -> bool:
        if status not in VALID_STATUSES:
            raise ValueError(f"status must be one of {VALID_STATUSES}, got {status!r}")
        if not self.url:
            _log("HEARTBEAT_URL unset — ping skipped")
            return False
        body: dict[str, str] = {
            "slot": self.slot,
            "agentId": self.agent_id,
            "status": status,
        }
        if task:
            body["task"] = task
        try:
            req = urllib.request.Request(
                self.url,
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                ok = 200 <= resp.status < 300
        except (urllib.error.URLError, OSError, ValueError) as exc:
            _log(f"POST failed (non-fatal) status={status}: {exc}")
            return False
        if ok:
            _log(f"POST ok  status={status} slot={self.slot}")
        return ok

    # -- lifecycle helpers ----------------------------------------------------
    def connected(self) -> bool:
        return self.ping("connected")

    def idle(self) -> bool:
        return self.ping("idle")

    def working(self, task: str) -> bool:
        return self.ping("working", task=task)

    # -- background loop ------------------------------------------------------
    def _run_loop(self) -> None:
        self.ping("connected")
        if self._stop.wait(self.connected_hold):
            self.ping("idle")
            return
        self.ping("idle")
        while not self._stop.wait(self.interval):
            self.ping("idle")

    def start(self) -> None:
        if not self.url:
            _log("HEARTBEAT_URL unset — background loop not started")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="agent-heartbeat", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval + REQUEST_TIMEOUT)
            self._thread = None
        self.ping("idle")
        _log("stop ping sent — slot reverts to 'assigned' after TTL expiry")


def main(argv: list[str]) -> int:
    url = os.environ.get("HEARTBEAT_URL", "")
    if not url and (not argv or argv[0] != "loop"):
        pass  # one-shot modes still warn inside ping()
    client = HeartbeatClient()
    mode = argv[0] if argv else "loop"
    if mode == "loop":
        if not url:
            _log("HEARTBEAT_URL unset — nothing to ping; exiting 0")
            return 0
        client.start()
        try:
            while client._thread and client._thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            client.stop()
        return 0
    if mode == "once":
        client.ping("idle")
        return 0
    if mode == "working":
        if len(argv) < 2:
            _log('usage: heartbeat.py working "<task description>"')
            return 2
        client.ping("working", task=argv[1])
        return 0
    if mode == "stop":
        client.ping("idle")
        _log("stop ping sent — slot reverts to 'assigned' after TTL expiry")
        return 0
    _log("usage: heartbeat.py [loop|once|working <task>|stop]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
