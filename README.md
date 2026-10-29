# eval-cost-budget-gate

**A CI gate that fails a change when an eval suite's token cost or latency regresses beyond a set budget — so a "small prompt tweak" can't quietly double the AI bill.**

Every team shipping LLM features runs **evals** (a fixed suite of test cases scored against expected behavior). What most suites don't watch is what each run *costs*: swap in a bigger model, lengthen a prompt, add a retry — quality scores hold, and the spend and **latency** (how long each call takes) creep up until finance or a timeout notices. This project is the missing gate: price every eval case from a bundled table, roll a run up into cost / latency / score metrics, compare a candidate run against a baseline under an explicit budget, and exit non-zero in **CI** (continuous integration — the automated checks that run on every change) when the candidate breaches. It composes two stories from this portfolio: the cost tracking of `llm-cost-sidecar` and the eval-health view of `agent-eval-dashboard`, pointed at the merge decision.

> **Synthetic data only.** Every run, model, and price in this project is fictional (the **Helios Home** smart-home store; models `helios-small` / `helios-medium` / `helios-large` with invented sample rates). No real usage, customer, or billing data is used anywhere.

Stdlib-only Python. Zero network, zero API keys, zero external dependencies.

## Quickstart

```bash
# 1. Metrics for a single run (the seeded baseline)
python3 cli.py report --input fixtures/baseline.json

# 2. Baseline vs candidate under the sample budget (table + verdict)
python3 cli.py compare --baseline fixtures/baseline.json \
    --candidate fixtures/candidate_fail.json --budget fixtures/budget.sample.json

# 3. The CI gate: exit 0 = pass/warn, 1 = budget breach, 2 = IO/data error
python3 cli.py check --baseline fixtures/baseline.json \
    --candidate fixtures/candidate_pass.json --budget fixtures/budget.sample.json
echo $?   # 0 — small regression, inside budget
python3 cli.py check --baseline fixtures/baseline.json \
    --candidate fixtures/candidate_fail.json --budget fixtures/budget.sample.json
echo $?   # 1 — cost +100%, p95 +115.6%, score -0.12: breach on all six rules

# 4. One-command end-to-end demo (report -> pass -> fail -> live serve)
python3 demo.py        # or: python3 cli.py demo

# 5. Tiny localhost API: POST /compare, GET /health on 127.0.0.1
python3 cli.py serve --port 8765
curl -s localhost:8765/health
curl -s -X POST localhost:8765/compare -H 'Content-Type: application/json' \
  -d '{"baseline": {...}, "candidate": {...}, "budget": {...}}'
```

## The seeded fixtures at a glance

Three runs of the same 24-case suite (8 cases × 3 suites — retrieval, summarization, support — all on `helios-medium`), plus the sample budget. **Tokens** — the chunks of text a model reads and writes, the unit AI usage is billed on — are priced per case as `input × $0.001/1k + output × $0.005/1k` for `helios-medium`:

| Run | Total cost | Tokens | Cost / case | p95 latency | Mean score |
|---|---|---|---|---|---|
| baseline | $0.1200 | 65,600 | $0.0050 | 320 ms | 0.88 |
| candidate (pass) | $0.1260 (+5.0%) | 68,880 | $0.00525 | 325 ms (+1.6%) | 0.87 |
| candidate (fail) | $0.2400 (+100.0%) | 131,200 | $0.0100 | 690 ms (+115.6%) | 0.76 |

**p95 latency** — the latency that 95% of cases beat (here, the 23rd smallest of 24 by nearest-rank); the tail users actually feel, not the average that hides it.

The sample budget (`fixtures/budget.sample.json`): total cost ≤ $0.18, cost **regression** (how much worse the candidate is than the baseline, as a percentage) ≤ 12%, p95 ≤ 500 ms, p95 regression ≤ 20%, cost per case ≤ $0.0075, score drop ≤ 0.05. The pass candidate clears all six rules; the fail candidate breaches all six. These numbers are pinned by golden evals, so any change to pricing, metrics, or fixtures shows up as an eval failure, not a surprise.

## How the gate works

| Piece | Rule |
|---|---|
| **Pricing** | Bundled table for the three fictional models; cost per case = `in/1000 × input rate + out/1000 × output rate`. An unknown model raises — a gate that guesses a price reports a made-up cost |
| **Metrics** | Total cost / tokens / cost per case, mean + p50 + p95 latency (nearest-rank: sort, take rank `ceil(p/100 × N)`), mean score, plus per-suite and per-model breakdowns whose costs sum exactly to the totals |
| **Budget** | Six optional limits (below); at least one required, all must be non-negative — an empty budget would pass everything, which is not a gate |
| **Findings** | One per configured rule: `{rule, severity, baseline, candidate, delta, delta_pct, message}`. **Verdict** — the gate's overall call — is the worst severity across findings |
| **Warn bands** | Absolute ceilings warn at 80% of the limit; regression and score-drop rules warn above 50% of the limit. Warn prints but `check` still exits 0 — warn means "heading toward the limit," and failing builds on it would train teams to ignore the gate |

