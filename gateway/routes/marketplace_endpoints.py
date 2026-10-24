import json
import os
import sqlite3
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.deps import get_current_user_token
from core.degraded_mode import sqlite_fallback_allowed
from core.errors.error_bus import with_error_bus
from core.logging_config import logger
from database.supabase_client import db
from tools.resource_catalog import ResourceCatalog
from tools.social.marketplace_agent import MarketplaceAgent

# Issue #1654: install mutates the local skills DB — enforce auth in-file
# (not only via mount flags) so the guard survives re-mounting.
router = APIRouter(
    prefix="/marketplace",
    tags=["marketplace"],
    dependencies=[Depends(get_current_user_token)],
)
marketplace_agent = MarketplaceAgent()

ALLOWED_CATALOG_SOURCES = {
    "awesome-selfhosted",
    "awesome-python",
    "ossinsight",
    "libraries.io",
}
DEFAULT_CATALOG_SOURCES = ["awesome-selfhosted", "awesome-python"]

# Legacy Local DB Logic (Merged)
DB_PATH = os.environ.get("SUPREMEAI_MARKETPLACE_DB", "data/marketplace.db")


def _get_conn() -> sqlite3.Connection:
    # P0 (Task 9-c2 + Wave 0.1): SQLite-only-by-design legacy catalog. In
    # production the ephemeral marketplace.db file is REFUSED unconditionally
    # (the degradation flag no longer permits SQLite fallback; CRITICAL logged
    # once by core.degraded_mode). To keep the API alive
    # (no 500s) each call gets a fresh IN-MEMORY connection: schema auto-creates,
    # searches return the remote results only, and local writes are per-request
    # only — the ephemeral file is never created or read.
    if not sqlite_fallback_allowed("marketplace_legacy_db"):
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)
        return conn
    (os.makedirs(os.path.dirname(DB_PATH), exist_ok=True) if os.path.dirname(DB_PATH) else None)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            version TEXT NOT NULL,
            description TEXT,
            dependencies TEXT,
            installed INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'builtin',
            installed_at REAL
        )
        """)
    conn.commit()


_seeded = False
_SEED_INDEX = [
    {
        "name": "web_scraper",
        "version": "1.0.0",
        "description": "Scrapes website contents using BeautifulSoup.",
        "dependencies": "beautifulsoup4, requests",
        "source": "builtin",
    },
    {
        "name": "csv_exporter",
        "version": "1.0.0",
        "description": "Exports tabular data to CSV using pandas.",
        "dependencies": "pandas",
        "source": "builtin",
    },
]


def _seed(conn: sqlite3.Connection) -> None:
    global _seeded
    if _seeded:
        return
    row = conn.execute("SELECT COUNT(*) AS c FROM skills").fetchone()
    if row["c"] > 0:
        _seeded = True
        return
    now = os.path.getctime(DB_PATH) if os.path.exists(DB_PATH) else 0
    for item in _SEED_INDEX:
        conn.execute(
            "INSERT INTO skills (id, name, version, description, dependencies, installed, source, installed_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
            (
                str(uuid.uuid4()),
                item["name"],
                item["version"],
                item["description"],
                item["dependencies"],
                item["source"],
                now,
            ),
        )
    conn.commit()
    _seeded = True


@with_error_bus("get_enabled_catalog_sources")
def get_enabled_catalog_sources() -> list[str]:
    if not db.client:
        return DEFAULT_CATALOG_SOURCES

    try:
        enabled = db.get_config("marketplace.resource_sources")
    except Exception:
        logger.exception("Unhandled exception")
        enabled = None

    if isinstance(enabled, str):
        try:
            enabled = json.loads(enabled)
        except Exception:
            logger.exception("Unhandled exception")
            enabled = [item.strip() for item in enabled.split(",") if item.strip()]

    if not isinstance(enabled, list):
        return DEFAULT_CATALOG_SOURCES

    enabled_sources = [src for src in enabled if src in ALLOWED_CATALOG_SOURCES]
    return enabled_sources or DEFAULT_CATALOG_SOURCES


def filter_requested_catalog_sources(
    categories: list[str], enabled_sources: list[str]
) -> list[str]:
    return [c for c in categories if c in enabled_sources]


class SearchRequest(BaseModel):
    query: str
    categories: list[str] | None = None
    filters: dict | None = None
    installed_only: bool = False


class InstallRequest(BaseModel):
    tool_id: str
    target_environment: str = "local"
    sandbox: bool = True
    version: str | None = None


@router.post("/search")
async def search_marketplaces(payload: SearchRequest, request: Request):
    try:
        categories = payload.categories if payload.categories is not None else []
        filters = payload.filters if payload.filters is not None else {}

        # 1. Search Remote Marketplaces
        results = marketplace_agent.search_marketplaces(payload.query, categories, filters)

        enabled_sources = get_enabled_catalog_sources()
        catalog_sources = filter_requested_catalog_sources(categories, enabled_sources)
        if not catalog_sources and not categories:
            catalog_sources = enabled_sources

        http_client = getattr(request.app.state, "http_client", None)
        async with ResourceCatalog(http_client=http_client) as catalog:
            resource_results = await catalog.search(payload.query, sources=catalog_sources, limit=5)

        if resource_results:
            results.extend(resource_results)

        # 2. Search Local Legacy DB
        conn = _get_conn()
        try:
            _seed(conn)
            sql = "SELECT id, name, version, description, dependencies, installed, source FROM skills WHERE (name LIKE ? OR description LIKE ?)"
            like = f"%{payload.query}%"
            params = [like, like]
            if payload.installed_only:
                sql += " AND installed = 1"
            rows = conn.execute(sql, params).fetchall()
            for r in rows:
                results.append(
                    {
                        "name": r["name"],
                        "marketplace": "local_db",
                        "description": r["description"],
                        "installed": bool(r["installed"]),
                        "id": r["id"],
                    }
                )
        except Exception as e:
            logger.error(f"Local DB search error: {e}")
        finally:
            conn.close()

        return {"status": "success", "tools": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/install")
async def install_tool(payload: InstallRequest):
    try:
        # Check Local DB First
        conn = _get_conn()
        local_tool = None
        try:
            _seed(conn)
            local_tool = conn.execute(
                "SELECT id, name, installed FROM skills WHERE name = ?",
                (payload.tool_id,),
            ).fetchone()
            if local_tool:
                if local_tool["installed"]:
                    return {
                        "success": True,
                        "tool_id": payload.tool_id,
                        "installed": True,
                        "message": "Already installed locally.",
                    }
                conn.execute(
                    "UPDATE skills SET installed = 1, installed_at = ? WHERE id = ?",
                    (__import__("time").time(), local_tool["id"]),
                )
                conn.commit()
                return {
                    "success": True,
                    "tool_id": payload.tool_id,
                    "installed": True,
                    "message": "Installed locally via legacy DB.",
                }
        except Exception as e:
            logger.error(f"Local install error: {e}")
        finally:
            conn.close()

        # Fallback to Agent Remote Installation
        res = marketplace_agent.install_tool(
            payload.tool_id, payload.target_environment, payload.sandbox
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
