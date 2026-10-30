# Browser CI #3538 (Run 41089438563) — parity census, artifact correction, and the durable lane fix (2026-10-31)

- **Refs:** #3538 (P0 CI incident) · landed triage #3545 (U3 facts) · landed delta #3561 (Delta A corrected here, Delta B confirmed here) · precedent shape: #3474
- **Agent:** GLM Agent 28 · Job 486832 · probes 2026-10-31 00:28–01:15+08 (= 2026-10-30 16:28–17:15Z) · zero-credential tower lane + local mirror plane · no claim taken on the issue (lease held by GLM-Agent-24 from 16:43Z; anti-stampede respected — this receipt rides its own bridge work order)
- **Verdict:** #3545's U3 facts CONFIRMED · **#3561's Delta B (≤18s fast-fail in the unpinned install) CONFIRMED** · **#3561's Delta A (malformed `branches:` trigger) RETRACTED — artifact-victimized evidence; the trigger blob is byte-intact** · NEW: full 49/49 blob-parity census satellite↔mirror, experimental proof of a second latent break (`cryptography` missing from the CI toolchain — the probe suite errors without it), and the durable fix landed as code: pinned-closure-first install + retry guard + a standing byte-level trigger guard (`tests/test_satellite_workflow_triggers.py`, mutation-proven).

**বাংলা সারসংক্ষেপ:** লুপ P0 #3538 দিয়েছে। তদন্তে দেখা গেছে — (১) স্যাটেলাইটের সব .py ফাইল (৪৯/৪৯) ও কনফিগ সবুজ মিররের সাথে blob-পর্যায়ে অভিন্ন, তাই কনটেন্ট কোনো ধাপই ভাঙে না; (২) #3561 যে "ভাঙা ট্রিগার" রিপোর্ট করেছে সেটি আসলে #3467 read-আর্টিফ্যাক্টের শিকার — `od` দিয়ে বাইট-স্তরে প্রমাণিত সব ৬টি মিরর workflow-এ `branches: [main]` অক্ষত; (৩) কিন্তু লেনে আরেকটি লুকানো ব্রেক আছে — `test_webbotauth_probe.py` মডিউল-লেভেলে `cryptography` আমদানি করে অথচ CI সেট ইনস্টলই করে না: CI-সমতুল্য venv-এ ৯ passed + ১ ERROR (cryptography ছাড়া), ১৭ passed (সহ) — অর্থাৎ pip ঠিক হলেও পরের রান লাল হত; (৪) স্থায়ী প্রতিকার কোড হিসেবে জমা হয়েছে: pinned-closure-first ইনস্টল + retry guard + বাইট-স্তরের ট্রিগার গার্ড।

## 1. Correcting #3561 Delta A — the trigger is intact; the evidence was the artifact

#3561 reported the satellite `ci.yml` trigger as textually malformed (`branches: ain]`) "mechanically verified" via `github.read_file` at two refs. The read plane is exactly where #3467's nondeterministic `[m`-span stripping lives. Byte-level verification of the ACTUAL blob:

- The satellite's `ci.yml` blob is `324471d6d0f1edb35b09ee936a02e1619a75184c` (tower `github.read_file` sha echo) — **bit-identical to the open mirror's** `browser/.github/workflows/ci.yml` (`git hash-object` = same sha).
- `od -c` on the mirror's line 5 returns the literal bytes `b r a n c h e s :   [ m a i n ] \n` — the flow sequence is intact. All six mirrored satellite workflows (browser/core/gateway `ci.yml`, studio `pipeline.yml` + `upstream-sync.yml`, vscode `release.yml`) verified the same way: every `branches:` line is `branches: [main]`.
- Display-path caveat demonstrated live during this probe: `rg`/`cat -A` on the intact file returned `ain]` while `od -c` on the same bytes returned `[main]` in the same session — the artifact is not tower-specific, it corrupts ANY text display of the payload. Only byte-level dumps (od/xxd) are trustworthy for this span class.

Consequence: the satellite trigger never fired "fail-open on a broken glob"; it has been a correct `branches: [main]` filter all along (the 19-run push/main history is consistent with the intact filter, no fail-open inference needed). **No admin action is needed on any `branches:` line.** An admin "restoring" the trigger from an artifact-read payload would be the first real corruption of this file.

## 2. Parity census — 49/49 Python blobs + all configs identical satellite↔mirror

Every `.py` file in the open mirror (49 files, incl. the 3 test files and `scripts/webbotauth/probe.py`) was read from the private satellite via the tower and blob-sha-compared against `git hash-object` of the mirror twin: **49/49 IDENTICAL, 0 differ, 0 absent.** Configs verified the same way: `ci.yml` (324471d6), `pyproject.toml` (ba9d50f5), `requirements.txt` (f4922342), `render.yaml` (430c8549), `server.py`, `main.py`. The only satellite↔mirror deltas found are the founder's docs-removal commit 4359f154 itself (e.g. `scripts/webbotauth/PROBE_EVIDENCE_2026-10-28.md` present in the mirror, absent on the satellite) — no code delta.

This supersedes #3561's requirements.txt-only parity with a whole-tree census: no test, no lint target, and no secret-scan surface differs between the green Run 18 state and the red Run 19 state.

## 3. The real latent break — `cryptography` missing from the CI toolchain (experimentally proven)

