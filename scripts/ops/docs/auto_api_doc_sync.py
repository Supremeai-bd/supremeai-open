#!/usr/bin/env python
"""
auto_api_doc_sync.py
====================
Automatically synchronizes FastAPI OpenAPI specification to documentation.

Fetches the OpenAPI JSON from the running SupremeAI API and converts it to
readable Markdown documentation.

SCRIPT-INTELLIGENCE v9: auto-discovers targets via scripts/lib/auto_discovery.py — no hardcoded file inventories.

Doc-target discovery (first existing candidate wins, in order):
  docs/api_reference.md  ->  docs/API_REFERENCE.md  ->  API_REFERENCE.md  ->  docs/api.md
If none exist, the doc is CREATED at the first candidate inside docs/
(docs/ root resolved via get_layout().docs) instead of a stale hardcoded path.

Environment Variables / CLI:
- SUPREMEAI_API_URL: Base URL of the SupremeAI API (default: http://localhost:8000)  # is_local()
- OPENAPI_ENDPOINT: OpenAPI JSON endpoint (default: /openapi.json)
- OUTPUT_DIR: Directory to write markdown files (default: the DISCOVERED doc
  target's parent directory; explicit pin keeps the legacy behavior)
- UPDATE_README: Whether to update the main README with API overview (default: true)
- --api-url / --output-dir / --no-readme: CLI equivalents of the env vars
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import requests

# SCRIPT-INTELLIGENCE v9: make the shared discovery lib importable from any cwd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from lib.auto_discovery import existing_paths, get_layout  # noqa: E402

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration (env defaults kept for backward compatibility; CLI flags override)
API_URL = os.getenv("SUPREMEAI_API_URL", "http://localhost:8000")  # is_local()
OPENAPI_ENDPOINT = os.getenv("OPENAPI_ENDPOINT", "/openapi.json")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "docs/06-api")
UPDATE_README = os.getenv("UPDATE_README", "true").lower() == "true"

# SCRIPT-INTELLIGENCE v9: candidate API doc targets, tried in order.
DOC_CANDIDATES = (
    "docs/api_reference.md",
    "docs/API_REFERENCE.md",
    "API_REFERENCE.md",
    "docs/api.md",
)


def resolve_api_doc_target() -> Path:
    """Discover the API doc target: first existing candidate, else create-at path.

    বাংলা মন্তব্য: কোনো হার্ডকোডেড স্টেল পাথ নেই — existing_candidates থেকে
    টার্গেট বেছে নেওয়া হয়; কিছু না পাওয়া গেলে docs/ এর ভেতরে প্রথম ক্যান্ডিডেটে
    নতুন ফাইল তৈরি হবে।
    """
    layout = get_layout()
    found = existing_paths(DOC_CANDIDATES, relative_to=layout.root)
    if found:
        target = found[0]
        skipped = [layout.rel(p) for p in found[1:]]
        logger.info("[discovery] existing API doc target: %s", layout.rel(target))
        if skipped:
            logger.info("[discovery] other existing candidates (unused): %s", ", ".join(skipped))
        return target
    base = layout.docs if layout.docs is not None else layout.root
    target = base / "api_reference.md"
    logger.info(
        "[discovery] no existing API doc found among %s; will create at %s",
        ", ".join(DOC_CANDIDATES), layout.rel(target),
    )
    return target


def fetch_openapi_spec(api_url: str | None = None, endpoint: str | None = None) -> dict[str, Any]:
    """Fetch OpenAPI specification from the API."""
    url = f"{(api_url or API_URL).rstrip('/')}{endpoint or OPENAPI_ENDPOINT}"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch OpenAPI spec from {url}: {e}")
        raise

def format_parameters(parameters: list[dict]) -> str:
    """Format OpenAPI parameters into Markdown."""
    if not parameters:
        return ""

    md = "| Name | Location | Type | Required | Description |\n"
    md += "|------|----------|------|----------|-------------|\n"

    for param in parameters:
        name = param.get("name", "")
        location = param.get("in", "")
        schema = param.get("schema", {})
        param_type = schema.get("type", "string")
        required = "Yes" if param.get("required", False) else "No"
        description = param.get("description", "").replace("|", "\\|").replace("\n", " ")

        md += f"| {name} | {location} | {param_type} | {required} | {description} |\n"

    return md

def format_request_body(content: dict) -> str:
    """Format OpenAPI request body into Markdown."""
    if not content:
        return ""

    # Handle JSON content primarily
    if "application/json" in content:
        schema = content["application/json"].get("schema", {})
        if schema:
            return f"```json\n{json.dumps(schema, indent=2)}\n```"

    return "_Request body content_"

def format_responses(responses: dict) -> str:
    """Format OpenAPI responses into Markdown."""
    if not responses:
        return "_No documented responses_"

    md = ""
    for status_code, response in responses.items():
        description = response.get("description", "")
        content = response.get("content", {})

        md += f"### {status_code}\n\n"
        md += f"{description}\n\n"

        if content:
            media_type = next(iter(content.keys()))  # Take first media type
            schema = content[media_type].get("schema", {})
            if schema:
                md += f"**{media_type}**:\n\n"
                md += f"```json\n{json.dumps(schema, indent=2)}\n```\n\n"

    return md

def generate_api_markdown(spec: dict[str, Any]) -> str:
    """Generate Markdown documentation from OpenAPI spec."""
    info = spec.get("info", {})
    title = info.get("title", "SupremeAI API")
    version = info.get("version", "1.0.0")
    description = info.get("description", "")

    md = f"# {title} v{version}\n\n"
    md += f"{description}\n\n"
    md += "*Generated automatically from OpenAPI specification*\n\n"
    md += "---\n\n"

    paths = spec.get("paths", {})
    if not paths:
        return md + "_No API paths documented._\n"

    # Group by tags for better organization
    tagged_paths = {}

    for path, path_item in paths.items():
        # Get tags from all operations in this path
        tags = set()
        for method, operation in path_item.items():
            if method in ["get", "post", "put", "delete", "patch", "options", "head"]:
                operation_tags = operation.get("tags", [])
                tags.update(operation_tags)

        # If no tags, put in "General" category
        if not tags:
            tags = {"General"}

        for tag in tags:
            if tag not in tagged_paths:
                tagged_paths[tag] = []
            tagged_paths[tag].append((path, path_item))

    # Sort tags alphabetically
    sorted_tags = sorted(tagged_paths.keys())

    for tag in sorted_tags:
        md += f"## {tag}\n\n"

        # Sort paths alphabetically within each tag
        tag_paths = sorted(tagged_paths[tag], key=lambda x: x[0])

        for path, path_item in tag_paths:
            md += f"### {path}\n\n"

            # Process each HTTP method
            for method in ["get", "post", "put", "delete", "patch", "options", "head"]:
                if method not in path_item:
                    continue

                operation = path_item[method]
                operation.get("operationId", f"{method.upper()} {path}")
                summary = operation.get("summary", "")
                description = operation.get("description", "")

                md += f"#### {method.upper()} {path}\n\n"
                if summary:
                    md += f"**{summary}**\n\n"
                if description:
                    md += f"{description}\n\n"

                # Parameters
                parameters = operation.get("parameters", [])
                if parameters:
                    md += "**Parameters**\n\n"
                    md += format_parameters(parameters)
                    md += "\n"

                # Request Body
                request_body = operation.get("requestBody")
                if request_body:
                    md += "**Request Body**\n\n"
                    content = request_body.get("content", {})
                    md += format_request_body(content)
                    md += "\n\n"

                # Responses
                responses = operation.get("responses", {})
                if responses:
                    md += "**Responses**\n\n"
                    md += format_responses(responses)
                    md += "\n"

                md += "---\n\n"

    return md

def update_main_readme(api_md: str, readme_path: Path | None = None) -> None:
    """Update the main README.md with API documentation section."""
    if readme_path is None:
        # SCRIPT-INTELLIGENCE v9: anchor at the discovered repo root, not cwd
        layout = get_layout()
        readme_path = layout.root / "README.md"
    if not readme_path.exists():
        logger.warning("README.md not found at %s, skipping update", readme_path)
        return

    try:
        content = readme_path.read_text(encoding="utf-8")

        # Look for API section markers
        start_marker = "<!-- API DOCS START -->"
        end_marker = "<!-- API DOCS END -->"

        if start_marker in content and end_marker in content:
            # Replace existing API section
            parts = content.split(start_marker)
            before = parts[0]
            after = parts[1].split(end_marker, 1)[1] if len(parts) > 1 else ""

            new_content = f"{before}{start_marker}\n\n{api_md}\n{end_marker}{after}"
            readme_path.write_text(new_content, encoding="utf-8")
            logger.info("Updated README.md with API documentation")
        else:
            # Append API section to end
            new_content = f"{content}\n\n<!-- API DOCS START -->\n\n{api_md}\n\n<!-- API DOCS END -->\n"
            readme_path.write_text(new_content, encoding="utf-8")
            logger.info("Added API documentation to README.md")

    except Exception as e:
        logger.error(f"Failed to update README.md: {e}")

def main(argv: list[str] | None = None) -> int:
    """Main function to synchronize API documentation."""
    parser = argparse.ArgumentParser(
        prog="auto_api_doc_sync.py",
        description="Sync the FastAPI OpenAPI spec into the discovered API doc (SCRIPT-INTELLIGENCE v9)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Doc-target discovery (first existing wins):
  docs/api_reference.md -> docs/API_REFERENCE.md -> API_REFERENCE.md -> docs/api.md
If none exist, the doc is created at docs/api_reference.md (docs/ via get_layout().docs).

Env overrides:
  SUPREMEAI_API_URL   API base URL (default: http://localhost:8000)
  OPENAPI_ENDPOINT    OpenAPI JSON path (default: /openapi.json)
  OUTPUT_DIR          explicit output dir pin (default: discovered target's parent)
  UPDATE_README       update README.md section (default: true)
""")
    parser.add_argument("--api-url", default=None, help="Override SUPREMEAI_API_URL")
    parser.add_argument(
        "--output-dir", default=None,
        help="Override OUTPUT_DIR (default: parent of the discovered doc target)",
    )
    parser.add_argument("--no-readme", action="store_true", help="Skip README.md update")
    args = parser.parse_args(argv)

    api_url = args.api_url or API_URL
    update_readme = UPDATE_README and not args.no_readme

    # SCRIPT-INTELLIGENCE v9: discover the doc target instead of a stale path
    doc_target = resolve_api_doc_target()
    output_dir = Path(args.output_dir or OUTPUT_DIR) if (args.output_dir or os.getenv("OUTPUT_DIR")) else doc_target.parent

    print("🔄 Starting API documentation synchronization...")
    print(f"📡 Fetching OpenAPI spec from: {api_url}{OPENAPI_ENDPOINT}")
    print(f"📁 Output directory: {output_dir}")
    print(f"🎯 Discovered doc target: {doc_target}")

    try:
        # Fetch OpenAPI specification
        spec = fetch_openapi_spec(api_url=api_url)
        print("✅ Successfully fetched OpenAPI specification")

        # Generate Markdown documentation
        api_markdown = generate_api_markdown(spec)

        # Ensure output directory exists
        output_path = output_dir
        output_path.mkdir(parents=True, exist_ok=True)

        # Write API documentation file (discovered target name)
        api_file = output_path / doc_target.name
        api_file.write_text(api_markdown, encoding="utf-8")
        print(f"✅ API documentation written to: {api_file}")

        # Optionally update main README
        if update_readme:
            update_main_readme(api_markdown)

        print("🎉 API documentation synchronization completed successfully!")

    except Exception as e:
        print(f"❌ Failed to synchronize API documentation: {e}")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
