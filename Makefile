.PHONY: help install run up down stop sh test unit-test eval integration-test k8s-up k8s-deploy k8s-smoke k8s-down e2e-test lint format build migrate migration migrate-test reindex

DC = docker compose
SERVICE = api
KIND_CLUSTER = catalog
K8S_NS = catalog
KUBECTL = kubectl --context kind-$(KIND_CLUSTER)

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

install: ## Build the docker image (installs deps)
	$(DC) build

run: ## Start dev server (foreground, --reload)
	$(DC) up

up: ## Start dev server in the background
	$(DC) up -d

down: ## Stop and remove containers
	$(DC) down

stop: ## Stop containers (keep them)
	$(DC) stop

sh: ## Open a shell in the api container
	$(DC) run --rm --no-deps $(SERVICE) sh

test: ## Run the full test suite
	$(DC) run --rm $(SERVICE) pytest

unit-test: ## Run unit tests only
	$(DC) run --rm $(SERVICE) pytest tests/unit

eval: ## Run the evals against the real Claude API (reads the key from .env)
	$(DC) run --rm -v $(CURDIR)/.env:/app/.env:ro $(SERVICE) pytest -m eval -s -p no:cacheprovider tests/evals

integration-test: ## Run integration tests
	$(DC) run --rm $(SERVICE) pytest tests/integration

e2e-test: ## Run end-to-end tests
	$(DC) run --rm $(SERVICE) pytest tests/e2e

lint: ## Run linters (ruff + pylint + mypy)
	$(DC) run --rm --no-deps $(SERVICE) sh -lc "ruff check . && pylint src main.py && mypy src main.py"

format: ## Auto-format code
	$(DC) run --rm --no-deps $(SERVICE) ruff format .

build: ## Build the docker image
	$(DC) build

migrate: ## Apply migrations to the dev database
	$(DC) run --rm $(SERVICE) alembic upgrade head

migrate-test: ## Apply migrations to the test database
	$(DC) run --rm $(SERVICE) sh -lc 'DATABASE_URL=$$TEST_DATABASE_URL alembic upgrade head'

reindex: ## Index catalog products for the assistant (incremental)
	$(DC) run --rm $(SERVICE) python -m contexts.assistant.ui.cli.reindex

migration: ## Create a new migration. Usage: make migration m="add products table"
	$(DC) run --rm $(SERVICE) alembic revision --autogenerate -m "$(m)"

k8s-up: build k8s-deploy ## Build the image and deploy it to a local kind cluster

k8s-deploy: ## Deploy the existing fastapi-api:latest image to the kind cluster
	kind get clusters | grep -qx $(KIND_CLUSTER) || kind create cluster --name $(KIND_CLUSTER)
	kind load docker-image fastapi-api:latest --name $(KIND_CLUSTER)
	$(KUBECTL) apply -f k8s/namespace.yaml
	$(KUBECTL) -n $(K8S_NS) create secret generic catalog-db \
		--from-literal=POSTGRES_USER=catalog --from-literal=POSTGRES_PASSWORD=catalog \
		--from-literal=POSTGRES_DB=catalog \
		--from-literal=DATABASE_URL=postgresql+asyncpg://catalog:catalog@db:5432/catalog \
		--dry-run=client -o yaml | $(KUBECTL) apply -f -
	(grep '^ANTHROPIC_API_KEY=' .env 2>/dev/null || true) | $(KUBECTL) -n $(K8S_NS) create secret generic assistant-llm \
		--from-env-file=/dev/stdin --dry-run=client -o yaml | $(KUBECTL) apply -f -
	$(KUBECTL) apply -k k8s
	$(KUBECTL) -n $(K8S_NS) rollout status statefulset/db --timeout=180s
	$(KUBECTL) -n $(K8S_NS) delete job migrate reindex --ignore-not-found
	$(KUBECTL) apply -f k8s/jobs/migrate.yaml
	$(KUBECTL) -n $(K8S_NS) wait --for=condition=complete job/migrate --timeout=180s
	$(KUBECTL) apply -f k8s/jobs/reindex.yaml
	$(KUBECTL) -n $(K8S_NS) wait --for=condition=complete job/reindex --timeout=180s
	$(KUBECTL) -n $(K8S_NS) rollout restart deployment/api
	$(KUBECTL) -n $(K8S_NS) rollout status deployment/api --timeout=300s

k8s-smoke: ## Call /healthz and GET /products through the api Service
	$(KUBECTL) -n $(K8S_NS) port-forward svc/api 8080:8000 >/dev/null 2>&1 & pid=$$!; \
	sleep 3; \
	curl -fsS http://localhost:8080/healthz && echo && curl -fsS http://localhost:8080/products && echo; \
	status=$$?; kill $$pid; exit $$status

k8s-down: ## Delete the local kind cluster
	kind delete cluster --name $(KIND_CLUSTER)
