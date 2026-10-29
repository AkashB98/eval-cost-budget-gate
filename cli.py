"""CLI: report / compare / check / demo / serve.

Exit codes for ``check`` (the CI gate):
    0  verdict pass or warn (warn prints, but does not break the build)
    1  verdict fail — a budget rule was breached
    2  IO or data error (missing file, invalid JSON, bad run or budget)
"""
import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

from budget import Budget
from compare import compare_runs
from metrics import compute_metrics, load_run_file


def _load_all(args):
    baseline = load_run_file(args.baseline)
    candidate = load_run_file(args.candidate)
    budget = Budget.load_file(args.budget)
    return baseline, candidate, budget


def _print_metrics(m):
    print(json.dumps(m, indent=2, sort_keys=True))


def cmd_report(args):
    try:
        run = load_run_file(args.input)
    except Exception as exc:
        print(f"report: cannot load input: {exc}")
        return 2
    _print_metrics(compute_metrics(run))
    return 0


def _print_compare(result):
    b, c = result["baseline"], result["candidate"]
    print(f"{'metric':<16}{'baseline':>14}{'candidate':>14}{'delta':>14}")
    for label, key in (("total_cost", "total_cost"),
                       ("cost_per_case", "cost_per_case"),
                       ("total_tokens", "total_tokens"),
                       ("p95_latency_ms", "p95_latency_ms"),
                       ("mean_score", "mean_score")):
        print(f"{label:<16}{b[key]:>14}{c[key]:>14}"
              f"{round(c[key] - b[key], 6):>14}")
    print()
    for f in result["findings"]:
        print(f"[{f['severity'].upper():<4}] {f['message']}")
    print(f"verdict: {result['verdict'].upper()}")


def cmd_compare(args):
    try:
        baseline, candidate, budget = _load_all(args)
    except Exception as exc:
        print(f"compare: cannot load inputs: {exc}")
        return 2
    _print_compare(compare_runs(baseline, candidate, budget))
    return 0


def cmd_check(args):
    try:
        baseline, candidate, budget = _load_all(args)
    except Exception as exc:
        print(f"check: cannot load inputs: {exc}")
        return 2
    result = compare_runs(baseline, candidate, budget)
    _print_compare(result)
    if result["verdict"] == "fail":
        print("check: FAIL (budget breach)")
        return 1
    print(f"check: PASS (verdict {result['verdict']})")
    return 0


def cmd_demo(args):
    import demo
    return demo.main()


def cmd_serve(args):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, payload, code=200):
            body = json.dumps(payload, sort_keys=True).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self._send({"status": "ok"})
            else:
                self._send({"error": "not found"}, 404)

        def do_POST(self):
            if self.path != "/compare":
                self._send({"error": "not found"}, 404)
                return
            length = int(self.headers.get("Content-Length", 0))
            try:
                req = json.loads(self.rfile.read(length) or b"{}")
                from metrics import validate_run
                baseline = validate_run(req["baseline"])
                candidate = validate_run(req["candidate"])
                budget = Budget.from_dict(req["budget"])
                self._send(compare_runs(baseline, candidate, budget))
            except Exception as exc:
                self._send({"error": str(exc)}, 400)

    server = HTTPServer(("127.0.0.1", args.port), Handler)
    print(f"serving on 127.0.0.1:{args.port}")
    server.serve_forever()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="evalgate")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("report", help="metrics for a single run")
    p.add_argument("--input", required=True)
    p.set_defaults(fn=cmd_report)

    for name, fn in (("compare", cmd_compare), ("check", cmd_check)):
        p = sub.add_parser(name)
        p.add_argument("--baseline", required=True)
        p.add_argument("--candidate", required=True)
        p.add_argument("--budget", required=True)
        p.set_defaults(fn=fn)

    p = sub.add_parser("demo", help="run the end-to-end demo")
    p.set_defaults(fn=cmd_demo)

    p = sub.add_parser("serve", help="POST /compare, GET /health on 127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.set_defaults(fn=cmd_serve)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
