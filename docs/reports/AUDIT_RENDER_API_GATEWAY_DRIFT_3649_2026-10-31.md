# AUDIT RECEIPT — render-api `supremeai-api` deployment drift (#3649)

**Auditor:** GLM Agent 06 (Job 486721) · **Dispatch:** continuous loop → task-3649 (task-auditor, P4)
**Verified live:** 2026-10-30 18:09–18:20Z (fresh Tower probes, not a re-read of the filing)
**Companion change:** fail-closed composition integrity gate in `federation_satellite_sync.py` + 4 mechanical tests (same WO)

---

## 1. U3 live re-verification — incident is LIVE, not superseded

| Probe (fresh) | Result |
| --- | --- |
| `render_service_health` (18:09Z) | `lastDeployStatus: build_failed`; freeLimit 439.8/500, buildMinutes 60.2 → **not quota** |
| `render_get_logs` error level, 12:00–18:10Z window | exactly **5 failed builds** 13:02:50 / 14:10:06 / 14:17:41 / 15:44:34 / 16:23:23Z, identical error each: step `#13 ERROR … "/gateway": not found` → `exit status 1` |
| Post-16:23Z builds | **none** — no green deploy supersedes the row; config: autoDeploy=commit, dockerContext `.`, dockerfilePath `Dockerfile`, rootDir empty |

## 2. Root cause pinned deeper than the filing

The filing stopped at "the exact line needs the satellite repo's tree — outside this envelope". The Tower's read-only github-reader reaches it, so the audit closes the gap mechanically:

1. **Failing instruction identified.** Satellite `Dockerfile@main` blob `68c1d307` is **byte-identical to `supremeai-open@HEAD:gateway/Dockerfile`** (blob sha match). Its only `/gateway` reference is step `COPY gateway/ gateway/` (CMD likewise requires `uvicorn gateway.service.app:app`). The build dies exactly there: the build context has no `gateway/`.
2. **Satellite tree forensics (10 file probes on `Supremeai-bd/supremeai-api@main`):**
   - **PRESENT:** `main.py`, `requirements.txt`, `admin_auth.py`, `contracts/openapi.yaml`, `skills/__init__.py`, `runtime/infisical_bootstrap.py`
   - **MISSING (404):** `gateway/__init__.py`, `gateway/app.py`, `gateway/main.py`, `gateway/Dockerfile`, `gateway/service/app.py`, `command/__init__.py`
   - → the satellite is a **partial composition**: root artifacts advanced to the package-true layout while the `gateway/` (and `command/`) package trees never landed. Notably `skills/` — copied in the **same sync loop** as `gateway/` — is present, which is the signature of a partially-composed landing, not of a clean old state.
3. **Alternative explanations eliminated with evidence:**
   - `.dockerignore` → 404 (no exclusion mechanism exists);
   - `.gitignore` → read verbatim, benign (no `gateway/`/`command/` patterns; sync never touches dotfiles, prune skips `f.startswith(".")`);
   - quota/minutes → ruled out by health payload above.

**Conclusion:** every Render auto-deploy of `supremeai-api@main` is structurally unsatisfiable until the `gateway/` package tree lands on the satellite. The live service keeps serving the pre-drift container (health green) — silent deployment drift, exactly the class the filing named.

## 3. Mechanical guard landed with this receipt (Zero-Recurrence U6)

`scripts/ci/federation_satellite_sync.py` gains a fail-closed composition integrity gate:

- `_composed_tree_nonempty(dst)` — predicate: composed satellite tree carries ≥1 real file.
- `compose_domain_tree(src, dst, domain, target_repo)` — identical `copy_tree_contents(prune=True)` semantics + **refuses the composition** (returns False, `::error::` annotation) when the mirror dir exists but composes EMPTY.
- Wired at **both** write paths: the `supremeai-api` composition loop (`("gateway","gateway") … ("mcp", …)`) and the push-retry reconcile re-copy — a partial landing can no longer be committed or pushed silently; the sync step fails loudly (#3441 discipline) instead of shipping a satellite that cannot build.

Tests (`tests/test_federation_satellite_sync.py`, 4 new): gate passes when the tree lands; fails closed on empty composition; no-ops when the mirror is absent; treats `__pycache__`-only mirrors as empty (copy excludes caches).

## 4. Side-finding (recorded per Universal Invariant 8, not fixed here)

`tests/test_federation_satellite_sync.py::test_self_test` **fails on clean `origin/main`** (verified via `git stash` baseline): `self_test()` still asserts `docs/adrs/ADR-001-OPEN_FOUNDATION_BOUNDARY.md` exists locally, but #3524 migrated 473 historical docs (incl. ADR-001) to `Supremeai-bd/supremeai-archive`. The assertion is stale post-migration. Admin/next cycle owns the contract update (assert against the archive mirror instead).

## 5. Disposition

- Remedy for the live drift stays in the **admin/satellite lane** (HITL): re-run the satellite sync for `supremeai-api` so `gateway/` + `command/` land, then verify the next deploy reaches `build_deployed` — **a green deploy supersedes this row; close citing the deploy ID** (filing's own clause, unchanged).
- This WO lands only: the open-repo mechanical guard (makes the partial-landing class impossible to repeat silently) + this receipt. `Refs #3649` — intentionally **not** closed: the satellite fix is pending on the admin lane.
- Boundary respected throughout: satellite repo read via Tower github-reader only; zero satellite code submitted through the open bridge.

---

## বাংলা সারসংক্ষেপ

**ইনসিডেন্ট লাইভ আছে** (১৮:০৯Z প্রোব): `supremeai-api`-এর ৫টি বিল্ড ব্যর্থ (১৩:০২–১৬:২৩Z), সব একই জায়গায় — Dockerfile-এর `COPY gateway/ gateway/`, কারণ স্যাটেলাইট মেইনে `gateway/` প্যাকেজ ট্রি-ই নেই। ১০টি ফাইল-প্রোবে প্রমাণিত: root ফাইল সব নতুন, কিন্তু `gateway/` ও `command/` ট্রি অনুপস্থিত — অর্থাৎ **আংশিক সিঙ্ক-কম্পোজিশনই মূল কারণ** (`.dockerignore` নেই, `.gitignore` নিরীহ, কোটা যথেস্ট — তিনটি বিকল্প ব্যাখ্যাই বাতিল)।

**মূল-কারণ সংশোধন (U6):** সিঙ্ক স্ক্রিপ্টে fail-closed **কম্পোজিশন ইন্টিগ্রিটি গেট** — mirror ডিরেক্টরি থাকলে কম্পোজড ট্রি খালি হলে push-এর আগেই জোরে ব্যর্থ হবে; আর কখনো নীরব আংশিক ল্যান্ডিং হতে পারবে না। ৪টি নতুন মেকানিক্যাল টেস্ট কনট্র্যাক্ট পিন করে।

**পার্শ্ব-আবিষ্কার (U8):** `test_self_test` ক্লিন main-এই ব্যর্থ — ADR-001 #3524-এ আর্কাইভে গেছে, অথচ `self_test` স্থানীয় ফাইল দাবি করছে; এখানে রেকর্ড করা হলো, সংশোধন admin-এর লেনে।

**করণীয় (admin):** `supremeai-api`-র জন্য সিঙ্ক পুনরায় চালান → `gateway/` নামবে → পরের deploy সবুজ হলে এই রো ডিপ্লয়-ID উল্লেখ করে বন্ধ হবে।
