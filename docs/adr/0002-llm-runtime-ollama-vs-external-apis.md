# ADR-0002: LLM Runtime — Ollama vs. External APIs

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-07 |
| **Deciders** | Konsole.ai team |
| **Related** | [ADR-0001: Vector Store](0001-vector-store-faiss-vs-qdrant.md) |

## Context

The platform needs an LLM inference backend for generation and (optionally)
embeddings. The two broad options are:

- **Ollama** — run open-weight models (Llama, Mistral, Qwen, etc.) locally
  via a lightweight daemon with an HTTP API, packaged as a container.
- **External APIs** — hosted model providers (e.g. Anthropic, OpenAI)
  accessed over the network, billed per token.

## Decision Drivers

- **Cost of iteration.** During blueprint development and for anyone
  cloning the repo, unmetered local experimentation matters more than
  frontier model quality.
- **Reproducibility & offline capability.** `docker compose up` should
  produce a fully working system without API keys or internet egress,
  which matters for demos, CI, and air-gapped environments.
- **Data privacy.** A blueprint aimed at enterprise adopters needs to
  demonstrate a path where sensitive data never leaves the user's
  infrastructure.
- **Model quality ceiling.** Production workloads may eventually need
  frontier-model reasoning quality that open-weight local models don't yet
  match.
- **Operational simplicity for a starter kit.** No secrets management, no
  billing setup required to get the first `curl` request working.

## Options Considered

### Option A — Ollama (local-first)

**Pros**
- No API keys, no billing, no network dependency to get started — critical
  for a "clone and run" blueprint experience.
- Data never leaves the deployment boundary; strong default for privacy-
  sensitive use cases and easy to demo in restricted environments.
- Predictable, zero marginal cost per request — safe for CI, load testing,
  and unlimited local iteration.
- Runs as a peer container in `docker-compose.yml`, matching the
  project's "batteries included" philosophy.
- Easy to swap the underlying open-weight model per use case
  (`OLLAMA_MODEL` env var) without code changes.

**Cons**
- Model quality/reasoning ceiling is currently below top-tier hosted
  models for complex tasks.
- Inference is bound by local hardware (CPU/GPU/RAM); latency and
  throughput are worse than provider infrastructure, especially without a
  GPU.
- The operator now owns model lifecycle: pulling, updating, and storing
  multi-gigabyte model weights.

### Option B — External APIs

**Pros**
- Access to frontier-quality models with minimal operational burden per
  request; provider handles scaling and hardware.
- No local compute/GPU requirements; latency and throughput are generally
  more predictable at scale.
- Fast access to newly released models without re-provisioning
  infrastructure.

**Cons**
- Requires API keys and billing before the blueprint does anything —
  raises the barrier to "clone and run."
- Ongoing per-token cost, including during development, testing, and CI.
- Data leaves the deployment boundary, which is a non-starter for some
  target adopters until explicitly opted into.
- Availability is dependent on a third party (rate limits, outages,
  pricing/model deprecation changes outside our control).

## Decision

**Default to Ollama as the local-first LLM runtime**, shipped as a service
in `docker-compose.yml`, with the application talking to it through a
narrow `OllamaClient` (`llm/ollama/client.py`).

External providers are not ruled out — they are a natural next step for
production deployments that need frontier model quality — but they are
**not the Sprint 1 default** because they would require secrets and
billing before anyone can run the blueprint end-to-end.

## Revisit Triggers

Introduce (not necessarily replace) an external-API adapter when:

- A concrete use case needs reasoning/quality beyond what local
  open-weight models deliver.
- Target deployment hardware cannot reasonably host local inference
  (e.g. constrained edge/serverless environments).
- Throughput requirements exceed what local hardware can sustain and
  horizontal scaling of local inference is not cost-effective.

## Consequences

- LLM access goes through an internal `LLMClient`-style interface;
  `OllamaClient` is the first implementation. Adding an
  `AnthropicClient`/`OpenAIClient` later is an additive change, selected
  via configuration (e.g. `LLM_PROVIDER=ollama|anthropic|openai`), not a
  rewrite.
- `docker-compose.yml` includes an `ollama` service by default; teams that
  only want external APIs can disable it via compose profiles in a future
  iteration.
- Model choice (`OLLAMA_MODEL`) is externalized via configuration, so
  swapping models doesn't require a code change or rebuild.
