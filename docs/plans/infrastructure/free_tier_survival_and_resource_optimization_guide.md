---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:free_tier_survival_and_resource_optimization_guide
subject: 🆓 SuperAI Free-Tier Survival Guide
document_role: implementation
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# 🆓 SuperAI Free-Tier Survival Guide
## Maximum Usage Optimization for Zero-Cost Operations

---

## 📊 Service-by-Service Free Tier Analysis

### 1. Supabase (Database + Auth + Storage)

| Feature | Free Tier Limit | Your Current Est. Usage | Optimization Tips |
|---------|-----------------|------------------------|-------------------|
| **Database** | 500 MB storage, 1 GB bandwidth/mo | ~200-400 MB | Enable Row Level Security, use connection pooling |
| **Auth** | 50,000 MAU (Monthly Active Users) | Track via dashboard | Use JWT caching, minimize auth checks |
| **Storage** | 1 GB storage, 1 GB bandwidth/mo | ~100-500 MB | Compress images, use CDN |
| **Realtime** | 2M concurrent connections/mo | Monitor WebSocket usage | Implement reconnection logic with backoff |
| **Edge Functions** | 500K invocations/mo, 1GB bandwidth | Cache API responses | Use Edge Function caching headers |
| **Backup** | 7 days retention | N/A (auto) | Export weekly backups manually |

#### 🔧 Supabase Cost-Saving Configurations

```javascript
// supabase/config.toml optimizations
[api]
enabled = true
max_request_duration_us = 30000000  # 30s timeout prevents runaway

[db]
pool_size = 10  # Conservative pooling
port = 5432

# Enable connection pooling (PgBouncer) - CRITICAL for free tier
[db.pooler]
enabled = true
mode = "transaction"  # Transaction mode = best performance
default_pool_size = 15
max_client_conn = 100

[auth]
site_url = "http://localhost:3000"
additional_redirect_urls = ["https://supremeai.vercel.app"]
jwt_expiry = 3600  # 1 hour (balance between UX and cost)
enable_refresh_token_rotation = true
refresh_token_reuse_interval = 10  # Prevent token abuse

[storage]
file_size_limit = 5242880  # 5MB max upload (prevents abuse)
image_transformation_enabled = true  # Use Supabase image optimization (free!)
```

#### 💡 Supabase Pro Tips for Free Tier Survival

1. **Use `pgbouncer` always** — Every connection counts toward your limit
2. **Implement client-side caching** — Reduce API calls by 60-70%
3. **Batch database operations** — Combine multiple queries into RPC calls
4. **Use materialized views** for heavy analytics queries
5. **Archive old data** monthly to keep under 500MB
6. **Enable RLS on ALL tables** — Prevents data bloat from unauthorized access

---

### 2. Upstash Redis (Caching)

| Feature | Free Tier Limit | Optimization Strategy |
|---------|-----------------|----------------------|
| **Commands** | 10,000 commands/day | Use aggressive caching, batch operations |
| **Storage** | 256 MB max | Compress cached data, set TTL on all keys |
| **Connections** | Unlimited (within command limit) | Connection pooling still recommended |
| **Requests** | 30,000 requests/day | Cache aggressively at edge |

#### 🔧 Upstash Optimization Code

```python
# lib/upstash_optimizer.py
import json
import gzip
import base64
from typing import Any, Optional
import redis.asyncio as redis

class UpstashFreeTierOptimizer:
    """
    Maximizes Upstash free tier usage through:
    - Data compression (3-10x reduction)
    - Smart TTL management
    - Command batching
    - Priority-based eviction
    """
    
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)
        self.daily_command_count = 0
        self.MAX_DAILY_COMMANDS = 9500  # Leave 500 buffer
        
    async def compress_and_set(self, key: str, data: Any, ttl: int = 3600):
        """Compress data before storing to save memory"""
        serialized = json.dumps(data).encode('utf-8')
        compressed = gzip.compress(serialized)
        
        # Only store if compressed size is beneficial
        if len(compressed) < len(serialized):
            await self.redis.setex(key, ttl, compressed)
            return True
        else:
            await self.redis.setex(key, ttl, serialized)
            return True
    
    async def get_and_decompress(self, key: str) -> Optional[Any]:
        """Retrieve and decompress cached data"""
        data = await self.redis.get(key)
        if not data:
            return None
            
        try:
            decompressed = gzip.decompress(data)
            return json.loads(decompressed)
        except:
            # Fallback for uncompressed data
            return json.loads(data)
    
    async def smart_set_with_priority(self, key: str, data: Any, priority: str = "normal"):
        """
        Set cache with priority-aware TTL:
        - critical: 24h TTL
        - high: 12h TTL  
        - normal: 4h TTL
        - low: 30min TTL
        """
        ttl_map = {
            "critical": 86400,
            "high": 43200,
            "normal": 14400,
            "low": 1800
        }
        
        ttl = ttl_map.get(priority, 14400)
        await self.compress_and_set(key, data, ttl)
```

