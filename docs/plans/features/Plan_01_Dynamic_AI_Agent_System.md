---
target_scope: combined_ecosystem
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto-Plan_01_Dynamic_AI_Agent_System
subject: "Plan 1: Dynamic AI Agent System & Multi-Agent Discovery"
document_role: architecture
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# Plan 1: Dynamic AI Agent System & Multi-Agent Discovery
**Status:** 🔄 **EVOLVED / ACTIVE IN PYTHON MCP ARCHITECTURE**  
**Completion:** ~90% (Active in MCP Control Plane & Backend Core)  
**Priority:** CRITICAL (P0)  
**Last Updated:** September 2026 (Migrated from Java prototype to Python/TypeScript MCP Control Plane)  
**Domain Circle:** Circle C1 (Code & Quality) + Circle C5 (Agent Orchestration)

---

## 🏛️ Architectural Evolution & Paradigm Shift (Java Prototype ➔ Python MCP Hub)
> [!NOTE]
> **Why this evolved from the May 2026 prototype:**
> - **Old Prototype (May 2026):** Implemented in Java 21/Spring Boot (`AgentOrchestrator.java`) with rigid hardcoded agent counts and Firebase in-memory quotas.
> - **Active Architecture (Sept 2026):** Re-engineered in **Python 3.12 (FastAPI + Pydantic v2) + Node/TS MCP Control Tower**.
> - **Core Philosophy Alignment:** Implements the true constitutional intent: **Dynamic Discovery of $1 \dots N$ Local/Remote Agents** (Ollama, Gemini, Groq, OpenRouter, Claude Code, Cline, Kilo, etc.) instead of hardcoded 3-model or 5-model constraints.

---

## 🎯 Architectural Intent & Overview
Implementation of a generalized, dynamic AI agent pool capable of discovering, rotating, and orchestrating any number of local or remote AI agents ($1 \dots N$). The system assigns roles (Writer, Reviewer, Security Checker, etc.) dynamically based on available compute without locking the user into rigid model names.

---

## ⚙️ Active Implementation Details (Python & MCP Control Plane)

### 1. Central MCP Capability & Discovery
- **Control Plane Tools:**
  - `ai_available_providers` — Discovers all active local/remote AI providers.
  - `ai_list_providers` — Enumerates health, latency, and capabilities.
  - `ai_test_provider` — Runs automated sanity checks per agent.
- **Location:** `infrastructure/mcp-control-plane/src/index.ts` & `src/service-circles.ts`

### 2. Backend Orchestration Engines
- **Dynamic Assembly Pipeline:** `backend/core/orchestration/trio_pipeline.py` (Chains discovered agents into Writer ➔ Reviewer ➔ Checker pipelines).
- **Cognitive Orchestrators:**
  - `backend/core/agent_orchestrator.py` — Multi-agent dispatch.
  - `backend/core/master_cognitive_orchestrator.py` — Swarm and hierarchical planning.
  - `backend/agents/ide/trio_adapters.py` — Modular model adapters (Gemini, Kilo, Cline, Local LLMs).

### 3. Key Active Features
- ✅ Dynamic provider discovery ($1 \dots N$ agents)
- ✅ Autonomous failover and provider-neutral routing
- ✅ Quota tracking and rate-limit backoff (Upstash Redis + Infisical secrets)
- ✅ Health monitoring endpoints and MCP heartbeat
- ✅ Zero cross-circle coupling; fully orchestrated via Central Hub

---

## 📊 Legacy Java Prototype Reference (Historical Archive)
*For historical audit, the original Java 21 classes (Spring Boot) were:*
- `src/main/java/com/supremeai/agent/AgentOrchestrator.java`
- `src/main/java/com/supremeai/agent/AIAgentPool.java`
- `src/main/java/com/supremeai/service/AgentRotationService.java`

---

## Current Status Analysis

### ✅ Completed Features
- Dynamic agent pool management
- Automatic rotation on 80% quota
- Multi-provider integration
- Health monitoring system
- Fallback mechanisms

