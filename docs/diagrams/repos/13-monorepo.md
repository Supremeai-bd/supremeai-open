# supremeai (Monorepo Anchor)

## Current
```mermaid
flowchart TD
    SATS[satellites] --> MONO[supremeai monorepo (passive mirror)]
    MONO --> AGG[aggregated view]
    MONO --> NOCI[zero CI / zero deploy]
```

## Simple
```mermaid
flowchart TD
    SATS[satellites] --> MONO[monorepo (passive mirror)]
```
Same passive anchor; aggregation and zero-CI are properties, not flow nodes.
