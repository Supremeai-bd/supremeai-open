# Vanguard's Journal 🛡️⚡

## 2026-03-31 - Fix Dynamic Credential Broker Undefined Variables in Infisical Vault Key Fetch
**Type:** Security 🛡️
**Finding / Learning:** In `scripts/agents/dynamic_credential_broker.py`, `_fetch_vault_keys` referenced undefined variables (`ROOT_DIR`, `env`, `allowed_keys`, `scoped`) when attempting to invoke `scripts/security/fetch_ai_keys.py` for missing vault credentials. The bare `except Exception: pass` swallowed the `NameError`, preventing dynamic credential fetching for assigned agent roles.
**Rule:** Always define `ROOT_DIR = Path(__file__).resolve().parents[N]` explicitly in script modules invoking repository relative helpers and ensure subprocess return objects are not assigned to dict variables.
