# 04 Bridge & Transit

## Current
```mermaid
flowchart TD
    PR[PR on open:main] --> LAND[auto-landing squash merge]
    LAND --> SYNC[federation_satellite_sync dispatch]
    SYNC --> SATS[satellites]
    SATS --> MONO[supremeai monorepo sync]
    MONO --> PRUNE[zero-residue prune]
    LAND -. fail .-> P0[auto P0 issue]
    SYNC -. fail .-> P0
```

## Simple
```mermaid
flowchart TD
    PR[PR on open:main] --> GATE{gate pass?}
    GATE -- pass --> ATOMIC[land→dispatch→prune (atomic)]
    GATE -- fail --> P0[auto P0 issue]
    ATOMIC --> SATS[satellites + monorepo]
```
Collapse landing/dispatch/prune into one atomic step with a single failure exit.
