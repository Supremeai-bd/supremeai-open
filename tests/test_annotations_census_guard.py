"""Unit test for annotations_census_guard."""
import unittest
from scripts.ci.annotations_census_guard import _self_test

class TestAnnotationsCensusGuard(unittest.TestCase):
    def test_self_test(self):
        self.assertEqual(_self_test(), 0)

if __name__ == "__main__":
    unittest.main()
