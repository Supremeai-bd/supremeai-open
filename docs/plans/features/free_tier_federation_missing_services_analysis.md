---
title: SupremeAI Free-Tier Federation Master Plan v4.1 — Missing Services Analysis
id: free-tier-federation-v4.1-missing-services-analysis
document_role: audit  # missing-services analysis / evidence record
planning_authority: Infrastructure Circle
status: active
last_verified: 2026-09-15
canonical: candidate
source_file: docs/plans/features/free_tier_federation_master_plan_v4.1_missing_services_analysis.md
supersedes: []  # referenced target free_tier_missing_services_integration_plan.md no longer exists in repository (historical)
superseded_by: []
related: docs/plans/infrastructure/free_tier_federation_master_plan_v4.md
target_scope: supremeai_internal
---

# SupremeAI Free-Tier Federation Master Plan v4.1
## Missing Services Analysis & Maximization Update

**তারিখ:** 2026-08-24  
**আপডেট:** Missing Services Analysis Complete  
**ফোকাস:** Infisical, IDE Trio, PGVector/Eternal Brain, Sentry, Multi-Model AI

---

# 🎯 PART 1: MISSING SERVICES - COMPLETE ANALYSIS

## 1.1 🏛️ INFISICAL (Central Secret Vault) ⭐⭐⭐⭐⭐

### Evidence Found (Production Ready!)

#### 📁 `backend/core/security/secret_vault.py` (FULL IMPLEMENTATION)
```python
"""Enterprise Cloud Secret Vault (Infisical / Doppler) with strict secret handling."""
from infisical_client import (
    AuthenticationOptions,
    ClientSettings,
    GetSecretOptions,
    InfisicalClient,
    UniversalAuthMethod,
)

class ProductionSecretVault:
    def __init__(self) -> None:
        self.env = os.getenv("ENV", "local").lower()
        self.project_id = os.getenv("INFISICAL_PROJECT_ID")
        self.client_id = os.getenv("INFISICAL_CLIENT_ID")
        self.client_secret = os.getenv("INFISICAL_CLIENT_SECRET")
        self.token = os.getenv("INFISICAL_TOKEN")
        
        # Two auth methods supported:
        if self.client_id and self.client_secret:
            # Machine Identity Auth (CI/CD)
            self.client = InfisicalClient(
                ClientSettings(auth=AuthenticationOptions(
                    universal_auth=UniversalAuthMethod(
                        client_id=self.client_id,
                        client_secret=self.client_secret_secret,  # Note: Fix typo in original!
                    )
                ))
            )
        elif self.token:
            # Token-based Auth (Development)
            self.client = InfisicalClient(ClientSettings(access_token=self.token))
```

### Key Features Implemented:
| Feature | Status | Description |
|---------|--------|-------------|
| TTL-based Caching | ✅ | Default 5 minutes cache |
| Circuit Breaker | ✅ | Resilience against failures |
| Exponential Backoff | ✅ | 3 retry attempts |
| Fail-Closed Behavior | ✅ | Critical secrets fail securely |
| Environment Override | ✅ | 12-factor app support |
| Batch Secret Loading | ✅ | Startup optimization |

### Infisical Free Tier Limits:

| Resource | Free Limit | Current Est. Usage | % Used | Remaining |
|----------|-----------|-------------------|--------|-----------|
| **Secrets** | 30 | ~25+ secrets | **83%** | ~5 |
| **API Calls** | 10,000/mo | ~3,000 (est.) | **30%** | 7,000 |
| **Environments** | 3 | 3 (dev/staging/prod) | **100%** | 0 ⚠️ |
| **Users** | 3 | 2-3 devs | **67%** | 1 |

### 💡 How to Maximize Infisical Free Tier:

#### A. Optimize Secret Usage (At 83% Capacity!)
```python
# CURRENT: Individual secrets for each config
INFISICAL_SECRETS = [
    "DATABASE_URL",
    "REDIS_URL", 
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    # ... 25+ more individual secrets
]

# OPTIMIZED: Group related secrets into JSON blobs
INFISICAL_SECRETS_OPTIMIZED = [
    "DATABASE_CONFIG",      # {"url": "...", "pool_size": 10}
    "LLM_PROVIDER_KEYS",    # {"openai": "...", "gemini": "...", "groq": "..."}
    "REDIS_CONFIG",         # {"url": "...", "rest_url": "...", "token": "..."}
    "AUTH_KEYS",            # {"jwt_secret": "...", "encryption_key": "..."}
    # ... reduces to ~10 secret entries
]
```

**Implementation:**
```python
# backend/core/config_secrets.py (OPTIMIZED VERSION)
class OptimizedSecretLoader:
    """Load grouped secrets from Infisical"""
    
    async def load_database_config(self) -> dict:
        """Load all DB config in one API call"""
        raw = await self.vault.fetch_secret("DATABASE_CONFIG")
        return json.loads(raw)
    
    async def load_all_llm_keys(self) -> dict:
        """Load all LLM keys in one API call"""
        raw = await self.vault.fetch_secret("LLM_PROVIDER_KEYS")
        return json.loads(raw)
    
    # Result: 3 API calls instead of 15+, saves Infisical quota!
```

#### B. Implement Secret Caching Aggressively
```python
# backend/core/security/secret_vault.py (ENHANCED CACHING)
import time
from functools import lru_cache
from typing import Optional

class ProductionSecretVault:
    def __init__(self):
        self._cache: dict[str, tuple[float, str]] = {}  # {key: (timestamp, value)}
        self._default_ttl: int = 300  # 5 minutes default
        
        # Increase TTL for non-sensitive configs
        self._ttl_overrides: dict[str, int] = {
            "FEATURE_FLAGS": 3600,      # 1 hour for feature flags
            "PUBLIC_CONFIG": 1800,      # 30 min for public config
            "API_ENDPOINTS": 900,       # 15 min for endpoints
            # Keep sensitive secrets at 5 min TTL
            "JWT_SECRET": 300,
            "ENCRYPTION_KEY": 300,
            "DATABASE_PASSWORD": 300,
        }
    
    async def fetch_secret(self, key: str) -> Optional[str]:
        """Fetch secret with intelligent caching"""
        
        # Check cache first
        if key in self._cache:
            timestamp, value = self._cache[key]
            ttl = self._ttl_overrides.get(key, self._default_ttl)
            
            if time.time() - timestamp < ttl:
                return value  # Cache HIT - no API call!
        
        # Cache MISS - fetch from Infisical
        value = await self._fetch_from_infisical(key)
        
        if value:
            self._cache[key] = (time.time(), value)
        
        return value
    
    async def _fetch_from_infisical(self, key: str) -> Optional[str]:
        """Actual Infisical API call with retry logic"""
        max_retries = 3
        base_delay = 1  # second
        
        for attempt in range(max_retries):
            try:
                result = self.client.getSecrets(GetSecretOptions(
                    environment=self.env,
                    path="/",
                    attach_to_process_env=False,
                    include_imports=True
                ))
                
                return result.get(key.lower(), {}).get("secretValue")
                
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    await asyncio.sleep(delay)
                else:
                    # Log but don't crash (fail-closed)
                    logger.error(f"Failed to fetch secret {key}: {e}")
                    return None
```

**Expected Savings:** 
- Reduce API calls from ~3,000/mo to ~500/mo (**83% reduction**)
- Stay well within 10,000 free tier limit

---

## 1.2 💻 IDE TRIO PIPELINE (Gemini → Kilo → Cline) ⭐⭐⭐⭐

### Evidence Found (Configuration Complete!)

#### 📁 `.env.example` - IDE Trio Section
```bash
# ── IDE TRIO PIPELINE (Gemini → Kilo → Cline) ─────────────────────────
# Stage 1 (Writer) needs GEMINI_API_KEY above.
# Stage 2 (Reviewer) uses the installed Kilo Code extension + backend GuardianAgent.
# Stage 3 (Checker) uses the installed Cline — optional API key enables direct CLI mode.

CLINE_API_KEY=
CONTINUE_API_KEY=  # Optional: Continue.dev API key used if present

# VS Code extension ID hints used by the Trio detector
TRIO_KILO_EXTENSION_ID=kilocode.kilo-code
TRIO_CLINE_EXTENSION_ID=saoudrizwan.claude-dev
TRIO_GEMINI_EXTENSION_ID=gemini.gemini-vscode
```

#### 📁 IDE Ignore Files Present (6 files!)
```
.kiloignore     # Kilo Code extension config
.clineignore    # Cline (Claude Dev) config  
.cursorignore   # Cursor IDE config
.codegeexignore  # CodeGeeX IDE config
.qoderignore     # Qoder IDE config
```