---

### 3. Render (Deployment/Hosting)

| Feature | Free Tier Limit | Survival Strategy |
|---------|-----------------|-------------------|
| **Web Service** | 750 hours/month (free tier) | Sleep after inactivity |
| **Static Sites** | Unlimited | Use for docs/marketing |
| **Background Workers** | 750 hours | Optimize cron jobs |
| **PostgreSQL** | 90 days free trial only | ⚠️ MIGRATE TO SUPABASE after trial! |
| **Bandwidth** | Unmetered | No worries here |

#### 🔧 Render Free-Tier Optimizations

```yaml
# render.yaml optimized configuration
services:
  - type: web
    name: supremeai-api
    runtime: python
    plan: free  # Explicitly use free tier
    
    # CRITICAL: Auto-suspend settings
    autoDeploy: false  # Manual deploys save build minutes
    healthCheckPath: /health
    
    # Environment variables for cost control
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.0
      - key: WORKERS
        value: "1"  # Single worker for free tier
      - key: MAX_REQUEST_SIZE
        value: "1048576"  # 1MB limit
      
    # Scaling (free tier is always 1 instance)
    scaling:
      minInstances: 1
      maxInstances: 1
      targetMemoryPercent: 80
      targetCPUPercent: 80

  - type: web
    name: supremeai-web
    runtime: node
    plan: free
    
    # Next.js specific optimizations
    buildCommand: npm run build
    startCommand: npm start
    
    envVars:
      - key: NEXT_TELEMETRY_DISABLED
        value: "1"  # Disable telemetry (saves requests)
      - key: NODE_ENV
        value: "production"

cronjobs:
  - name: daily-cleanup
    schedule: "0 4 * * *"  # 4 AM UTC
    command: python scripts/daily_cleanup.py
```

#### 💡 Render Survival Tips

1. **Disable auto-deploy** — Every push triggers a new build (wastes resources)
2. **Use `render.yaml`** — Version control your config
3. **Implement health checks properly** — Render uses these to decide if restart needed
4. **Keep bundle small** — Smaller containers = faster cold starts
5. **Use background workers sparingly** — They count against same 750hr limit

---

### 4. GitHub Actions (CI/CD)

| Resource | Free Tier Limit | Optimization |
|----------|-----------------|--------------|
| **Public repos** | Unlimited minutes | Make repo public if possible! |
| **Private repos** | 2,000 min/month (free), 3,000 (Pro) | Cache everything |
| **Storage** | 500 MB | Clean up artifacts |
| **Workflow runs** | Unlimited | But limited by minutes |

#### 🔧 GitHub Actions Cost-Saving Workflow

