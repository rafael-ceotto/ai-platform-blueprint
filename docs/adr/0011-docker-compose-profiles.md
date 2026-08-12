# ADR-0011: Docker Compose Profiles — Observability Stack Opt-In

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-12 |
| **Deciders** | Konsole.ai team |
| **Related** | [ADR-0008: Observability](0008-observability-tracing-metrics-dashboards.md) |

## Context

`docker compose up` brought up six containers: `api`, `ollama`, `ui`,
`jaeger`, `prometheus`, `grafana`. Three of those exist purely to show
off observability (ADR-0008) — real value for a portfolio piece, but
unnecessary weight for someone who just wants to try the RAG pipeline.

## Decision Drivers

- The core experience (`api` + `ollama` + `ui`) should stay fast and
  lean to start; observability is a deliberate, separate thing to show
  off, not a tax everyone pays by default.
- No functionality should be removed — this is about what starts by
  default, not what exists.

## Decision

**`jaeger`, `prometheus`, and `grafana` are gated behind Docker
Compose's `observability` profile**, via `profiles: ["observability"]`
on each. `api`/`ollama`/`ui` carry no `profiles` entry, so Compose
always starts them (services without a `profiles` key are part of
every run).

`docker compose up -d --build` → lean stack (3 containers).
`TRACING_ENABLED=true METRICS_ENABLED=true docker compose --profile
observability up -d --build` → full stack (6 containers).

**`api`'s `depends_on: jaeger` needed `required: false`** — without it,
Compose would fail to start `api` whenever the profile isn't active,
since `depends_on` normally requires its target to actually be part of
the run. `required: false` keeps the startup-order hint (wait for
Jaeger if it's there) without making it a hard requirement. Same fix
applied to `grafana`'s `depends_on: prometheus`.

**`TRACING_ENABLED`/`METRICS_ENABLED` now default to `false` in
`docker-compose.yml` too** (`${TRACING_ENABLED:-false}`), not
hardcoded `true`. Compose has no native "set this env var only when
profile X is active" mechanism, so without this change, `api` would
spend the lean-stack run retrying OTLP exports against a `jaeger`
hostname that doesn't exist — harmless, but a steady stream of warning
logs. Verified directly: confirmed zero export-warning log lines with
the lean stack, and a healthy Prometheus scrape target with the
observability profile + env vars both on.

## Revisit Triggers

- If remembering to pair the profile flag with the two env vars proves
  annoying in practice, revisit with a Compose override file
  (`docker-compose.observability.yml`) instead, which can set both the
  service list *and* environment overrides in one `-f` flag.

## Consequences

- Default `docker compose up` is faster and lighter; the full
  observability story is one longer, still copy-pasteable command away
  (documented in `README.md`), not a separate mechanism to learn.
- `docker compose ps` after a lean-stack run correctly shows only 3
  containers; `docker compose --profile observability ps` shows all 6.
