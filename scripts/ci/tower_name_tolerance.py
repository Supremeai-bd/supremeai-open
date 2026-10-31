#!/usr/bin/env python3
"""Tower tool-name tolerance — shared root cure for the rename-wave caller debt.

বাংলা (Zero-Recurrence U6): টাওয়ার-রেজিস্ট্রির নাম-ঢেউ দ্বিমুখী দোলন করে —
ঢেউ-১ (2026-10-29, #2454): `bridge_work_queue` → `bridge.work_queue`;
ঢেউ-৩ (2026-10-31, live): আবার ফেরকা (loop-এর প্রথম cure: loop-এর নিজের ২টি
কল-সাইট, এই মডিউলের পূর্বসূরি হেল্পারগুলি সেখানে landed c7290dc/#3845)।
অডিট (GLM Agent 31, এই সাইকেল) প্রথম-হাতে প্রমাণ করল একই শ্রেণির আরও
কল-সাইট CI-প্লেনে অন্ধ: closure_live_state_gate (bridge.work_order),
hollow_read_guard (bridge.work_queue), verdict_plane_gap_probe
(bridge.work_queue) — প্রতিটি মৃত-বানানের পরে টাওয়ার যে-সাড়া দেয় সেটি
JSON-RPC error নয়, HTTP-200 success envelope-এর isError content-text
("MCP error -32602: Tool <name> not found") — এক-আকৃতির প্রেডিকেট কলারকে
অন্ধ রাখে।

এই মডিউল একটিই ক্যাননিকাল ক্যুর: যুগ-লেজার নাম-তালিকা + ক্রমে-চেষ্টা +
প্রথম-জীবিত-জয়ী + সব-মৃতে সৎ fail-closed। নতুন ঢেউয়ে শুধু লেজারে এক এন্ট্রি।
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

# নাম-যুগ লেজার: দোলক-পরিবার → নথিভুক্ত বানানগুলির ক্রম (পুরনো → নতুন)।
# পরীক্ষার প্রমাণ: দুটি বানানই কোনো না কোনো যুগে জীবিত ছিল; যে-কোনো মুহূর্তে
# একটি জীবিত, একটি মৃত — ক্রমে চেষ্টা করলে ভবিষ্যৎ বিপরীত ঢেউও নিরাপদ।
TOOL_NAME_EPOCHS: dict[str, tuple[str, ...]] = {
    "bridge.work_queue": ("bridge.work_queue", "bridge_work_queue"),
    "bridge.work_order": ("bridge.work_order", "bridge_work_order"),
    "github.list_prs": ("github.list_prs", "github_list_prs"),
}


def epoch_spellings(canonical: str) -> tuple[str, ...]:
    """নথিভুক্ত বানান-তালিকা; অজানা নাম হলে সেটিই একক-এন্ট্রি তালিকা (সৎ ডিফল্ট)।"""
    return TOOL_NAME_EPOCHS.get(canonical, (canonical,))


def is_tool_not_found_error_env(env: Any) -> bool:
    """JSON-RPC error envelope-এ অজানা-নাম চিনে (code -32602 / 'not found')।"""
    if not isinstance(env, dict) or "error" not in env:
        return False
    err = env.get("error")
    if isinstance(err, dict):
        msg = str(err.get("message", ""))
        code = err.get("code")
    else:
        msg, code = str(err), None
    return code == -32602 or "-32602" in msg or "not found" in msg.lower()


def envelope_says_tool_not_found(resp: Any) -> bool:
    """তিন আকৃতিতেই মৃত-নাম ধরে: error envelope + isError content-text + raw text।

    বাংলা: টাওয়ার মৃত-নামে JSON-RPC error দেয় না — HTTP-200 success
    envelope-এর isError content-text-এ দেয় (live 2026-10-31, প্রথম-হাতে)।
    আরও সূক্ষ্ম: কিছু কলার (যেমন verdict_plane_gap_probe-এর tool_text) পুরো
    envelope না-খুলেই content-text-এর জোড়া str ফেরত দেয় — সেই আকৃতিতেও
    মৃত-নামের স্বাক্ষর "-32602" + "not found" খালি চোখে পড়ে, তাই str-ও ধরা
    হয়; নইলে মোড়ানো কলার প্রথম (মৃত) বানানের ত্রুটিপাঠেই আটকে থাকে।
    """
    if is_tool_not_found_error_env(resp):
        return True
    if isinstance(resp, str):
        low = resp.lower()
        return "-32602" in low and "not found" in low
    if not isinstance(resp, dict):
        return False
    # বাংলা: চতুর্থ আকৃতি (watchdog-funnel, live 2026-10-31 GLM Agent 11) —
    # JSON-RPC success envelope যার result.content-ই isError text বহন করে
    # ({"jsonrpc","id","result":{"content":[{"text":"MCP error -32602: ..."}]}})।
    # এটাই MCP tools/call-এর স্ট্যান্ডার্ড রেসপন্স শেপ; top-level content-শাখা
    # এই আকৃতিতে অন্ধ ছিল বলে funnel-কলার মৃত বানান চিনতে পারে নি।
    content = resp.get("content")
    if not isinstance(content, list):
        result = resp.get("result")
        content = result.get("content") if isinstance(result, dict) else None
    if not isinstance(content, list):
        return False
    for item in content:
        if isinstance(item, dict):
            txt = str(item.get("text") or "").lower()
            if "-32602" in txt and "not found" in txt:
                return True
    return False


def call_across_names(call_by_name: Callable[[str], Any], names: tuple[str, ...]) -> Any:
    """প্রতিটি বানান ক্রমে চেষ্টা; প্রথম জীবিত সাড়া জয়ী; সব-মৃতে সৎ ব্যর্থতা।

    - কোনো বানান সফল (raise নেই এবং not-found নয়) → সেই সাড়াই।
    - not-found সাড়া → পরের বানান।
    - exception → স্মরণে রাখা হয়; সব-ব্যর্থে শেষ exception পুনঃউত্থাপন
      (fail-closed — কলারের সৎ ব্যর্থতা-নোট সত্য থাকে)।
    - সব বানান not-found কিন্তু কোনো exception নেই → শেষ not-found সাড়াই
      ফেরত (কলারের নিজের আকৃতি-হ্যান্ডলিং সত্য রিপোর্ট করবে)।
    """
    last_exc: Exception | None = None
    last_resp: Any = None
    for name in names:
        try:
            resp = call_by_name(name)
        except Exception as exc:  # noqa: BLE001 — যুগ-সহনশীলতাই এখানে উদ্দেশ্য
            last_exc = exc
            continue
        if envelope_says_tool_not_found(resp):
            last_resp = resp
            continue
        return resp
    if last_exc is not None:
        raise last_exc
    return last_resp


def tolerant_tool_call(call: Callable[[str, dict], Any], canonical: str,
                       arguments: dict | None = None) -> Any:
    """সুবিধা-প্রবেশ: canonical নামের যুগ-তালিকা নিয়ে (name, args) স্টাইল কলার মোড়ে।

    বাংলা: কলার যেমন ছিল তেমন রাখা হয় — শুধু নাম-নির্বাচনটা ঢেউ-অজ্ঞেস্থ হয়।
    """
    args = arguments if arguments is not None else {}
    return call_across_names(lambda n: call(n, args), epoch_spellings(canonical))
