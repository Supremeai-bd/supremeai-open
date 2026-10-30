"""Claim-lease thresholds — single source of truth (#57).

বাংলা (#57): agent-fleet-এর release/orphan threshold গুলোর এক-সত্য-উৎস।
Evidence (#57): fleet-কম্পোনেন্টগুলো claim-staleness ভিন্ন উৎস থেকে মাপত
(প্রথম claim-comment vs updatedAt) এবং release↔re-claim প্রতি ~৬০s-এ
flip-flop war-এ জড়াত। এখন সংখ্যাগুলোর মালিক এই একটি মডিউল — যেকোনো
release-path এখান থেকে import করবে, হার্ডকোড নয়।

Related: #57 (claim-war follow-up), #4206 (branch-state machine),
#3042 (bot-mode claim recovery).
"""

# Crash-recovery release: এর চেয়ে পুরোনো claim (heartbeat ছাড়া) = orphan
# → release করা যাবে। (আগে continuous_agent_loop.py-তে হার্ডকোড ছিল।)
ORPHAN_RELEASE_MINUTES = 30

# Idempotency guard (#57 remedy): এর চেয়ে টাটকা claim কোনো sweep কখনো
# release করবে না — সদ্য-claimed issue-কে racing releaser-দের থেকে রক্ষা।
# War-evidence-এ release হচ্ছিল claim-এর ~১৬s-এর মধ্যেই।
MIN_CLAIM_AGE_BEFORE_RELEASE_MINUTES = 5

# Receipt-coverage TTL (saturation livelock-এর রুট-কজ ফিক্স; GLM Agent 18,
# Job 486801; প্রমাণ: #3634 saturation #2 + #3600 strand census): এর চেয়ে
# পুরোনো খোলা bridge-WO receipt আর dispatch-demote করতে পারবে না — এমন
# receipt-এর coverage "in-flight" নয়, "stranded" (event-driven auto-landing
# পুরোনো PR আর কখনো revisit করে না)। প্রমাণভিত্তিক সীমা: in-flight receipt
# মিনিটেই land হয় (#3578: 44s, #3602: 1m24s, #3604: 2m01s, #3599: ~3min),
# আর stranded কভারার ঘণ্টার পর ঘণ্টা খোলা থাকে (#3600: oldest PR 5.7h,
# 20/27 never-touched; #2756 ৪-তম সাইকেলেও stranded)। ১২০ মিনিট = সবচেয়ে
# ধীর পর্যবেক্ষিত সৎ ল্যান্ডিংয়ের ~৪০ গুণ, সবচেয়ে আগের স্ট্র্যান্ড-প্রমাণের
# অর্ধেক — দুই দিকেই বড় মার্জিন। এক-সত্য-উৎস: লুপ এখান থেকে import করবে,
# নিজে হার্ডকোড নয় (#57-এর হুবহু ডুয়াল-SSOT শ্রেণি)।
RECEIPT_COVERAGE_TTL_MINUTES = 120


def claim_age_minutes(claim_epoch: float, now_epoch: float | None = None) -> float:
    """Claim-এর বয়স (মিনিটে) — release-path-গুলো এই হেল্পার দিয়েই মাপবে।"""
    import time

    now = now_epoch if now_epoch is not None else time.time()
    return (now - claim_epoch) / 60.0
