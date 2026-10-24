---
id: supabase-database-schema-and-connection-management-plan
subject: Supabase Database Schema and Connection Management Plan
document_role: architecture
planning_authority: Data Circle (C3)
status: active
target_scope: combined_ecosystem
---
---
id: supabase-database-schema-and-connection-management-plan
subject: Supabase Database Schema and Connection Management Plan
document_role: architecture
planning_authority: Data Circle (C3)
status: active
---
বুঝেছি—আপনাদের **নতুন Supabase database তৈরি করার দরকার নেই**। লক্ষ্য হবে:

> Existing team Supabase project → SupremeAI codebase-এর সঙ্গে নিরাপদে connect → schema/RLS/auth ধাপে ধাপে configure করা।



# SupremeAI-এর জন্য Supabase A–Z Roadmap

## Phase 0: Access ও ownership ঠিক করা

প্রথমে team-এর Supabase owner/admin-কে করতে হবে:

1. Existing Supabase project খুলতে হবে।
2. আপনার Vercel/v0 account-কে project member হিসেবে invite করতে হবে।
3. Role:

4. শুধু দেখতে হলে: **Read-only**
5. schema/migration করতে হলে: **Developer বা Admin**

6. Project reference ID সংগ্রহ করতে হবে।
7. Dashboard থেকে এগুলো verify করতে হবে:

8. Project status: Active
9. Database status: Healthy
10. API status: Available
11. Auth enabled
12. Database password জানা আছে বা reset করার permission আছে

গুরুত্বপূর্ণ: Supabase project কোন email দিয়ে তৈরি হয়েছে সেটি সমস্যা নয়। আপনাকে project-এ member হিসেবে invite করলেই যথেষ্ট।

---

## Phase 1: “Supabase install” বলতে কী বোঝাচ্ছে তা আলাদা করা

Supabase-এ সাধারণত তিনটি আলাদা বিষয় থাকে:

### A. Supabase JavaScript/Python package

Application code থেকে API access করার জন্য package।

```shellscript
@supabase/supabase-js
```

অথবা Python backend-এর জন্য:

```shellscript
supabase
```

### B. Supabase CLI

Migration, local development এবং project linking-এর জন্য।

### C. Supabase integration/MCP

Agent বা v0 থেকে project inspect ও SQL কাজের জন্য।

একটির installation error মানেই database error নয়। আগে error category নির্ধারণ করতে হবে:

- npm authentication error
- CLI installation error
- project linking error
- invalid URL/key
- database connection error
- permission/RLS error
- existing integration conflict

---

## Phase 2: Existing project connect করা

নতুন Supabase integration provision করা যাবে না। Existing project-ই ব্যবহার করতে হবে।

প্রয়োজনীয় application variables:

```plaintext
SUPABASE_URL=SUPABASE_ANON_KEY=SUPABASE_SERVICE_ROLE_KEY=
```

ব্যবহারনীতি:

| Variable | কোথায় ব্যবহার হবে
| ----- | -----
| `SUPABASE_URL` | server/client দু’জায়গাতেই হতে পারে
| `SUPABASE_ANON_KEY` | browser-safe client
| `SUPABASE_SERVICE_ROLE_KEY` | server-only
| `NEXT_PUBLIC_SUPABASE_URL` | frontend দরকার হলে
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | frontend দরকার হলে

`SUPABASE_SERVICE_ROLE_KEY` কখনো:

- frontend-এ নয়
- `NEXT_PUBLIC_` prefix-এ নয়
- Git commit-এ নয়
- browser network response-এ নয়
- client-side JavaScript-এ নয়

আপনাদের project-এ আগে থেকেই `NEXT_PUBLIC_DEV_SUPABASE_REDIRECT_URL` আছে; সেটি আবার চাইতে হবে না।

---

## Phase 3: Environment separation

কমপক্ষে তিনটি environment রাখা উচিত:

```plaintext
developmentpreviewproduction
```

প্রতিটির জন্য ideally:

```plaintext
Supabase project বা branchSupabase URLanon keyservice role keyredirect URLs
```

সাশ্রয়ী MVP-তে একই Supabase project ব্যবহার করলে অন্তত আলাদা schema/table prefix বা strict environment flag রাখতে হবে। Production data-এর ওপর development migration চালানো যাবে না।

Recommended:

```plaintext
Development → Supabase branch/local databasePreview     → shared staging projectProduction  → existing team project
```

