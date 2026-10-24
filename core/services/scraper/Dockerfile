# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

ENV PIP_ROOT_USER_ACTION=ignore
RUN pip install --no-cache-dir poetry==2.4.1

# Copy dependencies
COPY pyproject.toml poetry.lock ./

# Install dependencies in project virtualenv including browser group
RUN poetry config virtualenvs.in-project true \
    && poetry install --no-interaction --no-ansi --only main,browser --no-root

# Stage 2: Runtime — browser-ready image (Playwright + Chromium)
FROM python:3.11-slim AS runtime

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# Bengali comment (DEP-AUDIT): Chromium only lives in this image.
# Base OS utilities first (playwright's --with-deps runs its own apt-get later)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy only the virtualenv from builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Install Chromium + OS-level browser deps. MUST run AFTER the playwright
# package is copied above — otherwise the `playwright` CLI does not exist
# yet and the image build fails.
RUN playwright install --with-deps chromium

# Copy application code
COPY . .

# Create and use non-root user for security compliance
RUN addgroup --system supremeai && adduser --system supremeai --ingroup supremeai \
    && chown -R supremeai:supremeai /app

USER supremeai

# Expose port
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Start command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]