```yaml
# .github/workflows/ci-optimized.yml
name: SuperAI CI (Cost-Optimized)

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true  # Cancel old runs (SAVES MINUTES!)

jobs:
  # Job 1: Quick lint & type check (CHEAPEST)
  lint:
    runs-on: ubuntu-latest
    timeout-minutes: 5  # Hard timeout
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'  # CACHE npm dependencies!
      
      - name: Install dependencies
        run: npm ci --prefer-offline  # Use cache first
        
      - name: Run linter
        run: npm run lint -- --max-warnings=0
        continue-on-error: true  # Don't block on warnings
  
  # Job 2: Build (CACHE HEAVY)
  build:
    runs-on: ubuntu-latest
    needs: lint
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      
      - name: Cache Next.js build
        uses: actions/cache@v4
        with:
          path: |
            .next/cache
            node_modules
            ~/.npm
          key: ${{ runner.os }}-nextjs-${{ hashFiles('**/package-lock.json') }}
          restore-keys: |
            ${{ runner.os }}-nextjs-
            
      - name: Build
        run: npm run build
        
      - name: Upload build artifact
        uses: actions/upload-artifact@v4
        with:
          name: nextjs-build
          path: .next/
          retention-days: 1  # Don't store long!

  # Job 3: Test (ONLY ON PR OR MAIN)
  test:
    runs-on: ubuntu-latest
    needs: build
    if: github.event_name == 'pull_request' || github.ref == 'refs/heads/main'
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      
      - name: Download build
        uses: actions/download-artifact@v4
        with:
          name: nextjs-build
          path: .next/
          
      - name: Run tests
        run: npm test -- --ci --coverage --maxWorkers=2
        env:
          CI: true

  # Job 4: Deploy (MAIN ONLY)
  deploy:
    runs-on: ubuntu-latest
    needs: [build, test]
    if: github.ref == 'refs/heads/main' && success()
    timeout-minutes: 5
    steps:
      - name: Deploy to Render
        run: |
          curl -X POST "$RENDER_DEPLOY_HOOK_URL" \
            -H "Content-Type: application/json"
        env:
          RENDER_DEPLOY_HOOK_URL: ${{ secrets.RENDER_DEPLOY_HOOK }}
```

---

### 5. LLM API Providers (OpenAI/Claude/Gemini)

| Provider | Free Credits/Tier | Limits | Best For |
|----------|------------------|--------|----------|
| **OpenAI** | $5 new users, then pay-as-you-go | Rate limits apply | GPT-4o mini (cheapest!) |
| **Anthropic** | Free tier varies | Rate limits | Claude 3 Haiku (cheapest) |
| **Google AI** | Free tier with rate limits | 1500 req/day free | Gemini Flash (FREE tier!) |
| **Groq** | Generous free tier | High rate limits | FAST inference, free models |
| **Together AI** | $5 free credits | Various open-source | Open source alternatives |
| **HuggingFace** | Free Inference API | Rate limited | Free model hosting |

#### 🎯 LLM Cost Optimization Strategy

```python
# lib/llm_router.py - Smart LLM Router for Cost Optimization
import os
import random
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class LLMProviderConfig:
    name: str
    free_tier_limit: int  # Daily requests
    current_usage: int
    cost_per_1k_tokens: float
    priority: int  # Lower = use first

class SmartLLMRouter:
    """
    Routes requests to cheapest available provider.
    Prioritizes free tiers, falls back gracefully.
    """
    
    PROVIDERS = {
        "gemini-flash": LLMProviderConfig(
            name="Gemini Flash",
            free_tier_limit=1500,  # Google's free tier!
            current_usage=0,
            cost_per_1k_tokens=0.0,  # FREE!
            priority=1  # Always try first
        ),
        "groq-llama": LLMProviderConfig(
            name="Groq Llama",
            free_tier_limit=14400,  # Very generous!
            current_usage=0,
            cost_per_1k_tokens=0.0,  # FREE!
            priority=2
        ),
        "gpt-4o-mini": LLMProviderConfig(
            name="GPT-4o Mini",
            free_tier_limit=0,  # No free tier
            current_usage=0,
            cost_per_1k_tokens=0.15,  # Very cheap!
            priority=3
        ),
        "claude-haiku": LLMProviderConfig(
            name="Claude Haiku",
            free_tier_limit=0,
            current_usage=0,
            cost_per_1k_tokens=0.25,
            priority=4
        )
    }
    
    def __init__(self):
        self.usage_tracker = {name: 0 for name in self.PROVIDERS}
        self.daily_reset_needed = False
    
    async def route_request(self, prompt: str, complexity: str = "simple") -> tuple[str, Dict]:
        """
        Route to optimal provider based on:
        1. Free tier availability
        2. Task complexity
        3. Current usage
        """
        # Simple tasks → Free providers first
        if complexity == "simple":
            for provider_name, config in sorted(
                self.PROVIDERS.items(), 
                key=lambda x: x[1].priority
            ):
                if config.current_usage < config.free_tier_limit or config.cost_per_1k_tokens == 0:
                    return await self._call_provider(provider_name, prompt)
        
        # Complex tasks → Best quality within budget
        return await self._call_provider("gpt-4o-mini", prompt)
    
    async def _call_provider(self, provider: str, prompt: str) -> tuple[str, Dict]:
        """Call specific provider and track usage"""
        # Implementation depends on your SDK setup
        self.usage_tracker[provider] += 1
        result = f"Response from {provider}"
        metadata = {"provider": provider, "cost_estimate": 0}
        return result, metadata
    
    def get_daily_summary(self) -> Dict:
        """Get usage summary for monitoring"""
        return {
            "total_requests": sum(self.usage_tracker.values()),
            "estimated_cost": sum(
                count * self.PROVIDERS[name].cost_per_1k_tokens / 1000
                for name, count in self.usage_tracker.items()
            ),
            "by_provider": self.usage_tracker.copy(),
            "free_tier_remaining": {
                name: max(0, cfg.free_tier_limit - self.usage_tracker[name])
                for name, cfg in self.PROVIDERS.items()
            }
        }
```