Free-tier budget constraint থাকলে প্রথমে:

```plaintext
Development → local SupabasePreview      → staging schemaProduction   → team Supabase project
```

---

## Phase 4: Local Supabase setup

Local development-এর জন্য Supabase CLI ব্যবহার করা ভালো, যাতে production database সরাসরি নষ্ট না হয়।

Local setup-এর উদ্দেশ্য:

- migration test
- RLS test
- schema validation
- seed data
- rollback test
- API contract test

Local stack না চালালেও migration আগে SQL review করে তারপর production-এ apply করতে হবে।

কখনো সরাসরি production-এ এই ধরনের পরীক্ষা চালাবেন না:

```sql
DROP TABLETRUNCATEALTER TYPEDROP COLUMN
```

---

# Phase 5: Existing codebase audit

Supabase configure করার আগে এই অংশগুলো মিলাতে হবে:

```plaintext
backend/models/ai_memory.pybackend/memory/supabase_store.pybackend/adaptive_engine/supabase_vector_backend.pybackend/database/contracts/schema_contract.yamlbackend/alembic_migrations/backend/core/config.py
```

Audit checklist:

- কোন table code ব্যবহার করছে?
- কোন column code প্রত্যাশা করছে?
- `user_id` নাকি `tenant_id` ব্যবহার হচ্ছে?
- UUID নাকি text ID?
- timestamp timezone-aware কি না?
- embedding dimension কত?
- RPC function-এর নাম কী?
- Supabase client sync নাকি async?
- service-role client কোথায় তৈরি হচ্ছে?
- কোন query-তে ownership filter অনুপস্থিত?

আগের audit অনুসারে সবচেয়ে critical বিষয়:

```plaintext
Embedding dimension: 384Database vector dimension: 384RPC input/output dimension: 384
```

`1536`, `TEXT`, এবং `vector(384)` মিশ্র অবস্থায় রাখা যাবে না।

---

# Phase 6: Core database schema

SupremeAI-এর জন্য schema logical ভাবে এভাবে ভাগ করা উচিত:

## Identity ও tenancy

```plaintext
profilesorganizationsorganization_members
```

## Agents

```plaintext
agentsagent_versionsagent_tools
```

## Conversations

```plaintext
conversationsmessagesmessage_runs
```

## Memory

```plaintext
ai_memorymemory_chunksmemory_metadata
```

## Tasks

```plaintext
taskstask_attemptstask_events
```

## Provider routing

```plaintext
provider_capabilitiesprovider_outcomesprovider_quota_snapshots
```

## Observability

```plaintext
audit_logsusage_eventserror_events
```

## Artifacts

বড় file বা code snapshot database-এ না রেখে object storage-এ রাখা উচিত:

```plaintext
artifact_metadata
```

Database-এ থাকবে:

```plaintext
artifact_idowner_idstorage_keycontent_typesize_byteschecksumcreated_atexpires_at
```

Actual binary content থাকবে R2 বা Supabase Storage-এ।

---

# Phase 7: `ai_memory`schema ঠিক করা

Recommended structure:

```sql
embedding vector(384) NOT NULL
```

এছাড়া:

```plaintext
id UUID primary keyuser_id UUID not nulltenant_id UUIDcontent TEXT not nullmemory_type TEXTimportance_score NUMERICsource TEXTmetadata JSONBcreated_at TIMESTAMPTZupdated_at TIMESTAMPTZexpires_at TIMESTAMPTZ
```

Indexes:

```plaintext
user_idtenant_idcreated_atmemory_typeexpires_atvector similarity index
```

Semantic search-এর জন্য RPC function-এ অবশ্যই ownership scope থাকতে হবে:

```plaintext
match_memories(  query_embedding,  match_threshold,  match_count,  requesting_user_id,  requesting_tenant_id)
```

শুধু vector similarity দিয়ে search করলে user A user B-এর memory দেখতে পারে—এটি গুরুতর security bug।

---

# Phase 8: RLS implementation

Supabase-এর exposed table-এ RLS mandatory।

প্রতিটি user-owned table-এ সাধারণ pattern:

```sql
ALTER TABLE ai_memory ENABLE ROW LEVEL SECURITY;
```

Select policy:

```sql
CREATE POLICY "Users read own memories"ON ai_memoryFOR SELECTTO authenticatedUSING ((SELECT auth.uid()) = user_id);
```

