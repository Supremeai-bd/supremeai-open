# supremeai-archive (Cold Storage)

## Current
```mermaid
flowchart TD
    RETIRE[retired feature/spec] --> ARCH[append-only archive]
    ARCH --> ADR[ADRs / worklogs / snapshots]
    ARCH -.-> MONO[removed from active repos]
```

## Simple
```mermaid
flowchart TD
    RETIRE[retire] --> ARCH[archive (append-only)]
```
Same append-only memory; removal from active repos is a side effect, not a flow node.
