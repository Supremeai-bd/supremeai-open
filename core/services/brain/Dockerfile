# SupremeAI Tiny Brain (core/services/brain) — 512MB micro-service image.
# Render service config: rootDir=core/services/brain, dockerfilePath=./Dockerfile
# ROOT-CAUSE FIX (render-brain build_failed 2026-11-01): the Render service
# builds from this directory but no Dockerfile existed here, so every
# autodeploy failed with "failed to read dockerfile: open Dockerfile: no
# such file or directory". This file restores the build contract.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Runtime deps only. Kept inline (no requirements.txt in this module yet)
# and unpinned-major so the build survives free-tier cache windows.
RUN pip install --no-cache-dir "fastapi>=0.115,<1" "uvicorn>=0.30,<1" "pydantic>=2,<3"

COPY main.py ./

EXPOSE 8000

# Render injects $PORT; local runs default to 8000.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