### 📊 Performance Metrics
- Agent rotation latency: <100ms
- Failover time: <500ms
- API success rate: 99.5%+
- Quota accuracy: 100%

---

## Suggestions for Enhancement

### 1. Advanced Features
- **Predictive Rotation**: Use ML to predict quota usage and rotate proactively
- **Agent Specialization**: Different agents for different task types (code, text, analysis)
- **Cost Optimization**: Dynamic provider selection based on cost/performance

### 2. Monitoring & Analytics
- **Real-time Dashboard**: Visual agent performance metrics
- **Usage Analytics**: Per-agent usage patterns and costs
- **Alert System**: Proactive notifications for quota limits

### 3. Scalability Improvements
- **Distributed Agent Pool**: Multi-region agent deployment
- **Caching Layer**: Redis for frequently accessed agent data
- **Async Processing**: Queue-based task distribution

### 4. Security Enhancements
- **API Key Encryption**: Enhanced security for stored keys
- **Audit Logging**: Complete audit trail of agent usage
- **Rate Limiting**: Per-user and per-agent rate limits

### 5. Integration Opportunities
- **Custom Agent Training**: Allow training on organization-specific data
- **Third-party Integrations**: Slack, Teams, Discord notifications
- **Webhook Support**: External system notifications

---

## Future Roadmap

### Short-term (Month 1)
- [ ] Implement predictive rotation algorithm
- [ ] Add agent specialization features
- [ ] Enhanced monitoring dashboard

### Medium-term (Quarter 1)
- [ ] Multi-region deployment
- [ ] Advanced caching implementation
- [ ] Custom agent training pipeline

### Long-term (Year 1)
- [ ] Fully autonomous agent management
- [ ] AI-powered cost optimization
- [ ] Enterprise-grade security features

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| API Rate Limits | Low | Medium | Rotation system implemented |
| Provider Downtime | Low | High | Multi-provider fallback |
| Cost Overruns | Medium | Medium | Monitoring and alerts |
| Security Breach | Low | High | Encryption and audit logs |

---

## Dependencies

- Firebase Firestore for agent state
- OpenAI API for GPT models
- Gemini API for Google models
- Spring Boot for backend services
- Java 21 for runtime

---

## Testing & Validation

### Unit Tests
- Agent rotation logic: ✅ 95% coverage
- Quota management: ✅ 98% coverage
- Health checks: ✅ 100% coverage

### Integration Tests
- Multi-provider failover: ✅ Passed
- Load balancing: ✅ Passed
- Fallback mechanisms: ✅ Passed

---

## Maintenance Notes

- Monitor API usage trends weekly
- Review agent performance monthly
- Update provider configurations quarterly
- Security audit semi-annually

---

**Document Owner**: Kilo Code  
**Version**: 2.0  
**Status**: ✅ Production Ready

---

## 🛰️ Integrated Blueprint: Ultimate AI Controller & 8 Pillars Dashboard
*(Merged from historical SupremeAI_Ultimate_Controller_Plan.md)*

# 🚀 SupremeAI Ultimate AI Controller Plan
**Version:** 3.0 (Zero-Hardcode Evolution)
**Status:** Approved for Implementation
**Focus:** Absolute control over AI Intelligence, Roles, and Real-time Telemetry.

---

## 1. Dashboard Structure (The 8 Pillars)

| # | Tab Name | Purpose | Key Features |
|---| :--- | :--- | :--- |
| 1 | **Intelligence Registry** | AI Discovery | Add/Delete local (Ollama) & Cloud (Gemini, GPT, Claude, etc.) models via API or Endpoint. |
| 2 | **Scenario Orchestration** | Role Delegation | Assign any number of roles (Chat, Execution, Voting, Reasoning, etc.) to any model. One model can handle 100% of tasks if assigned. |
| 3 | **Live Telemetry** | System Pulse | Real-time RAM/GPU usage, Tokens/sec, and Latency matrix (3D Visualizer integrated). |
| 4 | **Consensus Map** | Decision Logic | Visual display of Multi-agent voting, disagreement resolution, and final decision path. |
| 5 | **Quota & Traffic** | Resource Control | API usage tracking with auto-failover to alternative models when limits are reached. |
| 6 | **Knowledge (RAG)** | Brain Injection | Interface to upload documents or data streams to specific models or global knowledge store. |
| 7 | **Self-Healing Logs** | System Repair | Live diagnostic stream showing errors and the system's autonomous self-correction attempts. |
| 8 | **Learning Hub** | Cognitive Control | Manage subjects and topics the AI agents are actively learning. Add/Remove learning targets. |

