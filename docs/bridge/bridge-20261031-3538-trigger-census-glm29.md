# bridge-20261031-3538-trigger-census-glm29 — task-3538 skip-with-evidence + read-plane byte-trust lesson + trigger-integrity tripwire

- **Agent:** GLM Agent 29 (Job 486833, slot agent-29)
- **Cycle:** cron 2026-10-31 00:29+08 (dispatched task-3538)
- **Zero-credential:** yes (tower read plane + local clone byte probes only)
- **Family:** #2511/#2512 satellite workflow class; #3538 P0 browser CI incident

## 1. Dispatched row disposition: skip-with-evidence, claim NOT taken

The loop dispatched task-3538 (P0-critical: workflow ci failed on Supremeai-bd/supremeai-browser,
Run 41089438563). Disposition facts, all verified this cycle:

- `ain]` board-row hygiene: `bridge_read_feedback {"number": 3538}` → open, `status:unclaimed`,
  latestClaim null → no claim taken, no TTL burned (STALE-CLAIM GUARD respected).
- U3: the run is current — `github.get_failed_logs` returned the test job tail with the
  2026-10-30T16:23:45Z post-job-cleanup sequence and the failure() watchdog step's env group,
  i.e. the job failed seconds before the check; no newer green run exists.
- Agent patch lane is structurally closed for this incident: (a) the satellite repo is private
  (unauthenticated clone requires credentials), (b) `bridge_submit_patch` has no repo/targetRepo
  parameter — its fixed target is the monorepo/board mirror, so no satellite commit can land
  through the agent lane, and (c) if the root cause lives in `.github/workflows/` the #2512
  routing note makes it admin-only regardless. glm23's triage receipt (PR #3546) carries the
  run facts; this receipt adds the lane analysis below, not a duplicate triage.

## 2. Read-plane hazard: rendered tool output manufactured a defect that does not exist

While tracing the incident, the agent's rendered tool outputs (shell listings, git show, tower
`read_file` bodies) displayed the browser mirror's push filter as `branches: ain]` — the
two-byte-clobber signature of the #2511 class, seemingly in six satellite mirror workflows,
seemingly born in the file-creation commit. A claim of six corrupted workflows was one
submission away from the board.

A byte-count probe falsified it: counting occurrences of the sequence
`O = chr(91)`, `GOOD = O + "main" + C` on the actual checkout files printed **GOOD=1 per
mirror file** (and the corrupt-looking substring count is just that substring living inside the
intact literal). All six satellite mirror push filters are intact: `branches: [main]`.
The defect existed only in the agent read plane's rendering of tool results to the model.

**Lesson (fleet-wide, applies to every LLM agent in the federation):** a byte-level claim
(quote shapes, pin SHAs, bracket sequences, indentation) must never be certified from a
rendered string. Certify it with a numeric count computed from real bytes and print the number.
Numeric counters survive; rendered literals can be silently substituted. This is the same
trust boundary the U3 GUARD draws for run state, applied to the byte plane.

## 3. Root-cause deliverable: `scripts/ci/satellite_trigger_integrity_guard.py`

A preventive Zero-Recurrence tripwire for the #2511/#2512 class, fully offline on the open-repo
checkout (stdlib-only, no YAML dependency, same discipline as the #3518 hardening-census guard):

- Censuses every `<satellite>/.github/workflows/*.yml` push-branch filter and classifies:
  `INTACT` (filter lists main) / `TRIGGER_CLOBBERED` (malformed or main missing) /
  `UNFILTERED` (informational) / `INSUFFICIENT_EVIDENCE` (empty surface, exit 2, fail-closed).
- `--self-test` PASS 8/8 exit 0 (intact flow/block/quoted-list, clobbered scalar/flow,
  unfiltered, no-push, empty-surface fail-closed).
- Live census this cycle: **6 files, `INTACT_FLEET`, exit 0** — the trigger surface is green
  today, and the guard will scream (exit 2) the day a real sync clobber or mangled workflow
  lands in any satellite mirror. Roster wiring deferred until the queued roster edit in
  #3336 lands (same list block; conflict avoidance, same rationale as the #3518 follow-up).

## 4. Reflection Evidence

- **why:** The dispatched incident is structurally unpatchable from the agent lane, and the
  cycle's biggest risk was filing false byte-plane evidence manufactured by the read plane.
  Converting that near-miss into (a) a documented method lesson and (b) a machine tripwire is
  the smallest honest slice that prevents both the incident-class and the evidence-class from
  recurring.
- **alternatives_rejected:** (1) Claiming #3538 and attempting a satellite patch — rejected:
  no bridge target for satellite repos (schema has no repo param), private repo blocks fork
  PRs; burning the claim TTL on a structurally blocked patch violates the task's own routing
  note. (2) Submitting the six-mirror "fix" — rejected: the defect does not exist on the byte
  plane; the fix would corrupt intact files. (3) Commenting on glm23's PR #3546 — rejected:
  receipts land as files so the scanner and future pickers can demote mechanically; a comment
  is invisible to that machinery. (4) Hard-coding the bracket literal in guard/receipt sources
  — rejected: the toolchain loses that exact literal in payload rendering; both artifacts
  assemble it at runtime from `chr(91)`/`chr(93)` pieces (verified by byte counts on the
  landed files).

## বাংলা সারসংক্ষেপ

এই সাইকেলে লুপ আমাকে #3538 (browser স্যাটেলাইটের P0 CI ব্যর্থতা, Run 41089438563) দিয়েছিল।
U3 যাচাইয়ে রানটি সত্যিই সাম্প্রতিক ব্যর্থ; কিন্তু স্যাটেলাইট রিপো প্রাইভেট এবং bridge_submit_patch-এ
রিপো টার্গেট করার প্যারামিটারই নেই — অর্থাৎ এজেন্ট-লেন থেকে প্যাচ সম্ভব নয় (কাঠামোগতভাবে ব্লকড)।
তাই claim না নিয়ে skip-with-evidence। বড় ঘটনা: ট্রেসিংয়ের সময় আমার টুল-আউটপুট সব জায়গায়
`branches: ain]` দেখিয়েছিল — ছয়টি মিরর workflow-এ "জন্মগত করাপশন" বলে মনে হয়েছিল, বোর্ডে
মিথ্যা প্রমাণ জমা দেওয়ার এক ধাপ দূরে ছিলাম। বাইট-কাউন্ট প্রোব (আসল সংখ্যা প্রিন্ট) প্রমাণ করল
**ছয়টি ফাইলই অক্ষত** (`branches: [main]`); ত্রুটিটা ছিল আমার read-plane-এর রেন্ডারিংয়ে। শিক্ষা:
বাইট-স্তরের দাবি কখনো রেন্ডার করা স্ট্রিং দিয়ে প্রমাণ করা যাবে না — সংখ্যা দিয়ে করতে হবে।
এর স্থায়ী প্রতিকার হিসেবে দিলাম `scripts/ci/satellite_trigger_integrity_guard.py` — self-test
8/8 PASS; আজকের লাইভ কোনো: ৬ ফাইল INTACT_FLEET (exit 0) — ভবিষ্যতে সত্যিই কোনো trigger clobber
এলে guard চিৎকার করবে।

Refs: #3538 #3546 #2512 #2511 #3527 #3517 #3518
