#!/usr/bin/env python3
"""
SupremeAI - OpenAPI Schema Extractor
This script extracts the OpenAPI schema from the FastAPI app and writes it to API-swagger.yaml.
"""
import os
import sys
from pathlib import Path

import yaml

# Add backend directory to path so we can import the app
if os.path.basename(os.getcwd()) == 'backend':
    sys.path.insert(0, os.getcwd())
else:
    sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))

if "ENCRYPTION_KEY" not in os.environ:
    try:
        from cryptography.fernet import Fernet
        os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode("utf-8")
    except ImportError:
        import base64
        import os as _os
        os.environ["ENCRYPTION_KEY"] = base64.urlsafe_b64encode(_os.urandom(32)).decode("utf-8")

os.environ.setdefault("DOCS_PASSWORD", "dummy")
os.environ.setdefault("SUPREMEAI_ADMIN_PASSWORD_HASH", "$2b$12$dummyhashdummyhashdummyhashdummyhashdummyhashdummyha")
os.environ.setdefault("SUPREMEAI_JWT_SECRET", "dummy_jwt_secret_for_openapi_generation_that_is_at_least_64_bytes_long_so_it_passes_validation")
os.environ.setdefault("OPENROUTER_API_KEY", "dummy")
os.environ.setdefault("SUPABASE_DATABASE_URL", "postgresql+asyncpg://mock:mock@localhost:5432/mock_db")
os.environ.setdefault("SUPABASE_DATABASE_URL_POOLER", "postgresql+asyncpg://mock:mock@localhost:5432/mock_db")
os.environ.setdefault("SUPABASE_URL", "https://mock.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "mock-key")


try:
    from main import app
except ImportError as e:
    print(f"Failed to import FastAPI app from backend.main: {e}")
    sys.exit(1)

def generate_openapi():
    openapi_schema = app.openapi()

    output_path = Path(__file__).parent.parent / "backend" / "API-swagger.yaml"
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(openapi_schema, f, sort_keys=False)

    print(f"Successfully generated OpenAPI schema at {output_path.absolute()}")

if __name__ == "__main__":
    generate_openapi()
