# ADR-0006: Hybrid Retrieval, LangGraph Query Routing, LLM Re-ranking

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-08 |
| **Deciders** | Konsole.ai team |
| **Related** | [ADR-0001: Vector Store](0001-vector-store-faiss-vs-qdrant.md), [ADR-0004: LangChain for Answer Generation](0004-langchain-for-answer-generation.md), [ADR-0005: Document Loaders](0005-document-loaders.md) |

## Context

Retrieval was vector-only, and `/documents/ask` always retrieved before
answering, even for queries that don't need it (greetings, meta
questions). This closes the roadmap's grouped item "Hybrid retrieval,
query routing (LangGraph), re-ranking" in one change, spanning three
decisions.

## Decision 1 — Hybrid retrieval: hand-rolled BM25 + `langchain_classic`'s `EnsembleRetriever`

**`langchain_community` (where `BM25Retriever` lives) is archived** —
sunset by the LangChain team, repository read-only as of 2026-06-19, no
standalone BM25 replacement package published yet. Confirmed directly
(installing it prints a `DeprecationWarning` naming the sunset; the
GitHub repo banner confirms archival) before deciding, not assumed.
Building new code on an unmaintained package would undercut the exact
"current best practices" goal this project serves.

`langchain_classic` (where `EnsembleRetriever` lives) is a **separate,
actively maintained** package (1.0.x) — not part of the sunset. So:
`retrieval/retriever/bm25_retriever.py` implements `BM25DocumentRetriever`
ourselves (same `BaseRetriever` pattern as ADR-0004's `VectorStoreRetriever`,
using the still-active `rank_bm25` library), and `retrieval/retriever/hybrid.py`
combines it with the existing `VectorStoreRetriever` via the real,
maintained `EnsembleRetriever` — genuine LangChain usage for the fusion
mechanics, without depending on the archived package.

**BM25 index is rebuilt from `FaissVectorStore.payloads()` on every
call**, not maintained as a second persisted index. A second index that
must stay in sync with FAISS's additions is a real synchronization
surface (write to both, handle partial failure, etc.); rebuilding is
O(corpus size) but pure in-memory computation, and fast enough at this
project's MVP corpus scale. No drift is possible because there is only
one source of truth.

**`EnsembleRetriever` does not expose a fused RRF score.** Verified
directly with fake retrievers before writing real code: it returns
whichever sub-retriever's `Document` it saw first, carrying that
retriever's own (incomparable — cosine similarity vs. BM25 raw score)
score. `retrieval/retriever/hybrid.py`'s `with_rrf_scores` recomputes a
rank-based score from the final fused order (`1 / (60 + rank)`, the same
`k=60` convention `EnsembleRetriever` itself defaults to) instead of
surfacing a misleading raw score to API consumers.

Applies to **both** `/documents/search` and `/documents/ask` — better
retrieval quality benefits anywhere retrieval happens.

## Decision 2 — Query routing: LangGraph `StateGraph`, `/documents/ask` only

A `classify_query` node (one LLM call) decides `DIRECT` (greeting, meta
question — answer without retrieval) vs. `RETRIEVE` (needs document
context), routing to a `direct_answer` node or the
`hybrid_retrieve → rerank → generate` path. This is the standard,
demonstrable LangGraph pattern for conditional branching (`llm/routing/query_graph.py`).

Not applied to `/documents/search` — routing is specifically about
whether to *generate an answer* with or without context; `/search`
always just searches, there's no "direct" alternative for it.

A second conditional edge after `hybrid_retrieve` (`route_after_retrieve`)
skips straight to a fixed no-context answer when nothing was retrieved,
preserving the short-circuit ADR-0004's original flat implementation
had — no wasted LLM call when there's nothing to reason over.

## Decision 3 — Re-ranking: the existing local SLM, not a cross-encoder

Re-ranks the hybrid-retrieved candidates via one more `ChatOllama` call
(`rerank` node) rather than a dedicated cross-encoder model
(`sentence-transformers` + `torch`). Consistent with every prior
dependency-weight decision in this project (ADR-0001, ADR-0004, ADR-0005):
the local SLM is already in the stack; a cross-encoder would be a large
new ML dependency for a capability the SLM can already approximate.

**Fails open**: `llm/prompts/rerank_prompt.py`'s `parse_ranking` falls
back to the original (pre-rerank, RRF-fused) order if the model's
response isn't a valid permutation of the candidate indices. An 8B local
model asked to output `"3,1,2"` will sometimes get it wrong; a malformed
rerank response must never fail the request.

`/documents/search` does **not** rerank — it has no LLM dependency today,
and reranking is specifically about improving what gets fed to the
generation step, which only `/ask` has.

## Revisit Triggers

- BM25 corpus rebuild-per-query becomes a measurable latency problem at
  larger corpus sizes → cache the `BM25Okapi` instance, invalidated on
  `FaissVectorStore.add()`, instead of rebuilding every call.
- A standalone BM25 integration package appears from the LangChain team
  post-`langchain_community` sunset → reconsider importing it instead of
  the hand-rolled `BM25DocumentRetriever`.
- Re-ranking quality from the local SLM proves insufficient → evaluate a
  cross-encoder specifically for that gap (same reasoning as ADR-0004's
  embedding-quality revisit trigger).
- Routing needs more than two branches (e.g., choosing between retrieval
  strategies, not just retrieve-vs-not) → extend `query_graph.py`'s
  conditional edges; the graph structure already supports it.

## Consequences

- `llm/routing/` (doc-anticipated, empty since the Sprint 3 restructure)
  is now populated.
- `GenerationService.ask()` is a thin wrapper around
  `build_query_graph(...).ainvoke(...)` — the routing/retrieval/rerank/
  generation logic all lives in the graph's node functions, each
  independently testable.
- `VectorStoreRetriever` (ADR-0004) now sets `Document.id` (previously
  only in metadata) — required for `EnsembleRetriever`'s dedup; a
  one-line, non-functional change to that file.
- `FaissVectorStore` gained a `payloads()` accessor, and the `VectorStore`
  Protocol did **not** grow this method — `HybridVectorStore`
  (`retrieval/retriever/hybrid.py`) is a separate, narrower-scoped
  Protocol combining `VectorStore` + `PayloadSource`, so a future
  non-FAISS adapter (e.g. Qdrant, which has native hybrid search and
  wouldn't need this at all) isn't forced to implement it.
