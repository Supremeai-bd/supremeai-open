#!/usr/bin/env python3
"""Skill Bundle Generator (#3194 — role/task instruction bundles from DB policy).

=============================================================
# বাংলা মন্তব্য: স্ট্যাটিক role-instruction ফাইল বাড়ানোর বদলে প্রতিটি টাস্কে
# DB-তে রাখা canonical rule/policy থেকে একটি **ডিটারমিনিস্টিক skill bundle**
# তৈরি হয় — AGENTS.md (immutable entry contract) + DB policy set থেকে।
#
# ডিজাইন চুক্তি (#3194 verification contract):
#   1. প্রতিটি টাস্ক ঠিক একটি deterministic bundle পায়।
#   2. Mandatory global rule (U1-U8, P1-P5, BLOCK-severity constitution) কখনো
#      role/task filter-এ বাদ যেতে পারে না।
#   3. Bundle-এ policy/rule version + content hash থাকে।
#   4. একই task + একই policy version → একই bundle (byte-identical payload hash)।
#   5. Agent decision JSON-এ bundle hash/version রেকর্ড হয় (augment_decision)।
#   6. DB rule আপডেট → নতুন bundle বদলায়, স্ট্যাটিক role document ছোঁয়া লাগে না।
#   7. দ্বিতীয় কোনো সমন্বয়-ইঞ্জিন নয় — pure function + CLI, কোনো ব্যাকগ্রাউন্ড
#      কার্যপ্রবাহ নেই (P1 Simple + Effective)।
#
# Authority: bundle জেনারেশন read-only। DB-তে rule লেখা শুধু policy authority
# (admin) — CLI-তে `--confirm-policy-write` গার্ড ছাড়া লেখা অসম্ভব।
#
# Usage:
#   # 0. প্রথমবার bootstrap — canonical ফাইল থেকে DB seed (idempotent):
#   python scripts/agents/skill_bundle.py seed
#
#   # 1. টাস্ক শুরুর আগে bundle তৈরি:
#   python scripts/agents/skill_bundle.py generate --role coder --task-id 3194 \
#       --task-type coding --out /tmp/bundle-3194.json
#
#   # 2. U8 decision ledger-এ bundle hash যুক্ত করা:
#   python scripts/agents/skill_bundle.py stamp --bundle b.json --decision d.json
#
#   # 3. Bundle integrity verify (hash recompute):
#   python scripts/agents/skill_bundle.py verify --bundle b.json
#
#   # 4. Admin policy write (guard ছাড়া reject হবে):
#   python scripts/agents/skill_bundle.py rule-upsert --rule-id U9 \
#       --scope universal --category universal --title "..." --body "..." \
#       --mandatory --confirm-policy-write
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

ROOT_DIR = Path(__file__).resolve().parents[2]

# বাংলা মন্তব্য: script-লেয়ারের প্রতিষ্ঠিত DB path (agent_solution_memory.py এর মতোই)।
SQLITE_DB_PATH = ROOT_DIR / "data" / "supremeai.db"

BUNDLE_SCHEMA_VERSION = 1

# Canonical source files — seed-এর উপাদান, bundle-এর authority নয়।
# বাংলা মন্তব্য: AGENTS.md = immutable entry contract (শুধু hash ধরা হয়),
# AGENT_RULES.md + rules.yml = seed material যা DB-তে versioned কপি হয়।
CANONICAL_FILES = {
    "agents_md": ROOT_DIR / "AGENTS.md",
    "agent_rules_md": ROOT_DIR / "AGENT_RULES.md",
    "constitution_rules_yml": ROOT_DIR / ".github" / "constitution" / "rules.yml",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS policy_rules (
    rule_id     TEXT NOT NULL,
    version     INTEGER NOT NULL,
    scope       TEXT NOT NULL,
    category    TEXT NOT NULL,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    mandatory   INTEGER NOT NULL DEFAULT 0,
    superseded  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    source      TEXT NOT NULL,
    PRIMARY KEY (rule_id, version)
);
CREATE INDEX IF NOT EXISTS idx_policy_rules_scope
    ON policy_rules (scope, superseded, version);
"""


