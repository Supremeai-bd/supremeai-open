#!/usr/bin/env python3
"""Token rotation verification (Wave 0.4 — issue #1234, register R10).

R10: মুছে ফেলা pseudo-config ফাইলে পেস্ট করা CI log-এ সম্ভাব্য Render/GitHub
token ছিল। ফাইল deleted, কিন্তু "rotation করেছি" দাবি আর "পুরনো token মরে
গেছে" প্রমাণ — দুটো আলাদা। এই হার্নেস প্রমাণটা machine-checkable করে:

* candidate token শুধু ``GITHUB_PROBE_TOKEN`` env থেকে নেওয়া হয় — argv,
  stdout, log, exception message — কোথাওই token material প্রিন্ট হয় না;
* GitHub API ``GET /user`` probe:
    401 → REVOKED/invalid  (নিরাপদ — এটাই প্রত্যাশিত "পুরনো টোকেন মরে গেছে")
    200 → **ACTIVE**        (CRITICAL alarm — leaked token এখনো বেঁচে আছে!)
    403/5xx/network → INCONCLUSIVE (manual যাচাই লাগবে);
* ``--self-test`` injectable fetcher দিয়ে তিনটা response class + token
  non-disclosure যাচাই করে (network-free, CI-safe)।

Usage:
    python scripts/security/verify_token_rotation.py --self-test
    GITHUB_PROBE_TOKEN=<old-token> python scripts/security/verify_token_rotation.py --github
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

PROBE_TOKEN_ENV = "GITHUB_PROBE_TOKEN"
USER_AGENT = "supremeai-token-rotation-verify (issue #1234)"
MASKED = "***masked***"


class Verdict(str):
    """Probe verdicts (str subclass for clean printing)."""

    REVOKED = "REVOKED"
    ACTIVE = "ACTIVE"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class ProbeResult:
    verdict: str
    status: int | None
    detail: str


def probe_github(token: str, fetcher=None) -> ProbeResult:
    """Probe one candidate token against GET /user. Never logs the token."""
    if fetcher is None:

        def fetcher(url: str, headers: dict[str, str]) -> tuple[int, str]:
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return resp.status, resp.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as exc:
                return exc.code, exc.read().decode("utf-8", errors="replace")

    headers = {
        "Authorization": f"token {token}",
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    }
    try:
        status, _body = fetcher("https://api.github.com/user", headers)
    except Exception:  # noqa: BLE001 — probe must degrade to INCONCLUSIVE
        return ProbeResult(
            Verdict.INCONCLUSIVE, None, "network error (details suppressed)"
        )

    if status == 401:
        return ProbeResult(
            Verdict.REVOKED, status, "token rejected — rotation VERIFIED for this token"
        )
    if status == 200:
        return ProbeResult(
            Verdict.ACTIVE,
            status,
            "token is ALIVE — CRITICAL: revoke it immediately and audit its usage",
        )
    if status == 403:
        return ProbeResult(
            Verdict.INCONCLUSIVE,
            status,
            "403 (rate limit / resource restriction) — retry later",
        )
    return ProbeResult(
        Verdict.INCONCLUSIVE, status, "unexpected status — manual check required"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--github",
        action="store_true",
        help=f"probe the token in ${PROBE_TOKEN_ENV} against GET /user",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="verify harness logic (offline)"
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    if args.github:
        import os

        token = (os.getenv(PROBE_TOKEN_ENV, "") or "").strip()
        if not token:
            print(
                f"FAIL: ${PROBE_TOKEN_ENV} is empty — provide the candidate token via env only."
            )
            return 2
        result = probe_github(token)
        print(f"[{result.verdict}] status={result.status} — {result.detail}")
        if result.verdict == Verdict.ACTIVE:
            return 1
        if result.verdict == Verdict.INCONCLUSIVE:
            return 3
        return 0

    parser.print_help()
    return 2


def self_test() -> int:
    failures: list[str] = []

    # 1. 401 → REVOKED
    result = probe_github(
        "fake-token",
        fetcher=lambda url, headers: (401, '{"message":"Bad credentials"}'),
    )
    if result.verdict != Verdict.REVOKED:
        failures.append(f"401 must map to REVOKED, got {result.verdict}")

    # 2. 200 → ACTIVE
    result = probe_github(
        "fake-token", fetcher=lambda url, headers: (200, '{"login":"attacker"}')
    )
    if result.verdict != Verdict.ACTIVE:
        failures.append(f"200 must map to ACTIVE, got {result.verdict}")

    # 3. 403 → INCONCLUSIVE
    result = probe_github(
        "fake-token", fetcher=lambda url, headers: (403, '{"message":"rate limit"}')
    )
    if result.verdict != Verdict.INCONCLUSIVE:
        failures.append(f"403 must map to INCONCLUSIVE, got {result.verdict}")

    # 4. network exception → INCONCLUSIVE (never crashes)
    def _boom(url: str, headers: dict[str, str]) -> tuple[int, str]:
        raise OSError("network down")

    result = probe_github("fake-token", fetcher=_boom)
    if result.verdict != Verdict.INCONCLUSIVE:
        failures.append("network error must map to INCONCLUSIVE")

    # 5. token material must never appear in verdict/detail output
    secret = "ghp_SUPERSECRET1234567890"
    for fetcher in (
        lambda url, headers: (401, "nope"),
        lambda url, headers: (200, "nope"),
        _boom,
    ):
        result = probe_github(secret, fetcher=fetcher)
        if secret in f"{result.verdict}{result.detail}":
            failures.append("token material leaked into output")

    # 6. auth header actually carries the token (probe correctness)
    captured: dict[str, str] = {}

    def _capture(url: str, headers: dict[str, str]) -> tuple[int, str]:
        captured.update(headers)
        return 401, "{}"

    probe_github(secret, fetcher=_capture)
    if captured.get("Authorization") != f"token {secret}":
        failures.append("Authorization header not constructed correctly")

    if failures:
        print("SELF-TEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(
        "SELF-TEST PASSED — verdict mapping, fail-open safety, non-disclosure verified"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
