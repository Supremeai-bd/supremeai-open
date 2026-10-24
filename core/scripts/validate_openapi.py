#!/usr/bin/env python3
import json
import os
import sys

# Add the parent directory to sys.path so we can import 'main' and 'core'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Ensure OPENAPI_GENERATION mode is active so that DB/Redis connections are skipped
os.environ["OPENAPI_GENERATION"] = "true"

try:
    from fastapi.openapi.utils import get_openapi

    from main import app
except ImportError as e:
    print(f"Failed to import app: {e}")
    sys.exit(1)


def validate_openapi():
    try:
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            description=app.description,
            routes=app.routes,
        )

        schema_json = json.dumps(openapi_schema, indent=2)
        if not schema_json or len(schema_json) < 100:
            print("Generated OpenAPI schema seems suspiciously small.")
            sys.exit(1)

        print("[OK] OpenAPI schema generated and validated successfully.")

        # Optionally write it to a file
        schema_path = os.path.join(os.path.dirname(__file__), "..", "openapi.json")
        with open(schema_path, "w", encoding="utf-8") as f:
            f.write(schema_json)
        print(f"Schema written to {schema_path}")

    except Exception as e:
        print(f"[ERROR] Failed to generate OpenAPI schema: {e}")
        sys.exit(1)


if __name__ == "__main__":
    validate_openapi()
