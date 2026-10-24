#!/usr/bin/env python
"""
auto_migrate.py
===============
Automatic database migration runner for SupremeAI 2.0.

Runs Alembic migrations to bring the database schema up to date.
Can be used at startup or as part of a CI/CD pipeline.
"""

import os
import subprocess
import sys
from pathlib import Path


def run_migrations() -> None:
    """Run Alembic migrations to upgrade the database to the latest head."""
    # Get the directory where this script is located
    script_dir = Path(__file__).parent.parent.parent  # Go up to project root
    backend_dir = script_dir / "backend"

    # Change to the backend directory where alembic.ini is located
    os.chdir(backend_dir)

    # Check if alembic.ini exists
    if not (backend_dir / "alembic.ini").exists():
        print("Error: alembic.ini not found in backend directory")
        sys.exit(1)

    # Run the migration command
    try:
        print("Running database migrations...")
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            check=True,
            capture_output=True,
            text=True
        )
        print("Migration output:")
        print(result.stdout)
        if result.stderr:
            print("Warnings/Errors:")
            print(result.stderr)
        print("✅ Database migrations completed successfully")
    except subprocess.CalledProcessError as e:
        print(f"❌ Migration failed with exit code {e.returncode}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        raise RuntimeError(f"Database migration failed with exit code {e.returncode}") from e
    except FileNotFoundError as fnf:
        print("❌ Error: 'alembic' command not found. Is Alembic installed?")
        raise RuntimeError("Alembic command not found in environment") from fnf

if __name__ == "__main__":
    run_migrations()
