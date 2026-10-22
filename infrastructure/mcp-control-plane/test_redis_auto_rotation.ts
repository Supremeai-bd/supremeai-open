import assert from "node:assert/strict";
import {
  buildAccountChain,
  activeAccountChain,
  getActiveRedisAccount,
  markAccountQuotaExhausted,
  isAccountQuotaExhausted,
  quotaChainStatus,
  nextQuotaResetEpochMs,
  responseIndicatesQuotaExhaustion,
} from "./src/lib/redis_chain.js";

// Setup environment with 3 accounts
process.env.UPSTASH_REDIS_REST_URL = "https://primary.upstash.io";
process.env.UPSTASH_REDIS_REST_TOKEN = "t1";
process.env.UPSTASH_REDIS_SECONDARY_REST_URL = "https://secondary.upstash.io";
process.env.UPSTASH_REDIS_SECONDARY_REST_TOKEN = "t2";
process.env.UPSTASH_REDIS_TERTIARY_REST_URL = "https://tertiary.upstash.io";
process.env.UPSTASH_REDIS_TERTIARY_REST_TOKEN = "t3";
delete process.env.UPSTASH_REDIS_QUATERNARY_REST_URL;
delete process.env.UPSTASH_REDIS_QUATERNARY_REST_TOKEN;
delete process.env.UPSTASH_REDIS_QUINARY_REST_URL;
delete process.env.UPSTASH_REDIS_QUINARY_REST_TOKEN;
delete process.env.REDIS_URL;

// 1. Initial State: primary is active
assert.equal(getActiveRedisAccount().label, "primary");
assert.equal(activeAccountChain().length, 3);
assert.equal(activeAccountChain()[0].label, "primary");

// 2. Quota exhaustion marker detection
assert.ok(responseIndicatesQuotaExhaustion(400, "ERR max requests limit exceeded. Limit: 500000, Usage: 500002"));
assert.ok(responseIndicatesQuotaExhaustion(400, "command failed: max requests limit"));
assert.ok(responseIndicatesQuotaExhaustion(429, "Too Many Requests"));
assert.ok(responseIndicatesQuotaExhaustion(400, "Daily request limit exceeded"));
assert.ok(responseIndicatesQuotaExhaustion(400, "Monthly request limit exceeded"));
assert.ok(responseIndicatesQuotaExhaustion(402, "Payment Required"));
assert.ok(!responseIndicatesQuotaExhaustion(200, "PONG"));

// 3. Mark primary exhausted -> Auto-rotate to secondary
markAccountQuotaExhausted("primary");
assert.ok(isAccountQuotaExhausted("primary"));
assert.equal(getActiveRedisAccount().label, "secondary", "Active primary must auto-rotate to secondary");
assert.equal(activeAccountChain()[0].label, "secondary");
assert.equal(activeAccountChain().length, 2);

// 4. Quota chain status reflection
const status = quotaChainStatus();
const primaryStatus = status.find((s) => s.label === "primary");
const secondaryStatus = status.find((s) => s.label === "secondary");
assert.ok(primaryStatus?.cooldownUntil !== null, "Primary must have cooldownUntil timestamp");
assert.equal(primaryStatus?.isActivePrimary, false);
assert.equal(secondaryStatus?.isActivePrimary, true, "Secondary must be active primary");

// 5. If secondary also exhausts -> Auto-rotate to tertiary
markAccountQuotaExhausted("secondary");
assert.equal(getActiveRedisAccount().label, "tertiary", "Active primary must auto-rotate to tertiary");
assert.equal(activeAccountChain()[0].label, "tertiary");
assert.equal(activeAccountChain().length, 1);

// 6. Reset epoch verification: 1st of next month
const resetMs = nextQuotaResetEpochMs();
const resetDate = new Date(resetMs);
assert.equal(resetDate.getUTCDate(), 1, "Reset day must be 1st of month");
assert.equal(resetDate.getUTCHours(), 0, "Reset hour must be 00:00 UTC");

// 7. Auto-recovery probe verification
const { clearAccountCooldown, probeCooldownRecovery } = await import("./src/lib/redis_chain.js");
assert.equal(isAccountQuotaExhausted("primary"), true);
const recovered = await probeCooldownRecovery(async (acc) => acc.label === "primary");
assert.deepEqual(recovered, ["primary"]);
assert.equal(isAccountQuotaExhausted("primary"), false, "Primary should recover after successful probe");
assert.equal(getActiveRedisAccount().label, "primary", "Primary should resume active primary after recovery");

console.log("✅ All Redis auto-rotation contract tests PASSED!");
