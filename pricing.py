"""Bundled pricing for fictional Helios models.

Rates are USD per 1,000 tokens. These are sample rates for fictional
models, bundled so the project runs fully offline. Cost per case:

    cost = input_tokens / 1000 * input_rate + output_tokens / 1000 * output_rate

An unknown model raises ValueError — a gate that silently guesses a
price for a model it does not know would report a made-up cost.
"""

PRICING = {
    "helios-large": {"input_per_1k": 0.003, "output_per_1k": 0.015},
    "helios-medium": {"input_per_1k": 0.001, "output_per_1k": 0.005},
    "helios-small": {"input_per_1k": 0.0005, "output_per_1k": 0.0015},
}


def model_names():
    return sorted(PRICING)


def cost_for(model, input_tokens, output_tokens):
    """USD cost of one case. Raises ValueError for an unknown model."""
    if model not in PRICING:
        raise ValueError(
            f"unknown model {model!r}; known models: {', '.join(model_names())}")
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token counts must be non-negative")
    rates = PRICING[model]
    return (input_tokens / 1000.0 * rates["input_per_1k"]
            + output_tokens / 1000.0 * rates["output_per_1k"])
