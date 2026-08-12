# ADR-0009: Async Ingestion / Message Broker — Not Needed Yet

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-12 |
| **Deciders** | AI Platform Blueprint team |
| **Related** | [ADR-0002: LLM Runtime](0002-llm-runtime-ollama-vs-external-apis.md) |

## Context

Whether to introduce a message broker (Kafka or similar — Redis Streams,
RabbitMQ) to decouple document ingestion from the request/response cycle,
so `POST /documents`/`/documents/upload` could return immediately and
hand off chunking/embedding/indexing to an async consumer.

## Decision Drivers

- Ingestion today (`backend/services/ingestion_service.py`) is
  synchronous by design: chunk -> embed (Ollama) -> store (FAISS), all
  within the request. Documents ingested in this blueprint are small,
  low-volume, and the whole point of the local-first design (ADR-0002)
  is fast, predictable turnaround for a single operator.
- No functional need exists yet for multiple independent consumers of
  an "ingestion event," replay, or fan-out — the three things a broker
  is actually for.
- Every dependency added to this blueprint should be justified by a
  real problem it solves, not by "this is what production systems
  have" — the project has consistently avoided infra weight without a
  concrete driver (e.g. hand-rolled BM25 instead of a heavier
  retrieval framework, no external LLM adapter yet per ADR-0002).

## Options Considered

### Option A — Keep ingestion synchronous (no broker)

**Pros**
- Zero added infrastructure; `docker-compose.yml` stays at its current
  five services (`api`, `ollama`, `jaeger`, `prometheus`, `grafana`).
- Simpler request lifecycle: a `200` response means the document is
  actually searchable, no eventual-consistency window to reason about
  or explain.
- Matches actual usage: nothing in this blueprint ingests at a volume
  or concurrency that a synchronous call can't handle.

**Cons**
- Ingestion latency is bounded by embedding latency (Ollama), visible
  to the caller — fine at today's scale, would degrade under bulk
  imports.

### Option B — Kafka (or similar) fronting an async ingestion worker

**Pros**
- Decouples upload from processing; `POST /documents/upload` could
  return immediately and a worker consumes the event to chunk/embed/index.
- Real architectural pattern worth knowing, and multiple consumers
  (e.g. an indexing worker plus an audit/notification consumer) become
  possible later.

**Cons**
- A broker (plus Zookeeper/KRaft for Kafka specifically), producer/
  consumer code, topic/schema design, and a new worker process/container
  — substantial infrastructure for a local demo with no throughput
  problem to solve today.
- Complicates the "clone, `docker compose up`, it just works" story
  this blueprint has held to through every prior sprint.
- Not called for anywhere in the project's reference roadmap.

## Decision

**Keep ingestion synchronous. No message broker for now.** The
recurring theme across this blueprint's ADRs — minimal, justified
infrastructure over anticipatory architecture — applies here too:
nothing in the current scope needs decoupled/async processing, multiple
consumers, or event replay.

## Revisit Triggers

Introduce an async task queue (Celery/RQ — simpler, no separate broker
concept beyond Redis) or an event log (Kafka/Redis Streams, if multiple
independent consumers are genuinely needed) when:

- Ingestion needs to handle bulk/batch imports (many documents per
  request, or a folder-of-documents workflow) where synchronous
  embedding would make requests time out.
- More than one system needs to react to "a document was ingested"
  independently (e.g. a search-index updater and a separate audit log),
  which is what a broker's fan-out actually buys over a simple queue.
- Ingestion throughput requirements exceed what a single synchronous
  request path can sustain, and horizontal scaling of the API process
  itself isn't the right lever.

## Consequences

- No new services, dependencies, or code from this ADR — it exists to
  record the reasoning so the question doesn't need re-litigating, and
  so the trade-off is visible to anyone reviewing this blueprint's
  architecture decisions.
