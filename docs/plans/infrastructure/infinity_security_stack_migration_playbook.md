# Infinity Security Stack — Evaluation & Migration Playbook (Way 6)

> SupremeAI × Infinity Tech Stack follow plan, Way 6 deliverable.
> Status: **evaluation playbook** (no runtime code changes in this document).
> Author: continuous agent loop, 2026-10-24 · Basis: `infinitytechstack.uk` security stack
> (Infinity ID / Observe / Data / Stream — single Rust binary, zero per-seat tax) vs
> SupremeAI's current Qdrant/Redis/Upstash/OpenAI-dependency posture.

---

## 1. Component-by-component assessment

| Infinity module | What it replaces here | Current SupremeAI counterpart | Verdict |
|---|---|---|---|
| **Infinity ID** (OIDC + MFA, self-hosted) | Clerk/Auth0/Supabase auth seats | `gateway/service/admin_auth.py` (native admin JWT) + keygen API keys + OTP router | **Evaluate later (Phase 3).** Native auth already fail-closed (Rating-audit fixes #1085/#1083); migrating identity providers is high-blast-radius and must wait for the native surface to stabilize. Revisit when MFA enrollment + OIDC federation land in the roadmap. |
| **Observe** (logs/traces/metrics, single binary) | SaaS observability tax | `core/observability/` + `core/monitoring/` + gateway middleware; correlation ids standardized by **Way 28 patch** (`gateway/middleware/correlation_id.py` + optional OTel facade) | **Adopt pattern, not product (Phase 2).** OTel SDK is already wire-compatible; keep the facade vendor-neutral so an Observe-style collector can replace SaaS exporters without code churn. |
| **Data** (HNSW vector store) | Qdrant cluster cost | `gateway/service/memory_store.py` + `core/unified_memory.py` (Qdrant client, cosine 0.72 gate from Way 2) | **Benchmark before migrating (Phase 3).** Qdrant works and is already load-shaped; an embedded HNSW (single binary) only pays off if satellite count × QPS outgrows the free-tier cluster. Action: run a 1M-vector recall/latency benchmark (documented §3) before any decision. |
| **Stream** (BM25 + streaming search) | Upstash/Redis search usage | `core/tools/knowledge/local_search_rag.py` + Redis managers | **Low priority.** BM25 is embedded in several existing paths; duplication risk > benefit until the knowledge corpus scales past what SQLite/Redis hold comfortably. |

## 2. Migration decision gates (do NOT skip)

1. **Cost gate** — current monthly infra spend (Qdrant cloud + Upstash + auth seats) vs
   single-VPS cost for an Infinity-style stack. Migration must project ≥ 40% savings
   over 6 months to proceed (otherwise complexity is bought, not paid for).
2. **Recall gate** — HNSW candidate must hit ≥ 0.98 recall@10 on the knowledge corpus
   sample (same queries, same ground truth as the Qdrant baseline run).
3. **Latency gate** — p95 < 25 ms for top-10 search at satellite-peak concurrency
   (measure on the SAME box class as production: Render free-tier equivalent).
4. **Identity gate** — Infinity ID candidate must support: admin JWT parity (sub/uid/
   email/role claims, verified fail-closed), OTP/MFA enrollment, and keygen API-key
   coexistence during a 2-phase cutover.
5. **Rollback gate** — every migration step needs a documented revert (P3):
   dual-write period → verify → flip reads → drop old path. No in-place rewrites.

## 3. Benchmark procedure (Data module, when scheduled)

```bash
# 1. Export a 1M-vector sample from Qdrant (ids + vectors + metadata) to parquet.
# 2. Build the candidate index (Infinity Data module / hnswlib) with identical distance metric.
# 3. Replay 10k recorded queries; record recall@10, p50/p95/p99 latency, RSS.
# 4. Compare against the same replay on Qdrant. Persist both JSON reports under
#    docs/plans/infrastructure/benchmarks/<date>-vector-benchmark.json
```

Pass/fail per §2 gates 2–3; attach both reports to the migration PR.

## 4. Phased adoption sketch (if all gates pass)

- **Phase A** — Observe-pattern: correlation-id middleware (Way 28 patch, already provided) + OTel facade; point exporters at self-hosted collector.
- **Phase B** — Stream/Data: dual-write shadow index; verify recall/latency gates for 2 weeks; flip reads behind `VECTOR_BACKEND` env (Qdrant | embedded-hnsw), keep Qdrant warm for rollback.
- **Phase C** — Identity: OIDC federation in front of existing admin auth (no user-visible change), MFA enrollment, then keygen-key parity mode; 2-phase cutover with instant rollback.

## 5. Explicitly out of scope / rejected

- Replacing Redis with the Infinity Stream module for rate limiting — Way 14 patch
  (`gateway/service/redis_rate_limit.py`) already solves distribution with an
  optional, fail-open design; adding a second datastore for the same job violates
  zero-over-engineering.
- Forking Infinity's Rust binaries into the satellite fleet — the plan's own risk
  note (§7.1) stands: pattern-first, Rust sidecar only if a measured bottleneck exists.
- Any change that breaks the bridge's protected-path or secret-scan guarantees.

---

*Compliance note: this playbook is an engineering aid, not a legal document.
License attribution for referenced Infinity components (MIT/Apache-2.0) is
required in any derivative use — patterns adopted, never copy-pasted.*
