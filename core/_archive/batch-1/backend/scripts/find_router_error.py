import sys

from fastapi import FastAPI

from api import register_router
from api.routers import ALL_ROUTERS

for router_def in ALL_ROUTERS:
    path = router_def["path"]
    prefix = router_def["prefix"]
    try:
        app = FastAPI()
        register_router(app, path, prefix=prefix, optional=False)
        app.openapi()
        print(f"OK: {path}")
    except Exception as e:
        print(f"FAIL: {path} - {type(e).__name__}: {e}")
