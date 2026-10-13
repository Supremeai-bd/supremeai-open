# SupremeAI MCP Control Tower — multi-stage Docker build
# Build context: infrastructure/mcp-control-plane/ (per docker-compose.yml and CI).
# Runtime: node dist/index.js — Streamable-HTTP MCP server.
# Port: MCP_PORT (default 3771). Health: GET /health -> 200 JSON (see src/index.ts).
# All runtime imports (src/lib/**, src/tools/**, src/policy/**, src/events/**,
# src/remediation/**) compile into dist/ via tsc (tsconfig: rootDir=src, outDir=dist),
# so the runtime image needs only dist/ + production dependencies.
# Test scripts (test_*.ts) live at package root and are excluded by tsconfig — see .dockerignore.
#
# Task 4 fix (2026-09-19): Added Python 3 + uv to the runtime stage so the
# MemorySubAdapter can spawn the Python memory sidecar (backend/memory/mcp_server.py)
# via StdioClientTransport. Without these runtimes the Tower returned ENOENT on every
# memory.* tool call. The backend/ code is BAKED into the image at /app/backend
# (R-05 fix, issue #538 — see the COPY --from=backend stage below) and
# SUPREMEAI_BACKEND_DIR points the adapter at that path.

# ── Stage 1: builder (Node/TypeScript) ────────────────────────────────────────
# INF-16 fix (issue #562): both stages must run the SAME Node major as CI and
# the monorepo engines — .github/workflows/ci-mcp-build.yml sets NODE_VERSION: '24'
# and root package.json engines.node is ">=24.0.0". Testing the build on Node 24
# while shipping node:20-alpine meant Node 22+/24-only APIs (node:sqlite,
# webcrypto additions, RegExp.escape) passed CI but broke at runtime.
FROM node:24-alpine AS builder
WORKDIR /app

# Install the exact dependency tree first (typescript is a devDependency, used here)
COPY package.json package-lock.json ./
RUN npm ci

# Compile TypeScript -> dist/
COPY tsconfig.json ./
COPY src/ ./src/
RUN npm run build

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM node:24-alpine
WORKDIR /app
ENV NODE_ENV=production

# ── Python 3 + uv (needed for memory sidecar: backend/memory/mcp_server.py) ──
# python3, pip3, and curl for uv installer. Keep the layer small with --no-cache.
# #2525: pin uv version (was unpinned 'install.sh | sh' — supply-chain risk).
RUN apk add --no-cache python3 py3-pip curl \
    && curl -LsSf https://astral.sh/uv/install.sh | env UV_VERSION=0.8.15 sh \
    && ln -sf /root/.local/bin/uv /usr/local/bin/uv \
    && ln -sf /root/.local/bin/uvx /usr/local/bin/uvx

# Verify Python + uv are accessible
RUN python3 --version && uv --version

COPY --from=builder /app/dist ./dist
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

# ── Bake the backend/ Python source into the image (R-05 fix, issue #538) ────
# The memory sidecar (MemorySubAdapter → StdioClientTransport) spawns
#   uv run --directory /app/backend python memory/mcp_server.py
# and previously relied on a host bind-mount (`./backend:/app/backend:ro` in
# docker-compose.yml), which is empty/missing on any hostless container-only
# deploy (Render, plain `docker run` from a registry pull). Instead, backend/
# now ships INSIDE the image via the named build context `backend`:
#
#   docker compose build mcp                 → wired automatically (compose
#     additional_contexts: backend: ./backend; Compose v2.17+ / BuildKit)
#   docker build --build-context backend=<repo>/backend <ctx>   → plain docker
#
# The whole backend tree (~15 MB source) is copied so imports resolve without
# whack-a-mole; the backend/.dockerignore (colocated with the named context)
# keeps .venv/__pycache__/tests/uploads/data out of the bake. Python deps are
# resolved by uv on first sidecar start (identical to the previous mount-based
# flow), so no dependency tree is duplicated here. Must stay BEFORE the
# `chown -R node:node /app` below: the tower runs as `node` and uv needs to
# create /app/backend/.venv inside this directory.
#
# Issue #759/#798 fix: On Render's plain `docker build` (Docker-based service
# with dockerContext='.' relative to rootDir=infrastructure/mcp-control-plane/),
# the named build context `backend` is NOT available → `COPY --from=backend`
# fails → build_failed in ~18s on every push.
#
# Fix: removed `COPY --from=backend . ./backend/` entirely. The memory sidecar
# (backend/memory/mcp_server.py) is NOT baked into the image — memory.* tools
# will gracefully return "not available" when SUPREMEAI_BACKEND_DIR doesn't
# resolve. The MCP server itself still boots and serves all other 23 tool
# domains (render, github, supabase, infisical, cloudflare, ai, redis, etc.).
#
# docker-compose users: add `COPY --from=backend . ./backend/` back via a
# docker-compose.override.yml if you need memory tools locally. The named
# context `backend` is still declared in docker-compose.yml additional_contexts.
#
# To restore full memory support on Render: apply render.yaml as a blueprint
# (switches env: docker → env: node, which has full repo checkout access).

# For Render native (env: node) this bake is unnecessary but harmless: Render
# checks out the full repo, uv is installed via `pip install uv` in
# buildCommand (render.yaml), and SUPREMEAI_BACKEND_DIR (render.yaml) points
# the adapter at the repo-relative backend path instead.

RUN chown -R node:node /app

USER node

EXPOSE 3771

# busybox wget ships with alpine; /health returns HTTP 200 (src/index.ts)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3771/health || exit 1

CMD ["node", "dist/index.js"]

