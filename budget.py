"""Budget definition: the limits a candidate run must stay inside.

A budget is a JSON object; every field is optional, but at least one
must be set (an empty budget would pass everything, which is not a
gate). All values must be non-negative numbers.

    max_total_cost_usd       absolute ceiling on the run's total cost
    max_cost_regression_pct  candidate total may exceed baseline by at most this %
    max_p95_latency_ms       absolute ceiling on p95 latency
    max_p95_regression_pct   candidate p95 may exceed baseline by at most this %
    max_cost_per_case_usd    absolute ceiling on mean cost per case
    max_score_drop           candidate mean score may fall at most this much
                             (absolute points, e.g. 0.05)
"""
import json
from dataclasses import dataclass, fields

FIELDS = ("max_total_cost_usd", "max_cost_regression_pct", "max_p95_latency_ms",
          "max_p95_regression_pct", "max_cost_per_case_usd", "max_score_drop")


@dataclass
class Budget:
    max_total_cost_usd: float = None
    max_cost_regression_pct: float = None
    max_p95_latency_ms: float = None
    max_p95_regression_pct: float = None
    max_cost_per_case_usd: float = None
    max_score_drop: float = None

    def __post_init__(self):
        set_count = 0
        for f in fields(self):
            value = getattr(self, f.name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"budget field {f.name!r} must be a number")
            if value < 0:
                raise ValueError(f"budget field {f.name!r} must be non-negative")
            set_count += 1
        if set_count == 0:
            raise ValueError("budget sets no limits; at least one field is required")

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("budget must be a JSON object")
        unknown = sorted(set(data) - set(FIELDS))
        if unknown:
            raise ValueError(f"unknown budget fields: {', '.join(unknown)}")
        return cls(**{k: data[k] for k in FIELDS if k in data})

    @classmethod
    def load(cls, text):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid budget JSON: {exc}") from exc
        return cls.from_dict(data)

    @classmethod
    def load_file(cls, path):
        with open(path) as fh:
            return cls.load(fh.read())

    def to_dict(self):
        return {f.name: getattr(self, f.name) for f in fields(self)
                if getattr(self, f.name) is not None}