---

### 6. Vercel (Frontend Hosting - Alternative to Render)

| Feature | Free Tier | Notes |
|----------|-----------|-------|
| **Deployments** | 100/month | Plenty for most projects |
| **Bandwidth** | 100GB/month | May need optimization |
| **Build Minutes** | 6,000/month | More than GitHub Actions! |
| **Serverless Function** | 100GB-hours | Generous |
| **Edge Functions** | Unlimited invocations | Use for middleware! |

---

## 🛠️ Universal Free-Tier Survival Strategies

### 1. Request Deduplication Pattern

```python
# lib/request_deduplicator.py
import hashlib
import time
from functools import wraps
from typing import Any, Callable

class RequestDeduplicator:
    """
    Deduplicates identical requests within a time window.
    Saves 20-40% of API calls for repeated queries.
    """
    
    def __init__(self, window_seconds: int = 60):
        self.cache = {}
        self.window = window_seconds
    
    def _hash_request(self, *args, **kwargs) -> str:
        request_str = str(args) + str(sorted(kwargs.items()))
        return hashlib.sha256(request_str.encode()).hexdigest()
    
    def deduplicate(self, func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = self._hash_request(*args, **kwargs)
            
            if key in self.cache:
                cached_time, cached_result = self.cache[key]
                if time.time() - cached_time < self.window:
                    return cached_result  # Return cached result
            
            result = await func(*args, **kwargs)
            self.cache[key] = (time.time(), result)
            
            # Cleanup old entries periodically
            if len(self.cache) > 1000:
                cutoff = time.time() - self.window * 2
                self.cache = {k: v for k, v in self.cache.items() 
                             if v[0] > cutoff}
            
            return result
        return wrapper

# Usage
deduplicator = RequestDeduplicator(window_seconds=120)

@deduplicator.deduplicate
async def fetch_ai_response(prompt: str):
    # This will be deduplicated for identical prompts within 2min
    pass
```

### 2. Response Caching Middleware

```typescript
// middleware/responseCache.ts
import { NextRequest, NextResponse } from 'next/server';

interface CacheEntry {
  response: NextResponse;
  timestamp: number;
  hits: number;
}

const responseCache = new Map<string, CacheEntry>();
const DEFAULT_TTL = 5 * 60 * 1000; // 5 minutes
const MAX_CACHE_SIZE = 200;

export function responseCacheMiddleware(ttlMs: number = DEFAULT_TTL) {
  return async (request: NextRequest): Promise<NextResponse | null> => {
    const cacheKey = `${request.method}:${request.nextUrl.pathname}:${request.nextUrl.search}`;
    
    // Check cache
    const cached = responseCache.get(cacheKey);
    if (cached && Date.now() - cached.timestamp < ttlMs) {
      cached.hits++;
      console.log(`🎯 Cache HIT (${cached.hits}x): ${cacheKey}`);
      return cached.response;
    }
    
    return null; // Not cached, proceed to handler
  };
}

export function cacheResponse(request: NextRequest, response: NextResponse, ttlMs: number = DEFAULT_TTL) {
  const cacheKey = `${request.method}:${request.nextUrl.pathname}:${request.nextUrl.search}`;
  
  // Evict oldest if full
  if (responseCache.size >= MAX_CACHE_SIZE) {
    let oldestKey = '';
    let oldestTime = Infinity;
    for (const [key, entry] of responseCache.entries()) {
      if (entry.timestamp < oldestTime) {
        oldestTime = entry.timestamp;
        oldestKey = key;
      }
    }
    responseCache.delete(oldestKey);
  }
  
  responseCache.set(cacheKey, {
    response: response.clone(), // Clone to allow reuse
    timestamp: Date.now(),
    hits: 1
  });
  
  console.log(`💾 Cached: ${cacheKey}`);
}
```

