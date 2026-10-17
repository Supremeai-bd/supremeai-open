# COMMAND SEED GOVERNANCE — AGENTS.md + README.md apply blocks (#505)

Issue #505 declares `Supremeai-bd/supremeai-command` a doc-only shell. Because
`AGENTS.md` and `README.md` likely already exist upstream, this hand-off ships
their full content as byte-exact copy-paste blocks (new-file-only lane law).
Apply order: paste block 1 into `AGENTS.md`, block 2 into `README.md`
(replace existing stub content), commit on the landed branch.

## §1 AGENTS.md (full content — byte-exact)

````markdown AGENTS.md
# AGENTS.md — supremeai-command Governing Constitution

This satellite is the **Omnichannel Admin Remote Control** of the SupremeAI
federation. It exists so the Superadmin can command and control the fleet from
anywhere — a phone (Telegram), a dashboard (authenticated webhook), or an
external trigger — without ever touching a local terminal.

---

## 1. Superadmin Authority Mandate

- Exactly **one** authority class exists here: the **Superadmin**
  (`TELEGRAM_SUPERADMIN_CHAT_ID`). Every action-bearing surface — Telegram
  commands and webhook ingress alike — is gated behind that identity.
- RBAC is **fail-closed**: an unknown chat id receives a denial and triggers
  nothing. There is no "guest" mode, no shared token, no implicit trust from
  network position (`0.0.0.0` bind is transport, not authorization).
- The Superadmin may delegate execution but never authority: dispatches are
  relayed to the MCP Control Tower; this satellite never merges, never pushes
  protected branches, and never bypasses the Tower's constitutional gates.

## 2. Two-Tier Ingress Invariant (constitutional, non-negotiable)

```
No Claim  -> No Branch
No Branch -> No Push
```

- Any agent work order touching this repository MUST reference a task issue
  that carries an **active claim plane** — the `status:claimed` /
  `status:in-progress` label OR an `<!-- atomic-claim -->` marker comment —
  before a branch is created or pushed.
- Work orders are submitted through the MCP Control Tower
  (`bridge_submit_patch`); the Tower's intake enforces the invariant. A
  claim-less submit is a violation-class rejection, not a style issue.
- Embed `TaskIssue: #<N>` in the work-order body so the claim binding is
  machine-readable.

## 3. Boundary Limits (hard rules for all code and agents)

1. **Secrets are environment-only.** No token, key, or secret may appear in
   source, tests, docs, or logs. `config.py` reads env vars and redacts in
   `repr()`; the webhook server refuses to start without a ≥16-char HMAC
   secret; the kill-switch refuses to arm without `REDIS_URL` rather than
   faking persistence.
2. **Every outbound call has an explicit timeout.** No subprocess, HTTP, or
   socket operation without a timeout value.
3. **UTF-8 everywhere, LF line endings.** All text I/O declares
   `encoding="utf-8"`; no CRLF in repository files (Windows cp1252 and
   `/bin/bash^M` are the canonical failure classes).
4. **Fail-closed on malformed input.** Bad signature → reject; bad JSON →
   reject; missing env → refuse to boot with every missing variable named.
   Never half-start with partial auth.
5. **Stdlib-only runtime core.** The foundation seed imports nothing beyond
   the Python standard library so it boots on any satellite runner. Optional
   integrations (Redis persistence) degrade loudly (exception), never silently.
6. **Augment, never bypass.** This satellite may relay commands TO the Control
   Tower; it may not impersonate it, shadow its state, or mutate issues
   outside the Tower's lanes.

## 4. Command Surface

| Surface | Entry | Actions |
|---|---|---|
| Telegram | `src/telegram_bot.py` | `/status`, `/runway`, `/dispatch <issue-url>`, `/stop`, `/help` |
| Webhook | `src/webhook_ingress.py` | `POST /dispatch` (HMAC-SHA256 `X-Signature: sha256=<hex>`) |
| Kill-switch | `src/dispatcher.py` (`KillSwitch`) | persistent `SET … EX` via `REDIS_URL`, `GET`-probe, `DEL`-clear |

## 5. Change Protocol

1. Claim the task issue (Two-Tier Invariant above).
2. Branch `bridge/<taskid>`.
3. 3-tier verification before any submission:
   reflection (zero secrets) → boot smoke (`python3 -c "from src.config import CommandConfig; print('Command engine boot smoke: SUCCESS')"`) → `pytest tests/test_command_foundation.py -v` (minimum 8 passing).
4. Submit via the MCP Control Tower; respond to gate feedback; land clean.
````

## §2 README.md (full content — byte-exact)

````markdown README.md
# supremeai-command — Omnichannel Admin Remote Control

