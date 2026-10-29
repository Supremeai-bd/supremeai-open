#!/usr/bin/env python3
"""Zero-credential Tower MCP exposure probe — standing machine check (issue #2076).

বাংলা: এই স্ক্রিপ্টটি #2076-এর deliverable-B-র ভিত্তি — anonymous (zero-credential)
MCP ক্লায়েন্ট হয়ে tower-এ initialize handshake + tools/list চালায় এবং বিজ্ঞাপিত
tool তালিকায় secret-class / destructive-class নাম-প্যাটার্ন স্ক্যান করে। চুক্তি:

  exit 0 "pass" : বিজ্ঞাপিত ∩ {secret,destructive} = ∅ এবং সংখ্যা ≤ baseline
  exit 1        : যেকোনো secret/destructive প্রার্থী বিজ্ঞাপিত, বা সংখ্যা > baseline
                  (fail-close — নীরব পাস নেই)
  exit 0 "skip" : tower অনুপলব্ধ (honest-skip, #1760 অফলাইন-মতবাদ; নেটওয়ার্ক
                  নেই এমন CI-তে মিথ্যা লাল নয়)

শিকার-নীতি (invitation-only evidence): এই প্রোব কোনো বিজ্ঞাপিত tool **চালায় না** —
শুধু tools/list মেটাডেটা পড়ে। render_get_env_vars-এর মতো secret-class tool-এর
নাম বিজ্ঞাপিত হওয়াটাই নীতি-লঙ্ঘন; এক্সিকিউশন ছাড়াই প্রমাণ যথেষ্ট এবং নিরাপদ।

নাম-প্যাটার্ন বনাম tower-এর নিজস্ব capability শ্রেণিবিন্যাস (mcp-access.ts): প্যাটার্ন
ভিত্তিধর্মী স্ক্যান প্রার্থী (candidate) দেয়, চূড়ান্ত শ্রেণি নয় — তাই রিপোর্টে দুই
সংখ্যার পার্থক্য সৎভাবে থাকে (#2076: 5 destructive + 4 secret; এই প্রোব প্যাটার্নে
আরও প্রার্থী দেখতে পায়)। advertised ⊆ tree-registry অ্যাসার্শনের জন্য tower-রিপো
রেজিস্ট্রি দরকার — সেটি tower-লেনে (maintainer), এখানে সৎভাবে বাদ।

ব্যবহার:
  python scripts/tower_discovery_probe.py                # মানব-পাঠ্য রিপোর্ট
  python scripts/tower_discovery_probe.py --json         # মেশিন-রিসিট (archive)
  python scripts/tower_discovery_probe.py --baseline FILE # shrink-only ratchet
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request

DEFAULT_URL = "https://supremeai-mcp-tower.onrender.com/mcp"

SECRET_PATTERNS = (
    "secret", "env_var", "envvar", "credential", "token", "_key", "key_",
)
DESTRUCTIVE_PATTERNS = (
    "delete", "destroy", "drop_", "_drop", "reset", "rotate", "kill",
    "purge", "approve", "set_env", "provision", "deploy", "revoke",
)


def post(url: str, payload: dict, session_id: str | None, timeout: float):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            return resp.status, resp.headers.get("Mcp-Session-Id"), body
    except urllib.error.HTTPError as exc:
        return exc.code, None, exc.read().decode()
    except Exception as exc:  # noqa: BLE001 — honest-skip path needs the string
        return -1, None, str(exc)


def parse_sse(body: str) -> dict | None:
    if not body:
        return None
    if body.lstrip().startswith("{"):
        try:
            return json.loads(body)
        except Exception:
            return None
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            data = line[5:].strip()
            if data and data != "[DONE]":
                try:
                    return json.loads(data)
                except Exception:
                    pass
    return None


def zero_credential_tools_list(url: str, timeout: float):
    """বাংলা: কোনো টোকেন/প্রমাণ ছাড়া anonymous handshake → tools/list।"""
    status, sid, body = post(url, {
        "jsonrpc": "2.0", "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "tower-exposure-probe", "version": "1.0"},
        },
        "id": 1,
    }, None, timeout)
    if status != 200 or not sid:
        return None, f"initialize failed: status={status} body={body[:200]}"
    post(url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, sid, timeout)
    status, _, body = post(
        url, {"jsonrpc": "2.0", "method": "tools/list", "id": 2}, sid, timeout
    )
    if status != 200:
        return None, f"tools/list failed: status={status}"
    parsed = parse_sse(body)
    if not parsed or "result" not in parsed:
        return None, "tools/list: unparseable envelope"
    return parsed["result"].get("tools", []), None


def classify(names: list[str]) -> tuple[list[str], list[str]]:
    secret = [n for n in names if any(p in n.lower() for p in SECRET_PATTERNS)]
    destructive = [n for n in names if any(p in n.lower() for p in DESTRUCTIVE_PATTERNS)]
    return sorted(set(secret)), sorted(set(destructive))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--baseline", type=str, default="",
                        help="JSON file with prior receipt; advertised-count may only shrink")
    parser.add_argument("--out", type=str, default="", help="write receipt JSON here")
    args = parser.parse_args()

    receipt: dict = {
        "check": "tower_exposure_probe",
        "url": args.url,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "zero_credential": True,
        "executed_advertised_tools": 0,
    }

    tools, err = zero_credential_tools_list(args.url, args.timeout)
    if tools is None:
        receipt.update({"status": "skip", "reason": err})
        print(json.dumps(receipt, indent=2) if args.as_json else f"skip: {err}")
        return 0  # honest-skip: unreachable tower is not a red CI

    names = [str(t.get("name", "")) for t in tools if isinstance(t, dict)]
    secret, destructive = classify(names)
    receipt.update({
        "status": None,  # decided below (fail-close)
        "advertised_count": len(names),
        "secret_class_candidates": secret,
        "destructive_class_candidates": destructive,
        "classification_basis": "name-pattern (candidate-level; tower capability classification lives in mcp-access.ts)",
        "policy": "advertised ∩ {secret-class, destructive-class} = ∅; advertised count shrink-only",
    })

    violations: list[str] = []
    if secret:
        violations.append(f"secret-class candidates advertised: {', '.join(secret)}")
    if destructive:
        violations.append(f"destructive-class candidates advertised: {', '.join(destructive)}")

    if args.baseline:
        try:
            with open(args.baseline, encoding="utf-8") as fh:
                prior = json.load(fh)
            prior_count = int(prior.get("advertised_count", 0))
            if len(names) > prior_count:
                violations.append(
                    f"advertised count grew: {prior_count} -> {len(names)} (shrink-only ratchet)"
                )
            receipt["baseline_count"] = prior_count
        except Exception as exc:  # noqa: BLE001
            violations.append(f"baseline unreadable ({exc}) — fail-close")

    receipt["status"] = "violation" if violations else "pass"
    receipt["violations"] = violations

    rendered = json.dumps(receipt, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(rendered + "\n")
    if args.as_json:
        print(rendered)
    else:
        print(
            f"{receipt['status']}: {len(names)} tools advertised "
            f"({len(secret)} secret-class / {len(destructive)} destructive-class candidates)"
        )
        for v in violations:
            print(f"  - {v}")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
