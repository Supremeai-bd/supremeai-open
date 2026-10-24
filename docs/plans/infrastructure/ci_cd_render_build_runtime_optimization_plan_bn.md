---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:ci_cd_render_build_runtime_optimization_plan_bn
subject: SupremeAI CI/CD + Render Build Runtime Optimization Plan
document_role: implementation
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# SupremeAI CI/CD + Render Build Runtime Optimization Plan

## 1. Current Run — Forensic Summary

পরীক্ষা করা GitHub Actions run: **#921 / run ID 33564703304**।

বর্তমান run-এ **13/19 jobs passed**, success rate **68.4%**, total duration প্রায় **12.9 মিনিট**। সবচেয়ে বড় runtime consumer হলো **`Publish Images to GHCR` = 5.7 মিনিট**; Backend Tests = 4.7 মিনিট, Integration Tests = 1.9 মিনিট। fileciteturn88file0L1-L8

### Confirmed failures

| Job | Status | Finding |
|---|---|---|
| Deploy Core | ❌ | Render deploy trigger-এর Python command `SyntaxError` |
| Deploy Worker | ❌ | একই `SyntaxError` |
| Deploy Scraper | ❌ | একই `SyntaxError` |
| Deploy MCP Control Tower | ❌ | একই `SyntaxError` |
| DB Schema Contract Check | ❌ | Job failed; uploaded log bundle-এ root-cause output পাওয়া যায়নি, তাই আলাদা runtime inspection দরকার |

Failure pattern:

```text
headers={'Authorization': f'***'RENDER_API_KEY\')}'}
                                     ^
SyntaxError
```

এটি Render-এর deployment failure নয়; **GitHub Actions-এর deployment-trigger script-ই malformed** হয়েছে।

### Additional test-suite warnings/errors

Backend startup verification-এর সময় CI environment-এ:

- Upstash Redis hostname resolve হয়নি।
- SQLite fallback/test DB-তে `system_config` table missing ছিল।
- `rules` এবং `skills` relation missing সংক্রান্ত PostgreSQL errors এসেছে।
- pooler-only setup-এ DDL bootstrap করা সম্ভব নয় বলে error এসেছে।

এগুলো সব production failure প্রমাণ করে না; এগুলোর অনেকগুলো test harness/startup verification environment-এর সমস্যা। কিন্তু এগুলো CI-কে noisy করছে এবং test intent আরও deterministic করা দরকার।

---

# 2. সবচেয়ে গুরুত্বপূর্ণ প্রশ্ন — 4 Render service কি প্রতি push-এ build হয়?

## উত্তর: বর্তমানে Render-এ source build নয়; GitHub Actions-এ image build হচ্ছে।

Current workflow-এ:

```text
GitHub Actions
   ↓
Build Core image
Build Worker image
Build Scraper image
   ↓
Push → GHCR
   ↓
Render Deploy API trigger
   ↓
Render pulls container image
   ↓
Run service
```

Workflow-এ `Publish Images to GHCR` job রয়েছে এবং Core, Worker, Scraper-এর image build/push steps আছে। fileciteturn93file0L6-L23

অর্থাৎ **এই architecture-এ 3টি container image GitHub-hosted runner-এ build হচ্ছে**।

বর্তমান log অনুযায়ী measured build steps প্রায়:

```text
Core      ≈ 91s
Worker    ≈ 98s
Scraper   ≈ 141s
```

এগুলো sequentially একই publish job-এর মধ্যে চলছে; ফলে image publishing job-ই সবচেয়ে বড় bottleneck।

### গুরুত্বপূর্ণ distinction

আপনি 4টি Render deployment target ব্যবহার করলেও log-এ **4টি GitHub Docker build নেই**।

এখানে:

```text
Core
Worker
Scraper
```

= 3টি container image build।

আর:

```text
MCP Control Tower
```

আলাদা deployment target হলেও বর্তমান GHCR publish job-এ তার জন্য corresponding Docker image build এই log-এ দেখা যাচ্ছে না।

---

# 3. GitHub কি 3x build time ব্যবহার করছে?

**হ্যাঁ, CPU/runtime হিসেবে তিনটি image build হচ্ছে**, কিন্তু একটি গুরুত্বপূর্ণ বিষয় আছে:

তিনটি build একই job-এ sequential হওয়ায় মোট elapsed time প্রায় যোগ হচ্ছে।

Current bottleneck:

```text
Core ~1.5 min
+
Worker ~1.6 min
+
Scraper ~2.3 min
+
Cosign/SBOM work
≈ 5.7 min
```

