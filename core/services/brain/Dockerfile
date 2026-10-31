# Ultra-lightweight Dockerfile optimized for Render 512MB RAM tier
FROM python:3.12.16-slim-bookworm

WORKDIR /app

# Install minimal dependencies without caching bloat
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY main.py .

EXPOSE 8000

# Run with single worker to keep memory consumption under 80MB
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-level", "info"]
