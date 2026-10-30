# supremeai-browser (Stealth Runtime)

## Current
```mermaid
flowchart TD
    REQ[scrape request] --> STEALTH[anti-detect stealth engine]
    STEALTH --> PW[Playwright (headless)]
    PW --> DATA[extracted data]
    PW --> WS[websocket stream]
```

## Simple
```mermaid
flowchart TD
    REQ[request] --> BROWSER[stealth browser]
    BROWSER --> DATA[data]
```
Same stealth+playwright; internal anti-detect stays inside the browser node.
