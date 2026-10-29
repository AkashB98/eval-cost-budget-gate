import unittest

import helpers  # noqa: F401
from pricing import PRICING, cost_for, model_names


class TestPricing(unittest.TestCase):
    def test_large_cost(self):
        self.assertAlmostEqual(cost_for("helios-large", 1000, 1000), 0.003 + 0.015)

    def test_medium_cost(self):
        self.assertAlmostEqual(cost_for("helios-medium", 2000, 500), 0.002 + 0.0025)

    def test_small_cost(self):
        self.assertAlmostEqual(cost_for("helios-small", 1000, 1000), 0.0005 + 0.0015)

    def test_zero_tokens(self):
        self.assertEqual(cost_for("helios-medium", 0, 0), 0.0)

    def test_unknown_model_raises(self):
        with self.assertRaises(ValueError):
            cost_for("helios-ultra", 100, 100)

    def test_negative_tokens_raise(self):
        with self.assertRaises(ValueError):
            cost_for("helios-medium", -1, 0)

    def test_model_names_sorted(self):
        self.assertEqual(model_names(), ["helios-large", "helios-medium", "helios-small"])

    def test_table_rates(self):
        self.assertEqual(PRICING["helios-medium"]["input_per_1k"], 0.001)
        self.assertEqual(PRICING["helios-large"]["output_per_1k"], 0.015)


if __name__ == "__main__":
    unittest.main()