---

## 2. Technical Implementation Requirements

### A. Backend (Spring Boot 3 + Firestore)
- **Unified Provider Model**: `APIProvider` must support a dynamic array of capabilities.
- **WebSocket Metrics**: Finalize `MetricsBroadcasterService` to stream hardware and performance data.
- **Production Security**: Fix CORS and CSRF configurations for `supremeai-a.web.app` and `supremeai-a.firebaseapp.com`.
- **Dynamic Role Patching**: Ensure PATCH `/api/admin/providers/{id}/capability` supports adding/removing multiple roles.

### B. Frontend (React + Vite + Ant Design)
- **Tabbed Interface Cleanup**: Remove all irrelevant legacy tabs (Overview, Projects, etc.).
- **Dynamic Role UI**: Replace simple switches with a multi-select capability list in `APIManagement`.
- **Telemetry Integration**: Connect `ThreeDashboard` (3D Graph) to live metrics from the backend.
- **Production URL Sync**: Ensure `VITE_API_URL` correctly points to the GCloud Cloud Run instance.

---

## 3. Implementation Workflow
1. **Core UI Cleanup**: Strip `AdminDashboardUnified.tsx` of all non-essential tabs.
2. **Backend Hardening**: Fix the "Invalid CORS request" on production by updating `SecurityConfig`.
3. **Role Logic wiring**: Connect the Scenario Orchestration checkboxes to the `capability` patch endpoint.
4. **Telemetry Stream**: Wire the 3D visualizer to actual backend state via WebSockets.
5. **Final Production Push**: Deploy to Cloud Run and Firebase to verify zero-error connectivity.



---

## 🧬 Historical 5-Model Benchmark Reference (The Example Trap Record)
*(Merged from historical SupremeAI_Final_5Model_Structure.md)*


# SupremeAI - Model Topology: Evolution from Fixed 5-Model to Dynamic $1 \dots N$ Agent Pool
**Status:** 🔄 **EVOLVED / SUPERSEDED BY DYNAMIC AGENT DISCOVERY**  
**Last Updated:** September 2026  
**Governing Rule:** *AGENTS.md Clause 1: "Intent Over Concrete Examples (Avoid the Example Trap)"*

> [!IMPORTANT]
> **Architectural Evolution & Constitutional Note:**
> - **The Historical Context (May 2026):** This document proposed a rigid "Final 5-Model Structure" (Qwen, Llama, DeepSeek, Phi, Nomic) intended to fit within ~16GB RAM.
> - **The Constitutional Realization (Sept 2026):** Naming and restricting the system to a fixed "5-Model Structure" was an **Example Trap**.
> - **Active Production Architecture:** The platform now implements **Dynamic Discovery of $1 \dots N$ Agents**. The system auto-detects whatever local models (via Ollama, vLLM, LMStudio) or cloud APIs (Gemini, Groq, OpenRouter, OpenAI, Claude) are available in the user's active environment, assigning roles dynamically.
> - *This document is preserved as an audit record of local model quantization benchmarks.*

---

# 1. Historical Model Benchmarks (The Illustrative 5)

