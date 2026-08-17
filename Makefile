.PHONY: install run ui test lint format typecheck mcp-dev check docker-build docker-up docker-down docker-logs clean \
	terraform-fmt terraform-validate helm-lint helm-template kind-smoke-test kind-smoke-test-clean

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

# --- Terraform / Helm (see docs/adr/0017) -- validate-only, never apply ---

terraform-fmt:
	cd terraform && terraform fmt -check -recursive

terraform-validate:
	cd terraform && terraform init -backend=false && terraform validate

helm-lint:
	helm lint helm/konsole-ai

helm-template:
	helm template konsole-ai helm/konsole-ai
	helm template konsole-ai helm/konsole-ai --set ollama.gpu.enabled=true --set ingress.enabled=true

kind-smoke-test:
	docker compose build api ui
	kind create cluster --name konsole-ai-smoke
	kind load docker-image konsole-ai-api:local --name konsole-ai-smoke
	kind load docker-image konsole-ai-ui:local --name konsole-ai-smoke
	helm install konsole-ai helm/konsole-ai \
		--set api.image.repository=konsole-ai-api --set api.image.tag=local --set api.image.pullPolicy=Never \
		--set ui.image.repository=konsole-ai-ui --set ui.image.tag=local --set ui.image.pullPolicy=Never
	kubectl wait --for=condition=Ready pod --all --timeout=300s || true
	kubectl get pods -o wide

kind-smoke-test-clean:
	kind delete cluster --name konsole-ai-smoke
