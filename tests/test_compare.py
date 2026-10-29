import json
import unittest
from pathlib import Path

import helpers  # noqa: F401
from budget import Budget
from compare import compare_runs
from metrics import load_run, load_run_file

ROOT = Path(__file__).parent.parent
FIX = ROOT / "fixtures"


def _run(run_id, inp, out, lat, score, model="helios-medium"):
    return load_run(json.dumps({
        "run_id": run_id,
        "cases": [{"id": "a", "suite": "s", "model": model,
                   "input_tokens": inp, "output_tokens": out,
                   "latency_ms": lat, "score": score}]}))


BASE = None


def base():
    # cost 0.0045, p95 100, score 0.90
    return _run("b", 2000, 500, 100, 0.90)


class TestCompareFixtures(unittest.TestCase):
    def setUp(self):
        self.budget = Budget.load_file(str(FIX / "budget.sample.json"))
        self.baseline = load_run_file(str(FIX / "baseline.json"))

    def test_pass_candidate_all_pass(self):
        r = compare_runs(self.baseline,
                         load_run_file(str(FIX / "candidate_pass.json")), self.budget)
        self.assertEqual(r["verdict"], "pass")
        self.assertTrue(all(f["severity"] == "pass" for f in r["findings"]))
        self.assertEqual(len(r["findings"]), 6)

    def test_fail_candidate_all_fail(self):
        r = compare_runs(self.baseline,
                         load_run_file(str(FIX / "candidate_fail.json")), self.budget)
        self.assertEqual(r["verdict"], "fail")
        self.assertTrue(all(f["severity"] == "fail" for f in r["findings"]))

    def test_fail_deltas_pinned(self):
        r = compare_runs(self.baseline,
                         load_run_file(str(FIX / "candidate_fail.json")), self.budget)
        by_rule = {f["rule"]: f for f in r["findings"]}
        self.assertEqual(by_rule["max_total_cost"]["delta_pct"], 100.0)
        self.assertEqual(by_rule["max_p95_latency"]["delta_pct"], 115.625)
        self.assertEqual(by_rule["max_score_drop"]["delta"], -0.12)


class TestWarnBands(unittest.TestCase):
    def test_ceiling_warn_at_80pct(self):
        # limit 0.005 -> warn band starts at 0.004; candidate cost 0.0045
        budget = Budget(max_total_cost_usd=0.005)
        r = compare_runs(base(), base(), budget)
        self.assertEqual(r["findings"][0]["severity"], "warn")
        self.assertEqual(r["verdict"], "warn")

    def test_ceiling_pass_below_80pct(self):
        budget = Budget(max_total_cost_usd=0.01)
        r = compare_runs(base(), base(), budget)
        self.assertEqual(r["findings"][0]["severity"], "pass")

    def test_ceiling_fail_above_limit(self):
        budget = Budget(max_total_cost_usd=0.004)
        r = compare_runs(base(), base(), budget)
        self.assertEqual(r["findings"][0]["severity"], "fail")

    def test_regression_warn_above_half_limit(self):
        # candidate cost doubles baseline tokens: 0.009 vs 0.0045 = +100%
        cand = _run("c", 4000, 1000, 100, 0.90)
        budget = Budget(max_cost_regression_pct=150)  # warn > 75
        r = compare_runs(base(), cand, budget)
        self.assertEqual(r["findings"][0]["severity"], "warn")

    def test_regression_pass_at_or_below_half_limit(self):
        cand = _run("c", 4000, 1000, 100, 0.90)  # +100%
        budget = Budget(max_cost_regression_pct=200)  # warn > 100; 100 is not > 100
        r = compare_runs(base(), cand, budget)
        self.assertEqual(r["findings"][0]["severity"], "pass")

    def test_regression_fail_above_limit(self):
        cand = _run("c", 4000, 1000, 100, 0.90)
        budget = Budget(max_cost_regression_pct=50)
        r = compare_runs(base(), cand, budget)
        self.assertEqual(r["findings"][0]["severity"], "fail")

    def test_improvement_always_passes_regression(self):
        cand = _run("c", 1000, 250, 50, 0.95)  # cheaper, faster, better
        budget = Budget(max_cost_regression_pct=1, max_p95_regression_pct=1,
                        max_score_drop=0.01)
        r = compare_runs(base(), cand, budget)
        self.assertEqual(r["verdict"], "pass")

    def test_score_drop_warn_band(self):
        cand = _run("c", 2000, 500, 100, 0.86)  # drop 0.04
        budget = Budget(max_score_drop=0.05)  # warn > 0.025, fail > 0.05
        r = compare_runs(base(), cand, budget)
        self.assertEqual(r["findings"][0]["severity"], "warn")

    def test_score_drop_fail(self):
        cand = _run("c", 2000, 500, 100, 0.80)  # drop 0.10
        budget = Budget(max_score_drop=0.05)
        r = compare_runs(base(), cand, budget)
        self.assertEqual(r["findings"][0]["severity"], "fail")

    def test_only_configured_rules_emit_findings(self):
        budget = Budget(max_total_cost_usd=1.0)
        r = compare_runs(base(), base(), budget)
        self.assertEqual([f["rule"] for f in r["findings"]], ["max_total_cost"])

    def test_finding_shape(self):
        budget = Budget(max_total_cost_usd=1.0)
        f = compare_runs(base(), base(), budget)["findings"][0]
        self.assertEqual(set(f), {"rule", "severity", "baseline", "candidate",
                                  "delta", "delta_pct", "message"})


if __name__ == "__main__":
    unittest.main()
