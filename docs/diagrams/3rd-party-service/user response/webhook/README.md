# 🔗 SupremeAI ওয়েবহুক আর্কিটেকচার (Inbound & Outbound Webhook Flow)

আমাদের সিস্টেমে ওয়েবহুক কীভাবে কাজ করে—বাহির থেকে আসা ইভেন্ট (Inbound) এবং আমাদের সিস্টেম থেকে বাহিরে পাঠানো অ্যালার্ট (Outbound)—তার স্পষ্ট ডায়াগ্রাম।

---

```mermaid
flowchart TD
    %% ========================================================
    %% INBOUND WEBHOOKS
    %% ========================================================
    subgraph INBOUND [" 📥 ১. ইনবাউন্ড ওয়েবহুক (Inbound: বাইরে থেকে সিস্টেমে প্রবেশ) "]
        direction TB
        Src_GH["GitHub Webhook<br/>(PR Opened / Merged / CI Failed)"]
        Src_Render["Render Deploy Hook<br/>(Deploy Success / Failed)"]
        Src_External["Third-party Event Triggers"]

        Tower_Receiver["🏰 <b>MCP Tower Webhook Receiver</b>"]
        Verify_HMAC{"HMAC-SHA256 সিগনেচার<br/>ভ্যালিডেশন (Security Guard)"}
        
        Action_Inbound["⚡ ইভেন্ট ডিসপ্যাচ:<br/>• PR ওপেন করা (bridge-intake)<br/>• বোর্ডে নতুন P0 ইস্যু তৈরি<br/>• মেমোরি স্টেট আপডেট"]

        Src_GH --> Tower_Receiver
        Src_Render --> Tower_Receiver
        Src_External --> Tower_Receiver

        Tower_Receiver --> Verify_HMAC
        Verify_HMAC -- "বৈধ (Signature Match)" --> Action_Inbound
        Verify_HMAC -- "অবৈধ (Tampered)" --> Drop["🛑 ড্রপ ও ব্লক (401/403)"]
    end

    %% ========================================================
    %% OUTBOUND WEBHOOKS
    %% ========================================================
    subgraph OUTBOUND [" 📤 ২. আউটবাউন্ড ওয়েবহুক (Outbound: সিস্টেম থেকে বাইরে পাঠানো) "]
        direction TB
        InternalEvent["সিস্টেম ইভেন্ট ট্রিগার<br/>(CI Failure / Incident / Task Completed)"]
        
        Signer["🔐 <b>HMAC-SHA256 Signer</b><br/>(Header: <code>X-SupremeAI-Signature</code>)"]
        
        subgraph DESTINATIONS ["বাইরের নোটিফিকেশন গন্তব্য"]
            Dest_Telegram["📱 Telegram Bot API<br/>(ইনস্ট্যান্ট অ্যালার্ট ও অডিট লগ)"]
            Dest_Slack["💬 Slack / Discord Webhook"]
            Dest_Custom["🌐 কাস্টম ইউজার সার্ভার / Webhook URL"]
        end

        InternalEvent --> Signer
        Signer --> Dest_Telegram
        Signer --> Dest_Slack
        Signer --> Dest_Custom
    end

    %% Styling
    style INBOUND fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc
    style Src_GH fill:#1e293b,stroke:#0284c7,stroke-width:1px,color:#e0f2fe
    style Src_Render fill:#1e293b,stroke:#0284c7,stroke-width:1px,color:#e0f2fe
    style Src_External fill:#1e293b,stroke:#0284c7,stroke-width:1px,color:#e0f2fe
    style Tower_Receiver fill:#1e1b4b,stroke:#6366f1,stroke-width:2px,color:#ffffff
    style Verify_HMAC fill:#451a03,stroke:#d97706,stroke-width:1px,color:#fef3c7
    style Action_Inbound fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#ecfdf5
    style Drop fill:#881337,stroke:#ef4444,stroke-width:1px,color:#ffffff

    style OUTBOUND fill:#0f172a,stroke:#a855f7,stroke-width:2px,color:#f8fafc
    style InternalEvent fill:#1e293b,stroke:#8b5cf6,stroke-width:1px,color:#f5f3ff
    style Signer fill:#3b0764,stroke:#c084fc,stroke-width:2px,color:#ffffff
    style DESTINATIONS fill:#1e1b4b,stroke:#818cf8,stroke-width:1px,color:#f8fafc
    style Dest_Telegram fill:#082f49,stroke:#0284c7,stroke-width:1px,color:#e0f2fe
    style Dest_Slack fill:#082f49,stroke:#0284c7,stroke-width:1px,color:#e0f2fe
    style Dest_Custom fill:#082f49,stroke:#0284c7,stroke-width:1px,color:#e0f2fe
```

