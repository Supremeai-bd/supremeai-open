"""Unit test for verdict_plane_gap_probe."""
import unittest
from scripts.ci.verdict_plane_gap_probe import _self_test

class TestVerdictPlaneGapProbe(unittest.TestCase):
    def test_self_test(self):
        self.assertEqual(_self_test(), 0)

if __name__ == "__main__":
    unittest.main()
