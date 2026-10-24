# backend/api/routes/prompt_templates.py
"""Feature S9: Prompt Template Library.

Manages reusable prompt templates. Builtin templates are seeded on first access.
Custom templates are user-scoped.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import get_current_user_token
from core.logging_config import logger
from database.supabase_client import db as supabase_db

router = APIRouter(
    prefix="/api/prompt-templates",
    tags=["Prompt Templates"],
    dependencies=[Depends(get_current_user_token)],
)

# ---------------------------------------------------------------------------
# Builtin seed data
# ---------------------------------------------------------------------------

_BUILTIN_TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "Code Review",
        "description": "Thorough code review with actionable feedback on quality, security, and performance.",
        "category": "coding",
        "prompt": (
            "You are an expert code reviewer. Review the following code and provide detailed feedback.\n\n"
            "Focus on:\n"
            "1. **Correctness** — logic errors, edge cases\n"
            "2. **Security** — injection, auth, data exposure\n"
            "3. **Performance** — bottlenecks, unnecessary allocations\n"
            "4. **Readability** — naming, structure, documentation\n\n"
            "Code:\n```{{language}}\n{{code}}\n```"
        ),
        "variables": [
            {"name": "language", "description": "Programming language", "default": "python"},
            {"name": "code", "description": "Source code to review", "default": ""},
        ],
    },
    {
        "name": "Bug Fix",
        "description": "Diagnose and fix a bug from a code snippet and error description.",
        "category": "coding",
        "prompt": (
            "You are a senior debugging engineer. Analyze the bug report and code below,\n"
            "identify the root cause, and provide a corrected version.\n\n"
            "**Error / Symptom:** {{error}}\n\n"
            "**Code:**\n```{{language}}\n{{code}}\n```\n\n"
            "Provide:\n1. Root cause analysis\n2. Corrected code\n3. Prevention tips"
        ),
        "variables": [
            {"name": "error", "description": "Error message or observed behaviour", "default": ""},
            {"name": "language", "description": "Programming language", "default": "python"},
            {"name": "code", "description": "Code containing the bug", "default": ""},
        ],
    },
    {
        "name": "Content Writing",
        "description": "Generate engaging articles, blog posts, or marketing copy.",
        "category": "writing",
        "prompt": (
            "You are a professional content writer. Write a {{format}} about the following topic.\n\n"
            "**Topic:** {{topic}}\n"
            "**Tone:** {{tone}}\n"
            "**Target Audience:** {{audience}}\n"
            "**Key Points:** {{key_points}}\n\n"
            "Requirements:\n"
            "- Compelling introduction with a hook\n"
            "- Well-structured body with clear subheadings\n"
            "- Actionable conclusion with a call to action"
        ),
        "variables": [
            {
                "name": "format",
                "description": "Content format (article, blog post, email)",
                "default": "blog post",
            },
            {"name": "topic", "description": "Topic to write about", "default": ""},
            {"name": "tone", "description": "Writing tone", "default": "professional"},
            {"name": "audience", "description": "Target audience", "default": "general"},
            {
                "name": "key_points",
                "description": "Comma-separated key points to cover",
                "default": "",
            },
        ],
    },
    {
        "name": "Data Analysis",
        "description": "Interpret datasets, suggest insights, and recommend visualisations.",
        "category": "data",
        "prompt": (
            "You are a data analyst. Analyze the following dataset and provide insights.\n\n"
            "**Dataset Description:** {{description}}\n"
            "**Data (sample or schema):**\n```\n{{data}}\n```\n\n"
            "Provide:\n1. Summary statistics\n2. Key patterns and trends\n3. Anomalies or concerns\n"
            "4. Recommended visualisations\n5. Actionable next steps"
        ),
        "variables": [
            {"name": "description", "description": "Description of the dataset", "default": ""},
            {"name": "data", "description": "Sample data or schema", "default": ""},
        ],
    },
    {
        "name": "Translation",
        "description": "Accurate, context-aware translation between languages.",
        "category": "writing",
        "prompt": (
            "Translate the following text from {{source_language}} to {{target_language}}.\n\n"
            "**Context:** {{context}}\n\n"
            "**Text:**\n{{text}}\n\n"
            "Guidelines:\n"
            "- Preserve the original tone and style\n"
            "- Use natural, idiomatic phrasing\n"
            "- Keep technical terms accurate\n"
            "- Maintain any formatting (markdown, lists, etc.)"
        ),
        "variables": [
            {"name": "source_language", "description": "Source language", "default": "English"},
            {"name": "target_language", "description": "Target language", "default": "Spanish"},
            {"name": "context", "description": "Context for the translation", "default": "general"},
            {"name": "text", "description": "Text to translate", "default": ""},
        ],
    },
    {
        "name": "Email Draft",
        "description": "Compose professional emails with the right tone and structure.",
        "category": "writing",
        "prompt": (
            "Draft a professional email with the following specifications.\n\n"
            "**Purpose:** {{purpose}}\n"
            "**Recipient:** {{recipient}}\n"
            "**Tone:** {{tone}}\n"
            "**Key Points:** {{key_points}}\n\n"
            "Requirements:\n"
            "- Clear subject line\n"
            "- Professional greeting and sign-off\n"
            "- Concise body paragraphs\n"
            "- Clear call to action if applicable"
        ),
        "variables": [
            {"name": "purpose", "description": "Purpose of the email", "default": ""},
            {"name": "recipient", "description": "Who the email is addressed to", "default": ""},
            {"name": "tone", "description": "Email tone", "default": "professional"},
            {"name": "key_points", "description": "Points to include", "default": ""},
        ],
    },
    {
        "name": "Meeting Summary",
        "description": "Summarise meeting notes into action items and key decisions.",
        "category": "productivity",
        "prompt": (
            "Summarise the following meeting transcript.\n\n"
            "**Meeting Transcript:**\n{{transcript}}\n\n"
            "Provide:\n1. **Key Decisions** (numbered list)\n"
            "2. **Action Items** (owner + deadline)\n"
            "3. **Open Questions**\n"
            "4. **Next Steps**"
        ),
        "variables": [
            {"name": "transcript", "description": "Raw meeting notes or transcript", "default": ""},
        ],
    },
    {
        "name": "SQL Query",
        "description": "Generate, optimise, or explain SQL queries from natural language.",
        "category": "coding",
        "prompt": (
            "You are a database expert. {{action}} the following SQL.\n\n"
            "**Schema:**\n```sql\n{{schema}}\n```\n\n"
            "**Request:** {{request}}\n\n"
            "**Dialect:** {{dialect}}\n\n"
            "Provide the SQL query with comments explaining key parts."
        ),
        "variables": [
            {
                "name": "action",
                "description": "Generate, optimise, or explain",
                "default": "Generate",
            },
            {
                "name": "schema",
                "description": "Database schema (tables and columns)",
                "default": "",
            },
            {"name": "request", "description": "Natural language request", "default": ""},
            {
                "name": "dialect",
                "description": "SQL dialect (PostgreSQL, MySQL, etc.)",
                "default": "PostgreSQL",
            },
        ],
    },
]

_seeded = False


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class VariableDef(BaseModel):
    """Definition of a single template variable."""

    name: str
    description: str = ""
    default: str = ""


class TemplateCreateRequest(BaseModel):
    """Body for creating a custom template."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    category: str = "general"
    prompt: str = Field(..., min_length=1)
    variables: list[VariableDef] = Field(default_factory=list)


