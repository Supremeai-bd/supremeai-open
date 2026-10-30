# 🚀 SupremeAI মাল্টি-রিপো ডেপ্লয়মেন্ট ও হোস্টিং ডায়াগ্রাম (Render & Frontend Deploy)

এই ডায়াগ্রামে আমাদের ৬টি স্যাটেলাইট রিপোজিটরি থেকে Render ক্লাউড এবং ফ্রন্টএন্ড হোস্টিং প্ল্যাটফর্মে (Vercel / Marketplaces) কীভাবে স্বয়ংক্রিয়ভাবে লাইভ সার্ভিস ডেপ্লয় হয়, তা তুলে ধরা হয়েছে।

---

```mermaid
flowchart TD
    %% ========================================================
    %% REPOSITORIES LAYER
    %% ========================================================
    subgraph REPOS [" 🛰️ ৬টি স্যাটেলাইট রিপোজিটরি (Source Repos) "]
        Repo_Studio["১. supremeai-studio<br/>(React / Next.js Web Console)"]
        Repo_API["২. supremeai-api<br/>(FastAPI Multi-LLM Gateway)"]
        Repo_Tower["৩. MCP Control Tower / Infra<br/>(Node.js / TS MCP Server)"]
        Repo_Browser["৪. supremeai-browser<br/>(Stealth Playwright Service)"]
        Repo_Core["৫. supremeai-core<br/>(Agent Kernel & Worker Engine)"]
        Repo_VSCode["৬. supremeai-vscode<br/>(Extension & Desktop Client)"]
    end

    %% ========================================================
    %% CI/CD PIPELINE & DEPLOY TRIGGER
    %% ========================================================
    subgraph TRIGGERS [" ⚙️ সিআই/সিডি অটোমেশন ও ডেপ্লয় ট্রিগার "]
        T_Studio["Vercel GitHub Integration<br/>(Auto Build & Edge CDN)"]
        T_API["Render Webhook / Auto-Deploy<br/>(Python 3.13 Runtime)"]
        T_Tower["Render Web Service Deploy<br/>(Docker / Node Runtime)"]
        T_Browser["Render Background Worker<br/>(Headless Chromium Env)"]
        T_Core["Render Celery/Background Worker<br/>(Autonomous Loop Runtime)"]
        T_VSCode["VS Code Marketplace / Desktop Build<br/>(Tauri / VSIX Pipeline)"]

        Repo_Studio --> T_Studio
        Repo_API --> T_API
        Repo_Tower --> T_Tower
        Repo_Browser --> T_Browser
        Repo_Core --> T_Core
        Repo_VSCode --> T_VSCode
    end

    %% ========================================================
    %% HOSTING & DEPLOYMENT DESTINATIONS
    %% ========================================================
    subgraph DEPLOY_TARGETS [" 🌐 লাইভ প্রোডাকশন হোস্টিং প্ল্যাটফর্ম "]
        
        %% Frontend Cloud
        subgraph FRONTEND_HOST [" 🎨 ফ্রন্টএন্ড ও ক্লায়েন্ট হোস্টিং (Vercel / Stores) "]
            Live_Studio["💻 <b>SupremeAI Studio UI</b><br/>URL: <code>https://supremeai-studio.vercel.app</code><br/>(Edge CDN, SSR, Global Routing)"]
            Live_VSCode["🧩 <b>VS Code Extension & App</b><br/>Marketplace: <code>supremeai.vsix</code><br/>Desktop: Tauri Release Installer"]
        end

        %% Render Cloud
        subgraph RENDER_CLOUD [" ☁️ Render Cloud Services (Render Deploy) "]
            Live_API["⚡ <b>API Gateway Web Service</b><br/>URL: <code>https://supremeai-api-ulw0.onrender.com</code><br/>(Unified OpenAI-compatible Gateway)"]
            Live_Tower["🏰 <b>MCP Control Tower Service</b><br/>URL: <code>https://supremeai-mcp-tower.onrender.com</code><br/>(Streamable /mcp & /sse Hub)"]
            Live_Browser["🕷️ <b>Stealth Browser Engine Service</b><br/>(Headless Stealth Crawl API & Websocket)"]
            Live_Core["🧠 <b>Core Autonomous Worker</b><br/>(Continuous Task Runner & Self-Evolution)"]
        end

        T_Studio --> Live_Studio
        T_VSCode --> Live_VSCode
        
        T_API --> Live_API
        T_Tower --> Live_Tower
        T_Browser --> Live_Browser
        T_Core --> Live_Core
    end

    %% ========================================================
    %% INTEGRATION & BACKBONE
    %% ========================================================
    subgraph BACKBONE [" 🗄️ শেয়ার্ড ব্যাকবোন ও ইনফ্রাস্ট্রাকচার "]
        Supabase["🐘 Supabase PostgreSQL & Auth"]
        Redis["⚡ Redis Cache & Message Queue"]
        Vault["🔐 Infisical Secret Vault"]
    end

    Live_API <--> Supabase
    Live_Tower <--> Supabase
    Live_Core <--> Supabase
    Live_Browser <--> Redis
    Live_API <--> Redis

    Live_Studio -->|API Calls via SUPREMEAI_API_KEY| Live_API
    Live_Studio -->|Tool Invocation| Live_Tower
    Live_VSCode -->|Agent Context & Actions| Live_Tower

    %% Styling
    style Repo_Studio fill:#1e293b,stroke:#f59e0b,stroke-width:2px,color:#f8fafc
    style Repo_API fill:#1e293b,stroke:#10b981,stroke-width:2px,color:#f8fafc
    style Repo_Tower fill:#1e293b,stroke:#eab308,stroke-width:2px,color:#f8fafc
    style Repo_Browser fill:#1e293b,stroke:#ef4444,stroke-width:2px,color:#f8fafc
    style Repo_Core fill:#1e293b,stroke:#3b82f6,stroke-width:2px,color:#f8fafc
    style Repo_VSCode fill:#1e293b,stroke:#06b6d4,stroke-width:2px,color:#f8fafc

    style FRONTEND_HOST fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc
    style RENDER_CLOUD fill:#0f172a,stroke:#a855f7,stroke-width:2px,color:#f8fafc
    
    style Live_Studio fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#ecfdf5
    style Live_VSCode fill:#064e3b,stroke:#06b6d4,stroke-width:2px,color:#ecfdf5
    
    style Live_API fill:#3b0764,stroke:#a855f7,stroke-width:2px,color:#f5d0fe
    style Live_Tower fill:#3b0764,stroke:#c084fc,stroke-width:2px,color:#f5d0fe
    style Live_Browser fill:#3b0764,stroke:#9333ea,stroke-width:2px,color:#f5d0fe
    style Live_Core fill:#3b0764,stroke:#7e22ce,stroke-width:2px,color:#f5d0fe

    style BACKBONE fill:#1e1b4b,stroke:#6366f1,stroke-width:2px,color:#e0e7ff
```