Budget fields: `max_total_cost_usd`, `max_cost_regression_pct`, `max_p95_latency_ms`, `max_p95_regression_pct`, `max_cost_per_case_usd`, `max_score_drop` (absolute points, e.g. `0.05`).

## Architecture

| Module | Job |
|---|---|
| `pricing.py` | Bundled fictional pricing table (per-1k input/output rates) + per-case cost; unknown model raises |
| `metrics.py` | Run loading/validation (case `model` falls back to the run-level default; unknown models fail at load) + metrics: totals, nearest-rank percentiles, per-suite / per-model breakdowns |
| `budget.py` | `Budget` dataclass loaded from JSON: six optional limits, at least one required, non-negative validated, unknown fields rejected |
| `compare.py` | Baseline vs candidate + budget → findings with pass/warn/fail severities and warn bands; verdict = worst severity |
| `cli.py` | `report` / `compare` / `check` (CI exit 0/1/2) / `demo` / `serve` (stdlib `http.server` on 127.0.0.1: `POST /compare`, `GET /health`) |
| `demo.py` | End-to-end asserts: baseline totals pinned, pass candidate exits 0, fail candidate exits 1, live localhost serve round-trip matches local compare exactly |
| `fixtures/` | `baseline.json` (24 cases, 3 suites), `candidate_pass.json` (+5% cost, inside budget), `candidate_fail.json` (breaches all six rules), `budget.sample.json` |

## Evals

`python3 evals/run_evals.py` → **13/13 golden evals**, report committed at `evals/eval_report.json` (md5 `14c8585df1ed719d38fee4a4cba3e696`, byte-identical across 3 verified runs):

- **E1** baseline totals pinned (24 cases, $0.12, 65,600 tokens, $0.005/case)
- **E2** baseline latency/score pinned (mean 215 ms, p50 210, p95 320, score 0.88)
- **E3** per-suite breakdown pinned (retrieval $0.028 / summarization $0.056 / support $0.036) and sums to the total
- **E4** per-model breakdown sums to the total
- **E5** pricing math pinned for all three fictional models
- **E6** percentile math pinned (nearest-rank, incl. p100 = max)
- **E7** pass candidate: verdict pass, all six findings pass
- **E8** pass candidate totals pinned ($0.126, p95 325 ms, score 0.87)
- **E9** fail candidate: verdict fail, all six findings fail, deltas pinned (cost +100.0%, p95 +115.625%, score −0.12)
- **E10** warn band pinned (baseline under a $0.14 ceiling warns at the 80% line)
- **E11** budget validation (empty and negative budgets raise)
- **E12** CLI `check` exit codes 0 / 1 / 2
- **E13** determinism (repeat compare + metrics are identical)

Unit tests: `python3 -m unittest discover -s tests` → **58 hermetic tests**, including a no-network enforcement test, exact-rank percentile regression cases, warn-band boundaries for every rule family, budget validation, CLI exit codes, and a live serve round-trip compared against local results.

## Development loop — what the checks actually caught

1. **Float `ceil` misranks percentiles.** The first percentile implementation computed the nearest-rank with `math.ceil(pct / 100.0 * N)`. An exhaustive cross-check against exact integer math during the build found 702 mismatches in 500,000 (percentile, N) combinations — e.g. p7 of 100 values: `7 / 100.0 * 100` is `7.000000000000001`, so `ceil` returns rank 8 instead of 7 and silently picks the wrong element. The seeded fixtures (p50/p95 of 24) happened to be unaffected, which is exactly why the exhaustive check mattered. Fixed with exact `Fraction` arithmetic; a regression test pins p7 of 0..99 = 6.
2. **A seeded example must not sit on its own warn line.** The pass candidate is a +5.0% cost regression by construction. Warn fires above 50% of the regression limit, so a round 10% limit would put the warn line at exactly 5.0% — one floating-point wobble from flipping the portfolio's headline example between pass and warn. The sample budget therefore uses a 12% limit (warn above 6%), and the boundary itself — regression at exactly half the limit passes, strictly above warns — is pinned by a unit test rather than left to fixture luck.
3. **Warn must not break the build.** `check` exits 0 on a warn verdict by design (only a fail breaches). The alternative — failing on warn — makes the gate cry wolf on every healthy-but-growing suite, and teams respond by raising limits until the gate is decorative. The demo and CLI tests pin the 0/1/2 contract so the distinction can't erode silently.

## Scope and honest limits

- **Sample prices, fictional models.** The bundled rates are invented for the fictional Helios models so the project runs offline; a production gate loads the provider's current price table. The arithmetic and gate semantics are the real content.
- **One baseline, one candidate.** Real pipelines keep a rolling baseline window and per-suite budgets; here the budget is global for the run (per-suite breakdowns are reported, not gated) — suite-level limits are the named next step.
- **Latency is per-case, as recorded.** The gate trusts the `latency_ms` the eval harness wrote; it does not time anything itself, and percentile math over 24 cases is coarse by nature (each case is ~4% of the distribution).
- **Scores are taken at face value.** Whether the eval scores themselves are trustworthy is the `llm-judge-calibration` question; this gate only checks that they didn't drop while costs climbed.

## License

MIT — see LICENSE.
