# সুপ্রিমএআই VS Code এক্সটেনশন - আর্কিটেকচার গাইড (বাংলায়)

## ১. প্রযুক্তিগত ওভারভিউ

সুপ্রিমএআই একটি **রিয়েল-টাইম মেশিন লার্নিং-ভিত্তিক এআই-ড্রাইভেন ডেভেলপমেন্ট সহায়ক**। এটি VS Code এক্সটেনশন হিসেবে কাজ করে এবং ব্যবহারকারীর কোডিং প্যাটার্নকে শিখে, তার পছন্দের স্টাইল মেনে রাখে এবং স্মার্ট সাজেশন দেয়।

---

## ২. মূল কম্পোনেন্ট স্ট্রাকচার

```
supremeai-vscode-extension/
├── src/
│   ├── extension.ts              # মূল এন্ট্রি পয়েন্ট
│   ├── types/
│   │   └── index.ts              # সমস্ত টাইপ ডেফিনেশন
│   ├── services/
│   │   ├── SupremeAIService.ts   # ব্যাকএন্ড API কমিউনিকেশন
│   │   └── AuthService.ts        # ব্যবহারকারী অথেন্টিকেশন
│   ├── handlers/
│   │   ├── CodeEditHandler.ts    # কোড চেঞ্জ ট্র্যাকিং
│   │   ├── ErrorHandler.ts       # এরর রিপোর্টিং
│   │   ├── FeedbackHandler.ts    # ইউজার ফিডব্যাক
│   │   └── CodeFlowHandler.ts    # কোড ফ্লো বিশ্লেষণ
│   ├── providers/
│   │   ├── SupremeAISidebarProvider.ts    # সাইডবার UI
│   │   ├── SupremeAIChatProvider.ts       # চ্যাট ইন্টারফেস
│   │   └── SupremeAIActivityProvider.ts   # অ্যাক্টিভিটি ট্রি
│   └── dataconnect-generated/    # Firebase DataConnect জেনারেটেড
├── package.json                  # এক্সটেনশন মেটাডেটা
└── package.nls.bn.json          # বাংলা লোকালাইজেশন
```

---

## ৩. কম্পোনেন্ট ডিজাইন (Bangla Description)

### ৩.১ Extension.ts - মূল কন্ট্রোলার

- **ভাস্য**: এক্সটেনশনের লাইফ সাইকেল ম্যানেজ করে
- **কাজ**: সব সার্ভিস আর হ্যান্ডলার ইনিশিয়ালাইজ করে, কমান্ড রেজিস্টার করে
- **গুরুত্ব**: সবকিছুর সেন্ট্রাল অর্গানাইজেশন

### ৩.২ SupremeAIService - ব্যাকএন্ড কনেকশন

- **ভাস্য**: VS Code এবং SupremeAI ক্লাউড ব্যাকএন্ডের মধ্যে যোগাযোগ
- **কার্যক্রম**:
  - `POST /api/knowledge/learn` - কোড শিখানোর জন্য
  - `POST /api/knowledge/failure` - এরর রিপোর্ট করা
  - `POST /api/chat/message` - চ্যাট মেসেজ পাঠানো
  - `POST /api/codeflow/analyze` - কোডফ্লো বিশ্লেষণ
- **বিশেষতা**: Axios ইন্টারসেপ্টরে অথেন্টিকেশন টোকেন যুক্ত করা

### ৩.৩ CodeEditHandler - রিয়েল-টাইম লার্নিং

- **ভাস্য**: ব্যবহারকারীর কোড এডিটিটি ক্য্যাপচার করে শিখানোর জন্য
- **কিভাবে কাজ করে**:
  1. `onDidChangeTextDocument` ইভেন্ট শুনে
  2. ২ সেকেন্ড ডিবাউন্স করে (যাতে টাইপিং শেষ হয়)
  3. গিট ডিফ বা সেভড সংস্করণ থেকে অরিজিনাল কোড খুঁজে বের করে
  4. শুধু পরিবর্তনকারী কোড সাবমিট করে
- **সেভিং মেকানিজ্ম**: `context.globalState` এ বেসলাইন কোড স্টোর করে

### ৩.৪ ErrorHandler - এরর ট্র্যাকিং এবং সমাধান

