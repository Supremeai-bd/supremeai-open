"""SupremeAI Gateway — zero-dependency consumer client (P3, plan §15)।

বাংলা মন্তব্য (consumer-চুক্তি):
- key = `SUPREMEAI_API_KEY` env (monolith key-plane-ইস্যুকৃত, vault-ফিড) —
  কখনো কোড/git/log-এ নয় (SECRETS_MODEL.md)
- header সবসময় `X-SupremeAI-Key` — provider credential-এর কপি নয় (§২২-নীতি)
- error চার রকম এবং সৎ: 401=অবৈধ/বাতিল key, 429=সীমা (rate_limit_rps×window),
  502=সব provider ব্যর্থ, 503=keyplane/অবকাঠামো অপ্রাপ্য (retry-যোগ্য)
- retry শুধু 502/503-তে — 401/429 কখনো retry নয় (429-এ Retry-After সম্মান)
- 429-এ server Retry-After হেডার দিলে সেটা `err.retry_after`-এ বহন হয় — caller সম্মান করতে পারে (CONSUMERS.md §৩)
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = os.getenv(
    "SUPREMEAI_GATEWAY_URL", "https://supremeai-api-ulw0.onrender.com"
)
RETRY_BACKOFF_S = 2.0


class GatewayError(RuntimeError):
    """বাংলা: সব gateway-ত্রুটির মূল — status_code বহন করে।

    retry_after (str | None): শুধু 429-এ সেট হতে পারে — server-এর Retry-After
    হেডারের raw মান (সেকেন্ড বা HTTP-date)। caller এটা সম্মান করবে (CONSUMERS.md §৩)।
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        retry_after: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


class GatewayAuthError(GatewayError):
    """401 — key অবৈধ/বাতিল/মেয়াদোত্তীর্ণ। retry অর্থহীন।"""


class GatewayRateLimited(GatewayError):
    """429 — per-key সীমা ছাড়। Retry-After হেডার সম্মান করুন।"""


class GatewayProviderError(GatewayError):
    """502 — fallback chain শেষ, সব provider ব্যর্থ। সৎ ব্যর্থতা।"""


class GatewayUnavailable(GatewayError):
    """503 — keyplane/অবকাঠামো অপ্রাপ্য। retry-যোগ্য।"""


