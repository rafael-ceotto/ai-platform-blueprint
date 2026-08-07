# C4 Model — AI Platform Blueprint

Architecture overview using the [C4 model](https://c4model.com/)
(Context → Container → Component), rendered in Mermaid.

## Level 1 — System Context

Who uses the platform, and what external systems does it talk to.

```mermaid
C4Context
    title System Context — AI Platform Blueprint

    Person(user, "End User", "Interacts with the platform via a client app or API consumer")
    Person(developer, "Developer", "Integrates against the platform's API")

    System(platform, "AI Platform Blueprint", "FastAPI service exposing RAG / LLM capabilities over HTTP")

    System_Ext(ollama, "Ollama Runtime", "Local LLM inference daemon (generation + embeddings)")
    System_Ext(externalLLM, "External LLM Provider", "Optional hosted model API for higher-quality inference (future, see ADR-0002)")

    Rel(user, platform, "Sends requests to", "HTTPS/JSON")
    Rel(developer, platform, "Integrates via", "REST API")
    Rel(platform, ollama, "Requests completions/embeddings from", "HTTP")
    Rel(platform, externalLLM, "Optionally requests completions from", "HTTPS (not enabled by default)")
```

## Level 2 — Containers

The deployable units that make up the system and how they communicate.

```mermaid
C4Container
    title Container Diagram — AI Platform Blueprint

    Person(user, "End User")

    System_Boundary(platform, "AI Platform Blueprint") {
        Container(api, "API Service", "FastAPI / Python 3.12", "Exposes REST endpoints, orchestrates retrieval + generation, owns request validation and auth")
        Container(vectorstore, "Vector Store", "FAISS (in-process)", "Stores document embeddings, serves nearest-neighbor search (see ADR-0001)")
        ContainerDb(datavol, "Data Volume", "Docker volume", "Persists FAISS index files and other local artifacts")
    }

    Container_Ext(ollama, "Ollama", "Container / ollama/ollama", "Serves open-weight LLMs for generation and embeddings (see ADR-0002)")

    Rel(user, api, "HTTPS requests", "JSON/REST")
    Rel(api, vectorstore, "Similarity search / upsert", "in-process call")
    Rel(vectorstore, datavol, "Reads/writes index", "filesystem")
    Rel(api, ollama, "Generate / embed", "HTTP :11434")
```

## Level 3 — Components (API Service)

Internal structure of the `api` container, mirroring the `app/` package
layout.

```mermaid
C4Component
    title Component Diagram — API Service

    Container_Boundary(api, "API Service") {
        Component(main, "App Factory", "app/main.py", "Builds the FastAPI app, wires middleware and routers")
        Component(router, "API Router (v1)", "app/api/v1", "Aggregates versioned endpoint routers")
        Component(healthEp, "Health Endpoints", "app/api/v1/endpoints/health.py", "Liveness (/health) and readiness (/health/ready) probes")
        Component(config, "Settings", "app/core/config.py", "Typed configuration loaded from env / .env")
        Component(logging, "Logging Setup", "app/core/logging.py", "Structured JSON logging configuration")
        Component(ollamaClient, "Ollama Client", "app/services/ollama_client.py", "Thin async HTTP client for the Ollama API")
        Component(vectorPort, "VectorStore Port", "app/services (planned)", "Abstraction over the vector backend; FAISS is the current adapter")
    }

    Container_Ext(ollama, "Ollama", "Container")
    ContainerDb_Ext(datavol, "Data Volume")

    Rel(main, router, "includes")
    Rel(main, logging, "configures at startup")
    Rel(router, healthEp, "mounts")
    Rel(healthEp, config, "reads settings from")
    Rel(healthEp, ollamaClient, "checks reachability via")
    Rel(ollamaClient, ollama, "HTTP", "generate / version")
    Rel(vectorPort, datavol, "persists index to")
```

## Notes

- Diagrams use Mermaid's native `C4Context` / `C4Container` / `C4Component`
  syntax and render directly on GitHub and in most Markdown previewers.
- The Component diagram reflects the state after Sprint 1: health/readiness
  wiring and the Ollama client exist; the `VectorStore` port/FAISS adapter
  is the next piece of work (tracked alongside ADR-0001).
- Keep this file in sync with `app/` structure as new containers/components
  are added (e.g. a future ingestion worker, a Qdrant adapter, etc.).
