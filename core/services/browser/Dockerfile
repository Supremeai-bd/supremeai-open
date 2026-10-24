# STATUS NOTE (audit F-9): currently ORPHANED — no compose file, workflow or doc
# references this Dockerfile. Verify intent before use; see production audit F-9.
FROM python:3.12-slim
WORKDIR /app

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium --with-deps

COPY . .

# Create non-root user and grant permissions to app and playwright binaries (Trap #97)
RUN addgroup --system pwuser && adduser --system pwuser --ingroup pwuser && \
    mkdir -p /ms-playwright && \
    chown -R pwuser:pwuser /app /ms-playwright && \
    chmod -R 755 /ms-playwright

USER pwuser

CMD ["python", "main.py"]
