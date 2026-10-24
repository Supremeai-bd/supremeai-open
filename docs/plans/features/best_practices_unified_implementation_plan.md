---
target_scope: combined_ecosystem
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:best_practices_unified_implementation_plan
subject: 🏗️ SupremeAI — Best Implementation Plan
document_role: implementation
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# 🏗️ SupremeAI — Best Implementation Plan
## 4টি High-Value Feature (Codebase-Verified, Production-Ready)

> **ভিত্তি:** আমরা বাস্তব কোডবেস বিশ্লেষণ করেছি। প্রতিটি ফাইলের পাথ, API, ডেটাবেস স্কিমা এবং ইন্টিগ্রেশন পয়েন্ট সুনির্দিষ্টভাবে চিহ্নিত করা হয়েছে।

---

## কোডবেস থেকে যা আবিষ্কার করা হয়েছে (What Already Exists)

| Feature Area | Existing Code | Status |
|---|---|---|
| Vector Memory | [`backend/core/ai_memory/vector_store.py`](./backend/core/ai_memory/vector_store.py) | `FreeTierOptimizedVectorStore` w/ Supabase pgvector — কিন্তু agent prompt-এ auto-inject নেই |
| Unified Memory | [`backend/core/unified_memory.py`](./backend/core/unified_memory.py) | Interface আছে কিন্তু RAG-before-prompt hook নেই |
| Circuit Breaker | [`backend/core/circuit_breaker.py`](./backend/core/circuit_breaker.py) | Full CLOSED/OPEN/HALF_OPEN state machine — কিন্তু Cloudflare Worker-এ টাই-আপ নেই |
| Stealth Mouse | [`backend/core/human_behavior.py`](./backend/core/human_behavior.py) | `_generate_bezier_points()` আছে, কিন্তু Canvas fingerprint spoofing নেই |
| Dashboard UI | [`frontend/src/components/dashboard/`](./frontend/src/components/dashboard/) | 36 টি কম্পোনেন্ট — কিন্তু 1-Line MCP connect UX ও glass effects missing |
| Design Tokens | [`frontend/src/index.css`](./frontend/src/index.css) | Dark theme + neon colors আছে — glassmorphism layer নেই |

---

## ✅ Feature 1: 1-Line MCP Connection UX + Glassmorphic Dashboard Polish

### কী আছে এখন
- `ConnectedPlatformsVault.tsx` — credential vault আছে কিন্তু ugly form-based modal
- Design tokens: `--neon-blue: #00F3FF`, `--card-bg: #0B0F17` — glass effect নেই

### কী যোগ করতে হবে

---

#### [MODIFY] [`frontend/src/index.css`](./frontend/src/index.css)

নিচের CSS utilities যোগ করতে হবে (`:root` block-এর পরে):

```css
/* ═══════════════════ GLASSMORPHISM LAYER ═══════════════════ */
.glass-panel {
  background: rgba(11, 15, 23, 0.6);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border: 1px solid rgba(0, 243, 255, 0.12);
  border-radius: 16px;
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.4),
    inset 0 1px 0 rgba(255, 255, 255, 0.05);
}

.glass-input {
  background: rgba(6, 7, 11, 0.7);
  border: 1px solid rgba(0, 243, 255, 0.2);
  border-radius: 10px;
  color: #F8FAFC;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.glass-input:focus {
  outline: none;
  border-color: rgba(0, 243, 255, 0.6);
  box-shadow: 0 0 0 3px rgba(0, 243, 255, 0.1), 0 0 20px rgba(0, 243, 255, 0.15);
}

.pulse-ring {
  animation: pulse-neon 2s infinite;
}
@keyframes pulse-neon {
  0%, 100% { box-shadow: 0 0 8px rgba(0, 243, 255, 0.3); }
  50%       { box-shadow: 0 0 24px rgba(0, 243, 255, 0.7); }
}

.node-active {
  animation: node-beat 1.5s ease-in-out infinite;
}
@keyframes node-beat {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: 0.7; transform: scale(0.97); }
}
```

---

#### [NEW] `frontend/src/components/dashboard/OneLinerMCPConnect.tsx`

**Purpose:** একটি মাত্র URL/Token ইনপুটে MCP Server বা AI Provider সংযুক্ত করার ১-লাইন UX।

