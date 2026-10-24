#!/usr/bin/env python3
"""
SupremeAI Mesh Node — Daemon
=============================
MESH-3 (issue #941) — Phase A

PC-1 (Dev Rig) এবং PC-2 (Headless Tester) দুটো PC-তেই ব্যাকগ্রাউন্ডে চলে।
Mesh control plane (`backend_url` — SupremeAI **backend** API, কারণ mesh REST routes
(/api/v1/nodes/*, /api/v1/tasks/*) backend-এ থাকে; MCP Control Tower শুধু
MCP-protocol server) এর সাথে heartbeat পাঠায় + assigned task গুলো local-এ
execute করে + result ফেরত পাঠায়। Contract: docs/mesh/configuration-contract.md

Main loop (single asyncio event loop):
  1. WebSocket connect → `tower_ws_url` (OPTIONAL — কোনো deployed host এখনো
     /ws/node serve করে না; খালি রাখলে heartbeat-only mode চলে)
  2. heartbeat_loop — 60s পরপর POST {backend_url}/api/v1/nodes/heartbeat
     (task assignment heartbeat response-এর `assigned_tasks`-এ আসে — live path)
  3. listen_for_tasks — WebSocket message receive → dispatch_task → post result back
     (শুধু WS enabled হলে)
  4. reconnect on disconnect — exponential backoff (2s, 4s, 8s, ..., capped 300s)
  5. graceful shutdown on SIGINT/SIGTERM

Heartbeat contract (MESH-1, #939):
  POST /api/v1/nodes/heartbeat
  Body:
    {node_id, node_type, role, capabilities, timestamp, load: {cpu, mem, active_tasks}}
  Response:
    {status: "ok", lease_active: bool, lease_expires_at: str, assigned_tasks: []}

Tower-এর WebSocket message format (MESH-3 contract):
  Tower → Node:
    {"type": "task", "task_id": "...", "task_type": "bash"|"pytest"|"ollama"|"git_push",
     "payload": {...}, "timeout": 600}
  Node → Tower:
    {"type": "result", "task_id": "...", "status": "ok"|"error"|"timeout", "result": {...}}

Usage:
  python3 daemon.py --config /etc/supreme-node/config.yaml
  python3 daemon.py --config config.yaml --dry-run  # heartbeat একবার পাঠা + exit

Exit codes:
  0 = graceful shutdown
  1 = config error / fatal exception
  2 = unrecoverable reconnect failure (max retries exceeded)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any

try:
    import yaml  # PyYAML
except ImportError as e:  # pragma: no cover
    print(f"[FATAL] PyYAML ইনস্টল নেই: {e}", file=sys.stderr)
    print("        python3 -m pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)

try:
    import httpx
except ImportError as e:  # pragma: no cover
    print(f"[FATAL] httpx ইনস্টল নেই: {e}", file=sys.stderr)
    sys.exit(1)

# websockets is imported lazily inside connect() so test mocks work cleanly.
# (tests patch supreme_node.daemon._ws_connect)

# Local executor layer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from local_executors import (  # noqa: E402
    LocalExecutor,
    dispatch_task,
)

logger = logging.getLogger("supreme-node")


# ---------------------------------------------------------------------------
# Config — load YAML, validate required fields, fall back to env for secrets.
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_PATHS = [
    "./config.yaml",
    "/etc/supreme-node/config.yaml",
    os.path.expanduser("~/.config/supreme-node/config.yaml"),
]

REQUIRED_KEYS = (
    "node_id",
    "node_type",
    "role",
    "capabilities",
)
# Control-plane base URL: canonical key is `backend_url` (the SupremeAI backend
# hosts the mesh REST routes — /api/v1/nodes/*, /api/v1/tasks/*). The MCP
# Control Tower is an MCP-protocol server and hosts NO node REST routes, so
# pointing the base URL at the Tower 404s every heartbeat (#2255).
# Legacy key `tower_url` is still accepted (with a warning) for backward
# compatibility with already-deployed configs.
CONTROL_PLANE_URL_KEYS = ("backend_url", "tower_url")

# Keys whose string values may reference environment variables via "${VAR}"
# or "$VAR" (the config template advertises this — actually implement it).
ENV_EXPANDABLE_KEYS = ("backend_url", "tower_url", "tower_ws_url", "tower_auth_token")


def _expand_env(value: str) -> str:
    """Expand ${VAR}/$VAR references in config string values.

    Unset variables expand to the empty string and are logged once by the
    caller-visible result (empty ws url == disabled, per the contract doc).
    """
    import re as _re

    def _sub(m):
        var = m.group(1) or m.group(2)
        return os.environ.get(var, "")

    return _re.sub(r"\$\{(\w+)\}|\$(\w+)", _sub, value)

VALID_NODE_TYPES = {"local_pc", "cloud_agent", "web_ai", "edge_device", "external_mcp"}
VALID_ROLES = {"planner", "coder", "tester", "gate", "observer"}


class ConfigError(Exception):
    pass


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """YAML থেকে config লোড করে + validate করে।"""
    path = config_path
    if path is None:
        for cand in DEFAULT_CONFIG_PATHS:
            if os.path.isfile(cand):
                path = cand
                break
    if path is None or not os.path.isfile(path):
        raise ConfigError(
            f"config file পাওয়া যায়নি। "
            f" tried defaults: {DEFAULT_CONFIG_PATHS}"
        )
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg, dict):
        raise ConfigError(f"config root dict হতে হবে, got {type(cfg).__name__}")

    # required keys
    missing = [k for k in REQUIRED_KEYS if k not in cfg]
    if missing:
        raise ConfigError(f"config-এ অসম্পূর্ণ — missing keys: {missing}")

    # env interpolation on URL-ish keys (the template advertises "set via env
    # var" — honor it; previously ${VAR} literals leaked into URLs)
    for key in ENV_EXPANDABLE_KEYS:
        if isinstance(cfg.get(key), str):
            cfg[key] = _expand_env(cfg[key])

    # control-plane URL resolution: backend_url (canonical) > tower_url (legacy)
    url_key = next((k for k in CONTROL_PLANE_URL_KEYS if cfg.get(k)), None)
    if url_key is None:
        raise ConfigError(
            "config-এ control-plane base URL নেই — `backend_url` সেট করুন "
            "(legacy `tower_url` এখনও গ্রহণযোগ্য)"
        )
    if url_key == "tower_url":
        logger.warning(
            "config legacy key `tower_url` ব্যবহার হচ্ছে — canonical key `backend_url`-এ "
            "মাইগ্রেট করুন (value একই: SupremeAI backend API base, docs/mesh/configuration-contract.md)"
        )
    cfg["backend_url"] = cfg[url_key]
    cfg.setdefault("tower_url", cfg["backend_url"])

    # node_type validation
    if cfg["node_type"] not in VALID_NODE_TYPES:
        raise ConfigError(
            f"invalid node_type {cfg['node_type']!r}; valid: {sorted(VALID_NODE_TYPES)}"
        )
    if cfg["role"] not in VALID_ROLES:
        raise ConfigError(
            f"invalid role {cfg['role']!r}; valid: {sorted(VALID_ROLES)}"
        )

    # defaults
    cfg.setdefault("heartbeat_path", "/api/v1/nodes/heartbeat")
    cfg.setdefault("heartbeat_interval", 60)
    cfg.setdefault("reconnect_backoff_base", 2)
    cfg.setdefault("reconnect_backoff_max", 300)
    # Constitution ARCH-001: .py তে কোনো localhost literal থাকবে না —
    # override chain: SUPREME_NODE_OLLAMA_URL env > config.yaml এর ollama_url > খালি।
    # খালি হলে ollama capability task execute-এর সময় clear error হবে।
    cfg.setdefault("ollama_url", os.environ.get("SUPREME_NODE_OLLAMA_URL", ""))
    cfg.setdefault("task_timeout_seconds", 600)
    cfg.setdefault("workspace_dir", "./workspace")
    cfg.setdefault("log_level", "INFO")
    cfg.setdefault("tower_auth_token", "")

    # env override — TOWER_AUTH_TOKEN সেট থাকলে config-কে বাইপাস করে।
    env_tok = os.environ.get("TOWER_AUTH_TOKEN")
    if env_tok:
        cfg["tower_auth_token"] = env_tok

    # workspace dir create করি (না থাকলে)
    ws = cfg["workspace_dir"]
    if not os.path.isabs(ws):
        ws = os.path.abspath(ws)
    cfg["workspace_dir"] = ws
    os.makedirs(ws, exist_ok=True)

    return cfg


# ---------------------------------------------------------------------------
# WebSocket connect helper — wrapped for test mocking।
# ---------------------------------------------------------------------------

async def _ws_connect(url: str, **kwargs: Any) -> Any:
    """websockets.connect এর thin wrapper — tests এ mock করা যায়।"""
    import websockets  # lazy import for testability
    return await websockets.connect(url, **kwargs)


# ---------------------------------------------------------------------------
# System load — psutil দিয়ে।
# ---------------------------------------------------------------------------

def _get_system_load() -> dict[str, Any]:
    """CPU%, MEM%, active_tasks (count of running asyncio tasks)।"""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
    except ImportError:
        # psutil না থাকলেও চলবে — 0 রিপোর্ট করে (REL-002: observable action)।
        logging.getLogger("supreme_node").debug(
            "psutil installed নেই — system load metrics 0.0 রিপোর্ট হচ্ছে"
        )
        cpu = 0.0
        mem = 0.0
    # active_tasks = এই event loop এ চলমান task count
    try:
        active = len(asyncio.all_tasks())
    except RuntimeError:
        logging.getLogger("supreme_node").debug(
            "কোনো running event loop নেই — active_tasks 0 রিপোর্ট হচ্ছে"
        )
        active = 0
    return {
        "cpu": round(cpu, 1),
        "mem": round(mem, 1),
        "active_tasks": active,
    }


def _iso_timestamp() -> str:
    """UTC ISO8601 timestamp with Z suffix — Tower contract।"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Main daemon class।