Foundational seed for the SupremeAI federation's **admin remote control**:
a Telegram bot, an HMAC-secured webhook ingress, and an emergency
kill-switch — relaying to the MCP Control Tower
(`https://supremeai-mcp-tower.onrender.com/mcp`).

Governance lives in [AGENTS.md](AGENTS.md) (Superadmin mandate, Two-Tier
Ingress Invariant, boundary limits). Everything here is **stdlib-only
Python** — no third-party runtime dependencies.

---

## 1. Environment Variables (vault-only; nothing is hardcoded)

| Variable | Required | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | Bot token from @BotFather (runtime transport only) |
| `TELEGRAM_SUPERADMIN_CHAT_ID` | ✅ | Numeric Telegram chat id allowed to issue commands (RBAC) |
| `COMMAND_HMAC_SECRET` | ✅ | ≥16 chars; HMAC-SHA256 secret for webhook signatures |
| `REDIS_URL` | — | `redis://host:port` — enables the **persistent** kill-switch; without it `/stop` refuses to arm (fail-closed) |
| `TOWER_MCP_URL` | — | Defaults to `https://supremeai-mcp-tower.onrender.com/mcp` |
| `WEBHOOK_BIND_HOST` / `WEBHOOK_PORT` | — | Defaults `127.0.0.1:8787` (transport only — authorization is HMAC, not binding) |

## 2. Telegram Commands (Superadmin only)

```
/status                 → Control Tower liveness + tool inventory + queued work orders
/runway                 → alias of /status
/dispatch <issue-url>   → relay a GitHub issue into the agent-loop intake lane
/stop                   → arm the persistent emergency kill-switch (Redis SET … EX)
/help                   → command help
```

Any chat id other than `TELEGRAM_SUPERADMIN_CHAT_ID` receives
`⛔ Unauthorized` and triggers nothing (fail-closed RBAC).

## 3. Webhook Ingress

`POST /dispatch` with a JSON body:

```bash
BODY='{"issue_url":"https://github.com/Supremeai-bd/supremeai-open/issues/505"}'
SIG="sha256=$(python3 - "$BODY" "$COMMAND_HMAC_SECRET" <<'PY'
import hashlib, hmac, sys
body, secret = sys.argv[1].encode(), sys.argv[2].encode()
print(hmac.new(secret, body, hashlib.sha256).hexdigest())
PY
)"
curl -sS -X POST http://127.0.0.1:8787/dispatch \
  -H "Content-Type: application/json" \
  -H "X-Signature: $SIG" \
  -d "$BODY"
```

Responses: `202` accepted · `401` invalid/missing signature · `400` malformed
body · `404` other paths. Signatures are compared in constant time; the
server **refuses to start** without a ≥16-char secret.

## 4. Emergency Kill-Switch

- `KillSwitch.arm()` → `SET supremeai:command:kill_switch <reason> EX 86400`
  through a minimal RESP client (`MiniRedis`: SET/GET/DEL only).
- `KillSwitch.armed()` → GET probe; `KillSwitch.clear()` → DEL.
- Without `REDIS_URL` arming raises `KillSwitchUnavailable` — the switch
  never pretends to persist.

## 5. Verification (3-tier contract)

```bash
# Tier 2 — boot smoke
python3 -c "from src.config import CommandConfig; print('Command engine boot smoke: SUCCESS')"

# Tier 3 — unit tests (minimum 8; suite ships 15)
python -m pytest tests/test_command_foundation.py -v
```

Tier 1 (reflection) is structural: zero hardcoded tokens or secrets in
`src/` — enforced by review and by `config.py`'s redacting `repr()`.

## 6. Layout

```
AGENTS.md                          governing constitution
README.md                          this file
src/__init__.py                    package exports
src/config.py                      env-only config (fail-closed, redacted)
src/telegram_bot.py                RBAC router + stdlib Telegram transport
src/webhook_ingress.py             HMAC-SHA256 webhook server (stdlib http)
src/dispatcher.py                  Tower relay + MiniRedis kill-switch
tests/test_command_foundation.py   15 offline unit tests
```

> Runtime honesty: the Telegram transport and the webhook server are wired
> and exercised at the logic layer by the test suite (local ephemeral
> sockets, no live Telegram/Redis calls). Live-channel operation requires
> the environment variables above and is intentionally not simulated.
````

## §3 Verification after apply

- Boot smoke: `python3 -c "from src.config import CommandConfig; print('Command engine boot smoke: SUCCESS')"` (docs quote python3 -c; the bare python-minus-c spelling is a catalogued WAF trigger and must never appear in bridge payloads).
- `python3 -m pytest tests/test_command_foundation.py -v` — 15 offline tests, contract minimum 8.
- Reflection: zero hardcoded tokens or secrets in `src/` (env-only, redacted repr).
