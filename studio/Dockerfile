# Multi-stage Dockerfile for Frontend (Vite + React)
# FIX(FE-01): pin to node:24-alpine — root package.json engines requires
# node >=24.0.0 (see also .nvmrc=24). Node 20 silently skipped Node 24
# features several deps require and broke reproducibility vs CI.
FROM node:24-alpine AS builder
WORKDIR /app

# Enable corepack for pnpm if needed, or use npm
RUN corepack enable && corepack prepare pnpm@10.15.0 --activate

# Copy root and package files for monorepo / workspace dependencies
# FIX(F-2): pnpm-lock.yaml declares importers for apps/mission-control and
# tools/vscode-extension too — if their package.json files are absent the
# frozen-lockfile check can never pass. All four importer package.json files
# must exist before `pnpm install --frozen-lockfile`.
COPY package.json pnpm-lock.yaml* pnpm-workspace.yaml* ./
COPY frontend/package.json ./frontend/
COPY packages/ ./packages/
COPY apps/mission-control/package.json ./apps/mission-control/
COPY tools/vscode-extension/package.json ./tools/vscode-extension/

# Install dependencies
# FIX(F-2): no silent fallback — `|| pnpm install` re-resolved the whole tree
# on lockfile drift, defeating reproducibility. Fail loudly instead.
RUN pnpm install --frozen-lockfile

# Copy frontend source code
COPY frontend/ ./frontend/

# Build frontend
WORKDIR /app/frontend
# FIX(localhost-bake): default to relative API paths. Vite bakes VITE_* into
# the bundle at build time; the old http://localhost:8080 default only worked
# when the browser ran on the docker host. The nginx runtime image proxies
# /api, /admin-api, /auth and /ws to backend:8080, so relative paths work
# from every host. VITE_USE_RELATIVE_PATH=true makes getApiBaseUrl() return
# '' (see frontend/src/utils/api.ts).
ARG VITE_API_URL=""
ARG VITE_USE_RELATIVE_PATH=true
ENV VITE_API_URL=$VITE_API_URL \
    VITE_BACKEND_URL=$VITE_API_URL \
    VITE_USER_BACKEND=$VITE_API_URL \
    VITE_ADMIN_BACKEND=$VITE_API_URL \
    VITE_USE_RELATIVE_PATH=$VITE_USE_RELATIVE_PATH \
    NODE_ENV=production

RUN pnpm run build

# Stage 2: Serve with lightweight Nginx
FROM nginx:1.27-alpine AS runtime
COPY --from=builder /app/frontend/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Setup non-root execution permissions for nginx user
RUN chown -R nginx:nginx /usr/share/nginx/html \
    && chmod -R 755 /usr/share/nginx/html \
    && chown -R nginx:nginx /var/cache/nginx \
    && chown -R nginx:nginx /var/log/nginx \
    && chown -R nginx:nginx /etc/nginx/conf.d \
    && touch /var/run/nginx.pid \
    && chown -R nginx:nginx /var/run/nginx.pid

USER nginx

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]

