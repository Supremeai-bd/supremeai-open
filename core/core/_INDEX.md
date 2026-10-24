# backend/core/ — File Index
> AI: এটি Backend-এর সবচেয়ে বড় এবং সেনসিটিভ ফোল্ডার। স্ক্যান করার বদলে এই index পড়ুন।

## Core Application Lifecycle
| File | কী করে |
|---|---|
| `app.py` | FastAPI app instance creation (`get_application`) |
| `lifespan.py` | Startup/Shutdown events (DB connect, Redis, AI load) |
| `router.py` | Main API router registration (v1, admin routes) |

## Configuration & Environment
| File | কী করে |
|---|---|
| `config.py` | Main `Settings` class (Pydantic). All env vars are here. |
| `config_secrets.py` | Securely loads secrets from Infisical/Render/Local |
| `config_validation.py` | Startup config validation rules |

## Intelligence & Business Rules
| File | কী করে |
|---|---|
| `universal_rules.py` | Global business logic, rate limits, guardrails (24KB) |
| `autonoguard_engine.py` | AI safety, prompt injection detection (22KB) |
| `decision_engine.py` | Routing and logic decisions for AI agents |
| `cost_guard.py` | Free-tier enforcement, budget/token limits |

## Security, Middleware & Auth
| File | কী করে |
|---|---|
| `security/` | JWT, Role-based access control (RBAC), Hashing |
| `middleware/` | Custom FastAPI middlewares (CORS, Request ID, Error handling) |
| `cors_policy.py` | Strict CORS definitions for frontend vs admin |
| `rate_limiter.py` | Redis-based rate limiting logic |

## Infrastructure & Resilience
| File | কী করে |
|---|---|
| `retry_handler.py` | API failover and backoff strategies |
| `health_check.py` | `/health` API logic and dependency status |
| `database/` | SQLAlchemy setup and session management |
| `cache/` | Redis caching logic |