Insert policy:

```sql
CREATE POLICY "Users insert own memories"ON ai_memoryFOR INSERTTO authenticatedWITH CHECK ((SELECT auth.uid()) = user_id);
```

Update policy-তে দুটোই দিতে হবে:

```sql
USING ((SELECT auth.uid()) = user_id)WITH CHECK ((SELECT auth.uid()) = user_id);
```

Delete:

```sql
CREATE POLICY "Users delete own memories"ON ai_memoryFOR DELETETO authenticatedUSING ((SELECT auth.uid()) = user_id);
```

ভুল pattern:

```sql
TO authenticated
```

এটি শুধু logged-in কিনা যাচাই করে; ownership যাচাই করে না।

`user_metadata` ব্যবহার করে authorization করবেন না। Role/permission-এর জন্য `app_metadata` অথবা আলাদা membership table ব্যবহার করতে হবে।

---

# Phase 9: Auth setup

MVP-তে প্রথমে শুধু:

```plaintext
Email + password
```

রাখুন।

পরবর্তীতে প্রয়োজন হলে:

- email verification
- password reset
- session refresh
- account deletion
- rate limiting
- device/session revocation

Redirect URLs configure করতে হবে:

```plaintext
localhostv0 preview URLstaging URLproduction URL
```

Auth cookie configuration:

- secure production cookies
- correct same-site policy
- exact trusted origins
- short expiry for sensitive operations
- logout-এর সময় session revoke

---

# Phase 10: Backend client architecture

দুই ধরনের client রাখা উচিত:

## Browser client

শুধু:

```plaintext
SUPABASE_URLSUPABASE_ANON_KEY
```

ব্যবহার করবে।

## Server privileged client

শুধু trusted backend route বা worker-এ:

```plaintext
SUPABASE_SERVICE_ROLE_KEY
```

ব্যবহার করবে।

Server client-এর ক্ষেত্রে:

- request user identity validate করতে হবে
- প্রতিটি query-তে `user_id`/`tenant_id` filter রাখতে হবে
- service role থাকলেও authorization skip করা যাবে না
- raw user input parameterized query দিয়ে পাঠাতে হবে

Service-role key RLS bypass করে—তাই এটি security boundary নয়; backend code-ই ownership enforce করবে।

---

# Phase 11: Queue ও task persistence

Supabase-এ queue payload বড় করে রাখবেন না। Database task record:

```plaintext
task_idowner_idtenant_idtask_typestatuspriorityidempotency_keyattempt_countscheduled_atstarted_atcompleted_aterror_coderesult_artifact_id
```

Upstash-এ রাখবেন:

```plaintext
task_idlock tokenstatusretry counterdedup key
```

Task state machine:

```plaintext
queuedrunningsucceededfailedcancelledexpireddead_letter
```

প্রতিটি task-এ:

- timeout
- maximum attempts
- exponential backoff
- dead-letter handling
- idempotency
- ownership validation

থাকবে।

---

# Phase 12: Free-tier data strategy

Maintenance cost কম রাখতে retention policy আবশ্যক।

Recommended:

| Data | Retention
| ----- | -----
| Raw task events | 7–14 দিন
| Debug logs | 7 দিন
| Failed payload | 7–30 দিন
| Conversation messages | product policy অনুযায়ী
| Important memory | দীর্ঘমেয়াদি
| Temporary embeddings | 30–90 দিন
| Large artifacts | expiry-based
| Usage aggregates | monthly rollup

Supabase database-এ রাখবেন না:

- raw browser recordings
- বড় code archive
- generated videos
- duplicate prompt payload
- unlimited telemetry
- temporary build files

---

# Phase 13: Migration strategy

Migration workflow:

```plaintext
1. Inspect current schema2. Write contract3. Create migration4. Run locally5. Run unit tests6. Run RLS tests7. Run vector retrieval test8. Review SQL9. Apply staging10. Verify staging11. Backup production12. Apply production13. Monitor
```

Migration কখনো একবারে destructive করবেন না।

উদাহরণ:

```plaintext
old column → new columnbackfilldual-readdual-writeverifyremove old column later
```

Embedding migration:

```plaintext
TEXT embedding→ new vector(384) column→ re-embed records→ validate similarity→ switch reads→ remove old column
```

---

# Phase 14: Supabase install error diagnosis

