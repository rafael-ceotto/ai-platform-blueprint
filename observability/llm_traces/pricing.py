"""Static per-model pricing for cost estimation.

Local Ollama models cost nothing to run, so every model defaults to
$0.00 -- this table only matters once ADR-0002's `LLM_PROVIDER` external-
API adapter exists and requests actually cost money. Keeping the lookup
in place now means cost tracking works automatically on that day,
instead of needing to be retrofitted.
"""

# model name -> (USD per 1K prompt tokens, USD per 1K completion tokens)
MODEL_PRICING: dict[str, tuple[float, float]] = {}

_DEFAULT_PRICING = (0.0, 0.0)


def estimate_cost(model: str, prompt_tokens: int | None, completion_tokens: int | None) -> float:
    input_price, output_price = MODEL_PRICING.get(model, _DEFAULT_PRICING)
    prompt_cost = (prompt_tokens or 0) / 1000 * input_price
    completion_cost = (completion_tokens or 0) / 1000 * output_price
    return prompt_cost + completion_cost