```tsx
// frontend/src/components/dashboard/OneLinerMCPConnect.tsx
import React, { useState } from 'react';
import { apiClient } from '../../services/apiClient';

interface MCPConnectResult {
  id: string;
  name: string;
  type: 'mcp' | 'ai_provider' | 'webhook';
  status: 'connected' | 'failed';
  capabilities: string[];
}

export const OneLinerMCPConnect: React.FC = () => {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<MCPConnectResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleConnect = async () => {
    if (!url.trim()) return;
    setLoading(true);
    setError(null);
    try {
      // POST to backend discovery endpoint
      const res = await apiClient.post<MCPConnectResult>(
        '/api/v1/integrations/discover',
        { url: url.trim() }
      );
      setResult(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Connection failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-panel p-6 space-y-4">
      <h2 className="text-lg font-bold text-[#00F3FF]">
        ⚡ 1-Line Connect
      </h2>
      <p className="text-sm text-[#94A3B8]">
        MCP Server URL, AI Provider endpoint, বা Webhook — একটি URL হলেই যথেষ্ট।
      </p>

      <div className="flex gap-2">
        <input
          id="mcp-url-input"
          className="glass-input flex-1 px-4 py-3 text-sm"
          placeholder="https://your-mcp-server.com/mcp  or  https://api.openai.com/v1"
          value={url}
          onChange={e => setUrl(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleConnect()}
        />
        <button
          id="mcp-connect-btn"
          onClick={handleConnect}
          disabled={loading || !url.trim()}
          className="px-5 py-3 rounded-xl bg-[#00F3FF] text-[#06070B] font-bold text-sm
                     disabled:opacity-40 hover:bg-cyan-300 transition-all pulse-ring"
        >
          {loading ? '⏳' : '🔗 Connect'}
        </button>
      </div>

      {result && (
        <div className="glass-panel p-4 border-[#22C55E]/30 bg-green-900/10">
          <p className="text-[#22C55E] font-semibold">✅ {result.name}</p>
          <p className="text-xs text-[#94A3B8] mt-1">
            Type: {result.type} · Capabilities: {result.capabilities.join(', ')}
          </p>
        </div>
      )}
      {error && (
        <div className="glass-panel p-4 border-red-500/30 bg-red-900/10">
          <p className="text-red-400 text-sm">❌ {error}</p>
        </div>
      )}
    </div>
  );
};
```

---

#### [NEW] Backend endpoint: `backend/routes/integrations_router.py` — `/discover` action

```python
# POST /api/v1/integrations/discover
@router.post("/discover")
async def discover_integration(payload: DiscoverRequest, user=Depends(get_current_user)):
    """
    1-line connect: URL ইনপুট দিলে MCP/AI Provider/Webhook auto-detect করে রেজিস্ট্রি-তে নিবন্ধন।
    """
    result = await IntegrationDiscoveryService.discover(
        url=payload.url,
        tenant_id=user.tenant_id,
        actor_id=user.id,
    )
    return result
```

**`IntegrationDiscoveryService`** — MCP handshake (`/.well-known/mcp.json`) → AI provider detection → webhook fallback এই ক্রমে অটো-ডিটেক্ট করবে।

---

## 🧠 Feature 2: Auto-RAG Memory Injection (সবচেয়ে High-Impact)

### কী আছে এখন
- `FreeTierOptimizedVectorStore` → Supabase pgvector similarity search ✅
- `UnifiedMemoryInterface.query_long_term_memory()` ✅
- কিন্তু agent task শুরুর আগে এই memory **automatically system prompt-এ inject হচ্ছে না**

### সমাধান

#### [NEW] `backend/core/memory/auto_rag_injector.py`

