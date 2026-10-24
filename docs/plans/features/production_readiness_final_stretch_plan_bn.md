---
id: production-readiness-final-stretch
subject: "🏗️ ইমপ্লিমেন্টেশন প্ল্যান: বাকি ১৫% প্রডাকশন রেডিনেস পূরণ"
document_role: implementation
planning_authority: Architecture Circle
canonical: false
status: active
evidence_state: unverified
disposition: retain
last_verified: 2026-09-17
supersedes: []
superseded_by: []
related: docs/plans/features/production_hardening_and_p1_p2_roadmap_2026_09_11.md
target_scope: supremeai_internal
---

# 🏗️ ইমপ্লিমেন্টেশন প্ল্যান: বাকি ১৫% প্রডাকশন রেডিনেস পূরণ

> **তারিখ:** ১২ সেপ্টেম্বর ২০২৬ | **ব্র্যাঞ্চ:** `main` @ `78ddb9bc`
> **লক্ষ্য:** ৪টি বাকি P1/P2 হার্ডেনিং কাজ সম্পন্ন করে SupremeAI কে ১০০% প্রডাকশন-রেডি করা।

---

## ⚠️ গুরুত্বপূর্ণ নোট (রিভিউ করুন)

> [!IMPORTANT]
> **Cookie Migration:** `localStorage` থেকে `httpOnly` কুকিতে সরানো মানে লগইন-এ পুরোনো সেশন অটোমেটিক এক্সপায়ার হবে না — গ্রেসফুল ডুয়াল-রিড পিরিয়ড রাখা হবে যাতে ইউজার হঠাৎ লগ-আউট না হন।

> [!WARNING]
> **Scraper Auth Gate:** `/api/scraper/*` রুটে `get_current_admin` অ্যাড করলে যেকোনো নন-অ্যাডমিন বা টেস্টিং স্ক্রিপ্ট যদি ক্রেডেনশিয়াল ছাড়া স্ক্র্যাপার ডাকে, সেটা 401 পাবে। Postman/টেস্ট স্যুটে সঠিক অ্যাডমিন JWT দিতে হবে।

> [!CAUTION]
> **Fail-Closed Admin JWT:** এটি ইমপ্লিমেন্ট করার পর যদি Redis অনুপলব্ধ থাকে (Render free-tier cold start), অ্যাডমিন প্যানেলে অ্যাক্সেস সাময়িকভাবে রিজেক্ট হবে। এটি ইচ্ছাকৃত ও নিরাপদ আচরণ — Redis রিকভার হলে স্বয়ংক্রিয়ভাবে ঠিক হয়।

---

## 📋 পরিবর্তনের তালিকা (Component-wise)

---

### ১. Scraper Service Access Guard (P1)

#### বর্তমান অবস্থা (সমস্যা)
[`backend/api/routes/scraper.py`](./backend/api/routes/scraper.py) ফাইলে `/scrape`, `/browse`, `/recipe` — তিনটি এন্ডপয়েন্টই কোনো Auth ছাড়াই যেকোনো HTTP ক্লায়েন্ট থেকে কল করা যায়। শুধু `is_safe_url()` SSRF চেক আছে। একজন authenticated regular টেন্যান্টও এই পথে Playwright ব্রাউজার ইনস্ট্যান্স চালু করতে পারে — ভারী মেমোরি ও CPU খরচ।

```python
# বর্তমান অবস্থা — কোনো Auth গার্ড নেই!
@router.post("/browse")
async def browse(request: BrowseRequest):  # ← কোনো Depends() নেই
    ...
```

#### পরিবর্তন
**[MODIFY]** [`backend/api/routes/scraper.py`](./backend/api/routes/scraper.py)

