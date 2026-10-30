# 2026-10-31 07:19+08 — correction to the #3806 false-resolve receipt (GLM Agent 19)

U2 self-correction, same cycle as the original. One claim in
`bridge-20261031-3806-false-resolve-glm19-r1.md` (WO #3954 / PR #3955) is
wrong-scoped and is retracted here; the rest stands.

## Retracted: "gateway fully dark"

- The receipt said: "Gateway fully dark: `/`, `/health`, `/healthz`,
  `/api/health` all 404 — ops incident, P1-adjacent", without naming the
  host. A reader must assume the canonical public gateway — which is wrong.
- What was actually probed at 23:22Z: `supremeai-gateway.onrender.com`
  (all-404). That host appears **nowhere** in the repo (`git grep` → 0
  hits); it is not a documented federation service. The canonical gateway is
  `supremeai-api-ulw0.onrender.com` (README "Live Federation Services"
  table; the 05:19 A2A receipt's control-plane baseline), and it is
  **healthy**: `/health` → 200 `{"status":"healthy","service_name":
  "supremeai-api","version":"2.0.0","chat_ready":true}` at 23:28:52Z.
- The "gateway went dark between 21:24Z and 23:22Z" narrative is false. No
  evidence of any canonical-gateway outage exists in this cycle.

## Standing (unchanged, re-verified)

- A2A card URLs 404 on the **tower** at 23:22:10Z: `/.well-known/agent-card.json`,
  `/a2a` (plus legacy `agent.json` 404). The card's own `url` field declares
  `https://supremeai-mcp-tower.onrender.com/a2a`, so the tower is the
  card-relevant host; the serving-gap finding of #3806 is intact.
- Canonical gateway serves no A2A paths either (05:19 receipt: 404 ×4 with
  health 200 — the same split as the tower's).
- Tower `/health` 23:22:28Z self-reports `status:"degraded"` (20/21 healthy,
  `stale:true`, `lastCompletedSweepAt:null`, `sweepCompletions:0`).
- The false auto-close of #3806 ("Auto-closed: linked PR #2779 merged.") and
  its root-cause class (merge-linked ≠ finding-resolved) are unaffected by
  this correction.

## Meta root cause (fix so it cannot recur)

The bad probe target was reconstructed from memory instead of being taken
from the artifact under test — the landed 05:19 receipt records the exact
baseline host precisely so it can be re-probed. Rule going forward in this
lane: **a re-probe target must be quoted from the prior receipt or the repo
artifact, never recalled**; correction receipts quote the full URL of every
probe. Owner note: if PR #3955 has not landed yet, amending or rejecting it
in favor of this corrected receipt is preferred; if it has landed, this file
is the standing correction and the retraction is part of the public record.

U5: no other agent has filed a correction or duplicate for #3954 (tower
board + open-issue search, 23:29Z).
