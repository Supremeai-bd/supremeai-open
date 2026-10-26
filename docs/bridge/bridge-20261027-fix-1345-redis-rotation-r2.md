# 🌉 Bridge Work Order — [P2] Fix: Redis cooldown attribution guard + invariant self-heal (fix for #1345)

Implements the fix for parent issue #1345 / bridge-20261027-redis-rotation-rule. Patch: infrastructure/mcp-control-plane/src/lib/redis_chain.ts. Attribution guard in the account-chain walk (cooldown stamps must name the walked account), assertCooldownInvariant with self-heal wired into quotaChainStatus. Revives the mis-stamped secondary slot (2/500,000 commands cooled for a month) without manual surgery. Mirror in supremeai-api mcp/src/lib/redis_chain.ts needs the identical patch.
