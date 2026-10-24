"""
backend/scripts/migrate_files_to_db.py  (ক্যানোনিকাল ভার্সন)
================================================================
SupremeAI 2.0 — Code-to-Database migration script (একক ক্যানোনিকাল ভার্সন)

এই স্ক্রিপ্টটা নিচের দুইটা ডুপ্লিকেট/broken স্ক্রিপ্টকে replace করে:
  - scripts/migrate_files_to_db.py        (ভুল import path: tools.mcp_supabase, আসলে tools.mcp.mcp_supabase)
  - backend/scripts/migrate_files_to_db.py (আগের ভার্সনে DROP TABLE CASCADE ছিল — প্রতি রান এ ডেটা মুছে যেত!)

🚨 গুরুত্বপূর্ণ ফিক্স:
  1. আর কোনো DROP TABLE নেই — শুধু CREATE TABLE IF NOT EXISTS (ডেটা কখনো মুছবে না)
  2. ON CONFLICT DO UPDATE ব্যবহার করা হয়েছে (আগের ON CONFLICT DO NOTHING এর বদলে) —
     তাই skill/rule এর কোড পরিবর্তন হলে সেটা re-run করলে DB আপডেট হবে
  3. rules ডিরেক্টরি এখন সঠিক পাথ থেকে পড়ে: <repo_root>/docs/context_modules/*.xml
     (আগে ভুল করে backend/docs/context_modules খুঁজত, যেটা আসলে exist ই করে না)
  4. import path ঠিক করা হয়েছে (dependency এখন শুধু settings.supabase_database_url + psycopg2,
     কোনো broken tools.mcp_supabase import নেই)

চালানোর আগে অবশ্যই:
  - .env / environment এ SUPABASE_DATABASE_URL_POOLER সেট করা থাকতে হবে
  - প্রথমবার --dry-run দিয়ে চালিয়ে দেখে নিন কী migrate হবে

ব্যবহার:
    python backend/scripts/migrate_files_to_db.py             # আসল migration চালাবে
    python backend/scripts/migrate_files_to_db.py --dry-run   # শুধু দেখাবে কী migrate হতো, DB তে কিছু লিখবে না
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# বাংলা মন্তব্য (S314 ফিক্স): এই script শুধু repo-র নিজস্ব
# docs/context_modules/*.xml পড়ে (developer-authored, trusted), তাই real
# risk কম ছিল, কিন্তু defusedxml ইতিমধ্যে dependency-তে ছিল বলে best-practice
# অনুযায়ী সরিয়ে নেওয়া হলো — billion-laughs/XXE class attack একদম বন্ধ।
import defusedxml.ElementTree as ET
import psycopg2

from core.logging_config import logger

# backend ডিরেক্টরি sys.path এ যোগ করা হচ্ছে, যাতে core.*, tools.* ইম্পোর্ট করা যায়
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(BACKEND_DIR) == "scripts":
    BACKEND_DIR = os.path.dirname(BACKEND_DIR)  # backend/scripts -> backend
REPO_ROOT = os.path.dirname(BACKEND_DIR)  # backend -> repo root
sys.path.insert(0, BACKEND_DIR)

try:
    from core.config import settings
    from tools.headless_agent_registry import get_headless_agent_configs
except ImportError as e:
    logger.error(f"প্রয়োজনীয় মডিউল ইম্পোর্ট করা যায়নি: {e}. backend ডিরেক্টরি থেকে বা repo root থেকে চালান।")
    sys.exit(1)


def get_db_connection() -> psycopg2.extensions.connection | None:
    """settings.supabase_database_url থেকে ডাটাবেস কানেকশন তৈরি করে।"""
    db_url = getattr(settings, "supabase_database_url", None)
    if not db_url:
        logger.error("SUPABASE_DATABASE_URL_POOLER কনফিগার করা নেই (settings.supabase_database_url)।")
        return None
    try:
        conn = psycopg2.connect(db_url)
        logger.info("🐘 ডাটাবেসে সফলভাবে কানেক্ট হয়েছে।")
        return conn
    except psycopg2.OperationalError as e:
        logger.error(f"ডাটাবেস কানেকশন ব্যর্থ: {e}")
        return None


def ensure_tables(conn, dry_run: bool) -> None:
    """
    ডাটাবেস টেবিল তৈরি করে *যদি না থাকে* — কখনো বিদ্যমান টেবিল ড্রপ করে না।
    ⚠️ আগের ভার্সনে এখানে `DROP TABLE ... CASCADE` ছিল যা প্রতি রান এ সব ডেটা মুছে দিত। এখন সেটা সরানো হয়েছে।
    """
    if dry_run:
        logger.info("[DRY-RUN] টেবিল তৈরি স্কিপ করা হলো।")
        return

    logger.info("ডাটাবেস টেবিল আছে কিনা যাচাই করা হচ্ছে (কোনো DROP হবে না)...")
    cursor = conn.cursor()
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            skill_name VARCHAR(255) UNIQUE NOT NULL,
            description TEXT,
            code TEXT NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'active',
            version INT NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS rules (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            rule_key VARCHAR(255) UNIQUE NOT NULL,
            category VARCHAR(100) NOT NULL,
            value TEXT NOT NULL,
            description TEXT,
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS agent_configs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_name VARCHAR(255) UNIQUE NOT NULL,
            description TEXT,
            config_json JSONB NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """)
        conn.commit()
        logger.success("টেবিল প্রস্তুত (বিদ্যমান ডেটা অক্ষত আছে)।")
    except Exception as e:
        logger.error(f"টেবিল তৈরিতে সমস্যা: {e}")
        conn.rollback()
    finally:
        cursor.close()


