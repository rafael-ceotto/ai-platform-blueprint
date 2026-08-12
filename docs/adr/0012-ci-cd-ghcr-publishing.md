# ADR-0012: CI/CD — Vulnerability Scanning + GHCR Publishing

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-12 |
| **Deciders** | Konsole.ai team |
| **Related** | none |

## Context

CI (`.github/workflows/ci.yml`) ran lint/typecheck/test and a build-only
Docker check on every push/PR, but produced no artifact and had no
security scanning. There's no live deploy target yet (that's the K8s/
cloud discussion this ADR is a prerequisite for), so true continuous
*deployment* isn't possible yet — but continuous *delivery* of a
versioned, scanned image is, and is worth having in place before that
discussion.

## Decision

**Three jobs**, in order:

1. `lint-and-test` (unchanged, + `pip-audit` on the 3.12 leg) — ruff,
   mypy, pytest, now also auditing Python dependencies for known CVEs.
2. `docker-build` — builds both images (`api`, `ui`) via a matrix,
   without pushing, then scans each with **Trivy** (CRITICAL/HIGH,
   fixable only) and uploads results to GitHub's Security tab as SARIF.
   Runs on every push and PR — this is the gate.
3. `publish` — **only on push to `main`** (never on PRs, so unmerged
   branches never produce a public image), builds and pushes both
   images to **GitHub Container Registry** (`ghcr.io`), tagged `latest`
   + `sha-<short-sha>`, using the workflow's built-in `GITHUB_TOKEN` —
   no new secrets to manage.

**Every third-party Action is pinned to a full commit SHA, not a
version tag** (`uses: owner/repo@<40-char-sha> # vX.Y.Z` comment for
readability). This isn't precautionary theater: `aquasecurity/
trivy-action` — one of the exact actions this ADR adds — had 76 of 77
version tags force-pushed to credential-stealing malware in March 2026
(a ~12-hour window before detection; fully resolved, but tags are
mutable and can be rewritten again). Commit SHAs cannot be rewritten.
Applied consistently to *all* actions in this workflow, not just
Trivy, since the same risk applies to any of them.

**`.trivyignore`** at the repo root suppresses two findings
(`GHSA-6v7p-g79w-8964` / msgpack, `CVE-2025-47273` / setuptools) —
verified directly, not assumed, that both come from **pip's own
vendored bundle** (`pip/_vendor/msgpack`, pip's internal setuptools
bootstrap), not a package this project's code imports or depends on
(confirmed via `find /opt/venv -iname '*msgpack*'` inside the built
image — the only match is `pip/_vendor/msgpack`; the actual msgpack
library this project uses is the unrelated, unaffected `ormsgpack`).
Not independently upgradable through this project's `Dockerfile` —
only a newer `pip` release changes its own vendored copies.

## Revisit Triggers

- A live deploy target exists (K8s cluster, cloud VM, etc.) → extend
  `publish` into real continuous deployment.
- The base Python image or `pip` version bumps → re-check whether the
  `.trivyignore` entries are still needed; remove them if resolved
  upstream.
- If pairing `--profile observability` with two env vars (ADR-0011)
  and now a three-job pipeline starts feeling like too many moving
  pieces to hold in your head, that's a signal to simplify, not a
  reason to keep adding more.

## Consequences

- `docker compose pull` isn't needed for local dev (images still build
  locally per `docker-compose.yml`), but anyone can now also
  `docker pull ghcr.io/rafael-ceotto/konsole-ai-api:latest` directly.
- Every push to `main` produces a scanned, versioned, publicly
  pullable image — the actual artifact a deploy step would consume,
  whenever one exists.
- New CI jobs mean slightly longer pipeline time (Docker builds +
  Trivy scans, per image, matrixed) — acceptable for the security
  and delivery value gained.
