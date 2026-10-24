"""
Git Log Knowledge Extractor
Analyzes git history to extract error-fix patterns and architecture learnings.
Fulfills SK-0065 in autonomous_seed_knowledge.json.
"""

"""
Git Log Knowledge Extractor
Analyzes git history to extract error-fix patterns and architecture learnings.
Fulfills SK-0065 in autonomous_seed_knowledge.json.
"""

import contextlib
import json
import re
import sqlite3
import subprocess
import time
import uuid

from core.logging_config import logger

try:
    from core.feedback_loop import FeedbackLoop

    _feedback = FeedbackLoop()
except ImportError:
    _feedback = None

DB_PATH = "data/git_knowledge.db"


def init_db():
    """Initializes the SQLite database and table."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS git_fixes (
                id TEXT PRIMARY KEY,
                commit_hash TEXT,
                subject TEXT,
                body TEXT,
                files_changed TEXT,
                timestamp INTEGER
            )
        """)
        conn.commit()


def run_git(args):
    try:
        return subprocess.check_output(["git", *args], stderr=subprocess.STDOUT).decode("utf-8")
    except Exception as e:
        logger.info(f"Error running git: {e}")
        return ""


def extract_knowledge():
    init_db()
    logger.info("🔍 Analyzing git log for knowledge extraction...")
    # Get last 50 commits with diffs
    logs = run_git(["log", "-n", "50", "--pretty=format:COMMIT:%H%nSUBJECT:%s%nBODY:%b", "-p"])

    knowledge_entries = []
    commits = logs.split("COMMIT:")
    fix_keywords = ["fix", "solve", "resolved", "bug", "patch", "error"]

    for commit in commits:
        if not commit.strip():
            continue
        lines = commit.split("\n")
        commit_id = lines[0]
        subject = ""
        body = ""
        diff = ""

        in_body = False
        in_diff = False

        for line in lines[1:]:
            if line.startswith("SUBJECT:"):
                subject = line[8:]
            elif line.startswith("BODY:"):
                body = line[5:]
                in_body = True
            elif line.startswith("diff --git"):
                in_body = False
                in_diff = True
                diff += line + "\n"
            elif in_diff:
                diff += line + "\n"
            elif in_body:
                body += line + "\n"

        if any(kw in subject.lower() for kw in fix_keywords):
            logger.info(f"  ✨ Found fix pattern in commit {commit_id[:8]}: {subject}")
            files_changed = re.findall(r"diff --git a/(.*?) b/", diff)

            entry = {
                "id": str(uuid.uuid4()),
                "commit_hash": commit_id,
                "subject": subject,
                "body": body.strip(),
                "files_changed": json.dumps(files_changed),
                "timestamp": int(time.time()),
            }
            knowledge_entries.append(entry)

            if _feedback is not None:
                with contextlib.suppress(Exception):
                    _feedback.record_edit(
                        file_path=",".join(files_changed[:3]),
                        diff_summary=subject,
                    )

    if knowledge_entries:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.executemany(
                "INSERT OR REPLACE INTO git_fixes VALUES (:id, :commit_hash, :subject, :body, :files_changed, :timestamp)",
                knowledge_entries,
            )
            conn.commit()
        logger.info(f"✅ Extracted and stored {len(knowledge_entries)} entries into {DB_PATH}")


if __name__ == "__main__":
    extract_knowledge()
