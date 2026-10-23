# scripts/DEPLOYMENT_NOTES.md — Permanent Clock & Agent Scheduling Runbook

> Owner-directed runbook (explicit administrative authorization recorded in the
> bridge work order that landed this file). Companion to
> `scripts/agents/continuous_agent_loop.py`, `.github/workflows/federation-ci-watchdog.yml`,
> and `docs/CONTINUOUS_AGENT_LOOP_AND_SKILL_ARCHITECTURE.md`.

## TL;DR (বাংলা)

স্যান্ডবক্স সেশনে cron ডেমন নেই এবং সেশন শেষ হলে ব্যাকগ্রাউন্ড প্রসেস বন্ধ হয়ে যায় —
তাই কোনো ভার্চুয়াল এজেন্ট **নিজের ঘড়ি নিজে ধরে রাখতে পারে না**। সমাধান: ঘড়িটাকে
স্থায়ী কোনো সারফেসে রাখতে হবে — (A) GitHub Actions schedule (রেকমেন্ডেড, ফ্রি),
(B) পার্মানেন্ট হোস্টে crontab/systemd timer, (C) run_forever.py প্রসেস-রির‍্যাপার।
`continuous_agent_loop.py --schedule N` ইতিমধ্যেই start-to-start anchored
self-scheduler; ঘড়ি একবার টিক দিলেই লুপ নিজেই কাজ বেছে এজেন্ট ডিসপ্যাচ করে।
ভার্চুয়াল এজেন্টদের "জাগানো" লাগে না — তারা ক্লেইমেবল ইস্যু/bridge queue থেকে
কাজ তুলে নেয়; ঘড়ি শুধু কাজ তৈরি/রাউট করে।

## 1. The clock problem (why "agents wake themselves" needs a permanent surface)

- A virtual agent session (Z.ai, Claude, ChatGPT, Cursor) is **ephemeral**: when
  the session ends, its processes die and nothing it "scheduled" in-memory survives.
- The repo's own architecture doc is explicit: *"Skills do NOT run in the
  background by themselves. Hourly auditors and event-driven workers still need
  the Runtime/Orchestrator + scheduler/webhook."*
- Therefore the schedule must live on a **permanent surface** (Actions runner,
  VPS cron, systemd, or an always-on service), and the *loop* — not any single
  agent — owns dispatch. This is exactly the "Lazy Team Leader" contract.

## 2. Option A (recommended): GitHub Actions scheduled workflows — already 50% wired

`.github/workflows/federation-ci-watchdog.yml` already runs every 15 minutes:

```
cron: "*/15 * * * *"  ->  python scripts/ci/federation_ci_watchdog.py --poll --max-age-hours 1
```

The agent-loop equivalent (admin drops this as `.github/workflows/agent-loop.yml`;
`.github/*` is a protected path, hence documented here rather than patched):

```yaml
name: Continuous Agent Loop (Scheduled Dispatch)
on:
  schedule:
    - cron: "0 * * * *"   # hourly; start-to-start anchored inside the loop
  workflow_dispatch:
    inputs:
      cycles: { description: "cycles (0=indefinite)", default: "1" }
permissions:
  contents: read
  issues: write
  pull-requests: write
jobs:
  loop:
    runs-on: ubuntu-latest
    timeout-minutes: 55
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - name: One scheduled dispatch tick
        env:
          GH_TOKEN: ${{ secrets.MERGE_PAT || secrets.OPEN_SYNC_PAT || secrets.GITHUB_TOKEN }}
        run: |
          python scripts/agents/continuous_agent_loop.py \
            --schedule 60 --cycles ${CYCLES:-1}
```

Cost note: public repo → GitHub-hosted runners are free; the watchdog already
proves the pattern (per-tick `--cycles 1` keeps each run short and observable).

## 3. Option B: permanent host (VPS/home server) — crontab or systemd

- crontab (the loop prints its own line): `python3 scripts/agents/continuous_agent_loop.py --print-cron --schedule 60`
- systemd timer pair (user units are enough):

```ini
# supremeai-agent-loop.timer
[Unit] Description=SupremeAI agent loop tick
[Timer]
OnCalendar=hourly
Persistent=true
[Install] WantedBy=timers.target

# supremeai-agent-loop.service
[Unit] Description=SupremeAI agent loop (one tick)
[Service]
Type=oneshot
WorkingDirectory=/opt/supremeai-open
Environment=GH_TOKEN=...           # least-privilege PAT: issues:write + PR:write
ExecStart=/usr/bin/python3 scripts/agents/continuous_agent_loop.py --schedule 60 --cycles 1
```

`Persistent=true` + the loop's monotonic start-to-start anchor = missed ticks
catch up instead of drifting.

## 4. Option C: run_forever.py process wrapper (crash-resilient host process)

For a host where you want a single long-lived process instead of timer units:

```python
#!/usr/bin/env python3
"""run_forever.py — restart the scheduled loop if it ever dies (never on Ctrl-C)."""
import subprocess, sys, time
CMD = [sys.executable, "scripts/agents/continuous_agent_loop.py", "--schedule", "60"]
backoff = 15
while True:
    rc = subprocess.call(CMD)
    if rc == 130:                      # KeyboardInterrupt — clean stop
        break
    print(f"[run_forever] loop exited rc={rc}; restart in {backoff}s", flush=True)
    time.sleep(backoff)
    backoff = min(backoff * 2, 300)
```

Run it under `nohup`, `tmux`, `supervisord`, or a Render background worker.

## 5. How virtual agents plug into the scheduled clock

1. The clock ticks (Option A/B/C) → `continuous_agent_loop.py --schedule N` runs.
2. The loop picks the highest-priority claimable issue (or emits the
   `event:schedule.ecosystem_scan` auditor dispatch when the board is empty).
3. It builds the task envelope; an agent — Z.ai, Claude, a CLI runner — claims
   the issue (`work_claim` / atomic-claim comment), works, submits via bridge.
4. Nothing above requires any agent to "stay awake between ticks": agents are
   event-driven workers; the loop + board are the memory. External web agents
   (no repo credentials) simply read `bridge_work_queue` when invoked.

## 6. Related: board self-healing (same landing)

`federation_ci_watchdog.py --poll` now ends with an idempotent relink pass that
re-attaches any loose mirrored CI incident under CI Hub #761, and `--relink`
runs it standalone. After this lands, the next scheduled tick repairs the root
board back to exactly the 8 anchor hubs with zero admin clicks.
