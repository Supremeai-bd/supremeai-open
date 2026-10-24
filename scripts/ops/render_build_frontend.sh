#!/usr/bin/env bash
# Smart Build Script for SupremeAI Frontend (Self-Healing + Dynamic Config)
# 🔧 ADDED: Build-time placeholder replacement for firebase.json

echo "==========================================="
echo "🚀 Starting Smart Build for Frontend..."
echo "==========================================="

echo "📦 Skipping npm install -g pnpm for local mock run..."
# npm install -g pnpm

echo "📦 Attempting to install monorepo dependencies..."
# Disable exit-on-error temporarily to catch failures
set +e

# Issue #1593: production builds must respect pnpm-lock.yaml exactly —
# --frozen-lockfile fails instead of silently resolving drifted deps
# (supply-chain / reproducibility guard).
pnpm install --frozen-lockfile
EXIT_CODE=$?

# Re-enable exit-on-error
set -e

if [ $EXIT_CODE -ne 0 ]; then
    echo "⚠️ Dependency installation failed with exit code $EXIT_CODE!"
    echo "🧹 Possible corrupted cache detected. Clearing node_modules..."
    
    # Remove node_modules at root and inside frontend
    rm -rf node_modules
    rm -rf frontend/node_modules
    
    # Remove pnpm store cache if it exists locally
    pnpm store prune || true
    
    echo "🔄 Retrying clean installation..."
    # Issue #1593: production builds must respect pnpm-lock.yaml exactly —
# --frozen-lockfile fails instead of silently resolving drifted deps
# (supply-chain / reproducibility guard).
pnpm install --frozen-lockfile
else
    echo "✅ Frontend dependencies installed successfully."
fi

# 🔬 Evolution v3.0: Pre-build validation
echo "🔬 Running pre-build validation..."

# Check for required files
REQUIRED_FILES=("frontend/vite.config.ts" "frontend/package.json" "frontend/tsconfig.json")
for file in "${REQUIRED_FILES[@]}"; do
  if [ ! -f "$file" ]; then
    echo "❌ ERROR: Required file missing: $file"
    exit 1
  fi
done

# Validate backend URL format (must be https://)
if [ -n "$VITE_ADMIN_BACKEND" ] && [[ ! "$VITE_ADMIN_BACKEND" =~ ^https?:// ]]; then
  echo "❌ ERROR: VITE_ADMIN_BACKEND must be a valid URL (starting with http:// or https://)"
  exit 1
fi


echo "🔧 Checking for required environment variables..."
# বাংলা (unified single frontend): User + Admin একীভূত।
# VITE_API_URL বা VITE_BACKEND_URL আবশ্যক।
if [ -z "$VITE_API_URL" ] && [ -z "$VITE_BACKEND_URL" ] && [ -z "$VITE_USER_BACKEND" ]; then
  echo "❌ ERROR: VITE_API_URL or VITE_BACKEND_URL not set! A canonical backend URL is required."
  exit 1
fi

echo "🏗️ Building frontend (single unified build)..."
cd frontend
pnpm run build
cd ..

echo "🔧 Generating Firebase config..."
python scripts/deploy/generate_firebase_config.py

# 🔬 Evolution v3.0: Post-build verification
echo "🔬 Running post-build verification..."

if [ ! -d "frontend/dist" ]; then
  echo "❌ ERROR: Build output directory (frontend/dist) missing!"
  exit 1
fi

# Verify build-info.json was created (if production)
if [ "$NODE_ENV" = "production" ] && [ ! -f "frontend/dist/build-info.json" ]; then
  echo "❌ ERROR: build-info.json was not generated in production build!"
  exit 1
fi

echo "🎉 Frontend build finished successfully!"
