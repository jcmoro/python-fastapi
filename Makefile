.PHONY: help install run up down stop sh test unit-test integration-test e2e-test lint format build

DC = docker compose
SERVICE = api

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
	$(DC) run --rm $(SERVICE) sh

test: ## Run the full test suite
	$(DC) run --rm $(SERVICE) pytest

unit-test: ## Run unit tests only
	$(DC) run --rm $(SERVICE) pytest tests/unit

integration-test: ## Run integration tests
	$(DC) run --rm $(SERVICE) pytest tests/integration

e2e-test: ## Run end-to-end tests
	$(DC) run --rm $(SERVICE) pytest tests/e2e

lint: ## Run linters (ruff + pylint + mypy)
	$(DC) run --rm $(SERVICE) sh -lc "ruff check . && pylint src main.py && mypy src main.py"

format: ## Auto-format code
	$(DC) run --rm $(SERVICE) ruff format .

build: ## Build the docker image
	$(DC) build
