"""
MCP Server for Neon Serverless Postgres Integration in SupremeAI 2.0.

এই সার্ভারটি এজেন্টকে সরাসরি Neon Postgres-এ ব্রাঞ্চ তৈরি/ডিলিট,
সার্ভারলেস SQL কুয়েরি এক্সেকিউট এবং কম্পিউট এন্ডপয়েন্ট ম্যানেজ করার ক্ষমতা দেয়।
"""

import json
import os
from enum import StrEnum
from typing import Any

import psycopg2
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from core.config import settings
from core.logging_config import logger
from utils.environment import is_admin_authorized

mcp = FastMCP("neon_mcp")

CHARACTER_LIMIT = 25000
NEON_API_BASE = "https://console.neon.tech/api/v2"


def _get_neon_db_url() -> str:
    """Neon Database URL রিটার্ন করে।"""
    if not is_admin_authorized():
        return ""
    return (
        os.environ.get("NEON_DATABASE_URL", "")
        or getattr(settings, "neon_database_url", "")
        or getattr(settings, "database_url", "")
    )


def _get_neon_api_key() -> str:
    """Neon API Key রিটার্ন করে।"""
    if not is_admin_authorized():
        return ""
    return os.environ.get("NEON_API_KEY", "") or getattr(settings, "neon_api_key", "")


def _get_connection(db_url: str | None = None):
    """PostgreSQL কানেকশন পায়।"""
    target_url = db_url or _get_neon_db_url()
    if not target_url or target_url.startswith("sqlite"):
        return None
    try:
        conn = psycopg2.connect(target_url)
        return conn
    except Exception as e:
        logger.error(f"Neon DB connection error: {e}")
        return None


def _handle_db_error(e: Exception) -> str:
    """ডাটাবেস এরর স্ট্যান্ডার্ডাইজ্ড হ্যান্ডলিং।"""
    error_msg = str(e)
    if "connection" in error_msg.lower():
        return "Error: Neon database connection failed. Check NEON_DATABASE_URL is set correctly."
    if "syntax" in error_msg.lower() or "parse" in error_msg.lower():
        return "Error: SQL syntax error. Please check your query syntax."
    if "permission" in error_msg.lower():
        return "Error: Permission denied. Check database credentials and permissions."
    return f"Error: Database operation failed - {error_msg}"


class ResponseFormat(StrEnum):
    """আউটপুট ফরম্যাট।"""

    MARKDOWN = "markdown"
    JSON = "json"


class ExecuteQueryInput(BaseModel):
    """SQL কুয়েরি এক্সিকিউটের জন্য ইনপুট।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    query: str = Field(..., description="এক্সিকিউট করার SQL কুয়েরি", min_length=1)
    params: list[Any] | None = Field(default_factory=list, description="কুয়েরি প্যারামিটারস (ঐচ্ছিক)")
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN, description="আউটপুট ফরম্যাট"
    )
    database_url: str | None = Field(
        default=None, description="নির্দিষ্ট ব্রাঞ্চের ডাটাবেস URL (ঐচ্ছিক, ডিফল্ট NEON_DATABASE_URL)"
    )


class CreateBranchInput(BaseModel):
    """Neon ব্রাঞ্চ তৈরির ইনপুট।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    project_id: str = Field(..., description="Neon Project ID (যেমন: ep-frosty-surf-b3n7nx5b)")
    branch_name: str = Field(..., description="তৈরি করার ব্রাঞ্চের নাম", min_length=1, max_length=100)
    parent_id: str | None = Field(default=None, description="প্যারেন্ট ব্রাঞ্চ ID (ঐচ্ছিক)")


class DeleteBranchInput(BaseModel):
    """Neon ব্রাঞ্চ ডিলিটের ইনপুট।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    project_id: str = Field(..., description="Neon Project ID")
    branch_id: str = Field(..., description="ডিলিট করার ব্রাঞ্চ ID")


class ListBranchesInput(BaseModel):
    """Neon ব্রাঞ্চ লিস্ট করার ইনপুট।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    project_id: str = Field(..., description="Neon Project ID")