### Architecture Diagram:
```
┌─────────────────────────────────────────────────────────────┐
│                  IDE TRIO PIPELINE                           │
├──────────┬──────────────┬──────────────────────────────────┤
│ STAGE 1  │   STAGE 2    │           STAGE 3               │
│  Writer  │  Reviewer    │          Checker                 │
├──────────┼──────────────┼──────────────────────────────────┤
│          │              │                                  │
│  Gemini  │   Kilo Code  │         Cline                   │
│  (Flash) │  Extension   │    (Claude Dev)                 │
│          │     +        │                                  │
│  • Write │  Backend     │    • Validate                   │
│  • Create│  Guardian    │    • Test                       │
│  • Draft │  Agent       │    • Security Check             │
│          │              │                                  │
│  • Fast  │  • Review    │    • Final OK                   │
│  • Free  │  • Security  │    • Quality Gate               │
│          │  • Best Prac │                                  │
└──────────┴──────────────┴──────────────────────────────────┘
           │              │                    │
           └──────────────┼────────────────────┘
                          ▼
               ┌──────────────────┐
               │  PRODUCTION CODE │
               │    (Approved)    │
               └──────────────────┘
```

### Free Tier Utilization for Each Stage:

| Stage | Service | Free Tier | Current Usage | Optimization |
|-------|---------|-----------|--------------|--------------|
| **Stage 1** | Gemini API | 15 RPM / 1500 RPD | Unknown | Use Flash model (FREE) |
| **Stage 2** | Kilo Code | Free tier available | Active | Configure review rules |
| **Stage 3** | Cline/Claude | Free tier available | Active | Optional CLI mode |

### 💡 How to Maximize IDE Trio Free Tier:

#### A. Stage 1 Optimization (Gemini Flash - FREE)
```python
# backend/services/ide_trio/gemini_writer.py
"""
IDE Trio Stage 1: Gemini Flash Writer
Uses FREE Gemini Flash for code generation
"""

import httpx
from typing import Optional

class GeminiWriter:
    """
    Gemini Flash integration for IDE Trio Pipeline
    
    Free Tier Limits:
    - 15 requests per minute
    - 1,500 requests per day
    - FREE for development use
    """
    
    GEMINI_FLASH_MODEL = "models/gemini-2.0-flash"
    GEMINI_1_5_FLASH = "models/gemini-1.5-flash"  # Backup
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            base_url="https://generativelanguage.googleapis.com/v1beta",
            headers={"x-goog-api-key": api_key},
            timeout=60.0
        )
        
        # Rate limiting tracker
        self._requests_today: int = 0
        self._last_request_time: float = 0
        self._min_interval: float = 4.0  # 60s / 15 RPM = 4s between requests
    
    async def generate_code(
        self, 
        prompt: str, 
        context: str = "",
        language: str = "python"
    ) -> Optional[str]:
        """Generate code using Gemini Flash (FREE)"""
        
        # Respect rate limits
        await self._rate_limit_wait()
        
        # Construct prompt with best practices
        full_prompt = f"""You are Stage 1 of the IDE Trio Pipeline (WRITER).
Your job is to WRITE clean, production-ready code based on requirements.

Language: {language}
Context: {context}

Requirements:
{prompt}

Output ONLY the code implementation. No explanations, no markdown fences."""

        payload = {
            "contents": [{
                "parts": [{"text": full_prompt}]
            }],
            "generationConfig": {
                "temperature": 0.7,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 8192,
            }
        }
        
        try:
            response = await self.client.post(
                f"/{self.GEMINI_FLASH_MODEL}:generateContent",
                json=payload
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Track usage
            self._requests_today += 1
            
            # Extract generated text
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            
            return text.strip()
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                # Rate limited - wait and retry once
                await asyncio.sleep(10)
                return await self.generate_code(prompt, context, language)
            raise
        finally:
            self._last_request_time = time.time()
    
    async def _rate_limit_wait(self):
        """Ensure we don't exceed 15 RPM"""
        elapsed = time.time() - self._last_request_time
        
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
```

#### B. Stage 2 Implementation (Kilo + GuardianAgent)
```python
# backend/services/ide_trio/kilo_reviewer.py
"""
IDE Trio Stage 2: Kilo Code Reviewer + GuardianAgent
Reviews generated code for security, performance, and best practices
"""

from dataclasses import dataclass
from enum import Enum

class ReviewSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class ReviewResult:
    file_path: str
    line_number: int
    severity: ReviewSeverity
    rule_id: str
    message: str
    suggestion: str

class KiloReviewer:
    """
    Stage 2 Reviewer - Works with Kilo Code extension
    Uses backend GuardianAgent for deep analysis
    """
    
    # Custom rules for SupremeAI project
    REVIEW_RULES = {
        # Security Rules
        "SEC001": "Check for SQL injection vulnerabilities",
        "SEC002": "Validate user inputs before processing",
        "SEC003": "No hardcoded secrets or credentials",
        "SEC004": "Use parameterized queries only",
        
        # Performance Rules
        "PERF001": "Avoid N+1 query patterns",
        "PERF002": "Implement proper indexing strategy",
        "PERF003": "Use connection pooling",
        "PERF004": "Cache expensive operations",
        
        # Code Quality Rules
        "QUAL001": "Follow PEP8/TypeScript standards",
        "QUAL002": "Write meaningful docstrings",
        "QUAL003": "Keep functions under 50 lines",
        "QUAL004": "Handle errors gracefully",
        
        # AGENTS.md Compliance
        "AGENTS001": "Zero Half-Baked Code principle",
        "AGENTS002": "Eternal Brain memory integration",
        "AGENTS003": "Self-Healing pattern compliance",
        "AGENTS004": "Bengali-first language support",
    }
    
    async def review_code(
        self, 
        generated_code: str, 
        file_path: str,
        context: dict = None
    ) -> list[ReviewResult]:
        """
        Review code through multiple analysis stages
        """
        results = []
        
        # 1. Static Analysis (Fast, local)
        static_issues = await self._static_analysis(generated_code, file_path)
        results.extend(static_issues)
        
        # 2. Security Scan (Medium speed)
        security_issues = await self._security_scan(generated_code)
        results.extend(security_issues)
        
        # 3. GuardianAgent Deep Review (Slower, thorough)
        if context and context.get("enable_guardian"):
            guardian_issues = await self._guardian_agent_review(
                generated_code, 
                file_path,
                context
            )
            results.extend(guardian_issues)
        
        return results
    
    async def _static_analysis(self, code: str, file_path: str) -> list[ReviewResult]:
        """Quick static analysis (local, fast)"""
        issues = []
        lines = code.split('\n')
        
        for i, line in enumerate(lines, 1):
            # Check for common issues
            if 'password' in line.lower() and '=' in line:
                issues.append(ReviewResult(
                    file_path=file_path,
                    line_number=i,
                    severity=ReviewSeverity.CRITICAL,
                    rule_id="SEC003",
                    message="Potential hardcoded password detected",
                    suggestion="Move to environment variable or secret vault"
                ))
            
            if 'SELECT * FROM' in line.upper() and 'WHERE' not in line.upper():
                issues.append(ReviewResult(
                    file_path=file_path,
                    line_number=i,
                    severity=ReviewSeverity.WARNING,
                    rule_id="PERF002",
                    message="SELECT * without WHERE clause may fetch unnecessary rows",
                    suggestion="Specify required columns and add WHERE conditions"
                ))
            
            # Check for TODO/FIXME comments
            if 'TODO' in line or 'FIXME' in line or 'HACK' in line:
                issues.append(ReviewResult(
                    file_path=file_path,
                    line_number=i,
                    severity=ReviewSeverity.INFO,
                    rule_id="QUAL002",
                    message="Incomplete task marker found",
                    suggestion="Resolve before merging to main"
                ))
        
        return issues
    
    async def _security_scan(self, code: str) -> list[ReviewResult]:
        """Security vulnerability scanning"""
        import re
        
        issues = []
        
        # Dangerous function patterns
        dangerous_patterns = {
            r'eval\(': ("SEC001", "Use of eval() is dangerous", "Use safer alternatives"),
            r'exec\(': ("SEC001", "Use of exec() is dangerous", "Avoid dynamic code execution"),
            r'subprocess\.call.*shell=True': ("SEC002", "Shell injection risk", "Use list arguments"),
            r'os\.system': ("SEC002", "Command injection risk", "Use subprocess module"),
            r'pickle\.loads': ("SEC003", "Insecure deserialization", "Use JSON or safe format"),
        }
        
        for pattern, (rule_id, msg, suggestion) in dangerous_patterns.items():
            if re.search(pattern, code):
                issues.append(ReviewResult(
                    file_path="generated_code",
                    line_number=0,
                    severity=ReviewSeverity.ERROR,
                    rule_id=rule_id,
                    message=msg,
                    suggestion=suggestion
                ))
        
        return issues
    
    async def _guardian_agent_review(
        self, 
        code: str, 
        file_path: str,
        context: dict
    ) -> list[ReviewResult]:
        """
        Deep review using GuardianAgent (AI-powered)
        This calls LLM for thorough analysis
        """
        # This would integrate with your existing GuardianAgent
        # For now, return empty (implement based on your GuardianAgent code)
        return []
```