- `api.dependencies` থেকে `get_current_admin` ইম্পোর্ট করা।
- `/scrape`, `/browse`, `/recipe` — তিনটিতেই `Depends(get_current_admin)` যোগ করা।
- `asyncio.Semaphore(MAX_CONCURRENCY)` দিয়ে একসাথে সর্বোচ্চ কতটি ব্রাউজার সেশন চলতে পারবে তার সীমা নির্ধারণ করা (বর্তমান ডিফল্ট ৩)। বেশি রিকোয়েস্ট আসলে HTTP 429 ফেরত দেওয়া।

```python
# পরিবর্তনের পরে
from api.dependencies import get_current_admin
import asyncio

_semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

@router.post("/browse")
async def browse(request: BrowseRequest, _: dict = Depends(get_current_admin)):
    async with _semaphore:
        ...
```

**ফাইল সংখ্যা:** ১টি | **লাইন পরিবর্তন:** ~+8 লাইন

---

### ২. JWT Revocation — Admin-এর জন্য Fail-Closed (P1)

#### বর্তমান অবস্থা (সমস্যা)
[`backend/core/security/__init__.py`](./backend/core/security/__init__.py), **লাইন 264–277**:

```python
async def is_token_revoked(jti: str) -> bool:
    if jti in _IN_MEMORY_BLACKLIST:  # ← শুধুমাত্র প্রসেস-জীবনকালের ক্যাশ
        return True
    if not redis_manager or not getattr(redis_manager, "client", None):
        return False  # ← Fail-Open: Redis ডাউন হলে revoked token-ও ভ্যালিড!
    ...
```

`_IN_MEMORY_BLACKLIST` হলো একটি সাধারণ `set()` (লাইন ২৩৭)। সমস্যা: এটি TTL ছাড়া অসীম বড় হতে পারে, এবং অ্যাডমিন টোকেনের জন্যও Redis ডাউনে fail-open করে।

#### পরিবর্তন
**[MODIFY]** [`backend/core/security/__init__.py`](./backend/core/security/__init__.py)

- বর্তমান `_IN_MEMORY_BLACKLIST: set[str]` এর পাশে একটি TTL-aware LRU ক্যাশ (`_ADMIN_REVOCATION_CACHE`) যোগ করা যা সর্বোচ্চ ১০০০ সাম্প্রতিক revoked JTI ধরে রাখবে।
- `is_token_revoked()` ফাংশনে একটি `is_admin: bool = False` প্যারামিটার যোগ করা।
  - `is_admin=True` হলে Redis ডাউনের সময়ও **fail-closed** — অর্থাৎ রিভোকেশন ভেরিফাই করতে না পারলে অ্যাক্সেস রিজেক্ট করা।
  - `is_admin=False` (সাধারণ ইউজার) এর আগের মতোই fail-open থাকবে যাতে Redis blip-এ সাধারণ ইউজার লক-আউট না হন।

```python
# পরিবর্তনের পরে (সরলীকৃত)
async def is_token_revoked(jti: str, *, is_admin: bool = False) -> bool:
    if jti in _IN_MEMORY_BLACKLIST:
        return True
    if not redis_available:
        # অ্যাডমিন: নিরাপদ দিকে — Redis ছাড়া verify করা সম্ভব নয়, reject করো
        if is_admin:
            return True  # Fail-CLOSED
        return False     # Fail-Open (regular user)
    ...
```

- `optional_current_user()` এবং admin dependency-তে `is_admin=True` পাঠানো।

**ফাইল সংখ্যা:** ২টি | **লাইন পরিবর্তন:** ~+25 লাইন

---

### ৩. Frontend: localStorage → httpOnly Cookie Migration (P1)

#### বর্তমান অবস্থা (সমস্যা)

**ব্যাকএন্ড:** [`backend/api/routes/auth.py`](./backend/api/routes/auth.py) — ভালো খবর হলো `_set_auth_cookies()` ফাংশন (লাইন 48–83) ইতোমধ্যে `httpOnly=True, secure=True, samesite="lax"` সহ কুকি সেট করার লজিক লেখা আছে। কিন্তু এটি `/login` ও `/register` response-এ এখনও **কল করা হয় না**।

