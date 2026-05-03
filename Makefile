.PHONY: help install run up down stop sh test unit-test integration-test e2e-test lint format build migrate migration migrate-test

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
	$(DC) run --rm --no-deps $(SERVICE) sh

test: ## Run the full test suite
	$(DC) run --rm $(SERVICE) pytest

unit-test: ## Run unit tests only
	$(DC) run --rm $(SERVICE) pytest tests/unit

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

migration: ## Create a new migration. Usage: make migration m="add products table"
	$(DC) run --rm $(SERVICE) alembic revision --autogenerate -m "$(m)"