@mcp.tool(
    name="neon_execute_sql",
    annotations={
        "title": "Execute SQL Query on Neon",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def neon_execute_sql(params: ExecuteQueryInput) -> str:
    """
    Neon Serverless Postgres ডাটাবেসে SQL কুয়েরি এক্সিকিউট করে।

    Args:
        params (ExecuteQueryInput): ইনপুট প্যারামিটারস

    Returns:
        str: কুয়েরি রেজাল্ট বা এরর মেসেজ
    """
    destructive_keywords = ["drop", "delete", "truncate", "alter"]
    if not is_admin_authorized() and any(kw in params.query.lower() for kw in destructive_keywords):
        return json.dumps(
            {
                "error": "Admin authorization required for destructive operations",
                "message": "Set ADMIN_AUTHORIZED=true in environment",
            },
            ensure_ascii=False,
        )

    target_url = params.database_url or _get_neon_db_url()
    if not target_url:
        return json.dumps({"error": "NEON_DATABASE_URL not configured"}, ensure_ascii=False)

    conn = None
    try:
        conn = _get_connection(target_url)
        if not conn:
            return json.dumps({"error": "Failed to connect to Neon database"}, ensure_ascii=False)

        cur = conn.cursor()
        cur.execute(params.query, params.params if params.params else None)

        if params.query.strip().upper().startswith("SELECT"):
            columns = [desc[0] for desc in cur.description] if cur.description else []
            rows = cur.fetchall()

            if params.response_format == ResponseFormat.MARKDOWN:
                if not rows:
                    cur.close()
                    return "No results found."

                header = "| " + " | ".join(columns) + " |"
                separator = "| " + " | ".join(["---"] * len(columns)) + " |"
                md_rows = ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
                output = "\n".join([header, separator] + md_rows)
                cur.close()
                return output[:CHARACTER_LIMIT]

            cur.close()
            result = [dict(zip(columns, row, strict=False)) for row in rows]
            return json.dumps(result, default=str, ensure_ascii=False)[:CHARACTER_LIMIT]

        conn.commit()
        affected_rows = cur.rowcount
        cur.close()
        return json.dumps(
            {"success": True, "affected_rows": affected_rows, "query": params.query},
            ensure_ascii=False,
        )

    except Exception as e:
        return _handle_db_error(e)
    finally:
        if conn:
            try:
                conn.close()
            except Exception as e:
                logger.warning(f"Connection close error: {e}")


@mcp.tool(
    name="neon_list_tables",
    annotations={
        "title": "List Tables in Neon",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def neon_list_tables() -> str:
    """Neon ডাটাবেসের সব টেবিলের তালিকা দেখায়।"""
    if not _get_neon_db_url():
        return json.dumps({"error": "NEON_DATABASE_URL not configured"}, ensure_ascii=False)

    conn = None
    try:
        conn = _get_connection()
        if not conn:
            return json.dumps({"error": "Failed to connect to Neon database"}, ensure_ascii=False)

        cur = conn.cursor()
        cur.execute(
            """
            SELECT table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
            """
        )
        tables = cur.fetchall()
        cur.close()

        return json.dumps(
            {
                "tables": [{"name": t[0], "type": t[1]} for t in tables],
                "count": len(tables),
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return _handle_db_error(e)
    finally:
        if conn:
            try:
                conn.close()
            except Exception as e:
                logger.warning(f"Connection close error: {e}")


@mcp.tool(
    name="neon_list_branches",
    annotations={
        "title": "List Neon Database Branches",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def neon_list_branches(params: ListBranchesInput) -> str:
    """নির্দিষ্ট Neon প্রজেক্টের সব ব্রাঞ্চের তালিকা নিয়ে আসে।"""
    api_key = _get_neon_api_key()
    if not api_key:
        return json.dumps({"error": "NEON_API_KEY not configured"}, ensure_ascii=False)

    import httpx

    url = f"{NEON_API_BASE}/projects/{params.project_id}/branches"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            return json.dumps(
                {"error": f"Neon API error: {resp.status_code}", "detail": resp.text},
                ensure_ascii=False,
            )
        return json.dumps(resp.json(), ensure_ascii=False)


@mcp.tool(
    name="neon_create_branch",
    annotations={
        "title": "Create Neon Database Branch",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def neon_create_branch(params: CreateBranchInput) -> str:
    """টেস্টিং বা নতুন ফিচারের জন্য Neon ডাটাবেস ব্রাঞ্চ তৈরি করে।"""
    if not is_admin_authorized():
        return json.dumps(
            {"error": "Admin authorization required to create Neon branches"}, ensure_ascii=False
        )

    api_key = _get_neon_api_key()
    if not api_key:
        return json.dumps({"error": "NEON_API_KEY not configured"}, ensure_ascii=False)

    import httpx

    url = f"{NEON_API_BASE}/projects/{params.project_id}/branches"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {"branch": {"name": params.branch_name}}
    if params.parent_id:
        payload["branch"]["parent_id"] = params.parent_id

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code not in (200, 201):
            return json.dumps(
                {"error": f"Neon API error: {resp.status_code}", "detail": resp.text},
                ensure_ascii=False,
            )
        return json.dumps(resp.json(), ensure_ascii=False)


@mcp.tool(
    name="neon_delete_branch",
    annotations={
        "title": "Delete Neon Database Branch",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def neon_delete_branch(params: DeleteBranchInput) -> str:
    """নির্দিষ্ট Neon ব্রাঞ্চ ডিলিট করে।"""
    if not is_admin_authorized():
        return json.dumps(
            {"error": "Admin authorization required to delete Neon branches"}, ensure_ascii=False
        )

    api_key = _get_neon_api_key()
    if not api_key:
        return json.dumps({"error": "NEON_API_KEY not configured"}, ensure_ascii=False)

    import httpx

    url = f"{NEON_API_BASE}/projects/{params.project_id}/branches/{params.branch_id}"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.delete(url, headers=headers)
        if resp.status_code not in (200, 204):
            return json.dumps(
                {"error": f"Neon API error: {resp.status_code}", "detail": resp.text},
                ensure_ascii=False,
            )
        return json.dumps(
            {"success": True, "deleted_branch_id": params.branch_id}, ensure_ascii=False
        )


if __name__ == "__main__":
    mcp.run()
