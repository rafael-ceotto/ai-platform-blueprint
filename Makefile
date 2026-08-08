.PHONY: install run test lint format typecheck check docker-build docker-up docker-down docker-logs clean

install:
	pip install -e ".[dev]"

run:
	uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest

lint:
	ruff check .

format:
	ruff format .
	ruff check --fix .

typecheck:
	mypy backend ingestion retrieval llm observability

check: lint typecheck test

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f api

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
