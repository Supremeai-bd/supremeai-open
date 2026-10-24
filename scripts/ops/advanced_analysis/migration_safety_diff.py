#!/usr/bin/env python3
"""
SupremeAI মাইগ্রেশন সেফটি ডিফ — বিস্তারিত মাইগ্রেশন বিশ্লেষণ টুল

এই স্ক্রিপ্টটি scripts/ci/check_migration_safety.py এর এক্সটেনশন হিসেবে তৈরি করা হয়েছে।
পুরনো স্ক্রিপ্ট শুধু কয়েকটা বেসিক প্যাটার্ন চেক করতো, এটি সম্পূর্ণ বিশ্লেষণ করে:
- ডেটা-লস ঝুঁকি শ্রেণীবিভাগ (🔴 ক্রিটিক্যাল → 🟢 নিরাপদ)
- ব্যাকওয়ার্ড কম্প্যাটিবিলিটি যাচাই
- রিভিশন চেইন ভ্যালিডেশন
- ডেস্ট্রাক্টিভ অপারেশনের ডিফ ভিউ + নিরাপদ বিকল্প
- পুরনো স্ক্রিপ্ট বনাম নতুন তুলনা (নতুন ফাইন্ডিং হাইলাইট)

ব্যবহার:
    python scripts/migration_safety_diff.py                  # মার্কডাউন রিপোর্ট
    python scripts/migration_safety_diff.py --json           # JSON আউটপুট
    python scripts/migration_safety_diff.py --last-n 3       # শেষ ৩টি মাইগ্রেশন
    python scripts/migration_safety_diff.py --include-safe    # নিরাপদ মাইগ্রেশনও দেখাও

এক্সিট কোড:
    0 = সব নিরাপদ
    1 = অনিরাপদ মাইগ্রেশন পাওয়া গেছে
    2 = ত্রুটি (ফাইল পড়তে সমস্যা, ইত্যাদি)
"""

import ast
import glob
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════
# ধ্রুবক ও কনফিগারেশন — রিপোরুট থেকে প্যাথ নির্ধারণ
# ═══════════════════════════════════════════════════════════════════════

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ALEMBIC_DIR = REPO_ROOT / "backend" / "alembic_migrations" / "versions"
SQL_DIR = REPO_ROOT / "migrations"
OLD_SCRIPT = REPO_ROOT / "scripts" / "ci" / "check_migration_safety.py"


# ═══════════════════════════════════════════════════════════════════════
# ঝুঁকি শ্রেণী — ডেটা লসের মাত্রা অনুযায়ী শ্রেণীবদ্ধ
# ═══════════════════════════════════════════════════════════════════════

class RiskLevel(Enum):
    """ঝুঁকির মাত্রা নির্দেশ করে — CRITICAL থেকে SAFE পর্যন্ত"""
    CRITICAL = "CRITICAL"   # 🔴 অপূরণীয় ডেটা ক্ষতি
    HIGH = "HIGH"           # 🟠 সম্ভাব্য ডেটা ক্ষতি/ফল্ট
    MEDIUM = "MEDIUM"       # 🟡 রেফারেন্স ভাঙতে পারে
    SAFE = "SAFE"           # 🟢 কোনো ডেটা লস নেই

    @property
    def emoji(self) -> str:
        """ঝুঁকি মাত্রার সাথে ইমোজি ম্যাপিং"""
        return {
            RiskLevel.CRITICAL: "🔴",
            RiskLevel.HIGH: "🟠",
            RiskLevel.MEDIUM: "🟡",
            RiskLevel.SAFE: "🟢",
        }[self]

    @property
    def label(self) -> str:
        """ইমোজি সহ লেবেল ফেরত দেয়"""
        return f"{self.emoji} {self.value}"


# ═══════════════════════════════════════════════════════════════════════
# ডেটা ক্লাস — প্রতিটি মাইগ্রেশন অপারেশনের তথ্য সংরক্ষণ
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class MigrationOp:
    """একটি মাইগ্রেশন অপারেশনের বিস্তারিত তথ্য"""
    op_type: str             # create_table, drop_table, ইত্যাদি
    risk: RiskLevel          # ঝুঁকির মাত্রা
    target: str = ""         # প্রভাবিত টেবিল/কলাম/ইনডেক্স
    detail: str = ""         # অতিরিক্ত বিবরণ (যেমন টাইপ পরিবর্তন)
    line: int = 0            # ফাইলে লাইন নম্বর
    raw_text: str = ""       # মূল কোড/SQL স্নিপেট
    suggestion: str = ""     # নিরাপদ বিকল্পের পরামর্শ


@dataclass
class MigrationFile:
    """একটি মাইগ্রেশন ফাইলের সম্পূর্ণ বিশ্লেষণ ফলাফল"""
    path: str                          # ফাইলের পুরানো পথ
    rel_path: str = ""                 # রিপোরুট থেকে আপেক্ষিক পথ
    file_type: str = "alembic"         # alembic বা sql
    revision: str = ""                 # আলেম্বিক রিভিশন আইডি
    down_revision: str = ""            # আগের রিভিশন
    has_downgrade: bool = False        # downgrade() ফাংশন আছে কিনা
    downgrade_is_empty: bool = False   # downgrade() ফাঁকা কিনা (pass ছাড়া)
    uses_raw_execute: bool = False     # op.execute() ব্যবহার করা হয়েছে কিনা
    has_if_exists_guards: bool = False # IF EXISTS / IF NOT EXISTS গার্ড আছে কিনা
    has_ignore_warning: bool = False   # IGNORE_SAFETY_WARNING কমেন্ট আছে কিনা
    ops: list = field(default_factory=list)  # MigrationOp তালিকা
    errors: list = field(default_factory=list)  # পার্স ত্রুটি তালিকা

    @property
    def max_risk(self) -> RiskLevel:
        """এই মাইগ্রেশনের সর্বোচ্চ ঝুঁকি মাত্রা ফেরত দেয়"""
        if not self.ops:
            return RiskLevel.SAFE
        risk_order = {
            RiskLevel.CRITICAL: 4,
            RiskLevel.HIGH: 3,
            RiskLevel.MEDIUM: 2,
            RiskLevel.SAFE: 1,
        }
        return max(self.ops, key=lambda o: risk_order[o.risk]).risk

    @property
    def is_safe(self) -> bool:
        """মাইগ্রেশনটি কি সম্পূর্ণ নিরাপদ?"""
        return self.max_risk == RiskLevel.SAFE and not self.errors


# ═══════════════════════════════════════════════════════════════════════
# পুরনো স্ক্রিপ্টের প্যাটার্ন — তুলনার জন্য সংরক্ষিত
# ═══════════════════════════════════════════════════════════════════════

