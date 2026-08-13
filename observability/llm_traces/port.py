"""Port for the LLM trace store backend.

`LLMTraceStore` (`observability/llm_traces/store.py`) is the only
adapter today; callers depend on this `Protocol`, not the concrete
class, matching the pattern `retrieval/vector_store/port.py` already
uses -- lets tests substitute an in-memory fake without inheriting
from the real (SQLite-backed) store.
"""

from typing import Protocol, runtime_checkable

from observability.llm_traces.models import LLMTrace, TraceSummary


@runtime_checkable
class LLMTraceStorePort(Protocol):
    def record(self, trace: LLMTrace) -> None:
        """Persist one LLM call trace."""
        ...

    def recent(self, limit: int = 50) -> list[LLMTrace]:
        """Return the most recent traces, newest first."""
        ...

    def summary(self) -> TraceSummary:
        """Return aggregate cost/token/latency stats across all traces."""
        ...
