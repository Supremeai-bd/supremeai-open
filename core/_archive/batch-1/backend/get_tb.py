import sys
import traceback

try:
    from api.main import app
    from fastapi.testclient import TestClient

    TestClient(app)
except Exception:
    with open("traceback.txt", "w") as f:
        traceback.print_exc(file=f)
