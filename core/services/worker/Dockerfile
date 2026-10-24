# STATUS NOTE (audit F-9): currently ORPHANED — no compose file, workflow or doc
# references this Dockerfile. Verify intent before use; see production audit F-9.
# Issue #514 (BE-08): pin 3.11 to match backend/pyproject.toml (`python = "^3.11"`)
# and the backend/scraper Dockerfiles — avoids behavioral drift across Python
# minor versions between worker and API images.
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Create and switch to non-root user for security compliance (Trap #97)
RUN addgroup --system supremeai && adduser --system supremeai --ingroup supremeai && \
    chown -R supremeai:supremeai /app
USER supremeai

CMD ["python", "main.py"]