---

### 📌 ৬টি রিপোজিটরি ডেপ্লয়মেন্টের সংক্ষিপ্ত ছক:

| ক্রমিং | সোর্স রিপোজিটরি | ডেপ্লয় প্ল্যাটফর্ম | সার্ভিসের ধরন / আউটপুট | লাইভ URL / আউটপুট |
|---|---|---|---|---|
| ১ | **`supremeai-studio`** | **Vercel** (Frontend) | React / Vite Web Console | `https://supremeai-studio.vercel.app` |
| ২ | **`supremeai-api`** | **Render** (Cloud) | FastAPI Web Service | `https://supremeai-api-ulw0.onrender.com` |
| ৩ | **`MCP Control Tower`** | **Render** (Cloud) | Node.js MCP Proxy Web Service | `https://supremeai-mcp-tower.onrender.com` |
| ৪ | **`supremeai-browser`** | **Render** (Cloud) | Headless Browser Runtime Service | Private Internal Service |
| ৫ | **`supremeai-core`** | **Render** (Cloud) | Background Worker / Task Runner | Autonomous Background Worker |
| ৬ | **`supremeai-vscode`** | **VS Code Marketplace / Desktop** | Extension Bundle (VSIX) / Desktop App | VS Code Marketplace / Tauri Desktop |