- **ভাস্য**: কম্পাইলার/রানটাইম এররগুলোকে AI-এর কাছে পাঠায়
- **কার্যক্রম**:
  - Problem Matcher থেকে এরর পার্স করে
  - `ErrorReport` ফরম্যাটে ডাটা প্রসেস করে
  - সম্ভাব্য সমাধানের জন্য ব্যাকএন্ডে পাঠায়
- **ডিবাগিং**: Stack trace এবং কোড স্নিপেট সহজলভ্য করে

### ৩.৫ FeedbackHandler - ইউজার ইনপুট প্রসেসিং

- **ভাস্য**: ইউজারের সাজেশন গ্রহণ/অস্বীকারের ফিডব্যাক
- **কাজ**:
  - `supremeai.acceptSuggestion` কমান্ড হ্যান্ডেল করে
  - `SuggestionFeedback` টাইপে ডাটা গঠন করে
  - ব্যাকএন্ডে ফিডব্যাক পাঠায় (যাতে AI শিখতে পারে)

### ৩.৬ CodeFlowHandler - কোডবে�이সিক বিশ্লেষণ

- **ভাস্য**: কোডবেইসিক (Codebase) স্তরে বিশ্লেষণ করে
- **ফিচার**:
  - ডিপেন্ডেন্সি গ্রাফ জেনারেট করে
  - সিকিউরিটি ইস্যু ডিটেক্ট করে
  - কোড স্মৃতি (Pattern) চালু করে
  - হেলথ স্কোর গণনা করে

### ৩.৭ প্রোভাইডার्स - UI কম্পোনেন্ট

- **SupremeAISidebarProvider**: ওয়েবভিউইউ ব্যবহার করে সাইডবার তৈরি
- **SupremeAIChatProvider**: চ্যাট ইন্টারফেস
- **SupremeAIActivityProvider**: ট্রি ভিউয়ে অ্যাক্টিভিটি দেখায়

---

## ৪. রিয়েল এআই এক্সটেনশন কীভাবে হবে?

### ৪.১ ডাটা ফ্লো

```
VS Code → CodeEditHandler → SupremeAIService → Backend → ML Model → Response
   ↑                                                                   ↓
   ←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←
```

### ৪.২ লার্নিং মেকানিজ্ম

| ধাপ | বর্ণনা                       | বাংলা                   |
| --- | ---------------------------- | ----------------------- |
| ১   | কোড চেঞ্জ ডিটেক্ট            | কোড পরিবর্তন detect করা |
| ২   | অরিজিনাল vs এডিটেড কোড তুলনা | মূল আপত্তি তুলনা        |
| ৩   | ব্যাকএন্ডে লার্নিং রিকোয়ার্স | শিখানোর রিকোয়ার্স       |
| ৪   | ML মডেল প্যাটার্ন স্টোর      | প্যাটার্ন স্টোর         |
| ৫   | কন্টекстুअલ সাজেশন           | প্রসঙ্গভিত্তিক সাজেশন   |

### ৪.৩ AI মডেলের ভূমিকা

- **CodeGeeX4**: কোড জেনারেশন এবং সাজেশনের জন্য
- **কাস্টম লিন্সেনিং মডেল**: ব্যবহারকারীর স্টাইলকে শিখে
- **কোডবেইসিক এনালিসিস**: রিপোজিটরির সম্পূর্ণ মানচিত্র তৈরি

---

## ৫. বাংলায় সুগ্গেশন - কীভাবে একটি আসল AI এক্সটেনশন হবে?

### ৫.১ LLM-এর সাথে সরাসরি ইন্টিগ্রেশন

**কী যোগ করবেন:**

```typescript
// new file: src/services/AIService.ts
import { OpenAI } from "openai";

export class AIService {
  private openai: OpenAI;

  async generateCode(prompt: string, context: any) {
    return await this.openai.chat.completions.create({
      model: "gpt-4",
      messages: [{ role: "user", content: prompt }],
      tools: [
        {
          type: "code_interpreter",
          // Allow AI to run and test code
        },
      ],
    });
  }
}
```

### ৫.২ অ্যাসিস্ট্যান্ট মেমরি সিস্টেম

**কী যোগ করবেন:**

