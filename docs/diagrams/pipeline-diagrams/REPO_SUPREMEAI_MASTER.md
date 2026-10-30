# 👑 supremeai (Master Monorepo) পাইপলাইন (bridge-intake.yml)

- **ইভেন্ট:** `repository_dispatch`, `schedule` ও `workflow_dispatch`
- **জবস:** `bridge` (Rolling Train Consolidation ও মাস্টার ইনজেশন)

```mermaid
flowchart LR
    classDef ghJob fill:#161b22,stroke:#30363d,stroke-width:1px,color:#c9d1d9;
    classDef ghMaster fill:#161b22,stroke:#8957e5,stroke-width:2px,color:#d2a8ff;

    subgraph MASTER_PIPELINE [" 👑 supremeai: bridge-intake.yml "]
        direction LR
        J_Bridge["🚂 bridge<br/>(Rolling Train Sync + Full Umbrella Ingestion)"]
        J_Consolidate["👑 Master State Record<br/>(Consolidated SSOT)"]

        J_Bridge --> J_Consolidate
    end

    class J_Bridge ghJob;
    class J_Consolidate ghMaster;
```
