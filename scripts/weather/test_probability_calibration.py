import math
import unittest
from probability_calibration import apply_beta, apply_isotonic, apply_platt, fit_beta, fit_isotonic, fit_platt

class ProbabilityCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{"prediction": ".1", "outcome": "0"}, {"prediction": ".2", "outcome": "0"}, {"prediction": ".8", "outcome": "1"}, {"prediction": ".9", "outcome": "1"}]

    def test_platt_is_finite_and_monotone(self):
        model = fit_platt(self.rows); low = apply_platt(.2, model); high = apply_platt(.8, model)
        self.assertTrue(math.isfinite(low) and math.isfinite(high))
        self.assertLess(low, high)
        self.assertGreaterEqual(model["a"], 0.0)

    def test_isotonic_is_monotone_and_fallbacks_empty(self):
        model = fit_isotonic(self.rows); self.assertLessEqual(apply_isotonic(.2, model), apply_isotonic(.8, model)); self.assertEqual(fit_isotonic([])["training_rows"], 0)

    def test_platt_is_bounded_on_separable_small_sample(self):
        model = fit_platt([{"prediction": ".99", "outcome": "1"}, {"prediction": ".01", "outcome": "0"}])
        self.assertTrue(-20 <= model["a"] <= 20 and -20 <= model["b"] <= 20)
        self.assertTrue(math.isfinite(apply_platt(.5, model)))

    def test_beta_is_finite_and_monotone_on_calibration_rows(self):
        model = fit_beta(self.rows); self.assertFalse(model["fallback"])
        values = [apply_beta(p, model) for p in (.1, .2, .8, .9)]
        self.assertTrue(all(math.isfinite(value) for value in values)); self.assertLessEqual(values[0], values[-1])
        grid = [apply_beta(i / 100, model) for i in range(1, 100)]
        self.assertTrue(all(left <= right for left, right in zip(grid, grid[1:])))

if __name__ == "__main__": unittest.main()
