"""LLM call trace observability -- the read side of the tracing layer.

- `GET /observability/traces`  -> most recent LLM calls (prompt,
  completion, tokens, latency, cost), across every `/documents/ask` node.
- `GET /observability/summary` -> aggregate cost/token/latency stats,
  overall and broken down by node.

Traces are written transparently while `/documents/ask` runs (see
`observability/llm_traces/callback.py`); nothing here writes data.
Requires the same `X-API-Key` header and rate limit as every other
endpoint. See docs/adr/0015-llm-tracing-and-cost-observability.md.
"""

from fastapi import APIRouter, Depends, Query

from backend.api.deps import enforce_rate_limit, get_llm_trace_store
from backend.models.observability import (
    NodeAggregateItem,
    TraceItem,
    TracesResponse,
    TraceSummaryResponse,
)
from observability.llm_traces.port import LLMTraceStorePort

router = APIRouter(tags=["observability"])


@router.get("/observability/traces", response_model=TracesResponse, summary="Recent LLM traces")
async def list_traces(
    limit: int = Query(default=50, ge=1, le=500),
    store: LLMTraceStorePort = Depends(get_llm_trace_store),
    _: None = Depends(enforce_rate_limit),
) -> TracesResponse:
    traces = [
        TraceItem(
            request_id=t.request_id,
            node=t.node,
            model=t.model,
            prompt=t.prompt,
            completion=t.completion,
            prompt_tokens=t.prompt_tokens,
            completion_tokens=t.completion_tokens,
            latency_ms=t.latency_ms,
            cost_usd=t.cost_usd,
            created_at=t.created_at,
        )
        for t in store.recent(limit)
    ]
    return TracesResponse(traces=traces)


@router.get(
    "/observability/summary", response_model=TraceSummaryResponse, summary="LLM trace summary"
)
async def trace_summary(
    store: LLMTraceStorePort = Depends(get_llm_trace_store),
    _: None = Depends(enforce_rate_limit),
) -> TraceSummaryResponse:
    summary = store.summary()
    return TraceSummaryResponse(
        total_requests=summary.total_requests,
        total_calls=summary.total_calls,
        total_cost_usd=summary.total_cost_usd,
        total_prompt_tokens=summary.total_prompt_tokens,
        total_completion_tokens=summary.total_completion_tokens,
        avg_latency_ms=summary.avg_latency_ms,
        p95_latency_ms=summary.p95_latency_ms,
        by_node=[
            NodeAggregateItem(
                node=n.node,
                calls=n.calls,
                total_cost_usd=n.total_cost_usd,
                avg_latency_ms=n.avg_latency_ms,
            )
            for n in summary.by_node
        ],
    )
