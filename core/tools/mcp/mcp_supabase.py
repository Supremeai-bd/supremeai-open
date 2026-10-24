"""
MCP Server for Supabase/Postgres Database Integration in SupremeAI 2.0.

এই সার্ভারটি এজেন্টকে সরাসরে Supabase/Postgres ডাটাবেসে স্কিমা তৈরি,
টেবিল মাইগ্রেশন এবং SQL কুয়েরি রান করার ক্ষমতা দেয়।
"""

import json

# বাংলা মন্তব্য: পরিবেশের ভেরিয়েবল চেক করার জন্য os মডিউল ইমপোর্ট করা হলো
import os
from enum import StrEnum
from typing import Any

import psycopg2
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from core.config import settings
from core.logging_config import logger
from utils.environment import is_admin_authorized

mcp = FastMCP("supabase_mcp")

CHARACTER_LIMIT = 25000


def _get_supabase_db_url() -> str:
    # This MCP has no request-scoped tenant connection, so global credentials are platform-only.
    if not is_admin_authorized():
        return ""
    return (
        getattr(settings, "supabase_database_url", "")
        or os.environ.get("SUPABASE_DATABASE_URL", "")
        or os.environ.get("DATABASE_URL", "")
    )


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


class CreateTableInput(BaseModel):
    """টেবিল তৈরির জন্য ইনপুট।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    table_name: str = Field(..., description="তৈরি করার টেবিলের নাম", min_length=1, max_length=100)
    columns: str = Field(..., description="কলাম ডেফিনিশন (SQL সিনট্যাক্স)", min_length=1)
    if_not_exists: bool = Field(default=True, description="IF NOT EXISTS যোগ করবে কিনা")


class MigrationInput(BaseModel):
    """ডাটাবেস মাইগ্রেশনের জন্য ইনপুট।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    migration_name: str = Field(..., description="মাইগ্রেশনের নাম", min_length=1, max_length=100)
    up_sql: str = Field(..., description="UP migration SQL", min_length=1)
    down_sql: str = Field(..., description="DOWN migration SQL", min_length=1)


def _get_connection():
    """PostgreSQL কানেকশন পায়।"""
    supabase_db_url = _get_supabase_db_url()
    if not supabase_db_url or supabase_db_url.startswith("sqlite"):
        return None
    try:
        conn = psycopg2.connect(supabase_db_url)
        return conn
    except Exception as e:
        try:
            import loguru

            loguru.logger.error(f"Tool execution error: {e}")
        except Exception as e:
            logger.warning(f"Exception suppressed: {e}")
        return None


def _handle_db_error(e: Exception) -> str:
    """ডাটাবেস এরর স্ট্যান্ডার্ডাইজ্ড হ্যান্ডলিং।"""
    error_msg = str(e)
    if "connection" in error_msg.lower():
        return "Error: Database connection failed. Check SUPABASE_DATABASE_URL is set correctly."
    if "syntax" in error_msg.lower() or "parse" in error_msg.lower():
        return "Error: SQL syntax error. Please check your query syntax."
    if "permission" in error_msg.lower():
        return "Error: Permission denied. Check database credentials and permissions."
    return f"Error: Database operation failed - {error_msg}"


