# 🌐 Vercel ফ্রন্টএন্ড হোস্টিং আর্কিটেকচার

- **ক্যাটাগরি:** Frontend Edge Cloud & Serverless Deployment
- **ব্যবহার:** `supremeai-studio` (React / Next.js) গ্লোবাল এজ সিডিএন-এ হোস্ট করা

```mermaid
flowchart LR
    classDef svc fill:#161b22,stroke:#ffffff,stroke-width:1.5px,color:#ffffff;
    classDef gate fill:#161b22,stroke:#30363d,stroke-width:1px,color:#c9d1d9;

    StudioRepo["supremeai-studio repo"] --> Vercel["🌐 Vercel Global Edge<br/>(supremeai-studio.vercel.app)"]

    class StudioRepo gate;
    class Vercel svc;
```