**ফ্রন্টএন্ড:** [`frontend/src/store/authStore.ts`](./frontend/src/store/authStore.ts):
- **লাইন 126:** `localStorage.setItem(TOKEN_KEY, token)` — লগইনে টোকেন localStorage-এ সংরক্ষণ।
- **লাইন 161:** register-এও একই।
- **লাইন 201:** `initialize()` এ `localStorage.getItem(TOKEN_KEY)` দিয়ে সেশন রিস্টোর।

XSS অ্যাটাকে যে কেউ `localStorage.getItem('supremeai_auth_token')` করে পূর্ণ অ্যাক্সেস নিতে পারে।

#### পরিবর্তন

**[MODIFY]** [`backend/api/routes/auth.py`](./backend/api/routes/auth.py)
- `/auth/login` এন্ডপয়েন্টে response সাইন করার পর `_set_auth_cookies(response, access_token, refresh_token)` কল করা (ইতোমধ্যে ফাংশন প্রস্তুত, শুধু ব্যবহার হচ্ছে না)।
- `/auth/register`-এও একই।
- `/auth/logout`-এ `_clear_auth_cookies(response)` কল করা (এটিও ইতোমধ্যে লেখা আছে)।
- Response body-তে টোকেন ডুয়াল-মোড ট্রানজিশনের জন্য রাখা (breaking change নয়)।

**[MODIFY]** [`frontend/src/store/authStore.ts`](./frontend/src/store/authStore.ts)
- `login()` ও `register()` এ `localStorage.setItem(TOKEN_KEY, token)` লাইনগুলো রাখা (ট্রানজিশন পিরিয়ড — দুই মোডই কাজ করবে)।
- `initialize()` ফাংশন আপডেট করা: `localStorage` চেকের পাশাপাশি cookie-based সেশন detect করার ক্ষমতা যোগ করা — `credentials: 'include'` সহ `/api/v1/auth/me` কল থেকে সেশন রিস্টোর।

**[MODIFY]** [`frontend/src/services/apiClient.ts`](./frontend/src/services/apiClient.ts)
- সমস্ত fetch কলে `credentials: 'include'` নিশ্চিত করা (GLM patch 0016 থেকে ইতোমধ্যে `apiInterceptor.ts`-এ আছে, তবে `apiClient.ts`-এর নেটিভ কলগুলোতেও যাচাই করা)।

**ফাইল সংখ্যা:** ৩টি | **লাইন পরিবর্তন:** ~+30 লাইন

---

### ৪. Memory Service Phase-2: pgvector RPC (P2)

#### বর্তমান অবস্থা (সমস্যা)

[`backend/services/memory_service.py`](./backend/services/memory_service.py), **লাইন 425–472** (Postgres path):

```python
# বর্তমান অবস্থা — Python-এ ইন-মেমোরি কসাইন
rows = pooled_pg.query_dicts(
    "SELECT ... FROM ai_memory WHERE user_id = %s ORDER BY created_at DESC LIMIT 2000"
)
for row in rows:
    stored_vector = json.loads(row["embedding"])
    score = self._cosine_similarity(query_vector, stored_vector)  # Python-এ!
```

২০০০ রো → প্রতি রো ১৫৩৬-ডিম ভেক্টর লোড → Python কসাইন লুপ = ইভেন্ট লুপে ~সেকেন্ড স্তালের ঝুঁকি।

`match_ai_memory` নামের কোনো pgvector RPC ফাংশন কোডবেসে এখনও নেই (grep নিশ্চিত করেছে — শুধু পরিকল্পনায় আছে)।

#### পরিবর্তন

**[MODIFY]** [`backend/services/memory_service.py`](./backend/services/memory_service.py)

