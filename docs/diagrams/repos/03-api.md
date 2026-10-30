# supremeai-api (Gateway)

## Current
```mermaid
flowchart LR
    CLIENT[Client + SUPREMEAI_API_KEY] --> AUTH[auth + rate limit]
    AUTH --> ROUTER[OpenAI-compatible router]
    ROUTER --> GEMINI[Gemini]
    ROUTER --> GROQ[Groq]
    ROUTER --> OR[OpenRouter]
    ROUTER --> FB[failover / rotation / quota]
```

## Simple
```mermaid
flowchart LR
    CLIENT[client] --> GW[Gateway (OpenAI-compatible)]
    GW --> POOL[provider pool + failover/quota]
```
Same gateway; pool collapses providers into one node with internal failover.
