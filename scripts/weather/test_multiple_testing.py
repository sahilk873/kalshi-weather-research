import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multiple_testing import reality_check


class MultipleTestingTests(unittest.TestCase):
    def test_block_max_statistic_is_reproducible(self):
        strategies = {"a": [0.02, -0.01, 0.03, 0.01], "b": [0.0, 0.01, -0.02, 0.0]}
        first = reality_check(strategies, simulations=100, block_size=2, seed=4)
        second = reality_check(strategies, simulations=100, block_size=2, seed=4)
        self.assertEqual(first, second)
        self.assertEqual(first["best_strategy"], "a")
        self.assertGreaterEqual(first["max_statistic_p_value"], 0.0)
        self.assertLessEqual(first["max_statistic_p_value"], 1.0)

    def test_mismatched_lengths_fail_closed(self):
        with self.assertRaises(ValueError):
            reality_check({"a": [0.1], "b": [0.1, 0.2]})


if __name__ == "__main__":
    unittest.main()
