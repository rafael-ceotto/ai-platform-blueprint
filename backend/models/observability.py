"""Schemas for the LLM trace observability endpoints.

See docs/adr/0015-llm-tracing-and-cost-observability.md.
"""

from pydantic import BaseModel


class TraceItem(BaseModel):
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


class TracesResponse(BaseModel):
    traces: list[TraceItem]


class NodeAggregateItem(BaseModel):
    node: str
    calls: int
    total_cost_usd: float
    avg_latency_ms: float


class TraceSummaryResponse(BaseModel):
    total_requests: int
    total_calls: int
    total_cost_usd: float
    total_prompt_tokens: int
    total_completion_tokens: int
    avg_latency_ms: float
    p95_latency_ms: float
    by_node: list[NodeAggregateItem]
