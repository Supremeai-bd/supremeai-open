# Root Dockerfile — delegates to infrastructure/mcp-control-plane/Dockerfile
#
# Issue #759/#798/#598: the live Render MCP service (srv-dabm7inqj5pc738jkrt0)
# has dockerContext="." and dockerfilePath="Dockerfile" (set when the service
# was originally created). It cannot find a Dockerfile at the repo root →
# build_failed in ~18s on every push.
#
# The canonical MCP image lives at infrastructure/mcp-control-plane/Dockerfile
# (see docker-compose.yml service "mcp" with context: ./infrastructure/mcp-control-plane).
# The durable fix is to apply render.yaml (env: node, rootDir:
# infrastructure/mcp-control-plane) as a blueprint so the live service switches
# from Docker→Node runtime — but that requires a manual Render dashboard action
# (the API doesn't let you change runtime/dockerContext after creation).
#
# This root Dockerfile is a zero-disruption bridge: it builds the MCP image
# using the SAME multi-stage Dockerfile that docker-compose uses, so the live
# Docker-based Render service starts succeeding immediately. Once the blueprint
# is applied (switching to env: node), this file becomes harmless dead weight
# and can be deleted.
#
# Build: `docker build -t supremeai/mcp .` (from repo root)
# The -f flag is NOT needed — Render looks for ./Dockerfile at the context root.

# ── Stage 1: builder (Node/TypeScript) ────────────────────────────────────────
# INF-16 fix (issue #562): both stages must run the SAME Node major as CI and
# the monorepo engines — .github/workflows/ci-mcp-build.yml sets NODE_VERSION: '24'
# and root package.json engines.node is ">=24.0.0". Testing the build on Node 24
# while shipping node:20-alpine meant Node 22+/24-only APIs (node:sqlite,
# webcrypto additions, RegExp.escape) passed CI but broke at runtime.
FROM node:24-alpine AS builder
WORKDIR /app

# Install the exact dependency tree first (typescript is a devDependency, used here)
COPY infrastructure/mcp-control-plane/package.json infrastructure/mcp-control-plane/package-lock.json ./
RUN npm ci

# Compile TypeScript -> dist/
COPY infrastructure/mcp-control-plane/tsconfig.json ./
COPY infrastructure/mcp-control-plane/src/ ./src/
RUN npm run build

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM node:24-alpine
WORKDIR /app
ENV NODE_ENV=production

# ── Python 3 + uv (needed for memory sidecar: backend/memory/mcp_server.py) ──
# Task 4 fix (2026-09-19): the MemorySubAdapter spawns the Python memory sidecar
# via StdioClientTransport; without python3 + uv in the runtime image, every
# memory.* tool call returns ENOENT.
RUN apk add --no-cache python3 py3-pip curl \
    && python3 -m ensurepip --upgrade \
    && pip3 install --no-cache-dir --break-system-packages uv

# Copy compiled dist/ + production deps from builder
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY infrastructure/mcp-control-plane/package.json ./
# Vendored Infisical bootstrap script (scripts/runtime/infisical_bootstrap.py)
# is used by the startCommand in render.yaml.
COPY infrastructure/mcp-control-plane/scripts ./scripts

# ── R-05 fix (issue #538): bake backend/ source into the image ──────────────
# The MemorySubAdapter spawns `uv run --directory /app/backend python
# memory/mcp_server.py` at runtime. On hostless deploys (Render registry pull,
# plain `docker run`) there is no repo checkout, so backend/ must be in the
# image. SUPREMEAI_BACKEND_DIR env var points the adapter at /app/backend.
COPY backend/ /app/backend

# Non-root user compliance (Trap #97)
RUN chown -R node:node /app

USER node

# Healthcheck: the MCP server listens on MCP_PORT (default 3771) and responds
# to GET /health with 200 JSON.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=15s \
    CMD curl -f http://localhost:${MCP_PORT:-3771}/health || exit 1

# Start the MCP server (Streamable-HTTP on port 3771).
# render.yaml's startCommand wraps this with the Infisical bootstrap:
#   python scripts/runtime/infisical_bootstrap.py npm run start
# For the Docker-based live service, the Dockerfile CMD runs directly.
CMD ["node", "dist/index.js"]
