---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:infisical_enterprise_secret_management_guide
subject: 🔐 SuperAI Infisical Setup Guide
document_role: implementation
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# 🔐 SuperAI Infisical Setup Guide
## Enterprise-Grade Secret Management for Free-Tier Survival

---

## 📋 Table of Contents

1. [Why Infisical?](#why-infisical)
2. [Quick Start (5 minutes)](#quick-start)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Project Setup](#project-setup)
6. [Secret Management](#secret-management)
7. [Integration Examples](#integration-examples)
8. [Security Best Practices](#security-best-practices)
9. [Troubleshooting](#troubleshooting)

---

## Why Infisical?

### ❌ Problems with Traditional Secret Management

| Method | Problem | Risk Level |
|--------|---------|------------|
| **Hardcoded in source** | Visible in Git, deployments | 🔴 CRITICAL |
| **.env files committed** | Public repos expose secrets | 🔴 CRITICAL |
| **.env files local** | Easy to leak, share, forget | 🟠 HIGH |
| **Environment variables** | Log injection, process exposure | 🟡 MEDIUM |
| **Vault/HashiCorp** | Complex setup, expensive infra | 🟡 MEDIUM |

### ✅ Infisical Advantages

| Feature | Benefit |
|---------|---------|
| **End-to-end encryption** | Secrets encrypted at rest and in transit |
| **Never stored in code** | Zero chance of committing secrets |
| **Automatic rotation** | Schedule secret rotations easily |
| **Access control** | Granular permissions per secret/environment |
| **Audit trail** | Who accessed what, when |
| **Free tier** | Perfect for our free-tier strategy! |
| **Self-hostable** | Full control if needed |
| **Multi-environment** | Dev/Staging/Prod separation |

---

## Quick Start

### Step 1: Create Infisical Account (FREE)

```bash
# Option A: Use Infisical Cloud (free tier available)
1. Go to https://app.infisical.com
2. Sign up with GitHub/Google/Email
3. Create new project: "SuperAI"

# Option B: Self-host (for maximum security)
# See: Self-hosting section below
```

### Step 2: Install SDK

```bash
# Python SDK
pip install infisical-sdk

# Or add to requirements.txt
echo "infisical-sdk" >> requirements.txt
pip install -r requirements.txt
```

### Step 3: Configure Authentication

```bash
# Option 1: Universal Auth (Recommended for production)
export INFISICAL_CLIENT_ID="your_client_id"
export INFISICAL_CLIENT_SECRET="your_client_secret"
export INFISICAL_PROJECT_ID="your_project_id"
export INFISICAL_ENVIRONMENT="dev"  # dev/staging/prod

# Option 2: API Token (For CI/CD or quick testing)
export INFISICAL_TOKEN="your_api_token"
```

### Step 4: Start Using!

```python
from superai_infisical import get_secret, require_secret
import asyncio

async def main():
    # Get a secret (auto-cached, auto-fallback to env vars)
    api_key = await get_secret("OPENAI_API_KEY")
    
    # Get required secret (raises error if missing)
    db_url = await require_secret("DATABASE_URL")
    
    print(f"API Key: {api_key[:4]}...")
    print(f"DB URL: {db_url}")

asyncio.run(main())
```

---

## Installation

### Requirements

- Python 3.9+
- Infisical account (free) or self-hosted instance
- Internet access (for cloud) or internal access (self-hosted)

### Install from PyPI

```bash
# Install the SuperAI wrapper
cp /home/z/my-project/download/superai_infisical.py your_project/lib/

# Install dependencies
pip install infisical-sdk requests cryptography

# Verify installation
python -c "from superai_infisical import InfisicalSecretManager; print('✅ Installed!')"
```

### Docker Installation

```dockerfile
# Dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy our secret manager
COPY lib/superai_infisical.py /app/lib/

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Set environment (use Docker secrets or Kubernetes in production)
ENV INFISICAL_SITE_URL=https://app.infisical.com
# Don't set credentials here! Use runtime env or K8s secrets.

WORKDIR /app
CMD ["python", "main.py"]
```

---

## Configuration

### Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `INFISICAL_CLIENT_ID` | Yes* | Universal Auth Client ID | `abc123def456` |
| `INFISICAL_CLIENT_SECRET` | Yes* | Universal Auth Client Secret | `xyz789...` |
| `INFISICAL_PROJECT_ID` | Yes | Your project ID | `p_abc123...` |
| `INFISICAL_ENVIRONMENT` | No | Environment name (default: dev) | `prod` |
| `INFISICAL_SITE_URL` | No | Custom instance URL | `https://secrets.yourcompany.com` |
| `INFISICAL_TOKEN` | Yes** | Alternative: API Token | `st_xxx...` |

*Required for Universal Auth  
**Alternative to Client ID/Secret

### Configuration File (Optional)

Create `infisical.config.json`:

```json
{
  "siteUrl": "https://app.infisical.com",
  "projectId": "p_your_project_id",
  "auth": {
    "method": "universalAuth",
    "clientId": "${INFISICAL_CLIENT_ID}",
    "clientSecret": "${INFISICAL_CLIENT_SECRET}"
  },
  "caching": {
    "enabled": true,
    "ttlSeconds": 300,
    "maxCacheSize": 1000
  },
  "fallbacks": {
    "allowEnvironmentVariables": true,
    "allowDotEnvFile": true,
    "dotEnvPath": ".env.local"
  }
}
```

---

## Project Setup

### Creating Your First Project

#### Via Infisical Dashboard:

```
1. Login to https://app.infisical.com
2. Click "+ New Project"
3. Name: "SuperAI"
4. Workspace: Select or create workspace
5. Click "Create"
```

#### Via CLI (if installed):

```bash
# Install Infisical CLI (optional)
npm i -g infisical

# Login
infisical login

# Create project
infisical projects create SuperAI

# Get project ID
infisical projects ls
```

### Setting Up Environments

Infisical supports multiple environments out of the box:

```
SuperAI Project/
├── dev/          # Development (local, feature branches)
├── staging/      # Staging (pre-production testing)
├── prod/         # Production (live users)
├── ci/           # CI/CD pipelines
└── review/       # Pull request previews
```

### Creating Secrets

#### Method 1: Dashboard UI

```
1. Open your project
2. Select environment (e.g., "dev")
3. Click "+ New Secret"
4. Enter details:
   - Secret Name: OPENAI_API_KEY
   - Value: sk-...
   - Type: Shared (or Personal)
   - Note: "OpenAI API key for LLM features"
5. Click "Create Secret"
```

#### Method 2: CLI

```bash
# Set a secret
infisical secrets set OPENAI_API_KEY --value "sk-..." --environment dev

# Bulk import from .env file
infisical secrets import .env.production --environment prod

# Copy between environments
infisical secrets copy OPENAI_API_KEY --from dev --to staging
```

#### Method 3: Python SDK

```python
import asyncio
from infisical_sdk import InfisicalSDKClient

async def create_secret():
    client = InfisicalSDKClient(
        token="your_token",
        site_url="https://app.infisical.com"
    )
    
    await client.create_secret(
        secret_name="NEW_SECRET",
        secret_value="secret_value",
        project_id="your_project_id",
        environment="dev",
        type="shared",
        path="/"
    )

asyncio.run(create_secret())
```

### Recommended Secrets Structure for SuperAI

```
SuperAI Project Secrets
│
├── / (root path - shared across all services)
│   ├── APP_NAME = "SuperAI"
│   ├── APP_VERSION = "1.0.0"
│   │
├── /database/
│   ├── SUPABASE_URL
│   ├── SUPABASE_ANON_KEY
│   ├── SUPABASE_SERVICE_ROLE_KEY
│   │
├── /cache/
│   ├── UPSTASH_REDIS_REST_URL
│   ├── UPSTASH_REDIS_REST_TOKEN
│   │
├── /llm/
│   ├── OPENAI_API_KEY
│   ├── ANTHROPIC_API_KEY
│   ├── GOOGLE_AI_API_KEY
│   ├── GROQ_API_KEY
│   │
├── /deployment/
│   ├── RENDER_DEPLOY_HOOK
│   ├── VERCEL_TOKEN
│   ├── GITHUB_TOKEN
│   │
└── /third-party/
    ├── STRIPE_API_KEY
    ├── SENDGRID_API_KEY
    └── ANALYTICS_WRITE_KEY
```

---

## Secret Management

### Reading Secrets

#### Basic Usage

```python
from superai_infisical import (
    InfisicalSecretManager, 
    get_secret, 
    require_secret,
    SecretContext
)
import asyncio

async def basic_examples():
    manager = InfisicalSecretManager()
    
    # Simple fetch (with caching + fallback)
    api_key = await manager.get_secret("OPENAI_API_KEY")
    
    # Required secret (throws error if missing)
    try:
        db_url = await require_secret("DATABASE_URL")
    except ValueError as e:
        print(f"Missing required secret: {e}")
    
    # With explicit environment
    prod_key = await manager.get_secret(
        "STRIPE_SECRET_KEY",
        environment="prod"
    )
    
    # With default value
    debug_mode = await manager.get_secret(
        "DEBUG_MODE",
        default="false"
    )

asyncio.run(basic_examples())
```

#### Batch Fetching

```python
async def batch_example():
    manager = InfisicalSecretManager()
    
    # Fetch multiple at once (efficient!)
    llm_keys = await manager.get_secrets([
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_AI_API_KEY",
        "GROQ_API_KEY"
    ])
    
    for name, value in llm_keys.items():
        status = "✅" if value else "❌"
        masked = f"{value[:4]}..." if value else "None"
        print(f"{status} {name}: {masked}")

asyncio.run(batch_example())
```

#### Context Manager Usage

```python
async def context_example():
    async with SecretContext(prefetch_common_secrets=True) as secrets:
        # Access as attributes
        openai_key = secrets.OPENAI_API_KEY
        supabase_url = secrets.SUPABASE_URL
        
        # Use in application
        initialize_app(openai=openai_key, supabase=supabase_url)

asyncio.run(context_example())
```

### Writing/Updating Secrets

```python
async def update_secrets():
    """Update secrets programmatically"""
    manager = InfisicalSecretManager()
    
    # Rotate an API key
    new_key = generate_new_api_key()
    
    # Update in Infisical (requires write permissions)
    # This would use the Infisical SDK's update method
    # await manager.client.updateSecret(...)
    
    # Clear cache so next fetch gets new value
    manager.clear_cache("OPENAI_API_KEY")
    
    # Verify new value
    fetched = await manager.get_secret("OPENAI_API_KEY")
    assert fetched == new_key, "Key rotation failed!"

asyncio.run(update_secrets())
```

### Caching Strategy

The SuperAI Infisical Manager includes intelligent caching:

```python
# Cache configuration options
manager = InfisicalSecretManager(
    enable_cache=True,          # Enable caching (default: True)
    default_cache_ttl=300,      # 5 minute TTL (default: 300s)
)

# Manual cache control
await manager.get_secret("API_KEY", cache_ttl=3600)  # Cache for 1 hour
manager.clear_cache("API_KEY")  # Clear specific secret
manager.clear_cache()  # Clear ALL cached secrets

# Local override (for testing only!)
manager.set_local_override("API_KEY", "test_value", ttl=60)
```

---

## Integration Examples

### Next.js Integration

```typescript
// lib/secrets.ts - Server-side secret access
// This runs on the server ONLY - never exposed to client

import { InfisicalClient } from '@infisical/sdk';

let client: InfisicalClient | null = null;

function getClient(): InfisicalClient {
  if (!client) {
    client = new InfisicalClient({
      token: process.env.INFISICAL_TOKEN!,
    });
  }
  return client;
}

export async function getServerSecret(secretName: string): Promise<string> {
  const client = getClient();
  
  const secret = await client.getSecret({
    secretName,
    projectId: process.env.INFISICAL_PROJECT_ID!,
    environment: process.env.NODE_ENV === 'production' ? 'prod' : 'dev',
  });
  
  return secret.secretValue;
}

// Usage in API routes
export default async function handler(req: Request) {
  const apiKey = await getServerSecret('OPENAI_API_KEY');
  
  // Use apiKey securely...
}
```

### FastAPI Backend Integration

```python
# main.py - FastAPI with Infisical
from fastapi import FastAPI
from superai_infisical import get_secret_manager
from contextlib import asynccontextmanager

app = FastAPI(title="SuperAPI")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize secret manager on startup
    manager = get_secret_manager()
    
    # Pre-warm cache with critical secrets
    await manager.get_secrets([
        "DATABASE_URL",
        "REDIS_URL",
        "OPENAI_API_KEY"
    ])
    
    yield  # Application running
    
    # Cleanup on shutdown
    manager.clear_cache()

app.router.lifespan_context = lifespan

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.post("/api/chat")
async def chat_endpoint(prompt: str):
    manager = get_secret_manager()
    
    # Get API key securely
    api_key = await manager.get_secret("OPENAI_API_KEY", required=True)
    
    # Process chat...
    return {"response": "Hello!"}
```

### GitHub Actions CI/CD

```yaml
# .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Authenticate with Infisical
        uses: infisical/github-action-authenticate@v1
        with:
          url: ${{ secrets.INFISICAL_URL }}
          client-id: ${{ secrets.INFISICAL_CLIENT_ID }}
          client-secret: ${{ secrets.INFISICAL_CLIENT_SECRET }}
      
      - name: Inject Secrets into Environment
        uses: infisical/github-action-secrets@v1
        with:
          project-id: ${{ secrets.INFISICAL_PROJECT_ID }}
          env-name: 'prod'
      
      - name: Deploy
        run: |
          echo "Deploying with secrets..."
          echo "DB_URL is set: ${DATABASE_URL:+yes}"
          npm run deploy
```

### Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  superai-api:
    build: .
    ports:
      - "3000:3000"
    environment:
      - INFISICAL_SITE_URL=${INFISICAL_SITE_URL}
      - INFISICAL_CLIENT_ID=${INFISICAL_CLIENT_ID}
      - INFISICAL_CLIENT_SECRET=${INFISICAL_CLIENT_SECRET}
      - INFISICAL_PROJECT_ID=${INFISICAL_PROJECT_ID}
      - INFISICAL_ENVIRONMENT=${INFISICAL_ENVIRONMENT:-dev}
    # Alternative: Use Docker secrets for production
    # secrets:
    #   - infisical_client_id
    #   - infisical_client_secret

  # For production, use external secrets management
  # secrets:
  #   infisical_client_id:
  #     file: ./secrets/infisical_client_id.txt
  #   infisical_client_secret:
  #     file: ./secrets/infisical_client_secret.txt
```

---

## Security Best Practices

### ✅ DO's

1. **Use different environments**
   ```python
   # Separate secrets per environment
   dev_key = await get_secret("API_KEY", environment="dev")
   prod_key = await get_secret("API_KEY", environment="prod")
   ```

2. **Enable audit logging**
   ```python
   manager = InfisicalSecretManager(audit_log_enabled=True)
   
   # Review access logs regularly
   log = manager.get_audit_log(since=datetime.now() - timedelta(days=7))
   ```

3. **Rotate secrets regularly**
   ```bash
   # Set up automatic rotation schedule
   # Critical keys: Every 30 days
   # API keys: Every 90 days
   # DB passwords: Every 180 days
   ```

4. **Use minimal permissions**
   ```
   - CI/CD bots: Read-only access to specific environments
   - Developers: Read access to dev/staging only
   - Prod access: Limited to deployment service accounts
   ```

5. **Validate secrets exist at startup**
   ```python
   async def startup_check():
       required = ["DATABASE_URL", "REDIS_URL", "OPENAI_API_KEY"]
       for secret in required:
           value = await require_secret(secret)
           print(f"✅ {secret}: configured")
   ```

### ❌ DON'Ts

1. **Never commit .env files**
   ```bash
   # Add to .gitignore
   .env
   .env.local
   .env.production
   *.env
   
   # Use pre-commit hooks to prevent accidents
   pre-commit install
   ```

2. **Don't log secrets**
   ```python
   # BAD
   logger.info(f"Using API key: {api_key}")
   
   # GOOD (automatic masking by default)
   logger.info(f"Using API key: {api_key[:4]}...")
   ```

3. **Don't use production secrets in development**
   ```python
   # BAD
   prod_db = await get_secret("DB_URL", environment="prod")
   
   # GOOD
   dev_db = await get_secret("DB_URL", environment="dev")
   ```

4. **Don't hardcode fallback values**
   ```python
   # BAD
   key = await get_secret("API_KEY", default="sk-fake-key-for-dev")
   
   # BETTER
   key = await get_secret("API_KEY", required=True)
   # Or use local override explicitly
   manager.set_local_override("API_KEY", "dev-key", ttl=3600)
   ```

---

## Troubleshooting

### Common Issues

#### ❌ "Infisical not configured" Error

**Problem**: Missing credentials

**Solution**:
```bash
# Check environment variables
echo $INFISICAL_CLIENT_ID
echo $INFISICAL_CLIENT_SECRET
echo $INFISICAL_PROJECT_ID

# Set them
export INFISICAL_CLIENT_ID="your_id"
export INFISICAL_CLIENT_SECRET="your_secret"
export INFISICAL_PROJECT_ID="your_project_id"
```

#### ❌ "ModuleNotFoundError: No module named 'infisical_sdk'"

**Problem**: SDK not installed

**Solution**:
```bash
pip install infisical-sdk

# If using virtualenv
source venv/bin/activate
pip install infisical-sdk
```

#### ❌ "Authentication failed" Error

**Problem**: Invalid or expired credentials

**Solution**:
```bash
# 1. Check credentials are correct
# 2. Generate new ones in Infisical dashboard
# Settings → Machine Identities → Create New

# 3. Verify project access
# The identity must have access to the specified project
```

#### ❌ "Secret not found" but exists in dashboard

**Possible causes**:
1. Wrong environment name
2. Wrong path
3. Case-sensitive name mismatch
4. Permission issue

**Debug**:
```python
manager = InfisicalSecretManager()

# Try with explicit parameters
value = await manager.get_secret(
    "MySecret",  # Exact case
    environment="dev",
    path="/"  # Explicit path
)

# Check stats
print(manager.stats)
```

#### ❌ Slow response times

**Solution**: Enable caching
```python
manager = InfisicalSecretManager(
    enable_cache=True,
    default_cache_ttl=600  # 10 minutes
)
```

### Getting Help

- **Documentation**: https://infisical.com/docs
- **Community Slack**: https://infisical.com/slack
- **GitHub Issues**: https://github.com/Infisical/infisical/issues
- **SuperAI Support**: Check our Discord/community

---

## Advanced Topics

### Self-Hosting Infisical

For maximum security, self-host Infisical:

```yaml
# docker-compose.infisical.yml
version: '3.8'

services:
  infisical:
    image: infisical/infisical:latest
    ports:
      - '8080:8080'
    environment:
      - ENCRYPTION_KEY=${ENCRYPTION_KEY}
      - AUTH_SECRET=${AUTH_SECRET}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    depends_on:
      - postgres
      - redis
  
  postgres:
    image: postgres:14-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  redis:
    image: redis:6-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}

volumes:
  postgres_data:
```

### Secret Rotation Automation

```python
# scripts/rotate_secrets.py - Automated rotation
import asyncio
from datetime import datetime
from superai_infisical import InfisicalSecretManager

ROTATION_SCHEDULE = {
    "OPENAI_API_KEY": 90,     # days
    "SUPABASE_SERVICE_ROLE_KEY": 180,
    "REDIS_PASSWORD": 365,
}

async def check_rotation_needed():
    manager = InfisicalSecretManager(environment="prod")
    
    for secret_name, max_age_days in ROTATION_SCHEDULE.items():
        # Check when last rotated (you'd store this metadata)
        last_rotated = await get_last_rotation_date(secret_name)
        days_since = (datetime.now() - last_rotated).days
        
        if days_since >= max_age_days:
            print(f"⚠️ {secret_name} needs rotation ({days_since} days old)")
            # Trigger rotation workflow...

asyncio.run(check_rotation_needed())
```

### Multi-Region Support

```python
# For global applications
REGIONAL_CONFIGS = {
    "us-east": {
        "site_url": "https://us.infisical.com",
        "project_id": "us-project-id"
    },
    "eu-west": {
        "site_url": "https://eu.infisical.com", 
        "project_id": "eu-project-id"
    }
}

async def get_regional_secret(secret_name: str, region: str):
    config = REGIONAL_CONFIGS[region]
    manager = InfisicalSecretManager(**config)
    return await manager.get_secret(secret_name)
```

---

## Summary

✅ **You're now ready to use Infisical with SuperAI!**

### Quick Reference

```python
# Import
from superai_infisical import get_secret, require_secret, InfisicalSecretManager

# Basic usage
api_key = await get_secret("SECRET_NAME")

# Required (throws if missing)
db_url = await require_secret("REQUIRED_SECRET")

# Advanced
manager = InfisicalSecretManager(environment="prod")
all_secrets = await manager.get_secrets(["KEY1", "KEY2", "KEY3"])

# Export for legacy support
from superai_infisical import load_env_from_infisical
load_env_from_infisical()  # Now os.environ works!
```

### Security Checklist

- [ ] Infisical account created
- [ ] Project set up with environments
- [ ] Secrets imported from .env files
- [ ] Old .env files deleted
- [ ] .gitignore updated
- [ ] CI/CD configured with Infisical auth
- [ ] Access controls configured
- [ ] Audit logging enabled
- [ ] Rotation schedule planned
- [ ] Team trained on usage

---

**Last Updated**: August 2026  
**Version**: 1.0  
**Maintained By**: SuperAI Team

🚀 **Your secrets are now enterprise-grade secure!**