# 🗺️ SupremeAI রিপোজিটরি আর্কিটেকচার ডায়াগ্রাম

এই ফোল্ডারে SupremeAI ইকোসিস্টেমের বিভিন্ন আর্কিটেকচার, ডোমেইন সম্পর্ক এবং সিস্টেম ডিজাইনের ভিজ্যুয়াল ডায়াগ্রামগুলো সংরক্ষিত আছে।

---

## 📑 সূচিপত্র
1. **১. ৭টি প্রধান রিপোজিটরির সাথে supremeai-open এর সম্পর্ক**
2. **২. রিপোজিটরিগুলোর বিস্তারিত ভূমিকা**
3. **৩. ডেটা ফ্লো ও সিঙ্ক মেকানিজম**

---

## 🚀 ১. ৭টি প্রধান রিপোজিটরির সাথে `supremeai-open` এর সম্পর্ক

`supremeai-open` হলো আমাদের সেন্ট্রাল ওপেন হাব (Central Open Hub / Bridge)। এটি বাইরের এজেন্ট ও ডেভেলপারদের কাজের একক প্রবেশদ্বার (Single Door Gateway) হিসেবে কাজ করে এবং বাকি ৭টি স্যাটেলাইট রিপোজিটরির সাথে সংযুক্ত থাকে।

```mermaid
flowchart TD
    %% Main Open Hub
    subgraph HUB [" 🚀 সেন্ট্রাল ওপেন রিপোজিটরি (SSOT Bridge) "]
        OpenRepo["supremeai-open<br/>(Monorepo Mirror & Bridge Hub)"]
        subgraph InternalMirrors ["Open Repo-র অভ্যন্তরীণ ডোমেইন মিরর"]
            M_Core["core/*"]
            M_GW["gateway/*"]
            M_Studio["studio/*"]
            M_Browser["browser/*"]
            M_VSCode["vscode/*"]
            M_CI["scripts/ci/* ও Guards"]
        end
        OpenRepo --- InternalMirrors
    end

    %% External Satellite Repos
    subgraph SATELLITES [" 🛰️ প্রধান ৭টি স্যাটেলাইট রিপোজিটরি "]
        R_Main["1. supremeai<br/>(মাস্টার মনোরেপো / Crown Jewel)"]
        R_Core["2. supremeai-core<br/>(কার্নেল, ব্রেইন ও অটোনোমাস এজেন্ট)"]
        R_API["3. supremeai-api<br/>(FastAPI গেটওয়ে, রাউটার ও সিকিউরিটি)"]
        R_Studio["4. supremeai-studio<br/>(Next.js / React ড্যাশবোর্ড ও UI)"]
        R_Browser["5. supremeai-browser<br/>(স্টিলথ ইঞ্জিন ও ওয়েব স্ক্র্যাপার)"]
        R_VSCode["6. supremeai-vscode<br/>(IDE এক্সটেনশন ও ডেস্কটপ ব্রিজ)"]
        R_Infra["7. MCP Control Tower / Infra<br/>(ইনফ্রাস্ট্রাকচার, ডেটাবেজ ও ক্লাউড গেট)"]
    end

    %% Relationships and Flows
    OpenRepo -->|১. শিডিউলড রোলিং ট্রেইন সিঙ্ক| R_Main
    
    M_Core <==>|২. দ্বিমুখী ডোমেইন মিরর সিঙ্ক| R_Core
    M_GW <==>|৩. এপিআই ও রাউট কন্ট্রাক্ট সিঙ্ক| R_API
    M_Studio <==>|৪. ফ্রন্টএন্ড কম্পোনেন্ট সিঙ্ক| R_Studio
    M_Browser <==>|৫. স্ক্র্যাপার ও ব্রাউজার রানটাইম সিঙ্ক| R_Browser
    M_VSCode <==>|৬. আইডিই এক্সটেনশন কোড সিঙ্ক| R_VSCode

    R_Infra -->|৭. MCP কন্ট্রোল গেট ও টুলস প্রক্সি| OpenRepo

    %% Styling
    style OpenRepo fill:#1e293b,stroke:#38bdf8,stroke-width:3px,color:#f8fafc
    style R_Main fill:#4c1d95,stroke:#a855f7,stroke-width:2px,color:#f8fafc
    style R_Core fill:#0f172a,stroke:#3b82f6,stroke-width:2px,color:#f8fafc
    style R_API fill:#0f172a,stroke:#10b981,stroke-width:2px,color:#f8fafc
    style R_Studio fill:#0f172a,stroke:#f59e0b,stroke-width:2px,color:#f8fafc
    style R_Browser fill:#0f172a,stroke:#ef4444,stroke-width:2px,color:#f8fafc
    style R_VSCode fill:#0f172a,stroke:#06b6d4,stroke-width:2px,color:#f8fafc
    style R_Infra fill:#1c1917,stroke:#eab308,stroke-width:2px,color:#f8fafc
```

---

## 📦 ২. রিপোজিটরিগুলোর বিস্তারিত ভূমিকা

| ক্রমিং | রিপোজিটরির নাম | প্রধান ভূমিকা | ওপেন হাবের ডিরেক্টরি |
|---|---|---|---|
| ১ | **`supremeai`** | মূল প্রাইভেট মাস্টার মনোরেপো। সমস্ত কোডের চূড়ান্ত রূপ এখানে কনসোলিডেট হয়। | - |
| ২ | **`supremeai-core`** | সিস্টেমের মস্তিষ্ক—কার্নেল, অটোনোমাস লুপ ও ডিসপ্যাচার লজিক। | `core/*` |
| ৩ | **`supremeai-api`** | সেন্ট্রাল গেটওয়ে, ব্যাকএন্ড এন্ডপয়েন্ট, অথেনটিকেশন ও রেট লিমিটিং। | `gateway/*` |
| ৪ | **`supremeai-studio`** | ইউজার এবং অ্যাডমিন ড্যাশবোর্ড, মনিটরিং ইন্টারফেস (Next.js/React)। | `studio/*` |
| ৫ | **`supremeai-browser`** | ব্রাউজার অটোমেশন, অ্যান্টি-ডিটেকশন স্টিলথ ইঞ্জিন এবং ডেটা কালেকশন। | `browser/*` |
| ৬ | **`supremeai-vscode`** | ডেভেলপারদের জন্য VSCode এক্সটেনশন এবং ডেস্কটপ/মোবাইল ব্রিজ। | `vscode/*` |
| ৭ | **`MCP Control Tower / Infra`** | ইনফ্রাস্ট্রাকচার, Supabase ডেটাবেজ, Redis ক্যাশ ও MCP সিকিউরিটি ভেরিফিকেশন গেট। | `infrastructure/*` |

---

## 🔄 ৩. ডেটা ফ্লো ও সিঙ্ক মেকানিজম

১. **একক প্রবেশদ্বার (Single Door Invariant):** 외부 এক্সটার্নাল এজেন্ট এবং ডেভেলপাররা প্রথমে `supremeai-open` এ কাজ জমা দেয়।  
২. **স্বয়ংক্রিয় ভেরিফিকেশন (CI Guards):** কোড পরিবর্তন হলে স্বয়ংক্রিয় গার্ডস ও টেস্ট দ্বারা সততা নিশ্চিত করা হয়।  
৩. **রোলিং ট্রেইন সিঙ্ক (Rolling Train Sync):** ১০ মিনিট পর পর শিডিউল অনুযায়ী স্বয়ংক্রিয়ভাবে সংশ্লিষ্ট স্যাটেলাইট রিপোতে কোড পৌঁছে যায়।
