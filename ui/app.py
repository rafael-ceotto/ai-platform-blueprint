"""Minimal demo UI for Konsole.ai, beyond Swagger.

Talks to the API over HTTP only (see api_client.py) -- never imports
backend code directly. See docs/adr/0010-streamlit-demo-ui.md.
"""

import os
from typing import Any

import api_client
import streamlit as st

st.set_page_config(page_title="Konsole.ai", page_icon="🤖", layout="wide")

st.sidebar.header("Connection")
base_url = st.sidebar.text_input(
    "API base URL", value=os.environ.get("API_BASE_URL", "http://localhost:8000")
)
api_key = st.sidebar.text_input(
    "API key", value=os.environ.get("API_KEY", "dev-local-key"), type="password"
)

st.title("Konsole.ai")
st.caption("A minimal demo UI over the RAG API -- ask, search, and ingest, beyond Swagger.")

ask_tab, search_tab, ingest_tab, observability_tab = st.tabs(
    ["💬 Ask", "🔍 Search", "📄 Ingest", "📊 Observability"]
)


with ask_tab:
    st.subheader("Ask a question")
    st.caption(
        "Works for document content, or ask about ingestion history "
        '(e.g. "what happened when I uploaded document <id>").'
    )
    query = st.text_input("Question", key="ask_query")
    top_k = st.number_input("top_k", min_value=1, max_value=50, value=5, key="ask_top_k")

    if st.button("Ask", key="ask_button") and query:
        result: dict[str, Any] = {}

        def _tokens() -> Any:
            for event in api_client.ask_stream(base_url, api_key, query, int(top_k)):
                if event.type == "token":
                    yield event.content
                elif event.type == "done":
                    result["answer"] = event.answer
                    result["sources"] = event.sources
                elif event.type == "error":
                    result["error"] = event.detail

        try:
            st.write_stream(_tokens())
        except api_client.ApiError as exc:
            st.error(f"Request failed: {exc}")
        else:
            if result.get("error"):
                st.error(result["error"])
            elif result.get("sources"):
                with st.expander(f"Sources ({len(result['sources'])})"):
                    for source in result["sources"]:
                        st.markdown(f"**{source['chunk_id']}** (score: {source['score']:.3f})")
                        st.text(source["text"])
            else:
                st.caption("No sources -- routed to a direct answer, no retrieval needed.")


with search_tab:
    st.subheader("Hybrid search")
    search_query = st.text_input("Query", key="search_query")
    search_top_k = st.number_input("top_k", min_value=1, max_value=50, value=5, key="search_top_k")

    if st.button("Search", key="search_button") and search_query:
        try:
            results = api_client.search(base_url, api_key, search_query, int(search_top_k))
        except api_client.ApiError as exc:
            st.error(f"Request failed: {exc}")
        else:
            if not results:
                st.info("No results.")
            else:
                st.dataframe(
                    [
                        {
                            "chunk_id": r["chunk_id"],
                            "document_id": r["document_id"],
                            "score": r["score"],
                            "text": r["text"],
                        }
                        for r in results
                    ]
                )


with ingest_tab:
    st.subheader("Ingest a document")
    st.caption("Every run is logged -- ask about it later in the Ask tab.")
    mode = st.radio("Source", ["Raw text", "File upload"], key="ingest_mode")

    _STEP_LABELS = {
        "loading": "Loading file",
        "chunking": "Chunking text",
        "embedding": "Embedding chunks",
        "storing": "Storing in the vector index",
    }

    def _run_ingest(events: Any) -> None:
        result: dict[str, Any] = {}
        with st.status("Starting ingestion...", expanded=True) as status:
            try:
                for event in events:
                    if event.type == "step":
                        label = _STEP_LABELS.get(event.step, event.step)
                        status.update(label=label)
                        st.write(f"✅ {label}")
                    elif event.type == "done":
                        result["document_id"] = event.document_id
                        result["chunk_count"] = event.chunk_count
                        status.update(label="Ingestion complete", state="complete", expanded=False)
                    elif event.type == "error":
                        result["error"] = event.detail
                        status.update(label="Ingestion failed", state="error")
            except api_client.ApiError as exc:
                result["error"] = str(exc)
                status.update(label="Ingestion failed", state="error")

        if result.get("error"):
            st.error(result["error"])
        elif result.get("document_id"):
            st.success(
                f"Ingested document {result['document_id']} ({result['chunk_count']} chunk(s))"
            )

    if mode == "Raw text":
        text = st.text_area("Text", key="ingest_text")
        if st.button("Ingest", key="ingest_button") and text:
            _run_ingest(api_client.ingest_text_stream(base_url, api_key, text, {}))
    else:
        uploaded = st.file_uploader(
            "File (PDF, Markdown, TXT, or HTML)",
            type=["pdf", "md", "txt", "html"],
            key="ingest_file",
        )
        if uploaded is not None and st.button("Upload", key="upload_button"):
            _run_ingest(
                api_client.upload_file_stream(
                    base_url, api_key, uploaded.name, uploaded.getvalue(), {}
                )
            )


with observability_tab:
    st.subheader("LLM call observability")
    st.caption(
        "Every chat-model call made while answering a question -- prompt, "
        "completion, tokens, latency, and estimated cost. Local Ollama models "
        "are free, so cost reads $0.00 unless a paid provider is configured."
    )

    if st.button("Load / refresh", key="observability_refresh"):
        try:
            st.session_state["observability_summary"] = api_client.get_trace_summary(
                base_url, api_key
            )
            st.session_state["observability_traces"] = api_client.get_traces(
                base_url, api_key, limit=50
            )
        except api_client.ApiError as exc:
            st.error(f"Request failed: {exc}")

    summary = st.session_state.get("observability_summary")
    traces = st.session_state.get("observability_traces")

    if summary is None:
        st.info("Click 'Load / refresh' to fetch LLM call traces.")
    else:
        metric_cols = st.columns(4)
        metric_cols[0].metric("Requests", summary["total_requests"])
        metric_cols[1].metric("LLM calls", summary["total_calls"])
        metric_cols[2].metric("Total cost", f"${summary['total_cost_usd']:.4f}")
        metric_cols[3].metric("Avg latency", f"{summary['avg_latency_ms']:.0f} ms")

        if summary["by_node"]:
            st.caption("Breakdown by graph node")
            st.dataframe(summary["by_node"], hide_index=True)

        if traces:
            st.caption("Recent calls")
            st.dataframe(
                [
                    {
                        "node": t["node"],
                        "model": t["model"],
                        "prompt_tokens": t["prompt_tokens"],
                        "completion_tokens": t["completion_tokens"],
                        "latency_ms": round(t["latency_ms"], 1),
                        "cost_usd": t["cost_usd"],
                        "created_at": t["created_at"],
                    }
                    for t in traces
                ],
                hide_index=True,
            )
            with st.expander("Prompt / completion text for a call"):
                labels = [f"{t['created_at']} -- {t['node']}" for t in traces]
                selected = st.selectbox(
                    "Call", options=range(len(traces)), format_func=lambda i: labels[i]
                )
                st.text_area("Prompt", traces[selected]["prompt"], height=150, disabled=True)
                st.text_area(
                    "Completion", traces[selected]["completion"], height=100, disabled=True
                )
        else:
            st.info("No LLM calls recorded yet -- ask a question in the Ask tab first.")
