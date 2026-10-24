import os
import sqlite3
from typing import Any


class SQLiteMemoryStore:
    """Manages transactional data, session variables, and task history in SQLite database."""

    def __init__(self, db_path: str | None = None):
        if not db_path:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.db_path = os.path.join(base_dir, "data", "supreme_memory.db")
        else:
            self.db_path = db_path

        self.conn = None
        self._init_db()

    def _get_connection(self):
        if self.db_path == ":memory:":
            if self.conn is None:
                self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            return self.conn
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _close_connection(self, conn):
        if self.db_path != ":memory:":
            conn.close()

    def _init_db(self):
        if self.db_path != ":memory:":
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role TEXT,
                content TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_description TEXT,
                task_type TEXT,
                success INTEGER,
                cost REAL,
                outcome_text TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        self._close_connection(conn)

    def log_task(
        self,
        task_description: str,
        task_type: str,
        success: bool,
        cost: float,
        outcome_text: str,
    ):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tasks (task_description, task_type, success, cost, outcome_text) VALUES (?, ?, ?, ?, ?)",
            (task_description, task_type, 1 if success else 0, cost, outcome_text),
        )
        conn.commit()
        self._close_connection(conn)

    def get_task_history(self) -> list[dict[str, Any]]:
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks ORDER BY timestamp DESC")
        rows = cursor.fetchall()
        result = [dict(r) for r in rows]
        self._close_connection(conn)
        return result

    def save_message(self, session_id: str, role: str, content: str):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO sessions (id) VALUES (?)", (session_id,))
        cursor.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )
        conn.commit()
        self._close_connection(conn)

    def get_session_messages(self, session_id: str) -> list[dict[str, Any]]:
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role, content, timestamp FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        )
        rows = cursor.fetchall()
        result = [dict(r) for r in rows]
        self._close_connection(conn)
        return result
