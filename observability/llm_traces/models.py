"""Data shapes for LLM call traces (cost/token/latency observability).

See docs/adr/0015-llm-tracing-and-cost-observability.md.
"""

from dataclasses import dataclass


@dataclass
class LLMTrace:
    request_id: str
    node: str
    model: str
    prompt: str
    completion: str
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: float
    cost_usd: float
    created_at: str


@dataclass
class NodeAggregate:
    node: str
    calls: int
    total_cost_usd: float
    avg_latency_ms: float


@dataclass
class TraceSummary:
    total_requests: int
    total_calls: int
    total_cost_usd: float
    total_prompt_tokens: int
    total_completion_tokens: int
    avg_latency_ms: float
    p95_latency_ms: float
    by_node: list[NodeAggregate]
