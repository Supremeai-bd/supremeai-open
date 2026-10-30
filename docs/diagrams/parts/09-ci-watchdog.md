# 09 CI Watchdog & Anchor Hubs

## Current
```mermaid
flowchart TD
    RUNS[7 federation pipelines] --> W[federation_ci_watchdog (15m cron)]
    W --> DEDUP{idempotent marker?}
    DEDUP -- new --> ISSUE[P0 incident sub-issue]
    ISSUE --> HUBS[14 anchor hubs #749-#762]
```

## Simple
```mermaid
flowchart TD
    RUNS[pipelines] --> W[watchdog]
    W --> ISSUE[incident issue (deduped)]
    ISSUE --> HUBS[anchor hubs]
```
Same watchdog; dedup marker kept internal, not a separate branch in the diagram.