```python
"""
AutoRAGInjector — Agent task শুরুর আগে relevant past memories
automatically system prompt-এ inject করে।

ইন্টিগ্রেশন পয়েন্ট: backend/core/agent_factory.py এবং
backend/core/agents/ যেকোনো agent base class।
"""
from __future__ import annotations

from core.ai_memory.vector_store import FreeTierOptimizedVectorStore
from core.embeddings import get_embedding  # existing module
from core.logging_config import logger


class AutoRAGInjector:
    """Retrieves top-K relevant memories and prepends them to the system prompt."""

    MEMORY_PREFIX = "\n\n--- 🧠 Past Context (Auto-Recalled) ---\n"
    TOP_K = 5
    MAX_CHARS_PER_MEMORY = 400

    def __init__(self, vector_store: FreeTierOptimizedVectorStore):
        self._vs = vector_store

    async def enrich_system_prompt(
        self,
        system_prompt: str,
        user_query: str,
        user_id: str,
        tenant_id: str,
    ) -> str:
        """
        user_query와 유사한 past memories를 검색하여 system_prompt 앞에 추가.
        실패 시 원래 prompt를 그대로 반환 (silent graceful degradation).
        """
        try:
            embedding = await get_embedding(user_query)
            memories = await self._vs.similarity_search(
                query_embedding=embedding,
                limit=self.TOP_K,
                user_id=user_id,
            )
            if not memories:
                return system_prompt

            memory_block = self.MEMORY_PREFIX
            for i, mem in enumerate(memories, 1):
                content = mem.get("content", "")[:self.MAX_CHARS_PER_MEMORY]
                score = mem.get("score", 0)
                memory_block += f"{i}. [{score:.2f}] {content}\n"
            memory_block += "--- End of Past Context ---\n\n"

            logger.info(
                f"[AutoRAG] Injected {len(memories)} memories for user={user_id}"
            )
            return memory_block + system_prompt

        except Exception as e:
            logger.warning(f"[AutoRAG] Graceful degradation: {e}")
            return system_prompt

    async def store_session_memory(
        self,
        content: str,
        user_id: str,
        session_id: str,
        importance: float = 0.7,
    ) -> bool:
        """
        Session শেষে important exchange pgvector-এ store করে।
        importance < 0.5 হলে skip (low-value noise avoid)।
        """
        if importance < 0.5:
            return False
        try:
            embedding = await get_embedding(content)
            return await self._vs.upsert_batch(
                embeddings=[embedding],
                payloads=[{
                    "content": content,
                    "user_id": user_id,
                    "session_id": session_id,
                    "importance": importance,
                }],
                ids=[f"{user_id}:{session_id}:{hash(content) & 0xFFFFFF}"],
            )
        except Exception as e:
            logger.warning(f"[AutoRAG] Store failed: {e}")
            return False
```

#### [MODIFY] [`backend/core/agent_factory.py`](./backend/core/agent_factory.py)

`build_agent()` ফাংশনে system prompt তৈরির আগে `AutoRAGInjector.enrich_system_prompt()` call যোগ করতে হবে:

```python
# agent_factory.py — build_agent() এর ভেতরে, system_prompt set করার আগে:
from core.memory.auto_rag_injector import AutoRAGInjector
from core.ai_memory.vector_store import FreeTierOptimizedVectorStore

injector = AutoRAGInjector(FreeTierOptimizedVectorStore(...))
system_prompt = await injector.enrich_system_prompt(
    system_prompt=base_system_prompt,
    user_query=task.user_input,
    user_id=task.user_id,
    tenant_id=task.tenant_id,
)
```

---

## 🕵️ Feature 3: Biometric Stealth Scraper — Canvas & TLS Fingerprint Layer

### কী আছে এখন
- [`backend/core/human_behavior.py`](./backend/core/human_behavior.py): `_generate_bezier_points()` আছে ✅
- কিন্তু **Canvas fingerprint spoofing**, **WebGL noise**, **timezone/locale consistency** নেই

### সমাধান

#### [MODIFY] [`backend/core/human_behavior.py`](./backend/core/human_behavior.py)

`HumanBehaviorSimulators` class-এ নতুন `apply_stealth_fingerprint()` method যোগ করতে হবে:

```python
@classmethod
async def apply_stealth_fingerprint(cls, page: Page) -> None:
    """
    Cloudflare/Akamai bot-detection bypass করার জন্য
    Canvas ও WebGL fingerprint noise যোগ করে।
    """
    await page.add_init_script("""
    // 1. Canvas fingerprint noise
    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type, ...args) {
        const dataURL = origToDataURL.apply(this, [type, ...args]);
        // Add imperceptible noise to fingerprint
        return dataURL.replace(/.$/, String.fromCharCode(
            dataURL.charCodeAt(dataURL.length - 1) ^ (Math.random() * 4 | 0)
        ));
    };

    // 2. WebGL renderer string spoofing
    const getParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {
        if (param === 37445) return 'Intel Open Source Technology Center';
        if (param === 37446) return 'Mesa DRI Intel(R) Iris(R) Plus Graphics (ICL GT2)';
        return getParam.apply(this, [param]);
    };

    // 3. Remove navigator.webdriver trace
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

    // 4. Plugins array (appear as real browser)
    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
        ],
    });
    """)

    # 5. Random viewport (avoid fixed-size bot detection)
    import random
    widths = [1280, 1366, 1440, 1536, 1920]
    heights = [720, 768, 800, 864, 1080]
    await page.set_viewport_size({
        "width": random.choice(widths),
        "height": random.choice(heights)
    })
```

---

## ⚡ Feature 4: Cloudflare Worker → Backend Auto-Failover Circuit Breaker

### কী আছে এখন
- [`backend/core/circuit_breaker.py`](./backend/core/circuit_breaker.py): Full CLOSED/OPEN/HALF_OPEN state machine ✅
- [`infrastructure/cloudflare/enhanced-worker.js`](./infrastructure/cloudflare/enhanced-worker.js): Rate limit + caching আছে
- কিন্তু **backend primary node down হলে Cloudflare-level secondary failover নেই**

