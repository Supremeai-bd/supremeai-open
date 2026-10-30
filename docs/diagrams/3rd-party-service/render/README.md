# ☁️ Render ক্লাউড সার্ভিস আর্কিটেকচার

- **ক্যাটাগরি:** Cloud Hosting (Web Services & Background Workers)
- **ব্যবহার:** `supremeai-api`, `MCP Control Tower`, `browser` ও `core` ওয়ার্কার্স হোস্ট করা

```mermaid
flowchart LR
    classDef svc fill:#161b22,stroke:#a855f7,stroke-width:1.5px,color:#d8b4fe;
    classDef gate fill:#161b22,stroke:#30363d,stroke-width:1px,color:#c9d1d9;

    GitHub["GitHub Actions Dispatch"] --> Render["☁️ Render Cloud<br/>• supremeai-api (Web Service)<br/>• MCP Tower (FastMCP)<br/>• Browser & Core Workers"]

    class GitHub gate;
    class Render svc;
```