# পুরনো check_migration_safety.py শুধু এই ৩টা প্যাটার্ন চেক করতো
OLD_SCRIPT_PATTERNS = [
    re.compile(r"op\.drop_column"),
    re.compile(r"op\.drop_table"),
    re.compile(r"op\.alter_column\(.*type_=.*\)"),
]


# ═══════════════════════════════════════════════════════════════════════
# নিরাপদ বিকল্পের পরামর্শ — প্রতিটি ধ্বংসাত্মক অপারেশনের জন্য
# ═══════════════════════════════════════════════════════════════════════

SAFE_ALTERNATIVES = {
    "drop_table": (
        "সফট ডিলিট ব্যবহার করুন: `is_deleted` বুলিয়ান কলাম যোগ করুন। "
        "পরবর্তী রিলিজে ডেটা ব্যাকআপ নিয়ে তারপর ড্রপ করুন। "
        "Expand & Contract প্যাটার্ন অনুসরণ করুন: "
        "নতুন টেবিল তৈরি → ডুয়াল-রাইট → ব্যাকফিল → পুরনো ড্রop (ভবিষ্যতে)"
    ),
    "drop_column": (
        "কলামটি রিনেম করে `_deprecated_[timestamp]` রাখুন, অ্যাপ কোড আপডেট করুন, "
        "পরবর্তী রিলিজে ড্রপ করুন। এটি zero-downtime নিশ্চিত করে।"
    ),
    "alter_column_type": (
        "নতুন কলাম যোগ করুন (নতুন টাইপে), ডুয়াল-রাইট করুন, "
        "ব্যাকফিল করুন, তারপর পুরনো কলাম ডিপ্রিকেট করুন। "
        "সরাসরি টাইপ পরিবর্তনে ডেটা ট্রান্সফরমেশন ত্রুটি হতে পারে।"
    ),
    "rename_table": (
        "টেবিল রিনেম না করে ভিউ তৈরি করুন পুরনো নামে। "
        "সমস্ত রেফারেন্স আপডেট করার পর ভিউ সরিয়ে ফেলুন। "
        "নিশ্চিত করুন FK, ট্রিগার, ভিউ সব আপডেট হয়েছে।"
    ),
    "rename_column": (
        "কলাম রিনেম না করে নতুন কলাম যোগ করুন, ডুয়াল-রাইট, "
        "ব্যাকফিল, তারপর পুরনো কলাম ডিপ্রিকেট করুন।"
    ),
    "raw_ddl": (
        "আলেম্বিকের অপ ফাংশন ব্যবহার করুন (op.create_table, op.add_column, ইত্যাদি)। "
        "raw SQL execute() দিয়ে auto-rollback সম্ভব নয়। "
        "যদি raw SQL দরকার হয়, IF EXISTS/IF NOT EXISTS গার্ড যোগ করুন।"
    ),
}


# ═══════════════════════════════════════════════════════════════════════
# আলেম্বিক .py ফাইল পার্সার
# ═══════════════════════════════════════════════════════════════════════

def _extract_string_arg(call_node: ast.Call, arg_index: int) -> str:
    """AST কল নোড থেকে স্ট্রিং আর্গুমেন্ট বের করে"""
    args = call_node.args
    if arg_index < len(args):
        node = args[arg_index]
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
    return ""


def _get_keyword_value(call_node: ast.Call, keyword: str) -> Optional[str]:
    """AST কল নোড থেকে কীওয়ার্ড আর্গুমেন্টের মান বের করে"""
    for kw in call_node.keywords:
        if kw.arg == keyword and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


def _has_keyword(call_node: ast.Call, keyword: str) -> bool:
    """কল নোডে নির্দিষ্ট কীওয়ার্ড আর্গুমেন্ট আছে কিনা চেক করে"""
    return any(kw.arg == keyword for kw in call_node.keywords)


def _get_source_segment(source: str, node: ast.AST) -> str:
    """AST নোড থেকে সোর্স কোডের অংশ বের করে (লাইন ভিত্তিক)"""
    lines = source.split("\n")
    start = max(0, node.lineno - 1)
    end = min(len(lines), getattr(node, "end_lineno", node.lineno))
    return "\n".join(lines[start:end]).strip()


def parse_alembic_file(filepath: str) -> MigrationFile:
    """একটি আলেম্বিক মাইগ্রেশন ফাইল পার্স করে সম্পূর্ণ বিশ্লেষণ করে"""
    result = MigrationFile(
        path=filepath,
        rel_path=os.path.relpath(filepath, REPO_ROOT),
        file_type="alembic",
    )

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
    except OSError as exc:
        result.errors.append(f"ফাইল পড়তে সমস্যা: {exc}")
        return result

    # IGNORE_SAFETY_WARNING চেক — পুরনো স্ক্রিপ্টের মতো একই বাইপাস
    if "IGNORE_SAFETY_WARNING" in source:
        result.has_ignore_warning = True

    # ── রিভিশন আইডি বের করা (regex ব্যবহার — AST ছাড়াই) ──
    rev_match = re.search(r'''^revision:\s*str\s*=\s*["']([\w]+)["']''', source, re.MULTILINE)
    if not rev_match:
        # সরাসরি অ্যাসাইনমেন্ট প্যাটার্নও চেক করি (যেমন revision = "...")
        rev_match = re.search(r'''^revision\s*=\s*["']([\w]+)["']''', source, re.MULTILINE)
    result.revision = rev_match.group(1) if rev_match else ""

    down_match = re.search(
        r'''^down_revision:\s*str\s*\|\s*Sequence\[str\]\s*\|\s*None\s*=\s*["']?([^"'\n]+)["']?''',
        source,
        re.MULTILINE,
    )
    if not down_match:
        down_match = re.search(r'''^down_revision\s*=\s*["']?([^"'\n]+)["']?''', source, re.MULTILINE)
    if down_match:
        val = down_match.group(1).strip()
        # CI FIX: Handle tuple format for merge migrations.
        # Example: down_revision = ("rev_a", "rev_b") → val = '("rev_a", "rev_b")'
        # The old regex captures '("' as the value → broken chain warning.
        # Fix: if value starts with '(', extract all quoted strings from the tuple.
        if val.startswith("("):
            tuple_revs = re.findall(r'''["']([\w]+)["']''', val)
            val = ", ".join(tuple_revs) if tuple_revs else val
        result.down_revision = val if val != "None" else ""

    # ── AST পার্স করে upgrade()/downgrade() ফাংশন খোঁজা ──
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as exc:
        result.errors.append(f"Python সিনট্যাক্স ত্রুটি: {exc}")
        # সিনট্যাক্স ত্রুটি হলেও regex দিয়ে বেসিক চেক চালিয়ে যাই
        _regex_fallback_parse(source, result)
        return result

    upgrade_ops = []
    downgrade_ops = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue

        # downgrade() ফাংশন আছে কিনা চেক
        if node.name == "downgrade":
            result.has_downgrade = True
            # downgrade() ফাঁকা কিনা চেক (শুধু pass থাকলে বা কোনো মানবহনকারী স্টেটমেন্ট না থাকলে)
            non_pass_stmts = [s for s in node.body if not isinstance(s, ast.Pass)]
            if not non_pass_stmts:
                result.downgrade_is_empty = True
            downgrade_ops = _extract_ops_from_body(node, source)
            continue

        if node.name == "upgrade":
            upgrade_ops = _extract_ops_from_body(node, source)
            continue

    result.ops = upgrade_ops

    # ── raw execute চেক ──
    result.uses_raw_execute = any(o.op_type == "raw_execute" for o in upgrade_ops)

    # ── IF EXISTS / IF NOT EXISTS গার্ড চেক ──
    if "IF EXISTS" in source or "IF NOT EXISTS" in source:
        result.has_if_exists_guards = True

    return result