### 3. Database Query Optimization

```sql
-- Supabase/PostgreSQL optimization queries

-- 1. Check table sizes (keep under 500MB total)
SELECT 
  schemaname,
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'::text||tablename)) AS size,
  pg_total_relation_size(schemaname||'.'::text||tablename) AS size_bytes
FROM pg_tables 
WHERE schemaname = 'public'
ORDER BY size_bytes DESC;

-- 2. Find indexes that are never used (wasted space)
SELECT 
  indexrelid::regclass AS index_name,
  relname AS table_name,
  idx_scan AS times_used,
  pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
JOIN pg_index ON pg_index.indexrelid = pg_stat_user_indexes.indexrelid
WHERE idx_scan = 0  -- Never used!
AND NOT pg_index.indisunique;  -- Keep unique indexes

-- 3. Check connection count (stay under Supabase limits)
SELECT count(*) as active_connections,
       state
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state;

-- 4. Archive old logs (run monthly to save space)
CREATE OR REPLACE FUNCTION archive_old_logs(months_old INT = 3)
RETURNS void AS $$
BEGIN
  -- Create archive table if not exists
  CREATE TABLE IF NOT EXISTS logs_archive AS SELECT * FROM logs WHERE FALSE;
  
  -- Move old logs
  INSERT INTO logs_archive SELECT * FROM logs 
  WHERE created_at < NOW() - (months_old || ' months')::INTERVAL;
  
  -- Delete from main table
  DELETE FROM logs 
  WHERE created_at < NOW() - (months_old || ' months')::INTERVAL;
END;
$$ LANGUAGE plpgsql;
```

---

## 📈 Daily/Monthly Maintenance Checklist

### Daily (Automated via Cron)
- [ ] Check Supabase storage usage (< 450MB warning threshold)
- [ ] Verify Redis command count (< 8000/day safe zone)
- [ ] Review GitHub Actions minutes used
- [ ] Clear temporary caches
- [ ] Check error rates (high errors = wasted retries)

### Weekly
- [ ] Archive old database records
- [ ] Review LLM API costs across providers
- [ ] Clean up unused assets/storage
- [ ] Check Render deployment logs for issues
- [ ] Verify backup integrity

### Monthly
- [ ] Full audit of all service usage vs limits
- [ ] Rotate API keys/secrets
- [ ] Review and optimize expensive queries
- [ ] Update dependency versions
- [ ] Plan for scale (when to move off free tiers)

---

## 🚨 When to Upgrade (Warning Signs)

| Service | Warning Threshold | Action Required |
|---------|------------------|-----------------|
| Supabase DB | > 400MB / 500MB | Archive data, optimize |
| Supabase Auth | > 35K / 50K MAU | Review bot traffic |
| Upstash Redis | > 8K / 10K commands/day | Increase cache TTL |
| GitHub Actions | > 1500 / 2000 min/month | Optimize workflows |
| Render Web | > 600 / 750 hours | Check sleep settings |
| LLM APIs | > $20/month spend | Switch to cheaper models |

---

## 💰 Estimated Monthly Savings with These Optimizations

| Optimization | Potential Savings |
|--------------|------------------|
| LLM smart routing (Gemini Flash first) | $15-50/month |
| Response caching | 30-50% fewer API calls |
| Request deduplication | 20-40% fewer duplicate calls |
| Database query optimization | Faster responses = fewer timeouts |
| Image compression (Supabase) | 50-70% storage savings |
| GitHub Actions caching | 40-60% fewer build minutes |
| **Total Estimated Savings** | **$50-150+/month** |

---

*Last Updated: August 2026*
*For SupremeAI Project - Maximum Free-Tier Utilization Strategy*