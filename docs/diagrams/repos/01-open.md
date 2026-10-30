# supremeai-open (Embassy / Public Boundary)

## Current
```mermaid
flowchart TD
    AGENT[Any agent] --> TOWER[MCP Tower]
    TOWER --> LOOP[continuous_agent_loop.py]
    LOOP --> BOARD[GitHub issue board]
    BOARD --> BRIDGE[bridge work order]
    BRIDGE --> GATE[pipeline.yml gate]
    GATE --> SYNC[federation_satellite_sync]
    SYNC --> PRUNE[zero-residue prune]
```

## Simple
```mermaid
flowchart TD
    AGENT[agent] --> TOWER[Tower] --> LOOP[loop]
    LOOP --> BOARD[board]
    BOARD --> PIPE[gate + dispatch + prune (atomic)]
```
Single door + loop + one atomic pipeline; no scattered bridge scripts in hot path.