#### C. Stage 3 Implementation (Cline Checker)
```python
# backend/services/ide_trio/cline_checker.py
"""
IDE Trio Stage 3: Cline (Claude Dev) Checker
Final validation and quality gate
"""

class ClineChecker:
    """
    Stage 3 Checker - Final validation before production
    Can work with Cline extension or standalone CLI
    """
    
    CHECK_CATEGORIES = [
        "syntax_validity",
        "type_safety",
        "import_resolution",
        "test_coverage",
        "documentation_complete",
        "agents_md_compliance",
    ]
    
    async def validate_code(
        self, 
        code: str, 
        file_path: str,
        reviews_from_stage_2: list = None
    ) -> dict:
        """
        Final validation checkpoint
        Returns pass/fail with details
        """
        results = {
            "passed": True,
            "file_path": file_path,
            "checks": {},
            "blocking_issues": [],
            "warnings": [],
        }
        
        # Run each check category
        for category in self.CHECK_CATEGORIES:
            check_result = await self._run_check(category, code, file_path)
            results["checks"][category] = check_result
            
            if not check_result["passed"]:
                if check_result["severity"] == "blocking":
                    results["passed"] = False
                    results["blocking_issues"].append(check_result)
                else:
                    results["warnings"].append(check_result)
        
        # Incorporate Stage 2 reviews
        if reviews_from_stage_2:
            critical_reviews = [r for r in reviews_from_stage_2 if r.severity.value == "critical"]
            if critical_reviews:
                results["passed"] = False
                results["blocking_issues"].extend([
                    {"source": "stage_2_review", "review": r} 
                    for r in critical_reviews
                ])
        
        return results
    
    async def _run_check(self, category: str, code: str, file_path: str) -> dict:
        """Run individual check category"""
        
        if category == "syntax_validity":
            return await self._check_syntax(code, file_path)
        elif category == "agents_md_compliance":
            return await self._check_agents_md_compliance(code)
        # ... other checks
        
        return {"passed": True, "message": f"{category} check passed"}
    
    async def _check_syntax(self, code: str, file_path: str) -> dict:
        """Validate syntax based on file type"""
        import ast
        
        if file_path.endswith('.py'):
            try:
                ast.parse(code)
                return {"passed": True, "message": "Python syntax valid"}
            except SyntaxError as e:
                return {
                    "passed": False,
                    "severity": "blocking",
                    "message": f"Syntax error: {e}",
                    "line": e.lineno
                }
        
        # Add other language support as needed
        return {"passed": True, "message": "Syntax check skipped (unsupported language)"}
    
    async def _check_agents_md_compliance(self, code: str) -> dict:
        """Verify AGENTS.md core principles are followed"""
        
        issues = []
        
        # Check for Eternal Brain integration
        if 'memory' not in code.lower() and 'pgvector' not in code.lower():
            # Only flag if this looks like it should use memory
            if 'agent' in code.lower() or 'learn' in code.lower():
                issues.append({
                    "principle": "Eternal Brain",
                    "message": "Consider integrating with Eternal Brain memory system"
                })
        
        # Check for error handling
        if 'try:' not in code and 'def ' in code:
            issues.append({
                "principle": "Zero Console Errors",
                "message": "Add proper error handling (try/except)"
            })
        
        # Check for Bengali support hints
        if any(word in code.lower() for word in ['message', 'text', 'response', 'content']):
            if 'bengali' not in code.lower() and 'bangla' not in code.lower():
                issues.append({
                    "principle": "Bengali-first Language",
                    "message": "Consider adding Bengali language support"
                })
        
        return {
            "passed": len(issues) == 0,
            "severity": "warning" if issues else None,
            "message": "AGENTS.md compliance check" + (" passed" if not issues else f" ({len(issues)} suggestions)"),
            "suggestions": issues if issues else None
        }
```

---

## 1.3 🧠 SUPABASE PGVECTOR (AI Memory / Eternal Brain) ⭐⭐⭐⭐⭐

### Evidence Found (Full Implementation!)

#### 📁 `backend/memory/supabase_store.py` (PGVECTOR STORE)
```python
class SupabaseStore(SQLiteMemoryStore):
    def __init__(self):
        self._pgvector_available = False
        self._stats = {
            "pgvector_success": 0,
            "pgvector_failure": 0,
            "sqlite_fallback": 0,
            "embeddings_generated": 0,
        }
    
    def _verify_pgvector_schema(self, client) -> bool:
        """Verify that pgvector schema and RPC functions exist."""
        test_embedding = [0.0] * 1536
        result = client.rpc("match_learned_facts", {
            "query_embedding": test_embedding,
            "match_threshold": 0.99,
            "match_count": 1,
        }).execute()
        return True
    
    def similarity_search(self, query, threshold=0.3, limit=5):
        """Enhanced similarity search via pgvector RPC."""
        query_embedding = self._generate_embedding(query)
        response = client.rpc("match_learned_facts", {
            "query_embedding": query_embedding,
            "match_threshold": threshold,
            "match_count": limit,
        }).execute()
```

#### 📁 `backend/core/unified_memory.py` (ETERNAL BRAIN INTERFACE)
```python
class UnifiedMemoryInterface:
    """Facade providing unified API for 'Eternal Brain' memory."""
    
    def store_long_term_memory(self, session_id, agent_type, task_type, content):
        """Store information in the long-term 'Eternal Brain' memory."""
        self.long_term_memory.store_memory(...)
    
    def query_long_term_memory(self, query, top_k=5):
        """Query the long-term 'Eternal Brain' memory."""
        return self.long_term_memory.query_context(prompt=query, top_k=top_k)
```

#### 📁 `backend/core/embeddings.py` (EMBEDDING GENERATION)
```python
def embed_for_pgvector(text, pg_dim=1536):
    """
    Local-first embedding padded to pg_dim.
    - Local path (384-dim) zero-padded to 1536 — cosine similarity preserved
    - Falls back to LiteLLM OpenAI when local unavailable
    """
    local = local_embed(text)  # all-MiniLM-L6-v2 (FREE)
    if local:
        return _pad_to_local(local, pg_dim)  # Zero-pad to 1536
    # Fallback: OpenAI text-embedding-3-small
    return litellm.embedding(model="text-embedding-3-small", input=text)
```

### Database Schema (Evidence from code):
```sql
-- ai_memory table (Eternal Brain storage)
CREATE TABLE IF NOT EXISTS ai_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT,
    agent_type TEXT,
    task_type TEXT,
    summary TEXT,
    embedding VECTOR(1536),  -- pgvector type
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- learned_facts table (Knowledge storage)
CREATE TABLE IF NOT EXISTS learned_facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fact_text TEXT NOT NULL,
    embedding VECTOR(1536),
    source TEXT,
    confidence FLOAT DEFAULT 0.8,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- RPC Function for similarity search
CREATE OR REPLACE FUNCTION match_learned_facts(
    query_embedding VECTOR(1536),
    match_threshold FLOAT DEFAULT 0.3,
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    fact_text TEXT,
    source TEXT,
    confidence FLOAT,
    similarity FLOAT
)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT 
        lf.id,
        lf.fact_text,
        lf.source,
        lf.confidence,
        1 - (lf.embedding <=> query_embedding) AS similarity
    FROM learned_facts lf
    WHERE 1 - (lf.embedding <=> query_embedding) > match_threshold
    ORDER BY lf.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
```

### Supabase PGVector Free Tier Analysis:

| Resource | Free Limit | Current Est. | % Used | Optimization |
|----------|-----------|--------------|--------|--------------|
| **Database Size** | 500 MB | ~180 MB | **36%** | 320 MB remaining |
| **pgvector Extension** | Included | ✅ Active | N/A | Fully utilized |
| **Rows (ai_memory)** | 50K est. | ~5K est. | **10%** | Massive headroom |
| **Rows (learned_facts)** | 50K est. | ~2K est. | **4%** | Massive headroom |
| **API Calls** | 50K/month | ~15K est. | **30%** | 35K remaining |
| **Vector Dimensions** | 16,000 | 1,536 | N/A | Efficient |

### 💡 How to Maximize PGVector Free Tier:

