"""LangGraph query router for `/documents/ask`.

Decides whether a query needs retrieval before generating an answer,
instead of always paying for a retrieval round-trip. See
docs/adr/0006-hybrid-retrieval-and-query-routing.md.

Graph shape::

    classify_query --route="direct"----> direct_answer ------------> END
                    --route="retrieve"--> hybrid_retrieve --docs?--> rerank -> generate -> END
                                                            --empty--> no_context_answer -> END
"""

from typing import Any, Literal, TypedDict

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from llm.prompts.classify_prompt import CLASSIFY_PROMPT
from llm.prompts.direct_answer_prompt import DIRECT_ANSWER_PROMPT
from llm.prompts.rag_prompt import RAG_PROMPT
from llm.prompts.rerank_prompt import RERANK_PROMPT, parse_ranking
from retrieval.retriever.hybrid import HybridVectorStore, build_hybrid_retriever, with_rrf_scores
from retrieval.retriever.langchain_retriever import Embedder

NO_CONTEXT_ANSWER = "I don't have enough information to answer that."


class GraphState(TypedDict):
    query: str
    top_k: int
    rerank_top_n: int
    route: Literal["direct", "retrieve"]
    documents: list[Document]
    answer: str


def build_query_graph(
    vector_store: HybridVectorStore,
    embedder: Embedder,
    chat_model: BaseChatModel,
) -> CompiledStateGraph[GraphState, Any, GraphState, GraphState]:
    """Build and compile the query-routing graph.

    Called once per `GenerationService` instance -- the returned graph is
    reused across requests via `.ainvoke()`.
    """

    async def classify_query(state: GraphState) -> dict[str, Any]:
        chain = CLASSIFY_PROMPT | chat_model | StrOutputParser()
        response = await chain.ainvoke({"question": state["query"]})
        route: Literal["direct", "retrieve"] = (
            "direct" if "DIRECT" in response.upper() else "retrieve"
        )
        return {"route": route}

    def route_after_classify(state: GraphState) -> Literal["direct", "retrieve"]:
        return state["route"]

    async def direct_answer(state: GraphState) -> dict[str, Any]:
        chain = DIRECT_ANSWER_PROMPT | chat_model | StrOutputParser()
        answer = await chain.ainvoke({"question": state["query"]})
        return {"answer": answer, "documents": []}

    async def hybrid_retrieve(state: GraphState) -> dict[str, Any]:
        retriever = build_hybrid_retriever(vector_store, embedder, state["top_k"])
        documents = await retriever.ainvoke(state["query"])
        return {"documents": with_rrf_scores(documents)}

    def route_after_retrieve(state: GraphState) -> Literal["has_docs", "empty"]:
        return "has_docs" if state["documents"] else "empty"

    async def no_context_answer(state: GraphState) -> dict[str, Any]:
        # Skip the LLM entirely when retrieval found nothing -- there's
        # no context to reason over, and the answer is fixed either way.
        return {"answer": NO_CONTEXT_ANSWER}

    async def rerank(state: GraphState) -> dict[str, Any]:
        documents = state["documents"]
        if len(documents) <= 1:
            return {}

        candidates = "\n".join(f"{i + 1}. {doc.page_content}" for i, doc in enumerate(documents))
        chain = RERANK_PROMPT | chat_model | StrOutputParser()
        response = await chain.ainvoke({"question": state["query"], "candidates": candidates})
        order = parse_ranking(response, len(documents))
        reranked = [documents[i] for i in order][: state["rerank_top_n"]]
        return {"documents": reranked}

    async def generate(state: GraphState) -> dict[str, Any]:
        documents = state["documents"]
        context = "\n\n".join(f"[{i + 1}] {doc.page_content}" for i, doc in enumerate(documents))
        chain = RAG_PROMPT | chat_model | StrOutputParser()
        answer = await chain.ainvoke({"context": context, "question": state["query"]})
        return {"answer": answer}

    graph = StateGraph(GraphState)
    graph.add_node("classify_query", classify_query)
    graph.add_node("direct_answer", direct_answer)
    graph.add_node("hybrid_retrieve", hybrid_retrieve)
    graph.add_node("no_context_answer", no_context_answer)
    graph.add_node("rerank", rerank)
    graph.add_node("generate", generate)

    graph.add_edge(START, "classify_query")
    graph.add_conditional_edges(
        "classify_query",
        route_after_classify,
        {"direct": "direct_answer", "retrieve": "hybrid_retrieve"},
    )
    graph.add_edge("direct_answer", END)
    graph.add_conditional_edges(
        "hybrid_retrieve",
        route_after_retrieve,
        {"has_docs": "rerank", "empty": "no_context_answer"},
    )
    graph.add_edge("no_context_answer", END)
    graph.add_edge("rerank", "generate")
    graph.add_edge("generate", END)

    return graph.compile()
