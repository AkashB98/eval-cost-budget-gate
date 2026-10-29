"""End-to-end demo: report -> compare pass -> check fail -> serve."""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
FIX = ROOT / "fixtures"

from budget import Budget  # noqa: E402
from compare import compare_runs  # noqa: E402
from metrics import compute_metrics, load_run_file  # noqa: E402


def _check_cli(*argv):
    return subprocess.run([sys.executable, str(ROOT / "cli.py"), *argv],
                          capture_output=True, text=True, cwd=ROOT)


def main():
    baseline = load_run_file(str(FIX / "baseline.json"))
    cand_pass = load_run_file(str(FIX / "candidate_pass.json"))
    cand_fail = load_run_file(str(FIX / "candidate_fail.json"))
    budget = Budget.load_file(str(FIX / "budget.sample.json"))

    m = compute_metrics(baseline)
    assert m["total_cost"] == 0.12 and m["p95_latency_ms"] == 320, m
    assert m["mean_score"] == 0.88 and m["cases"] == 24, m
    print(f"1. baseline report: 24 cases, total cost ${m['total_cost']:.2f}, "
          f"p95 {m['p95_latency_ms']} ms, mean score {m['mean_score']}")

    result_pass = compare_runs(baseline, cand_pass, budget)
    assert result_pass["verdict"] == "pass", result_pass["findings"]
    ok = _check_cli("check", "--baseline", str(FIX / "baseline.json"),
                    "--candidate", str(FIX / "candidate_pass.json"),
                    "--budget", str(FIX / "budget.sample.json"))
    assert ok.returncode == 0, ok.stdout + ok.stderr
    print("2. pass candidate: verdict PASS, CLI check exits 0")

    result_fail = compare_runs(baseline, cand_fail, budget)
    assert result_fail["verdict"] == "fail", result_fail["findings"]
    bad = _check_cli("check", "--baseline", str(FIX / "baseline.json"),
                     "--candidate", str(FIX / "candidate_fail.json"),
                     "--budget", str(FIX / "budget.sample.json"))
    assert bad.returncode == 1, bad.stdout + bad.stderr
    print("3. fail candidate: verdict FAIL (cost +100%, p95 +115.6%, "
          "score -0.12), CLI check exits 1")

    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "cli.py"), "serve", "--port", "8793"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                with urllib.request.urlopen("http://127.0.0.1:8793/health",
                                            timeout=1) as r:
                    assert json.load(r)["status"] == "ok"
                break
            except Exception:
                time.sleep(0.1)
        payload = {
            "baseline": json.loads((FIX / "baseline.json").read_text()),
            "candidate": json.loads((FIX / "candidate_fail.json").read_text()),
            "budget": json.loads((FIX / "budget.sample.json").read_text()),
        }
        req = urllib.request.Request(
            "http://127.0.0.1:8793/compare",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=2) as r:
            served = json.load(r)
        assert served == json.loads(json.dumps(result_fail, sort_keys=True)), \
            "served compare must match local compare exactly"
        print("4. serve round-trip: POST /compare matches local compare exactly")
    finally:
        proc.terminate()
    print("demo: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
