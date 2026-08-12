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

ask_tab, search_tab, ingest_tab = st.tabs(["💬 Ask", "🔍 Search", "📄 Ingest"])


with ask_tab:
    st.subheader("Ask a question")
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
    mode = st.radio("Source", ["Raw text", "File upload"], key="ingest_mode")

    if mode == "Raw text":
        text = st.text_area("Text", key="ingest_text")
        if st.button("Ingest", key="ingest_button") and text:
            try:
                result = api_client.ingest_text(base_url, api_key, text, {})
            except api_client.ApiError as exc:
                st.error(f"Request failed: {exc}")
            else:
                st.success(
                    f"Ingested document {result['document_id']} ({result['chunk_count']} chunk(s))"
                )
    else:
        uploaded = st.file_uploader(
            "File (PDF, Markdown, TXT, or HTML)",
            type=["pdf", "md", "txt", "html"],
            key="ingest_file",
        )
        if uploaded is not None and st.button("Upload", key="upload_button"):
            try:
                result = api_client.upload_file(
                    base_url, api_key, uploaded.name, uploaded.getvalue(), {}
                )
            except api_client.ApiError as exc:
                st.error(f"Request failed: {exc}")
            else:
                st.success(
                    f"Ingested document {result['document_id']} ({result['chunk_count']} chunk(s))"
                )