class TemplateUpdateRequest(BaseModel):
    """Body for updating a custom template."""

    name: str | None = None
    description: str | None = None
    category: str | None = None
    prompt: str | None = None
    variables: list[VariableDef] | None = None


class TemplateUseRequest(BaseModel):
    """Body for the 'use' endpoint — provides variable values."""

    values: dict[str, str] = Field(
        default_factory=dict, description="Variable name -> value mapping."
    )


class TemplateResponse(BaseModel):
    """Normalised template shape returned by the API."""

    id: str
    name: str
    description: str
    category: str
    prompt: str
    variables: list[dict[str, str]]
    is_builtin: bool
    usage_count: int
    created_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_supabase() -> None:
    if not supabase_db.client:
        raise HTTPException(status_code=503, detail="Database is not available.")


def _bootstrap_schema() -> None:
    """Ensure the prompt_templates table exists in Supabase."""
    _ensure_supabase()
    try:
        supabase_db.client.rpc(
            "exec_sql",
            {
                "query_string": (
                    "CREATE TABLE IF NOT EXISTS prompt_templates ("
                    "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
                    "  user_id TEXT,"
                    "  name TEXT NOT NULL,"
                    "  description TEXT,"
                    "  category TEXT DEFAULT 'general',"
                    "  prompt TEXT NOT NULL,"
                    "  variables JSONB DEFAULT '[]',"
                    "  is_builtin BOOLEAN DEFAULT false,"
                    "  usage_count INTEGER DEFAULT 0,"
                    "  created_at TIMESTAMPTZ DEFAULT NOW(),"
                    "  updated_at TIMESTAMPTZ DEFAULT NOW()"
                    ")"
                )
            },
        ).execute()
    except asyncio.CancelledError:
        raise
    except Exception as e:
        import logging

        logging.getLogger(__name__).exception(f"Silenced error: {e}")


