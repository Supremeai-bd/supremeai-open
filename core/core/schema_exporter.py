import json
import os
import sys

from core.logging_config import logger


def export_openapi_schema(output_path: str = "packages/shared-types/openapi.json") -> str:
    """
    FastAPI অ্যাপ থেকে OpenAPI JSON স্কিমা এক্সপোর্ট করা।
    """
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
    from main import app

    schema = app.openapi()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)

    logger.info(f"[SchemaExporter] Exported OpenAPI schema to '{output_path}'")
    return output_path


if __name__ == "__main__":
    export_openapi_schema()
