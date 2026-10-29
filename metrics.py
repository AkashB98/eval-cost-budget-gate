"""Run loading and metric computation for eval runs.

An eval run is JSON:

    {"run_id": "baseline-001", "model": "helios-medium",
     "cases": [{"id": "r-01", "suite": "retrieval", "model": "helios-medium",
                "input_tokens": 1500, "output_tokens": 400,
                "latency_ms": 100, "score": 0.85}, ...]}

A case's ``model`` falls back to the run-level ``model`` when omitted.
Monetary and mean values are rounded to 6 decimal places in the output
so reports, evals, and the HTTP API agree byte-for-byte.
"""
import json

from pricing import cost_for

REQUIRED_CASE_FIELDS = ("id", "suite", "input_tokens", "output_tokens",
                        "latency_ms", "score")


def _r6(value):
    return round(float(value), 6)


def percentile(values, pct):
    """Nearest-rank percentile.

    Sort the values ascending, take rank = ceil(pct/100 * N) (1-indexed,
    clamped to [1, N]), and return the value at that rank. So the p95 of
    24 values is the 23rd smallest (ceil(0.95 * 24) = ceil(22.8) = 23).
    """
    if not values:
        raise ValueError("percentile of an empty list")
    if not 0 < pct <= 100:
        raise ValueError("pct must be in (0, 100]")
    ordered = sorted(values)
    # Exact rank via Fraction: float math.ceil(7 / 100.0 * 100) is 8, not 7
    # (7.000000000000001), which would silently pick the wrong element.
    import math
    from fractions import Fraction
    rank = math.ceil(Fraction(str(pct)) * len(ordered) / 100)
    rank = max(1, min(rank, len(ordered)))
    return ordered[rank - 1]


def load_run(text):
    """Parse and validate an eval run from JSON text. Raises ValueError."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    return validate_run(data)


def load_run_file(path):
    with open(path) as fh:
        return load_run(fh.read())


def validate_run(data):
    if not isinstance(data, dict):
        raise ValueError("run must be a JSON object")
    if "run_id" not in data:
        raise ValueError("run is missing 'run_id'")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("run 'cases' must be a non-empty list")
    default_model = data.get("model")
    for i, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"case {i} must be an object")
        for field in REQUIRED_CASE_FIELDS:
            if field not in case:
                raise ValueError(f"case {i} is missing field {field!r}")
        model = case.get("model", default_model)
        if not model:
            raise ValueError(f"case {i} has no model and the run sets no default")
        case = dict(case, model=model)
        cases[i] = case
        for field in ("input_tokens", "output_tokens"):
            if not isinstance(case[field], (int, float)) or case[field] < 0:
                raise ValueError(f"case {i} field {field!r} must be a non-negative number")
        if not isinstance(case["latency_ms"], (int, float)) or case["latency_ms"] < 0:
            raise ValueError(f"case {i} field 'latency_ms' must be a non-negative number")
        if not isinstance(case["score"], (int, float)):
            raise ValueError(f"case {i} field 'score' must be a number")
        # Price it now so an unknown model fails at load, not mid-report.
        cost_for(case["model"], case["input_tokens"], case["output_tokens"])
    return data


def _breakdown(cases, key, costs):
    groups = {}
    for case, cost in zip(cases, costs):
        groups.setdefault(case[key], []).append((case, cost))
    out = {}
    for name in sorted(groups):
        members = groups[name]
        lat = [c["latency_ms"] for c, _ in members]
        total = sum(co for _, co in members)
        out[name] = {
            "count": len(members),
            "total_cost": _r6(total),
            "total_tokens": sum(c["input_tokens"] + c["output_tokens"]
                                for c, _ in members),
            "cost_per_case": _r6(total / len(members)),
            "mean_latency_ms": _r6(sum(lat) / len(lat)),
            "p95_latency_ms": percentile(lat, 95),
            "mean_score": _r6(sum(c["score"] for c, _ in members) / len(members)),
        }
    return out


def compute_metrics(run):
    """Full metric summary for one validated run."""
    cases = run["cases"]
    costs = [cost_for(c["model"], c["input_tokens"], c["output_tokens"])
             for c in cases]
    total_cost = sum(costs)
    lat = [c["latency_ms"] for c in cases]
    n = len(cases)
    return {
        "run_id": run["run_id"],
        "cases": n,
        "total_cost": _r6(total_cost),
        "total_tokens": sum(c["input_tokens"] + c["output_tokens"] for c in cases),
        "input_tokens": sum(c["input_tokens"] for c in cases),
        "output_tokens": sum(c["output_tokens"] for c in cases),
        "cost_per_case": _r6(total_cost / n),
        "mean_latency_ms": _r6(sum(lat) / n),
        "p50_latency_ms": percentile(lat, 50),
        "p95_latency_ms": percentile(lat, 95),
        "mean_score": _r6(sum(c["score"] for c in cases) / n),
        "per_suite": _breakdown(cases, "suite", costs),
        "per_model": _breakdown(cases, "model", costs),
    }
