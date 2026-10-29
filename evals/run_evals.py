"""Golden evals for eval-cost-budget-gate. Deterministic; run 3x, md5 must match."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
FIX = ROOT / "fixtures"

from budget import Budget  # noqa: E402
from compare import compare_runs  # noqa: E402
from metrics import compute_metrics, load_run, load_run_file, percentile  # noqa: E402
from pricing import cost_for  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append({"eval": name, "pass": bool(ok), "detail": detail})


def main():
    baseline = load_run_file(str(FIX / "baseline.json"))
    cand_pass = load_run_file(str(FIX / "candidate_pass.json"))
    cand_fail = load_run_file(str(FIX / "candidate_fail.json"))
    budget = Budget.load_file(str(FIX / "budget.sample.json"))

    m = compute_metrics(baseline)
    check("E1_baseline_totals",
          m["cases"] == 24 and m["total_cost"] == 0.12
          and m["total_tokens"] == 65600 and m["cost_per_case"] == 0.005,
          f"cost={m['total_cost']} tokens={m['total_tokens']}")

    check("E2_baseline_latency_score",
          m["mean_latency_ms"] == 215.0 and m["p50_latency_ms"] == 210
          and m["p95_latency_ms"] == 320 and m["mean_score"] == 0.88,
          f"p95={m['p95_latency_ms']} score={m['mean_score']}")

    check("E3_suite_breakdown",
          m["per_suite"]["retrieval"]["total_cost"] == 0.028
          and m["per_suite"]["summarization"]["total_cost"] == 0.056
          and m["per_suite"]["support"]["total_cost"] == 0.036
          and abs(sum(v["total_cost"] for v in m["per_suite"].values())
                  - m["total_cost"]) < 1e-9)

    check("E4_model_breakdown_sums",
          abs(sum(v["total_cost"] for v in m["per_model"].values())
              - m["total_cost"]) < 1e-9
          and m["per_model"]["helios-medium"]["count"] == 24)

    check("E5_pricing_math",
          abs(cost_for("helios-large", 1000, 1000) - 0.018) < 1e-12
          and abs(cost_for("helios-medium", 2000, 500) - 0.0045) < 1e-12
          and abs(cost_for("helios-small", 1000, 1000) - 0.002) < 1e-12)

    check("E6_percentile_math",
          percentile([100 + i * 10 for i in range(24)], 95) == 320
          and percentile([10, 20, 30, 40], 50) == 20
          and percentile([3, 1, 2], 100) == 3)

    r_pass = compare_runs(baseline, cand_pass, budget)
    check("E7_pass_candidate_verdict",
          r_pass["verdict"] == "pass"
          and all(f["severity"] == "pass" for f in r_pass["findings"])
          and len(r_pass["findings"]) == 6)

    mp = compute_metrics(cand_pass)
    check("E8_pass_candidate_totals",
          mp["total_cost"] == 0.126 and mp["p95_latency_ms"] == 325
          and mp["mean_score"] == 0.87,
          f"cost={mp['total_cost']} p95={mp['p95_latency_ms']}")

    r_fail = compare_runs(baseline, cand_fail, budget)
    by_rule = {f["rule"]: f for f in r_fail["findings"]}
    check("E9_fail_candidate_verdict_and_deltas",
          r_fail["verdict"] == "fail"
          and all(f["severity"] == "fail" for f in r_fail["findings"])
          and by_rule["max_total_cost"]["delta_pct"] == 100.0
          and by_rule["max_p95_latency"]["delta_pct"] == 115.625
          and by_rule["max_score_drop"]["delta"] == -0.12,
          f"cost_delta_pct={by_rule['max_total_cost']['delta_pct']}")

    # Warn band: a ceiling budget whose 80% warn line the baseline crosses.
    warn_run = compare_runs(baseline, baseline, Budget(max_total_cost_usd=0.14))
    check("E10_warn_band", warn_run["verdict"] == "warn"
          and warn_run["findings"][0]["severity"] == "warn")

    ok_budget = True
    for bad in ({}, {"max_total_cost_usd": -1}):
        try:
            Budget.from_dict(bad)
            ok_budget = False
        except ValueError:
            pass
    check("E11_budget_validation", ok_budget)

    with tempfile.TemporaryDirectory() as td:
        def cli_check(candidate):
            return subprocess.run(
                [sys.executable, str(ROOT / "cli.py"), "check",
                 "--baseline", str(FIX / "baseline.json"),
                 "--candidate", str(FIX / candidate),
                 "--budget", str(FIX / "budget.sample.json")],
                capture_output=True, cwd=ROOT).returncode
        missing = subprocess.run(
            [sys.executable, str(ROOT / "cli.py"), "check",
             "--baseline", str(Path(td) / "nope.json"),
             "--candidate", str(FIX / "candidate_pass.json"),
             "--budget", str(FIX / "budget.sample.json")],
            capture_output=True, cwd=ROOT).returncode
        codes = (cli_check("candidate_pass.json"), cli_check("candidate_fail.json"),
                 missing)
        check("E12_cli_check_exit_codes", codes == (0, 1, 2), f"{codes}")

    check("E13_determinism",
          compare_runs(baseline, cand_fail, budget)
          == compare_runs(baseline, cand_fail, budget)
          and compute_metrics(baseline) == m)

    passed = sum(1 for r in RESULTS if r["pass"])
    out = {"passed": passed, "total": len(RESULTS), "results": RESULTS}
    (ROOT / "evals" / "eval_report.json").write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"evals: {passed}/{len(RESULTS)} passed")
    for r in RESULTS:
        print(("PASS " if r["pass"] else "FAIL ") + r["eval"] + f"  {r['detail']}")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
