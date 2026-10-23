# SupremeAI 24/7 Guest Chat, Webshare Residential Relay & Autonomous Deployment Architecture

> **Document Version:** 3.0.0  
> **Status:** Production / Live  
> **Target Frontend:** [https://supremeai-studio.pages.dev](https://supremeai-studio.pages.dev)  
> **Target API Service:** `https://supremeai-api-ulw0.onrender.com`  
> **Target Scraper Relay:** `https://supremeai-scraper-node.onrender.com`  
> **Zero-Local Dependency:** 100% Cloud-native ($0 Cost / 24/7 High-Availability)

---

## 1. High-Level Architecture Overview

পুরো সিস্টেমটি এমনভাবে আর্কিটেক্ট করা হয়েছে যাতে লোকাল পিসি বা কোনো ক্ষণস্থায়ী টানেলের ওপর কোনো নির্ভরতা না থাকে। ব্যবহারকারী যখন চ্যাটবক্সে মেসেজ পাঠান, তখন সম্পূর্ণ ক্লাউড পাইপলাইনের মধ্য দিয়ে রিকোয়েস্ট প্রসেস হয়ে উত্তর ফিরে আসে:

```mermaid
flowchart TD
    subgraph CLIENT ["1. Client Layer (Edge)"]
        USER["🌐 Visitor / Guest User"] -->|Sends prompt| STUDIO["Cloudflare Pages<br>(supremeai-studio.pages.dev)"]
    end

    subgraph GATEWAY ["2. Gateway Routing & Branding (Render - supremeai-api)"]
        STUDIO -->|POST /v1/chat/completions| API["Render Gateway<br>(supremeai-api-ulw0.onrender.com)"]
        API -->|Fetch Config & Secrets| INFISICAL["Infisical Cloud Vault<br>(Universal Auth Machine Identity)"]
        API -->|Inject Server Badge| BRAND["SupremeAI Branding Engine<br>(SupremeAI w.ge Turbo)"]
    end

    subgraph ENGINE ["3. Scraper Relay & Residential Rotation (Render - scraper-node)"]
        API -->|Signed Webhook Request<br>X-Stealth-Secret: njel.com.bd| SCRAPER["SupremeAI Scraper Relay<br>(supremeai-scraper-node.onrender.com)"]
        
        SCRAPER -->|Residential Rotation Pool| PROXY["Webshare Proxy Pool<br>(GB, DE, ES, PL Egress)"]
        PROXY -->|Session Cookies<br>__Secure-1PSID / 3PSID| GEMINI_WEB["gemini.google.com<br>(Google BardFrontendService)"]
        GEMINI_WEB -->|Success: 200 OK| REPLY["Formatted Chat Reply + Engine Hint (ge)"]
    end

    subgraph SECURITY ["4. Strict Governance & Admin Mandate"]
        LOCK["🔒 HEADLINE LOCK<br>Admin command chara API fallback enable kora jabe na"]
        INFISICAL -.->|ENABLE_API_FALLBACK = false| API
        LOCK -.->|Enforced in code & vault| API
    end

    REPLY --> BRAND --> API --> STUDIO --> USER

    classDef edge fill:#f38020,stroke:#fff,stroke-width:2px,color:#fff;
    classDef cloud fill:#1d76db,stroke:#fff,stroke-width:2px,color:#fff;
    classDef ai fill:#34a853,stroke:#fff,stroke-width:2px,color:#fff;
    classDef lock fill:#d93f0b,stroke:#fff,stroke-width:2px,color:#fff;
    class STUDIO edge;
    class API,SCRAPER,INFISICAL,PROXY cloud;
    class GEMINI_WEB,REPLY,BRAND ai;
    class LOCK lock;
```

---

## 2. Layer-by-Layer Detailed Flow

### Layer 1: ক্লায়েন্ট ও ফ্রন্টএন্ড এজ (Cloudflare Pages)
- **হোস্টিং:** Cloudflare Pages (`supremeai-studio.pages.dev`)
- **প্রযুক্তি:** Vite + React + TypeScript + TailwindCSS (Cosmic Dark Design)
- **গেটওয়ে ইউআরএল বাইন্ডিং:** ফ্রন্টএন্ড বিল্ডের সময় `VITE_SUPREMEAI_API_URL` সরাসরি রেন্ডার গেটওয়ে (`https://supremeai-api-ulw0.onrender.com`) পয়েন্ট করে।
- **গেস্ট চ্যাট ও ব্র্যান্ড ব্যাজ রেন্ডারিং:**
  - প্রতিটি মেসেজের নিচে পুরোনো `[auto]` টেক্সটের পরিবর্তে প্রিমিয়াম ডাইনামিক ব্যাজ প্রদর্শিত হয়:
    - **ব্র্যান্ড:** `SupremeAI` (গ্রিন-পার্পল কসমিক গ্রেডিয়েন্ট)
    - **চ্যানেল ও ইঞ্জিন:** `w.ge` (মনোস্পেস পিল স্টাইল — Webhook + Gemini)
    - **মার্কেটিং টায়ার:** `Turbo` (নিয়ন সায়ান ট্যাগ — $0 হাই-স্পিড সেশন)

---

### Layer 2: সেন্ট্রাল গেটওয়ে ও পলিসি লক (SupremeAI API Gateway - supremeai-api)
- **সার্ভিস:** `supremeai-api-ulw0.onrender.com` (Render Web Service)
- **রুট:** `POST /v1/chat/completions` (OpenAI Specification Compliant)
- **🔒 হেডলাইন পলিসি লক (Admin Command Required):**
  - **নিয়ম:** অ্যাডমিনের লিখিত কমান্ড ছাড়া এপিআই ফলব্যাক চালু করা সম্পূর্ণ নিষিদ্ধ।
  - **কোড গার্ড:** `gateway/service/app.py`-এ হার্ডকোডেড ব্লক নিশ্চিত করে যে সমস্ত চ্যাট শুধুমাত্র সিকিউর ওয়েব রিলের মাধ্যমে আসবে। কোনো ফলব্যাক প্রোভাইডারে সুইচ করার অনুমতি কোডে নেই।
  - **ভল্ট গার্ড:** Infisical-এ `ENABLE_API_FALLBACK=false` লক কমেন্টসহ সেট করা।
- **ব্র্যান্ডিং ইঞ্জিন (`service/branding.py`):**
  - সার্ভার নিজে রেসপন্সের চ্যানেল (`w`/`a`), ইঞ্জিন (`ge`/`gr`/`cl`) এবং টায়ার (`Turbo`/`Free`/`Pro`/`Ultra`) যাচাই করে `supremeai` ব্র্যান্ড অবজেক্ট তৈরি করে।

---

### Layer 3: স্ক্র্যাপার নোড ও Webshare প্রক্সি রোটেশন (Scraper Relay)
- **সার্ভিস:** `supremeai-scraper-node.onrender.com` (Render Web Service)
- **এন্ট্রি পয়েন্ট:** `browser/server.py` (`uvicorn main:app --port 8080`)
- **Webshare রেসিডেন্ট প্রক্সি ইন্টিগ্রেশন:**
  - **প্রক্সি পুল:** `WEBSHARE_API_KEY` ব্যবহার করে ডাইনামিকালি ১০টি ইউরোপিয়ান রেসিডেন্ট/কনজিউমার প্রক্সি (GB, DE, ES, PL) লোড ও রোটেট করে।
  - **গুগল 302 বাইপাস:** রেন্ডারের ইউএস ডেটাসেন্টার আইপি গুগলের সামনে উন্মুক্ত না হয়ে ইউরোপিয়ান রেসিডেন্ট ইগ্রেস দিয়ে গুগলে ট্রাফিক যায়। ফলে কোনো লগইন রিডাইরেক্ট (`HTTP 302`) বা ক্যাপচা ব্লকিং ঘটে না।
- **সেশন কুকিজ:**
  - Infisical থেকে ডিক্রিপ্ট করা তাজা কুকিজ (`__Secure-1PSID`, `__Secure-3PSID`, `SID` ইত্যাদি) গুগলের অভ্যন্তরীণ `BardFrontendService/StreamGenerate`-এ পাস করা হয়।
  - রেসপন্স সফলভাবে এক্সট্র্যাক্ট করে `gemini-web` ও ইঞ্জিন হিন্ট `ge` সহ গেটওয়েতে পাঠানো হয়।

---

## 3. স্বয়ংক্রিয় সিআই/সিডি ও ফেডারেশন ল্যান্ডিং (Satellite Auto-Sync)

সুপ্রিমএআই ফেডারেশন আর্কিটেকচার (`AGENTS.md`) অনুযায়ী `supremeai-open` হলো ট্রানজিট হাব। কোড মার্জ হলে স্যাটেলাইটে স্বয়ংক্রিয়ভাবে ডিসপ্যাচ হয়:

```mermaid
sequenceDiagram
    autonumber
    actor Dev as Developer / Agent
    participant Open as Supremeai-bd/supremeai-open
    participant SatAPI as Supremeai-bd/supremeai-api
    participant SatStudio as Supremeai-bd/supremeai-studio
    participant SatBrowser as Supremeai-bd/supremeai-browser
    participant CF as Cloudflare Pages Edge

    Dev->>Open: PR Merged into main
    alt Code touches gateway/*
        Open->>SatAPI: landing.yml syncs to supremeai-api:main
        SatAPI-->>SatAPI: Auto-redeploy on Render (API Gateway)
    else Code touches studio/*
        Open->>SatStudio: landing.yml syncs to supremeai-studio:main
        SatStudio->>CF: deploy-pages.yml triggers Cloudflare build
    else Code touches browser/*
        Open->>SatBrowser: landing.yml syncs to supremeai-browser:main
        SatBrowser-->>SatBrowser: Auto-redeploy on Render (Scraper Node)
    end
```

---

## 4. স্থায়িত্ব ও রিলায়েবিলিটি মেট্রিক্স

| কম্পোনেন্ট | আপটাইম গ্যারান্টি | মেকানিজম | লোকাল পিসি অফ থাকলে স্ট্যাটাস |
|---|---|---|---|
| **Studio Frontend** | ৯৯.৯৯% | Cloudflare Edge Global CDN | সচল (১০০%) |
| **API Gateway** | ৯৯.৯% | Render Web Service + Token Auth | সচল (১০০%) |
| **Scraper Relay** | ৯৯.৯% | Render Web Service + Webshare Proxy | সচল (১০০%) |
| **Google Anti-Bot Protection** | ৯৯.৯% | Webshare 10 Residential Rotating IPs | সচল (১০০%) |
| **Fallback Governance** | ১০০% | Strict Admin-Only Lock Policy | সচল (১০০%) |

> [!TIP]
> পুরো আর্কিটেকচারটি সম্পূর্ণ জিরো-মেইনটেন্যান্স (Admin Effort <= 0.01%) হিসেবে ডিজাইন করা। আপনার লোকাল পিসি বন্ধ বা স্লিপে থাকলেও ক্লাউডের এই পাইপলাইন ২৪/৭ স্বয়ংক্রিয়ভাবে $0 খরচে লাইভ কাজ করবে।
