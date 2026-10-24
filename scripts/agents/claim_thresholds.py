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


def claim_age_minutes(claim_epoch: float, now_epoch: float | None = None) -> float:
    """Claim-এর বয়স (মিনিটে) — release-path-গুলো এই হেল্পার দিয়েই মাপবে।"""
    import time

    now = now_epoch if now_epoch is not None else time.time()
    return (now - claim_epoch) / 60.0