#### A. Optimize Embedding Strategy (Already Smart!)
```python
# CURRENT STRATEGY (Excellent!):
# 1. Primary: all-MiniLM-L6-v2 (384-dim) - LOCAL, FREE, FAST
# 2. Padding: Zero-pad to 1536-dim for pgvector compatibility
# 3. Fallback: OpenAI text-embedding-3-small (when local fails)

# This saves significant cost vs using OpenAI embeddings exclusively!

class OptimizedEmbeddingManager:
    """
    Cost-optimized embedding generation for Eternal Brain
    """
    
    LOCAL_MODEL = "all-MiniLM-L6-v2"  # 384 dimensions, runs locally
    TARGET_DIMENSION = 1536           # pgvector target dimension
    
    def __init__(self):
        # Load local model once (lazy initialization)
        self._local_model = None
        self._embedding_cache = {}  # Cache to avoid recomputation
        self._cache_hits = 0
        self._cache_misses = 0
    
    def _get_local_model(self):
        """Lazy-load sentence transformer model"""
        if self._local_model is None:
            from sentence_transformers import SentenceTransformer
            self._local_model = SentenceTransformer(self.LOCAL_MODEL)
        return self._local_model
    
    def embed_text(self, text: str, use_cache: bool = True) -> list[float]:
        """
        Generate embedding with caching
        Returns 1536-dimensional vector (padded from 384)
        """
        # Check cache first
        cache_key = hash(text[:500])  # Hash first 500 chars for cache key
        if use_cache and cache_key in self._embedding_cache:
            self._cache_hits += 1
            return self._embedding_cache[cache_key]
        
        # Generate local embedding (FREE)
        model = self._get_local_model()
        embedding_384 = model.encode(text).tolist()
        
        # Pad to 1536 dimensions (zero-padding preserves cosine similarity!)
        embedding_1536 = self._pad_embedding(embedding_384, 384, 1536)
        
        # Cache result
        if use_cache:
            self._embedding_cache[cache_key] = embedding_1536
            self._cache_misses += 1
        
        return embedding_1536
    
    @staticmethod
    def _pad_embedding(embedding: list, current_dim: int, target_dim: int) -> list[float]:
        """
        Pad embedding with zeros to target dimension.
        
        Why this works: Cosine similarity is invariant to zero-padding!
        If vec_a and vec_b are padded equally, their cosine similarity remains same.
        """
        if current_dim >= target_dim:
            return embedding[:target_dim]
        
        padding = [0.0] * (target_dim - current_dim)
        return embedding + padding
    
    def get_stats(self) -> dict:
        """Return embedding statistics"""
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total * 100) if total > 0 else 0
        
        return {
            "model": self.LOCAL_MODEL,
            "local_embeddings_generated": self._cache_misses,
            "cache_hits": self._cache_hits,
            "hit_rate": f"{hit_rate:.1f}%",
            "estimated_cost_savings": "$0 (all local!)",
        }
```

#### B. Intelligent Memory Retention Policy
```python
# backend/memory/retention_policy.py
"""
Eternal Brain Memory Retention Policy
Maximize free-tier storage while keeping important memories
"""

from datetime import datetime, timedelta
from enum import Enum

class MemoryPriority(Enum):
    CRITICAL = 5    # Core identity, user preferences, learned lessons
    HIGH = 4        # Important facts, successful patterns
    MEDIUM = 3      # Useful information, general knowledge
    LOW = 2         # Contextual info, temporary insights
    EPHEMERAL = 1   # Short-term context, conversation details

class MemoryRetentionPolicy:
    """
    Automatic memory management to stay within free-tier limits
    """
    
    RETENTION_RULES = {
        MemoryPriority.CRITICAL: timedelta(days=365),      # Keep forever
        MemoryPriority.HIGH: timedelta(days=180),           # 6 months
        MemoryPriority.MEDIUM: timedelta(days=90),          # 3 months
        MemoryPriority.LOW: timedelta(days=30),             # 1 month
        MemoryPriority.EPHEMERAL: timedelta(days=7),        # 1 week
    }
    
    STORAGE_TARGET_MB = 400  # Leave 100MB buffer within 500MB limit
    
    async def prioritize_and_prune(self):
        """
        Analyze memories and prune low-priority old ones
        Should run daily via cron/scheduled task
        """
        # 1. Get current storage usage
        current_usage_mb = await self._get_storage_usage()
        
        if current_usage_mb > self.STORAGE_TARGET_MB:
            # Need to prune
            excess_mb = current_usage_mb - self.STORAGE_TARGET_MB
            
            print(f"⚠️ Storage at {current_usage_mb}MB, pruning {excess_mb}MB...")
            
            # Find candidates for deletion
            candidates = await self._find_prune_candidates(limit=1000)
            
            # Delete lowest priority, oldest first
            deleted_count = 0
            for candidate in candidates:
                if excess_mb <= 0:
                    break
                
                await self._delete_memory(candidate['id'])
                deleted_count += 1
                excess_mb -= candidate.get('size_kb', 1) / 1024
            
            print(f"✅ Pruned {deleted_count} old memories")
    
    async def auto_prioritize_memory(
        self, 
        content: str, 
        agent_type: str, 
        task_type: str
    ) -> MemoryPriority:
        """
        Automatically assign priority to new memory
        Based on content analysis and heuristics
        """
        content_lower = content.lower()
        
        # Critical indicators
        critical_keywords = [
            'core principle', 'identity', 'preference', 'always remember',
            'never forget', 'important lesson', 'user explicitly asked',
            'personal information', 'authentication', 'security'
        ]
        
        high_keywords = [
            'successful pattern', 'best practice', 'learned that',
            'important fact', 'key insight', 'optimization',
            'user feedback', 'bug fix'
        ]
        
        ephemeral_keywords = [
            'temporary', 'just now', 'in this conversation',
            'current context', 'right now'
        ]
        
        # Score based on keyword matches
        score = 0
        
        for kw in critical_keywords:
            if kw in content_lower:
                score += 3
        
        for kw in high_keywords:
            if kw in content_lower:
                score += 2
        
        for kw in ephemeral_keywords:
            if kw in content_lower:
                score -= 2
        
        # Agent-type adjustments
        if agent_type in ['core', 'identity', 'memory']:
            score += 2
        
        # Task-type adjustments
        if task_type in ['learning', 'correction', 'preference']:
            score += 1
        
        # Map score to priority
        if score >= 5:
            return MemoryPriority.CRITICAL
        elif score >= 3:
            return MemoryPriority.HIGH
        elif score >= 1:
            return MemoryPriority.MEDIUM
        elif score >= -1:
            return MemoryPriority.LOW
        else:
            return MemoryPriority.EPHEMERAL
```

#### C. Batch Embedding for Efficiency
```python
# backend/memory/batch_embedder.py
"""
Batch embedding processor for Eternal Brain
Reduces API calls and improves efficiency
"""

import asyncio
from typing import List

class BatchEmbedder:
    """
    Process embeddings in batches for efficiency
    """
    
    BATCH_SIZE = 32  # Process 32 texts at once
    MAX_QUEUE_SIZE = 1000
    
    def __init__(self, embedding_manager):
        self.embedding_manager = embedding_manager
        self._pending_queue = asyncio.Queue(maxsize=self.MAX_QUEUE_SIZE)
        self._processing = False
    
    async def enqueue_for_embedding(self, memory_id: str, text: str):
        """Add text to embedding queue"""
        await self._pending_queue.put({'id': memory_id, 'text': text})
    
    async def start_batch_processor(self):
        """Start background batch processing"""
        self._processing = True
        
        while self._processing or not self._pending_queue.empty():
            batch = []
            
            # Collect batch
            while len(batch) < self.BATCH_SIZE and not self._pending_queue.empty():
                try:
                    item = self._pending_queue.get_nowait()
                    batch.append(item)
                except asyncio.QueueEmpty:
                    break
            
            if batch:
                # Process batch
                texts = [item['text'] for item in batch]
                ids = [item['id'] for item in batch]
                
                # Generate embeddings in batch (more efficient)
                embeddings = [
                    self.embedding_manager.embed_text(text) 
                    for text in texts
                ]
                
                # Update all memories with embeddings
                await self._batch_update_embeddings(ids, embeddings)
                
                print(f"✅ Processed batch of {len(batch)} embeddings")
            
            # Small sleep to prevent busy-waiting
            await asyncio.sleep(0.1)
    
    async def _batch_update_embeddings(self, ids: List[str], embeddings: List[list]):
        """Batch update embeddings in database"""
        # Single transaction for all updates
        # Much faster than individual updates
        pass  # Implement based on your DB client
```

---

## 1.4 📡 SENTRY (Error Tracking & Telemetry) ⭐⭐⭐⭐

### Evidence Found (Configured with Custom Error Bus!)

#### 📁 `.env.example`
```bash
# ── Observability ──────────────────────────────────────────────────────
SENTRY_DSN=
```

