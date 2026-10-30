# 03 Guards (4 tiers)

## Current
```mermaid
flowchart TD
    A[attempt change] --> T1[1. AGENTS.md rules]
    T1 --> T2[2. pre-commit hooks]
    T2 --> T3[3. Tower CAS gate]
    T3 --> T4[4. remote CI pipeline.yml]
    T4 -->|all pass| OK[land + deploy]
    T4 -->|any fail| FAIL[fail-closed + auto P0 issue]
```

## Simple
```mermaid
flowchart TD
    A[attempt change] --> G[mechanical gate (single entry: run_all_guards)]
    G -->|pass| OK[land + deploy]
    G -->|fail| FAIL[fail-closed + auto P0 issue]
```
Same 4 tiers internally, but one entry point and one report; no per-guard scattered scripts in the hot path.