def _extract_ops_from_body(func_node: ast.FunctionDef, source: str) -> list:
    """ফাংশন বডি থেকে সকল মাইগ্রেশন অপারেশন বের করে"""
    ops = []
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue

        # op.xxx() কল চিনে নেওয়া
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            if node.func.value.id != "op":
                continue
            op_name = node.func.attr
            raw = _get_source_segment(source, node)
            line = node.lineno
            new_ops = _classify_alembic_op(op_name, node, raw, line)
            ops.extend(new_ops)

    return ops


def _classify_alembic_op(op_name: str, call_node: ast.Call, raw: str, line: int) -> list:
    """আলেম্বিক op.xxx() কল বিশ্লেষণ করে ঝুঁকি শ্রেণী নির্ধারণ করে"""
    ops = []

    if op_name == "create_table":
        table = _extract_string_arg(call_node, 0)
        ops.append(MigrationOp(
            op_type="create_table",
            risk=RiskLevel.SAFE,
            target=table or "(অজানা টেবিল)",
            detail=f"নতুন টেবিল তৈরি: {table}",
            line=line,
            raw_text=raw[:200],
        ))

    elif op_name == "drop_table":
        table = _extract_string_arg(call_node, 0) or _get_keyword_value(call_node, "table_name")
        ops.append(MigrationOp(
            op_type="drop_table",
            risk=RiskLevel.CRITICAL,
            target=table or "(অজানা টেবিল)",
            detail=f"টেবিল ড্রপ: {table} — সকল ডেটা মুছে যাবে",
            line=line,
            raw_text=raw[:200],
            suggestion=SAFE_ALTERNATIVES["drop_table"],
        ))

    elif op_name == "add_column":
        table = _extract_string_arg(call_node, 0)
        # দ্বিতীয় আর্গুমেন্ট sa.Column(...) থেকে কলাম নাম বের করা
        col_name = ""
        if len(call_node.args) >= 2 and isinstance(call_node.args[1], ast.Call):
            col_name = _extract_string_arg(call_node.args[1], 0)
        ops.append(MigrationOp(
            op_type="add_column",
            risk=RiskLevel.SAFE,
            target=f"{table}.{col_name}" if col_name else table,
            detail=f"কলাম যোগ: {table}.{col_name}",
            line=line,
            raw_text=raw[:200],
        ))

    elif op_name == "drop_column":
        table = _extract_string_arg(call_node, 0)
        col = _extract_string_arg(call_node, 1)
        ops.append(MigrationOp(
            op_type="drop_column",
            risk=RiskLevel.CRITICAL,
            target=f"{table}.{col}" if col else table,
            detail=f"কলাম ড্রপ: {table}.{col} — ডেটা মুছে যাবে",
            line=line,
            raw_text=raw[:200],
            suggestion=SAFE_ALTERNATIVES["drop_column"],
        ))

    elif op_name == "alter_column":
        table = _extract_string_arg(call_node, 0)
        col = _extract_string_arg(call_node, 1)
        # type_= থাকলে HIGH risk (সম্ভাব্য ডেটা ক্ষতি)
        has_type_change = _has_keyword(call_node, "type_")
        # nullable পরিবর্তনও ঝুঁকিপূর্ণ হতে পারে
        has_nullable_change = _has_keyword(call_node, "nullable")

        if has_type_change:
            ops.append(MigrationOp(
                op_type="alter_column_type",
                risk=RiskLevel.HIGH,
                target=f"{table}.{col}",
                detail=f"কলাম টাইপ পরিবর্তন: {table}.{col}",
                line=line,
                raw_text=raw[:200],
                suggestion=SAFE_ALTERNATIVES["alter_column_type"],
            ))
        elif has_nullable_change:
            ops.append(MigrationOp(
                op_type="alter_column_nullable",
                risk=RiskLevel.MEDIUM,
                target=f"{table}.{col}",
                detail=f"কলাম nullable পরিবর্তন: {table}.{col}",
                line=line,
                raw_text=raw[:200],
            ))
        else:
            ops.append(MigrationOp(
                op_type="alter_column",
                risk=RiskLevel.MEDIUM,
                target=f"{table}.{col}",
                detail=f"কলাম পরিবর্তন: {table}.{col}",
                line=line,
                raw_text=raw[:200],
            ))

    elif op_name == "rename_table":
        old_name = _extract_string_arg(call_node, 0)
        new_name = _extract_string_arg(call_node, 1)
        ops.append(MigrationOp(
            op_type="rename_table",
            risk=RiskLevel.MEDIUM,
            target=f"{old_name} → {new_name}",
            detail=f"টেবিল রিনেম: {old_name} → {new_name}",
            line=line,
            raw_text=raw[:200],
            suggestion=SAFE_ALTERNATIVES["rename_table"],
        ))

    elif op_name == "create_index":
        idx_name = _extract_string_arg(call_node, 0)
        table = _extract_string_arg(call_node, 1)
        ops.append(MigrationOp(
            op_type="create_index",
            risk=RiskLevel.SAFE,
            target=f"{table}.{idx_name}",
            detail=f"ইনডেক্স তৈরি: {idx_name} on {table}",
            line=line,
            raw_text=raw[:200],
        ))

    elif op_name == "drop_index":
        idx_name = _extract_string_arg(call_node, 0) or _get_keyword_value(call_node, "index_name")
        ops.append(MigrationOp(
            op_type="drop_index",
            risk=RiskLevel.SAFE,
            target=idx_name or "(অজানা ইনডেক্স)",
            detail=f"ইনডেক্স ড্রপ: {idx_name}",
            line=line,
            raw_text=raw[:200],
        ))

    elif op_name == "execute":
        # raw SQL — বিষয়বস্তু বিশ্লেষণ করে আসল অপারেশন চিনে নেওয়া
        sql_text = ""
        if call_node.args:
            arg = call_node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                sql_text = arg.value
        raw_sql_ops = _classify_raw_sql(sql_text, line, raw)
        if raw_sql_ops:
            ops.extend(raw_sql_ops)
        else:
            # SQL পার্স করা না গেলেও raw_execute হিসেবে রেকর্ড
            ops.append(MigrationOp(
                op_type="raw_execute",
                risk=RiskLevel.MEDIUM,
                target="(raw SQL)",
                detail=f"raw SQL execute কল",
                line=line,
                raw_text=raw[:200],
                suggestion=SAFE_ALTERNATIVES["raw_ddl"],
            ))

    elif op_name == "create_foreign_key":
        ops.append(MigrationOp(
            op_type="create_foreign_key",
            risk=RiskLevel.SAFE,
            target=_extract_string_arg(call_node, 0) or "(FK)",
            detail="ফরেন কী তৈরি",
            line=line,
            raw_text=raw[:200],
        ))

    elif op_name == "drop_constraint":
        ops.append(MigrationOp(
            op_type="drop_constraint",
            risk=RiskLevel.MEDIUM,
            target=_extract_string_arg(call_node, 0) or "(constraint)",
            detail="কনস্ট্রেইন্ট ড্রপ",
            line=line,
            raw_text=raw[:200],
        ))

    return ops


