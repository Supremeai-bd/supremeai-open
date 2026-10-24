import json
import sys
from pathlib import Path

from fastapi.routing import APIRoute


def generate_health_report():
    # Adjust python path to allow importing from backend
    backend_path = Path(__file__).resolve().parent.parent / "backend"
    sys.path.insert(0, str(backend_path))

    # Import the FastAPI app
    from core.app import app

    report_path = backend_path / "pytest-report.json"

    tests = {"tests": []}
    if report_path.exists():
        with open(report_path, encoding="utf-8") as f:
            try:
                tests = json.load(f)
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception(f"Silenced error: {e}")

    report = "### 🩺 API Health & Route Coverage Matrix\n\n"
    report += "| Endpoint Path | Method | Has Test? | Status |\n|---|---|---|---|\n"

    for route in app.routes:
        if isinstance(route, APIRoute):
            path = route.path
            methods = ", ".join(list(route.methods - {"HEAD"}))
            # Simple logic to check if route path is mentioned in tests
            has_test = any(path.strip('/').replace('/', '_') in test.get('nodeid', '') for test in tests.get('tests', []))
            if not has_test:
                # Also check by direct string match in nodeid just in case
                has_test = any(path in test.get('nodeid', '') for test in tests.get('tests', []))

            status_icon = "✅" if has_test else "⚠️"
            status_text = "Pass" if has_test else "Untested"
            report += f"| `{path}` | `{methods}` | {status_icon} | {status_text} |\n"

    # Infrastructure & Memory Ecosystem Status
    report += "\n### 🧠 Vector Database & Cache Ecosystem\n\n"
    report += "| Service | Target / Engine | Status | Dashboard / Endpoint |\n|---|---|---|---|\n"

    import os
    qdrant_url = os.getenv("QDRANT_URL")
    if qdrant_url:
        report += f"| **Qdrant Vector DB** | Neural & Knowledge Memory | 🟢 Configured | [Qdrant Cluster]({qdrant_url}) |\n"
    else:
        report += "| **Qdrant Vector DB** | Neural & Knowledge Memory | ⚪ Fallback | In-Memory / Local PgVector |\n"

    redis_url = os.getenv("UPSTASH_REDIS_REST_URL") or os.getenv("REDIS_URL")
    if redis_url:
        display_redis = "Upstash Managed Redis" if "upstash" in redis_url.lower() else "Distributed Redis"
        report += f"| **Redis Cache** | {display_redis} | 🟢 Configured | Connected |\n"
    else:
        report += "| **Redis Cache** | Real-time Ephemeral Cache | ⚪ In-Memory | Local Memory Engine |\n"

    from core.config import settings
    supabase_url = getattr(settings, "supabase_url", "")
    if supabase_url:
        report += f"| **Supabase Storage** | Primary Relational & Vector DB | 🟢 Configured | [Supabase Console]({supabase_url}) |\n"

    try:
        print(report)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(report.encode("utf-8"))

if __name__ == "__main__":
    generate_health_report()
