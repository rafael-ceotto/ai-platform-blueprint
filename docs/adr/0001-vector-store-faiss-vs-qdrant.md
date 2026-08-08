# ADR-0001: Vector Store — FAISS vs. Qdrant

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-07 |
| **Deciders** | AI Platform Blueprint team |
| **Related** | [ADR-0002: LLM Runtime](0002-llm-runtime-ollama-vs-external-apis.md) |

## Context

The platform needs a vector similarity search component to support
retrieval-augmented generation (RAG): embedding documents, storing vectors,
and running nearest-neighbor queries at inference time.

Two candidates were evaluated for Sprint 1 / MVP scope:

- **FAISS** (Facebook AI Similarity Search) — an in-process library. No
  server, no network hop; the index lives as a file/artifact next to the
  application.
- **Qdrant** — a standalone vector database with its own HTTP/gRPC API,
  payload filtering, clustering, and persistence guarantees.

## Decision Drivers

- **Time to first working system.** Sprint 1 is about proving the
  end-to-end shape (API → retrieval → LLM), not scaling a search cluster.
- **Operational surface.** Every extra container is something to deploy,
  monitor, secure, and pay for. The blueprint should stay runnable with
  `docker compose up` and a single service, in addition to Ollama.
- **Data scale (near term).** Expected corpus size for the blueprint and
  early adopters is small-to-medium (thousands to low millions of vectors),
  well within FAISS's comfortable range on a single node.
- **Filtering / metadata needs.** Complex payload filtering, multi-tenant
  isolation, and horizontal scaling are anticipated *future* requirements,
  not present ones.
- **Migration cost later.** Whatever we pick now must not be a dead end —
  swapping stores later should not require rewriting the RAG pipeline.

## Options Considered

### Option A — FAISS (in-process)

**Pros**
- Zero extra infrastructure: no additional container, no network latency
  between the API and the index.
- Extremely fast for exact and approximate search at small/medium scale;
  battle-tested at Meta's own scale.
- Simple to snapshot (index is just a file) and to version alongside model
  artifacts.
- Free, permissive license (MIT), no vendor lock-in.

**Cons**
- No built-in persistence/replication story — the app owns index
  load/save and consistency.
- No native metadata filtering or multi-tenant access control; that logic
  has to live in the application layer.
- Scaling beyond a single process (sharding, horizontal scale-out) requires
  custom engineering.
- No first-class update/delete-by-id workflow; mutating an index is more
  manual than in a purpose-built vector DB.

### Option B — Qdrant (standalone service)

**Pros**
- Purpose-built vector database: payload filtering, hybrid search,
  snapshots, clustering, and a stable HTTP/gRPC API out of the box.
- Scales independently of the API tier; supports horizontal scale-out and
  multi-tenant collections.
- Active OSS project with a managed cloud option, easing a future
  production migration.

**Cons**
- Adds an operational dependency (another container/service to run,
  monitor, secure, and back up) — disproportionate for Sprint 1 scope.
- Network hop between API and vector store adds latency and a new failure
  mode to handle (retries, timeouts, circuit breaking).
- Overkill for the current data scale; most of its differentiators
  (filtering at scale, clustering) are unused in the MVP.

## Decision

**Adopt FAISS for the current stage (Sprint 1 / MVP).**

The blueprint prioritizes a lean, single-command local setup and fast
iteration on the RAG pipeline itself. FAISS satisfies the near-term scale
and functional requirements with the least operational overhead, and keeps
`docker-compose.yml` limited to the API and the LLM runtime.

To avoid lock-in, retrieval access goes through a small internal
abstraction (`VectorStore` interface in `retrieval/vector_store`) so the concrete
backend is an implementation detail, not something scattered through the
codebase.

## Revisit Triggers

Re-evaluate this decision (and prefer Qdrant) when any of the following
becomes true:

- Corpus size approaches tens of millions of vectors, or index rebuild
  time/memory footprint becomes a bottleneck on a single node.
- The product needs metadata filtering, multi-tenant isolation, or
  per-document ACLs at query time.
- The vector store needs to scale or fail independently from the API
  process (separate deploy/scaling lifecycle).
- Multiple services need concurrent read/write access to the same index.

## Consequences

- `retrieval/vector_store` defines a `VectorStore` port; FAISS is the first (and
  currently only) adapter behind it.
- Index artifacts are treated as data, not code: persisted under
  `VECTOR_STORE_PATH`, excluded from git, included in backup/restore
  runbooks once those exist.
- A future migration to Qdrant becomes a new adapter implementation plus a
  data migration script, not a rewrite of calling code.
