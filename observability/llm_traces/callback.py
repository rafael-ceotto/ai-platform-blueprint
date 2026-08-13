"""LangChain callback that captures every chat-model call made while
answering one `/documents/ask` request as an `LLMTrace`.

Attached per-request via `config={"callbacks": [...]}` on the compiled
LangGraph's `.ainvoke()`/`.astream()` -- LangGraph tags every callback
invocation with the node that triggered it (`metadata["langgraph_node"]`),
the same mechanism `GenerationService.ask_stream` already relies on to
filter which tokens reach the client. See docs/adr/0015.

`on_llm_end` is the only place token usage/latency/completion text are
available, but it isn't given `metadata` -- only `on_chat_model_start`
is -- so the node name and start time are stashed here, keyed by
`run_id`, and picked back up in `on_llm_end`.
"""

import asyncio
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage, get_buffer_string
from langchain_core.outputs import ChatGeneration, LLMResult

from observability.llm_traces.models import LLMTrace
from observability.llm_traces.port import LLMTraceStorePort
from observability.llm_traces.pricing import estimate_cost


class LLMTraceCallbackHandler(AsyncCallbackHandler):
    """One instance per request -- holds in-flight call state, so it must
    not be shared across concurrent requests."""

    def __init__(self, store: LLMTraceStorePort, request_id: str, model: str) -> None:
        self._store = store
        self._request_id = request_id
        self._model = model
        self._pending: dict[UUID, tuple[float, str, str]] = {}

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        node = (metadata or {}).get("langgraph_node", "unknown")
        prompt = get_buffer_string(messages[0]) if messages else ""
        self._pending[run_id] = (time.perf_counter(), node, prompt)

    async def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        pending = self._pending.pop(run_id, None)
        if pending is None:
            return
        start, node, prompt = pending
        latency_ms = (time.perf_counter() - start) * 1000

        generation = response.generations[0][0]
        completion = generation.text
        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        if isinstance(generation, ChatGeneration) and isinstance(generation.message, AIMessage):
            usage = generation.message.usage_metadata
            if usage is not None:
                prompt_tokens = usage.get("input_tokens")
                completion_tokens = usage.get("output_tokens")

        trace = LLMTrace(
            request_id=self._request_id,
            node=node,
            model=self._model,
            prompt=prompt,
            completion=completion,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            cost_usd=estimate_cost(self._model, prompt_tokens, completion_tokens),
            created_at=datetime.now(UTC).isoformat(),
        )
        await asyncio.to_thread(self._store.record, trace)
