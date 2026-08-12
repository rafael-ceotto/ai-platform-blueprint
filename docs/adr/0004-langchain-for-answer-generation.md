# ADR-0004: Answer Generation — LangChain LCEL Chain

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-08 |
| **Deciders** | Konsole.ai team |
| **Related** | [ADR-0001: Vector Store](0001-vector-store-faiss-vs-qdrant.md), [ADR-0002: LLM Runtime](0002-llm-runtime-ollama-vs-external-apis.md) |

## Context

Through Sprint 3, `OllamaClient.generate()` was defined but never called:
`/documents/search` returned raw retrieved chunks with no answer
synthesis. For a platform whose premise is local SLM usage, an
unexercised generation path undersells the whole point. Sprint 4 closes
that gap with a real retrieval-augmented *generation* endpoint,
`POST /documents/ask`, and does so using LangChain — the platform's
reference vision document lists LangChain/LangGraph as part of the
intended stack, and retrieval+prompt+LLM chains are LangChain's most
common, most interview-relevant use case.

## Decision Drivers

- **Close the SLM usage gap** with the standard tool for the job, not a
  second hand-rolled prompt-formatting layer.
- **Don't relitigate ADR-0001.** The `VectorStore` port and FAISS adapter
  already work and are unit-tested; generation should consume them, not
  replace them.
- **Keep the dependency footprint proportional to what's used.** Sprint 2
  and 3 avoided extra frameworks because nothing needed them yet: this is
  the first time something does (LCEL chain composition, a maintained
  Ollama chat-model integration).
- **Testability without a live Ollama daemon**, matching the existing
  pattern (`get_ollama_client`/`get_vector_store` are already overridable
  FastAPI dependencies).

## Options Considered

### Dependency scope: Option A — `langchain-core` + `langchain-ollama` only

**Pros**
- Everything this feature needs — `BaseRetriever`, `Document`,
  `ChatPromptTemplate`, `StrOutputParser`, `FakeListChatModel` for tests —
  ships in `langchain-core`; `ChatOllama` ships in `langchain-ollama`.
  Neither requires the full `langchain` meta-package.
- Smaller dependency surface; no unused agent/chain-legacy code paths.

**Cons**
- If a later sprint needs prebuilt chains, document loaders, or agents
  from `langchain`/`langchain-community`, those get added then, not now.

### Dependency scope: Option B — full `langchain` + `langgraph` now

**Pros**
- One dependency decision instead of several spread across sprints.
- Immediately available for agentic/multi-step work.

**Cons**
- Nothing in this sprint uses agents, graphs, or legacy chain classes —
  adding them now is speculative weight with no current caller.

### Retrieval integration: Option A — custom `BaseRetriever` wrapping our `VectorStore`

**Pros**
- Preserves ADR-0001: FAISS stays behind our own port; LangChain becomes
  a consumer of it, not a replacement.
- No duplicate index/embedding logic to keep in sync.

**Cons**
- A small amount of adapter code (`retrieval/retriever/langchain_retriever.py`)
  instead of using LangChain's built-in FAISS vector store class directly.

### Retrieval integration: Option B — LangChain's own FAISS vectorstore wrapper

**Pros**
- Less adapter code; LangChain examples mostly assume this path.

**Cons**
- Would duplicate or replace `FaissVectorStore`/`VectorStore`, reopening
  ADR-0001 for no functional gain, and forces embeddings through
  LangChain's `Embeddings` interface instead of the existing
  `OllamaClient.embed()`.

## Decision

**Add `langchain-core` and `langchain-ollama` only**, and integrate via a
custom `VectorStoreRetriever(BaseRetriever)` (`retrieval/retriever/`) that
wraps the existing `VectorStore` port and `OllamaClient.embed()`. The
generation chain itself (`RAG_PROMPT | chat_model | StrOutputParser()`,
`llm/prompts/rag_prompt.py` + `backend/services/generation_service.py`)
is genuine LCEL composition — a `ChatPromptTemplate`, a `ChatOllama`
chat model, and `StrOutputParser`, piped together. The chat model is
injected via a new `get_chat_model` FastAPI dependency (mirroring
`get_ollama_client`/`get_vector_store`), overridden in tests with
`langchain_core.language_models.FakeListChatModel` — no real Ollama
daemon required to test `POST /documents/ask`.

The full `langchain` package and LangGraph are **not** added yet. They
are the natural fit for the doc's later "query routing" / hybrid
retrieval work (Sprint 4's other item), which needs multi-step / graph
control flow this straight-line chain doesn't.

## Revisit Triggers

- Multi-step or branching retrieval logic (query routing, re-ranking,
  agentic tool use) is needed → adopt LangGraph then, not speculatively now.
- Document loaders are needed for PDF/Markdown/HTML ingestion → evaluate
  `langchain-community`'s loaders at that point (separate from this ADR's
  generation-chain scope).
- The custom retriever's async-only limitation (`_get_relevant_documents`
  raises `NotImplementedError`) becomes a real constraint (e.g. a sync
  caller appears) → give `OllamaClient` a sync embedding path.

## Consequences

- `retrieval/retriever/langchain_retriever.py` and
  `llm/prompts/rag_prompt.py` populate two folders the reference doc's
  layout anticipated but that were empty after the Sprint 3 restructure.
- `VectorStore` (`retrieval/vector_store/port.py`) is now `@runtime_checkable`,
  and a new narrow `Embedder` protocol (`retrieval/retriever/langchain_retriever.py`,
  matching `OllamaClient.embed`) was extracted for the same reason:
  `BaseRetriever` is a pydantic model, and pydantic validates
  arbitrary-type fields via `isinstance` — which requires either a
  `@runtime_checkable` `Protocol` (structural match) or the exact
  concrete class. Depending on `Embedder` rather than concrete
  `OllamaClient` also means the retriever (and its tests) don't care
  which client implements embedding.
- `POST /documents/ask` is the first endpoint where the SLM actually
  generates text; `OllamaClient.generate()` itself remains unused —
  generation now goes through `ChatOllama` instead. Worth revisiting
  whether `generate()` should be removed if nothing else calls it by the
  time this stabilizes.