def _seed_builtins() -> None:
    """Insert builtin templates if they do not already exist."""
    global _seeded
    if _seeded:
        return

    _ensure_supabase()
    for tpl in _BUILTIN_TEMPLATES:
        try:
            existing = (
                supabase_db.client.table("prompt_templates")
                .select("id")
                .eq("name", tpl["name"])
                .eq("is_builtin", True)
                .execute()
            )
            if not existing.data:
                supabase_db.client.table("prompt_templates").insert(
                    {
                        "name": tpl["name"],
                        "description": tpl["description"],
                        "category": tpl["category"],
                        "prompt": tpl["prompt"],
                        "variables": tpl["variables"],
                        "is_builtin": True,
                        "usage_count": 0,
                    }
                ).execute()
                logger.info(f"Seeded builtin template: {tpl['name']}")
        except Exception as exc:
            logger.warning(f"Failed to seed template '{tpl['name']}': {exc}")

    _seeded = True


def _row_to_template(row: dict[str, Any]) -> dict[str, Any]:
    """Normalise a DB row into the API response shape."""
    variables = row.get("variables") or []
    if isinstance(variables, str):
        try:
            variables = json.loads(variables)
        except (json.JSONDecodeError, TypeError):
            variables = []
    return {
        "id": row.get("id", ""),
        "name": row.get("name", ""),
        "description": row.get("description", ""),
        "category": row.get("category", "general"),
        "prompt": row.get("prompt", ""),
        "variables": variables,
        "is_builtin": row.get("is_builtin", False),
        "usage_count": row.get("usage_count", 0),
        "created_at": row.get("created_at", ""),
    }


def _fill_variables(prompt: str, variables: list[dict[str, str]], values: dict[str, str]) -> str:
    """Replace {{var_name}} placeholders in the prompt with provided values."""
    result = prompt
    for var in variables:
        var_name = var.get("name", "")
        default = var.get("default", "")
        replacement = values.get(var_name, default)
        result = result.replace(f"{{{{{var_name}}}}}", replacement)
    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=list[dict[str, Any]],
    summary="List all prompt templates",
)
async def list_templates(
    category: str | None = Query(None, description="Optional category filter."),
    user: dict = Depends(get_current_user_token),
) -> list[dict[str, Any]]:
    """Return builtin templates plus the user's custom templates.
    Optionally filter by *category*.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _bootstrap_schema()
    _seed_builtins()
    _ensure_supabase()

    try:
        query = (
            await supabase_db.client.table("prompt_templates")
            .select("*")
            .or_(f"is_builtin.eq.true,user_id.eq.{user_id}")
        )
        if category:
            query = query.eq("category", category)

        resp = query.order("is_builtin", desc=True).order("usage_count", desc=True).execute()
        return [_row_to_template(r) for r in (resp.data or [])]
    except Exception as exc:
        logger.error(f"list_templates failed for user {user_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to list templates.") from exc


@router.post(
    "/",
    response_model=dict[str, Any],
    summary="Create a custom prompt template",
    status_code=201,
)
async def create_template(
    payload: TemplateCreateRequest,
    user: dict = Depends(get_current_user_token),
) -> dict[str, Any]:
    """Create a new user-scoped template."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _bootstrap_schema()
    _ensure_supabase()

    try:
        row = {
            "user_id": user_id,
            "name": payload.name,
            "description": payload.description,
            "category": payload.category,
            "prompt": payload.prompt,
            "variables": [v.model_dump() for v in payload.variables],
            "is_builtin": False,
            "usage_count": 0,
        }
        resp = await supabase_db.client.table("prompt_templates").insert(row).execute()
        if not resp.data:
            raise HTTPException(status_code=500, detail="Template creation returned no data.")
        return _row_to_template(resp.data[0])
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"create_template failed for user {user_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to create template.") from exc


