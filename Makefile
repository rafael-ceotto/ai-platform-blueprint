.PHONY: install run ui test lint format typecheck mcp-dev check docker-build docker-up docker-down docker-logs clean

install:
	pip install -e ".[dev,ui,mcp]"

run:
	uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

ui:
	cd ui && pip install -r requirements.txt && streamlit run app.py

test:
	pytest

lint:
	ruff check .

format:
	ruff format .
	ruff check --fix .

typecheck:
	mypy backend ingestion retrieval llm observability mcp_server

mcp-dev:
	mcp dev mcp_server/server.py

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