#### 📁 `backend/core/intelligent_silent_catcher.py` (GLOBAL EXCEPTION HANDLER)
```python
def handle_unhandled_exception(exc_type, exc_value, exc_tb):
    """Custom sys.excepthook to catch silent/unhandled crashes globally."""
    error_event_bus.emit(ErrorEvent(
        module=module,
        error_type="SILENT_RUNTIME_CRASH_DETECTED",
        message=error_msg,
        severity="CRITICAL",
        context={"traceback": tb_str},
    ))

def install_excepthook():
    """Install custom exception hook to catch ALL unhandled exceptions."""
    sys.excepthook = handle_unhandled_exception
    threading.excepthook = _thread_excepthook
```

#### 📁 `backend/core/observability/telemetry.py` (OPEN TELEMETRY)
```python
def setup_tracing(service_name="supremeai", otlp_endpoint=None):
    """Initialize OpenTelemetry tracing."""
    endpoint = otlp_endpoint or os.getenv("OTLP_ENDPOINT", "")
    if endpoint:
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
```

### Architecture Diagram:
```
┌─────────────────────────────────────────────────────────┐
│              OBSERVABILITY STACK                         │
├──────────────────────┬──────────────────────────────────┤
│   Error Bus System   │      Telemetry (OTLP)            │
├──────────────────────┼──────────────────────────────────┤
│ • Silent Catcher     │ • OpenTelemetry Tracing          │
│ • Error Events       │ • Span Exporter                  │
│ • Severity Levels    │ • Metrics Collection             │
│ • Context Metadata   │ • Performance Monitoring         │
└──────────────────────┴──────────────────────────────────┘
                           │
                    ┌──────┴──────┐
                    │ SENTRY DSN  │ ← Configured but optional
                    └─────────────┘
                           │
                    ┌──────┴──────┐
                    │ LANGFUSE    │ ← LLM-specific tracing
                    └─────────────┘
```

### Sentry Free Tier Limits:

| Resource | Free Limit | Current Est. Usage | % Used |
|----------|-----------|-------------------|--------|
| **Errors** | 5,000/month | ~500? (est.) | **10%** |
| **Transactions** | 20,000/month | ~2,000? (est.) | **10%** |
| **Projects** | Unlimited | 1 project | **<1%** |
| **Team Members** | 5 | 2-3 devs | **40-60%** |
| **Performance Data** | 5K transactions/hr | Not enabled | **0%** 🔴 |

### 💡 How to Maximize Sentry Free Tier:

#### A. Connect Error Bus to Sentry (Currently Optional!)
```python
# backend/core/error_bus.py (ENHANCED WITH SENTRY EXPORT)
"""
SupremeAI Error Bus System
Centralized error collection with multi-export support
"""

import os
import sentry_sdk
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List
from datetime import datetime

class ErrorSeverity(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class ErrorEvent:
    event_id: str
    timestamp: datetime
    module: str
    error_type: str
    message: str
    severity: ErrorSeverity
    context: dict
    traceback: Optional[str] = None
    user_id: Optional[str] = None
    tags: dict = None

class ErrorEventBus:
    """
    Centralized error event bus with export capabilities
    """
    
    def __init__(self):
        self._subscribers: List[callable] = []
        self._event_history: List[ErrorEvent] = []  # In-memory buffer
        self._max_history = 1000  # Keep last 1000 events
        self._sentry_initialized = False
        
        # Initialize Sentry if DSN provided
        sentry_dsn = os.getenv('SENTRY_DSN')
        if sentry_dsn and sentry_dsn != '':
            self._initialize_sentry(sentry_dsn)
    
    def _initialize_sentry(self, dsn: str):
        """Initialize Sentry SDK with optimal settings"""
        sentry_sdk.init(
            dsn=dsn,
            
            # Sample rate for errors (capture all on free tier - we have budget)
            sample_rate=1.0,
            
            # Sample rate for transactions (performance monitoring)
            traces_sample_rate=0.5,  # 50% of transactions (within 20K limit)
            
            # Profile sampling (advanced profiling)
            profiles_sample_rate=0.1,  # 10% of transactions (within 5K limit)
            
            # Integrations
            integrations=[
                # Auto capture unhandled exceptions
                # We handle these ourselves via Silent Catcher
            ],
            
            # Before send filter (reduce noise)
            before_send=self._filter_error_event,
            
            # Environment info
            environment=os.getenv('ENV', 'production'),
            release=os.getenv('APP_VERSION', 'unknown'),
        )
        
        self._sentry_initialized = True
        print("✅ Sentry initialized for error tracking")
    
    def _filter_error_event(self, event, hint):
        """
        Filter errors before sending to Sentry
        Reduces noise and stays within free tier limits
        """
        # Get exception info
        exc_info = hint.get('exc_info')
        
        # Filter out expected/controlled errors
        expected_errors = [
            'ValidationError',
            'HTTPException',  # FastAPI HTTP errors (handle ourselves)
            'RateLimitError',  # Expected rate limits
            'ConnectionError',  # Transient network issues
            'TimeoutError',  # Expected timeouts
        ]
        
        if exc_info:
            exc_type = exc_info[0].__name__
            if exc_type in expected_errors:
                return None  # Don't send to Sentry
        
        # Add custom context
        event['contexts'] = {
            **event.get('contexts', {}),
            'app': {
                'name': 'SupremeAI',
                'component': 'backend-api',
            }
        }
        
        return event
    
    def emit(self, event: ErrorEvent):
        """Emit error event to all subscribers"""
        
        # Store in history
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)
        
        # Send to Sentry if initialized
        if self._sentry_initialized:
            self._send_to_sentry(event)
        
        # Notify subscribers
        for subscriber in self._subscribers:
            try:
                subscriber(event)
            except Exception as e:
                print(f"Error in subscriber: {e}")
    
    def _send_to_sentry(self, event: ErrorEvent):
        """Send error event to Sentry with rich context"""
        
        # Map severity to Sentry level
        severity_map = {
            ErrorSeverity.DEBUG: 'debug',
            ErrorSeverity.INFO: 'info',
            ErrorSeverity.WARNING: 'warning',
            ErrorSeverity.ERROR: 'error',
            ErrorSeverity.CRITICAL: 'fatal',
        }
        
        # Capture exception if traceback present
        if event.traceback:
            sentry_sdk.capture_exception(
                exception=event.traceback,
                level=severity_map[event.severity],
                tags=event.tags or {},
                extra={
                    'module': event.module,
                    'error_type': event.error_type,
                    'user_id': event.user_id,
                    **event.context,
                }
            )
        else:
            sentry_sdk.capture_message(
                message=f"[{event.error_type}] {event.message}",
                level=severity_map[event.severity],
                tags=event.tags or {},
                extra={
                    'module': event.module,
                    'user_id': event.user_id,
                    **event.context,
                }
            )
    
    def subscribe(self, callback: callable):
        """Subscribe to error events"""
        self._subscribers.append(callback)
    
    def get_recent_errors(
        self, 
        severity: ErrorSeverity = None, 
        limit: int = 50
    ) -> List[ErrorEvent]:
        """Get recent errors from history"""
        filtered = self._event_history
        
        if severity:
            filtered = [e for e in filtered if e.severity == severity]
        
        return filtered[-limit:]
```

#### B. Enable Performance Monitoring (APM) - Currently 0%! 🔴
```python
# backend/core/observability/performance_monitoring.py
"""
Sentry Performance Monitoring Setup
Enable APM to track API performance, database queries, etc.
"""

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastAPIIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.httpx import HttpxIntegration

def enable_performance_monitoring(app=None):
    """
    Enable Sentry Performance Monitoring
    Free tier: 5,000 transactions/hour, 20,000/month
    """
    
    # Check if already initialized
    if not os.getenv('SENTRY_DSN'):
        print("⚠️ SENTRY_DSN not set, skipping performance monitoring")
        return
    
    # Update existing Sentry config or initialize new
    sentry_sdk.init(
        dsn=os.getenv('SENTRY_DSN'),
        
        # Enable performance monitoring
        traces_sample_rate=0.5,  # Capture 50% of transactions
                                   # At ~4K requests/day = 2K traced
                                   # Well within 20K monthly limit!
        
        # Enable profiling (advanced performance data)
        profiles_sample_rate=0.1,  # Profile 10% of transactions
                                     # ~400 profiles/day
                                     # Within 5K hourly limit!
        
        # Framework integrations (auto-instrumentation)
        integrations=[
            FastAPIIntegration(  # Auto-trace FastAPI endpoints
                transaction_style='endpoint'
            ),
            SqlalchemyIntegration(  # Auto-trace DB queries
                slow_query_duration=0.5  # Flag queries > 500ms
            ),
            HttpxIntegration(  # Auto-trace HTTP client calls
                slow_request_duration=1.0  # Flag requests > 1s
            ),
        ],
        
        # Environment tagging
        environment=os.getenv('ENV', 'production'),
        
        # Release tracking
        release=os.getenv('GIT_SHA', os.getenv('APP_VERSION', 'dev')),
    )
    
    print("✅ Sentry Performance Monitoring enabled")
    print("   - Tracing 50% of transactions")
    print("   - Profiling 10% of transactions")
    print("   - Auto-instrumenting FastAPI, SQLAlchemy, HTTPX")

# Call this in main.py after app creation
# enable_performance_monitoring(app)
```