# ---------------------------------------------------------------------------

class SupremeNodeDaemon:
    """
    Async daemon — WebSocket connect, heartbeat loop, task listener, reconnect।
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.node_id: str = config["node_id"]
        # Control-plane base URL — canonical key `backend_url` (legacy
        # `tower_url` alias resolved by load_config). Hosts the mesh REST
        # routes (POST /api/v1/nodes/heartbeat); the MCP Tower does NOT.
        self.tower_url: str = config["backend_url"].rstrip("/")
        self.tower_ws_url: str = config.get("tower_ws_url", "")
        # WS push channel is planned but served by no deployed host today;
        # empty URL => heartbeat-only mode (tasks arrive via the heartbeat
        # response `assigned_tasks`). See docs/mesh/configuration-contract.md.
        self.ws_enabled: bool = bool(self.tower_ws_url.strip())
        self.heartbeat_url: str = self.tower_url + config["heartbeat_path"]
        self.heartbeat_interval: float = float(config["heartbeat_interval"])
        self.backoff_base: float = float(config["reconnect_backoff_base"])
        self.backoff_max: float = float(config["reconnect_backoff_max"])
        self.workspace_dir: str = config["workspace_dir"]
        self.auth_token: str = config.get("tower_auth_token", "")

        # executor
        self.executor = LocalExecutor(
            workspace_dir=self.workspace_dir,
            ollama_url=config["ollama_url"],
            task_timeout_seconds=float(config["task_timeout_seconds"]),
        )

        # runtime state
        self._ws: Any = None
        self._stop_event: asyncio.Event = asyncio.Event()
        self._tasks: set[asyncio.Task] = set()
        self._backoff_current: float = self.backoff_base
        self._active_task_count: int = 0
        self._lease_active: bool = False
        self._lease_expires_at: str = ""

    # ------------------------------------------------------------------
    # Lifecycle।
    # ------------------------------------------------------------------
    async def run(self, dry_run: bool = False) -> int:
        """Main entrypoint। dry_run=True হলে একবার heartbeat পাঠিরে exit।"""
        if dry_run:
            logger.info("dry-run mode — একবার heartbeat + exit")
            ok = await self.send_heartbeat()
            return 0 if ok else 1

        # signal handlers — SIGINT/SIGTERM এ graceful shutdown।
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._handle_signal, sig)
            except NotImplementedError:
                # Windows / some sandboxes — fallback to default signal behavior
                # (Constitution REL-001: silent handler নিষিদ্ধ — observable log বাধ্যতামূলক)
                logger.warning(
                    "%s signal handler এই platform-এ unsupported — "
                    "default signal behavior ব্যবহার হচ্ছে",
                    sig.name,
                )

        retry_count = 0
        while not self._stop_event.is_set():
            try:
                if self.ws_enabled:
                    await self.connect()
                    # parallel — heartbeat + listen
                    hb_task = asyncio.create_task(self.heartbeat_loop())
                    listen_task = asyncio.create_task(self.listen_for_tasks())
                    self._tasks = {hb_task, listen_task}
                else:
                    # Heartbeat-only mode: no deployed host serves /ws/node yet;
                    # task assignment rides the heartbeat response.
                    logger.info(
                        "tower_ws_url খালি — heartbeat-only mode "
                        "(task delivery = heartbeat response `assigned_tasks`)"
                    )
                    hb_task = asyncio.create_task(self.heartbeat_loop())
                    self._tasks = {hb_task}
                # যেকোনো একটা শেষ হলে আমরা reconnect করব।
                done, pending = await asyncio.wait(
                    self._tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()
                    try:
                        await t
                    except asyncio.CancelledError:
                        logger.debug(
                            "pending task %s cancelled — reconnect শুরু হচ্ছে",
                            t.get_name(),
                        )
                    except Exception as e:
                        logger.warning(
                            "pending task %s cancel-এর সময় error: %s: %s",
                            t.get_name(), type(e).__name__, e,
                        )
                retry_count = 0  # successful run resets backoff
            except asyncio.CancelledError:
                logger.info("daemon cancelled — shutting down")
                break
            except Exception as e:
                logger.warning("daemon loop error: %s: %s", type(e).__name__, e)
                retry_count += 1
                wait = self._compute_backoff(retry_count)
                logger.info("reconnect attempt %d — backoff %.1fs", retry_count, wait)
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=wait)
                    # stop signaled during backoff
                    break
                except asyncio.TimeoutError:
                    logger.debug("backoff %.1fs শেষ — reconnect করা হচ্ছে", wait)
                    continue
            finally:
                await self._close_ws()

        logger.info("daemon exited cleanly")
        return 0

    def _compute_backoff(self, retry_count: int) -> float:
        """Exponential backoff — 2, 4, 8, 16, 32, 64, 128, 256, 300 (capped)।"""
        backoff = self.backoff_base * (2 ** max(0, retry_count - 1))
        return min(backoff, self.backoff_max)

    def _handle_signal(self, sig: int) -> None:
        logger.info("signal %s received — initiating graceful shutdown", sig)
        self._stop_event.set()
        for t in self._tasks:
            if not t.done():
                t.cancel()

    # ------------------------------------------------------------------
    # WebSocket connect।
    # ------------------------------------------------------------------
    async def connect(self) -> None:
        """Tower-এর WebSocket-এ connect করে।"""
        logger.info("connecting to Tower WebSocket: %s", self.tower_ws_url)
        # Auth header (optional per MESH-1 spec)
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        # node_id header দিলে Tower কে সহজ হয় (info only — auth নয়)
        headers["X-SupremeAI-Node-ID"] = self.node_id

        self._ws = await _ws_connect(
            self.tower_ws_url,
            additional_headers=headers if headers else None,
            ping_interval=self.heartbeat_interval,
            ping_timeout=30,
            close_timeout=10,
        )
        logger.info("WebSocket connected")

    async def _close_ws(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception as e:
                logger.debug("ws close error: %s", e)
            finally:
                self._ws = None

    # ------------------------------------------------------------------
    # Heartbeat loop — 60s পরপর POST /api/v1/nodes/heartbeat।
    # ------------------------------------------------------------------
    async def heartbeat_loop(self) -> None:
        """প্রতি heartbeat_interval সেকেন্ড পরপর Tower-কে heartbeat POST করে।"""
        logger.info("heartbeat loop started — interval %ss", self.heartbeat_interval)
        # প্রথমবার একটু দেরি না করে একবার পাঠাই — Tower দ্রুত register করে।
        while not self._stop_event.is_set():
            try:
                ok = await self.send_heartbeat()
                if not ok:
                    logger.warning("heartbeat failed — will retry in %ss",
                                   self.heartbeat_interval)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("heartbeat exception: %s: %s", type(e).__name__, e)
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.heartbeat_interval
                )
                return  # stop signaled
            except asyncio.TimeoutError:
                logger.debug("heartbeat interval শেষ — পরের beat পাঠানো হচ্ছে")
                continue

    async def send_heartbeat(self) -> bool:
        """একবার heartbeat POST করে। True/False রিটার্ন করে।"""
        payload = {
            "node_id": self.node_id,
            "node_type": self.config["node_type"],
            "role": self.config["role"],
            "capabilities": list(self.config["capabilities"]),
            "timestamp": _iso_timestamp(),
            "load": _get_system_load(),
        }
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(self.heartbeat_url, json=payload, headers=headers)
            if resp.status_code != 200:
                logger.warning("heartbeat HTTP %s: %s",
                               resp.status_code, resp.text[:200])
                return False
            try:
                data = resp.json()
            except json.JSONDecodeError:
                logger.warning("heartbeat response not JSON: %s", resp.text[:200])
                return False
            self._lease_active = bool(data.get("lease_active", False))
            self._lease_expires_at = str(data.get("lease_expires_at", ""))
            assigned = data.get("assigned_tasks", []) or []
            logger.info("heartbeat ok — lease_active=%s expires=%s assigned=%d",
                        self._lease_active, self._lease_expires_at, len(assigned))
            return True
        except httpx.HTTPError as e:
            logger.warning("heartbeat HTTP error: %s: %s", type(e).__name__, e)
            return False

    # ------------------------------------------------------------------
    # Listen for tasks — WebSocket থেকে message receive + dispatch + result post।
    # ------------------------------------------------------------------
    async def listen_for_tasks(self) -> None:
        """WebSocket message receive করে এবং task execute করে।"""
        if self._ws is None:
            logger.error("listen_for_tasks — WebSocket not connected")
            return
        logger.info("task listener started")
        while not self._stop_event.is_set():
            try:
                raw = await self._ws.recv()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("ws recv error: %s: %s", type(e).__name__, e)
                # connection drop — break and let outer loop reconnect
                return
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("invalid JSON from Tower: %s", str(raw)[:200])
                continue
            await self._handle_message(msg)

    async def _handle_message(self, msg: dict[str, Any]) -> None:
        """Tower-এর message dispatch — type-based।"""
        mtype = msg.get("type", "")
        if mtype == "ping":
            # Tower keepalive — ack back
            await self._send_message({"type": "pong", "node_id": self.node_id,
                                       "timestamp": _iso_timestamp()})
            return
        if mtype == "task":
            task = {
                "task_id": msg.get("task_id", "unknown"),
                "type": msg.get("task_type") or msg.get("type"),
                "payload": msg.get("payload") or {},
                "timeout": msg.get("timeout"),
            }
            # task_type field আলাদা fix করি
            task["type"] = msg.get("task_type") or msg.get("executor")
            asyncio.create_task(self._execute_and_report(task))
            return
        if mtype == "shutdown":
            logger.info("Tower requested shutdown")
            self._stop_event.set()
            return
        # unknown message — log only, don't crash
        logger.info("unknown message type %r — ignoring", mtype)

    async def _execute_and_report(self, task: dict[str, Any]) -> None:
        """Task execute করে + result Tower-কে পাঠায়।"""
        task_id = task.get("task_id", "unknown")
        logger.info("executing task %s (type=%s)", task_id, task.get("type"))
        self._active_task_count += 1
        start = time.monotonic()
        try:
            result = await dispatch_task(self.executor, task)
        except Exception as e:
            result = {
                "task_id": task_id,
                "status": "error",
                "result": {"error": f"{type(e).__name__}: {e}"},
            }
        finally:
            self._active_task_count -= 1
        duration = round(time.monotonic() - start, 3)
        result["duration_seconds"] = duration
        result["node_id"] = self.node_id
        logger.info("task %s done — status=%s duration=%ss",
                     task_id, result.get("status"), duration)
        await self._send_message({"type": "result", **result})

    async def _send_message(self, msg: dict[str, Any]) -> None:
        """Tower-কে JSON message পাঠায়। Connection না থাকলে log only।"""
        if self._ws is None:
            logger.debug("send_message skipped — no ws (msg type=%s)", msg.get("type"))
            return
        try:
            await self._ws.send(json.dumps(msg))
        except Exception as e:
            logger.warning("send_message failed: %s: %s", type(e).__name__, e)


# ---------------------------------------------------------------------------
# CLI entrypoint।
# ---------------------------------------------------------------------------

def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="supreme-node",
        description="SupremeAI Mesh Node Daemon (MESH-3 #941)",
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to config.yaml (default: ./config.yaml or /etc/supreme-node/config.yaml)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Send one heartbeat and exit — useful for setup smoke test.",
    )
    parser.add_argument(
        "--log-level",
        help="Override log level (DEBUG/INFO/WARNING/ERROR)",
    )
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        print(f"[FATAL] config error: {e}", file=sys.stderr)
        return 1

    setup_logging(args.log_level or cfg.get("log_level", "INFO"))
    logger.info("SupremeAI Mesh Node daemon starting — node_id=%s role=%s",
                cfg["node_id"], cfg["role"])

    daemon = SupremeNodeDaemon(cfg)
    try:
        return asyncio.run(daemon.run(dry_run=args.dry_run))
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt — shutting down")
        return 0
    except ConfigError as e:
        print(f"[FATAL] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
