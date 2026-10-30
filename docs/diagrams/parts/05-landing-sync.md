# 05 Landing & Satellite Sync

## Current
```mermaid
flowchart TD
    LAND[landing] --> STEP1[Step1: open→satellite]
    STEP1 --> V1{satellite verified?}
    V1 -- yes --> STEP2[Step2: satellite→monorepo]
    STEP2 --> V2{monorepo verified?}
    V2 -- yes --> PRUNE[prune transit files + branches]
```

## Simple
```mermaid
flowchart TD
    LAND[landing] --> ATOMIC[sync all targets + verify + prune (one job)]
    ATOMIC -->|ok| CLEAN[clean steady state]
    ATOMIC -->|fail| P0[auto P0 issue]
```
One job, one verification, one prune; no separate Step1/Step2 gates in the hot path.
