import unittest

import helpers  # noqa: F401
from budget import Budget


class TestBudget(unittest.TestCase):
    def test_single_field_ok(self):
        b = Budget(max_total_cost_usd=1.0)
        self.assertEqual(b.to_dict(), {"max_total_cost_usd": 1.0})

    def test_empty_budget_raises(self):
        with self.assertRaises(ValueError):
            Budget()

    def test_negative_raises(self):
        with self.assertRaises(ValueError):
            Budget(max_p95_latency_ms=-5)

    def test_negative_regression_raises(self):
        with self.assertRaises(ValueError):
            Budget(max_cost_regression_pct=-0.1)

    def test_zero_is_allowed(self):
        self.assertEqual(Budget(max_score_drop=0).max_score_drop, 0)

    def test_from_dict_unknown_field_raises(self):
        with self.assertRaises(ValueError):
            Budget.from_dict({"max_vibes": 3})

    def test_from_dict_non_object_raises(self):
        with self.assertRaises(ValueError):
            Budget.from_dict([1, 2])

    def test_load_invalid_json_raises(self):
        with self.assertRaises(ValueError):
            Budget.load("{oops")

    def test_sample_fixture_loads(self):
        from pathlib import Path
        b = Budget.load_file(str(Path(__file__).parent.parent
                                 / "fixtures" / "budget.sample.json"))
        self.assertEqual(b.max_total_cost_usd, 0.18)
        self.assertEqual(b.max_score_drop, 0.05)


if __name__ == "__main__":
    unittest.main()
