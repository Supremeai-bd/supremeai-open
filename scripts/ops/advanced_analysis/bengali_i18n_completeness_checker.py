#!/usr/bin/env python3
"""বাংলা i18n সম্পূর্ণতা পরীক্ষক — SupremeAI frontend অনুবাদ ফাইলের ইংরেজি (en) ও বাংলা (bn) কীগুলো
তুলনা করে অনুবাদের গ্যাপ খুঁজে বের করে।

ব্যবহার:
    python scripts/bengali_i18n_completeness_checker.py
    python scripts/bengali_i18n_completeness_checker.py --json
    python scripts/bengali_i18n_completeness_checker.py --category admin_metrics
    python scripts/bengali_i18n_completeness_checker.py --missing-only

এক্সিট কোড:
    0 — ১০০% সম্পূর্ণ (কোনো গ্যাপ নেই)
    1 — গ্যাপ পাওয়া গেছে (মিসিং, প্লেসহোল্ডার, ইত্যাদি)
    2 — ত্রুটি (ফাইল পাওয়া যায়নি, পার্স করতে সমস্যা)

সম্পূরক স্ক্রিপ্ট: scripts/i18n/rtl_support_checker.py (RTL সাপোর্ট পরীক্ষা)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


# ─── কনফিগারেশন ───────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TRANSLATIONS_PATH = REPO_ROOT / "frontend" / "src" / "i18n" / "translations.ts"
DEFAULT_BACKEND_PATH = REPO_ROOT / "backend"
INTERPOLATION_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
BANGLA_CHAR_RE = re.compile(r"[\u0980-\u09FF]")

USER_FACING_PREFIXES = (
    "appName", "send", "thinking", "newChat", "settings",
    "ud_", "user_", "chat_", "auth_", "login_", "signup_",
    "home_", "profile_", "error_", "success_", "nav_",
    "common_", "general_", "search_", "filter_", "help_",
)
ADMIN_PREFIXES = ("admin_",)


# ─── স্ট্যাটাস ধরন ──────────────────────────────────────────────────────────────

STATUS_MISSING = "MISSING"
STATUS_PLACEHOLDER = "PLACEHOLDER"
STATUS_EMPTY = "EMPTY"
STATUS_TRANSLATED = "TRANSLATED"
STATUS_EXTRA = "EXTRA"

STATUS_EMOJI = {
    STATUS_MISSING: "\U0001f534",  # 🔴
    STATUS_PLACEHOLDER: "\U0001f7e1",  # 🟡
    STATUS_EMPTY: "\U0001f7e1",  # 🟡
    STATUS_TRANSLATED: "\U0001f7e2",  # 🟢
    STATUS_EXTRA: "\U0001f535",  # 🔵
}

STATUS_LABEL_BN = {
    STATUS_MISSING: "অনুপস্থিত",
    STATUS_PLACEHOLDER: "কপি-পেস্ট (অনুবাদ হয়নি)",
    STATUS_EMPTY: "খালি স্ট্রিং",
    STATUS_TRANSLATED: "অনুবাদিত",
    STATUS_EXTRA: "অতিরিক্ত (পুরনো)",
}


# ─── পার্সার ────────────────────────────────────────────────────────────────────


def extract_lang_block(content: str, lang_code: str) -> Optional[str]:
    """অনুবাদ ফাইল থেকে নির্দিষ্ট ভাষার ব্লক বের করে (ব্রেস কাউন্টিং সহ)।"""
    pattern = re.compile(r"^\s+" + re.escape(lang_code) + r"\s*:\s*\{", re.MULTILINE)
    match = pattern.search(content)
    if not match:
        return None

    start = match.end()
    brace_count = 1
    pos = start
    length = len(content)
    in_string = False
    string_char = None

    while pos < length and brace_count > 0:
        ch = content[pos]
        if in_string:
            if ch == "\\" and pos + 1 < length:
                pos += 2
                continue
            if ch == string_char:
                in_string = False
        else:
            if ch in ("'", '"'):
                in_string = True
                string_char = ch
            elif ch == "{":
                brace_count += 1
            elif ch == "}":
                brace_count -= 1
        pos += 1

    if brace_count != 0:
        return None
    return content[start : pos - 1]


def flatten_ts_object(block: str, prefix: str = "") -> Dict[str, str]:
    """TypeScript অবজেক্ট ব্লককে ফ্ল্যাট ডিকশনারিতে রূপান্তর করে (ডট-নোটেশন)।"""
    result: Dict[str, str] = {}
    no_comments = re.sub(r"//.*$", "", block, flags=re.MULTILINE)
    no_comments = re.sub(r"/\*.*?\*/", "", no_comments, flags=re.DOTALL)
    no_comments = re.sub(r",\s*\}", "}", no_comments)
    _parse_object(no_comments.strip(), prefix, result)
    return result


def _parse_object(text: str, prefix: str, result: Dict[str, str]) -> None:
    """রিকার্সিভভাবে TS অবজেক্ট পার্স করে।"""
    text = text.strip()
    if not text or text == "{}":
        return
    if text.startswith("{") and text.endswith("}"):
        text = text[1:-1].strip()

    pos = 0
    length = len(text)
    while pos < length:
        # হোয়াইটস্পেস স্কিপ
        while pos < length and text[pos] in " \t\n\r":
            pos += 1
        if pos >= length:
            break

        # কী পড়ুন
        key_match = re.match(r"([A-Za-z_$][A-Za-z0-9_$]*)", text[pos:])
        if not key_match:
            pos += 1
            continue
        key = key_match.group(1)
        pos += key_match.end()

        # কোলন স্কিপ
        while pos < length and text[pos] in " \t\n\r":
            pos += 1
        if pos < length and text[pos] == ":":
            pos += 1
        while pos < length and text[pos] in " \t\n\r":
            pos += 1
        if pos >= length:
            break

        # মান নির্ধারণ
        if text[pos] in ("'", '"'):
            # স্ট্রিং লিটারাল
            quote = text[pos]
            pos += 1
            vc: List[str] = []
            while pos < length and text[pos] != quote:
                if text[pos] == "\\" and pos + 1 < length:
                    vc.append(text[pos])
                    vc.append(text[pos + 1])
                    pos += 2
                else:
                    vc.append(text[pos])
                    pos += 1
            if pos < length:
                pos += 1  # ক্লোজিং কোট স্কিপ
            full_key = f"{prefix}.{key}" if prefix else key
            result[full_key] = "".join(vc)
        elif text[pos] == "{":
            # নেস্টেড অবজেক্ট
            bc = 1
            start = pos + 1
            pos += 1
            in_s = False
            sc = None
            while pos < length and bc > 0:
                c = text[pos]
                if in_s:
                    if c == "\\" and pos + 1 < length:
                        pos += 2
                        continue
                    if c == sc:
                        in_s = False
                else:
                    if c in ("'", '"'):
                        in_s = True
                        sc = c
                    elif c == "{":
                        bc += 1
                    elif c == "}":
                        bc -= 1
                pos += 1
            nested = text[start : pos - 1]
            np_ = f"{prefix}.{key}" if prefix else key
            _parse_object(nested, np_, result)
        else:
            # অন্যান্য মান — স্কিপ
            while pos < length and text[pos] not in (",}") and text[pos] not in "\n\r":
                pos += 1

        # কমা স্কিপ
        while pos < length and text[pos] in " \t":
            pos += 1
        if pos < length and text[pos] == ",":
            pos += 1


# ─── বিশ্লেষণ ফাংশন ────────────────────────────────────────────────────────────


def get_category(key: str) -> str:
    """কী থেকে ক্যাটেগরি নির্ধারণ করে।

    admin_metrics.apiStatus -> admin_metrics
    ud_welcome -> ud
    appName -> general
    """
    dot = key.find(".")
    if dot > 0:
        return key[:dot]
    us = key.find("_")
    if us > 0:
        return key[:us]
    return "general"


def is_user_facing(key: str) -> bool:
    """কী ইউজার-ফেসিং কিনা নির্ধারণ করে।"""
    cat = get_category(key)
    if cat.startswith("admin"):
        return False
    for p in USER_FACING_PREFIXES:
        if key.startswith(p):
            return True
    for p in ADMIN_PREFIXES:
        if key.startswith(p):
            return False
    return True


def get_interpolations(value: str) -> Set[str]:
    """স্ট্রিং থেকে ইন্টারপোলেশন প্লেসহোল্ডার সেট বের করে।

    উদাহরণ: "Welcome, {name}!" -> {"name"}
    """
    return set(INTERPOLATION_RE.findall(value))


def contains_bangla(text: str) -> bool:
    """টেক্সটে বাংলা ক্যারেক্টার আছে কিনা চেক করে।"""
    return bool(BANGLA_CHAR_RE.search(text))


def compare_translations(
    en: Dict[str, str], bn: Dict[str, str]
) -> List[Dict[str, Any]]:
    """en ও bn অনুবাদ তুলনা করে প্রতিটি কী-এর স্ট্যাটাস রিটার্ন করে।"""
    results: List[Dict[str, Any]] = []
    en_keys = set(en.keys())
    bn_keys = set(bn.keys())

    for key in sorted(en_keys):
        en_val = en[key]
        if key not in bn:
            results.append({
                "key": key,
                "en": en_val,
                "bn": None,
                "status": STATUS_MISSING,
                "user_facing": is_user_facing(key),
                "category": get_category(key),
                "en_placeholders": get_interpolations(en_val),
                "bn_placeholders": set(),
                "placeholder_mismatch": False,
            })
            continue

        bn_val = bn[key]
        en_ph = get_interpolations(en_val)
        bn_ph = get_interpolations(bn_val)
        ph_mismatch = en_ph != bn_ph

        if bn_val.strip() == "":
            st = STATUS_EMPTY
        elif bn_val == en_val:
            st = STATUS_PLACEHOLDER
        else:
            st = STATUS_TRANSLATED

        results.append({
            "key": key,
            "en": en_val,
            "bn": bn_val,
            "status": st,
            "user_facing": is_user_facing(key),
            "category": get_category(key),
            "en_placeholders": en_ph,
            "bn_placeholders": bn_ph,
            "placeholder_mismatch": ph_mismatch,
        })

    # bn এ আছে কিন্তু en এ নেই — EXTRA
    for key in sorted(bn_keys - en_keys):
        bn_val = bn[key]
        results.append({
            "key": key,
            "en": None,
            "bn": bn_val,
            "status": STATUS_EXTRA,
            "user_facing": is_user_facing(key),
            "category": get_category(key),
            "en_placeholders": set(),
            "bn_placeholders": get_interpolations(bn_val),
            "placeholder_mismatch": False,
        })

    return results


def build_category_breakdown(
    results: List[Dict[str, Any]]
) -> Dict[str, Dict[str, int]]:
    """ক্যাটেগরি অনুযায়ী স্ট্যাটাস সারাংশ তৈরি করে।"""
    bd: Dict[str, Dict[str, int]] = OrderedDict()
    for r in results:
        cat = r["category"]
        if cat not in bd:
            bd[cat] = {
                STATUS_TRANSLATED: 0,
                STATUS_MISSING: 0,
                STATUS_PLACEHOLDER: 0,
                STATUS_EMPTY: 0,
                STATUS_EXTRA: 0,
                "total_en": 0,
            }
        if r["en"] is not None:
            bd[cat]["total_en"] += 1
        bd[cat][r["status"]] += 1
    return bd


def calculate_completeness(results: List[Dict[str, Any]]) -> float:
    """অনুবাদ সম্পূর্ণতার শতাংশ হিসাব করে।

    সূত্র: (TRANSLATED / মোট en কী) x 100
    """
    en_total = sum(1 for r in results if r["en"] is not None)
    if en_total == 0:
        return 100.0
    translated = sum(1 for r in results if r["status"] == STATUS_TRANSLATED)
    return (translated / en_total) * 100.0


# ─── ব্যাকএন্ড স্ক্যানার ──────────────────────────────────────────────────────────


def scan_backend_bangla_strings(backend_path: Path) -> List[Dict[str, Any]]:
    """ব্যাকএন্ডে হার্ডকোডেড বাংলা স্ট্রিং স্ক্যান করে।

    localization/, tests/, __pycache__/, alembic_migrations/, docs/ বাদ দেওয়া হয়।
    """
    findings: List[Dict[str, Any]] = []
    if not backend_path.exists():
        return findings

    # কোটের ভেতরে বাংলা ক্যারেক্টার — সিঙ্গেল এবং ডাবল কোট আলাদাভাবে
    bangla_single_re = re.compile(r"'(?:[^'\\]|\\.)*'")
    bangla_double_re = re.compile(r'"(?:[^"\\]|\\.)*"')
    skip_dirs = {"localization", "tests", "__pycache__", "alembic_migrations", "docs"}

    for py_file in backend_path.rglob("*.py"):
        parts = py_file.relative_to(backend_path).parts
        if any(p in skip_dirs for p in parts):
            continue
        try:
            content = py_file.read_text(encoding="utf-8")
        except Exception:
            continue
        # কমেন্ট সরান
        no_cmt = re.sub(r"#.*$", "", content, flags=re.MULTILINE)
        no_cmt = re.sub(r'""".*?"""', "", no_cmt, flags=re.DOTALL)
        no_cmt = re.sub(r"'''.*?'''", "", no_cmt, flags=re.DOTALL)
        for m in bangla_single_re.finditer(no_cmt):
            s = m.group(0)[1:-1].strip()
            if len(s) >= 2 and contains_bangla(s):
                findings.append({
                    "file": str(py_file.relative_to(REPO_ROOT)),
                    "string": s,
                    "line": content[: m.start()].count("\n") + 1,
                })
        for m in bangla_double_re.finditer(no_cmt):
            s = m.group(0)[1:-1].strip()
            if len(s) >= 2 and contains_bangla(s):
                findings.append({
                    "file": str(py_file.relative_to(REPO_ROOT)),
                    "string": s,
                    "line": content[: m.start()].count("\n") + 1,
                })
    return findings


# ─── রিপোর্ট তৈরি ───────────────────────────────────────────────────────────────


def build_report(
    results: List[Dict[str, Any]],
    en: Dict[str, str],
    bn: Dict[str, str],
    backend_findings: List[Dict[str, Any]],
    translations_path: str,
) -> Dict[str, Any]:
    """সম্পূর্ণ JSON রিপোর্ট তৈরি করে।"""
    tr = sum(1 for r in results if r["status"] == STATUS_TRANSLATED)
    mi = sum(1 for r in results if r["status"] == STATUS_MISSING)
    pl = sum(1 for r in results if r["status"] == STATUS_PLACEHOLDER)
    em = sum(1 for r in results if r["status"] == STATUS_EMPTY)
    ex = sum(1 for r in results if r["status"] == STATUS_EXTRA)
    comp = calculate_completeness(results)
    ph_mm = [r for r in results if r["placeholder_mismatch"]]
    uf_gaps = [
        r
        for r in results
        if r["user_facing"]
        and r["status"] in (STATUS_MISSING, STATUS_PLACEHOLDER, STATUS_EMPTY)
    ]

    return {
        "translations_file": translations_path,
        "summary": {
            "total_en_keys": len(en),
            "total_bn_keys": len(bn),
            "translated": tr,
            "missing": mi,
            "placeholder": pl,
            "empty": em,
            "extra_in_bn": ex,
            "completeness_percent": round(comp, 1),
            "is_100_percent": comp >= 99.99,
        },
        "category_breakdown": build_category_breakdown(results),
        "user_facing_gaps": [
            {"key": r["key"], "en": r["en"], "bn": r["bn"], "status": r["status"]}
            for r in uf_gaps
        ],
        "all_issues": [
            {
                "key": r["key"],
                "en": r["en"],
                "bn": r["bn"],
                "status": r["status"],
                "category": r["category"],
                "user_facing": r["user_facing"],
                "placeholder_mismatch": r["placeholder_mismatch"],
                "en_placeholders": sorted(r["en_placeholders"]),
                "bn_placeholders": sorted(r["bn_placeholders"]),
            }
            for r in results
            if r["status"] != STATUS_TRANSLATED or r["placeholder_mismatch"]
        ],
        "placeholder_mismatches": [
            {
                "key": r["key"],
                "en": r["en"],
                "bn": r["bn"],
                "en_placeholders": sorted(r["en_placeholders"]),
                "bn_placeholders": sorted(r["bn_placeholders"]),
            }
            for r in ph_mm
        ],
        "backend_bangla_strings": backend_findings,
        "rtl_checker_note": (
            "সম্পূরক স্ক্রিপ্ট: scripts/i18n/rtl_support_checker.py — "
            "এই স্ক্রিপ্ট অনুবাদ সম্পূর্ণতা চেক করে; "
            "RTL সাপোর্ট চেক করতে rtl_support_checker.py ব্যবহার করুন।"
        ),
    }


def _bn(text: str) -> str:
    """Bengali টেক্সট নিরাপদে রিটার্ন করে (ASCII fallback সহ)।"""
    try:
        return text.encode("utf-8").decode("utf-8")
    except Exception:
        return text.encode("ascii", errors="replace").decode("ascii")


def print_text_report(
    report: Dict[str, Any],
    category_filter: Optional[str] = None,
    missing_only: bool = False,
) -> None:
    """হিউম্যান-রিডেবল টার্মিনাল আউটপুট প্রিন্ট করে।"""
    s = report["summary"]
    sep = _bn("═") * 70
    thin = _bn("─") * 70
    e_tr = STATUS_EMOJI[STATUS_TRANSLATED]
    e_mi = STATUS_EMOJI[STATUS_MISSING]
    e_pl = STATUS_EMOJI[STATUS_PLACEHOLDER]
    e_em = STATUS_EMOJI[STATUS_EMPTY]
    e_ex = STATUS_EMOJI[STATUS_EXTRA]

    print()
    print(sep)
    print(_bn("  বাংলা i18n সম্পূর্ণতা পরীক্ষা — SupremeAI"))
    print(_bn(f"  ফাইল: {report['translations_file']}"))
    print(sep)
    print()

    # ── সারাংশ ──
    print(_bn(f"  ইংরেজি (en) কী:        {s['total_en_keys']}"))
    print(_bn(f"  বাংলা (bn) কী:         {s['total_bn_keys']}"))
    print(_bn(f"  অনুবাদিত ({e_tr}):          {s['translated']}"))
    print(_bn(f"  অনুপস্থিত ({e_mi}):          {s['missing']}"))
    print(_bn(f"  কপি-পেস্ট ({e_pl}):         {s['placeholder']}"))
    print(_bn(f"  খালি ({e_em}):               {s['empty']}"))
    print(_bn(f"  অতিরিক্ত ({e_ex}):           {s['extra_in_bn']}"))
    print()

    # ── সম্পূর্ণতা বার ──
    pct = s["completeness_percent"]
    bar_len = 40
    filled = int(bar_len * pct / 100)
    bar = _bn("█") * filled + _bn("░") * (bar_len - filled)
    print(_bn(f"  সম্পূর্ণতা: [{bar}] {pct}%"))
    print()

    if s["is_100_percent"]:
        print(_bn(f"  {e_tr} সব কী সঠিকভাবে অনুবাদিত হয়েছে!"))
    else:
        gaps = s["missing"] + s["placeholder"] + s["empty"]
        print(_bn(f"  {e_mi} {gaps}টি কী-এ গ্যাপ আছে (অনুবাদ প্রয়োজন)"))
    print()

    # ── ক্যাটেগরি ব্রেকডাউন ──
    bd = report["category_breakdown"]
    if bd:
        print(thin)
        # হেডার
        hdr_parts = [
            f"  {_bn('ক্যাটেগরি'):<22}",
            f"{'en':<5}",
            f"{e_tr} {_bn('অনুবাদিত'):<10}",
            f"{e_mi} {_bn('মিসিং'):<8}",
            f"{e_pl} {_bn('কপি'):<6}",
            f"{e_em} {_bn('খালি'):<6}",
            f"{e_ex} {_bn('অতিরিক্ত'):<8}",
        ]
        print("".join(hdr_parts))
        print(thin)
        for cat, counts in bd.items():
            if category_filter and cat != category_filter:
                continue
            t = counts["total_en"]
            tr_ = counts[STATUS_TRANSLATED]
            mi_ = counts[STATUS_MISSING]
            pl_ = counts[STATUS_PLACEHOLDER]
            em_ = counts[STATUS_EMPTY]
            ex_ = counts[STATUS_EXTRA]
            pct_cat = (tr_ / t * 100) if t > 0 else 100
            row_parts = [
                f"  {cat:<22}",
                f"{t:<5}",
                f"{e_tr} {tr_:<10}",
                f"{e_mi} {mi_:<8}",
                f"{e_pl} {pl_:<6}",
                f"{e_em} {em_:<6}",
                f"{e_ex} {ex_:<8}",
                f"  ({pct_cat:.0f}%)",
            ]
            print("".join(row_parts))
        print(thin)
        print()

    # ── সমস্যায়ুক্ত কী-র তালিকা ──
    issues = report["all_issues"]
    if category_filter:
        issues = [i for i in issues if i["category"] == category_filter]
    if missing_only:
        issues = [i for i in issues if i["status"] == STATUS_MISSING]

    if issues:
        print(thin)
        uf_issues = [i for i in issues if i["user_facing"]]
        admin_issues = [i for i in issues if not i["user_facing"]]

        if uf_issues:
            print(_bn(f"  ⚠️  ইউজার-ফেসিং গ্যাপ ({len(uf_issues)}):"))
            print(thin)
            for i in uf_issues:
                emoji = STATUS_EMOJI[i["status"]]
                en_val = (i["en"] or "")[:50]
                bn_val = (i["bn"] or "")[:50]
                print(f"  {emoji} {i['key']}")
                print(f"      en: {en_val}")
                print(f"      bn: {bn_val}")
                if i.get("placeholder_mismatch"):
                    print(
                        f"      ⚠️ প্লেসহোল্ডার মিসম্যাচ: "
                        f"en={sorted(i['en_placeholders'])} "
                        f"bn={sorted(i['bn_placeholders'])}"
                    )
                print()

        if admin_issues:
            print(_bn(f"  🔧 অ্যাডমিন-ইন্টারনাল গ্যাপ ({len(admin_issues)}):"))
            print(thin)
            for i in admin_issues:
                emoji = STATUS_EMOJI[i["status"]]
                en_val = (i["en"] or "")[:50]
                bn_val = (i["bn"] or "")[:50]
                print(f"  {emoji} {i['key']}")
                print(f"      en: {en_val}")
                print(f"      bn: {bn_val}")
                if i.get("placeholder_mismatch"):
                    print(
                        f"      ⚠️ placeholder মিসম্যাচ: "
                        f"en={sorted(i['en_placeholders'])} "
                        f"bn={sorted(i['bn_placeholders'])}"
                    )
                print()
    elif not missing_only:
        print(_bn(f"  {e_tr} কোনো সমস্যা পাওয়া যায়নি!"))

    # ── প্লেসহোল্ডার মিসম্যাচ ──
    ph_mm = report["placeholder_mismatches"]
    if ph_mm and not missing_only:
        print(thin)
        print(_bn(f"  ⚠️  ইন্টারপোলেশন মিসম্যাচ ({len(ph_mm)}):"))
        for i in ph_mm:
            print(
                f"  {i['key']}: "
                f"en={sorted(i['en_placeholders'])} "
                f"bn={sorted(i['bn_placeholders'])}"
            )
        print()

    # ── ব্যাকএন্ড বাংলা স্ট্রিং ──
    bf = report["backend_bangla_strings"]
    if bf and not missing_only:
        print(thin)
        print(_bn(f"  ℹ️  ব্যাকএন্ডে {len(bf)}টি বাংলা স্ট্রিং পাওয়া গেছে (i18n বাইরে):"))
        for f in bf[:20]:
            print(_bn(f"  • {f['file']}:{f['line']} — {f['string'][:60]}"))
        if len(bf) > 20:
            print(_bn(f"  ... এবং আরও {len(bf) - 20}টি"))
        print()

    # ── RTL নোট ──
    if not missing_only:
        print(thin)
        print(_bn(f"  ℹ️  {report['rtl_checker_note']}"))
        print()

    print(sep)


# ─── এন্ট্রি পয়েন্ট ──────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description=_bn("বাংলা i18n সম্পূর্ণতা পরীক্ষক — en vs bn তুলনা"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_bn(
            "উদাহরণ:\n"
            "  python scripts/bengali_i18n_completeness_checker.py\n"
            "  python scripts/bengali_i18n_completeness_checker.py --json\n"
            "  python scripts/bengali_i18n_completeness_checker.py --category admin_metrics\n"
            "  python scripts/bengali_i18n_completeness_checker.py --missing-only\n"
            "\nএক্সিট কোড: 0=১০০% সম্পূর্ণ, 1=গ্যাপ আছে, 2=ত্রুটি"
        ),
    )
    parser.add_argument(
        "--file",
        default=str(DEFAULT_TRANSLATIONS_PATH),
        help=_bn("অনুবাদ ফাইলের পাথ (ডিফল্ট: frontend/src/i18n/translations.ts)"),
    )
    parser.add_argument(
        "--json", action="store_true", help=_bn("JSON ফরম্যাটে আউটপুট")
    )
    parser.add_argument(
        "--category",
        default=None,
        help=_bn("নির্দিষ্ট ক্যাটেগরি ফিল্টার করুন (যেমন admin_metrics)"),
    )
    parser.add_argument(
        "--missing-only", action="store_true", help=_bn("শুধুমাত্র মিসিং কী দেখান")
    )
    parser.add_argument(
        "--no-backend", action="store_true", help=_bn("ব্যাকএন্ড স্ক্যান বাদ দিন")
    )
    args = parser.parse_args()

    # ফাইল লোড
    tpath = Path(args.file)
    if not tpath.exists():
        print(_bn(f"ত্রুটি: ফাইল পাওয়া যায়নি — {tpath}"), file=sys.stderr)
        sys.exit(2)

    try:
        content = tpath.read_text(encoding="utf-8")
    except Exception as e:
        print(_bn(f"ত্রুটি: ফাইল পড়তে সমস্যা — {e}"), file=sys.stderr)
        sys.exit(2)

    # ভাষা ব্লক বের করুন
    en_block = extract_lang_block(content, "en")
    bn_block = extract_lang_block(content, "bn")

    if en_block is None:
        print(_bn("ত্রুটি: 'en' ভাষা ব্লক পাওয়া যায়নি"), file=sys.stderr)
        sys.exit(2)
    if bn_block is None:
        print(_bn("ত্রুটি: 'bn' ভাষা ব্লক পাওয়া যায়নি"), file=sys.stderr)
        sys.exit(2)

    # ফ্ল্যাট করুন
    try:
        en = flatten_ts_object(en_block)
        bn = flatten_ts_object(bn_block)
    except Exception as e:
        print(_bn(f"ত্রুটি: পার্স করতে সমস্যা — {e}"), file=sys.stderr)
        sys.exit(2)

    # তুলনা
    results = compare_translations(en, bn)

    # ব্যাকএন্ড স্ক্যান
    backend_findings: List[Dict[str, Any]] = []
    if not args.no_backend:
        backend_findings = scan_backend_bangla_strings(DEFAULT_BACKEND_PATH)

    # রিপোর্ট
    report = build_report(
        results, en, bn, backend_findings,
        str(tpath.relative_to(REPO_ROOT)),
    )

    # আউটপুট
    if args.json:
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print_text_report(
            report, category_filter=args.category, missing_only=args.missing_only
        )

    # এক্সিট কোড
    if report["summary"]["is_100_percent"]:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