def chat(
    messages: list[dict],
    model: str = "auto",
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: float = 90.0,
    retries: int = 2,
) -> dict:
    """OpenAI-compatible চুক্তিতে chat-completion। provider-অজ্ঞেয়বাদী।"""
    key = api_key or os.getenv("SUPREMEAI_API_KEY")
    if not key:
        raise GatewayAuthError("SUPREMEAI_API_KEY নেই — vault/env যাচাই করুন", 401)
    base = (base_url or DEFAULT_BASE_URL).rstrip("/")
    payload: dict = {"model": model, "messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    last: GatewayError | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            f"{base}/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"X-SupremeAI-Key": key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode()[:200]
            except Exception:
                pass
            code = exc.code
            if code == 401:
                raise GatewayAuthError(f"invalid key: {body}", 401) from exc
            if code == 429:
                # বাংলা: CONSUMERS.md §৩ — "429 → Retry-After সম্মান"। হেডার না দিলে
                # caller সম্মান করার কিছুই পেত না; এখন raw মান error-এই বহন হয়।
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                msg = f"rate limited: {body}"
                if retry_after:
                    msg = f"rate limited (Retry-After: {retry_after}): {body}"
                raise GatewayRateLimited(msg, 429, retry_after=retry_after) from exc
            if code == 502:
                last = GatewayProviderError(f"all providers failed: {body}", 502)
            elif code == 503:
                last = GatewayUnavailable(f"unavailable: {body}", 503)
            else:
                raise GatewayError(f"gateway error {code}: {body}", code) from exc
        except urllib.error.URLError as exc:
            # বাংলা: নেটওয়ার্ক-স্তরের ব্যর্থতা = অপ্রাপ্যতা, retry-যোগ্য
            last = GatewayUnavailable(f"network: {exc.reason}", 503)
        except (json.JSONDecodeError, OSError) as exc:
            # READ-PHASE FIX (2026-10-09): পড়া-পর্বের ব্যর্থতা — read/decode timeout
            # (socket.timeout/TimeoutError), ConnectionResetError, truncated body
            # (→ JSONDecodeError) — এরা URLError নয়, আগে uncaught escape করত এবং
            # retry-চুক্তি (শুধু 502/503) পেত না। চুক্তি অনুযায়ী এরাও 503-family।
            last = GatewayUnavailable(f"read: {exc}", 503)
        if attempt < retries:
            time.sleep(RETRY_BACKOFF_S * (attempt + 1))
    raise last if last else GatewayError("unreachable", None)


def health(
    *,
    base_url: str | None = None,
    path: str = "/health",
    timeout: float = 30.0,
) -> dict:
    """বাংলা: অ-প্রমাণীকৃত liveness probe — GET /health (alias /healthz)।

    #1620 (audit:finding) চুক্তি: example client এখন /healthz-ও exercise করে।
    HTTP 200 + status="healthy" = alive (docs/CONSUMERS.md HTTP-status branching);
    body field watchdog-দের চুক্তি নয় (redacted #1729)।
    """
    base = (base_url or DEFAULT_BASE_URL).rstrip("/")
    req = urllib.request.Request(f"{base}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise GatewayError(f"gateway error {exc.code} on {path}", exc.code) from exc
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        # বাংলা: chat()-এর সৎ-ব্যর্থতা চুক্তির মতোই — নেটওয়ার্ক/পড়া-পর্ব = 503-family
        raise GatewayUnavailable(f"network/read: {exc}", 503) from exc


def models(*, base_url: str | None = None, timeout: float = 30.0) -> list[dict]:
    """বাংলা: GET /v1/models — অ-প্রমাণীকৃত virtual-model list।

    #1620 চুক্তি: example client এখন /v1/models-ও exercise করে।
    live contract (2026-10-29, supremeai-api-ulw0): 200, key লাগে না,
    {"object": "list", "data": [{id, default_target, healthy_keys, ...}]}।
    """
    base = (base_url or DEFAULT_BASE_URL).rstrip("/")
    req = urllib.request.Request(f"{base}/v1/models", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        raise GatewayError(f"gateway error {exc.code} on /v1/models", exc.code) from exc
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        raise GatewayUnavailable(f"network/read: {exc}", 503) from exc
    return payload.get("data", [])


if __name__ == "__main__":
    # বাংলা: one-shot CLI — agent-script/শেল-বান্ধব
    # সৎ-ব্যর্থতা: typed GatewayError → এক-লাইন stderr + exit 1 (raw traceback নয়) —
    # CI/GitHub-automation consumer (CONSUMERS.md §৬) non-blocking `||` পলিসি নির্ভর করে।
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="SupremeAI Gateway client")
    parser.add_argument("--model", default="auto")
    parser.add_argument("--prompt")
    parser.add_argument(
        "--health",
        action="store_true",
        help="probe /health + /healthz (unauthenticated liveness)",
    )
    parser.add_argument(
        "--models",
        action="store_true",
        help="list /v1/models virtual models (unauthenticated)",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args()
    # বাংলা: mode-নির্বাচন — ঠিক একটি হতে হবে (chat XOR health XOR models)
    if sum([bool(args.prompt), args.health, args.models]) != 1:
        parser.error("exactly one of --prompt / --health / --models")
    try:
        if args.health:
            # বাংলা: #1620 — দুটো probe-path-ই exercise হয়, দুটোই 200 হতে হবে
            for probe_path in ("/health", "/healthz"):
                payload = health(base_url=args.base_url, path=probe_path)
                print(f"{probe_path}: {payload.get('status')}")
        elif args.models:
            for m in models(base_url=args.base_url):
                print(
                    f"{m.get('id')}  (default_target={m.get('default_target')}, "
                    f"healthy_keys={m.get('healthy_keys')})"
                )
        else:
            out = chat(
                [{"role": "user", "content": args.prompt}],
                model=args.model,
                base_url=args.base_url,
            )
            print(out["choices"][0]["message"]["content"])
    except GatewayError as err:
        print(f"{type(err).__name__}: {err}", file=sys.stderr)
        sys.exit(1)