### সমাধান

#### [MODIFY] [`infrastructure/cloudflare/enhanced-worker.js`](./infrastructure/cloudflare/enhanced-worker.js)

`handleApiRequest` function-এ multi-node failover logic যোগ করতে হবে:

```javascript
// enhanced-worker.js — handleApiRequest() replacement
const BACKEND_NODES = [
  { url: 'https://<render-primary-url>', priority: 1 },
  { url: 'https://<render-worker-url>',  priority: 2 },
];

async function handleApiRequest(request, env, ctx) {
  const HEALTH_CACHE_KEY = 'node_health_v1';
  
  // Check KV for last known-bad node (circuit open)
  let failedNodes = new Set();
  try {
    const cached = await env.SUPREME_KV.get(HEALTH_CACHE_KEY);
    if (cached) failedNodes = new Set(JSON.parse(cached));
  } catch (_) {}

  for (const node of BACKEND_NODES.sort((a, b) => a.priority - b.priority)) {
    if (failedNodes.has(node.url)) continue; // skip OPEN circuit

    const targetUrl = request.url.replace(
      /^https:\/\/[^/]+/,
      node.url
    );

    try {
      const response = await fetch(new Request(targetUrl, request), {
        signal: AbortSignal.timeout(8000), // 8s timeout
      });

      if (response.ok || response.status < 500) {
        // Mark node as healthy (remove from failed set)
        failedNodes.delete(node.url);
        ctx.waitUntil(
          env.SUPREME_KV.put(
            HEALTH_CACHE_KEY,
            JSON.stringify([...failedNodes]),
            { expirationTtl: 120 } // 2 min circuit open
          )
        );
        return response;
      }
    } catch (err) {
      // Node failed — open circuit, try next
      console.error(`[FAILOVER] Node ${node.url} failed: ${err.message}`);
      failedNodes.add(node.url);
      ctx.waitUntil(
        env.SUPREME_KV.put(
          HEALTH_CACHE_KEY,
          JSON.stringify([...failedNodes]),
          { expirationTtl: 120 }
        )
      );
    }
  }

  return new Response(
    JSON.stringify({ error: 'All backend nodes unavailable. Please retry.' }),
    { status: 503, headers: { 'Content-Type': 'application/json' } }
  );
}
```

> **Note:** `wrangler.toml`-এ `[[kv_namespaces]]` — `binding = "SUPREME_KV"` যোগ করতে হবে।

---

## 📋 Implementation Order & Task Checklist

```markdown
Phase 1 — Dashboard UI (2-3 hours)
  - [ ] index.css: glassmorphism utilities যোগ করা
  - [ ] OneLinerMCPConnect.tsx তৈরি করা
  - [ ] ConnectedPlatformsVault.tsx-এ OneLinerMCPConnect embed করা
  - [ ] Backend: /api/v1/integrations/discover endpoint তৈরি করা

Phase 2 — Auto-RAG Injection (2-3 hours)
  - [ ] backend/core/memory/auto_rag_injector.py তৈরি করা
  - [ ] agent_factory.py-এ enrich_system_prompt() hook যোগ করা
  - [ ] backend/tests/test_auto_rag_injector.py লেখা (pytest)

Phase 3 — Stealth Fingerprint (1-2 hours)
  - [ ] human_behavior.py-এ apply_stealth_fingerprint() যোগ করা
  - [ ] playwright_manager.py-এ stealth bootstrap call করা

Phase 4 — Cloudflare Failover (1-2 hours)
  - [ ] enhanced-worker.js: multi-node failover logic যোগ করা
  - [ ] wrangler.toml: KV namespace binding যোগ করা
  - [ ] Cloudflare Dashboard-এ KV namespace তৈরি ও wrangler deploy
```

---

## 📊 Verification Plan

### Automated Tests
```bash
# Phase 1 - Frontend build clean
pnpm --filter frontend typecheck

# Phase 2 - RAG injection unit tests
pytest backend/tests/test_auto_rag_injector.py -v

# Phase 3 - Stealth browser integration
pytest backend/tests/test_stealth_browser.py -v

# Phase 4 - Cloudflare worker dry-run
npx wrangler dev infrastructure/cloudflare/enhanced-worker.js
```

### Manual Verification
- Feature 1: ড্যাশবোর্ডে MCP URL paste করে ১ ক্লিকে connect হওয়া যাচাই।
- Feature 2: Agent-কে question করার পর response-এ past memory recall হচ্ছে কিনা log-এ দেখা।
- Feature 3: Primary node URL তুলে নিয়ে failover auto-switch যাচাই।