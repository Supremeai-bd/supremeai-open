from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid

from fastapi.responses import JSONResponse

from core.errors.error_bus import with_error_bus
from core.logging_config import logger
from core.messaging.event_bus import ErrorContext, ErrorEvent


class HoneypotMiddleware:
    def __init__(self, app):
        self.app = app
        # বাংলা মন্তব্য: RulesMutator ইনস্ট্যান্স একবার তৈরি করে রাখি (প্রতি রিকোয়েস্টে নতুন ইনস্ট্যান্স
        # বানানোর বদলে) — sync Redis কল rules_mutator-এর ৩-সেকেন্ড in-memory ক্যাশে দ্বারা আগে থেকেই সীমিত।
        from core.rules_mutator import RulesMutator

        self.rules_mutator = RulesMutator()
        # পরিচিত অ্যাটাক সিগনেচার
        # বাংলা মন্তব্য: SQL-injection সিগনেচারে আগের বেয়ার `--` প্যাটার্নটি Firebase ID token
        # (JWT, base64url) এর signature অংশে র‍্যান্ডম ভাবে থাকা `--` কে ম্যাচ করে ফেলত এবং
        # ভ্যালিড admin login কে 418 (honeypot) দিয়ে ব্লক করত। তাই `--` কে এখন শুধু আসল SQL
        # comment context-এ ম্যাচ করানো হয়: whitespace/EOL দ্বারা অনুসরণ করা, অথবা quote/semicolon
        # দ্বারা পূর্ববর্তী। এতে base64 টোকেনের false-positive দূর হয়, কিন্তু ক্লাসিক SQLi
        # (যেমন `' OR 1=1--`, `admin'--`, `; --`) ঠিকই ধরা পড়ে।
        #
        # FIX (P1, review 2026-09-12): signature-গুলো এখন দুই স্তরে বিভক্ত।
        # আগে "what is a system prompt?" বা কোড পেস্ট করা মাত্র (<script> ট্যাগ থাকলে)
        # সাধারণ চ্যাট ইউজারও ১ ঘণ্টার জন্য IP-ব্লক হয়ে যেত — AI চ্যাট প্ল্যাটফর্মের জন্য
        # এটি মারাত্মক false-positive। এখন:
        #   - strict (SQLi): যেকোনো পাথে ব্লক করে — এটি context নির্বিশেষে আক্রমণ সংকেত,
        #   - prompt-injection / XSS সিগনেচার: শুধু auth/admin সারফেসে ব্লক করে।
        self.strict_signatures = [
            re.compile(r"(?i)(union\s+select|\b1\s*=\s*1\b|--\s|--$|'\s*--|;\s*--|drop\s+table)"),
        ]
        self.auth_surface_signatures = [
            re.compile(r"(?i)(ignore previous instructions|system prompt)"),
            re.compile(r"(?i)(<script>|javascript:)"),
        ]
        self.attack_signatures = self.strict_signatures + self.auth_surface_signatures
        # FIX (P1, review 2026-09-12): pre-auth RAM exhaustion guard — আগে যেকোনো
        # সাইজের body পুরোপুরি মেমোরিতে buffer হত (multi-GB upload = OOM)।
        self._max_inspect_bytes = int(os.getenv("HONEYPOT_MAX_INSPECT_BYTES", "1000000"))
        self._security_surface_markers = (
            "/admin",
            "/auth",
            "/login",
            "/token",
            "/otp",
            "/password",
            "/register",
            "/signup",
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        env = os.getenv("ENV", "").lower()
        if env == "test":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        hacker_ip = client[0] if client else "unknown"

        # Check if the IP is already dynamically blocked by the RulesMutator
        # (sync Redis কল rules_mutator-এর ৩-সেকেন্ড in-memory ক্যাশে দ্বারা সীমিত — event loop ব্লক ন্যূনতম)
        if self.rules_mutator.is_ip_blocked(hacker_ip):
            logger.warning(f"Honeypot: Blocked request from blacklisted IP: {hacker_ip}")
            response = JSONResponse(
                status_code=403,
                content={"detail": "Forbidden: Access denied due to security policy violations."},
            )
            await response(scope, receive, send)
            return

        # রিকোয়েস্ট বডি রিড করা (Safely inside ASGI)
        body_bytes = b""
        messages = []
        body_oversized = False

        if scope.get("method") in ("POST", "PUT", "PATCH"):
            # FIX (P1, review 2026-09-12): honor Content-Length — large bodies are
            # never buffered/scanned (OOM prevention); they pass straight through.
            content_length = 0
            for hname, hval in scope.get("headers") or []:
                if hname == b"content-length":
                    try:
                        content_length = int(hval)
                    except ValueError:
                        content_length = 0
                    break
            if content_length > self._max_inspect_bytes:
                body_oversized = True

            if not body_oversized:
                more_body = True
                try:
                    while more_body:
                        message = await receive()
                        messages.append(message)
                        body_bytes += message.get("body", b"")
                        if len(body_bytes) > self._max_inspect_bytes:
                            body_oversized = True
                            break
                        more_body = message.get("more_body", False)
                except Exception as exc:
                    logger.debug(f"Honeypot middleware failed to read request body: {exc}")

        # Reconstruct receive channel for downstream handlers
        @with_error_bus("new_receive")
        async def new_receive():
            if messages:
                return messages.pop(0)
            return {"type": "http.disconnect"}

        if body_oversized:
            # FIX (P1, review 2026-09-12, round 2): oversized bodies must reach the
            # app INTACT. If we stopped buffering mid-stream, the already-buffered
            # messages are replayed first and the remaining body is forwarded
            # straight from the real channel (no truncation, no disconnect).
            async def passthrough_receive():
                if messages:
                    return messages.pop(0)
                return await receive()

            logger.debug(f"Honeypot: oversized body from {hacker_ip} — skipping inspection")
            await self.app(scope, passthrough_receive, send)
            return

        body_str = body_bytes.decode("utf-8", errors="ignore")
        query_str = scope.get("query_string", b"").decode("utf-8", errors="ignore")

        # FIX (P1, review 2026-09-12): full signature set only on security
        # surfaces; content paths (e.g. chat) only block on high-confidence SQLi.
        path_lower = scope.get("path", "").lower()
        is_security_surface = any(m in path_lower for m in self._security_surface_markers)
        active_signatures = (
            self.attack_signatures if is_security_surface else self.strict_signatures
        )

        # Check query string and body for malicious signatures
        is_malicious = any(
            sig.search(body_str) or sig.search(query_str) for sig in active_signatures
        )

        if is_malicious:
            # P0 Fix: হ্যাকার ডিটেক্টেড — Immediate auto-block
            logger.warning(f"🕷️ Malicious payload from {hacker_ip}. Auto-blocking...")

            # 1. Immediately block IP via RulesMutator (cached instance)
            self.rules_mutator.block_ip(hacker_ip, reason="honeypot_malicious_payload_detected")

            # 2. Log threat intelligence to Firestore
            self._log_threat_intelligence(hacker_ip, body_str or query_str, scope.get("path", ""))

            # 3. Set distributed block in Redis with 1 hour TTL
            import core.services as app_mod

            if (
                hasattr(app_mod, "redis_queue")
                and app_mod.redis_queue
                and app_mod.redis_queue.configured
            ):
                try:
                    # Set honeypot block key with 1 hour TTL
                    block_entry = {
                        "ip": hacker_ip,
                        "reason": "malicious_payload",
                        "timestamp": time.time(),
                        "threat_level": "HIGH",
                        "path": scope.get("path", ""),
                        "method": scope.get("method", "GET"),
                    }
                    app_mod.redis_queue.set(
                        f"honeypot:blocked:{hacker_ip}",
                        json.dumps(block_entry),
                        ex=3600,  # 1 hour block
                    )
                    # Also set blocklist entry
                    app_mod.redis_queue.set(
                        f"blocklist:ip:{hacker_ip}",
                        json.dumps(
                            {
                                "reason": "honeypot_malicious_payload",
                                "timestamp": time.time(),
                            }
                        ),
                        ex=3600,
                    )
                except Exception as e:
                    logger.error(f"Redis honeypot block operation failed: {e}")

            # 4. Fire security event to event bus
            try:
                from core.messaging.event_bus import ErrorEventBus as _EventBus

                _bus = _EventBus()
                _bus.emit(
                    ErrorEvent(
                        module="honeypot",
                        error_type="HONEYPOT_TRIGGERED",
                        message=f"Malicious payload detected from {hacker_ip}",
                        severity="ERROR",
                        structured_context=ErrorContext(module="auto_fixed"),
                        context={
                            "ip": hacker_ip,
                            "action": "ip_blocked",
                            "block_duration_seconds": 3600,
                            "path": scope.get("path", ""),
                            "method": scope.get("method", "GET"),
                        },
                    )
                )
            except Exception as exc:
                logger.debug(
                    f"Event bus emit failed during honeypot block (suppressed by design): {exc}"
                )

            # 5. Return RFC 2324 (418 I'm a teapot) — اطلاعات-লীন রেসপন্স
            response = JSONResponse(
                status_code=418,  # RFC 2324 — I'm a teapot
                content={
                    "status": "ok",
                    "session_id": str(uuid.uuid4())[:8],
                },
                headers={"X-Server": "nginx/1.18.0"},  # Generic server header
            )
            await response(scope, new_receive, send)
            return

        # নরমাল ইউজার হলে রেগুলার ফ্লো
        if scope.get("method") in ("POST", "PUT", "PATCH"):
            await self.app(scope, new_receive, send)
        else:
            await self.app(scope, receive, send)

    def _log_threat_intelligence(self, ip: str, payload: str, endpoint: str):
        logger.info(f"Threat studied and recorded for IP {ip}")
        try:
            loop = asyncio.get_running_loop()
            # বাংলা মন্তব্য: P1 Fix — run_in_executor নিজেই Future রিটার্ন করে।
            # asyncio.ensure_future() দিয়ে double-wrap করা নিষিদ্ধ — Python 3.10+ DeprecationWarning দেয়।
            future = loop.run_in_executor(None, self._persist_threat_intel, ip, payload, endpoint)

            def _on_done(fut):
                exc = fut.exception()
                if exc:
                    logger.error(f"Threat intel persistence failed: {exc}")

            future.add_done_callback(_on_done)
        except RuntimeError:
            # বাংলা মন্তব্য: event loop না থাকলে synchronously execute করুন
            self._persist_threat_intel(ip, payload, endpoint)
        except Exception as exc:
            logger.debug(f"Failed to schedule threat intel persistence: {exc}")

    def _persist_threat_intel(self, ip: str, payload: str, endpoint: str):
        try:
            import firebase_admin
            from firebase_admin import firestore

            if not firebase_admin._apps:
                firebase_admin.initialize_app()
            db = firestore.client()
            db.collection("threat_intel").add(
                {
                    "ip": ip,
                    "payload": payload[:1000],
                    "endpoint": endpoint,
                    "timestamp": time.time(),
                }
            )
        except Exception as exc:
            logger.debug(f"Failed to persist threat intel to Firestore: {exc}")
