import json
import unittest
from pathlib import Path

import helpers  # noqa: F401
from metrics import compute_metrics, load_run, load_run_file, percentile

ROOT = Path(__file__).parent.parent
FIX = ROOT / "fixtures"


def _run(cases, run_id="t", model=None):
    data = {"run_id": run_id, "cases": cases}
    if model:
        data["model"] = model
    return load_run(json.dumps(data))


def _case(cid="a", suite="s", model="helios-medium", inp=1000, out=500,
          lat=100, score=0.9):
    return {"id": cid, "suite": suite, "model": model, "input_tokens": inp,
            "output_tokens": out, "latency_ms": lat, "score": score}


class TestPercentile(unittest.TestCase):
    def test_nearest_rank_p95_of_24(self):
        values = [100 + i * 10 for i in range(24)]
        self.assertEqual(percentile(values, 95), 320)  # ceil(.95*24)=23rd

    def test_p50(self):
        self.assertEqual(percentile([10, 20, 30, 40], 50), 20)

    def test_p100_is_max(self):
        self.assertEqual(percentile([3, 1, 2], 100), 3)

    def test_single_value(self):
        self.assertEqual(percentile([7], 95), 7)

    def test_unsorted_input(self):
        self.assertEqual(percentile([40, 10, 30, 20], 50), 20)

    def test_exact_rank_no_float_drift(self):
        # Regression: float ceil(7/100.0*100) == 8 (7.000000000000001);
        # the exact 7th smallest of 0..99 is 6.
        self.assertEqual(percentile(list(range(100)), 7), 6)
        self.assertEqual(percentile(list(range(200)), 7), 13)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            percentile([], 50)

    def test_bad_pct_raises(self):
        with self.assertRaises(ValueError):
            percentile([1], 0)
        with self.assertRaises(ValueError):
            percentile([1], 101)


class TestMetrics(unittest.TestCase):
    def test_baseline_fixture_totals(self):
        m = compute_metrics(load_run_file(str(FIX / "baseline.json")))
        self.assertEqual(m["cases"], 24)
        self.assertEqual(m["total_cost"], 0.12)
        self.assertEqual(m["total_tokens"], 65600)
        self.assertEqual(m["cost_per_case"], 0.005)
        self.assertEqual(m["mean_latency_ms"], 215.0)
        self.assertEqual(m["p50_latency_ms"], 210)
        self.assertEqual(m["p95_latency_ms"], 320)
        self.assertEqual(m["mean_score"], 0.88)

    def test_breakdowns_sum_to_totals(self):
        m = compute_metrics(load_run_file(str(FIX / "baseline.json")))
        self.assertAlmostEqual(
            sum(v["total_cost"] for v in m["per_suite"].values()), m["total_cost"])
        self.assertAlmostEqual(
            sum(v["total_cost"] for v in m["per_model"].values()), m["total_cost"])
        self.assertEqual(sum(v["count"] for v in m["per_suite"].values()), 24)

    def test_per_suite_values(self):
        m = compute_metrics(load_run_file(str(FIX / "baseline.json")))
        self.assertEqual(m["per_suite"]["retrieval"]["total_cost"], 0.028)
        self.assertEqual(m["per_suite"]["summarization"]["total_cost"], 0.056)
        self.assertEqual(m["per_suite"]["support"]["total_cost"], 0.036)

    def test_default_model_fallback(self):
        case = _case()
        del case["model"]
        run = _run([case], model="helios-small")
        m = compute_metrics(run)
        self.assertEqual(list(m["per_model"]), ["helios-small"])
        self.assertAlmostEqual(m["total_cost"], 0.0005 + 0.00075)

    def test_mixed_models_breakdown(self):
        run = _run([_case("a", model="helios-small"), _case("b", model="helios-large")])
        m = compute_metrics(run)
        self.assertEqual(set(m["per_model"]), {"helios-small", "helios-large"})

    def test_empty_cases_raise(self):
        with self.assertRaises(ValueError):
            _run([])

    def test_missing_field_raises(self):
        case = _case()
        del case["score"]
        with self.assertRaises(ValueError):
            _run([case])

    def test_unknown_model_raises_at_load(self):
        with self.assertRaises(ValueError):
            _run([_case(model="nope-1")])

    def test_invalid_json_raises(self):
        with self.assertRaises(ValueError):
            load_run("{not json")

    def test_determinism(self):
        run = load_run_file(str(FIX / "baseline.json"))
        self.assertEqual(compute_metrics(run), compute_metrics(run))


if __name__ == "__main__":
    unittest.main()
