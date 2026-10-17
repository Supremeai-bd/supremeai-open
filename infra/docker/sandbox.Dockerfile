# SupremeAI Hardened Agent Execution Sandbox
# Hardened non-root container for isolated PR and bridge patch test runs.

FROM python:3.11-slim

# Security: Install minimal runtime dependencies and drop package manager cache
RUN apt-get update && \
    apt-get install -y --no-install-recommends git curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Create non-root unprivileged execution user and group
RUN groupadd -g 10001 sandboxgroup && \
    useradd -u 10001 -g sandboxgroup -m -s /bin/bash sandboxuser

# Create workspace and temp directory with strict ownership
WORKDIR /workspace
RUN chown -R sandboxuser:sandboxgroup /workspace && \
    chmod 755 /workspace

# Switch to non-root user
USER sandboxuser:sandboxgroup

# Environment isolation
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUSERBASE=/tmp/.local \
    TMPDIR=/tmp \
    HOME=/home/sandboxuser

# Default entrypoint runs tests in read-only environment
ENTRYPOINT ["python3", "-m", "unittest"]