# ---------------------------------------------------------------------------
# DB helpers — সরল sqlite3, কোনো নতুন ORM/layer নয় (P2: complexity must earn)
# ---------------------------------------------------------------------------
def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else SQLITE_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


# ---------------------------------------------------------------------------
# Canonical seed parsing — AGENT_RULES.md + constitution rules.yml → DB rows
# ---------------------------------------------------------------------------
_RULE_HEADER_RE = re.compile(r"^## (U\d+|P\d+) — (.+?)\s*$")


# বাংলা মন্তব্য: role header → canonical role scope কী (AGENT_RULES.md §3-এর
# ৮টি role এবং continuous_agent_loop.py-র ROLE_ALIASES-এর সাথে সামঞ্জস্যপূর্ণ)।
_ROLE_HEADER_TO_SCOPE = {
    "Auditor": "auditor",
    "Ecosystem Scout / Planner": "planner",
    "Coder": "coder",
    "CI Fixer": "ci-fixer",
    "Watcher": "watcher",
    "Human-Eyes / Browser Agent": "human-eyes",
    "Breaker / Adversarial Auditor": "breaker",
    "Merge Agent": "merge-agent",
}


def parse_agent_rules_md(path: Path) -> list[dict]:
    """AGENT_RULES.md পার্স করে policy row dict তৈরি করে।

    # বাংলা মন্তব্য: §1 Universal (U*) → scope='universal', mandatory=1;
    # §2 Engineering (P*) → scope='engineering', mandatory=1 (Non-Negotiable);
    # §3 Role সেকশন → scope='role:<name>', mandatory=0 (role-filterable)।
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    rules: list[dict] = []
    section = None  # (kind, key, title) — kind: 'rule' | 'role'
    buf: list[str] = []

    def _flush():
        nonlocal buf
        if section is None or not buf:
            buf = []
            return
        body = "\n".join(buf).strip()
        if body:
            kind, key, title = section
            if kind == "rule":
                # U* = universal contract, P* = engineering policy — দুটোই mandatory
                scope = "universal" if key.startswith("U") else "engineering"
                rules.append({
                    "rule_id": key, "scope": scope, "category": scope,
                    "title": title, "body": body, "mandatory": 1,
                    "source": "seed:AGENT_RULES.md",
                })
            else:
                rules.append({
                    "rule_id": f"role:{key}", "scope": f"role:{key}", "category": "role",
                    "title": title, "body": body, "mandatory": 0,
                    "source": "seed:AGENT_RULES.md",
                })
        buf = []

    for line in lines:
        m = _RULE_HEADER_RE.match(line)
        if m:
            _flush()
            section = ("rule", m.group(1), m.group(2))
            continue
        if line.startswith("## "):
            role_name = line[3:].strip()
            if role_name in _ROLE_HEADER_TO_SCOPE:
                _flush()
                section = ("role", _ROLE_HEADER_TO_SCOPE[role_name], role_name)
                continue
        if line.startswith("# "):
            # H1 — নতুন top-level সেকশন, চলমান rule/role flush করা ঠিক নয়;
            # শুধু buf ধরে রাখি (§ হেডারের পরের প্রথম H1 এসে flush হবে)।
            _flush()
            section = None
            continue
        if section is not None:
            buf.append(line)
    _flush()
    return rules


def parse_constitution_rules_yml(path: Path) -> list[dict]:
    """constitution rules.yml → policy rows। severity=BLOCK → mandatory।"""
    import yaml  # local import — CLI seed path only, import cost এড়ানো

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules: list[dict] = []
    for category, entries in data.items():
        if not isinstance(entries, dict):
            continue
        for rule_id, entry in entries.items():
            if not isinstance(entry, dict):
                continue
            severity = str(entry.get("severity", "WARN")).upper()
            rules.append({
                # বাংলা মন্তব্য: rules.yml একই rule_id (rule_001...) একাধিক
                # category-তে পুনর্ব্যবহার করে — তাই identity-তে category
                # যুক্ত, নইলে আলাদা নিয়ম নীরবে এক row-তে মিলিয়ে যায়।
                "rule_id": f"constitution:{category}:{rule_id}",
                "scope": f"constitution:{category}",
                "category": str(entry.get("category", category)),
                "title": str(entry.get("title", rule_id)),
                "body": str(entry.get("description", "")),
                "mandatory": 1 if severity == "BLOCK" else 0,
                "source": "seed:rules.yml",
            })
    return rules


def seed_from_canonical(db_path: Path | None = None, force: bool = False) -> dict:
    """Canonical ফাইল থেকে DB seed (idempotent)।

    # বাংলা মন্তব্য: একই rule_id + একই body থাকলে কিছুই হয় না; body বদলালে
    # নতুন version row তৈরি হয় এবং পুরনো version superseded=1 হয়।
    # ফলে DB-ই সত্যের উৎস, ফাইল শুধু bootstrap material।
    """
    parsed = parse_agent_rules_md(CANONICAL_FILES["agent_rules_md"])
    parsed += parse_constitution_rules_yml(CANONICAL_FILES["constitution_rules_yml"])
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        added = updated = unchanged = 0
        for row in parsed:
            cur.execute(
                "SELECT version, body, mandatory, title FROM policy_rules "
                "WHERE rule_id = ? ORDER BY version DESC LIMIT 1",
                (row["rule_id"],),
            )
            prev = cur.fetchone()
            if prev is None:
                cur.execute(
                    "INSERT INTO policy_rules (rule_id, version, scope, category, title,"
                    " body, mandatory, superseded, created_at, source)"
                    " VALUES (?, 1, ?, ?, ?, ?, ?, 0, ?, ?)",
                    (row["rule_id"], row["scope"], row["category"], row["title"],
                     row["body"], row["mandatory"], now, row["source"]),
                )
                added += 1
            elif force and (prev["body"] != row["body"] or prev["title"] != row["title"]
                            or prev["mandatory"] != row["mandatory"]):
                new_version = prev["version"] + 1
                cur.execute(
                    "UPDATE policy_rules SET superseded = 1 WHERE rule_id = ?",
                    (row["rule_id"],),
                )
                cur.execute(
                    "INSERT INTO policy_rules (rule_id, version, scope, category, title,"
                    " body, mandatory, superseded, created_at, source)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
                    (row["rule_id"], new_version, row["scope"], row["category"],
                     row["title"], row["body"], row["mandatory"], now, row["source"]),
                )
                updated += 1
            else:
                unchanged += 1
        conn.commit()
        return {"added": added, "updated": updated, "unchanged": unchanged,
                "total_parsed": len(parsed)}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Bundle generation — deterministic, mandatory rules always injected
# ---------------------------------------------------------------------------
def _latest_rules(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT rule_id, MAX(version) AS v FROM policy_rules WHERE superseded = 0 "
        "GROUP BY rule_id"
    ).fetchall()
    rules: list[dict] = []
    for r in rows:
        row = cur.execute(
            "SELECT rule_id, version, scope, category, title, body, mandatory "
            "FROM policy_rules WHERE rule_id = ? AND version = ?",
            (r["rule_id"], r["v"]),
        ).fetchone()
        rules.append(dict(row))
    return rules


def sha256_file(path: Path) -> str:
    """ফাইলের sha256 — AGENTS.md entry-contract version pinning-এর জন্য।"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_payload_bytes(payload: dict) -> bytes:
    """বাংলা মন্তব্য: hash নির্ধারণের জন্য canonical JSON — sort_keys + compact
    separators, যাতে একই অর্থের payload সবসময় একই byte sequence দেয়।"""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def generate_bundle(
    role: str,
    task_id: str,
    task_type: str | None = None,
    db_path: Path | None = None,
    agents_md_path: Path | None = None,
) -> dict:
    """একটি deterministic skill bundle তৈরি করে।

    Selection নিয়ম (#3194 §2):
      - mandatory rule → সবসময় অন্তর্ভুক্ত (filter দিয়েও বাদ যায় না);
      - scope == 'role:<role>' → অন্তর্ভুক্ত;
      - scope == 'task:<task_type>' → অন্তর্ভুক্ত (task_type দিলে);
      - বাকি সব (অন্য role/constitution WARN) → বাদ।

    বাংলা মন্তব্য: generated_at ইচ্ছাকৃতভাবে hash-এর বাইরে — একই task + একই
    policy version দুবার generate করলে content_hash অভিন্ন থাকে (replay audit)।
    """
    role = role.strip().lower()
    conn = _connect(db_path)
    try:
        all_rules = _latest_rules(conn)
    finally:
        conn.close()

    selected: list[dict] = []
    task_scope = f"task:{task_type}" if task_type else None
    for rule in all_rules:
        if rule["mandatory"]:
            selected.append(rule)
        elif rule["scope"] == f"role:{role}":
            selected.append(rule)
        elif task_scope and rule["scope"] == task_scope:
            selected.append(rule)

    # বাংলা মন্তব্য: deterministic ordering — (mandatory DESC, scope, rule_id);
    # একই ইনপুটে সবসময় একই ক্রম, কোনো dict-iteration randomness নেই।
    selected.sort(key=lambda r: (-int(r["mandatory"]), r["scope"], r["rule_id"]))

    agents_md = Path(agents_md_path) if agents_md_path else CANONICAL_FILES["agents_md"]
    agents_md_hash = sha256_file(agents_md) if agents_md.exists() else "MISSING"

    policy_versions = {r["rule_id"]: r["version"] for r in selected}

    hashed_payload = {
        "bundle_schema": BUNDLE_SCHEMA_VERSION,
        "role": role,
        "task_id": str(task_id),
        "task_type": task_type,
        "agents_md_sha256": agents_md_hash,
        "rules": [
            {"rule_id": r["rule_id"], "version": r["version"], "scope": r["scope"],
             "category": r["category"], "title": r["title"], "body": r["body"],
             "mandatory": int(r["mandatory"])}
            for r in selected
        ],
    }
    content_hash = hashlib.sha256(_canonical_payload_bytes(hashed_payload)).hexdigest()

    return {
        "bundle_schema": BUNDLE_SCHEMA_VERSION,
        "role": role,
        "task_id": str(task_id),
        "task_type": task_type,
        "agents_md_sha256": agents_md_hash,
        "content_hash": content_hash,
        "policy_versions": policy_versions,
        "rules": hashed_payload["rules"],
        # বাংলা মন্তব্য: envelope metadata — hash-এর বাইরে, audit টাইমস্ট্যাম্প মাত্র।
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def verify_bundle(bundle: dict, db_path: Path | None = None,
                  agents_md_path: Path | None = None) -> dict:
    """Bundle-এর content hash recompute করে integrity প্রমাণ করে।"""
    recomputed = {
        "bundle_schema": bundle["bundle_schema"],
        "role": bundle["role"],
        "task_id": bundle["task_id"],
        "task_type": bundle["task_type"],
        "agents_md_sha256": bundle["agents_md_sha256"],
        "rules": bundle["rules"],
    }
    expected = hashlib.sha256(_canonical_payload_bytes(recomputed)).hexdigest()
    return {
        "valid": expected == bundle.get("content_hash"),
        "expected_hash": expected,
        "recorded_hash": bundle.get("content_hash"),
    }


# ---------------------------------------------------------------------------
# Decision ledger integration — U8 decision JSON-এ bundle প্রমাণ যোগ
# ---------------------------------------------------------------------------
def augment_decision(decision: dict, bundle: dict) -> dict:
    """U8 decision ledger-এ skill_bundle hash/version stamp করে।

    # বাংলা মন্তব্য: ফলে পুরনো সিদ্ধান্ত যে সঠিক policy contract-এর অধীনে
    # নেওয়া হয়েছিল তা replay-যোগ্য — #3194 §4 (reproducibility)।
    """
    stamped = dict(decision)
    stamped["skill_bundle"] = {
        "bundle_schema": bundle["bundle_schema"],
        "content_hash": bundle["content_hash"],
        "policy_versions": bundle["policy_versions"],
        "agents_md_sha256": bundle["agents_md_sha256"],
    }
    return stamped


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cmd_seed(args: argparse.Namespace) -> int:
    result = seed_from_canonical(db_path=args.db, force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    bundle = generate_bundle(role=args.role, task_id=args.task_id,
                             task_type=args.task_type, db_path=args.db)
    text = json.dumps(bundle, ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"bundle written: {out} (content_hash={bundle['content_hash'][:16]}…)")
    else:
        print(text)
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    bundle = json.loads(Path(args.bundle).read_text(encoding="utf-8"))
    result = verify_bundle(bundle)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


def _cmd_stamp(args: argparse.Namespace) -> int:
    bundle = json.loads(Path(args.bundle).read_text(encoding="utf-8"))
    decision = json.loads(Path(args.decision).read_text(encoding="utf-8"))
    stamped = augment_decision(decision, bundle)
    Path(args.decision).write_text(
        json.dumps(stamped, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"decision stamped: bundle={bundle['content_hash'][:16]}…")
    return 0


def _cmd_rule_upsert(args: argparse.Namespace) -> int:
    # বাংলা মন্তব্য: policy write = admin authority। guard ছাড়া reject —
    # এজেন্টরা আকস্মিকভাবে rule বদলাতে পারে না (#3194 §5 read-only bundles)।
    if not args.confirm_policy_write:
        print("REFUSED: policy writes require --confirm-policy-write "
              "(admin/policy authority only — AGENTS.md §1)", file=sys.stderr)
        return 2
    if not args.rule_id or not args.title or not args.body:
        print("REFUSED: --rule-id, --title, --body are required", file=sys.stderr)
        return 2
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect(args.db)
    try:
        cur = conn.cursor()
        cur.execute("SELECT MAX(version) AS v FROM policy_rules WHERE rule_id = ?",
                    (args.rule_id,))
        prev = cur.fetchone()
        new_version = (prev["v"] or 0) + 1
        cur.execute("UPDATE policy_rules SET superseded = 1 WHERE rule_id = ?",
                    (args.rule_id,))
        cur.execute(
            "INSERT INTO policy_rules (rule_id, version, scope, category, title,"
            " body, mandatory, superseded, created_at, source)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, 'admin')",
            (args.rule_id, new_version, args.scope, args.category, args.title,
             args.body, 1 if args.mandatory else 0, now),
        )
        conn.commit()
        print(f"rule {args.rule_id} upserted → version {new_version}")
        return 0
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Skill Bundle Generator (#3194)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_seed = sub.add_parser("seed", help="bootstrap DB from canonical files")
    p_seed.add_argument("--force", action="store_true",
                        help="re-seed: changed canonical rules → new DB version")
    p_seed.add_argument("--db", default=None, help="policy DB path (default: data/supremeai.db)")
    p_seed.set_defaults(func=_cmd_seed)

    p_gen = sub.add_parser("generate", help="generate deterministic bundle")
    p_gen.add_argument("--role", required=True)
    p_gen.add_argument("--task-id", required=True)
    p_gen.add_argument("--task-type", default=None)
    p_gen.add_argument("--out", default=None)
    p_gen.add_argument("--db", default=None, help="policy DB path (default: data/supremeai.db)")
    p_gen.set_defaults(func=_cmd_generate)

    p_ver = sub.add_parser("verify", help="recompute bundle content hash")
    p_ver.add_argument("--bundle", required=True)
    p_ver.set_defaults(func=_cmd_verify)

    p_stamp = sub.add_parser("stamp", help="stamp U8 decision JSON with bundle hash")
    p_stamp.add_argument("--bundle", required=True)
    p_stamp.add_argument("--decision", required=True)
    p_stamp.set_defaults(func=_cmd_stamp)

    p_rule = sub.add_parser("rule-upsert", help="admin: upsert a policy rule version")
    p_rule.add_argument("--rule-id", required=True)
    p_rule.add_argument("--scope", default="universal")
    p_rule.add_argument("--category", default="admin")
    p_rule.add_argument("--title", required=True)
    p_rule.add_argument("--body", required=True)
    p_rule.add_argument("--mandatory", action="store_true")
    p_rule.add_argument("--confirm-policy-write", action="store_true")
    p_rule.add_argument("--db", default=None, help="policy DB path (default: data/supremeai.db)")
    p_rule.set_defaults(func=_cmd_rule_upsert)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
