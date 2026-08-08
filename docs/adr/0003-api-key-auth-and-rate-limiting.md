# ADR-0003: API Access Control — API Keys + In-Memory Rate Limiting

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-08 |
| **Deciders** | AI Platform Blueprint team |
| **Related** | [ADR-0001: Vector Store](0001-vector-store-faiss-vs-qdrant.md) |

## Context

The RAG endpoints (`POST /documents`, `POST /documents/search`) added in
Sprint 2 are open to anyone who can reach the port: no identity, no
throttling. Sprint 3 needs to answer two questions:

1. How do callers authenticate?
2. How do we stop a single caller (buggy client, retry loop, or abuse)
   from monopolizing the LLM/embedding backend?

## Decision Drivers

- **Who calls this API.** Per the C4 model, the platform's consumers are
  services/developers integrating over REST — not end users logging in
  through a browser session.
- **Operational surface.** Same principle as ADR-0001: no extra
  infrastructure (no auth server, no Redis) for the current MVP scale.
- **Time to first working system.** A lightweight mechanism that's
  correct for a single-process deployment beats a more "complete" one that
  isn't built yet.
- **Migration cost later.** Whatever ships now must not block moving to a
  real key-management system or a shared rate-limit backend.

## Options Considered

### Auth: Option A — Static API keys (`X-API-Key` header)

**Pros**
- No auth server, no login flow, no session state.
- Matches machine-to-machine/service integration, the platform's actual
  consumer today.
- Trivial to test and to reason about.

**Cons**
- No per-key scopes, expiry, or rotation without a redeploy.
- Keys are bearer secrets — anyone who has one has full access.

### Auth: Option B — OAuth2 / JWT

**Pros**
- Standard, supports scopes, expiry, and third-party identity providers.
- Necessary if end users ever authenticate directly (not just services).

**Cons**
- Needs a token issuer/auth server (or a third-party IdP) — real
  infrastructure the current consumer base doesn't need yet.
- Meaningfully more code and more failure modes to test.

### Rate limiting: Option A — In-memory fixed-window counter

**Pros**
- Zero extra infrastructure; a plain dict keyed by API key.
- Simple to implement, test (injectable clock), and reason about.

**Cons**
- Per-process only — multiple uvicorn workers or replicas each enforce
  their own limit, so the effective limit multiplies with instance count.
- Fixed windows allow bursts at window boundaries (up to ~2x the limit
  across a boundary), unlike a sliding-window or token-bucket scheme.

### Rate limiting: Option B — Redis-backed / `slowapi`

**Pros**
- Shared state across processes/replicas — the limit means what it says
  regardless of how many workers are running.
- `slowapi` covers sliding-window and other strategies out of the box.

**Cons**
- Requires Redis (or another shared store) as a new operational
  dependency — disproportionate for current scale, same reasoning as
  ADR-0001's rejection of Qdrant for Sprint 1.

## Decision

**Adopt static API keys via `X-API-Key`, checked against a configured
list (`Settings.API_KEYS`), plus a hand-rolled in-memory fixed-window rate
limiter keyed by API key.**

Both endpoints require a valid key; `/health` and `/health/ready` stay
public and unlimited since they're infra probes, not the product surface.
`API_KEYS` defaults to a single working local key so the Quickstart
doesn't require extra setup; an explicitly empty list fails closed
(rejects everything) rather than silently allowing all requests.

## Revisit Triggers

- **Auth**: end users need to authenticate directly (not just services);
  keys need per-scope permissions, expiry, or rotation without a
  redeploy; or key issuance needs to be self-service. → move to OAuth2/JWT
  with a real identity provider.
- **Rate limiting**: the API runs behind more than one process/replica
  and limits need to be enforced consistently across them; or a smoother
  (sliding-window/token-bucket) strategy is required. → move to a
  Redis-backed limiter (or `slowapi` with a Redis storage backend).

## Consequences

- `backend/api/security.py` and `backend/api/rate_limit.py` hold the two
  decisions as small, independently testable units; `backend/api/deps.py`
  wires them into FastAPI as `require_api_key` / `enforce_rate_limit`.
- A future migration to OAuth2 or a shared rate-limit backend is a new
  implementation behind the same dependency functions, not a rewrite of
  every endpoint that calls them.
- Running more than one API process/replica currently means each one
  enforces its own rate-limit window independently.