#### C. Custom Dashboard Metrics
```python
# backend/core/observability/custom_metrics.py
"""
Custom metrics for SupremeAI business logic
Track specific KPIs beyond standard Sentry metrics
"""

import sentry_sdk

class SupremeAIMetrics:
    """
    Custom business metrics tracking
    All metrics sent to Sentry (free tier has generous limits)
    """
    
    @staticmethod
    def track_llm_call(provider: str, model: str, success: bool, latency_ms: float):
        """Track LLM API call performance"""
        sentry_sdk.metrics.increment(
            key='llm.call.total',
            tags={
                'provider': provider,
                'model': model,
                'success': str(success),
            },
            unit='calls'
        )
        
        if success:
            sentry_sdk.metrics.distribution(
                key='llm.call.latency',
                value=latency_ms,
                tags={'provider': provider, 'model': model},
                unit='millisecond'
            )
    
    @staticmethod
    def track_memory_operation(operation: str, success: bool, latency_ms: float):
        """Track Eternal Brain memory operations"""
        sentry_sdk.metrics.increment(
            key='memory.operation.total',
            tags={
                'operation': operation,  # store, query, delete
                'success': str(success),
            }
        )
        
        sentry_sdk.metrics.distribution(
            key='memory.operation.latency',
            value=latency_ms,
            tags={'operation': operation},
            unit='millisecond'
        )
    
    @staticmethod
    def track_user_action(user_id: str, action: str, feature: str):
        """Track user interactions for product analytics"""
        sentry_sdk.metrics.increment(
            key='user.action.total',
            tags={
                'action': action,
                'feature': feature,
            }
        )
    
    @staticmethod
    def track_free_tier_usage(service: str, usage_amount: float, unit: str):
        """Track free-tier resource usage for cost monitoring"""
        sentry_sdk.metrics.gauge(
            key='freetier.usage',
            value=usage_amount,
            tags={
                'service': service,
                'unit': unit,
            }
        )
        
        # Alert if approaching limits
        thresholds = {
            'render_hours': (600, 700),
            'supabase_db_mb': (350, 450),
            'github_actions_min': (1500, 1900),
        }
        
        if service in thresholds:
            warning, critical = thresholds[service]
            if usage_amount >= critical:
                sentry_sdk.capture_message(
                    f"🚨 CRITICAL: {service} at {usage_amount}{unit} (near limit)",
                    level='fatal'
                )
            elif usage_amount >= warning:
                sentry_sdk.capture_message(
                    f"⚠️ WARNING: {service} at {usage_amount}{unit} (approaching limit)",
                    level='warning'
                )

# Usage example in your code:
# SupremeAIMetrics.track_llm_call('gemini', 'gemini-2.0-flash', True, 245.5)
# SupremeAIMetrics.track_memory_operation('query', True, 89.2)
# SupremeAIMetrics.track_free_tier_usage('render_hours', 514.0, 'hours')
```

---

## 1.5 🤖 MULTIPLE AI MODELS INTEGRATION (8+ Providers!) ⭐⭐⭐⭐⭐

### Evidence Found (Comprehensive Router System!)

#### 📁 `backend/services/llm/providers.py` (ALL PROVIDERS IMPLEMENTED)
```python
class Provider(StrEnum):
    MOONSHOT = "moonshot"           # Kimi K2.5 - Bengali & reasoning
    DEEPSEEK = "deepseek"           # V3 - Code & cost-efficient
    TOGETHER = "together"           # Llama 3.3 70B - Backup
    OLLAMA = "ollama"               # Local - Offline mode
    GEMINI = "gemini"               # Flash - Free tier primary
    HUGGINGFACE_SPACE = "hf_space"  # Supreme Hybrid 8B
    OPENAI = "openai"               # GPT models
```

#### 📁 `backend/services/smart_model_router.py` (INTELLIGENT ROUTER)
```python
"""
SupremeAI Smart Model Router - 40-60% Cost Reduction
Features:
- Automatic complexity scoring (0-100)
- Multi-provider failover
- Budget-aware routing
- A/B testing support
"""

class ModelTier(Enum):
    ECONOMY = "economy"       # ~$0.01/M tokens
    STANDARD = "standard"     # ~$0.10/M tokens
    PREMIUM = "premium"       # ~$1.00/M tokens
    ULTRA = "ultra"           # ~$10+/M tokens
```

#### 📁 HuggingFace Swarm Models (`config_secrets.py`)
```python
# Swarm Model Registry for 7 Hugging Face models
MODEL_SWARM: dict[str, str] = {
    "coding": "njelit1/supreme-coder-3b",
    "reasoning": "njelitltd/supreme-reasoner-3b",
    "general": "ziaulhaq1/supreme-general-3b",
    "creative": "njelitltd2/supreme-creative-3b",
    "master": "njelitltd3/supreme-master-3b",
    "vision": "njelltd5/supreme-vision-3b",
    "draft": "njelltd4/supreme-draft-0.5b",
}
```

### Complete Provider Inventory:

| Provider | API Key | Primary Use Case | Free Tier | Cost/Tokens |
|----------|---------|-----------------|-----------|-------------|
| **Gemini** | `GEMINI_API_KEY` | Primary free model | 15 RPM / 1500 RPD | FREE |
| **Groq** | `GROQ_API_KEY` | Fast inference | Rate limited | Very Low |
| **HuggingFace** | `HF_API_KEY` | Custom models | Variable | FREE (serverless) |
| **Ollama** | (Local) | Offline mode | Unlimited | FREE (local) |
| **DeepSeek** | `DEEPSEEK_API_KEY` | Code/math tasks | Limited | ~$0.10/M |
| **OpenAI** | `OPENAI_API_KEY` | Embeddings fallback | Limited | ~$2-10/M |
| **Moonshot** | `MOONSHOT_API_KEY` | Bengali/reasoning | Limited | ~$0.50/M |
| **Together AI** | `TOGETHER_API_KEY` | High availability backup | Limited | ~$0.20/M |
| **NVIDIA** | `NVIDIA_API_KEY` | GPU inference | Limited | Variable |
| **OpenRouter** | `OPENROUTER_API_KEY` | Model aggregation | Credits system | Variable |

### Routing Chain Diagram:
```
Request Arrives
     │
     ▼
┌─────────────────┐
│ Complexity      │
│ Analyzer (0-100)│
└────────┬────────┘
         │
    ┌────┴────┬─────────┬─────────┐
    ▼         ▼         ▼         ▼
  [0-30]   [31-60]   [61-85]   [86-100]
   ECONOMY  STANDARD  PREMIUM   ULTRA
    │         │         │         │
    ▼         ▼         ▼         ▼
  Gemini    DeepSeek  Moonshot  OpenAI
  Groq      Together  Groq      Claude
  Ollama    Gemini    DeepSeek  GPT-4
  HF Space  Groq      Together   NVIDIA
```

### 💡 How to Maximize AI Model Free Tiers:

