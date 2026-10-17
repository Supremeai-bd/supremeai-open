# SupremeAI Infrastructure Guardian

The **Autonomous Infrastructure Guardian (ইনফ্রাস্ট্রাকচার গার্ডিয়ান)** oversees federation-wide uptime, runner quota budgeting, container sandboxes, and disaster recovery automations across all 11 federation satellites.

## Architecture

```text
infra/
├── ops/
│   ├── health_watchdog.py        # Periodic multi-satellite HTTP/probe watchdog
│   └── quota_monitor.py          # GitHub Actions quota burn rate alerting (2,000 min/mo budget)
├── docker/
│   ├── sandbox.Dockerfile        # Hardened non-root agent execution container
│   └── docker-compose.yml        # Local federation services mock stack
├── dr/
│   ├── snapshot_backup.sh        # Database and state snapshot automation
│   └── automated_rollback.py     # Fail-closed automated deployment rollback engine
└── tests/
    └── test_infra_watchdog.py    # Unit tests for health probes, quotas, and DR triggers
```

## Quick Start & Verification

### Boot Smoke Test
```bash
python -c "from infra.ops.health_watchdog import FederationWatchdog; print('Infra guardian boot smoke: SUCCESS')"
```

### Run Unit Tests
```bash
python -m unittest infra/tests/test_infra_watchdog.py
```