def _classify_raw_sql(sql: str, line: int, raw: str) -> list:
    """raw SQL স্ট্রিং থেকে DDL অপারেশন চিনে ঝুঁকি নির্ধারণ করে"""
    if not sql:
        return []

    ops = []
    sql_upper = sql.upper().strip()

    # DROP TABLE
    for m in re.finditer(r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?([\w\"\`\.]+)", sql_upper):
        table = m.group(1).strip('`"')
        ops.append(MigrationOp(
            op_type="raw_drop_table",
            risk=RiskLevel.CRITICAL,
            target=table,
            detail=f"raw SQL টেবিল ড্রপ: {table}",
            line=line,
            raw_text=raw[:200],
            suggestion=SAFE_ALTERNATIVES["drop_table"],
        ))

    # DROP COLUMN (ALTER TABLE ... DROP COLUMN)
    for m in re.finditer(
        r"ALTER\s+TABLE\s+([\w\"\`\.]+)\s+DROP\s+COLUMN\s+(?:IF\s+EXISTS\s+)?([\w\"\`]+)",
        sql_upper,
    ):
        table, col = m.group(1).strip('`"'), m.group(2).strip('`"')
        ops.append(MigrationOp(
            op_type="raw_drop_column",
            risk=RiskLevel.CRITICAL,
            target=f"{table}.{col}",
            detail=f"raw SQL কলাম ড্রপ: {table}.{col}",
            line=line,
            raw_text=raw[:200],
            suggestion=SAFE_ALTERNATIVES["drop_column"],
        ))

    # CREATE TABLE (IF NOT EXISTS সহ)
    for m in re.finditer(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w\"\`\.]+)", sql_upper):
        table = m.group(1).strip('`"')
        ops.append(MigrationOp(
            op_type="raw_create_table",
            risk=RiskLevel.SAFE,
            target=table,
            detail=f"raw SQL টেবিল তৈরি: {table}",
            line=line,
            raw_text=raw[:200],
        ))

    # CREATE INDEX
    for m in re.finditer(r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w\"\`]+)", sql_upper):
        idx = m.group(1).strip('`"')
        ops.append(MigrationOp(
            op_type="raw_create_index",
            risk=RiskLevel.SAFE,
            target=idx,
            detail=f"raw SQL ইনডেক্স তৈরি: {idx}",
            line=line,
            raw_text=raw[:200],
        ))

    # DROP INDEX
    for m in re.finditer(r"DROP\s+INDEX\s+(?:IF\s+EXISTS\s+)?([\w\"\`\.]+)", sql_upper):
        idx = m.group(1).strip('`"')
        ops.append(MigrationOp(
            op_type="raw_drop_index",
            risk=RiskLevel.SAFE,
            target=idx,
            detail=f"raw SQL ইনডেক্স ড্রপ: {idx}",
            line=line,
            raw_text=raw[:200],
        ))

    # ALTER TABLE ... ALTER COLUMN (টাইপ পরিবর্তন)
    for m in re.finditer(
        r"ALTER\s+TABLE\s+([\w\"\`\.]+)\s+ALTER\s+COLUMN\s+([\w\"\`]+)",
        sql_upper,
    ):
        table, col = m.group(1).strip('`"'), m.group(2).strip('`"')
        ops.append(MigrationOp(
            op_type="raw_alter_column",
            risk=RiskLevel.HIGH,
            target=f"{table}.{col}",
            detail=f"raw SQL কলাম পরিবর্তন: {table}.{col}",
            line=line,
            raw_text=raw[:200],
            suggestion=SAFE_ALTERNATIVES["alter_column_type"],
        ))

    # ALTER TABLE ... ADD COLUMN
    for m in re.finditer(
        r"ALTER\s+TABLE\s+([\w\"\`\.]+)\s+ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w\"\`]+)",
        sql_upper,
    ):
        table, col = m.group(1).strip('`"'), m.group(2).strip('`"')
        ops.append(MigrationOp(
            op_type="raw_add_column",
            risk=RiskLevel.SAFE,
            target=f"{table}.{col}",
            detail=f"raw SQL কলাম যোগ: {table}.{col}",
            line=line,
            raw_text=raw[:200],
        ))

    # ALTER TABLE ... RENAME (টেবিল বা কলাম)
    for m in re.finditer(
        r"ALTER\s+TABLE\s+([\w\"\`\.]+)\s+RENAME\s+(?:COLUMN\s+)?([\w\"\`]+)\s+TO\s+([\w\"\`]+)",
        sql_upper,
    ):
        table = m.group(1).strip('`"')
        old_name = m.group(2).strip('`"')
        new_name = m.group(3).strip('`"')
        ops.append(MigrationOp(
            op_type="raw_rename",
            risk=RiskLevel.MEDIUM,
            target=f"{table}: {old_name} → {new_name}",
            detail=f"raw SQL রিনেম: {table}.{old_name} → {new_name}",
            line=line,
            raw_text=raw[:200],
            suggestion=SAFE_ALTERNATIVES["rename_column"],
        ))

    # ALTER TABLE ... ENABLE ROW LEVEL SECURITY বা অন্যান্য নিরাপদ অপারেশন
    for m in re.finditer(r"ALTER\s+TABLE\s+[\w\"\`\.]+\s+ENABLE", sql_upper):
        table = re.search(r"ALTER\s+TABLE\s+([\w\"\`\.]+)", m.group(0))
        tbl = table.group(1).strip('`"') if table else "(অজানা)"
        ops.append(MigrationOp(
            op_type="raw_alter_enable",
            risk=RiskLevel.SAFE,
            target=tbl,
            detail=f"raw SQL: {tbl} এ enable অপারেশন",
            line=line,
            raw_text=raw[:200],
        ))

    # CREATE POLICY — নিরাপদ
    for m in re.finditer(r"CREATE\s+POLICY", sql_upper):
        ops.append(MigrationOp(
            op_type="raw_create_policy",
            risk=RiskLevel.SAFE,
            target="(policy)",
            detail="raw SQL: পলিসি তৈরি",
            line=line,
            raw_text=raw[:200],
        ))

    # যদি কোনো DDL প্যাটার্ন মেলেনি, তাহলে raw_execute হিসেবে রেকর্ড
    if not ops:
        ops.append(MigrationOp(
            op_type="raw_execute",
            risk=RiskLevel.MEDIUM,
            target="(raw SQL)",
            detail=f"raw SQL execute (DDL পার্স করা যায়নি)",
            line=line,
            raw_text=raw[:200],
            suggestion=SAFE_ALTERNATIVES["raw_ddl"],
        ))

    return ops


def _regex_fallback_parse(source: str, result: MigrationFile) -> None:
    """AST পার্স ব্যর্থ হলে regex দিয়ে বেসিক অপারেশন খোঁজা"""
    # f-string এ উদ্ধৃতি চরিত্র এমবেড করা সম্ভব নয়, তাই কনক্যাটেনেশন ব্যবহার
    _q = "[" + chr(34) + chr(39) + "]"  # ["'] ক্যারেক্টার ক্লাস
    patterns = [
        ("op\\.drop_table\\(" + _q + "([\\w_]+)" + _q, "drop_table", RiskLevel.CRITICAL, SAFE_ALTERNATIVES["drop_table"]),
        ("op\\.drop_column\\(" + _q + "([\\w_]+)" + _q, "drop_column", RiskLevel.CRITICAL, SAFE_ALTERNATIVES["drop_column"]),
        ("op\\.create_table\\(" + _q + "([\\w_]+)" + _q, "create_table", RiskLevel.SAFE, ""),
        ("op\\.add_column\\(" + _q + "([\\w_]+)" + _q, "add_column", RiskLevel.SAFE, ""),
        ("op\\.alter_column\\(" + _q + "([\\w_]+)" + _q + ",\\s*" + _q + "([\\w_]+)" + _q + ".*?type_", "alter_column_type", RiskLevel.HIGH, SAFE_ALTERNATIVES["alter_column_type"]),
    ]
    for i, line in enumerate(source.split("\n"), 1):
        for pattern, op_type, risk, suggestion in patterns:
            m = re.search(pattern, line)
            if m:
                target = m.group(1)
                if op_type == "alter_column_type":
                    target = f"{m.group(1)}.{m.group(2)}"
                result.ops.append(MigrationOp(
                    op_type=op_type,
                    risk=risk,
                    target=target,
                    detail=f"{op_type}: {target}",
                    line=i,
                    raw_text=line.strip()[:200],
                    suggestion=suggestion,
                ))

    result.has_downgrade = bool(re.search(r"def downgrade\(\)", source))


# ═══════════════════════════════════════════════════════════════════════
# SQL মাইগ্রেশন ফাইল পার্সার
# ═══════════════════════════════════════════════════════════════════════

def parse_sql_file(filepath: str) -> MigrationFile:
    """একটি SQL মাইগ্রেশন ফাইল পার্স করে অপারেশন বের করে"""
    result = MigrationFile(
        path=filepath,
        rel_path=os.path.relpath(filepath, REPO_ROOT),
        file_type="sql",
        has_downgrade=False,  # SQL ফাইলে downgrade নেই
        has_if_exists_guards=False,
    )

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
    except OSError as exc:
        result.errors.append(f"ফাইল পড়তে সমস্যা: {exc}")
        return result

    if "IF EXISTS" in source or "IF NOT EXISTS" in source:
        result.has_if_exists_guards = True

    # SQL স্টেটমেন্ট সেমিকোলন দিয়ে ভাগ করা — মাল্টি-লাইন স্টেটমেন্ট হ্যান্ডেল
    statements = source.split(";")
    line_offset = 0
    for stmt in statements:
        stmt = stmt.strip()
        if not stmt or all(l.strip().startswith("--") or not l.strip() for l in stmt.split("\n")):
            line_offset += stmt.count("\n") + 1
            continue
        # কমেন্ট লাইন বাদ দিয়ে প্রথম নন-কমেন্ট লাইনের নম্বর বের করা
        actual_line = line_offset + 1
        for pre_line in stmt.split("\n"):
            if pre_line.strip() and not pre_line.strip().startswith("--"):
                break
            actual_line += 1

        # CI FIX: Strip comment lines from the statement before classification.
        # Previously, comments containing 'DROP TABLE' text (e.g. explanatory
        # comments like '-- আগে এখানে DROP TABLE IF EXISTS messages ছিল --')
        # were matched by the regex → false CRITICAL alert.
        stmt_no_comments = "\n".join(
            line for line in stmt.split("\n") if not line.strip().startswith("--")
        )

        ops = _classify_raw_sql(stmt_no_comments, actual_line, stmt.splitlines()[0].strip() if stmt.splitlines() else stmt)
        result.ops.extend(ops)
        line_offset += stmt.count("\n") + 1

    return result


# ═══════════════════════════════════════════════════════════════════════
# ফাইল সংগ্রহ — সকল মাইগ্রেশন ফাইল খোঁজা
# ═══════════════════════════════════════════════════════════════════════

def collect_migration_files() -> list:
    """আলেম্বিক ও SQL মাইগ্রেশন ফাইল সংগ্রহ করে, সংশোধনের সময় অনুযায়ী সাজায়"""
    files = []

    # আলেম্বিক .py ফাইল (এক্সক্লুড __init__.py)
    if ALEMBIC_DIR.exists():
        for fp in sorted(ALEMBIC_DIR.glob("*.py")):
            if fp.name == "__init__.py":
                continue
            files.append(parse_alembic_file(str(fp)))

    # SQL মাইগ্রেশন ফাইল
    if SQL_DIR.exists():
        for fp in sorted(SQL_DIR.glob("*.sql")):
            files.append(parse_sql_file(str(fp)))

    # সংশোধনের সময় অনুযায়ী সাজানো (নতুন ফাইল শেষে)
    files.sort(key=lambda f: os.path.getmtime(f.path) if os.path.exists(f.path) else 0)
    return files


# ═══════════════════════════════════════════════════════════════════════
# রিভিশন চেইন ভ্যালিডেশন — চেইন ভাঙা কিনা চেক
# ═══════════════════════════════════════════════════════════════════════

def validate_revision_chain(migrations: list) -> list:
    """আলেম্বিক রিভিশন চেইন ভ্যালিডেট করে, সমস্যা তালিকা ফেরত দেয়"""
    issues = []

    # শুধু আলেম্বিক ফাইলের রিভিশন ম্যাপ তৈরি
    alembic_migs = [m for m in migrations if m.file_type == "alembic"]
    revision_set = {m.revision for m in alembic_migs if m.revision}

    for mig in alembic_migs:
        if not mig.revision:
            issues.append({
                "file": mig.rel_path,
                "issue": "রিভিশন আইডি পাওয়া যায়নি",
                "severity": "HIGH",
            })
            continue

        if mig.down_revision and mig.down_revision != "None":
            # CI FIX: Handle comma-separated down_revisions (merge migrations).
            # Example: down_revision = "2026_08_15_145220, tier_s_001"
            # Each revision ID must be in revision_set.
            down_revs = [r.strip() for r in mig.down_revision.split(",") if r.strip()]
            for dr in down_revs:
                if dr not in revision_set:
                    issues.append({
                        "file": mig.rel_path,
                        "issue": (
                            f"down_revision '{dr}' কোনো মাইগ্রেশনের "
                            f"revision হিসেবে পাওয়া যায়নি — চেইন ভাঙা"
                        ),
                        "severity": "HIGH",
                    })

    # ডুপ্লিকেট রিভিশন চেক
    seen = {}
    for mig in alembic_migs:
        if mig.revision:
            if mig.revision in seen:
                issues.append({
                    "file": mig.rel_path,
                    "issue": f"ডুপ্লিকেট revision '{mig.revision}' — আগে পাওয়া গেছে: {seen[mig.revision]}",
                    "severity": "HIGH",
                })
            else:
                seen[mig.revision] = mig.rel_path

    # অরফান চেক — কোনো মাইগ্রেশনের down_revision হিসেবে যারা নেই
    referenced = {m.down_revision for m in alembic_migs if m.down_revision and m.down_revision != "None"}
    roots = [m for m in alembic_migs if m.revision and m.revision not in referenced]
    if len(roots) > 1:
        # একাধিক রুট = ব্রাঞ্চিং, যা সমস্যাগ্রস্ত হতে পারে
        root_names = [r.rel_path for r in roots]
        issues.append({
            "file": ", ".join(root_names),
            "issue": f"একাধিক রুট মাইগ্রেশন পাওয়া গেছে ({len(roots)}টি) — চেইন ব্রাঞ্চ হতে পারে",
            "severity": "MEDIUM",
        })

    return issues


# ═══════════════════════════════════════════════════════════════════════
# পুরনো স্ক্রিপ্ট তুলনা — নতুন ফাইন্ডিং হাইলাইট
# ═══════════════════════════════════════════════════════════════════════

def check_old_script_coverage(migration: MigrationFile) -> list:
    """পুরনো check_migration_safety.py কি এই মাইগ্রেশন ধরতে পারত? নতুন ফাইন্ডিং ফেরত দেয়"""
    new_findings = []

    if migration.has_ignore_warning:
        return new_findings  # বাইপাস করা হলে তুলনা করার দরকার নেই

    # পুরনো স্ক্রিপ্ট শুধু upgrade() এর op.drop_column, op.drop_table, op.alter_column(type_=) চেক করতো
    try:
        with open(migration.path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return new_findings

    # upgrade() ফাংশনের কন্টেন্ট বের করা
    upgrade_match = re.search(r"def upgrade\(\).*?^(?=def\s+\w+\(|$)", content, re.MULTILINE | re.DOTALL)
    if not upgrade_match:
        return new_findings
    upgrade_content = upgrade_match.group(0)

    # পুরনো স্ক্রিপ্ট যা ধরতে পারত
    old_would_catch = False
    for pattern in OLD_SCRIPT_PATTERNS:
        if pattern.search(upgrade_content):
            old_would_catch = True
            break

    # নতুন স্ক্রিপ্ট যা বাড়তি পায়
    for op in migration.ops:
        if op.risk == RiskLevel.SAFE:
            continue  # নিরাপদ অপারেশন তুলনায় আসে না

        # পুরনো স্ক্রিপ্ট যদি ইতিমধ্যে ধরতে পারত
        if old_would_catch and op.op_type in ("drop_table", "drop_column", "alter_column_type"):
            continue  # পুরনো স্ক্রিপ্টেও পাওয়া যেত

        # নতুন ফাইন্ডিং — পুরনো স্ক্রিপ্ট ধরতে পারতো না
        finding_reason = _explain_new_finding(op, migration)
        if finding_reason:
            new_findings.append(finding_reason)

    # ব্যাকওয়ার্ড কম্প্যাটিবিলিটি — পুরনো স্ক্রিপ্ট চেক করতো না
    if not migration.has_downgrade:
        new_findings.append(
            f"  🆕 downgrade() ফাংশন নেই — মাইগ্রেশন অপূর্ণনশীল (irreversible)"
        )
    elif migration.downgrade_is_empty:
        new_findings.append(
            f"  🆕 downgrade() ফাঁকা (শুধু pass) — rollback সম্ভব নয়"
        )

    # raw SQL execute — পুরনো স্ক্রিপ্ট চেক করতো না
    if migration.uses_raw_execute and not old_would_catch:
        # শুধু তখনই নতুন যদি raw SQL এ কোনো destructive op থাকে
        has_destructive = any(
            o.risk in (RiskLevel.CRITICAL, RiskLevel.HIGH)
            for o in migration.ops
            if "raw_" in o.op_type
        )
        if has_destructive:
            new_findings.append(
                f"  🆕 op.execute() এ raw DDL আছে যা destructive — পুরনো স্ক্রিপ্ট ধরতে পারতো না"
            )

    # SQL ফাইল — পুরনো স্ক্রিপ্ট একদমই চেক করতো না
    if migration.file_type == "sql":
        unsafe_ops = [o for o in migration.ops if o.risk in (RiskLevel.CRITICAL, RiskLevel.HIGH)]
        if unsafe_ops:
            new_findings.append(
                f"  🆕 SQL মাইগ্রেশন ফাইল — পুরনো স্ক্রিপ্ট এগুলো সম্পূর্ণ এড়িয়ে যেত"
            )

    return new_findings


def _explain_new_finding(op: MigrationOp, migration: MigrationFile) -> Optional[str]:
    """নতুন ফাইন্ডিং কেন নতুন তা ব্যাখ্যা করে"""
    if op.op_type.startswith("raw_"):
        return f"  🆕 raw SQL এ {op.op_type} (লাইন {op.line}): {op.detail} — পুরনো স্ক্রিপ্ট regex দিয়ে ধরতে পারতো না"
    if op.op_type == "rename_table":
        return f"  🆕 rename_table (লাইন {op.line}): {op.detail} — পুরনো স্ক্রিপ্ট চেক করতো না"
    if op.op_type == "raw_rename":
        return f"  🆕 raw SQL rename (লাইন {op.line}): {op.detail} — পুরনো স্ক্রিপ্ট চেক করতো না"
    if op.op_type == "drop_constraint":
        return f"  🆕 drop_constraint (লাইন {op.line}): {op.detail} — পুরনো স্ক্রিপ্ট চেক করতো না"
    if op.op_type == "alter_column_nullable":
        return f"  🆕 alter_column nullable পরিবর্তন (লাইন {op.line}): {op.detail} — পুরনো স্ক্রিপ্ট চেক করতো না"
    return None


# ═══════════════════════════════════════════════════════════════════════
# মার্কডাউন রিপোর্ট জেনারেটর
# ═══════════════════════════════════════════════════════════════════════

def generate_markdown_report(
    migrations: list,
    chain_issues: list,
    include_safe: bool = False,
) -> str:
    """সম্পূর্ণ বিশ্লেষণ ফলাফল থেকে মার্কডাউন রিপোর্ট তৈরি করে"""
    lines = []
    lines.append("# 🔍 SupremeAI মাইগ্রেশন সেফটি ডিফ রিপোর্ট\n")
    lines.append(f"**মোট মাইগ্রেশন ফাইল:** {len(migrations)}")

    unsafe = [m for m in migrations if not m.is_safe and not m.has_ignore_warning]
    safe = [m for m in migrations if m.is_safe]
    ignored = [m for m in migrations if m.has_ignore_warning]
    with_errors = [m for m in migrations if m.errors]

    lines.append(f"**নিরাপদ:** {len(safe)} | **অনিরাপদ:** {len(unsafe)} | **বাইপাস করা:** {len(ignored)} | **ত্রুটি:** {len(with_errors)}\n")

    # ── সারাংশ টেবিল ──
    lines.append("---\n")
    lines.append("## 📊 সারাংশ\n")
    lines.append("| ফাইল | ধরন | ঝুঁকি | অপারেশন সংখ্যা | Downgrade | Raw SQL |")
    lines.append("|------|------|------|-----------------|-----------|----------|")

    for m in migrations:
        if m.is_safe and not include_safe:
            continue
        risk_emoji = m.max_risk.emoji if not m.has_ignore_warning else "⛔"
        downgrade_status = "✅" if m.has_downgrade and not m.downgrade_is_empty else "❌"
        raw_status = "⚠️" if m.uses_raw_execute else "—"
        op_count = len(m.ops)
        lines.append(
            f"| `{m.rel_path}` | {m.file_type} | {risk_emoji} | {op_count} | {downgrade_status} | {raw_status} |"
        )

    lines.append("")

    # ── রিভিশন চেইন সমস্যা ──
    if chain_issues:
        lines.append("---\n")
        lines.append("## 🔗 রিভিশন চেইন সমস্যা\n")
        for issue in chain_issues:
            sev = "🔴" if issue["severity"] == "HIGH" else "🟡"
            lines.append(f"- {sev} `{issue['file']}`: {issue['issue']}")
        lines.append("")

    # ── অনিরাপদ মাইগ্রেশনের বিস্তারিত ডিফ ──
    if unsafe:
        lines.append("---\n")
        lines.append("## ⚠️ অনিরাপদ মাইগ্রেশন — বিস্তারিত ডিফ\n")

        for m in unsafe:
            lines.append(f"### {m.max_risk.label} `{m.rel_path}`\n")

            if m.file_type == "alembic":
                if m.revision:
                    lines.append(f"- **Revision:** `{m.revision}` → down: `{m.down_revision or '(root)'}`")
                lines.append(f"- **Downgrade:** {'✅ আছে' if m.has_downgrade else '❌ নেই (irreversible)'}")
                if m.downgrade_is_empty:
                    lines.append("- **⚠️ Downgrade ফাঁকা** — rollback সম্ভব নয়")
                lines.append(f"- **Raw SQL:** {'⚠️ হ্যাঁ' if m.uses_raw_execute else 'না'}")
                lines.append(f"- **IF EXISTS গার্ড:** {'✅ আছে' if m.has_if_exists_guards else '❌ নেই'}")

            # প্রতিটি অপারেশনের বিস্তারিত
            unsafe_ops = [o for o in m.ops if o.risk != RiskLevel.SAFE]
            if unsafe_ops:
                lines.append("")
                lines.append("| লাইন | অপারেশন | ঝুঁকি | লক্ষ্য | বিবরণ |")
                lines.append("|------|----------|------|------|--------|")
                for op in unsafe_ops:
                    lines.append(
                        f"| {op.line} | `{op.op_type}` | {op.risk.label} | `{op.target}` | {op.detail} |"
                    )

            # নিরাপদ বিকল্পের পরামর্শ
            suggestions = {op.suggestion for op in m.ops if op.suggestion}
            if suggestions:
                lines.append("")
                lines.append("**💡 নিরাপদ বিকল্প:**")
                for s in suggestions:
                    lines.append(f"> {s}")

            # পুরনো স্ক্রিপ্ট তুলনা — নতুন ফাইন্ডিং
            new_findings = check_old_script_coverage(m)
            if new_findings:
                lines.append("")
                lines.append("**🆕 পুরনো স্ক্রিপ্টে নতুন (পুরনোটিতে ধরা পড়তো না):**")
                for nf in new_findings:
                    lines.append(nf)

            lines.append("")

    # ── নিরাপদ মাইগ্রেশন (ঐচ্ছিক) ──
    if include_safe and safe:
        lines.append("---\n")
        lines.append(f"## ✅ নিরাপদ মাইগ্রেশন ({len(safe)}টি)\n")
        for m in safe:
            lines.append(f"- 🟢 `{m.rel_path}` — {len(m.ops)}টি অপারেশন")
        lines.append("")

    # ── বাইপাস করা মাইগ্রেশন ──
    if ignored:
        lines.append("---\n")
        lines.append(f"## ⛔ IGNORE_SAFETY_WARNING দিয়ে বাইপাস করা ({len(ignored)}টি)\n")
        for m in ignored:
            lines.append(f"- `{m.rel_path}`")
        lines.append("")

    # ── ত্রুটি ──
    if with_errors:
        lines.append("---\n")
        lines.append("## ❌ ত্রুটি\n")
        for m in with_errors:
            for err in m.errors:
                lines.append(f"- `{m.rel_path}`: {err}")
        lines.append("")

    # ── পুরনো স্ক্রিপ্ট তুলনা সারাংশ ──
    lines.append("---\n")
    lines.append("## 📈 পুরনো স্ক্রিপ্ট তুলনা (check_migration_safety.py)\n")
    total_new = 0
    for m in migrations:
        if m.has_ignore_warning or m.is_safe:
            continue
        nf = check_old_script_coverage(m)
        total_new += len(nf)

    if total_new == 0:
        lines.append("✅ সকল অনিরাপদ মাইগ্রেশন পুরনো স্ক্রিপ্টেও ধরা পড়তো। নতুন কোনো ফাইন্ডিং নেই।")
    else:
        lines.append(f"🆕 **{total_new}টি নতুন ফাইন্ডিং** যা পুরনো স্ক্রিপ্ট ধরতে পারতো না:")
        lines.append("")
        lines.append("| মাইগ্রেশন | নতুন ফাইন্ডিং |")
        lines.append("|-------------|---------------|")
        for m in migrations:
            if m.has_ignore_warning or m.is_safe:
                continue
            nf = check_old_script_coverage(m)
            if nf:
                lines.append(f"| `{m.rel_path}` | {len(nf)}টি |")
                for finding in nf:
                    lines.append(f"| | {finding} |")

    lines.append("")
    lines.append("---")
    lines.append(f"*Generated by `migration_safety_diff.py` — SupremeAI*\n")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# JSON আউটপুট জেনারেটর
# ═══════════════════════════════════════════════════════════════════════

def generate_json_report(
    migrations: list,
    chain_issues: list,
    include_safe: bool = False,
) -> str:
    """সম্পূর্ণ বিশ্লেষণ ফলাফল JSON ফরম্যাটে ফেরত দেয়"""

    def _op_to_dict(op: MigrationOp) -> dict:
        return {
            "op_type": op.op_type,
            "risk": op.risk.value,
            "risk_label": op.risk.label,
            "target": op.target,
            "detail": op.detail,
            "line": op.line,
            "raw_text": op.raw_text,
            "suggestion": op.suggestion,
        }

    def _migration_to_dict(m: MigrationFile) -> dict:
        ops = m.ops if include_safe else [o for o in m.ops if o.risk != RiskLevel.SAFE]
        new_findings = check_old_script_coverage(m) if not m.is_safe and not m.has_ignore_warning else []
        return {
            "path": m.rel_path,
            "file_type": m.file_type,
            "revision": m.revision,
            "down_revision": m.down_revision,
            "max_risk": m.max_risk.value,
            "max_risk_label": m.max_risk.label,
            "is_safe": m.is_safe,
            "has_downgrade": m.has_downgrade,
            "downgrade_is_empty": m.downgrade_is_empty,
            "uses_raw_execute": m.uses_raw_execute,
            "has_if_exists_guards": m.has_if_exists_guards,
            "has_ignore_warning": m.has_ignore_warning,
            "errors": m.errors,
            "operations": [_op_to_dict(o) for o in ops],
            "new_vs_old_script": new_findings,
        }

    result = {
        "summary": {
            "total": len(migrations),
            "safe": sum(1 for m in migrations if m.is_safe),
            "unsafe": sum(1 for m in migrations if not m.is_safe and not m.has_ignore_warning),
            "ignored": sum(1 for m in migrations if m.has_ignore_warning),
            "with_errors": sum(1 for m in migrations if m.errors),
            "new_findings_vs_old_script": sum(
                len(check_old_script_coverage(m))
                for m in migrations
                if not m.is_safe and not m.has_ignore_warning
            ),
        },
        "revision_chain_issues": chain_issues,
        "migrations": [_migration_to_dict(m) for m in migrations],
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════════════
# CLI আর্গুমেন্ট পার্সার
# ═══════════════════════════════════════════════════════════════════════

def parse_args(argv: list) -> dict:
    """কমান্ড-লাইন আর্গুমেন্ট পার্স করে"""
    args = {
        "json": False,
        "last_n": 0,  # 0 মানে সব ফাইল
        "include_safe": False,
        "fail_on_critical": False,
    }
    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg == "--json":
            args["json"] = True
        elif arg == "--last-n":
            if i + 1 < len(argv):
                try:
                    args["last_n"] = int(argv[i + 1])
                    i += 1
                except ValueError:
                    print("Error: --last-n এর মান একটি পূর্ণসংখ্যা হতে হবে", file=sys.stderr)
                    sys.exit(2)
            else:
                print("Error: --last-n এর পরে একটি সংখ্যা দিন", file=sys.stderr)
                sys.exit(2)
        elif arg == "--include-safe":
            args["include_safe"] = True
        elif arg == "--fail-on-critical":
            args["fail_on_critical"] = True
        elif arg in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        else:
            print(f"Error: অজানা আর্গুমেন্ট '{arg}'", file=sys.stderr)
            print("ব্যবহার: python migration_safety_diff.py [--json] [--last-n N] [--include-safe] [--fail-on-critical]", file=sys.stderr)
            sys.exit(2)
        i += 1
    return args


# ═══════════════════════════════════════════════════════════════════════
# মূল ফাংশন — এন্ট্রি পয়েন্ট
# ═══════════════════════════════════════════════════════════════════════

def main() -> int:
    """মূল ফাংশন — সকল মাইগ্রেশন বিশ্লেষণ করে রিপোর্ট আউটপুট দেয়"""
    args = parse_args(sys.argv)

    # সকল মাইগ্রেশন ফাইল সংগ্রহ
    try:
        all_migrations = collect_migration_files()
    except Exception as exc:
        print(f"Error: মাইগ্রেশন ফাইল সংগ্রহে সমস্যা: {exc}", file=sys.stderr)
        return 2

    # --last-n: শুধু শেষ Nটি মাইগ্রেশন বিশ্লেষণ
    if args["last_n"] > 0:
        all_migrations = all_migrations[-args["last_n"]:]

    # রিভিশন চেইন ভ্যালিডেশন
    chain_issues = validate_revision_chain(all_migrations)

    # ত্রুটি থাকলে exit code 2
    has_errors = any(m.errors for m in all_migrations)

    # আউটপুট ফরম্যাট অনুযায়ী রিপোর্ট তৈরি
    if args["json"]:
        report = generate_json_report(all_migrations, chain_issues, args["include_safe"])
    else:
        report = generate_markdown_report(all_migrations, chain_issues, args["include_safe"])

    print(report)

    # এক্সিট কোড নির্ধারণ
    if has_errors:
        return 2
    if args["fail_on_critical"]:
        critical = any(
            not m.has_ignore_warning and m.max_risk == RiskLevel.CRITICAL
            for m in all_migrations
        )
        return 1 if critical else 0
    if any(not m.is_safe and not m.has_ignore_warning for m in all_migrations):
        return 1
    return 0


# ═══════════════════════════════════════════════════════════════════════
# স্ক্রিপ্ট এক্সিকিউশন — সরাসরি চালানো গেলে মূল ফাংশন কল
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    sys.exit(main())
