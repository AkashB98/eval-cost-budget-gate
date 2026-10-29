"""Baseline vs candidate comparison against a budget.

One finding per configured budget rule:

    {rule, severity, baseline, candidate, delta, delta_pct, message}

``severity`` is "pass", "warn", or "fail"; the verdict is the worst
severity across findings (fail > warn > pass).

Warn bands (so a run heading toward the limit is visible before it
breaches):
  * Absolute ceilings (total cost, p95 latency, cost per case): warn
    when the candidate reaches 80% of the limit, fail above the limit.
  * Regression limits (cost %, p95 %): warn when the regression exceeds
    50% of the allowed limit, fail above the limit.
  * Score drop: warn when the drop exceeds 50% of the allowed drop,
    fail above it.
"""
from metrics import compute_metrics

SEVERITY_RANK = {"pass": 0, "warn": 1, "fail": 2}


def _pct(delta, base):
    if base == 0:
        return 0.0 if delta == 0 else float("inf")
    return round(delta / base * 100.0, 4)


def _finding(rule, severity, baseline, candidate, message):
    delta = round(candidate - baseline, 6)
    return {
        "rule": rule,
        "severity": severity,
        "baseline": baseline,
        "candidate": candidate,
        "delta": delta,
        "delta_pct": _pct(delta, baseline),
        "message": message,
    }


def _ceiling(rule, baseline, candidate, limit, unit):
    if candidate > limit:
        severity = "fail"
    elif candidate >= 0.8 * limit:
        severity = "warn"
    else:
        severity = "pass"
    message = f"{rule}: candidate {candidate}{unit} vs limit {limit}{unit} ({severity})"
    return _finding(rule, severity, baseline, candidate, message)


def _regression(rule, baseline, candidate, limit_pct):
    delta_pct = _pct(candidate - baseline, baseline)
    if delta_pct > limit_pct:
        severity = "fail"
    elif delta_pct > 0.5 * limit_pct:
        severity = "warn"
    else:
        severity = "pass"
    message = (f"{rule}: regression {delta_pct}% vs allowed {limit_pct}% "
               f"({severity})")
    return _finding(rule, severity, baseline, candidate, message)


def compare_runs(baseline_run, candidate_run, budget):
    """Return {verdict, baseline_metrics, candidate_metrics, findings}."""
    base = compute_metrics(baseline_run)
    cand = compute_metrics(candidate_run)
    findings = []

    if budget.max_total_cost_usd is not None:
        findings.append(_ceiling(
            "max_total_cost", base["total_cost"], cand["total_cost"],
            budget.max_total_cost_usd, " USD"))
    if budget.max_cost_regression_pct is not None:
        findings.append(_regression(
            "max_cost_regression", base["total_cost"], cand["total_cost"],
            budget.max_cost_regression_pct))
    if budget.max_p95_latency_ms is not None:
        findings.append(_ceiling(
            "max_p95_latency", base["p95_latency_ms"], cand["p95_latency_ms"],
            budget.max_p95_latency_ms, " ms"))
    if budget.max_p95_regression_pct is not None:
        findings.append(_regression(
            "max_p95_regression", base["p95_latency_ms"], cand["p95_latency_ms"],
            budget.max_p95_regression_pct))
    if budget.max_cost_per_case_usd is not None:
        findings.append(_ceiling(
            "max_cost_per_case", base["cost_per_case"], cand["cost_per_case"],
            budget.max_cost_per_case_usd, " USD"))
    if budget.max_score_drop is not None:
        drop = round(base["mean_score"] - cand["mean_score"], 6)
        if drop > budget.max_score_drop:
            severity = "fail"
        elif drop > 0.5 * budget.max_score_drop:
            severity = "warn"
        else:
            severity = "pass"
        finding = _finding(
            "max_score_drop", severity, base["mean_score"], cand["mean_score"],
            f"max_score_drop: drop {drop} vs allowed {budget.max_score_drop} "
            f"({severity})")
        findings.append(finding)

    verdict = "pass"
    for finding in findings:
        if SEVERITY_RANK[finding["severity"]] > SEVERITY_RANK[verdict]:
            verdict = finding["severity"]
    return {
        "verdict": verdict,
        "baseline": base,
        "candidate": cand,
        "findings": findings,
    }
