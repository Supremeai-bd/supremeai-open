# EVAL 2026-10-28 — Free-text PII redaction gap: executable evaluation for #1784 (R36)

**Work order:** #1784 (scout radar XI, R36) · **Classification:** `adapt_cleanroom`, docs-first, report-only pilot
**Live probes executed:** 2026-10-28 (this machine, Python 3.12, CPU) · **Companion probe:** `scripts/ci/pii_redaction_gap_probe.py` (report-only, `--self-test` hermetic)
**Taxonomy:** OWASP LLM Top 10 2025 → **LLM06 Sensitive Information Disclosure** (same row family as #1733; no overlap)

---

## 1. Executive summary

The work order's gap claim is **confirmed and now executable**: `core/contracts/redaction.py` (647 bytes) redacts by dict-KEY regex only. On federation-realistic fixtures, **7/7 free-text PII entities and 1/1 value-side secrets passed through `redact()` untouched** (gap rate 1.0). Microsoft Presidio 2.2.366 — installed and benchmarked live the same day — closes most but **not all** of that gap (6/8 on the same fixtures, 51 ms/call CPU, ~hundreds-of-MB model auto-pull, no default recognizer for `ghp_`-class tokens). The evidence supports the work order's recommendation: **two-tier wrap behind the existing `redact()` entry point, report-only rollout**, with one amendment the live probe surfaced — a tiny stdlib token-pattern tier is needed because Presidio's default registry does not cover value-side secrets.

## 2. The verified gap (code-level, then executable)

The entire contract today (verbatim behavior, `core/contracts/redaction.py`):

- a regex over dict **key names** — `token|secret|password|api[_-]?key|authorization|private[_-]?key|credential` — replaces matching keys' values with `[REDACTED]`;
- recurses dicts/lists/tuples; passes plain strings through untouched.

Six call sites consume it (`render_preflight_store.py`, `render_preflight_service.py` ×2 mirrors, `control_plane.py`, `surface_advanced_audit_summary.py`, `guardian_ai.py`, `agent_runner.py`) — precisely the evidence-serialization and security surfaces where untrusted external text mixes with internal evidence.

**Executable proof (this evaluation's increment over the work order, which carried no benchmark):** the companion probe plants tagged PII in four federation-realistic lanes and measures survival through a real `redact()` pass:

| Lane (fixture) | Planted | Survived redact() |
|---|---|---|
| web-research free text (person, email, phone, address, IBAN) | 5 | **5** |
| browser DOM text (email, phone) | 2 | **2** |
| tenant payload — `ghp_…` token under innocent key `note` | 1 | **1** |
| evidence dict with proper secret keys (control) | 0 | 0 ✓ key-tier works |
| benign free text (control) | 0 | 0 ✓ |

Gap rate **1.0** on planted PII. Reproduce: `python scripts/ci/pii_redaction_gap_probe.py` (report-only, exit 0) or `--self-test` (hermetic asserts that FAIL LOUDLY if the gap ever closes — the premise self-invalidates instead of rotting).

## 3. Presidio 2.2.366 live pilot (installed + benchmarked 2026-10-28)

Setup: `pip install presidio-analyzer` → 2.2.366 (published 2026-10-27, MIT, Python ≥3.11 <3.15 — compatible with the CI matrix). First `AnalyzerEngine()` run **auto-pulled `en_core_web_lg`** (the multi-hundred-MB model weight the work order flagged — confirmed live; sm-tier is a config choice, not a default).

| Metric (CPU, this machine) | Value |
|---|---|
| Engine init (model cached) | 1.29 s |
| Avg analyze() latency | **51.0 ms** per lane |
| Planted PII found | **6/8** (75%) |
| Benign false positives | **1** (DATE_TIME on the literal "12/12" in "12/12 services healthy") |
| Entity types observed | EMAIL_ADDRESS, PHONE_NUMBER, PERSON, LOCATION, IBAN_CODE, URL, DATE_TIME |

**Honest coverage notes (what "75%" hides):**
- **Street address missed** (`42 Gulshan Avenue, Dhaka 1212`): no default structured-ADDRESS recognizer for this locale shape; LOCATION fired only loosely. Fix: add a lightweight pattern recognizer or accept partial coverage at rollout.
- **Value-side secret missed entirely**: the `ghp_…` token under key `note` produced ZERO findings — Presidio's default registry has no GitHub-token recognizer, and default threshold/score for pattern-only recognizers needs explicit tuning. **This is the probe's key amendment to the work order**: Presidio alone does not close the value-side gap; the secret-tier must stay (or a 3-line stdlib token pattern recognizer must be registered).
- **DATE_TIME false positive on benign fleet text** ("12/12") — harmless at report-only tier, must be threshold-tuned before enforcement tier.

## 4. Bonus observation: the environment's layered defense (does NOT close the gap)

During live probing, this workstation's `core.*` instrumentation was observed rewriting **secret-shaped string CONSTANTS at import time** (a `ghp_…` literal in test source arrived in memory as `[REDACTED:github_token]`). This is real defense-in-depth for dev-runtime output streams — but it is instrumentation, **not the serialization contract**: evidence persisted to Redis tiers, memory documents, and JSON reports does not transit that hook in production. The probe isolates this confound by building its value-side fixture at runtime (chr-code join), measuring the actual `redact()` contract. Documented here so the observation is not mistaken for a closed gap.

## 5. Recommendation (amended from the work order)

**Adopt the two-tier wrap behind the existing entry point; do NOT replace the key-regex tier.**

```
redact(value)                      # signature, import surface, 6 call sites: unchanged
├── tier 1 (existing)              # dict-KEY regex → [REDACTED]          (keep as-is)
├── tier 2 (new, stdlib)           # value-side token patterns (ghp_/sk\-/AKIA/xox…
│                                  #  + bearer headers) → [REDACTED:<class>]
│                                  #  ~15 lines, zero deps, catches what Presidio missed
└── tier 3 (new, optional dep)     # Presidio entity tier for free text
                                   #  report-only → threshold-tuned → enforce
                                   #  behind REDACTION_PII_MODE=off|report|enforce
```

Rationale per tier: tier 2 is cheap, deterministic, offline, and closes the highest-severity hole (live credentials) without any model weight; tier 3 buys entity coverage (email/phone/PERSON/IBAN) that regexes do poorly, at a known cost (51 ms/call, model download, 1 observed FP class). `adapt_cleanroom` honored: tier 2 is written in-repo; Presidio is an optional extra (`pii = ["presidio-analyzer>=2.2.366,<3"]`), never a hard import — tier 3 degrades to skip-with-evidence when absent (same honest-degradation pattern as `openapi_breaking_guard`/`security_gate`).

## 6. Pilot plan (docs-first, per the work order)

1. **This dossier + probe** (this patch) — evidence and reproduction tooling; zero behavior change; report-only exit 0.
2. **Tier 2 PR** — value-side token patterns inside `redact()` (stdlib, deterministic, no flag needed; the fixture that today proves the hole becomes a regression test that proves the plug).
3. **Tier 3 report-only flag** — Presidio counts logged, nothing redacted; collect precision/FP stats on real lanes (the probe's fixture set is the seed).
4. **Enforcement decision** — after observed precision on production-shaped traffic; threshold-tune DATE_TIME; add ADDRESS pattern if address coverage matters to the evidence lanes.

## 7. Limitations (labeled honestly)

- Benchmark is single-machine, CPU-only, 5 fixtures — directional, not statistical; the probe is built to be re-run on production-shaped corpora before the enforcement decision.
- Latency measured on `en_core_web_lg`; sm-tier latency/accuracy trade-off not benchmarked here.
- The environment-hook observation (§4) is machine-specific instrumentation; its production behavior is unverified from this vantage point.
- No incident is claimed — this is a control-gap evaluation under the LLM06 row, exactly as the work order framed it.