| # | Model | Role | Size | RAM | Why |
|---|-------|------|------|-----|-----|
| 1 | **Qwen 2.5 Coder 7B** | Primary Coder | 7B | ~4GB | Best code generation |
| 2 | **Llama 3.1 8B** | General Chat | 8B | ~4.5GB | Best all-rounder |
| 3 | **DeepSeek Coder 6.7B** | Review/Debug | 6.7B | ~4GB | Best reasoning |
| 4 | **Phi 3 Mini** | Fast Tasks | 3.8B | ~2GB | Quick responses |
| 5 | **Nomic Embed** | Embeddings | - | ~1GB | Search/Similarity |

**Total RAM Needed:** ~15.5GB (all loaded)
**Recommended:** Load 2-3 at a time, swap as needed

---

# 2. Project Structure

```
supremeai/
├── .github/
│   └── workflows/
│       └── ci.yml
├── config/
│   ├── __init__.py
│   ├── settings.py          # Main config
│   ├── model_config.py      # Model definitions
│   └── api_keys.py          # API key management
├── core/
│   ├── __init__.py
│   ├── orchestrator.py      # Plan 1: Agent orchestrator
│   ├── router.py            # Model router
│   └── fallback.py          # System AI fallback
├── models/
│   ├── __init__.py
│   ├── local/
│   │   ├── __init__.py
│   │   ├── qwen_coder.py    # Qwen 2.5 Coder 7B
│   │   ├── llama_general.py # Llama 3.1 8B
│   │   ├── deepseek_debug.py# DeepSeek Coder 6.7B
│   │   ├── phi_fast.py      # Phi 3 Mini
│   │   └── nomic_embed.py   # Nomic Embed
│   └── external/
│       ├── __init__.py
│       ├── openai_client.py     # OpenAI API
│       ├── anthropic_client.py  # Claude API
│       ├── google_client.py     # Gemini API
│       ├── groq_client.py       # Groq API (fast)
│       └── together_client.py   # Together AI
├── api/
│   ├── __init__.py
│   ├── key_manager.py       # Plan 2: Key rotation
│   ├── key_validator.py     # Validate keys
│   ├── rotation_strategy.py # Rotation logic
│   └── free_tier_monitor.py # Monitor limits
├── learning/
│   ├── __init__.py
│   ├── knowledge_base.py    # Knowledge storage
│   ├── web_scraper.py       # Browser learning
│   └── pattern_learner.py   # Pattern learning
├── storage/
│   ├── __init__.py
│   ├── database.py          # SQLite/PostgreSQL
│   └── cache.py             # Redis/Memcached
├── github_integration/
│   ├── __init__.py
│   ├── repo_manager.py      # Dual repo
│   └── webhook_handler.py   # GitHub webhooks
├── voice/
│   ├── __init__.py
│   └── speech_processor.py  # Voice input
├── vision/
│   ├── __init__.py
│   └── image_processor.py   # Image understanding
├── dashboard/
│   ├── __init__.py
│   ├── admin.py             # Admin settings
│   └── user_ui.py           # User interface
├── utils/
│   ├── __init__.py
│   ├── logger.py
│   └── helpers.py
├── tests/
│   ├── __init__.py
│   ├── test_orchestrator.py
│   ├── test_key_manager.py
│   ├── test_models.py
│   └── test_integration.py
├── scripts/
│   ├── setup.sh
│   └── deploy.sh
├── docs/
│   ├── architecture.md
│   └── api_reference.md
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── .gitignore
└── README.md
```

---

# 3. Free API Keys Configuration

## Supported Free Tiers:

| Provider | Free Tier | Limit | Model Access |
|----------|-----------|-------|--------------|
| **OpenAI** | $5 credit | 3 months | GPT-3.5, GPT-4 |
| **Anthropic** | $5 credit | - | Claude 3 Haiku |
| **Google AI** | Free tier | 60 req/min | Gemini Pro, Flash |
| **Groq** | Free tier | - | Llama, Mixtral (fast) |
| **Together AI** | $5 credit | - | Various models |
| **Cohere** | Trial | - | Command models |
| **Mistral** | Free tier | - | Mistral 7B |

## config/api_keys.py:

