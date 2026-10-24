#!/usr/bin/env python
"""
auto_readme_update.py
=====================
Automatically updates README.md with API endpoint tables when new routers are added.

Scans the backend/api/routes/ directory for Python files and generates a markdown
table of API endpoints for inclusion in README.md.

Environment Variables:
- ROUTES_DIR: Directory containing route modules (default: backend/api/routes)
- README_PATH: Path to README.md file (default: README.md)
- API_TABLE_MARKER_START: Start marker for API table in README (default: <!-- API ENDPOINTS START -->)
- API_TABLE_MARKER_END: End marker for API table in README (default: <!-- API ENDPOINTS END -->)
"""

import ast
import logging
import os
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
ROUTES_DIR = os.getenv("ROUTES_DIR", "backend/api/routes")
README_PATH = os.getenv("README_PATH", "README.md")
API_TABLE_MARKER_START = os.getenv("API_TABLE_MARKER_START", "<!-- API ENDPOINTS START -->")
API_TABLE_MARKER_END = os.getenv("API_TABLE_MARKER_END", "<!-- API ENDPOINTS END -->")

def extract_route_info_from_file(file_path: Path) -> list[dict[str, str]]:
    """
    Extract route information from a Python file using AST parsing.

    Returns list of dictionaries with keys: method, path, function_name, description
    """
    routes = []

    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
    except (SyntaxError, UnicodeDecodeError) as e:
        logger.warning(f"Could not parse {file_path}: {e}")
        return routes

    # Walk through the AST to find FastAPI route decorators
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Check for decorators on the function
            for decorator in node.decorator_list:
                # Look for @app.get, @app.post, etc. or @router.get, @router.post, etc.
                if isinstance(decorator, ast.Call):
                    if isinstance(decorator.func, ast.Attribute):
                        method_name = decorator.func.attr.lower()
                        if method_name in ['get', 'post', 'put', 'delete', 'patch', 'options', 'head']:
                            # Get the path (first argument)
                            path = ""
                            if decorator.args:
                                if isinstance(decorator.args[0], ast.Constant):
                                    path = decorator.args[0].value
                                elif isinstance(decorator.args[0], ast.Str):  # Python < 3.8
                                    path = decorator.args[0].s

                            # Get function name and docstring
                            func_name = node.name
                            docstring = ast.get_docstring(node) or ""

                            # Clean up docstring for display (first line only)
                            description = docstring.split('\n')[0] if docstring else "No description"

                            routes.append({
                                "method": method_name.upper(),
                                "path": path,
                                "function": func_name,
                                "description": description
                            })
                # Also handle direct attribute access like @app.get (without call)
                elif isinstance(decorator, ast.Attribute):
                    method_name = decorator.attr.lower()
                    if method_name in ['get', 'post', 'put', 'delete', 'patch', 'options', 'head']:
                        # This is less common but handle it
                        func_name = node.name
                        docstring = ast.get_docstring(node) or ""
                        description = docstring.split('\n')[0] if docstring else "No description"

                        routes.append({
                            "method": method_name.upper(),
                            "path": "/",  # Default path when not specified in decorator
                            "function": func_name,
                            "description": description
                        })

    return routes

def generate_api_table() -> str:
    """Generate markdown table of all API routes."""
    routes_dir = Path(ROUTES_DIR)
    if not routes_dir.exists():
        logger.warning(f"Routes directory not found: {ROUTES_DIR}")
        return "_No routes found_"

    all_routes = []

    # Scan all Python files in the routes directory
    for py_file in routes_dir.glob("*.py"):
        if py_file.name.startswith("__"):
            continue  # Skip __init__.py and similar

        routes = extract_route_info_from_file(py_file)
        if routes:
            # Add module name for context
            for route in routes:
                route["module"] = py_file.stem
            all_routes.extend(routes)

    if not all_routes:
        return "_No API routes found_"

    # Sort by method, then path
    all_routes.sort(key=lambda x: (x["method"], x["path"]))

    # Generate markdown table
    md = "| Method | Path | Module | Function | Description |\n"
    md = "|--------|------|--------|----------|-------------|\n"

    for route in all_routes:
        method = route["method"]
        path = route["path"]
        module = route["module"]
        function = route["function"]
        description = route["description"].replace("|", "\\|")  # Escape pipe characters

        md += f"| {method} | `{path}` | {module} | {function} | {description} |\n"

    return md

def update_readme(api_table: str) -> bool:
    """Update README.md with the API table."""
    readme_path = Path(README_PATH)
    if not readme_path.exists():
        logger.error(f"README file not found: {README_PATH}")
        return False

    try:
        content = readme_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Could not read {README_PATH}: {e}")
        return False

    # Check if markers exist
    if API_TABLE_MARKER_START not in content or API_TABLE_MARKER_END not in content:
        logger.warning(f"API table markers not found in {README_PATH}")
        logger.info(f"Looking for: {API_TABLE_MARKER_START} ... {API_TABLE_MARKER_END}")

        # Optionally, append to end of file
        new_content = f"{content}\n\n## API Endpoints\n\n{API_TABLE_MARKER_START}\n\n{api_table}\n\n{API_TABLE_MARKER_END}\n"
        try:
            readme_path.write_text(new_content, encoding="utf-8")
            logger.info(f"Added API table to end of {README_PATH}")
            return True
        except Exception as e:
            logger.error(f"Could not write to {README_PATH}: {e}")
            return False

    # Replace content between markers
    try:
        parts = content.split(API_TABLE_MARKER_START)
        if len(parts) < 2:
            logger.error("Could not split content by start marker")
            return False

        before = parts[0]
        after_parts = parts[1].split(API_TABLE_MARKER_END, 1)
        if len(after_parts) < 2:
            logger.error("Could not split content by end marker")
            return False

        after = after_parts[1]

        new_content = f"{before}{API_TABLE_MARKER_START}\n\n{api_table}\n\n{API_TABLE_MARKER_END}{after}"

        readme_path.write_text(new_content, encoding="utf-8")
        logger.info(f"Updated API table in {README_PATH}")
        return True

    except Exception as e:
        logger.error(f"Error updating README: {e}")
        return False

def main() -> int:
    """Main function to update README with API table."""
    print("📖 Starting README API table update...")
    print(f"📁 Scanning routes in: {ROUTES_DIR}")
    print(f"📄 Updating README: {README_PATH}")

    try:
        # Generate the API table
        api_table = generate_api_table()
        print(f"📊 Generated table with {len(api_table.split('|')[3:-2]) if '|' in api_table else 0} routes")

        # Update the README
        if update_readme(api_table):
            print("✅ README updated successfully")
            return 0
        else:
            print("❌ Failed to update README")
            return 1

    except Exception as e:
        print(f"❌ Error during README update: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