`test_webbotauth_probe.py` loads `scripts/webbotauth/probe.py` through importlib in its module fixture; `probe.py` imports `cryptography` at module level (line 43). The CI install line never installs it, and the pinned `requirements.txt` closure (23 packages, #2042) does not carry it either. Reproduced in a CI-equivalent clean venv (pytest + fastapi + httpx + pydantic + beautifulsoup4 + loguru + pytest-asyncio, python 3.12):

- **without `cryptography`: 9 passed, 1 ERROR** (`ModuleNotFoundError: No module named 'cryptography'` at the probe fixture) — pytest exits non-zero → the job goes red;
- **with `cryptography`: 17 passed, 1 skipped** — exactly the green shape.

So once the transient fast-fail (#3561 Delta B, confirmed below) is past, the very next browser main run would have gone red again on this collection error. The lane had two independent breaks stacked.

## 4. Run 19 fast-fail — Delta B confirmed, and the durable remedy (ready-to-apply admin patch)

Concur with #3561's arithmetic: run created 16:23:27Z, watchdog-env tail at 16:23:45Z → the whole job lived ≲18s; pip's cold resolution of 8 packages cannot fit that window, so pytest/ruff never ran and the unpinned single-shot install died mid-flight (transient registry/network class). The remedy is exactly the hardening #3561 prescribed; it could NOT ride this bridge submission because the intake hard-rejects `.github/` writes (live verdict: "Path 'browser/.github/workflows/ci.yml' is protected (.github/)" — the #2512 contract working as designed). The exact patch for the admin lane, verified locally (yaml.safe_load parses; the full mirror suite passes 17 passed / 1 skipped under the new install set):

```yaml
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          # Pinned runtime closure FIRST (#2042 pattern): fastapi/httpx/pydantic
          # stop floating at CI time — they re-resolved latest on every run.
          pip install -r requirements.txt
          # Toolchain + the probe suite's module-level `cryptography` import
          # (test_webbotauth_probe.py errors at fixture setup without it —
          # CI-equivalent venv repro 2026-10-31: 9 passed + 1 ERROR without,
          # 17 passed with). Retry-once guards the transient-registry
          # fast-fail class that red Run 41089438563 (#3538): the whole job
          # lived <= ~18s, so the unpinned single-shot install died mid-flight.
          pip install ruff pytest pytest-asyncio beautifulsoup4 loguru cryptography \
            || { sleep 20; pip install ruff pytest pytest-asyncio beautifulsoup4 loguru cryptography; }
```

It replaces the current block (`pip install ruff pytest pytest-asyncio pydantic fastapi httpx beautifulsoup4 loguru` + the `|| true` requirements line). Three effects:

1. `pip install -r requirements.txt` FIRST — the heavy deps (fastapi/httpx/pydantic) stop floating at CI time (#2042 pattern applied to the CI lane);
2. the tool line drops the now-pinned trio and adds `cryptography` (section 3's proven fix);
3. retry-once (`|| { sleep 20; ... }`) on the tool line — the transient fast-fail class cannot red the lane twice in a row on a blip.

## 5. Standing guard — byte-level trigger validation, mutation-proven

`tests/test_satellite_workflow_triggers.py` (new, PyYAML-only) pins the mirror plane: every mirrored satellite workflow's `push`/`pull_request` branch filter must be (1) a YAML list — a bare scalar is the #3467 truncation shape and fails; (2) bracket-free/glob-safe entries; (3) the six main-trigger lanes must keep `main`. It reads REAL working-tree bytes (no tower, no display path). Mutation test executed during this cycle: corrupting `[main]` → `ain]` in the mirror flips the guard red; restoring flips it green. The artifact class's most dangerous vector — a corrupted full_file landing through the bridge — is now mechanically blocked from entering the mirror plane, and the sync (`sync_workflows`) therefore cannot propagate it to the satellites.

## 6. Scope discipline and resolution predicate

- No claim taken on #3538 (GLM-Agent-24 holds the 16:43Z lease); this receipt + guard ride their own bridge work order, `Refs #3538`, **no autoclose** — the resolution predicate stays as landed in #3545/#3561: **next browser main run green**. Section 4's patch is the admin-lane item; the guard lands agent-side now.
- Admin-lane follow-ups (out of agent envelope): (1) apply section 4's ci.yml install patch (bridge hard-rejects `.github/` — by design, #2512); (2) `cryptography` may deserve a row in the pinned `requirements.txt` closure for the Render runtime too — not done here because that surface is CVE-guard-tracked (#1975) and is a maintainer bump decision (#1969 doctrine).

## 7. Reflection Evidence

- **why:** the loop dispatched the P0 as a solver task; the two landed triages left the admin-lane fix list containing one ghost item (Delta A) and one confirmed item without a landing path. Rederiving the whole failure from the mirror plane (blob census + clean-venv experiment + byte dumps) both corrected the record and produced an agent-reachable durable fix (install hardening + standing guard) instead of a third report that re-argues the same facts. The correction matters operationally: an admin acting on Delta A would have written the first real corruption into the satellite trigger.
- **alternatives_rejected:**
  - second full triage re-arguing U3/timeline: duplicate of #3545/#3561; only deltas minted here.
  - fixing `branches:` anywhere: nothing to fix — od-level bytes prove `[main]` intact on all six; a "fix" would BE the corruption.
  - adding `cryptography` to the pinned requirements.txt: touches the Render runtime surface (CVE-guard #1975, no-auto-bump #1969) — maintainer decision; CI-scoped install is the minimal safe fix.
  - pinning exact CI tool versions: would freeze today's sandbox-resolved versions I cannot verify as the satellite's known-good set; retry-once + pinned-closure-first addresses the failure class without inventing pins.
  - claiming #3538: lease held by GLM-Agent-24 (16:43Z) — anti-stampede; the work order carries the evidence instead.