def migrate_skills(conn, dry_run: bool) -> None:
    """backend/core/skills থেকে .py ফাইল পড়ে 'skills' টেবিলে upsert করে (আপডেট-সহ)।"""
    logger.info("Skill migration শুরু হচ্ছে...")
    skills_dir = os.path.join(BACKEND_DIR, "core", "skills")
    if not os.path.isdir(skills_dir):
        logger.warning(f"Skills ডিরেক্টরি পাওয়া যায়নি: {skills_dir}। স্কিপ করা হলো।")
        return

    migrated_count = 0
    cursor = None if dry_run else conn.cursor()
    for filename in sorted(os.listdir(skills_dir)):
        if filename.endswith(".py") and filename != "__init__.py":
            skill_name = os.path.splitext(filename)[0]
            file_path = os.path.join(skills_dir, filename)
            try:
                with open(file_path, encoding="utf-8") as f:
                    code = f.read()
                description = f"Skill for {skill_name.replace('_', ' ')}. Automatically migrated."

                if dry_run:
                    logger.info(f"  [DRY-RUN] -> মাইগ্রেট হতো: {skill_name}")
                    migrated_count += 1
                    continue

                cursor.execute(
                    """
                    INSERT INTO skills (skill_name, description, code, status, version)
                    VALUES (%s, %s, %s, 'active', 1)
                    ON CONFLICT (skill_name) DO UPDATE
                    SET code = EXCLUDED.code,
                        description = EXCLUDED.description,
                        version = skills.version + 1,
                        updated_at = NOW();
                    """,
                    (skill_name, description, code),
                )
                migrated_count += 1
                logger.success(f"  -> Migrated skill: {skill_name}")
            except Exception as e:
                logger.error(f"Skill মাইগ্রেট করতে ব্যর্থ {skill_name}: {e}")

    if not dry_run:
        conn.commit()
        cursor.close()
    logger.info(f"Skill migration সম্পন্ন। মোট প্রক্রিয়াকৃত: {migrated_count}")