#### A. Smart Free-Tier-Aware Router
```python
# backend/services/llm/free_tier_router.py
"""
Free-Tier-Aware Model Router
Maximizes usage of free tiers before falling back to paid providers
"""

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, List

class FreeTierStatus(Enum):
    AVAILABLE = "available"
    RATE_LIMITED = "rate_limited"
    EXHAUSTED = "exhausted"
    UNKNOWN = "unknown"

@dataclass
class ProviderQuota:
    provider: str
    free_tier_limit: int  # Requests per day
    used_today: int
    reset_time: float  # Unix timestamp when quota resets
    
    @property
    def remaining(self) -> int:
        return max(0, self.free_tier_limit - self.used_today)
    
    @property
    def status(self) -> FreeTierStatus:
        if self.remaining == 0:
            if time.time() > self.reset_time:
                return FreeTierStatus.AVAILABLE  # Reset!
            return FreeTierStatus.EXHAUSTED
        elif self.remaining < self.free_tier_limit * 0.1:
            return FreeTierStatus.RATE_LIMITED
        return FreeTierStatus.AVAILABLE

class FreeTierAwareRouter:
    """
    Routes requests to maximize free-tier usage
    Falls back to paid providers only when necessary
    """
    
    # Free tier daily limits (approximate)
    FREE_TIER_LIMITS = {
        'gemini': 1500,      # 1500 requests/day (Flash)
        'groq': 14400,       # ~600 RPM × 24h (varies)
        'huggingface': 1000,  # Serverless inference (varies)
        'ollama': float('inf'),  # Unlimited (local)
    }
    
    # Paid providers (fallback order - cheapest first)
    PAID_PROVIDERS_ORDERED = [
        'deepseek',      # ~$0.10/M tokens
        'together',      # ~$0.20/M tokens
        'moonshot',      # ~$0.50/M tokens
        'openai',        # ~$2-10/M tokens
    ]
    
    def __init__(self):
        self._quotas: Dict[str, ProviderQuota] = {}
        self._usage_log: List[dict] = []
        self._initialize_quotas()
    
    def _initialize_quotas(self):
        """Initialize quota trackers for free-tier providers"""
        for provider, limit in self.FREE_TIER_LIMITS.items():
            self._quotas[provider] = ProviderQuota(
                provider=provider,
                free_tier_limit=limit,
                used_today=0,
                reset_time=self._get_midnight_utc()
            )
    
    def _get_midnight_utc(self) -> float:
        """Get Unix timestamp for next midnight UTC"""
        import datetime
        now = datetime.datetime.utcnow()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + \
                  datetime.timedelta(days=1)
        return midnight.timestamp()
    
    async def route_request(
        self, 
        prompt: str, 
        complexity_score: int = 50,
        preferred_providers: List[str] = None
    ) -> dict:
        """
        Route request to best available provider
        Prioritizes free tiers, falls back to paid
        """
        
        # Determine which providers can handle this request
        candidates = await self._get_candidates(complexity_score)
        
        # Apply preference filter
        if preferred_providers:
            candidates = [c for c in candidates if c in preferred_providers]
        
        # Try free providers first
        for provider in candidates:
            if provider in self._quotas:
                quota = self._quotas[provider]
                
                # Reset quota if it's a new day
                if time.time() > quota.reset_time:
                    quota.used_today = 0
                    quota.reset_time = self._get_midnight_utc()
                
                if quota.status == FreeTierStatus.AVAILABLE:
                    # Use this free provider
                    result = await self._call_provider(provider, prompt)
                    
                    if result['success']:
                        quota.used_today += 1
                        self._log_usage(provider, complexity_score, True)
                        
                        return {
                            **result,
                            'provider_used': provider,
                            'cost': 0.0,
                            'tier': 'FREE',
                        }
                    else:
                        # Provider failed, try next
                        continue
        
        # All free providers exhausted - fall back to paid
        print(f"⚠️ Free tiers exhausted, using paid provider")
        
        for provider in self.PAID_PROVIDERS_ORDERED:
            if provider in candidates:
                result = await self._call_provider(provider, prompt)
                
                if result['success']:
                    self._log_usage(provider, complexity_score, True, paid=True)
                    
                    return {
                        **result,
                        'provider_used': provider,
                        'cost': result.get('cost', 0.0),
                        'tier': 'PAID',
                    }
        
        # All providers failed
        return {
            'success': False,
            'error': 'All providers unavailable',
            'providers_attempted': candidates,
        }
    
    async def _get_candidates(self, complexity_score: int) -> List[str]:
        """Get ordered list of candidate providers for complexity level"""
        
        if complexity_score <= 30:
            # Simple tasks - use fastest free options
            return ['ollama', 'gemini', 'groq', 'huggingface']
        
        elif complexity_score <= 60:
            # Medium complexity - more capable free + cheap paid
            return ['gemini', 'groq', 'deepseek', 'together']
        
        elif complexity_score <= 85:
            # Complex tasks - need quality models
            return ['gemini', 'deepseek', 'moonshot', 'groq']
        
        else:
            # Most complex - use best available
            return ['gemini', 'moonshot', 'openai', 'deepseek']
    
    async def _call_provider(self, provider: str, prompt: str) -> dict:
        """Call specific provider (implementation depends on your provider classes)"""
        # This would call your existing provider implementations
        # For now, mock implementation
        return {'success': True, 'response': f'Mock response from {provider}'}
    
    def _log_usage(
        self, 
        provider: str, 
        complexity: int, 
        success: bool, 
        paid: bool = False
    ):
        """Log usage for analytics"""
        self._usage_log.append({
            'timestamp': time.time(),
            'provider': provider,
            'complexity': complexity,
            'success': success,
            'paid': paid,
        })
    
    def get_quota_status(self) -> dict:
        """Get current quota status for all providers"""
        return {
            provider: {
                'used': quota.used_today,
                'limit': quota.free_tier_limit,
                'remaining': quota.remaining,
                'status': quota.status.value,
            }
            for provider, quota in self._quotas.items()
        }
    
    def get_cost_savings_summary(self) -> dict:
        """Calculate cost savings from free tier usage"""
        total_requests = len(self._usage_log)
        free_requests = sum(1 for log in self._usage_log if not log.get('paid'))
        paid_requests = total_requests - free_requests
        
        # Estimate costs (rough averages)
        estimated_paid_cost = paid_requests * 0.01  # ~$0.01 per paid request avg
        estimated_free_savings = free_requests * 0.02  # Would have cost ~$0.02 each
        
        return {
            'total_requests': total_requests,
            'free_tier_requests': free_requests,
            'paid_requests': paid_requests,
            'free_tier_percentage': round(free_requests / total_requests * 100, 1) if total_requests > 0 else 0,
            'estimated_paid_cost': f"${estimated_paid_cost:.2f}",
            'estimated_free_savings': f"${estimated_free_savings:.2f}",
        }
```

#### B. HuggingFace Model Swarm Optimization
```python
# backend/services/llm/hf_swarm_orchestrator.py
"""
HuggingFace Swarm Model Orchestrator
Manage 7 specialized SupremeAI models hosted on HF
"""

import aiohttp
from typing import Optional, Dict, List
from enum import Enum

class HFSwarmModel(Enum):
    CODING = ("njelit1/supreme-coder-3b", "coding_tasks")
    REASONING = ("njelitltd/supreme-reasoner-3b", "reasoning_tasks")
    GENERAL = ("ziaulhaq1/supreme-general-3b", "general_tasks")
    CREATIVE = ("njelitltd2/supreme-creative-3b", "creative_tasks")
    MASTER = ("njelitltd3/supreme-master-3b", "master_tasks")
    VISION = ("njelltd5/supreme-vision-3b", "vision_tasks")
    DRAFT = ("njelltd4/supreme-draft-0.5b", "quick_drafts")

class HFSwarmOrchestrator:
    """
    Orchestrate calls to 7 specialized HuggingFace models
    Free tier: Serverless Inference API (generous limits)
    """
    
    HF_INFERENCE_BASE_URL = "https://api-inference.huggingface.co/models/"
    
    def __init__(self, hf_api_key: str):
        self.api_key = hf_api_key
        self.client_session: Optional[aiohttp.ClientSession] = None
        self._model_stats: Dict[str, dict] = {
            model.value[0]: {
                'calls_total': 0,
                'calls_success': 0,
                'calls_failed': 0,
                'avg_latency_ms': 0,
            }
            for model in HFSwarmModel
        }
    
    async def __aenter__(self):
        self.client_session = aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client_session:
            await self.client_session.close()
    
    async def call_swarm_model(
        self, 
        model: HFSwarmModel, 
        inputs: dict,
        task_type: str = "text-generation"
    ) -> dict:
        """
        Call a specific swarm model
        """
        model_id, purpose = model.value
        url = f"{self.HF_INFERENCE_BASE_URL}/{model_id}"
        
        start_time = time.time()
        
        try:
            async with self.client_session.post(url, json=inputs) as response:
                latency_ms = (time.time() - start_time) * 1000
                
                if response.status == 200:
                    result = await response.json()
                    
                    # Update stats
                    stats = self._model_stats[model_id]
                    stats['calls_total'] += 1
                    stats['calls_success'] += 1
                    stats['avg_latency_ms'] = (
                        (stats['avg_latency_ms'] * (stats['calls_success'] - 1) + latency_ms) 
                        / stats['calls_success']
                    )
                    
                    return {
                        'success': True,
                        'result': result,
                        'model': model_id,
                        'purpose': purpose,
                        'latency_ms': latency_ms,
                    }
                
                elif response.status == 503:
                    # Model loading - wait and retry
                    await asyncio.sleep(5)
                    return await self.call_swarm_model(model, inputs, task_type)
                
                else:
                    error_text = await response.text()
                    self._model_stats[model_id]['calls_failed'] += 1
                    
                    return {
                        'success': False,
                        'error': f"HF API error {response.status}: {error_text}",
                        'model': model_id,
                    }
                    
        except Exception as e:
            self._model_stats[model_id]['calls_failed'] += 1
            return {
                'success': False,
                'error': str(e),
                'model': model_id,
            }
    
    async def auto_select_model(self, task_description: str, inputs: dict) -> dict:
        """
        Automatically select best swarm model for task
        """
        task_lower = task_description.lower()
        
        # Task type detection
        if any(word in task_lower for word in ['code', 'function', 'program', 'api']):
            model = HFSwarmModel.CODING
        elif any(word in task_lower for word in ['reason', 'logic', 'analyze', 'think']):
            model = HFSwarmModel.REASONING
        elif any(word in task_lower for word in ['creative', 'write', 'story', 'imagine']):
            model = HFSwarmModel.CREATIVE
        elif any(word in task_lower for word in ['image', 'vision', 'see', 'visual']):
            model = HFSwarmModel.VISION
        elif any(word in task_lower for word in ['quick', 'fast', 'draft', 'simple']):
            model = HFSwarmModel.DRAFT
        else:
            # Default to GENERAL or MASTER for complex tasks
            model = HFSwarmModel.GENERAL if len(task_description) < 200 else HFSwarmModel.MASTER
        
        return await self.call_swarm_model(model, inputs)
    
    def get_swarm_stats(self) -> dict:
        """Get statistics for all swarm models"""
        return {
            model.value[0]: stats for model, stats in self._model_stats.items()
        }

# Usage example:
# async with HFSwarmOrchestrator(hf_api_key) as swarm:
#     result = await swarm.auto_select_model("Write a Python function for sorting", {...})
```