Error অনুযায়ী solution:

## `401 Unauthorized`/ npm error

npm registry authentication বা package access সমস্যা। Existing Supabase database-এর সঙ্গে এর সম্পর্ক নেই।

## `supabase: command not found`

CLI install হয়নি বা PATH সমস্যা। Application SDK install করলেও CLI automatically পাওয়া যায় না।

## `Invalid API key`

ভুল project-এর key, expired key, বা key copy করার সময় whitespace।

## `Invalid URL`

URL অবশ্যই project URL হতে হবে:

```plaintext
https://<project-ref>.supabase.co
```

## `relation does not exist`

Migration apply হয়নি অথবা ভুল schema/project connected।

## `permission denied`

RLS, grant, অথবা wrong role।

## `PGRST204`

Column/schema cache mismatch। Migration-এর পরে schema reload ও query verification দরকার।

## `connection refused`

Database paused, wrong host, wrong port, অথবা direct connection limit exceeded।

## `JWT expired`

Session refresh বা server-side cookie handling ঠিক নেই।

---

# Phase 15: Verification checklist

Supabase setup সম্পন্ন বলার আগে পরীক্ষা:

## Connection

- Correct existing project connected
- URL valid
- anon key valid
- service key server-only
- environment variables separated

## Auth

- Signup works
- Login works
- Logout works
- Invalid password rejected
- Session refresh works
- Redirect URLs work

## Database

- Tables exist
- Foreign keys valid
- Required indexes exist
- Timestamps timezone-aware
- `vector(384)` consistent
- RPC works

## Security

- RLS enabled everywhere
- User A cannot access user B
- Tenant isolation works
- Update cannot change owner
- Service-role key not exposed
- Storage policies tested
- SSRF/input validation enabled

## Reliability

- Duplicate task does not duplicate work
- Retry works
- Timeout works
- Dead-letter state works
- Expired data is cleaned
- Provider quota fallback works

---

# Phase 16: Recommended implementation order

## Milestone 1: Connection foundation

- Existing project access
- Environment variable mapping
- Server/browser client separation
- Health-check endpoint
- No schema mutation yet

## Milestone 2: Schema contract

- Compare existing DB with codebase
- Finalize table/column names
- Resolve user/tenant ownership model
- Resolve embedding dimension

## Milestone 3: Safe migration

- Add missing columns/tables
- Add indexes
- Add non-destructive backfills
- Add migration verification

## Milestone 4: Auth and RLS

- Email/password auth
- Profile/member tables
- RLS policies
- Cross-tenant access tests

## Milestone 5: Memory system

- `vector(384)`
- embedding write path
- similarity RPC
- scoped retrieval
- retention and pruning

## Milestone 6: Queue persistence

- task records
- idempotency
- retry/backoff
- dead-letter flow
- Upstash pointer storage

## Milestone 7: Compute offload

- client-side WASM/WebGPU path
- user-local Ollama path
- approved external batch path
- paid burst fallback
- no keep-alive or quota evasion

## Milestone 8: Observability

- usage events
- quota snapshots
- provider outcome metrics
- error aggregation
- privacy-safe logs

## Milestone 9: Production hardening

- backup and restore test
- migration rollback
- load test
- RLS audit
- secret rotation
- incident runbook

---

# Final recommended architecture

```plaintext
Frontend  ↓Cloudflare/Vercel edge  - cache  - rate limit  - request normalization  ↓Render Core API  - auth validation  - tenant scope  - task admission  - router  ↓Supabase  - auth  - durable data  - scoped memory  - task metadata  ↓Upstash  - short queue  - lock  - dedup  ↓Execution layer  - browser WASM/WebGPU  - user-local Ollama  - scheduled research batch  - approved paid burst  ↓R2/Supabase Storage  - large artifacts
```

## সবচেয়ে গুরুত্বপূর্ণ সিদ্ধান্ত

Supabase configure করার সময় প্রথমে database migration নয়, বরং:

1. Existing team project access
2. Correct project identification
3. Environment separation
4. Schema audit
5. Ownership model
6. RLS design
7. তারপর migration

এই order অনুসরণ করলে নতুন database তৈরি হবে না, production data নষ্ট হওয়ার ঝুঁকি কমবে, এবং SupremeAI-এর memory, queue ও multi-tenant architecture ভবিষ্যতে safely scale করা যাবে।