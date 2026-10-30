# 06 Deploy Topology

## Current
```mermaid
flowchart TD
    SATS[satellites] --> R1[Render: api]
    SATS --> R2[Render: tower]
    SATS --> R3[Render: browser]
    SATS --> R4[Render: core]
    SATS --> V[Vercel: studio]
    SATS --> M[VSCode marketplace]
```

## Simple
```mermaid
flowchart TD
    SATS[satellites] --> DEPLOY[deploy router (detect changed targets)]
    DEPLOY --> RENDER[Render services]
    DEPLOY --> VERCEL[Vercel studio]
    DEPLOY --> MKT[Marketplace]
```
Keep all 6 targets; add a change-detect router so only touched services redeploy.