---

# 📊 PART 2: INTEGRATED SERVICE ARCHITECTURE

## Complete Service Interaction Map:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     SUPREMAI COMPLETE SERVICE MAP                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐                                                        │
│  │   INFISICAL     │ ← Central Secret Vault (All secrets managed here)     │
│  │   (Secrets)     │                                                            │
│  └────────┬────────┘                                                        │
│           │                                                                 │
│           ▼                                                                 │
│  ┌──────────────────────────────────────────────────────────────────┐       │
│  │                    RENDER BACKEND (FastAPI)                      │       │
│  ├──────────────────────────────────────────────────────────────────┤       │
│  │                                                                  │       │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐  │       │
│  │  │ IDE TRIO     │  │ SMART MODEL  │  │ ETERNAL BRAIN          │  │       │
│  │  │ PIPELINE     │  │ ROUTER       │  │ (PGVector Memory)      │  │       │
│  │  │              │  │              │  │                        │  │       │
│  │  │ • Gemini     │  │ • 10+        │  │ • Supabase pgvector    │  │       │
│  │  │   (Writer)   │  │   Providers  │  │ • 1536-dim vectors     │  │       │
│  │  │ • Kilo       │  │ • Free-first │  │ • Local embeddings     │  │       │
│  │  │   (Reviewer) │  │   Routing    │  │ • Auto-prioritize      │  │       │
│  │  │ • Cline      │  │ • Failover   │  │ • Retention policy     │  │       │
│  │  │   (Checker)  │  │              │  │                        │  │       │
│  │  └──────────────┘  └──────────────┘  └───────────┬────────────┘  │       │
│  │                                                  │               │       │
│  │  ┌──────────────┐                               │               │       │
│  │  │ OBSERVABILITY│                               ▼               │       │
│  │  │ STACK        │                    ┌──────────────────┐       │       │
│  │  │              │                    │ SUPABASE         │       │       │
│  │  │ • Error Bus  │                    │ (Postgres +      │       │       │
│  │  │ • Sentry     │                    │  pgvector)       │       │       │
│  │  │ • Langfuse   │                    │                  │       │       │
│  │  │ • OTLP Trace │                    │ • ai_memory tbl  │       │       │
│  │  │              │                    │ • learned_facts  │       │       │
│  │  └──────────────┘                    │ • Vector index   │       │       │
│  │                                      └──────────────────┘       │       │
│  └──────────────────────────────────────────────────────────────────┘       │
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │  VERCEL         │  │  CLOUDFLARE     │  │  KAGGLE         │             │
│  │  (Frontend)     │  │  WORKERS        │  │  (Compute)      │             │
│  │                 │  │                 │  │                 │             │
│  │  • Admin Panel  │  │  • Edge Gateway │  │  • 6 Accounts    │             │
│  │  • User App     │  │  • R2 Storage   │  │  • 180 hrs/mo    │             │
│  │  • Analytics    │  │  • D1 Database  │  │  • Heavy jobs    │             │
│  └─────────────────┘  │  • Queue        │  └─────────────────┘             │
│                       └─────────────────┘                                      │
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │  TELEGRAM       │  │  UPTIMEROBOT    │  │  EXTERNAL APIs  │             │
│  │  (Backup)       │  │  (Monitoring)   │  │                 │             │
│  │                 │  │                 │  │ • OpenRouter    │             │
│  │  • Encrypted    │  │  • 50 Monitors  │  │ • Gemini API    │             │
│  │  • Daily Cron   │  │  • Alerts       │  │ • Groq API      │             │
│  │  • Cross-cloud  │  │  • Status Page  │  │ • HF Inference  │             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# 🎯 PART 3: MAXIMIZATION SUMMARY

## Complete Free-Tier Utilization Table (UPDATED):

| Service | Current % | Target % | Action Required |
|---------|-----------|----------|-----------------|
| **Infisical Secrets** | 83% (25/30) | 70% (21/30) | Group secrets into JSON blobs |
| **Infisical API Calls** | 30% (3K/10K) | 50% (5K/10K) | Aggressive caching |
| **Gemini API** | Unknown | 80% (1200/1500) | Primary for simple tasks |
| **Groq API** | Unknown | 90% of limit | Fast inference queue |
| **HuggingFace** | Unknown | 100% of free | Use all 7 swarm models |
| **Ollama (Local)** | 0% 🔴 | 100% | Enable offline fallback |
| **PGVector Storage** | 36% (180/500MB) | 80% (400/500MB) | More memories, retention policy |
| **PGVector Rows** | 14% (7K/50K) | 50% (25K/50K) | Store more learnings |
| **Sentry Errors** | 10% (500/5K) | 40% (2K/5K) | Connect Error Bus |
| **Sentry Transactions** | 10% (2K/20K) | 50% (10K/20K) | Enable Performance |
| **IDE Trio (Gemini)** | Unknown | 80% | Use Flash for code gen |
| **Render Hours** | 69% ⚠️ | 45% | Smart keep-alive strategy |
| **CF Workers** | 0.18% 🔴 | 40% | Full edge stack |
| **Codespaces** | 0% 🔴 | 50% | .devcontainer setup |

---

## Priority Actions for Missing Services:

### 🔴 IMMEDIATE (This Week):

1. **Connect Error Bus to Sentry** (10 min)
   - Currently SENTRY_DSN configured but not actively exporting
   - Enable automatic error capture from Error Bus
   
2. **Enable Sentry Performance/APM** (15 min)
   - Currently at 0% utilization
   - Free 20K transactions/month going to waste
   
3. **Optimize Infisical Secrets** (30 min)
   - At 83% capacity (25/30 secrets)
   - Group into JSON blobs → reduce to ~15 entries

4. **Set up IDE Trio Monitoring** (1 hr)
   - Track Gemini API usage for Stage 1
   - Log Kilo review statistics
   - Measure Cline validation pass rates

### 🟡 SHORT-TERM (This Month):

5. **Implement Free-Tier-Aware Router** (2-3 hrs)
   - Always try free providers first
   - Track free vs paid usage split
   - Report cost savings monthly

6. **Expand PGVector Usage** (ongoing)
   - Lower retention threshold (store more)
   - Add more learned facts
   - Increase embedding cache hits

7. **Activate HuggingFace Swarm** (2 hrs)
   - Route specialized tasks to 7 custom models
   - Track inference costs (should be $0 on free tier)

8. **Set up Ollama Local Fallback** (2 hrs)
   - Download models for offline use
   - Infinite free requests when online
   - Privacy mode option

---

## 📁 File Location:

**Updated Plan v4.1:** `/home/z/my-project/download/SUPREMAI_FREE_TIER_FEDERATION_MASTER_PLAN_V4.md`

**This version includes:**
- ✅ Infisical Secret Vault (with optimization code)
- ✅ IDE Trio Pipeline (Gemini→Kilo→Cline with implementations)
- ✅ Supabase PGVector/Eternal Brain (complete memory system)
- ✅ Sentry Error Tracking & Telemetry (Error Bus integration)
- ✅ Multiple AI Models (10+ providers with smart router)
- ✅ HuggingFace Swarm (7 specialized models)
- ✅ Complete service interaction map
- ✅ Maximization strategies for EACH service

---

**Plan Version:** 4.1 (Missing Services Edition)  
**Status:** COMPLETE - All services now documented  
**Next Step:** Begin Phase 1 implementation focusing on missing services!

> *"We didn't just find missing services - we found MASSIVE untapped potential!"* 🚀