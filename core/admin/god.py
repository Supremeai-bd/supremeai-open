import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from core.degraded_mode import sqlite_fallback_allowed
from core.logging_config import logger

# শেয়ার্ড ইউটিলিটি — Firestore ও টেস্ট এনভায়রনমেন্ট চেক কেন্দ্রীভূত
from utils.firestore_helpers import get_firestore_db


class AdminGodLayer:
    """
    Constitutional enforcement layer.
    Every write action requires admin approval unless explicitly whitelisted.
    Reads from Google Cloud Firestore (Distributed & Serverless) with SQLite local fallback.
    """

    def __init__(self, db_path: str | None = None):
        if not db_path:
            # বাংলা মন্তব্য: settings থেকে রুলস ডাটাবেস পাথ রিড করা হচ্ছে
            try:
                from core.config import settings

                db_path = settings.admin_rules_db
            except ImportError:
                db_path = "data/constitutional_rules.db"

            if not db_path:
                db_path = "data/constitutional_rules.db"

        self.db_path = Path(db_path)
        import os

        # P0 (Task 9-c2): SQLite-only-by-design rules fallback. In production
        # without SUPABASE_ALLOW_DB_DEGRADATION=true the ephemeral
        # constitutional_rules.db file is REFUSED (CRITICAL logged once by
        # core.degraded_mode): the layer boots WITHOUT touching the filesystem,
        # reads resolve to safe defaults ("not authorized" = fail-closed) and
        # SQLite writes are skipped loudly. Firestore stays the primary store.
        self._sqlite_refused = not sqlite_fallback_allowed("admin_god_rules")
        if self._sqlite_refused:
            logger.warning(
                "[P0] AdminGodLayer running WITHOUT local SQLite rules store — rules "
                "resolve to safe defaults (deny). The degradation flag no longer permits "
                "SQLite fallback; provision Firestore."
            )
            self.sqlite_lock = threading.Lock()

            self.collection_name = "constitutional_rules"
            self._db = None
            return

        data_dir_env = os.getenv("DATA_DIR")
        if data_dir_env:
            self.db_path = Path(data_dir_env) / self.db_path.name
        elif os.getenv("RENDER"):
            # বাংলা মন্তব্য: Render কনটেইনারের রিড-ওনলি ফাইল সিস্টেমের জন্য /tmp ফাস্ট ডিরেক্টরি ব্যবহার করা
            self.db_path = Path("/tmp/data") / self.db_path.name

        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError) as e:
            logger.warning(
                f"Permission denied creating directory for {self.db_path}: {e}. Falling back to /tmp/data."
            )
            self.db_path = Path("/tmp/data") / self.db_path.name
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.sqlite_lock = threading.Lock()

        self.collection_name = "constitutional_rules"
        # রিফ্যাক্টর: সরাসরি firestore.Client() এর বদলে শেয়ার্ড হেল্পার ব্যবহার
        self._db = get_firestore_db()
        if self._db is not None:
            try:
                self._init_db()
            except Exception as e:
                logger.warning(
                    f"Failed to initialize Firestore for AdminGodLayer: {e}. Falling back to SQLite."
                )
                self._db = None
        else:
            logger.warning(
                "Firestore unavailable or in test mode. AdminGodLayer using local SQLite fallback."
            )

        self._init_sqlite_db()

    def _init_sqlite_db(self):
        # বাংলা মন্তব্য: লোকাল SQLite ডাটাবেস এবং ডিফল্ট রুলস সেটআপ
        from contextlib import closing

        with self.sqlite_lock:
            with closing(sqlite3.connect(self.db_path, check_same_thread=False)) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS rules (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        key TEXT UNIQUE NOT NULL,
                        value TEXT NOT NULL,
                        updated_at REAL NOT NULL
                    )
                    """)
                conn.commit()

        # বাংলা মন্তব্য: নিরাপত্তার জন্য প্রথমবার চালানোর সময় সকল অ্যাডমিন অথরাইজেশন ডিফল্টভাবে 'false' রাখা হচ্ছে এবং সতর্কতা লগ করা হচ্ছে।
        if not self.get_rule("admin_authorized"):
            self.set_rule("admin_authorized", "false")
            logger.warning(
                "Defaulting 'admin_authorized' to 'false' for security. Please configure explicitly."
            )
        if not self.get_rule("autofix_authorized"):
            self.set_rule("autofix_authorized", "false")
            logger.warning("Defaulting 'autofix_authorized' to 'false' for security.")
        if not self.get_rule("autofix_reporting_authorized"):
            self.set_rule("autofix_reporting_authorized", "false")
            logger.warning("Defaulting 'autofix_reporting_authorized' to 'false' for security.")

    def _init_db(self):
        if not self._db:
            return
        try:
            # বাংলা মন্তব্য: Firestore-এ autofix_authorized এবং admin_authorized নিয়মগুলো না থাকলে সেগুলো 'false' দিয়ে ইনিশিয়ালাইজ করা হচ্ছে।
            doc_ref = self._db.collection(self.collection_name).document("admin_authorized")
            if not doc_ref.get().exists:
                self.set_rule("admin_authorized", "false")
                logger.warning("Firestore: Defaulting 'admin_authorized' to 'false' for security.")

            autofix_ref = self._db.collection(self.collection_name).document("autofix_authorized")
            if not autofix_ref.get().exists:
                self.set_rule("autofix_authorized", "false")
                logger.warning(
                    "Firestore: Defaulting 'autofix_authorized' to 'false' for security."
                )
        except Exception as e:
            logger.error(f"Error initializing AdminGodLayer DB: {e}")

    def get_rule(self, key: str, default: str | None = None) -> str | None:
        if self._db:
            try:
                doc_ref = self._db.collection(self.collection_name).document(key)
                doc = doc_ref.get()
                if doc.exists:
                    return doc.to_dict().get("value", default)
                return default
            except Exception as e:
                logger.error(f"Error fetching rule {key} from Firestore: {e}")

        # P0 (Task 9-c2): SQLite fallback refused in production — resolve to the
        # safe default (deny) instead of ever touching the ephemeral file.
        if getattr(self, "_sqlite_refused", False):
            return default

        # বাংলা মন্তব্য: ফায়ারস্টোর নিষ্ক্রিয় বা টেস্ট মোডে থাকলে SQLite ব্যাকআপ থেকে রিড হবে
        from contextlib import closing

        with self.sqlite_lock:
            with closing(sqlite3.connect(self.db_path, check_same_thread=False)) as conn:
                cur = conn.execute("SELECT value FROM rules WHERE key = ?", (key,))
                row = cur.fetchone()
                return row[0] if row else default

    def list_rules(self) -> list[dict[str, Any]]:
        """All constitutional rules as [{"key", "value", "updated_at"}].

        Issue #1489/#1469: `GET /api/admin/rules` (api/routes/admin.py) and
        `GET /api/admin/llm/rules` (api/routes/admin_llm.py) call this method,
        which never existed on the layer — `AttributeError` → 500 on every
        admin rules read. Firestore is the primary store; the SQLite fallback
        applies only where degradation is allowed (production refuses the
        ephemeral file, matching get_rule/set_rule policy).
        """
        rules: dict[str, dict[str, Any]] = {}

        if self._db:
            try:
                for doc in self._db.collection(self.collection_name).stream():
                    data = doc.to_dict() or {}
                    rules[doc.id] = {
                        "key": doc.id,
                        "value": str(data.get("value", "")),
                        "updated_at": data.get("updated_at"),
                    }
            except Exception as e:
                logger.error(f"list_rules: Firestore read failed: {e}")

        if not rules and not self._sqlite_refused:
            from contextlib import closing

            try:
                with self.sqlite_lock:
                    with closing(sqlite3.connect(self.db_path, check_same_thread=False)) as conn:
                        conn.row_factory = sqlite3.Row
                        rows = conn.execute("SELECT key, value, updated_at FROM rules").fetchall()
                for row in rows:
                    rules[row["key"]] = {
                        "key": row["key"],
                        "value": row["value"],
                        "updated_at": row["updated_at"],
                    }
            except Exception as e:
                logger.warning(f"list_rules: SQLite read failed: {e}")

        return list(rules.values())

    def set_rule(self, key: str, value: str) -> None:
        if self._db:
            try:
                doc_ref = self._db.collection(self.collection_name).document(key)
                doc_ref.set({"value": value, "updated_at": time.time()})
                logger.info(f"Constitutional rule updated in Firestore: {key} = {value}")
                return
            except Exception as e:
                logger.error(f"Error setting rule {key} in Firestore: {e}. Falling back to SQLite.")

        # P0 (Task 9-c2): SQLite fallback refused in production — skip the
        # ephemeral file loudly instead of silently persisting there.
        if getattr(self, "_sqlite_refused", False):
            logger.warning(
                f"[P0] rule {key!r} NOT persisted: SQLite fallback refused in production."
            )
            return

        # বাংলা মন্তব্য: SQLite ব্যাকআপ ডাটাবেসে রুল সংরক্ষণ করা হচ্ছে
        from contextlib import closing

        with self.sqlite_lock:
            with closing(sqlite3.connect(self.db_path, check_same_thread=False)) as conn:
                conn.execute(
                    """
                    INSERT INTO rules(key, value, updated_at)
                    VALUES(?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                    """,
                    (key, value, time.time()),
                )
                conn.commit()
        logger.info(f"Constitutional rule updated in SQLite: {key} = {value}")

    def is_admin_action_allowed(self, action: str) -> bool:
        whitelist = {"health", "read", "learn", "ping"}
        if action in whitelist:
            return True
        flag = self.get_rule("admin_authorized")
        return flag == "true"

    def enforce(self, action: str) -> None:
        if not self.is_admin_action_allowed(action):
            raise PermissionError(
                "Action blocked by constitutional rules. Admin authorization required."
            )
