# 🕷️ supremeai-browser পাইপলাইন (ci.yml)

- **ইভেন্ট:** `push` (main) এবং `pull_request`
- **জবস:** `test` (Playwright Stealth Engine, Profile & Anti-Detect Tests)

```mermaid
flowchart LR
    classDef ghJob fill:#161b22,stroke:#30363d,stroke-width:1px,color:#c9d1d9;
    classDef ghDeploy fill:#161b22,stroke:#1f6feb,stroke-width:1.5px,color:#58a6ff;

    subgraph BROWSER_PIPELINE [" 🕷️ supremeai-browser: ci.yml "]
        direction LR
        J_Test["🧪 test<br/>(Playwright Chromium / Stealth Profile / Anti-Detect)"]
        J_Deploy["☁️ Render Worker Deploy<br/>(Auto on main push)"]

        J_Test --> J_Deploy
    end

    class J_Test ghJob;
    class J_Deploy ghDeploy;
```