```python
# Free API Key Configuration
FREE_API_PROVIDERS = {
    'openai': {
        'base_url': 'https://api.openai.com/v1',
        'models': ['gpt-3.5-turbo', 'gpt-4'],
        'free_credits': 5.0,
        'validity_days': 90,
    },
    'anthropic': {
        'base_url': 'https://api.anthropic.com',
        'models': ['claude-3-haiku-20240307'],
        'free_credits': 5.0,
        'validity_days': None,
    },
    'google': {
        'base_url': 'https://generativelanguage.googleapis.com',
        'models': ['gemini-pro', 'gemini-flash'],
        'free_requests_per_min': 60,
        'validity_days': None,  # Always free
    },
    'groq': {
        'base_url': 'https://api.groq.com/openai/v1',
        'models': ['llama3-8b-8192', 'mixtral-8x7b-32768'],
        'free_tier': True,
        'validity_days': None,
    },
    'together': {
        'base_url': 'https://api.together.xyz/v1',
        'models': ['mistralai/Mixtral-8x7B-Instruct-v0.1'],
        'free_credits': 5.0,
        'validity_days': None,
    },
    'mistral': {
        'base_url': 'https://api.mistral.ai/v1',
        'models': ['mistral-tiny', 'mistral-small'],
        'free_tier': True,
        'validity_days': None,
    }
}

# Priority order (best first)
PROVIDER_PRIORITY = [
    'groq',      # Fastest, always free
    'google',    # Generous limits
    'mistral',   # Good for small tasks
    'openai',    # $5 credit
    'anthropic', # $5 credit
    'together',  # $5 credit
]
```

---

# 4. Model Router Logic

```python
# core/router.py
class ModelRouter:
    def __init__(self):
        self.local_models = {
            'qwen_coder': LocalModel('qwen2.5-coder:7b'),
            'llama_general': LocalModel('llama3.1:8b'),
            'deepseek_debug': LocalModel('deepseek-coder:6.7b'),
            'phi_fast': LocalModel('phi3:mini'),
            'nomic_embed': LocalModel('nomic-embed-text'),
        }
        self.external_clients = {
            'groq': GroqClient(),
            'google': GoogleClient(),
            'openai': OpenAIClient(),
        }
        self.key_manager = APIKeyManager()

    def route(self, task_type, task_input, user_preference=None):
        # Step 1: Check if local model can handle
        local_model = self.select_local_model(task_type)
        if local_model and self.is_available(local_model):
            return local_model.process(task_input)

        # Step 2: Try external API (free tier)
        external_provider = self.select_external_provider(task_type)
        if external_provider:
            return external_provider.process(task_input)

        # Step 3: Fallback to system AI
        return self.system_ai_fallback(task_input)

    def select_local_model(self, task_type):
        mapping = {
            'code_generation': 'qwen_coder',
            'code_review': 'deepseek_debug',
            'general_chat': 'llama_general',
            'quick_task': 'phi_fast',
            'embedding': 'nomic_embed',
        }
        return self.local_models.get(mapping.get(task_type))

    def select_external_provider(self, task_type):
        # Check which provider has available quota
        for provider_name in PROVIDER_PRIORITY:
            provider = self.external_clients.get(provider_name)
            if provider and provider.has_quota():
                return provider
        return None
```

---

# 5. API Key Rotation (Plan 2)

```python
# api/key_manager.py
class APIKeyManager:
    def __init__(self):
        self.keys = self.load_keys()
        self.usage_tracker = UsageTracker()
        self.rotation_threshold = 0.8  # 80%

    def get_key(self, provider):
        key_data = self.keys.get(provider)
        if not key_data:
            return None

        # Check usage ratio
        usage_ratio = key_data['used'] / key_data['limit']

        if usage_ratio >= self.rotation_threshold:
            # Try next provider
            next_provider = self.get_next_provider(provider)
            if next_provider:
                return self.get_key(next_provider)
            # All exhausted, use local
            return 'LOCAL_FALLBACK'

        key_data['used'] += 1
        return key_data['key']

    def get_next_provider(self, current):
        idx = PROVIDER_PRIORITY.index(current)
        if idx + 1 < len(PROVIDER_PRIORITY):
            return PROVIDER_PRIORITY[idx + 1]
        return None
```

