# 12 Gateway (Provider Routing)

## Current
```mermaid
flowchart LR
    CLIENT[client + SUPREMEAI_API_KEY] --> GW[supremeai-api gateway]
    GW --> P1[Gemini]
    GW --> P2[Groq]
    GW --> P3[OpenRouter]
    GW --> PN[... providers]
    GW --> FB[dynamic failover / rotation / quota]
```

## Simple
```mermaid
flowchart LR
    CLIENT[client] --> GW[gateway (OpenAI-compatible)]
    GW --> POOL[provider pool + failover]
```
Same gateway; pool/failover collapsed into one node in the diagram.
