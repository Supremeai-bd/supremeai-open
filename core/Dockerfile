# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install poetry (Pip root warning suppressed as builder is isolated)
ENV PIP_ROOT_USER_ACTION=ignore
RUN pip install --no-cache-dir poetry==2.4.1

# Copy dependencies
COPY pyproject.toml poetry.lock ./

# Install dependencies in project virtualenv
RUN poetry config virtualenvs.in-project true \
    && poetry install --no-interaction --no-ansi --only main --no-root

# Stage 2: Runtime
FROM python:3.11-slim AS runtime

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# Create non-root user for security compliance & update perl-base
RUN apt-get update && apt-get install -y --only-upgrade perl-base && rm -rf /var/lib/apt/lists/* \
    && addgroup --system supremeai && adduser --system supremeai --ingroup supremeai

# Copy only the virtualenv from builder with correct ownership
COPY --from=builder --chown=supremeai:supremeai /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code with non-root ownership
COPY --chown=supremeai:supremeai . .

# Ensure data directory exists with non-root ownership
RUN mkdir -p /app/data /app/uploads /app/logs /app/tmp && chown -R supremeai:supremeai /app/data /app/uploads /app/logs /app/tmp

USER supremeai

# Expose port
EXPOSE 8080

# Container liveness probe. Keep this aligned with the FastAPI route and Render's health path.
# The app exposes /health/live (not /api/v1/health/live); a wrong path marks a healthy
# container as unhealthy and can cause Render to roll back the deployment.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=5 \
  CMD python -c "import os, urllib.request; p=os.getenv('PORT','8080'); urllib.request.urlopen(f'http://127.0.0.1:{p}/health/live', timeout=4)" || exit 1

# Start command
CMD ["python", "main.py"]