def migrate_rules(conn, dry_run: bool) -> None:
    """<repo_root>/docs/context_modules/*.xml থেকে rules পড়ে 'rules' টেবিলে upsert করে।"""
    logger.info("Rules migration শুরু হচ্ছে...")
    rules_dir = os.path.join(REPO_ROOT, "docs", "context_modules")
    if not os.path.isdir(rules_dir):
        logger.warning(f"Rules ডিরেক্টরি পাওয়া যায়নি: {rules_dir}। স্কিপ করা হলো।")
        return

    migrated_count = 0
    cursor = None if dry_run else conn.cursor()
    for filename in sorted(os.listdir(rules_dir)):
        if filename.endswith(".xml"):
            file_path = os.path.join(rules_dir, filename)
            try:
                tree = ET.parse(file_path)
                root = tree.getroot()
                category = os.path.splitext(filename)[0].replace("_context", "")

                for rule_tag in root.findall("rule"):
                    rule_key = rule_tag.get("key", f"{category}_{migrated_count}")
                    value = (rule_tag.text or "").strip()
                    description = rule_tag.get("description", f"Rule for {category}")

                    if dry_run:
                        logger.info(f"  [DRY-RUN] -> মাইগ্রেট হতো: {rule_key}")
                        migrated_count += 1
                        continue

                    cursor.execute(
                        """
                        INSERT INTO rules (rule_key, category, value, description, is_enabled)
                        VALUES (%s, %s, %s, %s, TRUE)
                        ON CONFLICT (rule_key) DO UPDATE
                        SET value = EXCLUDED.value,
                            description = EXCLUDED.description,
                            updated_at = NOW();
                        """,
                        (rule_key, category, value, description),
                    )
                    migrated_count += 1
                    logger.success(f"  -> Migrated rule: {rule_key}")

            except Exception as e:
                logger.error(f"{filename} থেকে rule পার্স/মাইগ্রেট করতে ব্যর্থ: {e}")

    if not dry_run:
        conn.commit()
        cursor.close()
    logger.info(f"Rules migration সম্পন্ন। মোট প্রক্রিয়াকৃত: {migrated_count}")


def migrate_agent_configs(conn, dry_run: bool) -> None:
    """tools/headless_agent_registry.py থেকে config নিয়ে 'agent_configs' টেবিলে upsert করে।"""
    logger.info("Agent config migration শুরু হচ্ছে...")
    try:
        agent_configs = get_headless_agent_configs()
        migrated_count = 0
        cursor = None if dry_run else conn.cursor()

        for agent_name, config in agent_configs.items():
            description = config.get("description", f"Configuration for {agent_name}")
            config_json = json.dumps(config)

            if dry_run:
                logger.info(f"  [DRY-RUN] -> মাইগ্রেট হতো: {agent_name}")
                migrated_count += 1
                continue

            cursor.execute(
                """
                INSERT INTO agent_configs (agent_name, description, config_json, status)
                VALUES (%s, %s, %s, 'active')
                ON CONFLICT (agent_name) DO UPDATE
                SET config_json = EXCLUDED.config_json,
                    description = EXCLUDED.description,
                    updated_at = NOW();
                """,
                (agent_name, description, config_json),
            )
            migrated_count += 1
            logger.success(f"  -> Migrated agent config: {agent_name}")

        if not dry_run:
            conn.commit()
            cursor.close()
        logger.info(f"Agent config migration সম্পন্ন। মোট প্রক্রিয়াকৃত: {migrated_count}")

    except Exception as e:
        logger.error(f"Agent configs মাইগ্রেট করতে ব্যর্থ: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="SupremeAI 2.0 code-to-database migration")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="শুধু দেখাবে কী migrate হতো, DB তে কোনো write হবে না",
    )
    args = parser.parse_args()

    logger.info(
        "🚀 CODE_TO_DATABASE migration শুরু হচ্ছে..." + (" [DRY-RUN MODE]" if args.dry_run else "")
    )

    if args.dry_run:
        migrate_skills(None, dry_run=True)
        migrate_rules(None, dry_run=True)
        migrate_agent_configs(None, dry_run=True)
        logger.info("✅ Dry-run সম্পন্ন। কোনো ডেটা লেখা হয়নি।")
        return

    db_conn = get_db_connection()
    if not db_conn:
        logger.error("ডাটাবেস কানেকশন ব্যর্থ হওয়ায় migration চালানো গেল না।")
        sys.exit(1)

    try:
        ensure_tables(db_conn, dry_run=False)
        migrate_skills(db_conn, dry_run=False)
        migrate_rules(db_conn, dry_run=False)
        migrate_agent_configs(db_conn, dry_run=False)
        logger.info("✅ Migration process সম্পন্ন হয়েছে।")
    finally:
        db_conn.close()


if __name__ == "__main__":
    main()
