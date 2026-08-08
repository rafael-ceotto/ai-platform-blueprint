# syntax=docker/dockerfile:1

# ---- Stage 1: build dependencies into a virtualenv -------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies first so this layer is cached unless deps change.
# README.md is copied alongside pyproject.toml because hatchling reads it
# for the package's `readme` metadata field during the build.
COPY pyproject.toml README.md ./
RUN pip install --upgrade pip \
    && pip install .

COPY backend ./backend
COPY ingestion ./ingestion
COPY retrieval ./retrieval
COPY llm ./llm
COPY observability ./observability

# ---- Stage 2: minimal runtime image -----------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Non-root user for defense in depth.
RUN groupadd --system app && useradd --system --gid app --home-dir /app app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build/backend ./backend
COPY --from=builder /build/ingestion ./ingestion
COPY --from=builder /build/retrieval ./retrieval
COPY --from=builder /build/llm ./llm
COPY --from=builder /build/observability ./observability

RUN mkdir -p /app/data && chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://localhost:8000/api/v1/health', timeout=3).status == 200 else sys.exit(1)"

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