@mcp.tool(
    name="supabase_execute_sql",
    annotations={
        "title": "Execute SQL Query",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def supabase_execute_sql(params: ExecuteQueryInput) -> str:
    """
    Supabase/Postgres ডাটাবেসে SQL কুয়েরি এক্সিকিউট করে।

    এই টুলটি SELECT, INSERT, UPDATE, DELETE সব কুয়েরি সমর্থন করে।
    এডমিন অথরাইজেশন প্রয়োজন এমন ক্রুয়াগুলো যাচাই করে।

    Args:
        params (ExecuteQueryInput): ইনপুট প্যারামিটার সম্বলিত:
            - query (str): SQL কুয়েরি স্ট্রিং
            - params (Optional[List[Any]]): প্যারামিটার লিস্ট
            - response_format (ResponseFormat): আউটপুট ফরম্যাট

    Returns:
        str: কুয়েরি রেজাল্ট বা এরর মেসেজ
    """
    # বাংলা মন্তব্য: কেবলমাত্র সত্যিকারের ডেস্ট্রাকটিভ অপারেশনগুলো চেক করা হচ্ছে
    destructive_keywords = ["drop", "delete", "truncate", "alter"]
    if not is_admin_authorized() and any(kw in params.query.lower() for kw in destructive_keywords):
        return json.dumps(
            {
                "error": "Admin authorization required for destructive operations",
                "message": "Set ADMIN_AUTHORIZED=true in environment",
            },
            ensure_ascii=False,
        )

    if not _get_supabase_db_url():
        return json.dumps({"error": "SUPABASE_DATABASE_URL not configured"}, ensure_ascii=False)

    conn = None
    try:
        conn = _get_connection()
        if not conn:
            return json.dumps({"error": "Failed to connect to database"}, ensure_ascii=False)

        cur = conn.cursor()
        cur.execute(params.query, params.params if params.params else None)

        if params.query.strip().upper().startswith("SELECT"):
            columns = [desc[0] for desc in cur.description] if cur.description else []
            rows = cur.fetchall()

            if params.response_format == ResponseFormat.MARKDOWN:
                if not rows:
                    result = "# Query Results\n\nNo rows returned."
                else:
                    lines = ["# Query Results\n"]
                    lines.append("| " + " | ".join(columns) + " |")
                    lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
                    for row in rows[:100]:
                        lines.append("| " + " | ".join(str(v) for v in row) + " |")
                    if len(rows) > 100:
                        lines.append(f"\n*Showing 100 of {len(rows)} rows*")
                    result = "\n".join(lines)
            else:
                result = json.dumps(
                    {
                        "columns": columns,
                        "rows": [list(row) for row in rows],
                        "row_count": len(rows),
                    },
                    ensure_ascii=False,
                )

            cur.close()
            return result

        conn.commit()
        affected = cur.rowcount
        cur.close()

        return json.dumps(
            {
                "success": True,
                "affected_rows": affected,
                "message": f"Query executed successfully. Affected {affected} rows.",
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
                try:
                    import loguru

                    loguru.logger.error(f"Tool execution error: {e}")
                except Exception as e:
                    logger.warning(f"Exception suppressed: {e}")
                pass


@mcp.tool(
    name="supabase_create_table",
    annotations={
        "title": "Create Table",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def supabase_create_table(params: CreateTableInput) -> str:
    """
    নতুন ডাটাবেস টেবিল তৈরি করে।

    Args:
        params (CreateTableInput): ইনপুট প্যারামিটার সম্বলিত:
            - table_name (str): টেবিলের নাম
            - columns (str): কলাম ডেফিনিশন
            - if_not_exists (bool): IF NOT EXISTS যোগ করবে কিনা

    Returns:
        str: টেবিল তৈরির স্ট্যাটাস
    """
    if not is_admin_authorized():
        return json.dumps(
            {"error": "Admin authorization required for table creation"},
            ensure_ascii=False,
        )

    if not _get_supabase_db_url():
        return json.dumps({"error": "SUPABASE_DATABASE_URL not configured"}, ensure_ascii=False)

    if_not_exists = "IF NOT EXISTS" if params.if_not_exists else ""
    query = f"CREATE TABLE {if_not_exists} {params.table_name} ({params.columns})"

    conn = None
    try:
        conn = _get_connection()
        if not conn:
            return json.dumps({"error": "Failed to connect to database"}, ensure_ascii=False)

        cur = conn.cursor()
        cur.execute(query)
        conn.commit()
        cur.close()

        return json.dumps(
            {
                "success": True,
                "table_name": params.table_name,
                "message": f"Table '{params.table_name}' created successfully.",
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
                try:
                    import loguru

                    loguru.logger.error(f"Tool execution error: {e}")
                except Exception as e:
                    logger.warning(f"Exception suppressed: {e}")
                pass


@mcp.tool(
    name="supabase_run_migration",
    annotations={
        "title": "Run Database Migration",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def supabase_run_migration(params: MigrationInput) -> str:
    """
    ডাটাবেস মাইগ্রেশন চালায়।

    এই টুলটি উভয় UP এবং DOWN migration সমর্থন করে।
    মাইগ্রেশন হিস্ট্রি ডাটাবেসে লগ করে।

    Args:
        params (MigrationInput): ইনপুট প্যারামিটার সম্বলিত:
            - migration_name (str): মাইগ্রেশনের নাম
            - up_sql (str): UP SQL স্টেটমেন্ট
            - down_sql (str): DOWN SQL স্টেটমেন্ট

    Returns:
        str: মাইগ্রেশন স্ট্যাটাস
    """
    if not is_admin_authorized():
        return json.dumps(
            {"error": "Admin authorization required for migrations"}, ensure_ascii=False
        )

    if not _get_supabase_db_url():
        return json.dumps({"error": "SUPABASE_DATABASE_URL not configured"}, ensure_ascii=False)

    conn = None
    try:
        conn = _get_connection()
        if not conn:
            return json.dumps({"error": "Failed to connect to database"}, ensure_ascii=False)

        cur = conn.cursor()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS migrations (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                up_sql TEXT,
                down_sql TEXT,
                applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """
        )

        cur.execute("SELECT id FROM migrations WHERE name = %s", (params.migration_name,))
        if cur.fetchone():
            conn.close()
            return json.dumps(
                {"message": f"Migration '{params.migration_name}' already applied"},
                ensure_ascii=False,
            )

        cur.execute(params.up_sql)
        cur.execute(
            "INSERT INTO migrations (name, up_sql, down_sql) VALUES (%s, %s, %s)",
            (params.migration_name, params.up_sql, params.down_sql),
        )
        conn.commit()
        cur.close()

        return json.dumps(
            {
                "success": True,
                "migration": params.migration_name,
                "message": f"Migration '{params.migration_name}' applied successfully.",
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
                try:
                    import loguru

                    loguru.logger.error(f"Tool execution error: {e}")
                except Exception as e:
                    logger.warning(f"Exception suppressed: {e}")
                pass


@mcp.tool(
    name="supabase_list_tables",
    annotations={
        "title": "List Database Tables",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def supabase_list_tables() -> str:
    """
    ডাটাবেসের সব টেবিলের তালিকা দেখায়।

    Returns:
        str: টেবিল তালিকা JSON ফরম্যাটে
    """
    if not _get_supabase_db_url():
        return json.dumps({"error": "SUPABASE_DATABASE_URL not configured"}, ensure_ascii=False)

    conn = None
    try:
        conn = _get_connection()
        if not conn:
            return json.dumps({"error": "Failed to connect to database"}, ensure_ascii=False)

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
                try:
                    import loguru

                    loguru.logger.error(f"Tool execution error: {e}")
                except Exception as e:
                    logger.warning(f"Exception suppressed: {e}")
                pass


class ExplainQueryInput(BaseModel):
    """SQL কোয়েরি পারফরম্যান্স বিশ্লেষণের জন্য ইনপুট।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    query: str = Field(..., description="বিশ্লেষণ করার জন্য SQL EXPLAIN কোয়েরি", min_length=5)
    analyze: bool = Field(
        default=False, description="সত্যিই এক্সিকিউট করে নিখুঁত টাইম পরিমাপ করবে কি না (ANALYZE)"
    )


class DescribeTableInput(BaseModel):
    """টেবিল স্কিমা ও ইনডেক্স বিস্তারিত দেখার জন্য ইনপুট।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    table_name: str = Field(..., description="যে টেবিলের কলাম ও ইনডেক্স স্ট্রাকচার দেখা হবে", min_length=1)


@mcp.tool(
    name="supabase_explain_query",
    annotations={
        "title": "Explain SQL Query Performance Plan",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def supabase_explain_query(params: ExplainQueryInput) -> str:
    """
    SQL কোয়েরি চালালে ডাটাবেস কীভাবে রান করবে (Execution Plan) তা বিশ্লেষণ করে দেখায়।

    Args:
        params (ExplainQueryInput): query ও analyze ফ্ল্যাগ

    Returns:
        str: JSON ফরম্যাটে EXPLAIN রেজাল্ট
    """
    conn = None
    try:
        conn = _get_connection()
        if not conn:
            return json.dumps({"error": "Failed to connect to database"}, ensure_ascii=False)

        explain_sql = f"EXPLAIN {'(ANALYZE, FORMAT JSON)' if params.analyze else '(FORMAT JSON)'} {params.query}"

        cur = conn.cursor()
        cur.execute(explain_sql)
        plan = cur.fetchone()
        cur.close()

        if plan and plan[0]:
            return json.dumps({"query": params.query, "plan": plan[0]}, ensure_ascii=False)
        return json.dumps({"error": "No execution plan returned."}, ensure_ascii=False)

    except Exception as e:
        return _handle_db_error(e)
    finally:
        if conn:
            try:
                conn.close()
            except Exception as e:
                try:
                    import loguru

                    loguru.logger.error(f"Tool execution error: {e}")
                except Exception as e:
                    logger.warning(f"Exception suppressed: {e}")
                pass


@mcp.tool(
    name="supabase_describe_table",
    annotations={
        "title": "Describe Database Table Schema & Indexes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def supabase_describe_table(params: DescribeTableInput) -> str:
    """
    নির্দিষ্ট টেবিলের সকল কলাম, ডাটা টাইপ, প্রাইমারি কি এবং ইনডেক্সের তালিকা দেখায়।

    Args:
        params (DescribeTableInput): টেবিলের নাম

    Returns:
        str: কলাম তালিকা ও ইনডেক্স তথ্য
    """
    conn = None
    try:
        conn = _get_connection()
        if not conn:
            return json.dumps({"error": "Failed to connect to database"}, ensure_ascii=False)

        cur = conn.cursor()
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
            """,
            (params.table_name,),
        )
        columns = cur.fetchall()

        cur.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = %s",
            (params.table_name,),
        )
        indexes = cur.fetchall()
        cur.close()

        if not columns:
            return json.dumps(
                {"error": f"Table '{params.table_name}' not found"}, ensure_ascii=False
            )

        return json.dumps(
            {
                "table": params.table_name,
                "columns": [
                    {"name": c[0], "type": c[1], "nullable": c[2] == "YES", "default": c[3]}
                    for c in columns
                ],
                "indexes": [{"name": i[0], "definition": i[1]} for i in indexes],
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
                try:
                    import loguru

                    loguru.logger.error(f"Tool execution error: {e}")
                except Exception as e:
                    logger.warning(f"Exception suppressed: {e}")
                pass


if __name__ == "__main__":
    mcp.run()
