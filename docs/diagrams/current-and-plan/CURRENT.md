# Current Architecture (as-is)

```mermaid
flowchart TB
    subgraph ENTRY["Agent Entry"]
        EXT[Any agent] --> TOWER[MCP Tower (single door)]
        TOWER --> LOOP[continuous_agent_loop.py]
        LOOP --> DISPATCH{board scan + cadence}
        DISPATCH -->|issue exists| CODER[Coder]
        DISPATCH -->|cadence over / none| ROLES[Auditor / Scout / CI-fixer / Reviewer / Rules-breaker / Human-eye / Platform-guardian]
    end

    subgraph GUARDS["4-tier guards"]
        G1[AGENTS.md rules] --> G2[pre-commit hooks] --> G3[Tower CAS gate (baseSha)] --> G4[pipeline.yml CI]
    end

    subgraph BRIDGE["Bridge & Transit"]
        PR[PR on open:main] --> LAND[auto-landing squash merge]
        LAND --> SYNC[federation_satellite_sync dispatch]
        SYNC --> SATS[satellites: studio/api/core/browser/vscode/command/skills/sdk/infra/mcp]
        SATS --> MONO[supremeai monorepo sync]
        MONO --> PRUNE[zero-residue prune]
    end

    subgraph DEPLOY["Deploy"]
        SATS --> RENDER[Render: api/tower/browser/core]
        SATS --> VERCEL[Vercel: studio]
        SATS --> MKT[VSCode marketplace]
    end

    subgraph BB["Backbone"]
        SB[(Supabase)]
        RD[(Redis)]
        VF[(Infisical vault)]
    end

    subgraph HEAL["Self-healing"]
        FAIL[any gate fail] --> P0[auto P0 issue on open]
        P0 --> LOOP
        Q[3-strike quarantine]
    end

    subgraph WATCH["CI Watchdog"]
        CW[federation_ci_watchdog] --> HUBS[14 anchor hubs]
    end

    CODER --> GUARDS
    ROLES --> GUARDS
    GUARDS --> PR
    RENDER --> SB
    RENDER --> RD
    RENDER --> VF
```