- ব্যবহারকারীর পছন্দের কোড স্টাইল স্টোর করার ডাটাবেস
- রিপোজিটরির হিস্টোরি থেকে কন্টেক্স্ট বানানো
- ইতিহাসস্থলীয় সাজেশনের জন্য মেমরি

### ৫.৩ রিয়েল-টাইম কোড রিভিউ

**কী যোগ করবেন:**

- প্রতিটি কী-স্ট্রোকের পরে AI ইনফিলেন্সার দেখানো
- অন-দিমান্ডিং এরর ডিটেকশন
- স্বয়ংক্রিয় রিফ্যাকচуар সাজেশন

### ৫.৪ মাল্টি-ল্যাঙ্গুয়েজ সাপোর্ট

**কী যোগ করবেন:**

```typescript
// src/languages/languageDetector.ts
export class LanguageDetector {
  detectLanguage(fileExtension: string): LanguageConfig {
    const configs = {
      ts: { model: "gpt-4", templ: tsTemplate },
      py: { model: "codex", template: pyTemplate },
      java: { model: "codegeex", template: javaTemplate },
    };
    return configs[fileExtension] || configs["ts"];
  }
}
```

### ৫.৫ কোড স্ন্যাপশট বেসড সাজেশন

**কী যোগ করবেন:**

- ফাইল সেভ করার সময় কোডের স্ন্যাপশট নেয়
- পূর্ববর্তী স্ন্যাপশটের সাথে পার্থক্য বের করে
- AI-এর সাথে পাঠায় শুধু পরি঵র্তনগুলো

### ৫.৬ ভিজ্যুয়ালাইজেশন ড্যাশবোর্ড

**কী যোগ করবেন:**

- কোডক্যোয়ার্ড ম্যাপ (যে কোড কোথায় কল করে)
- লার্নিং প্রগ্রেস চার্ট
- এরর ট্র্যাকিং ড্যাশবোর্ড

---

## ৬. প্রোডাকশন রিডিনেসেস চেকলিস্ট

- [x] AI Service ইমপ্লিমেন্ট করা (`src/ai/`)
- [x] OpenAI API ইন্টিগ্রেশন
- [x] বাংলা লজ মেসেজ সম্পূর্ণ
- [x] TypeScript কম্পাইল সফল
- [ ] Backend API এন্ডপয়েন্টস (need to implement)
- [ ] VS Code Marketplace-এ পাবলিশ

---

## ৭. রিপোজিটরি স্ট্রাকচার

```
supremeai-vscode-extension/
├── src/
│   ├── extension.ts
│   ├── types/
│   ├── services/
│   │   ├── SupremeAIService.ts
│   │   └── AuthService.ts
│   ├── handlers/
│   │   ├── CodeEditHandler.ts
│   │   ├── ErrorHandler.ts
│   │   ├── FeedbackHandler.ts
│   │   └── CodeFlowHandler.ts
│   ├── providers/
│   │   ├── SupremeAISidebarProvider.ts
│   │   ├── SupremeAIChatProvider.ts
│   │   └── SupremeAIActivityProvider.ts
│   ├── ai/                         # ← নতুন AI সার্ভিসেস
│   │   ├── AIService.ts            # ← OpenAI ইন্টিগ্রেশন
│   │   ├── CodeGenerationService.ts # ← কোড জেনারেশন
│   │   ├── CodeReviewService.ts     # ← অটোম্যাটিক রিভিউ
│   │   └── ContextBuilder.ts        # ← কন্টেক্স্ট তৈরি
│   └── dataconnect-generated/
├── package.json
└── ARCHITECTURE_BN.md
```

---

## ৮. বাংলা ট্রান্সলেশন গাইড

| ইংরেজি             | বাংলা              |
| ------------------ | ------------------ |
| AI Assistant       | এআই সহায়ক          |
| Real-time Learning | রিয়েল-টাইম শিখুন  |
| Code Analysis      | কোড বিশ্লেষণ       |
| Suggestion         | প্রস্তাব           |
| Error Resolution   | এরর সমাধান         |
| CodeFlow           | কোড ফ্লো           |
| Dashboard          | ড্যাশবোর্ড         |
| Feedback           | ফিডব্যাক           |
| Security Issues    | সুরক্ষা সমস্যা     |
| Dependency Graph   | ডিপেন্ডেন্সি গ্রাফ |
