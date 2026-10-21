# SupremeAI Browser - headless Gemini web relay (Playwright + Chromium)
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

# Install Python deps
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[runtime]" fastapi uvicorn[standard] httpx

# Copy source
COPY . .

ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Persisted browser profile (mount a Render disk at /data/profile)
ENV GEMINI_PROFILE_DIR=/data/profile
ENV PORT=8000

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]

