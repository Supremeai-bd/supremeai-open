# SupremeAI unified deployment reference (issue #339)

Fail-closed deployment orchestration artifacts for the federation gateway
layer, with a pytest integrity suite that gates every landing.

| Artifact | Role |
| -------- | ---- |
| `deployments/render.yaml`           | Render Blueprint reference: gateway web + worker services, `/healthz` probe, every secret rides the dashboard (`sync: false`) — no committed values |
| `deployments/secrets-inventory.json`| Secret KEY inventory (names, owners, purpose, rotation surface — never values); the integrity SSOT cross-referenced by the tests |
| `deployments/Dockerfile`            | Pinned base, non-root UID 10001, HEALTHCHECK on the credential-free probe, no dot-env/.git in the image |
| `scripts/deploy.sh`                 | POSIX deploy orchestrator: gate 1 (no value-shaped secrets in `deployments/`), gate 2 (manifest keys ⊆ inventory), dry-run default — live deploy is operator-side by construction |
| `scripts/ops/health_check.py`       | AC3 fail-closed health probe: non-2xx, timeout, refusal, non-JSON, and 200-but-self-reported-degraded ALL exit 1 |
| `tests/test_infra_integrity.py`     | 17 offline pytest integrity checks (AC1/AC2/AC3 + boot smoke) |

## Verification (issue contract)

```bash
bash -n scripts/deploy.sh                      # boot smoke
pytest tests/test_infra_integrity.py -v        # integrity suite
```

`docker build` requires a docker runtime and is therefore not executed in the
public verification environment; the Dockerfile's structural invariants
(non-root, HEALTHCHECK, pinned base, no secret-bearing COPY) are enforced by
the pytest suite instead — honestly stated, per the no-unverified-success
doctrine.

## Secret posture (AC1)

- Values live ONLY in the Render dashboard / provider consoles.
- Manifests declare `sync: false` (or `generateValue`) — the suite fails any
  literal value on a secret-shaped key.
- `secrets-inventory.json` lists names + owners + purpose; the suite fails
  any key declared in a manifest but missing from the inventory, and any
  value-shaped blob inside the inventory itself.
