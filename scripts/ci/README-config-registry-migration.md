# Registry evidence workflow

Run from the repository root:

```bash
python scripts/ci/config_registry_evidence.py > config-registry-report.json
```

The report is intentionally non-authoritative. Review each unclassified key against
its runtime default, type, feature flag, deployment configuration and credential use
before adding it to `backend/core/config_classification.py`.

Do not use variable-name heuristics as the final classification rule.
