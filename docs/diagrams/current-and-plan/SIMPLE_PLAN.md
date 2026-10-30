# Simple Plan (streamlined, no feature dropped)

```mermaid
flowchart LR
    A[Agent] --> T[MCP Tower (single door)]
    T --> L[continuous_agent_loop.py]
    L --> D{board + cadence}
    D --> X[dispatch payload (issue + rules + scope)]
    X --> W[work: claim→fix→verify→submit]
    W --> G[mechanical gate (4 tiers, one entry: run_all_guards)]
    G -->|pass| LAND[land→dispatch→prune (atomic)]
    G -->|fail| HEAL[auto P0 issue]
    HEAL --> L
    LAND --> SATS[satellites + monorepo sync]
    SATS --> DEPLOY[deploy: Render / Vercel / Marketplace]
    DEPLOY --> BB[(Supabase / Redis / Vault)]
    SATS --> WATCH[CI watchdog → anchor hubs]
```

Notes: keeps single door, loop, 4-tier guards, bridge dispatch, deploy, backbone, self-healing, watchdog. Drops only the separate archive/retirement transit path from the active flow (archive = explicit retire step, not every cycle).