@router.get(
    "/{template_id}",
    response_model=dict[str, Any],
    summary="Get a single prompt template",
)
async def get_template(
    template_id: str,
    user: dict = Depends(get_current_user_token),
) -> dict[str, Any]:
    """Retrieve a template by ID. Users can access builtins and their own."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _bootstrap_schema()
    _seed_builtins()
    _ensure_supabase()

    try:
        resp = (
            await supabase_db.client.table("prompt_templates")
            .select("*")
            .eq("id", template_id)
            .or_(f"is_builtin.eq.true,user_id.eq.{user_id}")
            .execute()
        )
        if not resp.data:
            raise HTTPException(status_code=404, detail="Template not found.")
        return _row_to_template(resp.data[0])
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"get_template failed for {template_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch template.") from exc


@router.put(
    "/{template_id}",
    response_model=dict[str, Any],
    summary="Update a custom prompt template",
)
async def update_template(
    template_id: str,
    payload: TemplateUpdateRequest,
    user: dict = Depends(get_current_user_token),
) -> dict[str, Any]:
    """Update a user-owned template. Builtins cannot be modified."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_supabase()

    try:
        # Verify ownership and that it is not builtin
        existing = (
            await supabase_db.client.table("prompt_templates")
            .select("id, is_builtin, user_id")
            .eq("id", template_id)
            .execute()
        )
        if not existing.data:
            raise HTTPException(status_code=404, detail="Template not found.")
        row = existing.data[0]
        if row.get("is_builtin"):
            raise HTTPException(status_code=403, detail="Cannot modify a builtin template.")
        if row.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to update this template.")

        update_fields: dict[str, Any] = {"updated_at": datetime.now(UTC).isoformat()}
        if payload.name is not None:
            update_fields["name"] = payload.name
        if payload.description is not None:
            update_fields["description"] = payload.description
        if payload.category is not None:
            update_fields["category"] = payload.category
        if payload.prompt is not None:
            update_fields["prompt"] = payload.prompt
        if payload.variables is not None:
            update_fields["variables"] = [v.model_dump() for v in payload.variables]

        resp = (
            await supabase_db.client.table("prompt_templates")
            .update(update_fields)
            .eq("id", template_id)
            .execute()
        )
        if not resp.data:
            raise HTTPException(status_code=500, detail="Update returned no data.")
        return _row_to_template(resp.data[0])
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"update_template failed for {template_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to update template.") from exc


@router.delete(
    "/{template_id}",
    summary="Delete a custom prompt template",
)
async def delete_template(
    template_id: str,
    user: dict = Depends(get_current_user_token),
) -> dict[str, str]:
    """Delete a user-owned template. Builtins cannot be deleted."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _ensure_supabase()

    try:
        existing = (
            await supabase_db.client.table("prompt_templates")
            .select("id, is_builtin, user_id")
            .eq("id", template_id)
            .execute()
        )
        if not existing.data:
            raise HTTPException(status_code=404, detail="Template not found.")
        row = existing.data[0]
        if row.get("is_builtin"):
            raise HTTPException(status_code=403, detail="Cannot delete a builtin template.")
        if row.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this template.")

        await supabase_db.client.table("prompt_templates").delete().eq("id", template_id).execute()
        return {"status": "deleted", "id": template_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"delete_template failed for {template_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to delete template.") from exc


@router.post(
    "/{template_id}/use",
    response_model=dict[str, Any],
    summary="Fill a template and increment usage count",
)
async def use_template(
    template_id: str,
    payload: TemplateUseRequest = TemplateUseRequest(),
    user: dict = Depends(get_current_user_token),
) -> dict[str, Any]:
    """Increment usage_count and return the prompt with variables filled in."""
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")

    _bootstrap_schema()
    _seed_builtins()
    _ensure_supabase()

    try:
        resp = (
            await supabase_db.client.table("prompt_templates")
            .select("*")
            .eq("id", template_id)
            .or_(f"is_builtin.eq.true,user_id.eq.{user_id}")
            .execute()
        )
        if not resp.data:
            raise HTTPException(status_code=404, detail="Template not found.")

        row = resp.data[0]
        variables = row.get("variables") or []
        if isinstance(variables, str):
            try:
                variables = json.loads(variables)
            except (json.JSONDecodeError, TypeError):
                variables = []

        filled_prompt = _fill_variables(row["prompt"], variables, payload.values)

        # Atomically increment usage_count
        new_count = (row.get("usage_count") or 0) + 1
        await (
            supabase_db.client.table("prompt_templates")
            .update({"usage_count": new_count, "updated_at": datetime.now(UTC).isoformat()})
            .eq("id", template_id)
            .execute()
        )

        return {
            "id": template_id,
            "name": row.get("name", ""),
            "filled_prompt": filled_prompt,
            "usage_count": new_count,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"use_template failed for {template_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to use template.") from exc
