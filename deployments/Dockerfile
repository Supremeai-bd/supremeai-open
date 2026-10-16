# SupremeAI API gateway image (issue #339 AC2 — reference Dockerfile).
#
# Integrity invariants (enforced by tests/test_infra_integrity.py):
#   - runs as a NON-ROOT user (no bare `USER root`, explicit UID user)
#   - HEALTHCHECK present and pointing at the credential-free /healthz probe
#   - no dot-env files, no credential files, no .git copied into the image
#   - pinned base image (digest-or-version tag, never `latest`)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first (layer cache), source second.
COPY gateway/requirements.txt /app/gateway/requirements.txt
RUN pip install --no-cache-dir -r /app/gateway/requirements.txt

COPY gateway/ /app/gateway/

# Non-root runtime user (no shell needed by the app).
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin gateway
USER 10001

EXPOSE 8080

# Fail-closed container health: /healthz is the credential-free probe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; \
r=urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4); \
sys.exit(0 if r.status==200 else 1)" || exit 1

CMD ["uvicorn", "gateway.serve:app", "--host", "0.0.0.0", "--port", "8080"]