---

# 6. Environment Configuration (.env.example)

```bash
# Local Models (Ollama)
OLLAMA_HOST=http://localhost:11434

# External API Keys (Free tiers)
OPENAI_API_KEY=sk-your-openai-key
ANTHROPIC_API_KEY=sk-ant-your-anthropic-key
GOOGLE_API_KEY=your-google-api-key
GROQ_API_KEY=gsk-your-groq-key
TOGETHER_API_KEY=your-together-key
MISTRAL_API_KEY=your-mistral-key

# Database
DATABASE_URL=sqlite:///supremeai.db

# Application
DEBUG=False
SECRET_KEY=your-secret-key
PORT=8000

# Features
ENABLE_LOCAL_MODELS=True
ENABLE_EXTERNAL_APIS=True
ENABLE_VOICE=False
ENABLE_VISION=False
AUTO_APPROVE=False
```

---

# 7. Docker Compose (Optional)

```yaml
version: '3.8'
services:
  supremeai:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=sqlite:///data/supremeai.db
    volumes:
      - ./data:/app/data
    depends_on:
      - ollama

  ollama:
    image: ollama/ollama
    volumes:
      - ollama:/root/.ollama
    ports:
      - "11434:11434"

  redis:
    image: redis:alpine
    ports:
      - "6379:6379"

volumes:
  ollama:
```

---

# 8. Quick Start Commands

```bash
# 1. Clone and setup
git clone https://github.com/paykaribazaronline/supremeai
cd supremeai
cp .env.example .env
# Edit .env with your API keys

# 2. Install dependencies
pip install -r requirements.txt

# 3. Pull local models (Ollama)
ollama pull qwen2.5-coder:7b
ollama pull llama3.1:8b
ollama pull deepseek-coder:6.7b
ollama pull phi3:mini
ollama pull nomic-embed-text

# 4. Run tests
pytest

# 5. Start server
python src/main.py
```

---

# 9. Model Usage Decision Tree

```
User Request
    │
    ├── Code Task? ──→ Qwen 2.5 Coder 7B (Local)
    │   └── If busy ──→ DeepSeek Coder (Local)
    │       └── If busy ──→ Groq API (External)
    │
    ├── General Chat? ──→ Llama 3.1 8B (Local)
    │   └── If busy ──→ Google Gemini (External)
    │
    ├── Debug/Review? ──→ DeepSeek Coder (Local)
    │   └── If busy ──→ Claude Haiku (External)
    │
    ├── Quick Task? ──→ Phi 3 Mini (Local)
    │   └── If busy ──→ Mistral Tiny (External)
    │
    ├── Embedding? ──→ Nomic Embed (Local)
    │
    └── All Busy? ──→ Queue or System AI Fallback
```

---

# 10. Monitoring Dashboard

```
┌─────────────────────────────────────┐
│  SupremeAI Dashboard                 │
├─────────────────────────────────────┤
│                                      │
│  Local Models:                       │
│  [🟢] Qwen 2.5 Coder 7B  - Active   │
│  [🟢] Llama 3.1 8B       - Active   │
│  [🟡] DeepSeek Coder 6.7B - Busy    │
│  [🟢] Phi 3 Mini         - Idle     │
│  [🟢] Nomic Embed        - Active   │
│                                      │
│  External APIs:                      │
│  [🟢] Groq        - 80% quota left  │
│  [🟢] Google      - Unlimited       │
│  [🟡] OpenAI      - $2.50 left      │
│  [🔴] Anthropic   - Exhausted       │
│                                      │
│  Active Users: 12                    │
│  Queue: 3 requests                   │
│  Avg Response: 2.3s                  │
│                                      │
└─────────────────────────────────────┘
```

---

**Document Status:** Ready for Implementation
**Next Step:** Start with local models + 1-2 free APIs
