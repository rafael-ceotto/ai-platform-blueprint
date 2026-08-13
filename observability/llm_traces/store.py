"""SQLite-backed store for LLM call traces.

A single file (`Settings.LLM_TRACE_DB_PATH`), no separate service --
same "reuse the simplest mechanism that fits" approach the project has
followed throughout (see docs/adr/0009, docs/adr/0015). Each method
opens and closes its own connection: at this project's scale (a local
demo, not a production write load) that's simpler and safer than
managing a shared connection across the thread pool `LLMTraceStore`
is called from (see `callback.py`), and SQLite's own file locking
handles the concurrency.
"""

import sqlite3
from pathlib import Path

from observability.llm_traces.models import LLMTrace, NodeAggregate, TraceSummary

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS llm_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL,
    node TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt TEXT NOT NULL,
    completion TEXT NOT NULL,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    latency_ms REAL NOT NULL,
    cost_usd REAL NOT NULL,
    created_at TEXT NOT NULL
)
"""


class LLMTraceStore:
    def __init__(self, db_path: str) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path))
        conn.row_factory = sqlite3.Row
        return conn

    def record(self, trace: LLMTrace) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO llm_traces (
                    request_id, node, model, prompt, completion,
                    prompt_tokens, completion_tokens, latency_ms, cost_usd, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace.request_id,
                    trace.node,
                    trace.model,
                    trace.prompt,
                    trace.completion,
                    trace.prompt_tokens,
                    trace.completion_tokens,
                    trace.latency_ms,
                    trace.cost_usd,
                    trace.created_at,
                ),
            )

    def recent(self, limit: int = 50) -> list[LLMTrace]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM llm_traces ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row_to_trace(row) for row in rows]

    def summary(self) -> TraceSummary:
        with self._connect() as conn:
            totals = conn.execute(
                """
                SELECT
                    COUNT(DISTINCT request_id) AS total_requests,
                    COUNT(*) AS total_calls,
                    COALESCE(SUM(cost_usd), 0) AS total_cost_usd,
                    COALESCE(SUM(prompt_tokens), 0) AS total_prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0) AS total_completion_tokens,
                    COALESCE(AVG(latency_ms), 0) AS avg_latency_ms
                FROM llm_traces
                """
            ).fetchone()

            latencies = [
                row["latency_ms"]
                for row in conn.execute("SELECT latency_ms FROM llm_traces ORDER BY latency_ms")
            ]

            by_node_rows = conn.execute(
                """
                SELECT
                    node,
                    COUNT(*) AS calls,
                    COALESCE(SUM(cost_usd), 0) AS total_cost_usd,
                    COALESCE(AVG(latency_ms), 0) AS avg_latency_ms
                FROM llm_traces
                GROUP BY node
                ORDER BY node
                """
            ).fetchall()

        return TraceSummary(
            total_requests=totals["total_requests"],
            total_calls=totals["total_calls"],
            total_cost_usd=totals["total_cost_usd"],
            total_prompt_tokens=totals["total_prompt_tokens"],
            total_completion_tokens=totals["total_completion_tokens"],
            avg_latency_ms=totals["avg_latency_ms"],
            p95_latency_ms=_percentile(latencies, 0.95),
            by_node=[
                NodeAggregate(
                    node=row["node"],
                    calls=row["calls"],
                    total_cost_usd=row["total_cost_usd"],
                    avg_latency_ms=row["avg_latency_ms"],
                )
                for row in by_node_rows
            ],
        )


def _row_to_trace(row: sqlite3.Row) -> LLMTrace:
    return LLMTrace(
        request_id=row["request_id"],
        node=row["node"],
        model=row["model"],
        prompt=row["prompt"],
        completion=row["completion"],
        prompt_tokens=row["prompt_tokens"],
        completion_tokens=row["completion_tokens"],
        latency_ms=row["latency_ms"],
        cost_usd=row["cost_usd"],
        created_at=row["created_at"],
    )


def _percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(int(len(sorted_values) * fraction), len(sorted_values) - 1)
    return sorted_values[index]
