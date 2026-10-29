#!/usr/bin/env python3
"""Pin: both dispatch surfaces carry the STALE-CLAIM advisory (#2100 arc).

Live 2026-10-28: the tower's queue labels lagged live claims on three rows
(#2111, #2123, #2102) - agents picking from the board saw `status:unclaimed`
on rows claimed >=19 minutes earlier, then burned their cycle on atomic-claim
rejection (work_claim GRANT_NEW fails on the second claimer). The loop cannot
fix wrong label DATA (b3dfbbe already excludes bridge-plane states; this is a
different failure: the label value itself is stale), so the loop's honest
mitigation is the advisory carried to the agent at dispatch time, in the two
places the U3 precedent already uses: the envelope's specialist_prompt and the
dispatch print block.

Comment-immune string-presence pin (wiring-pin precedent test_27 /
test_pick_excludes_bridge_states.py AST pin family): reads the loop module's
source and asserts the guard exists exactly twice with its operative tokens.
Dual-mode: runs under both `python3 -m unittest` and `pytest`.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
LOOP_PATH = _ROOT / "scripts" / "agents" / "continuous_agent_loop.py"
LOOP_SRC = LOOP_PATH.read_text(encoding="utf-8")

GUARD_KEY = "STALE-CLAIM GUARD"
# বাংলা: পিন লাইভ-রেজিস্ট্রি অনুসরণ করবে (#2775)। 2026-10-30 04:08Z লাইভ-প্রোব:
# `bridge.read_feedback` (ডটেড) -> -32602 Tool not found (মৃত নাম);
# `bridge_read_feedback` (আন্ডারস্কোর) -> args-ভ্যালিডেশন চলে (টুল জীবিত) —
# #2640 A-1/A-3-এর হাইব্রিড-রেজিস্ট্রি মানচিত্রের সাথে সামঞ্জস্যপূর্ণ। রিগ্রেশন:
# R78 guard-টেক্সট সঠিকভাবে জীবিত নামে সরেছিল, কিন্তু পিন মৃত ডটেড নামেই ছিল —
# landed suite main-এ 1/35 RED হয়ে গিয়েছিল। টুল-নাম ভবিষ্যতে আবার বদলালে
# guard-টেক্সট ও এই পিন একই স্লাইসে একসাথে সরবে (SSOT-first ডকট্রিন)।
REQUIRED_TOKENS = (
    "bridge_read_feedback",
    "latestClaim",
    "work_claim",
    "never retry the same row",
)


class TestStaleClaimGuardPin(unittest.TestCase):
    def _string_literal_count(self) -> int:
        """AST count of string CONSTANTS starting with the guard key -
        comment-immune (Bangla contract comments may mention the guard by name)."""
        tree = ast.parse(LOOP_SRC)
        return sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.startswith(GUARD_KEY)
        )

    def test_guard_present_exactly_twice(self):
        """Envelope specialist_prompt + dispatch print - the U3 two-surface pattern."""
        count = self._string_literal_count()
        self.assertEqual(
            count,
            2,
            f"{GUARD_KEY} string literals must be exactly 2 (envelope + dispatch); found {count}",
        )

    def test_guard_carries_operative_tokens(self):
        """The advisory must name the verify step and the rejection protocol."""
        for token in REQUIRED_TOKENS:
            self.assertIn(token, LOOP_SRC, f"guard token missing: {token}")

    def test_u3_precedent_untouched(self):
        """The new guard must not displace the existing U3 advisory."""
        self.assertIn("STALE-INCIDENT GUARD", LOOP_SRC)


if __name__ == "__main__":
    unittest.main()
