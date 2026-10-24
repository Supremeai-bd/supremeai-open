FROM mcr.microsoft.com/devcontainers/python:3.11

# Install native database clients and build dependencies
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
        redis-tools \
        postgresql-client \
        libpq-dev \
        build-essential \
        curl \
        git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install pinned global Python tooling matching CI invariants
RUN pip install --no-cache-dir --upgrade pip==24.0 \
    && pip install --no-cache-dir poetry==2.4.1 ruff==0.16.4 pytest==8.2.2
