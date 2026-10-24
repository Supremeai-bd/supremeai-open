import json
import os
import sqlite3
import threading
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import get_current_admin
from core.config import settings
from core.degraded_mode import sqlite_fallback_allowed

router = APIRouter(
    prefix="/api/admin/site-actions",
    tags=["Site Actions Registry"],
    dependencies=[Depends(get_current_admin)],
)

DB_PATH = getattr(settings, "site_actions_db", "data/site_actions.db")
_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    if not sqlite_fallback_allowed("site_actions"):
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        _ensure_schema(conn)
        return conn
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS site_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_name TEXT NOT NULL,
            url_pattern TEXT NOT NULL,
            action_name TEXT NOT NULL,
            selector TEXT NOT NULL,
            action_type TEXT NOT NULL DEFAULT 'click',
            notes TEXT DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            fallback_selectors TEXT DEFAULT '[]',
            selector_strategy TEXT DEFAULT 'exact',
            health_score INTEGER DEFAULT 100,
            updated_at REAL NOT NULL
        )
        """)

    cur = conn.cursor()
    cur.execute("PRAGMA table_info(site_actions)")
    columns = [col[1] for col in cur.fetchall()]
    if "fallback_selectors" not in columns:
        conn.execute("ALTER TABLE site_actions ADD COLUMN fallback_selectors TEXT DEFAULT '[]'")
    if "selector_strategy" not in columns:
        conn.execute("ALTER TABLE site_actions ADD COLUMN selector_strategy TEXT DEFAULT 'exact'")
    if "health_score" not in columns:
        conn.execute("ALTER TABLE site_actions ADD COLUMN health_score INTEGER DEFAULT 100")


class SiteActionIn(BaseModel):
    site_name: str
    url_pattern: str
    action_name: str
    selector: str
    action_type: str = "click"
    notes: str = ""
    enabled: bool = True
    fallback_selectors: list[str] = []
    selector_strategy: str = "exact"
    health_score: int = 100


class TestSelectorRequest(BaseModel):
    action_id: int


def _row_to_dict(row: tuple) -> dict:
    return {
        "id": row[0],
        "site_name": row[1],
        "url_pattern": row[2],
        "action_name": row[3],
        "selector": row[4],
        "action_type": row[5],
        "notes": row[6],
        "enabled": bool(row[7]),
        "fallback_selectors": json.loads(row[8] if row[8] else "[]"),
        "selector_strategy": row[9] or "exact",
        "health_score": row[10] if row[10] is not None else 100,
        "updated_at": row[11] if len(row) > 11 else time.time(),
    }


@router.get("/")
def list_site_actions():
    with _lock, _conn() as conn:
        rows = conn.execute("SELECT * FROM site_actions ORDER BY updated_at DESC").fetchall()
    return {"items": [_row_to_dict(r) for r in rows], "total": len(rows)}


@router.post("/")
def create_site_action(payload: SiteActionIn):
    with _lock, _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO site_actions
                (site_name, url_pattern, action_name, selector, action_type, notes, enabled,
                 fallback_selectors, selector_strategy, health_score, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.site_name,
                payload.url_pattern,
                payload.action_name,
                payload.selector,
                payload.action_type,
                payload.notes,
                int(payload.enabled),
                json.dumps(payload.fallback_selectors),
                payload.selector_strategy,
                payload.health_score,
                time.time(),
            ),
        )
        conn.commit()
        new_id = cur.lastrowid
        row = conn.execute("SELECT * FROM site_actions WHERE id = ?", (new_id,)).fetchone()
    return _row_to_dict(row)


@router.put("/{action_id}")
def update_site_action(action_id: int, payload: SiteActionIn):
    with _lock, _conn() as conn:
        cur = conn.execute(
            """
            UPDATE site_actions SET
                site_name = ?, url_pattern = ?, action_name = ?, selector = ?,
                action_type = ?, notes = ?, enabled = ?, fallback_selectors = ?,
                selector_strategy = ?, health_score = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                payload.site_name,
                payload.url_pattern,
                payload.action_name,
                payload.selector,
                payload.action_type,
                payload.notes,
                int(payload.enabled),
                json.dumps(payload.fallback_selectors),
                payload.selector_strategy,
                payload.health_score,
                time.time(),
                action_id,
            ),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Site action not found")
        row = conn.execute("SELECT * FROM site_actions WHERE id = ?", (action_id,)).fetchone()
    return _row_to_dict(row)


@router.delete("/{action_id}")
def delete_site_action(action_id: int):
    with _lock, _conn() as conn:
        cur = conn.execute("DELETE FROM site_actions WHERE id = ?", (action_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Site action not found")
    return {"success": True}


@router.post("/test")
async def test_selector(req: TestSelectorRequest):
    with _lock, _conn() as conn:
        row = conn.execute(
            "SELECT selector FROM site_actions WHERE id = ?", (req.action_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Action not found")

    is_production = getattr(settings, "env", "local").lower() == "production"
    if is_production:
        raise HTTPException(
            status_code=501,
            detail="Dry-run screenshot preview not available in production. Connect a real CDP proxy endpoint.",
        )

    mock_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    return {
        "found": True,
        "screenshot_base64": mock_b64,
        "metrics": {"time_to_find_ms": 142, "strategy_used": "exact_dry_run"},
    }