এটি সবচেয়ে বড় optimization target।

---

# 4. Render-এ build করলে কি সমস্যা হবে?

বর্তমান image-based deployment model-এ Render source build করছে না; তাই “Render build time exceed করলে” বর্তমান workflow-এর প্রধান concern নয়।

তবে Render-এর deployment phase-এ:

```text
image pull
startup
health check
```

সময় লাগতে পারে।

সুতরাং build এবং deploy time আলাদা metric হিসেবে track করতে হবে:

```text
CI build time
CI publish/sign/SBOM time
Render image pull time
Render startup time
health-check time
```

---

# 5. Smartest Strategy — “Build Once, Deploy Many”

**প্রতিটি Render service-কে নিজের source rebuild করতে দেওয়া উচিত নয়।**

Recommended architecture:

```text
GitHub
  ↓
Test
  ↓
Build image ONCE
  ↓
Immutable digest
  ↓
GHCR
  ↓
Render Core
Render Worker
Render Scraper
```

একই artifact সব environment-এ deploy হবে।

এতে:

- duplicate build কমবে
- reproducibility বাড়বে
- rollback সহজ হবে
- “কোন code actually deploy হয়েছে?” প্রশ্নের উত্তর পরিষ্কার থাকবে

---

# 6. Immediate Runtime Optimization

## A. Core/Worker/Scraper build parallelize করা

বর্তমান:

```text
Core → Worker → Scraper
```

Preferred:

```text
          ┌→ Core
Tests ────┼→ Worker
          └→ Scraper
```

GitHub Actions matrix বা Buildx Bake ব্যবহার করে parallel build করা যায়।

এতে 5.7 মিনিটের elapsed time উল্লেখযোগ্যভাবে কমতে পারে।

---

## B. Docker Build Cache বাধ্যতামূলক

প্রতিটি push-এ dependencies/image layers নতুন করে build করার দরকার নেই।

Use:

```text
docker/build-push-action
cache-from: type=gha
cache-to: type=gha,mode=max
```

এবং dependency files আগে copy:

```dockerfile
COPY pyproject.toml poetry.lock ./
RUN poetry install ...
COPY app ./app
```

তাহলে source-only change হলে dependency layer পুনরায় build হবে না।

---

## C. Path-Aware Image Builds

বর্তমান workflow-এ change detection ইতিমধ্যে আছে। fileciteturn91file0L2-L8

এখন এটিকে deployment artifacts-এর সঙ্গে পুরোপুরি connect করতে হবে।

উদাহরণ:

```text
backend/core change
 → Core image

worker-only change
 → Worker image

scraper/** change
 → Scraper image

infrastructure/mcp-control-plane/**
 → MCP image

frontend-only change
 → no backend image build
```

তবে shared dependency/config change হলে affected images automatically mark হবে।

---

# 7. “Every Push” Policy পরিবর্তন করা উচিত

Production deployment-এর জন্য:

```text
feature branch push
    → tests only

PR
    → validation only

develop
    → optional staging

main
    → production artifacts + deployment
```

এতে অপ্রয়োজনীয় Docker build অনেক কমবে।

---

# 8. Better CI Pipeline

Recommended final flow:

```text
Detect Changes
      ↓
Fast checks ─────────────┐
      ↓                  │
Tests                    │
      ↓                  │
Security                 │
      ↓                  │
Integration              │
      ↓                  │
Affected artifact build  │
      ↓                  │
GHCR push                │
      ↓                  │
Cosign + SBOM            │
      ↓                  │
Deployment plan          │
      ↓                  │
Render deploy            │
      ↓                  │
Health + smoke           │
      ↓                  │
Success / rollback       │
```

---

# 9. Render Deployment Smartness

Render-এর জন্য প্রতি push-এ blind redeploy নয়।

প্রথমে detect:

```text
Did artifact change?
Did service-specific code change?
Did shared runtime change?
```

তারপর শুধু affected service deploy:

```text
Core changed
 → Core deploy

Scraper unchanged
 → no Scraper deploy
```

---

# 10. Image Identity

Production deployment-এ শুধু:

```text
:main
```

ব্যবহার না করে:

```text
repository@sha256:<digest>
```

বা Git SHA tag ব্যবহার করা উচিত।

Recommended:

```text
supremeai-core:<git-sha>
supremeai-worker:<git-sha>
supremeai-scraper:<git-sha>
```

তার সঙ্গে digest pinning রাখলে আরও ভালো।

---

# 11. Cosign/SBOM Optimization