**ধাপ ১:** Supabase SQL Migration (নতুন ফাইল):
```sql
-- match_ai_memories pgvector RPC ফাংশন তৈরি করুন Supabase SQL Editor-এ:
CREATE OR REPLACE FUNCTION match_ai_memories(
    query_embedding vector(1536),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 5,
    filter_user_id text DEFAULT NULL,
    filter_session_id text DEFAULT NULL
)
RETURNS TABLE (id uuid, session_id text, summary text, score float)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT m.id, m.session_id, m.summary,
           1 - (m.embedding <=> query_embedding) AS score
    FROM ai_memory m
    WHERE (filter_user_id IS NULL OR m.user_id = filter_user_id)
      AND (filter_session_id IS NULL OR m.session_id = filter_session_id)
      AND 1 - (m.embedding <=> query_embedding) > match_threshold
    ORDER BY m.embedding <=> query_embedding
    LIMIT match_count;
END; $$;
```

**ধাপ ২:** `CascadeMemoryService.query_context()` আপডেট:
- pgvector extension detect করা (`pooled_pg.has_pgvector()` হেলপার যোগ করা)।
- Extension পাওয়া গেলে `match_ai_memories` RPC কল করা — ডাটাবেসেই similarity ranking।
- না পাওয়া গেলে বর্তমান `_MEMORY_ROW_CAP=2000` কসাইন fallback ব্যবহার করা।

**[NEW]** `backend/database/migrations/legacy/001_pgvector_match_fn.sql` — Supabase-এ run করার জন্য migration ফাইল।

**ফাইল সংখ্যা:** ২টি (১ modified + ১ new) | **লাইন পরিবর্তন:** ~+60 লাইন

---

## 🗃️ পরিবর্তনের সারসংক্ষেপ টেবিল

| # | কাজ | Priority | ফাইল | পরিবর্তন |
|---|---|:---:|---|---|
| ১ | Scraper `/browse`, `/scrape`, `/recipe`-এ admin auth + semaphore | P1 | `api/routes/scraper.py` | ~+8 লাইন |
| ২ | Admin JWT revocation fail-closed + TTL LRU ক্যাশ | P1 | `core/security/__init__.py`, `api/dependencies.py` | ~+25 লাইন |
| ৩a | Backend: `_set_auth_cookies()` login/register/logout-এ activate | P1 | `api/routes/auth.py` | ~+8 লাইন |
| ৩b | Frontend: cookie-aware `initialize()` + dual-mode transition | P1 | `store/authStore.ts`, `services/apiClient.ts` | ~+22 লাইন |
| ৪a | pgvector SQL migration ফাইল | P2 | `database/migrations/legacy/001_pgvector_match_fn.sql` | নতুন ফাইল |
| ৪b | `query_context()` এ pgvector RPC detect + call | P2 | `services/memory_service.py` | ~+60 লাইন |

---

## ✅ ভেরিফিকেশন প্ল্যান

### স্বয়ংক্রিয় পরীক্ষা
```bash
# ব্যাকএন্ড — সমস্ত পরিবর্তিত মডিউল
cd backend
poetry run ruff check api/routes/scraper.py core/security/__init__.py api/routes/auth.py services/memory_service.py

# Python compile check
python -m py_compile api/routes/scraper.py core/security/__init__.py services/memory_service.py

# ফ্রন্টএন্ড
cd frontend && npm run build && npm run lint
```

### ম্যানুয়াল পরীক্ষা
1. **Scraper Guard:** Postman/cURL দিয়ে অ্যাডমিন JWT ছাড়া `POST /api/scraper/browse` → HTTP 401 পাওয়া নিশ্চিত করুন।
2. **Cookie:** লগইন করুন → Browser DevTools → Application → Cookies → `supreme_access_token` কুকিতে `HttpOnly ✓`, `Secure ✓` চিহ্ন দেখুন।
3. **Fail-Closed:** Redis connection string ভুল দিন → Admin dashboard access করুন → HTTP 403 পাওয়া নিশ্চিত করুন।
4. **pgvector:** Supabase-এ SQL Editor-এ `SELECT match_ai_memories(...)` কল করে ফাংশন কাজ করছে যাচাই করুন।