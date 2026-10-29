import json
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

import helpers  # noqa: F401

ROOT = Path(__file__).parent.parent
FIX = ROOT / "fixtures"


def _run_cli(*argv):
    return subprocess.run([sys.executable, str(ROOT / "cli.py"), *argv],
                          capture_output=True, text=True, cwd=ROOT)


class TestCLI(unittest.TestCase):
    def test_report_exit_0_and_totals(self):
        out = _run_cli("report", "--input", str(FIX / "baseline.json"))
        self.assertEqual(out.returncode, 0)
        self.assertEqual(json.loads(out.stdout)["total_cost"], 0.12)

    def test_report_missing_file_exit_2(self):
        out = _run_cli("report", "--input", str(FIX / "nope.json"))
        self.assertEqual(out.returncode, 2)

    def test_compare_exit_0(self):
        out = _run_cli("compare", "--baseline", str(FIX / "baseline.json"),
                       "--candidate", str(FIX / "candidate_pass.json"),
                       "--budget", str(FIX / "budget.sample.json"))
        self.assertEqual(out.returncode, 0)
        self.assertIn("verdict: PASS", out.stdout)

    def test_check_pass_exit_0(self):
        out = _run_cli("check", "--baseline", str(FIX / "baseline.json"),
                       "--candidate", str(FIX / "candidate_pass.json"),
                       "--budget", str(FIX / "budget.sample.json"))
        self.assertEqual(out.returncode, 0)

    def test_check_fail_exit_1(self):
        out = _run_cli("check", "--baseline", str(FIX / "baseline.json"),
                       "--candidate", str(FIX / "candidate_fail.json"),
                       "--budget", str(FIX / "budget.sample.json"))
        self.assertEqual(out.returncode, 1)

    def test_check_bad_data_exit_2(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad.json"
            bad.write_text('{"run_id": "x", "cases": []}')
            out = _run_cli("check", "--baseline", str(bad),
                           "--candidate", str(FIX / "candidate_pass.json"),
                           "--budget", str(FIX / "budget.sample.json"))
            self.assertEqual(out.returncode, 2)

    def test_check_missing_budget_exit_2(self):
        out = _run_cli("check", "--baseline", str(FIX / "baseline.json"),
                       "--candidate", str(FIX / "candidate_pass.json"),
                       "--budget", str(FIX / "nope.json"))
        self.assertEqual(out.returncode, 2)

    def test_serve_round_trip_matches_local(self):
        from budget import Budget
        from compare import compare_runs
        from metrics import load_run_file
        local = compare_runs(load_run_file(str(FIX / "baseline.json")),
                             load_run_file(str(FIX / "candidate_fail.json")),
                             Budget.load_file(str(FIX / "budget.sample.json")))
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "cli.py"), "serve", "--port", "8794"],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(50):
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8794/health",
                                                timeout=1) as r:
                        self.assertEqual(json.load(r)["status"], "ok")
                    break
                except Exception:
                    time.sleep(0.1)
            payload = {
                "baseline": json.loads((FIX / "baseline.json").read_text()),
                "candidate": json.loads((FIX / "candidate_fail.json").read_text()),
                "budget": json.loads((FIX / "budget.sample.json").read_text()),
            }
            req = urllib.request.Request(
                "http://127.0.0.1:8794/compare", data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=2) as r:
                served = json.load(r)
            self.assertEqual(served, json.loads(json.dumps(local, sort_keys=True)))
        finally:
            proc.terminate()


class TestNoNetwork(unittest.TestCase):
    def test_core_logic_runs_with_sockets_blocked(self):
        import socket

        original = socket.socket

        class Blocked(socket.socket):
            def connect(self, *a, **k):
                raise AssertionError("network access attempted")

        socket.socket = Blocked
        try:
            from budget import Budget
            from compare import compare_runs
            from metrics import load_run_file
            r = compare_runs(load_run_file(str(FIX / "baseline.json")),
                             load_run_file(str(FIX / "candidate_pass.json")),
                             Budget.load_file(str(FIX / "budget.sample.json")))
            self.assertEqual(r["verdict"], "pass")
        finally:
            socket.socket = original


if __name__ == "__main__":
    unittest.main()