বর্তমান run-এ Cosign/SBOM steps-ও significant time নিচ্ছে।

এগুলো বাদ দেওয়া উচিত নয়।

বরং:

```text
parallel image builds
+
parallel signing
+
parallel SBOM generation
```

করতে হবে।

Security gate বজায় থাকবে, runtime কমবে।

---

# 12. Backend Test Runtime

Backend Tests প্রায় **4.7 মিনিট**।

Optimization:

```text
critical tests
important tests
full suite
```

আলাদা tier করা।

Main branch-এর ক্ষেত্রে full gate রাখা যেতে পারে, কিন্তু independent test groups parallel করা উচিত:

```text
unit/critical
integration-safe
contract
startup
```

Coverage measurement একবারেই করা হবে, যতটা সম্ভব duplicate pytest execution এড়ানো হবে।

---

# 13. Integration Test Runtime

Integration Tests প্রায় **1.9 মিনিট**।

Optimization:

- unnecessary container startup বাদ দেওয়া
- service health wait কমানো
- test database seed minimal করা
- parallel-safe test groups
- artifacts only on failure
- reused setup/cache

---

# 14. Current Render Deploy Failure — Must Fix First

চারটি deploy job-এ একই malformed Python command এসেছে।

বর্তমান pattern-এর বদলে:

```bash
python -c '...'
```

এর ভিতরে GitHub secret interpolation করা উচিত নয়।

Safe pattern:

```yaml
env:
  RENDER_API_KEY: ${{ secrets.RENDER_API_KEY }}
run: |
  python scripts/ci/render_trigger_deploy.py
```

Python:

```python
api_key = os.environ["RENDER_API_KEY"]
```

এতে:

- quoting সমস্যা কমে
- secret masking-safe হয়
- একই script সব Render service ব্যবহার করতে পারে
- retry logic reusable হয়

---

# 15. Four Render Targets — Recommended Model

বর্তমান logical deployment targets:

```text
Render
├── Core
├── Worker
├── Scraper
└── MCP Control Tower
```

কিন্তু image strategy:

```text
Core image
Worker image
Scraper image
MCP image
```

শুধু **যে image-এর source বা dependency পরিবর্তিত হয়েছে সেটি build** হবে।

---

# 16. Long-Term “Zero-Waste CI” Rule

CI সিদ্ধান্ত নেবে:

```text
What changed?
       ↓
What is affected?
       ↓
What needs testing?
       ↓
What artifact needs rebuilding?
       ↓
What service needs redeploying?
```

অর্থাৎ:

> **Every push ≠ rebuild everything.**

---

# 17. Target Runtime

বর্তমান ~12.9 মিনিট run-এর লক্ষ্য:

### First target

```text
~8 minutes
```

### Optimized target

```text
~5–7 minutes
```

### Small frontend/docs/config-only push

```text
~1–3 minutes
```

এগুলো engineering targets; guarantee নয়। বাস্তব measurement-এর পরে thresholds ঠিক করতে হবে।

---

# 18. Implementation Order

### Step 1 — Reliability
- Fix shared Render deploy trigger script.
- Fix/diagnose DB Schema Contract Check.
- Clean Redis/test environment noise.

### Step 2 — Biggest Runtime Win
- Parallel Core/Worker/Scraper/MCP image builds.
- Enable persistent BuildKit/GHA cache.

### Step 3 — Smart Build Selection
- Connect path detection to image matrix.
- Build only affected images.

### Step 4 — Smart Deployment
- Deploy only affected Render services.
- Use immutable Git SHA/digest.

### Step 5 — Test Optimization
- Parallelize safe backend test groups.
- Reduce duplicate setup.

---

# 19. Final Recommendation

**Render-এ source rebuild করানোতে ফিরে যাওয়ার দরকার নেই।**

বর্তমান architecture-এর জন্য সবচেয়ে smart model:

```text
GitHub Actions
    ↓
Test once
    ↓
Build affected images once
    ↓
Cache layers
    ↓
Push immutable artifact to GHCR
    ↓
Sign + SBOM
    ↓
Deploy exact artifact to Render
    ↓
Health verify
```

এতে Render free-tier build limit নিয়ে dependency কমে এবং একই artifact Core/Worker/Scraper-এর মধ্যে predictable থাকে।

সবচেয়ে বড় immediate win হবে:

> **Sequential 3-image build → parallel cached affected-image build.**

আর দ্বিতীয় বড় win:

> **প্রতিটি push-এ সব service rebuild/redeploy নয়; change-aware artifact + deployment selection।**