"""WO #4057 leg-4 — U6 message-consistency pins (GLM Agent 28, Job 486832).

চুক্তি (landed scout report PR #4058, docs/reports/scout-board-falseempty-cleanclaim-20261031.md):
যে রানে preflight board-plane-কে dark বলে (UNSEEN, not zero), সেই রান ACTION-
লাইন কখনো "System is clean and healthy" দাবি করতে পারে না — কোনো plane দ্বারা
সমর্থিত নয় এমন clean claim-ই U2 false assurance। এই pins দুটি source-scan
স্তরে (test_24/25 ও cadence guard-দের একই rigor) চুক্তি ধরে রাখে:

1. ACTION clean-claim অবশ্যই board_unavailable-gated হবে, এবং dark শাখায়
   সৎ শব্দচয়ন ("UNSEEN not zero; not certified clean (U2)") থাকবে।
2. revival block success-empty-কে fallback-ব্যর্থতা থেকে আলাদা করবে — tower
   SUCCESS note ("tower board fallback: N rows") দেখলে সৎ "ANSWERED EMPTY"
   নোট সারফেস করবে, পুরোনো "gh CLI not found" ভুল অ্যাট্রিবিউশন নয়।
"""

import re
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_LOOP = _ROOT / "scripts" / "agents" / "continuous_agent_loop.py"


class LoopMessageConsistency(unittest.TestCase):
    def _source(self) -> str:
        return _LOOP.read_text(encoding="utf-8")

    def test_01_action_clean_claim_gated_on_board_availability(self) -> None:
        src = self._source()
        gate_idx = src.find("if board_unavailable:")
        clean_idx = src.find("System is clean and healthy")
        honest_idx = src.find("UNSEEN not zero; not certified clean (U2)")
        self.assertGreater(gate_idx, -1, "ACTION clean-claim gate missing")
        self.assertGreater(clean_idx, gate_idx,
                           "'clean and healthy' must sit inside the available-branch, after the gate")
        self.assertGreater(honest_idx, -1, "dark-branch honesty wording missing")
        self.assertLess(honest_idx, clean_idx,
                        "dark-branch honesty ACTION must precede the available-branch clean claim")

    def test_02_success_empty_surfaces_tower_note_not_gh_misattribution(self) -> None:
        src = self._source()
        # Success-note discriminator: the colon-form "tower board fallback: N rows"
        # is unique to a SUCCESSFUL tower response (failure notes read
        # "failed/timed out/error/not found" and never carry the colon form).
        self.assertIsNotNone(
            re.search(r'tower board fallback: \\d\+ rows', src),
            "success-empty discriminator missing in the revival block",
        )
        self.assertIn("ANSWERED EMPTY", src,
                      "success-empty honest surface missing")
        self.assertIn("empty answer UNVERIFIED", src,
                      "ingest-lag caveat missing — a 0-row answer is not certified empty (R94 E5/R96)")

    def test_03_precedence_success_rows_before_success_empty(self) -> None:
        src = self._source()
        revived_idx = src.find("board query revived: ")
        empty_idx = src.find("board fallback answered empty: ")
        self.assertGreater(revived_idx, -1)
        self.assertGreater(empty_idx, -1)
        self.assertLess(revived_idx, empty_idx,
                        "revival-on-rows must be tested before the answered-empty branch")


if __name__ == "__main__":
    unittest.main()
